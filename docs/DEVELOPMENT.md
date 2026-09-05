# Development Guide

> For a full system overview — architecture, database schema, deployment, known
> gaps and decision history — see **[HANDOVER.md](HANDOVER.md)**. This file
> covers day-to-day development tasks.

## Local Development Setup

### 1. Python Backend

```bash
# From the ATheria root
python3.11 -m venv .venv
source .venv/bin/activate

# Install all packages in editable mode
pip install -e ".[dev]"
pip install -e packages/atheria-contracts
pip install -e packages/atheria-llm
```

### 2. Database

SQLite is the default — no server needed. Use an **absolute** path so the API
(run from the repo root) and Alembic (run from `backend/`) agree on the file:

```bash
cd backend
ATHERIA_DATABASE_URL="sqlite:///$(cd .. && pwd)/atheria.db" alembic upgrade head
cd ..
```

Put the same value in `.env` as `ATHERIA_DATABASE_URL` with the async driver:

```bash
ATHERIA_DATABASE_URL=sqlite+aiosqlite:////absolute/path/to/ATheria/atheria.db
```

### 3. Run the API

`--reload-include '*.yaml'` matters: prompt templates are cached at startup, so
without it prompt edits are ignored until you restart manually.

```bash
uvicorn backend.app.main:app --reload --reload-include '*.yaml' --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

UI on <http://localhost:5173>, API docs on <http://localhost:8000/docs>.

### 5. PostgreSQL instead of SQLite (optional)

The same code runs against Postgres; only the URL changes.

```bash
docker compose up -d db
export ATHERIA_DATABASE_URL="postgresql+asyncpg://atheria:atheria@localhost:5432/atheria"
cd backend && alembic upgrade head
```

---

## Code Style & Quality

### Python

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy backend/ packages/ --ignore-missing-imports

# Tests
pytest -v
```

### Frontend

```bash
cd frontend
npm run typecheck    # TypeScript type checking
npm run lint         # ESLint
npm run build        # Production build
```

---

## Adding a New API Endpoint

1. Create the route handler in `backend/app/api/v1/your_endpoint.py`
2. Import and register the router in `backend/app/main.py`
3. Add types to `packages/atheria-contracts` if new data shapes are needed
4. Add corresponding TypeScript types in `frontend/src/types/`

**Conventions to follow:** tenant/actor/trace come from `x-tenant-id`,
`x-actor-id`, `x-trace-id` headers with defaults; the DB session comes from
`Depends(get_session)`; and **services `flush()` while handlers `commit()`** —
never commit inside a service.

---

## Adding a New Intake Channel

Connectors are the extension point. Downstream code depends only on
`SourceRecord`, so a new channel changes nothing else.

1. Create `backend/app/connectors/<channel>.py`
2. Build the record with `connectors.base.build_source_record(...)` — it handles
   ULID assignment, content hashing, and Day 0
3. Pick the right `Channel` and `ChannelClass` from the contracts enums.
   `ChannelClass` drives regulatory obligation rules, so it matters:
   `solicited` (we asked), `earned` (public mention), `literature`, `partner`
4. Render the payload into labelled text. **Omit empty fields entirely** rather
   than writing "unknown" — a blank field must not read to the model as a
   positive assertion of absence
5. Add an intake route that persists via
   `TriageService.persist_source_record()` then calls `triage()`
6. For polling channels, pass `known_content_hashes` from
   `TriageService.existing_content_hashes()` to skip duplicates

`connectors/pubmed.py` is the reference implementation for a remote source
(retry with backoff, XML parsing, dedup). `connectors/web_form.py` is the
reference for a submitted payload.

---

## Adding a New Rule Set

1. Create `backend/app/rules/<name>.py` with `RULE_ID`, `RULE_SET_VERSION`, and
   an `evaluate_*` function
2. Keep it a **pure function** — no I/O, no model calls, no clock, no randomness
3. Always return a `RuleEvaluation` with `inputs`, `input_provenance`,
   `fired_rules`, `explanation`, `outcome`
4. Write the exhaustive truth-table test first (see `test_validity_rule.py`,
   which covers all 16 combinations of four booleans)
5. Record the decision with `AuditService.record_rule_evaluation(...)`
6. Expose the rule set under `/api/v1/triage/rules/...` for transparency
7. **Bump `RULE_SET_VERSION` on every logic change** so historical decisions stay
   attributable to the rules that made them

If an input cannot be determined, escalate — never guess.

---

## Adding a New Database Table

