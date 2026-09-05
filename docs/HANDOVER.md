# Atheria — Engineering Handover

**Version:** 0.2.0 · **Last verified:** 5 September 2026
**Status:** Working prototype. ICSR identification (intake → triage → validity decision) runs end to end.

This document is written for an engineer taking over the codebase with no prior
context. It covers what the system does, how it is built, how to run it, how to
deploy it, the database schema, and the known gaps.

---

## Table of contents

1. [What this system does](#1-what-this-system-does)
2. [Domain primer for engineers](#2-domain-primer-for-engineers)
3. [Architecture](#3-architecture)
4. [Tech stack](#4-tech-stack)
5. [Repository layout](#5-repository-layout)
6. [Local setup](#6-local-setup)
7. [Configuration reference](#7-configuration-reference)
8. [Database schema](#8-database-schema)
9. [API reference](#9-api-reference)
10. [The LLM layer](#10-the-llm-layer)
11. [The rules engine](#11-the-rules-engine)
12. [Frontend](#12-frontend)
13. [Testing](#13-testing)
14. [Deployment](#14-deployment)
15. [Known gaps and next steps](#15-known-gaps-and-next-steps)
16. [Troubleshooting](#16-troubleshooting)
17. [Decision log](#17-decision-log)

---

## 1. What this system does

Atheria automates pharmacovigilance (drug safety) intake. Right now it does one
job completely: **decide whether an inbound report is a valid ICSR**
(Individual Case Safety Report).

Two intake channels feed it:

| Channel | What it is |
|---|---|
| **Web form** | A physician, pharmacist, or patient submits a suspected adverse reaction |
| **PubMed literature** | Scheduled screening of published literature for adverse reactions |

For each inbound record the system:

1. Stores the raw content immutably with a SHA-256 hash (the *evidence vault*)
2. Asks a language model to report what the text says about the four ICSR
   minimum criteria, quoting evidence verbatim
3. Runs a **deterministic, versioned rule** (`val_001`) over those four facts to
   decide `valid_icsr` / `potential_icsr` / `non_icsr`
4. Writes a hash-chained audit trail of both the AI proposal and the rule decision
5. Surfaces the result in a reviewer's inbox with click-to-highlight evidence

### The governing principle

> **The AI proposes, the rules decide, a human approves.**

This is not a slogan; it is enforced structurally. The model is forbidden — by
prompt instruction *and* by code path — from deciding validity. It only reports
observations. A pure function makes the regulatory call. This matters because:

- **Auditability.** Regulators ask "which rule decided this, and why?" A model
  cannot answer that. A versioned rule can.
- **Reproducibility.** Rules are pure functions, so the same inputs plus the
  same `rule_set_version` always produce the same decision — years later.
- **Honesty about uncertainty.** When data is missing, the rule *escalates* to a
  human rather than guessing.

---

## 2. Domain primer for engineers

You do not need pharmacovigilance experience, but these terms appear throughout
the code.

| Term | Meaning |
|---|---|
| **ICSR** | Individual Case Safety Report — the regulatory unit of "one patient had one or more adverse reactions to one or more drugs" |
| **The four minimum criteria** | An ICSR is only valid if it has: an identifiable **patient**, an identifiable **reporter**, a **suspect product**, and an **adverse event**. Missing any one changes the outcome. |
| **Adverse event (AE)** | Any unwanted medical occurrence following medicine use |
| **Day 0 / awareness date** | The date the company first became aware of the report. Regulatory reporting clocks start here, so it is **immutable once written** (`source_records.awareness_datetime`) |
| **Seriousness** | A formal classification (death, life-threatening, hospitalisation, disability, congenital anomaly, other medically important). Not yet implemented — we only capture a `seriousness_signal` flag today |
| **Provenance** | For every value: who or what produced it, from what evidence, with what confidence |
| **Evidence span** | A pointer into the source text (`char_start`/`char_end` + verbatim quote) proving where a value came from |
| **MedDRA** | The licensed medical terminology dictionary used to code reactions. **Out of scope** — requires a licence |
| **E2B(R3)** | The XML standard for transmitting ICSRs to regulators. Out of scope for now |
| **Tenant** | A pharmaceutical company. Every table and storage key is tenant-scoped |

### The three possible outcomes

| Outcome | Meaning | What a reviewer does |
|---|---|---|
| `valid_icsr` | All four criteria present | Proceed to full case processing |
| `potential_icsr` | Product + event present, but patient or reporter missing | **Follow up** to obtain the missing information |
| `non_icsr` | No suspect product or no adverse event | No reportable safety signal; file and close |

---

## 3. Architecture

### Pipeline

```
┌───────────────┐
│   INTAKE      │  connectors/web_form.py, connectors/pubmed.py
│               │  → SourceRecord (channel-agnostic envelope)
└───────┬───────┘  → SHA-256 content hash, Day 0 stamped
        │
┌───────▼───────┐
│ EVIDENCE VAULT│  core/evidence.py
│               │  Immutable, write-once. Filesystem or MinIO.
└───────┬───────┘  Key: {tenant}/{channel}/{yyyy}/{mm}/{dd}/{id}/raw.txt
        │
┌───────▼───────┐
│  AI PROPOSES  │  services/triage_service.py::_propose
│               │  Model reads text → reports 4 criteria + verbatim quotes
└───────┬───────┘  Records model_id + prompt_version. Decides NOTHING.
        │
┌───────▼───────┐
│ RULES DECIDE  │  rules/validity.py::evaluate_validity
│               │  Pure function → ICSROutcome + RuleEvaluation trace
└───────┬───────┘  Records rule_id + rule_set_version
        │
┌───────▼───────┐
│    PERSIST    │  source_records.triage_result (JSON)
│               │  + pipeline_runs / pipeline_stages
└───────┬───────┘  + audit_events (hash-chained)
        │
┌───────▼───────┐
│ HUMAN REVIEWS │  Inbox UI. Read-only. Evidence highlighting.
└───────────────┘
```

### Why the layers are separated this way

**Connectors emit a channel-agnostic `SourceRecord`.** Adding email, social
media, or a partner file feed means writing one connector; nothing downstream
changes. This is the single most important extensibility decision in the
codebase.

**The evidence vault is separate from the database.** The database holds
decisions; the vault holds the bytes we received. Provenance is only credible if
the original artefact still exists unchanged.

**The LLM sits behind a provider interface.** No service imports `boto3`.
Switching vendors is a config change (see [section 10](#10-the-llm-layer)).

**Rules are pure functions in their own package.** No I/O, no model calls, no
randomness. They can be unit-tested exhaustively and replayed at any time.

### Request lifecycle

1. `RequestAuditMiddleware` binds `request_id`, `trace_id`, `tenant_id` into
   structlog contextvars, so every log line in the request is correlated
2. `GlobalErrorMiddleware` converts unhandled exceptions into structured 500s
3. Route handler resolves `Depends(get_session)` for a DB session
4. Handler calls services; **services `flush()`, handlers `commit()`** — this is
   a firm convention, do not commit inside a service
5. On error the session dependency rolls back

---

## 4. Tech stack

Everything is open source and self-hostable. The only managed dependency is
Amazon Bedrock for model inference.

| Layer | Choice | Version | Why |
|---|---|---|---|
| Language | Python | 3.11 | Matches existing PV pipeline code |
| API framework | FastAPI | 0.115 | Async, OpenAPI generation, dependency injection |
| Validation | Pydantic | 2.13 | The contracts package is the type system |
| ORM | SQLAlchemy (async) | 2.0.52 | Same code for SQLite and PostgreSQL |
| Migrations | Alembic | 1.19 | |
| DB (dev) | SQLite + aiosqlite | 0.20 | Zero setup |
| DB (deploy) | PostgreSQL + asyncpg | 16 / 0.31 | Relational fit for case data |
| Async glue | greenlet | 3.5.5 | **Required** by SQLAlchemy async |
| Object store | Filesystem or MinIO | — | S3-compatible, open source |
| Inference | Amazon Bedrock Converse | boto3 1.43 | Structured output via forced tool-use |
| Retries | tenacity | 9.1 | Backoff for Bedrock and PubMed |
| Logging | structlog | 26.1 | JSON, contextvar-correlated |
| IDs | python-ulid | 4.0 | Time-sortable, globally unique |
| Frontend | React + Vite + TypeScript | 18 / 5.4 | |
| Styling | Tailwind CSS | 3.x | |
| Routing | react-router-dom | 6.x | |
| Lint/format | ruff | 0.16 | Replaces black + flake8 + isort |
| Types | mypy (strict) | 2.3 | |
| Tests | pytest + pytest-asyncio | 9.1 / 1.4 | |
| CI | GitHub Actions | — | lint → mypy → pytest → build |

---

## 5. Repository layout

```
ATheria/
├── backend/
│   ├── app/
│   │   ├── api/v1/                  HTTP layer — thin, no business logic
│   │   │   ├── health.py            Liveness/readiness
│   │   │   ├── intake.py            Web form + PubMed sweep
│   │   │   ├── triage.py            Run/read triage, expose rule set
│   │   │   ├── inbox.py             Work queue + stats (read-only)
│   │   │   ├── cases.py             Case CRUD (pre-existing, not yet wired to triage)
│   │   │   └── fixtures.py          Golden fixture serving (dev aid)
│   │   ├── connectors/              INTAKE — one module per channel
│   │   │   ├── base.py              SourceRecord assembly, hashing, Day 0
│   │   │   ├── web_form.py          Solicited direct reports
│   │   │   └── pubmed.py            NCBI E-utilities, retry, XML parsing
│   │   ├── rules/                   DETERMINISTIC DECISIONS
│   │   │   └── validity.py          val_001 — the four minimum criteria
│   │   ├── services/                Business logic
│   │   │   ├── triage_service.py    The pipeline orchestrator
│   │   │   ├── inbox_service.py     Read model + deterministic rule replay
│   │   │   ├── case_service.py      Case CRUD + versioning
│   │   │   └── audit_service.py     Hash-chained audit events
│   │   ├── core/
│   │   │   ├── config.py            Pydantic Settings (env-driven)
│   │   │   ├── database.py          Async engine + session dependency
│   │   │   ├── evidence.py          Evidence vault (filesystem | S3/MinIO)
│   │   │   ├── llm.py               Cached provider + prompt registry
│   │   │   └── logging.py           structlog setup
│   │   ├── middleware/
│   │   │   ├── request_audit.py     Trace context binding
│   │   │   └── error_handler.py     Global exception → structured 500
│   │   ├── models/                  SQLAlchemy ORM
│   │   │   ├── base.py              Base, TenantMixin, TimestampMixin
│   │   │   └── case.py              All 7 tables
│   │   └── main.py                  App factory, router registration
│   ├── prompts/
│   │   └── triage_icsr.yaml         Versioned prompt + output schema
│   ├── migrations/                  Alembic
│   │   └── versions/001_initial_schema.py
│   ├── tests/                       56 tests
│   └── Dockerfile
│
├── packages/
│   ├── atheria-contracts/           Shared Pydantic types (the domain vocabulary)
│   │   └── atheria_contracts/
│   │       ├── enums.py             All domain enumerations
│   │       ├── provenance.py        Provenanced[T], EvidenceSpan, Locator
│   │       ├── source_record.py     SourceRecord, TriageResult, ICSRElements
│   │       ├── canonical_case.py    CanonicalCase, RuleEvaluation
│   │       └── audit.py             AuditEvent
│   └── atheria-llm/                 Provider-agnostic inference
│       └── atheria_llm/
│           ├── base.py              LLMProvider protocol, LLMConfig, LLMResponse
│           ├── factory.py           get_provider() — the switch point
│           ├── prompts.py           PromptRegistry (versioned YAML)
│           └── providers/
│               ├── bedrock.py       Converse + forced tool-use
│               └── gemini.py        Google AI Studio (ready, see caveat)
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── DashboardPage.tsx        Live counts + recent records
│       │   ├── ReportFormPage.tsx       The web form (intake)
│       │   ├── LiteratureSweepPage.tsx  PubMed screening (intake)
│       │   ├── InboxPage.tsx            Review queue (read-only)
│       │   └── WorkbenchPage.tsx        Case review (pre-existing, fixture-driven)
│       ├── components/triage/
│       │   ├── OutcomeBadge.tsx         The determination badge
│       │   ├── CriteriaPanel.tsx        4 criteria + clickable evidence
│       │   ├── RuleTracePanel.tsx       Rule decision trace
│       │   └── SourceTextView.tsx       Source text with highlight
│       ├── types/triage.ts              TS mirrors of backend contracts
│       └── lib/utils.ts                 apiFetch, tenant headers, formatters
│
├── fixtures/                        3 hand-authored golden cases
├── infrastructure/                  AWS CDK — NOT USED (see decision log)
├── docker-compose.yml               Postgres + MinIO self-hosted stack
├── pyproject.toml                   Deps, ruff, mypy, pytest config
└── .env                             Local config (gitignored)
```

---

## 6. Local setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- AWS credentials with Bedrock access (inference only; nothing is deployed)
- No database server required

### Steps

```bash
cd ATheria

# 1. Python environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install -e packages/atheria-contracts
pip install -e packages/atheria-llm

# 2. Create the .env file (see section 7 for the full template)
#    At minimum, set an absolute DB path so the API and Alembic agree.

# 3. Create the schema
cd backend
ATHERIA_DATABASE_URL="sqlite:///$(cd .. && pwd)/atheria.db" alembic upgrade head
cd ..

# 4. Verify Bedrock is reachable
python -c "
from atheria_llm import get_provider, LLMConfig
p = get_provider(provider='bedrock', aws_region='ap-south-1',
                 bedrock_model_id='apac.amazon.nova-lite-v1:0')
print(p.invoke('Reply with OK', LLMConfig(max_tokens=10)).text)
"

# 5. Run the API (--reload-include is needed to pick up prompt YAML changes)
uvicorn backend.app.main:app --reload --reload-include '*.yaml' --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

- UI: <http://localhost:5173>
- API docs: <http://localhost:8000/docs>

### Smoke test

```bash
curl -s localhost:8000/api/v1/intake/web-form \
  -H 'content-type: application/json' \
  -H 'x-tenant-id: acme_pharma' \
  -d '{"narrative":"I am Dr. Rao. My patient, a 54-year-old woman, took Atherex 100mg and developed a severe rash requiring hospital admission."}' \
  | python -m json.tool | head -30
```

Expect `"icsr_outcome": "valid_icsr"`.

---

## 7. Configuration reference

All settings are environment variables prefixed `ATHERIA_`, loaded by
`backend/app/core/config.py` via pydantic-settings. A `.env` file in the repo
root is read automatically and is gitignored.

### `.env` template

```bash
ATHERIA_ENVIRONMENT=development
ATHERIA_DEBUG=true
ATHERIA_LOG_FORMAT=console          # console for humans, json for production
ATHERIA_LOG_LEVEL=INFO

# Database — use an ABSOLUTE path so the API (run from repo root) and
# Alembic (run from backend/) resolve to the same file.
ATHERIA_DATABASE_URL=sqlite+aiosqlite:////absolute/path/to/ATheria/atheria.db

# LLM
ATHERIA_LLM_PROVIDER=bedrock                        # bedrock | gemini
ATHERIA_AWS_REGION=ap-south-1
ATHERIA_BEDROCK_MODEL_ID=apac.amazon.nova-lite-v1:0
ATHERIA_LLM_MAX_TOKENS=2000

# Evidence vault
ATHERIA_EVIDENCE_BACKEND=filesystem                 # filesystem | s3
ATHERIA_EVIDENCE_ROOT=./evidence_vault

# Literature intake (optional; a key raises PubMed's limit from 3/s to 10/s)
# ATHERIA_NCBI_API_KEY=
ATHERIA_NCBI_TOOL_EMAIL=you@example.com
```

### Full settings table

| Variable | Default | Purpose |
|---|---|---|
| `ATHERIA_ENVIRONMENT` | `development` | Environment name |
| `ATHERIA_DEBUG` | `false` | Enables `/docs` and `/redoc` |
| `ATHERIA_HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address |
| `ATHERIA_DATABASE_URL` | `sqlite+aiosqlite:///./atheria.db` | Async DB URL |
| `ATHERIA_DATABASE_ECHO` | `false` | Log all SQL |
| `ATHERIA_LLM_PROVIDER` | `bedrock` | `bedrock` or `gemini` |
| `ATHERIA_LLM_MAX_TOKENS` | `2000` | Output ceiling; raise for reasoning models |
| `ATHERIA_LLM_TEMPERATURE` | `0.0` | Keep at 0 for reproducibility |
| `ATHERIA_AWS_REGION` | `ap-south-1` | Bedrock region |
| `ATHERIA_BEDROCK_MODEL_ID` | `apac.amazon.nova-lite-v1:0` | **Must be an inference-profile ID** |
| `ATHERIA_BEDROCK_GUARDRAIL_ID` | `None` | Optional Bedrock guardrail |
| `ATHERIA_BEDROCK_GUARDRAIL_VERSION` | `None` | |
| `ATHERIA_GEMINI_API_KEY` | `None` | Required when provider is `gemini` |
| `ATHERIA_GEMINI_MODEL_ID` | `gemini-2.5-flash` | |
| `ATHERIA_GEMINI_BASE_URL` | Google endpoint | Override for a proxy |
| `ATHERIA_EVIDENCE_BACKEND` | `filesystem` | `filesystem` or `s3` |
| `ATHERIA_EVIDENCE_ROOT` | `./evidence_vault` | Filesystem root |
| `ATHERIA_EVIDENCE_BUCKET` | `atheria-evidence` | Bucket name for `s3` |
| `ATHERIA_EVIDENCE_ENDPOINT_URL` | `None` | e.g. `http://localhost:9000` for MinIO |
| `ATHERIA_EVIDENCE_ACCESS_KEY` / `SECRET_KEY` | `None` | MinIO credentials |
| `ATHERIA_AUTH_MODE` | `dev_bypass` | `dev_bypass` or `oidc` (OIDC not implemented) |
| `ATHERIA_OIDC_ISSUER_URL` / `AUDIENCE` | `None` | Reserved for Keycloak |
| `ATHERIA_NCBI_API_KEY` | `None` | Raises PubMed rate limit |
| `ATHERIA_NCBI_TOOL_EMAIL` | `None` | NCBI asks callers to identify themselves |
| `ATHERIA_PROMPTS_DIR` | `backend/prompts` | Prompt YAML location |
| `ATHERIA_CORS_ORIGINS` | `["http://localhost:5173", ...]` | Allowed origins |
| `ATHERIA_LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` | Logging |

> **Security note:** the current build has **no authentication**. `auth_mode` is
> `dev_bypass` and the frontend's auth context always reports authenticated.
> Tenancy comes from a client-supplied `x-tenant-id` header, which is trivially
> spoofable. This is acceptable for a local demo and **must not be exposed to a
> network** without implementing real auth first. See
> [section 15](#15-known-gaps-and-next-steps).

---

## 8. Database schema

Seven tables, created by `backend/migrations/versions/001_initial_schema.py`.
DDL below is the SQLite form as actually created; PostgreSQL types are
equivalent (`JSON` → `JSONB` is a recommended future change).

### Conventions

- **Every table has `tenant_id`**, indexed. Multi-tenancy by construction
  (`TenantMixin` in `models/base.py`). All queries must filter on it.
- Primary keys are **ULIDs** (26-char strings): time-sortable and globally unique.
- Most tables carry `created_at` / `updated_at` (`TimestampMixin`).
- JSON columns hold Pydantic-validated documents; the contracts package is the
  schema of record for their shape.

### Entity relationships

```
source_records ──1:N──► evidence_refs
      │
      ├──1:N──► pipeline_runs ──1:N──► pipeline_stages
      │
      └──(derived_case_ids JSON)──► cases ──1:N──► case_versions

audit_events  ── references case_id and/or source_record_id (no FK by design:
                 append-only log must never be blocked by referential integrity)
```

### 8.1 `source_records`

The channel-agnostic intake envelope. **The central table for triage.**

```sql
CREATE TABLE source_records (
    source_record_id      VARCHAR(64) NOT NULL PRIMARY KEY,  -- ULID
    tenant_id             VARCHAR(64) NOT NULL,
    trace_id              VARCHAR(64) NOT NULL,   -- correlates logs
    sweep_id              VARCHAR(64),            -- groups a literature sweep
    channel               VARCHAR(64) NOT NULL,   -- web_form | literature_pubmed | ...
    channel_class         VARCHAR(32) NOT NULL,   -- solicited | literature | earned | ...
    external_id           VARCHAR(512),           -- e.g. PubMed PMID
    external_url          TEXT,                   -- link back to the source
    retrieved_at          DATETIME NOT NULL,
    awareness_datetime    DATETIME NOT NULL,      -- DAY 0 — IMMUTABLE
    platform_published_at DATETIME,
    raw_text              TEXT,                   -- normalised source text
    raw_language          VARCHAR(16),
    content_hash          VARCHAR(64) NOT NULL,   -- SHA-256, used for dedup
    manifest_ref          TEXT,                   -- evidence vault key
    triage_result         JSON,                   -- TriageResult (see 8.1.1)
    status                VARCHAR(32),            -- SourceStatus
    error_type            VARCHAR(64),
    error_message         TEXT,
    derived_case_ids      JSON,                   -- list[str]
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_source_records_tenant_id ON source_records (tenant_id);
CREATE INDEX ix_source_records_status    ON source_records (tenant_id, status);
```

`status` values (`SourceStatus` enum): `received`, `normalising`, `triaging`,
`triaged`, `case_created`, `non_icsr`, `noise`, `error`, `quarantined`.

**`awareness_datetime` is Day 0.** Regulatory clocks run from it. Never
recompute or backdate it.

**`content_hash`** is SHA-256 over Unicode-NFC-normalised, whitespace-normalised
text (`connectors/base.py::normalise_text`). Cosmetic differences hash
identically, so deduplication is reliable.

#### 8.1.1 `triage_result` JSON shape

Serialised `atheria_contracts.source_record.TriageResult`:

```jsonc
{
  "is_noise": false,
  "noise_reason": null,
  "products_mentioned": [
    { "verbatim": "Atherex 100mg", "confidence": 0.0,
      "span": { "source_record_id": "...", "evidence_ref": "...",
                "locator": { "char_start": 129, "char_end": 151 },
                "quote": "Atherex 100mg" } }
  ],
  "ae_candidates":  [ /* same shape as products_mentioned */ ],
  "content_types":  ["ae"],
  "patient_count":  1,
  "icsr_elements": {
    "identifiable_patient":  { "present": true,
      "evidence_span": { "locator": {"char_start": 87, "char_end": 128},
                         "quote": "Patient age: 54 years" } },
    "identifiable_reporter": { "present": true,  "evidence_span": { } },
    "suspect_product":       { "present": true,  "evidence_span": { } },
    "adverse_event":         { "present": true,  "evidence_span": { } }
  },
  "icsr_outcome": "valid_icsr",
  "outcome_rule_id": "val_001",
  "outcome_rule_version": "1.0.0",
  "priority_score": 1.0,
  "seriousness_signal": true,
  "model_id": "apac.amazon.nova-lite-v1:0",
  "prompt_version": "triage_icsr_v1.0",
  "rationale": "The source describes a specific patient who..."
}
```

The rule trace is **not** stored here. `InboxService` recomputes it from
`icsr_elements` on read — the rule is a pure function, so replay is free and
guaranteed identical.

### 8.2 `audit_events`

Append-only, hash-chained. This is what makes the system inspectable.

```sql
CREATE TABLE audit_events (
    event_id         VARCHAR(64) NOT NULL PRIMARY KEY,
    tenant_id        VARCHAR(64) NOT NULL,
    case_id          VARCHAR(64),
    source_record_id VARCHAR(64),
    event_type       VARCHAR(64) NOT NULL,  -- field_change | state_change | approval
                                            -- | ai_invocation | rule_evaluation
    field_path       VARCHAR(256),
    old_value        TEXT,
    new_value        TEXT,
    actor_type       VARCHAR(16) NOT NULL,  -- ai | rule | human | system
    actor_id         VARCHAR(128),
    model_id         VARCHAR(128),          -- set when actor_type = ai
    prompt_version   VARCHAR(64),           -- set when actor_type = ai
    rule_id          VARCHAR(128),          -- set when actor_type = rule
    rule_set_version VARCHAR(32),           -- set when actor_type = rule
    reason_code      VARCHAR(64),
    rationale        TEXT,
    confidence       FLOAT,
    timestamp        DATETIME NOT NULL,
    content_hash     VARCHAR(64) NOT NULL,  -- SHA-256(previous_hash + event data)
    previous_hash    VARCHAR(64) NOT NULL,  -- genesis = 64 zeros
    trace_id         VARCHAR(64),
    request_id       VARCHAR(64)
);
CREATE INDEX ix_audit_events_tenant_id       ON audit_events (tenant_id);
CREATE INDEX ix_audit_events_case_id         ON audit_events (case_id);
CREATE INDEX ix_audit_events_case_timestamp  ON audit_events (case_id, timestamp);
```

**Hash chain.** Each event's `content_hash` =
`SHA-256(previous_hash + ":" + canonical_json(event_fields))`. The chain is
per-tenant, starting from 64 zeros. Verify with
`AuditService.verify_chain_integrity(tenant_id)`.

Each triage writes **two** events: an `ai_invocation` (which model, which
prompt) and a `rule_evaluation` (which rule, which version, what outcome).

> **Known limitation:** the hashed field subset in
> `AuditService._record_event` omits `rule_id`, `prompt_version` and
> `confidence`. Tampering with those specific columns would not break the chain.
> Worth fixing before any compliance claim — note that changing the hash inputs
> invalidates existing chains, so it needs a migration strategy.

### 8.3 `pipeline_runs` and `pipeline_stages`

Durable orchestration without a workflow engine. One run per triage; one stage
row per step.

```sql
CREATE TABLE pipeline_runs (
    run_id           VARCHAR(64) NOT NULL PRIMARY KEY,
    tenant_id        VARCHAR(64) NOT NULL,
    source_record_id VARCHAR(64) NOT NULL,
    case_id          VARCHAR(64),
    pipeline_type    VARCHAR(64) NOT NULL,   -- "triage"
    status           VARCHAR(32),            -- running | completed | failed
    started_at       DATETIME NOT NULL,
    completed_at     DATETIME,
    error_type       VARCHAR(64),
    error_message    TEXT,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pipeline_stages (
    id            VARCHAR(64) NOT NULL PRIMARY KEY,
    tenant_id     VARCHAR(64) NOT NULL,
    run_id        VARCHAR(64) NOT NULL REFERENCES pipeline_runs (run_id),
    stage_name    VARCHAR(64) NOT NULL,      -- "triage"
    stage_order   INTEGER NOT NULL,
    status        VARCHAR(32),               -- pending | running | completed | failed
    started_at    DATETIME,
    completed_at  DATETIME,
    input_hash    VARCHAR(64),               -- source content hash
    output_hash   VARCHAR(64),               -- hash of the triage result
    error_type    VARCHAR(64),
    error_message TEXT,
    duration_ms   FLOAT
);
```

`input_hash` and `output_hash` together give deterministic-replay evidence: the
same input hash and same versions should reproduce the same output hash.

### 8.4 `cases` and `case_versions`

The canonical case store with immutable versioning. **Present and tested, but
triage does not create cases yet** — that is the next piece of work.

```sql
CREATE TABLE cases (
    case_id         VARCHAR(64) NOT NULL PRIMARY KEY,
    tenant_id       VARCHAR(64) NOT NULL,
    case_number     VARCHAR(128) NOT NULL,
    current_version INTEGER,
    lifecycle_state VARCHAR(32),        -- CaseState enum
    lock_state      VARCHAR(32),        -- open | locked_for_review | locked_submitted
    created_by      VARCHAR(128) NOT NULL,
    approved_at     DATETIME,
    approved_by     VARCHAR(128),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tenant_case_number UNIQUE (tenant_id, case_number)
);
CREATE INDEX ix_cases_lifecycle ON cases (tenant_id, lifecycle_state);

CREATE TABLE case_versions (
    id                 VARCHAR(64) NOT NULL PRIMARY KEY,
    case_id            VARCHAR(64) NOT NULL REFERENCES cases (case_id),
    tenant_id          VARCHAR(64) NOT NULL,
    version            INTEGER NOT NULL,
    version_type       VARCHAR(32),     -- initial | follow_up | amendment | nullification
    supersedes_version INTEGER,
    data               JSON NOT NULL,   -- the full CanonicalCase document
    content_hash       VARCHAR(64) NOT NULL,   -- binds e-signatures
    created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_case_version UNIQUE (case_id, version)
);
```

Versions are **never updated**. Every change writes a new row, so "show me what
this case looked like at time T" is a primary-key lookup.

> **Known limitation:** `CaseService.update_case` applies updates as top-level
> key replacement (`new_data[field_path] = value`). It does not support nested
> paths like `patient.age.value`. Fix this before building the review loop.

### 8.5 `evidence_refs`

Pointers to objects in the evidence vault. The column is named `s3_key` for
historical reasons; it holds the object key for whichever backend is active.

```sql
CREATE TABLE evidence_refs (
    id               VARCHAR(64) NOT NULL PRIMARY KEY,
    tenant_id        VARCHAR(64) NOT NULL,
    source_record_id VARCHAR(64) NOT NULL REFERENCES source_records (source_record_id),
    s3_key           TEXT NOT NULL,
    sha256           VARCHAR(64) NOT NULL,
    object_type      VARCHAR(32) NOT NULL,   -- raw | rendered | canonical_document | manifest
    size_bytes       INTEGER,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

> Currently unused by the triage path: the vault key is stored on
> `source_records.manifest_ref` instead. Populate this table when multiple
> artefacts per record appear (PDFs, attachments, renderings).

### Migrations

```bash
cd backend

# Apply
alembic upgrade head

# Create a new revision after changing models/
alembic revision --autogenerate -m "add_something"

# Roll back one step
alembic downgrade -1
```

`migrations/env.py` strips `+asyncpg` / `+aiosqlite` from the URL because
Alembic runs synchronously. Any new model **must** be imported in `env.py` or
autogenerate will not see it.

**Rule:** every new table gets `tenant_id` via `TenantMixin`.

---

## 9. API reference

Base path `/api/v1`. Interactive docs at `/docs` when `ATHERIA_DEBUG=true`.

### Headers

| Header | Default | Purpose |
|---|---|---|
| `x-tenant-id` | `default` | Tenant scope. **Currently trusted — see security note** |
| `x-actor-id` | varies | Acting user, recorded in audit events |
| `x-trace-id` | generated | Distributed trace correlation |
| `x-request-id` | generated | Request correlation / dedup |

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/health/ready` | Readiness |
| POST | `/intake/web-form` | Submit a direct report; triages inline |
| POST | `/intake/literature/pubmed` | PubMed sweep; ingests and triages |
| POST | `/triage/{source_record_id}` | Run or re-run triage |
| GET | `/triage/{source_record_id}` | Stored triage result |
| GET | `/triage/rules/validity` | Active rule set + decision table |
| GET | `/inbox` | Work queue (`?status=`, `?outcome=`, `?limit=`, `?offset=`) |
| GET | `/inbox/stats` | Counts by status and outcome |
| GET | `/inbox/{source_record_id}` | Full detail incl. source text and rule trace |
| GET | `/cases` | List cases |
| POST | `/cases` | Create a case |
| GET | `/cases/{case_id}` | Latest version |
| GET | `/cases/{case_id}/versions/{version}` | Specific version |
| PATCH | `/cases/{case_id}` | Update fields (new version) |
| POST | `/cases/{case_id}/approve` | Approve with e-signature |
| GET | `/cases/{case_id}/audit` | Audit trail |
| GET | `/fixtures/cases` | Golden fixtures (dev aid) |
| GET | `/fixtures/cases/{case_id}` | One fixture |

### `POST /intake/web-form`

Only `narrative` is required. Omit fields you do not have — do **not** send
empty strings or `"unknown"`, because a blank field must not read as a positive
assertion of absence.

```jsonc
// Request
{
  "narrative": "My patient developed a severe rash after starting Atherex.",
  "reporter_name": "Dr. Anita Sharma",
  "reporter_qualification": "physician",
  "reporter_email": "a.sharma@example.com",
  "reporter_country": "IN",
  "patient_initials": "R.K.",
  "patient_age": "54 years",
  "patient_sex": "female",
  "product_name": "Atherex 100mg",
  "dose": "100mg once daily",
  "event_description": "Severe itchy rash",
  "onset_date": "2026-08-28",
  "language": "en",
  "triage": true          // false to ingest without triaging
}
```

```jsonc
// 201 Response
{
  "source_record_id": "01M1RV8PGRQ31TB19HG4JSZHDP",
  "channel": "web_form",
  "content_hash": "c99d6d5a...",
  "awareness_datetime": "2026-09-05T13:14:00.088398+00:00",
  "status": "triaged",
  "icsr_outcome": "valid_icsr",
  "triage": { /* TriageResult — see 8.1.1 */ },
  "rule_trace": {
    "rule_id": "val_001",
    "rule_set_version": "1.0.0",
    "inputs": { "identifiable_patient": true, "identifiable_reporter": true,
                "suspect_product": true, "adverse_event": true },
    "input_provenance": { "identifiable_patient": "present — evidence: '...'" },
    "fired_rules": ["val_001_all_criteria_present"],
    "explanation": "VALID ICSR. Rule val_001 v1.0.0. All four minimum criteria...",
    "outcome": "valid_icsr"
  },
  "run_id": "01M1RV8..."
}
```

### `POST /intake/literature/pubmed`

```jsonc
// Request
{ "query": "drug induced liver injury case report", "max_results": 3, "triage": true }

// 201 Response
{
  "query": "...",
  "summary": "PubMed sweep '...': 3 hits, 3 fetched, 3 new, 0 duplicate(s) skipped.",
  "ingested": 3,
  "duplicates_skipped": 0,
  "triaged": 3,
  "failures": [],           // per-article failures; one bad article never aborts the sweep
  "results": [ /* one triage response per article */ ]
}
```

### Status codes

| Code | Meaning |
|---|---|
| 201 | Ingested (and triaged if requested) |
| 404 | Source record or case not found |
| 409 | Case is locked (`cases` PATCH) |
| 502 | Upstream failure — model call or PubMed unreachable |
| 500 | Unhandled error; structured `{"error": {"type", "message"}}` |

---

## 10. The LLM layer

### Design

`packages/atheria-llm` exposes one interface. No service imports `boto3`.

```python
from atheria_llm import LLMConfig, get_provider

provider = get_provider(provider="bedrock", aws_region="ap-south-1",
                        bedrock_model_id="apac.amazon.nova-lite-v1:0")

response = provider.invoke(prompt, LLMConfig(
    prompt_version="triage_icsr_v1.0",
    system_prompt="...",
    output_schema={...},      # JSON Schema
    max_tokens=1200,
    temperature=0.0,
    tenant_id="acme_pharma",
    trace_id="trc_1",
))

data   = response.require_structured()   # raises if no structured output
record = response.record                 # model_id, prompt_version, tokens, latency
```

Inside the app use the cached accessors in `backend/app/core/llm.py`:
`get_llm_provider()` and `get_prompt_registry()`.

### How structured output works

**Bedrock:** declares a single tool whose input schema is your JSON Schema, and
sets `toolChoice` to force it. The model must reply with schema-shaped arguments
rather than prose.

**Gemini:** uses native JSON mode (`responseMimeType: application/json` +
`responseSchema`). `_sanitise_schema` strips keywords Gemini rejects
(`additionalProperties`, `$schema`, `title`, ...) so the *same* schema object
works for both providers unchanged.

Both fail loudly rather than degrading to free text.

### Model selection — verified against the live API

Bedrock **rejects bare model IDs** for on-demand invocation. You must use an
inference-profile ID (`apac.`, `us.`, or `global.` prefix for your region).
The error message is unhelpful, so `providers/bedrock.py` detects it and raises
a clear `LLMConfigurationError`.

| Model | Region | Verdict |
|---|---|---|
| `apac.amazon.nova-lite-v1:0` | ap-south-1 | **Current default.** Cheapest that honours the full schema. ~$0.14/1000 cases |
| `apac.amazon.nova-micro-v1:0` | ap-south-1 | **Do not use.** Cheaper, but silently returns `null` for `content_type`, `product_names`, `event_terms`, `seriousness_signal`, `patient_count`, `rationale` while filling the nested objects correctly. Looks like it works until you read the output |
| `global.anthropic.claude-sonnet-4-5-20250929-v1:0` | ap-south-1 | Works. Much stronger clinical judgement, roughly 20× the cost |
| `openai.gpt-oss-120b-1:0` | **us-west-2 only** | Works, but needs `max_tokens >= 4000` because reasoning tokens are consumed before the tool call. Judged "54-year-old female" as *not* an identifiable patient in testing |
| `anthropic.claude-3-5-sonnet-20241022-v2:0` | — | End of life; rejected |

### Switching to Gemini

```bash
export ATHERIA_LLM_PROVIDER=gemini
export ATHERIA_GEMINI_API_KEY=...
```

> **Caveat:** `generativelanguage.googleapis.com` and
> `aiplatform.googleapis.com` are **blocked** on the network this was developed
> on (a TLS-inspecting corporate proxy; certificates are reissued by an internal
> CA). The provider is written and unit-testable but could not be validated
> against the live endpoint. It raises a clear connectivity error in that case.
> AWS Bedrock and NCBI PubMed are both reachable from that network.

### Prompts

Versioned YAML in `backend/prompts/`, loaded at startup by `PromptRegistry`.
Each file carries the system prompt, the user template, and the JSON output
schema together, so a prompt and its contract move as one unit.

`triage_icsr.yaml` is the only prompt today. Note that the system prompt
**explicitly forbids the model from deciding validity** — that instruction is
load-bearing, not decorative.

Prompts are cached, so **editing YAML requires a restart** unless you run
uvicorn with `--reload-include '*.yaml'`.

To add a prompt: drop a YAML file in `backend/prompts/` with `name`, `version`,
`system_prompt`, `user_template`, `output_schema`. It is picked up
automatically. Bump `version` on every meaningful change — it is recorded in the
audit trail as `prompt_version`.

---

## 11. The rules engine

`backend/app/rules/validity.py` implements `val_001 v1.0.0`.

```python
from backend.app.rules.validity import evaluate_validity

decision = evaluate_validity(icsr_elements)   # pure function
decision.outcome                # ICSROutcome
decision.trace                  # RuleEvaluation — the full audit trace
decision.is_valid_icsr          # bool
decision.requires_human_review  # True when escalated
```

### Decision table

| Condition | Outcome | Rule fired |
|---|---|---|
| All four criteria present | `valid_icsr` | `val_001_all_criteria_present` |
| Suspect product **or** adverse event absent | `non_icsr` | `val_001_missing_core_element` |
| Product + event present, patient **or** reporter absent | `potential_icsr` | `val_001_incomplete_escalate` |

The third branch is the important one. A genuine safety signal with an
incomplete record is escalated for follow-up — never guessed at, never silently
discarded.

### Rules for writing rules

1. **Pure functions only.** No I/O, no model calls, no clock reads, no randomness.
2. **Always emit a `RuleEvaluation`** with `inputs`, `input_provenance`,
   `fired_rules`, `explanation`, `outcome`.
3. **Bump `RULE_SET_VERSION`** whenever logic changes. Historical decisions must
   stay attributable to the exact rules that made them.
4. **Never guess.** If an input cannot be determined, escalate.
5. **Test exhaustively.** `test_validity_rule.py` asserts all 16 combinations of
   the four booleans.

### Adding a new rule set

1. Create `backend/app/rules/<name>.py` with `RULE_ID`, `RULE_SET_VERSION`, and
   an `evaluate_*` function returning a decision plus trace
2. Write the exhaustive truth-table test first
3. Call it from the relevant service
4. Record it via `AuditService.record_rule_evaluation(...)`
5. Expose it under `/triage/rules/...` for transparency

The next rule set is seriousness (`ser_003`) over the six ICH criteria. The
contracts already define `SeriousnessFacts` and `ReactionBlock.is_serious`, and
`fixtures/golden_case_03_escalation.json` shows the expected output shape.

---

## 12. Frontend

React + Vite + TypeScript + Tailwind. Vite proxies `/api` to
`localhost:8000` (`vite.config.ts`).

### Pages

| Route | Page | Role |
|---|---|---|
| `/` | `DashboardPage` | Live counts, latest records, platform health |
| `/report` | `ReportFormPage` | **Intake.** Full reporting form; engine runs on submit |
| `/literature` | `LiteratureSweepPage` | **Intake.** PubMed screening |
| `/inbox` | `InboxPage` | **Review only.** Queue, determination, evidence |
| `/cases/:caseId` | `WorkbenchPage` | Pre-existing, fixture-driven |
| `/login` | `LoginPage` | Bypassed in dev |

Intake and review are deliberately separate: the inbox is a reviewer's view and
performs no ingestion.

### Key components

- **`OutcomeBadge`** — the determination. Green = valid, amber = escalated,
  grey = not an ICSR.
- **`CriteriaPanel`** — the four criteria with clickable evidence quotes.
- **`RuleTracePanel`** — rule ID, version, fired rules, inputs and their basis.
- **`SourceTextView`** — source text with the selected span highlighted.

### Evidence highlighting

The backend locates each model-supplied quote inside the stored source text and
records `char_start`/`char_end` (`triage_service.py::_locate_quote`). It tries
the exact quote, then the quote stripped of wrapping quotation marks, then a
whitespace-normalised form, then the leading 40 characters.

If none match it returns an **empty locator rather than a guess** — a wrong
offset would highlight the wrong sentence, which is worse than highlighting
nothing.

### Tenancy in the client

`lib/utils.ts` sets `x-tenant-id: acme_pharma` and `x-actor-id: demo_reviewer`
on every request. Replace with values from a real auth token when auth lands.

### Commands

```bash
npm run dev        # dev server on 5173
npm run typecheck  # tsc --noEmit
npm run lint       # eslint
npm run build      # production build
```

---

## 13. Testing

56 tests, no network calls, no AWS credentials needed. They run against
in-memory SQLite with a stub LLM provider.

```bash
pytest backend/tests -q                                  # all
pytest backend/tests/test_validity_rule.py -v            # one file
pytest --cov=backend --cov=packages --cov-report=term     # coverage
```

| File | Covers |
|---|---|
| `conftest.py` | Async session fixture, `StubProvider`, `make_proposal()` helper, `stored_record` fixture |
| `test_validity_rule.py` | All 16 criteria combinations, trace contents, determinism, provenance formatting |
| `test_triage_service.py` | All outcomes, evidence location (incl. quote-mark and whitespace variants), audit chain, pipeline rows, tenant isolation, loud failure |
| `test_inbox_service.py` | Deterministic rule replay, stability, stats, tenant isolation |
| `test_connectors.py` | Hash normalisation, Day 0, web-form rendering, PubMed XML parsing, retry behaviour |

### Test philosophy

The LLM is stubbed. Its *job* is to return a schema-shaped proposal; what
matters is what the rules do with it. `make_proposal(patient=False, ...)` builds
any input scenario, so rule behaviour is asserted without spend or flakiness.

### Quality gates (also run in CI)

```bash
ruff check .                                    # lint
ruff format --check .                           # formatting
mypy backend/ packages/ --ignore-missing-imports  # strict types
pytest backend/tests -q                         # tests
cd frontend && npm run typecheck && npm run build
```

All five must pass. `pyproject.toml` ignores two ruff rules deliberately:
`B008` (FastAPI's `Depends()`/`Header()` in defaults is required idiom) and
`UP042` (`class X(str, Enum)` is intentional for JSON serialisation).

---

## 14. Deployment

### Design constraint

Open-source, self-hostable components only. No managed cloud services except
Bedrock for inference. The `infrastructure/` CDK directory (VPC, RDS, S3, ECS,
Cognito) is **not used** and has never been deployed — treat it as reference
material for a future AWS-native path.

| AWS service | Open-source replacement |
|---|---|
| RDS | PostgreSQL container |
| S3 | MinIO (S3-compatible) |
| Cognito | Keycloak (not yet implemented) |
| ECS / CDK | Docker Compose |

### Docker Compose stack

> **Verification status:** `docker-compose.yml` is syntactically valid
> (`docker compose config` passes) and `backend/Dockerfile` is a pre-existing
> multi-stage build that copies `packages/`, `backend/` (including
> `prompts/` and `migrations/`), and installs all dependencies. However **the
> images have never been built or run**, because the Docker daemon was
> unavailable on the development machine. Treat the first `docker compose up` as
> an unverified step and expect minor fixes. Everything in
> [section 6](#6-local-setup) *is* verified.

```bash
# Credentials for Bedrock are passed through from the host environment
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...        # if using temporary credentials

docker compose up -d                                  # postgres, minio, api
docker compose --profile tools run --rm migrate        # apply migrations
```

If the API container cannot reach Bedrock, confirm the credentials actually
reached it:

```bash
docker compose exec api env | grep -c AWS_ACCESS_KEY_ID
```

Services:

| Service | Port | Notes |
|---|---|---|
| `db` | 5432 | postgres:16-alpine, healthchecked |
| `minio` | 9000 (API), 9001 (console) | Credentials `atheria` / `atheria123` — **change these** |
| `minio-init` | — | Creates the bucket and enables versioning, then exits |
| `api` | 8000 | Built from `backend/Dockerfile` |
| `migrate` | — | One-shot Alembic; `--profile tools` |

The compose file points the API at Postgres and MinIO via
`ATHERIA_EVIDENCE_BACKEND=s3` and `ATHERIA_EVIDENCE_ENDPOINT_URL=http://minio:9000`.

### Frontend deployment

`npm run build` emits static files to `frontend/dist/`. Serve behind any web
server (nginx, Caddy) and reverse-proxy `/api` to the backend. There is
currently no frontend container in the compose file.

### Before exposing this to any network

This build is a **local prototype**. At minimum, do all of the following first:

1. **Implement authentication.** There is none. `auth_mode=dev_bypass`, the
   frontend always reports authenticated, and `x-tenant-id` is a client-supplied
   header. Anyone can read any tenant's data by changing one header. Keycloak +
   OIDC is the intended path; `oidc_issuer_url` / `oidc_audience` settings are
   already reserved.
2. **Derive `tenant_id` from a verified token**, never from a request header.
3. **Change all default credentials** (MinIO, Postgres).
4. **Set `ATHERIA_DEBUG=false`** to disable `/docs`, and `LOG_FORMAT=json`.
5. **Add TLS termination.**
6. **Add rate limiting** on the intake endpoints — each call costs a model
   invocation, so an open endpoint is a billing risk as well as a load risk.
7. **Restrict CORS** to real origins.
8. **Review PII handling.** `source_records.raw_text` stores reporter names,
   emails and patient details in the clear. Consider encryption at rest, a
   retention policy, and the tokenisation the contracts anticipate
   (`patient_pii_token`).
9. **Switch `JSON` columns to `JSONB`** on PostgreSQL and consider generated
   columns for `triage_result->>'icsr_outcome'` — `InboxService.stats` currently
   aggregates outcomes in Python, which will not scale.

### CI

`.github/workflows/ci.yml`: lint + mypy → pytest (against
`sqlite+aiosqlite`) → build Python packages and the Docker image → frontend
typecheck and build.

---

## 15. Known gaps and next steps

### Not implemented

| Gap | Notes |
|---|---|
| **Authentication** | Highest priority before any shared deployment |
| **Case creation from triage** | A `valid_icsr` does not yet create a `cases` row. The tables and `CaseService` exist and are tested; the link is missing |
| **Field extraction** | Patient/drug/reaction blocks of `CanonicalCase` are not populated |
| **Seriousness rules** | `SeriousnessFacts` contract exists; `ser_003` not written |
| **MedDRA coding** | Requires a licensed dictionary. Deliberately deferred |
| **Email intake** | Deferred. `Channel.EMAIL` exists; write `connectors/email_imap.py` following the `pubmed.py` pattern |
| **E2B(R3) export** | Not started |
| **Review/approval loop** | `CaseService.approve_case` exists but no UI |
| **Scheduled sweeps** | Literature sweeps are manual; no scheduler |
| **`evidence_refs` population** | Vault key lives on `source_records.manifest_ref` instead |

### Known defects

1. **Audit hash omits some fields.** `rule_id`, `prompt_version`, `confidence`
   are not in the hashed subset. Fix requires a chain migration strategy.
2. **`CaseService.update_case` does not handle nested paths.** Top-level key
   replacement only. Must be fixed before the review loop.
3. **`InboxService.stats` aggregates in Python.** Fine at prototype volume; use
   a generated column or JSONB index later.
4. **Outcome filtering happens after the DB query**, so `?outcome=` combined
   with `?limit=` can return fewer rows than the limit.
5. **`confidence` is always 0.0** on `TriageResult`. The prompt does not ask for
   a per-criterion confidence yet.
6. **Frontend has no test suite.**

### Suggested order of work

1. **Authentication** (Keycloak + OIDC), and derive tenancy from the token
2. **Create cases from `valid_icsr`** — connects triage to the existing case store
3. **Extraction** into the canonical case, reusing the evidence-span pattern
4. **Seriousness rules** (`ser_003`), following `validity.py`
5. **Review and approval UI** — fix nested-path updates first
6. **Audit viewer**, then **E2B(R3) export**

---

## 16. Troubleshooting

**`ValueError: the greenlet library is required`**
`pip install greenlet`. SQLAlchemy's async layer needs it. It is declared in
`pyproject.toml` but easy to miss in an existing venv.

**`ValidationException: Invocation of model ID ... with on-demand throughput isn't supported`**
You used a bare model ID. Use the inference-profile form
(`apac.amazon.nova-lite-v1:0`). List available profiles:

```python
import boto3
c = boto3.client("bedrock", region_name="ap-south-1")
print([p["inferenceProfileId"] for p in c.list_inference_profiles(maxResults=100)["inferenceProfileSummaries"]])
```

**Model returns `null` for several fields**
You are probably on Nova Micro. Switch to `apac.amazon.nova-lite-v1:0`.

**`stop_reason=max_tokens` and no structured output**
A reasoning model consumed the budget before emitting the tool call. Raise
`ATHERIA_LLM_MAX_TOKENS` to 4000+.

**PubMed sweep returns 502**
Transient network failure; retry. The connector already retries three times with
backoff. A persistent failure means egress to `eutils.ncbi.nlm.nih.gov` is
blocked.

**Gemini raises a connectivity error**
Expected on TLS-inspecting corporate networks, which block
`generativelanguage.googleapis.com`. Needs a firewall exception.

**Prompt YAML edits have no effect**
The registry is cached at startup. Restart, or run uvicorn with
`--reload-include '*.yaml'`.

**Alembic and the API disagree about the database**
Relative SQLite paths resolve against the working directory, and Alembic runs
from `backend/` while uvicorn runs from the repo root. Use an absolute path in
`ATHERIA_DATABASE_URL`.

**Records stuck in `received`**
They were ingested with `triage: false`. `POST /triage/{id}` to process them.

**UI shows no data**
Check the tenant. `lib/utils.ts` sends `acme_pharma`; data created with a
different `x-tenant-id` is invisible by design.

---

## 17. Decision log

Why things are the way they are.

| Decision | Reasoning |
|---|---|
| **Rules decide, not the model** | Regulators require an auditable, reproducible basis for determinations. A model cannot provide one; a versioned pure function can |
| **Escalate instead of guessing** | A fabricated patient identity is worse than an admitted gap. `potential_icsr` exists specifically to carry that admission |
| **SQLite by default** | Docker was unavailable on the dev machine; SQLite removes all setup friction and the CI already targeted it. Same SQLAlchemy code runs on Postgres |
| **Nova Lite over Nova Micro** | Micro is cheaper but silently drops schema fields. Verified by A/B against the live API. The instruction was "cheapest", but a model that returns incomplete data is not functional |
| **Provider abstraction from the start** | Gemini was requested as the eventual engine, so vendor-swapping had to be a config change rather than a rewrite |
| **`client.py` deleted** | Its `LLMResponse`/`LLMInvocationRecord` names collided with the new `base.py`. Nothing imported it; only docs referenced it |
| **Rule trace recomputed, not stored** | The rule is pure, so replay is free and guaranteed identical. This also keeps the inbox genuinely read-only |
| **Evidence offsets computed server-side** | Models cannot reliably report character positions. Locating the quote in stored text is deterministic and verifiable |
| **Empty locator over a wrong one** | A bad offset sends a reviewer to the wrong sentence — worse than no highlight |
| **Services flush, handlers commit** | Keeps transaction boundaries at the HTTP layer where the request outcome is known |
| **Intake separate from the inbox** | The inbox is a reviewer's tool; mixing ingestion controls into it confuses the two roles |
| **CDK left in place but unused** | Deleting it would discard design work; the current requirement is an open-source self-hosted stack |
| **Prompts as YAML with their schema** | A prompt and its output contract must version together, and the audit trail records `prompt_version` |
| **Fail loud on model failure** | `record.status = "error"` plus a failed pipeline stage. A silently skipped safety report is the worst possible outcome |

---

## Appendix A: what has and has not been verified

Being explicit so you know where to be careful.

### Verified from a clean checkout

The [section 6](#6-local-setup) instructions were tested by copying the repo to
a fresh directory, deleting `.venv`, `node_modules` and the database, and running
them verbatim:

| Step | Result |
|---|---|
| `pip install -e ".[dev]"` + both packages | Installs cleanly; no missing transitive deps |
| `alembic upgrade head` (documented command) | Creates all 7 tables |
| `pytest backend/tests -q` | 56 passed |
| `ruff check .` | Clean |
| `mypy backend/ packages/` | Clean, 56 files |
| Bedrock verification snippet | Returns a live completion |
| Frontend `tsc --noEmit` | Clean |
| Live triage, all three outcomes | Correct (see Appendix B) |
| Live PubMed sweep + dedup on repeat | Correct |
| Audit hash chain | Intact from genesis |
| Evidence offsets | `raw_text[start:end] == quote` for every located quote |

### Not verified

| Item | Why |
|---|---|
| **Docker Compose stack** | Docker daemon unavailable on the dev machine. Compose file parses; images never built |
| **Gemini provider against the live API** | Google's endpoints are firewall-blocked on the dev network. Code is complete and unit-testable |
| **PostgreSQL** | All runs used SQLite. The SQLAlchemy code is dialect-agnostic and the migration uses no Postgres-specific types, but it has not been exercised |
| **Frontend production build served behind a web server** | `npm run build` passes; serving it has not been set up |
| **Concurrency / load** | Single-request testing only. No load testing, no connection-pool tuning under load |
| **Multi-tenant isolation under real auth** | Tenant filtering is unit-tested, but there is no auth layer to enforce which tenant a caller may claim |

---

## Appendix B: verified behaviour

Recorded from a live run against a fresh database on 5 September 2026, using
`apac.amazon.nova-lite-v1:0`.

| Input | Outcome | Rule fired |
|---|---|---|
| "I am Dr. Anita Sharma, a physician. My patient, a 54-year-old female, took Atherex 100mg and developed a severe itchy rash. Admitted overnight." | `valid_icsr` | `val_001_all_criteria_present` |
| "Someone on a forum said people are getting bad stomach bleeding from Atherex. No other details." | `potential_icsr` | `val_001_incomplete_escalate` |
| "I am a pharmacist. Can Atherex 100mg tablets be split in half? No patient has had any problem." | `non_icsr` | `val_001_missing_core_element` |

PubMed sweep for `drug induced liver injury case report` retrieved 3 articles,
ingested and triaged all 3, and skipped 0 duplicates; a repeat of the same query
skipped all 3 as duplicates.

Audit trail after those runs: 12 events (6 `ai_invocation`, 6 `rule_evaluation`),
hash chain intact from genesis. 6 artefacts written to the evidence vault.

Evidence offsets were verified byte-exact: for every located quote,
`raw_text[char_start:char_end] == quote`.

Typical cost and latency per triage call: ~1,400 input tokens, ~160 output
tokens, ~1.8 s.
