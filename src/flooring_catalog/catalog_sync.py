"""One-command catalog ingestion, reconciliation, and embedding refresh."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from psycopg import Connection

from flooring_catalog.embeddings import EmbeddingProvider, update_product_embeddings
from flooring_catalog.ingestion import ingest_catalog

SYNC_ADVISORY_LOCK_ID = 734_652_901


@dataclass(frozen=True, slots=True)
class CatalogSyncStats:
    run_id: UUID
    source_records: int
    upserted_records: int
    rejected_records: int
    deactivated_records: int
    embedded_records: int


def _acquire_lock(connection: Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (SYNC_ADVISORY_LOCK_ID,))
        row = cursor.fetchone()
    return bool(row and row[0])


def _release_lock(connection: Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (SYNC_ADVISORY_LOCK_ID,))


def _start_run(
    connection: Connection,
    run_id: UUID,
    source_name: str,
    authoritative_snapshot: bool,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
INSERT INTO catalog_sync_runs (run_id, source_name, authoritative_snapshot, status)
VALUES (%s, %s, %s, 'running')
""",
            (run_id, source_name, authoritative_snapshot),
        )
    connection.commit()


def _deactivate_missing_products(connection: Connection, run_id: UUID) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
UPDATE catalog_products
SET status = 'inactive', updated_at = now()
WHERE status = 'active'
  AND last_seen_sync_id IS DISTINCT FROM %s
""",
            (run_id,),
        )
        affected = cursor.rowcount
    connection.commit()
    return affected


def _finish_run(
    connection: Connection,
    run_id: UUID,
    *,
    status: str,
    source_records: int | None = None,
    upserted_records: int | None = None,
    deactivated_records: int | None = None,
    embedded_records: int | None = None,
) -> None:
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute(
            """
UPDATE catalog_sync_runs
SET status = %s,
    source_records = %s,
    upserted_records = %s,
    deactivated_records = %s,
    embedded_records = %s,
    finished_at = now()
WHERE run_id = %s
""",
            (
                status,
                source_records,
                upserted_records,
                deactivated_records,
                embedded_records,
                run_id,
            ),
        )
    connection.commit()


def synchronize_catalog(
    connection: Connection,
    catalog_path: str | Path,
    embedding_provider: EmbeddingProvider,
    *,
    batch_size: int = 1000,
    embedding_batch_size: int = 100,
    max_text_characters: int = 12_000,
    authoritative_snapshot: bool = False,
) -> CatalogSyncStats:
    """Synchronize one catalog while preventing overlapping scheduled runs."""

    source = Path(catalog_path)
    run_id = uuid4()
    if not _acquire_lock(connection):
        raise RuntimeError("another catalog synchronization is already running")
    started = False
    try:
        _start_run(connection, run_id, source.name, authoritative_snapshot)
        started = True
        ingestion = ingest_catalog(
            connection,
            source,
            batch_size=batch_size,
            sync_id=run_id,
        )
        deactivated = (
            _deactivate_missing_products(connection, run_id) if authoritative_snapshot else 0
        )
        embeddings = update_product_embeddings(
            connection,
            embedding_provider,
            batch_size=embedding_batch_size,
            max_text_characters=max_text_characters,
        )
        stats = CatalogSyncStats(
            run_id=run_id,
            source_records=ingestion.source_records,
            upserted_records=ingestion.upserted_records,
            rejected_records=ingestion.rejected_records,
            deactivated_records=deactivated,
            embedded_records=embeddings.products_embedded,
        )
        _finish_run(
            connection,
            run_id,
            status="succeeded",
            source_records=stats.source_records,
            upserted_records=stats.upserted_records,
            deactivated_records=stats.deactivated_records,
            embedded_records=stats.embedded_records,
        )
        return stats
    except Exception:
        if started:
            _finish_run(connection, run_id, status="failed")
        raise
    finally:
        _release_lock(connection)
