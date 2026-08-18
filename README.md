# AI-Powered Flooring Product Recommendation Chatbot

This repository currently implements Step 1 only: environment setup, bounded-memory
JSON analysis, reusable product eligibility validation, dataset profiling, and tests.
Database, search, LLM, API, and widget functionality are intentionally deferred.

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

