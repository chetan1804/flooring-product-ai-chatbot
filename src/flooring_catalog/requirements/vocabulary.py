"""Load canonical filter values from the searchable PostgreSQL catalog."""

from __future__ import annotations

from psycopg import Connection

from flooring_catalog.requirements.models import CatalogVocabulary

VOCABULARY_COLUMNS = {
    "product_types": "z_prod_type",
    "brands": "brand",
    "materials": "material",
    "colors": "color",
    "styles": "style",
}


class CatalogVocabularyRepository:
    """Read distinct values using a fixed allow-list of schema-owned columns."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def load(self) -> CatalogVocabulary:
        values: dict[str, tuple[str, ...]] = {}
        with self._connection.cursor() as cursor:
            for vocabulary_field, column in VOCABULARY_COLUMNS.items():
                # Column identifiers are developer-owned constants, never request input.
                cursor.execute(
                    f"""
SELECT DISTINCT btrim({column})
FROM catalog_products
WHERE {column} IS NOT NULL AND btrim({column}) <> ''
ORDER BY btrim({column})
"""
                )
                values[vocabulary_field] = tuple(row[0] for row in cursor.fetchall())
        return CatalogVocabulary.model_validate(values)

