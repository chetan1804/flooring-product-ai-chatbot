# AI-Powered Flooring Product Recommendation Chatbot

This repository currently implements Steps 1 through 9: bounded-memory catalog profiling,
PostgreSQL ingestion, embeddings, hybrid retrieval, and Pydantic-validated AI customer
requirement extraction, plus a LangGraph conversational agent and deterministic flooring
business-rule ranking with clickable catalog-backed recommendation cards, a FastAPI
backend, a framework-independent JavaScript widget, and registered multi-site installation.

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

The retrieval score only fuses structured and semantic candidate signals. The separate
Step 6 ranking layer applies flooring room and household rules to those candidates.

## Customer requirement extraction

The extractor uses the OpenAI Responses structured-output parser with a strict Pydantic
model. Customer text is isolated as an untrusted user message. Model output is validated
again in application code and mapped only to vocabulary values loaded from the current
database. Unknown or ambiguous values remain contextual terms and never become arbitrary
SQL fields or values.

```bash
export DATABASE_URL='postgresql://flooring_app:password@localhost:5432/flooring'
export OPENAI_API_KEY='server-side-secret'
export REQUIREMENT_EXTRACTION_MODEL='gpt-5-mini'

flooring-extract \
  'I need warm light-oak luxury vinyl for a busy kitchen under $6 per square foot.'
```

The command returns both the source extraction and the normalized result. For example,
`luxury vinyl` maps to `lvt` only when `lvt` exists in the database vocabulary. Rooms,
pets, kids, traffic, installation, durability, and subjective appearance preferences are
retained for the later conversational and business-rule steps.

## Conversational recommendation agent

The LangGraph agent remembers validated flooring preferences by conversation thread,
detects missing information, asks at most one focused clarification per turn, and then
orchestrates the existing hybrid product search. It asks about product type, room/use,
and appearance in priority order, without repeating a question the customer has already
declined to answer.

All project commands automatically read `.env` when it exists, while existing shell
environment variables retain precedence. After setting up the database, ingesting the
catalog, and generating embeddings, launch an interactive conversation with:

```bash
flooring-chat --thread-id demo-customer
```

Example interaction:

```text
You: I need flooring for my kitchen.
Assistant: What type of flooring would you prefer? Available options include ...
You: Luxury vinyl.
Assistant: Do you have a preferred color, shade, style, material, or overall look?
You: Light natural oak.
Assistant: I ranked 5 matching products.
  1. Coastal Oak (ABC123, $4.75)
     Matches your requested color: Light Oak.
     https://exampleflooring.com/?s=ABC123
```

The command uses LangGraph's in-memory checkpointer, so thread history survives turns
within that running process and resets when it exits. The graph accepts an injected
checkpointer for a durable production deployment. Candidate retrieval in this step is
followed by deterministic Step 6 ranking and Step 7 recommendation presentation.

## Flooring business rules and ranking

Business rules live outside LLM prompts and score only retrieved catalog products. The
default ranker selects five products using these normalized weights:

| Component | Default weight |
| --- | ---: |
| Hybrid retrieval relevance | 40% |
| Room suitability | 20% |
| Lifestyle and durability | 15% |
| Budget fit | 15% |
| Catalog availability | 10% |

`RankingConfig` and `RankingWeights` can be injected when constructing the agent, allowing
weights and result count to change without editing rule code. Each ranked candidate
includes the raw score, normalized weight, weighted contribution, and reasons for every
component.

The initial domain layer handles moisture-sensitive rooms, kitchen durability, bedroom
comfort, pets, kids, traffic, and residential/commercial use. It uses confirmed product
columns and catalog metadata such as `application`, `features`, `in_stock`, and
`wear_layer`. A missing price receives a neutral budget score and is never interpreted as
zero.

Run the interactive agent to see ordered SKUs and final scores:

```bash
flooring-chat --thread-id ranking-demo
```

## Recommendation cards and product links

For the local `flooring-chat` CLI, set the storefront origin in server-side configuration.
It must be an HTTP(S) origin without a path, query, fragment, or embedded credentials:

```bash
CLIENT_DOMAIN=https://exampleflooring.com
```

The application—not the LLM—URL-encodes each catalog SKU and generates links in this
fixed format:

```text
https://exampleflooring.com/?s=ABC123
```

Each recommendation DTO includes the catalog name, SKU, swatch, gallery image when
available, positive price when available, an allow-listed set of important catalog
attributes, deterministic factual reasons, product URL, and its explainable ranking
score. Missing product values remain absent instead of being invented. The hosted API
instead resolves domains from its registered multi-site configuration.

## FastAPI backend and embeddable widget

The hosted API uses Pydantic request/response contracts and initializes its database pool,
catalog vocabulary, AI clients, and shared LangGraph agent during application lifespan.
Create the deployment-specific site registry from the sanitized example, then point `.env`
to it:

```bash
cp config/sites.example.json config/sites.json
```

```dotenv
SITE_CONFIG_PATH=config/sites.json
```

Start the development server:

```bash
source .venv/bin/activate
flooring-api --host 127.0.0.1 --port 8000 --reload
```

Available routes:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Service health |
| `GET` | `/api/config/{site_code}` | Widget display configuration |
| `POST` | `/api/session` | Server-generated conversation session |
| `POST` | `/api/chat` | Validated conversational recommendations |
| `GET` | `/widget.js` | Cacheable standalone widget asset |

The initial session registry and LangGraph checkpointer are in memory, so sessions reset
when the process restarts. Durable distributed session persistence is production work for
a later step.

Embed the floating widget from the API origin:

```html
<script
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001"
  data-position="bottom-right">
</script>
```

Or render it inside an existing element:

```html
<div id="flooring-chatbot"></div>
<script
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001"
  data-target="#flooring-chatbot">
</script>
```

The widget has no React or client-library dependency. It uses Shadow DOM isolation where
available, creates content with DOM text nodes instead of injecting API HTML, shows
loading/API errors, and renders catalog recommendation cards with safe external links.

## Multi-site configuration and one-line installation

Each entry in `config/sites.json` registers one client and controls its product-link domain,
allowed browser origins, default floating position, and chatbot title:

```json
{
  "sites": [
    {
      "site_code": "CLIENT001",
      "domain": "https://exampleflooring.com",
      "allowed_origins": ["https://exampleflooring.com"],
      "position": "bottom-right",
      "chatbot_title": "Flooring Assistant"
    }
  ]
}
```

Domains and origins must be HTTP(S) origins without paths, credentials, queries, or
fragments. The product domain must also appear in `allowed_origins`. Duplicate site codes
and unknown sites are rejected. Browser sessions are bound to their registered site, and
config, session, and chat requests with a different `Origin` are rejected.

Install the registered floating chatbot with one script include:

```html
<script
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001">
</script>
```

The registry supplies the default position. A page may override floating placement:

```html
<script
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001"
  data-position="bottom-left">
</script>
```

Or render inside a specific element:

```html
<div id="flooring-chatbot"></div>
<script
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001"
  data-target="#flooring-chatbot">
</script>
```

The browser sends only `site_code` and the server-generated session ID. Product links are
always generated from the domain in the server registry and the catalog SKU; a browser
cannot supply or override the destination domain.
