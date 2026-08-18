# AI-Powered Flooring Product Recommendation Chatbot

This repository currently implements Steps 1 through 3: bounded-memory catalog profiling,
eligibility validation, PostgreSQL ingestion, batched product embeddings, parameterized
structured filtering, pgvector semantic retrieval, and hybrid candidate fusion. LLM
requirement extraction, business ranking, API, and widget functionality are deferred.

## Setup

Create the virtual environment before installing or running project code:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Profile the catalog

```bash
flooring-profile /absolute/path/to/products.json \
  --output reports/product_profile.json
```

The source file must be a top-level JSON array of product objects. It is processed in
bounded chunks instead of being loaded into memory. Reports contain discovered fields,
a sanitized sample, product type and status distributions, eligibility counts, per-field
missing-value/type statistics, and duplicate SKU statistics.

Numeric zero and boolean false are retained as real values. Numeric zeros are counted
separately so that missing prices are never silently converted to zero.

## Verify

```bash
pytest
ruff check .
```

## PostgreSQL ingestion

The database must be PostgreSQL with the pgvector extension available. Copy the example
configuration, replace the credentials, and export it through your preferred environment
manager. Do not commit `.env` files.

```bash
cp .env.example .env
export DATABASE_URL='postgresql://flooring_app:password@localhost:5432/flooring'
export INGEST_BATCH_SIZE=1000
flooring-ingest /absolute/path/to/products.json --apply-schema
```

The command streams the source file, rejects non-active products and invalid swatches,
requires SKU for database identity, converts unavailable/non-positive prices to SQL
`NULL`, and commits parameterized upserts in bounded batches. Re-running it updates the
same SKU rather than creating duplicates.

To run the optional real-database test against a disposable test database:

```bash
export TEST_DATABASE_URL='postgresql://user:password@localhost:5432/flooring_test'
pytest -m integration
```

## Embeddings and hybrid retrieval

Apply the latest idempotent migrations before embedding. The schema stores 1,536-value
vectors and creates an HNSW cosine-distance index. Embedding source text is assembled only
from fields confirmed in the catalog profile. Updating a searchable product field
automatically invalidates its old vector.

```bash
export DATABASE_URL='postgresql://flooring_app:password@localhost:5432/flooring'
export OPENAI_API_KEY='server-side-secret'
export EMBEDDING_MODEL='text-embedding-3-small'

# Reapply all migrations, then ingest any catalog changes.
flooring-ingest /absolute/path/to/products.json --apply-schema

# Generate vectors only for products with missing or stale embeddings.
flooring-embed
```

Exact structured filters work without an embedding API call:

```bash
flooring-search --type lvt --brand 'Shaw Floors' --waterproof yes --limit 10
```

Subjective language invokes semantic search, while exact filters still constrain the SQL
candidate set:

```bash
flooring-search \
  --query 'warm natural oak with a modern appearance' \
  --type lvt \
  --waterproof yes \
  --limit 10
```

The retrieval score only fuses structured and semantic candidate signals. Flooring room
rules and final recommendation ranking intentionally belong to Step 6.