1. Add the SQLAlchemy model in `backend/app/models/`
2. Import it in `backend/migrations/env.py` (so Alembic sees it)
3. Generate a migration:
   ```bash
   cd backend
   alembic revision --autogenerate -m "add_your_table"
   ```
4. Review the generated migration, then apply:
   ```bash
   alembic upgrade head
   ```

**Rule:** Every table MUST have `tenant_id` (use `TenantMixin`).

---

## Working with Fixtures

Golden fixtures live in `/fixtures/`. They serve two purposes:

1. **Frontend development** — the workbench renders against these without a DB
2. **Test baselines** — used as expected outputs in evaluation and golden-set testing

To add a new fixture:
1. Author the JSON following the `CanonicalCase` schema
2. Include realistic provenance (model_id, prompt_version, evidence spans)
3. Name it `golden_case_NN_description.json`
4. It auto-appears at `GET /api/v1/fixtures/cases`

---

## Working with the LLM layer

Call sites never import a vendor SDK. They ask the factory for a provider and
get the same interface regardless of engine, so switching vendors is a config
change rather than a code change.

```python
from atheria_llm import LLMConfig, get_provider

provider = get_provider(
    provider="bedrock",  # or "gemini"
    aws_region="ap-south-1",
    bedrock_model_id="apac.amazon.nova-lite-v1:0",
)

response = provider.invoke(
    "Source text:\n---\nDr. Smith reports...\n---",
    LLMConfig(
        prompt_version="triage_icsr_v1.0",
        system_prompt="You are a pharmacovigilance triage assistant...",
        output_schema={"type": "object", "properties": {...}},
        max_tokens=1200,
        tenant_id="acme_pharma",
        trace_id="trc_001",
    ),
)

data = response.require_structured()  # raises if the model returned no JSON
record = response.record  # model_id, prompt_version, tokens, latency
```

Inside the app, use the cached accessors instead of building a provider
per call:

```python
from backend.app.core.llm import get_llm_provider, get_prompt_registry
```

### Choosing a model

Bedrock rejects **bare model IDs** for on-demand invocation — you must use an
inference-profile ID (`apac.` / `us.` / `global.` prefix for your region).

Verified against the live API:

| Model | Works | Notes |
|-------|-------|-------|
| `apac.amazon.nova-lite-v1:0` | Yes | Current default. Cheapest that honours the full triage schema |
| `apac.amazon.nova-micro-v1:0` | Partly | Cheaper, but **silently omits** schema fields — do not use |
| `global.anthropic.claude-sonnet-4-5-...` | Yes | Much stronger, ~20x the cost |
| `openai.gpt-oss-120b-1:0` | Yes | `us-west-2` only; reasoning tokens need `max_tokens` >= 4000 |

### Switching to Gemini

```bash
export ATHERIA_LLM_PROVIDER=gemini
export ATHERIA_GEMINI_API_KEY=...
```

The Gemini provider is implemented and unit-tested. Note that
`generativelanguage.googleapis.com` is blocked on networks with TLS-inspecting
proxies; the provider raises a clear connectivity error in that case.

---

## Working with Prompts

Prompts are versioned YAML files loaded at startup:

```yaml
# backend/prompts/extraction_patient.yaml
name: extraction_patient
version: "1.0"
model_id: anthropic.claude-sonnet-4-20250514
max_tokens: 2048
temperature: 0.0
system_prompt: |
  You are a pharmacovigilance extraction agent. Extract patient
  demographics from the provided source text...
user_template: |
  Source text:
  {source_text}

  Extract: age, sex, weight, height.
output_schema:
  type: object
  properties:
    age:
      type: object
      properties:
        value: {type: number}
        unit: {type: string}
    sex:
      type: string
      enum: [male, female, unknown]
```

Load and use:
```python
from atheria_llm import PromptRegistry

registry = PromptRegistry("backend/prompts")
template = registry.get_or_raise("extraction_patient")
```

---

## Key Conventions

| Convention | Rationale |
|------------|-----------|
| `tenant_id` on every table and S3 key | Multi-tenancy by construction |
| `Provenanced[T]` wrapper on every clinical field | Inspection readiness |
| Structured logging with contextvars | Queryable, correlated logs |
| Hash-chained audit events | Tamper-evidence for inspectors |
| ULIDs for all IDs | Time-sortable, globally unique |
| Immutable case versions | "Show me what it looked like at time T" |
| Rules produce `rule_id` + `rule_set_version` | "Which rule decided this?" |
| AI produces `model_id` + `prompt_version` | "Which model/prompt produced this?" |
| Fail loud: typed errors, terminal states, visible work items | Never silent failures |
| Evidence spans: source_record_id + locator + quote | Click any field → see the source |
