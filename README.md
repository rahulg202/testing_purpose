# Atheria — AI-Native Pharmacovigilance Intelligence Platform

Atheria automates the pharmacovigilance lifecycle end-to-end: from unstructured source
intake through triage, extraction, coding, assessment, review, and E2B(R3) generation.
Every automated decision is explainable, evidence-anchored, and auditable.

**Core thesis:** The AI proposes, a versioned deterministic rules engine decides,
a qualified human approves. Atheria owns the reasoning; the customer's safety database
(Argus, LifeSphere, Vault Safety) keeps the record.

> **New to this codebase?** Read **[docs/HANDOVER.md](docs/HANDOVER.md)** first.
> It is a complete engineering handover: architecture, tech stack, full database
> schema, API reference, deployment guide, known gaps, and the reasoning behind
> every significant decision.

---

## Current State — ICSR identification working end-to-end (5 Sep 2026)

The prototype ingests real reports, has a model read them, and has a versioned
deterministic rule decide whether each one is a valid ICSR. Every decision
carries its evidence, its model/prompt version, and its rule ID.

### What works today

| Layer | Status | Description |
|-------|--------|-------------|
| Web form intake | Working | Solicited direct reports, triaged on submission |
| Literature intake | Working | Live PubMed sweeps via NCBI E-utilities, deduplicated by content hash |
| Triage (AI) | Working | Model reports the 4 ICSR criteria with verbatim evidence quotes |
| Validity rule | Working | `val_001 v1.0.0` decides valid / potential / non-ICSR, emits a full trace |
| Evidence anchoring | Working | Every quote located to character offsets in the stored source |
| Evidence vault | Working | Immutable store: local filesystem, or MinIO (S3-compatible) |
| Audit trail | Working | Hash-chained events for both the AI proposal and the rule decision |
| Pipeline tracking | Working | `pipeline_runs` / `pipeline_stages` rows per triage run |
| Inbox UI | Working | Prioritised queue, outcome badges, click-a-quote evidence highlighting |
| LLM layer | Working | Provider-agnostic; Bedrock live, Gemini implemented and switchable |
| Database | Working | SQLite by default (zero setup); PostgreSQL via Docker Compose |
| Tests | 48 passing | Rule truth table, triage pipeline, connectors, audit chain |
| CI/CD | Green | ruff → ruff format → mypy (strict) → pytest |

### Deliberately out of scope for now

- **MedDRA coding** — needs the licensed dictionary
- **Email intake** — connector deferred; web form and literature cover the demo
- **Seriousness / listedness rules** — next after ICSR identification
- **E2B(R3) export** — later
- **AWS deployment** — the stack is self-hosted open source; only Bedrock
  inference is used, and no cloud infrastructure is provisioned

### What's next

| Step | Goal |
|------|------|
| 1 | Extraction into the full canonical case (patient, drug, reaction blocks) |
| 2 | Seriousness rules (`ser_003`) over the 6 ICH criteria |
| 3 | Review and approval loop with e-signature |
| 4 | Audit viewer, then E2B(R3) generation |

---

## Quick Start

### Prerequisites

- Python 3.11+, Node.js 20+
- AWS credentials with Bedrock access (inference only — nothing is deployed)
- No database server needed: SQLite is the default

### 1. Backend

```bash
cd ATheria
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install -e packages/atheria-contracts
pip install -e packages/atheria-llm

# Create the schema (SQLite file in the repo root)
cd backend && ATHERIA_DATABASE_URL="sqlite:///$(cd ..&&pwd)/atheria.db" alembic upgrade head && cd ..

uvicorn backend.app.main:app --reload --reload-include '*.yaml' --port 8000
```

API docs: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173/inbox (auth bypassed in dev mode)

### 3. Try it

In the Inbox, either submit a web-form report (three preset scenarios show the
three possible outcomes) or run a live PubMed sweep. Then click any evidence
quote to highlight it in the source text.

From the command line:

```bash
curl -s localhost:8000/api/v1/intake/web-form \
  -H 'content-type: application/json' -H 'x-tenant-id: acme_pharma' \
  -d '{"narrative":"I am Dr. Rao. My patient, a 54-year-old woman, took Atherex 100mg and developed a severe rash needing hospital admission."}' | jq '.icsr_outcome, .rule_trace.explanation'
```

### Self-hosted stack (Postgres + MinIO, all open source)

```bash
docker compose up -d
docker compose --profile tools run --rm migrate
```

Postgres replaces RDS, MinIO replaces S3. No AWS infrastructure is created.

---

## Project Structure

```
ATheria/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── api/v1/            # API route handlers
│   │   │   ├── health.py      # Health check endpoints
│   │   │   ├── intake.py      # Web form + PubMed literature intake
│   │   │   ├── triage.py      # Run/inspect triage, expose the rule set
│   │   │   ├── inbox.py       # Triage work queue + stats
│   │   │   ├── cases.py       # Case CRUD + approve + audit
│   │   │   └── fixtures.py    # Golden fixture serving (dev)
│   │   ├── connectors/        # INTAKE — one module per channel
│   │   │   ├── base.py        # SourceRecord assembly, hashing, Day 0
│   │   │   ├── web_form.py    # Solicited direct reports
│   │   │   └── pubmed.py      # NCBI E-utilities literature sweeps
│   │   ├── rules/             # DETERMINISTIC DECISIONS
│   │   │   └── validity.py    # val_001 — the 4 ICSR minimum criteria
│   │   ├── prompts/           # Versioned prompt YAML
│   │   │   └── triage_icsr.yaml
│   │   ├── core/              # Configuration, DB, logging
│   │   │   ├── config.py      # Pydantic settings (env vars)
│   │   │   ├── database.py    # SQLAlchemy async engine
│   │   │   ├── evidence.py    # Evidence vault (filesystem | MinIO)
│   │   │   ├── llm.py         # Cached provider + prompt registry
│   │   │   └── logging.py     # Structlog JSON logging
│   │   ├── middleware/        # Request processing
│   │   │   ├── request_audit.py   # Trace context + request logging
│   │   │   └── error_handler.py   # Global exception handling
│   │   ├── models/            # SQLAlchemy ORM models
│   │   │   ├── base.py        # Base, TenantMixin, TimestampMixin
│   │   │   └── case.py        # All DB models (cases, audit, pipeline)
│   │   ├── services/          # Business logic
│   │   │   ├── triage_service.py  # AI proposes → rule decides → persist
│   │   │   ├── inbox_service.py   # Work queue read model
│   │   │   ├── case_service.py    # Case CRUD + versioning
│   │   │   └── audit_service.py   # Hash-chained audit events
│   │   └── main.py            # FastAPI app factory
│   ├── migrations/            # Alembic DB migrations
│   │   └── versions/001_initial_schema.py
│   ├── tests/                 # pytest test suite
│   ├── Dockerfile             # Multi-stage production build
│   └── alembic.ini
│
├── frontend/                   # React SPA (Vite + TypeScript + Tailwind)
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/AppLayout.tsx      # Sidebar + main content
│   │   │   └── workbench/
│   │   │       ├── Workbench.tsx         # Split-pane container
│   │   │       ├── FieldList.tsx         # Grouped fields with provenance
│   │   │       └── SourcePane.tsx        # Evidence viewer (Sprint 5: PDF)
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx         # Health check + stats
│   │   │   ├── InboxPage.tsx             # Triage inbox (Sprint 3)
│   │   │   ├── WorkbenchPage.tsx         # Case review screen
│   │   │   └── LoginPage.tsx             # Auth (bypassed in dev)
│   │   ├── hooks/useAuth.tsx             # Auth context (dev: always authenticated)
│   │   ├── types/case.ts                 # TypeScript case types
│   │   ├── lib/utils.ts                  # Helpers (cn, apiFetch, formatDate)
│   │   ├── App.tsx                       # Routes + protected layout
│   │   ├── main.tsx                      # Entry point
│   │   └── index.css                     # Tailwind + component classes
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── tsconfig.json
│
├── packages/
│   ├── atheria-contracts/      # Shared Pydantic models
│   │   └── atheria_contracts/
│   │       ├── enums.py        # All PV domain enumerations
│   │       ├── provenance.py   # Provenanced[T], EvidenceSpan, Locator
│   │       ├── source_record.py # SourceRecord (Contract C7)
│   │       ├── canonical_case.py # CanonicalCase (Contract C8)
│   │       ├── audit.py        # AuditEvent
│   │       └── schema_export.py # JSON Schema generation
│   │
│   └── atheria-llm/            # Provider-agnostic inference layer
│       └── atheria_llm/
│           ├── base.py         # LLMProvider protocol, LLMConfig, LLMResponse
│           ├── factory.py      # get_provider() — the single switch point
│           ├── providers/
│           │   ├── bedrock.py  # Converse + forced tool-use structured output
│           │   └── gemini.py   # Google AI Studio (responseSchema JSON mode)
│           └── prompts.py      # PromptRegistry (versioned YAML)
│
├── infrastructure/             # AWS CDK (TypeScript)
│   ├── lib/atheria-stack.ts    # VPC, RDS, S3, ECS, Cognito
│   ├── bin/app.ts              # CDK app entry
│   ├── package.json
│   └── cdk.json
│
├── fixtures/                   # Golden test cases
│   ├── golden_case_01_fully_populated.json
│   ├── golden_case_02_sparse_with_unknowns.json
│   └── golden_case_03_escalation.json
│
├── .github/workflows/ci.yml   # GitHub Actions CI pipeline
├── pyproject.toml              # Root Python project config
└── .gitignore
```

---

## How ICSR identification works

```
intake ──► evidence vault ──► AI proposes ──► RULE DECIDES ──► inbox
(web form,   (immutable,      (4 criteria +   (val_001,        (human
 PubMed)      SHA-256)         verbatim        versioned)        approves)
                               quotes)
```

The split is the whole point. The model is **forbidden** — by prompt and by code
path — from deciding validity. It only reports what the source text says about
each of the four ICSR minimum criteria, quoting its evidence. A deterministic,
versioned rule then makes the regulatory call:

| Condition | Outcome | Rule fired |
|-----------|---------|------------|
| All four criteria present | `valid_icsr` | `val_001_all_criteria_present` |
| Suspect product or adverse event absent | `non_icsr` | `val_001_missing_core_element` |
| Product + event present, patient or reporter absent | `potential_icsr` | `val_001_incomplete_escalate` |

That third row is the one that matters most: a real safety signal with an
incomplete record is **escalated for follow-up, never guessed at and never
discarded**. Rules are pure functions, so the same facts and the same
`rule_set_version` always reproduce the same decision — years later, during an
inspection.

Each triage writes two audit events: an `ai_invocation` (which model, which
prompt version) and a `rule_evaluation` (which rule, which version, what
outcome), hash-chained to the previous event.

Example decision trace:

> **POTENTIAL ICSR.** Rule val_001 v1.0.0. A suspect product and an adverse
> event are both present, but identifiable patient and identifiable reporter
> could not be established from the source. We do not guess — escalating for
> human review and follow-up rather than asserting or discarding validity.

---

## Architecture Principles

1. **AI proposes, rules decide, humans approve** — every regulatory determination has a rule ID and version
2. **Nothing without provenance** — every field carries `evidence_ref`, `produced_by`, `confidence`
3. **Fail loud, never silent** — every failure is a terminal state with a typed error
4. **Immutable evidence, append-only decisions** — SHA-256 hashes, hash-chained audit
5. **Durable orchestration** — pipeline_run/pipeline_stage tables, not conversational chains
6. **Deterministic replay** — same inputs + versions = same output, always
7. **Tenant isolation by construction** — `tenant_id` in every table, S3 key, and log line
8. **Degrade, don't stop** — manual entry always possible if AI/external services are down
9. **Configuration over code** — rules, thresholds, prompts are versioned config objects
10. **Boring where it matters** — relational DB for cases, event-driven for throughput

---

## API Reference

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Service status |
| GET | `/api/v1/health/ready` | Dependency readiness |

### Intake
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/intake/web-form` | Submit a direct report; triages immediately |
| POST | `/api/v1/intake/literature/pubmed` | Live PubMed sweep; ingests and triages new articles |

### Triage
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/triage/{source_record_id}` | Run or re-run triage |
| GET | `/api/v1/triage/{source_record_id}` | Stored triage result |
| GET | `/api/v1/triage/rules/validity` | The active rule set and its decision table |

### Inbox
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/inbox` | Prioritised work queue (filter by `status`, `outcome`) |
| GET | `/api/v1/inbox/stats` | Counts by status and ICSR outcome |
| GET | `/api/v1/inbox/{source_record_id}` | Full detail with source text and evidence |

### Cases (requires PostgreSQL)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/cases` | List cases for tenant |
| POST | `/api/v1/cases` | Create new case |
| GET | `/api/v1/cases/{id}` | Get latest version |
| GET | `/api/v1/cases/{id}/versions/{v}` | Get specific version |
| PATCH | `/api/v1/cases/{id}` | Update fields (new version) |
| POST | `/api/v1/cases/{id}/approve` | Approve with e-signature |
| GET | `/api/v1/cases/{id}/audit` | Hash-chained audit trail |

### Fixtures (development)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/fixtures/cases` | List golden cases |
| GET | `/api/v1/fixtures/cases/{id}` | Get fixture by ID |

### Headers
- `x-tenant-id` — tenant isolation (default: "default")
- `x-actor-id` — acting user for audit
- `x-trace-id` — distributed trace correlation
- `x-request-id` — request deduplication

---

## Technology Stack

Open source and self-hostable throughout; Bedrock inference is the only
managed dependency.

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | Python 3.11 + FastAPI | Matches existing PV pipeline code |
| Frontend | React + Vite + TypeScript + Tailwind | One polished workbench screen |
| Database | SQLite (dev) → PostgreSQL 16 (self-hosted) | Zero-setup locally, same code either way |
| Object Store | Local filesystem (dev) → MinIO | S3-compatible, open source, versioned |
| AI | Bedrock Converse, behind a provider interface | Structured output via forced tool-use; Gemini swappable |
| Auth | Dev bypass → Keycloak | Open source, no vendor lock-in |
| Deployment | Docker Compose | No cloud infrastructure required |
| CI | GitHub Actions | Free tier sufficient |
| Observability | Structlog JSON logs | Queryable, correlated by trace_id |

### Model selection

Nova Lite is the default: the cheapest Bedrock model that reliably honours the
triage output schema, at roughly **$0.14 per 1,000 cases**. Nova Micro is
cheaper but was verified to silently drop schema fields, so it is not usable
here. See `docs/DEVELOPMENT.md` for the full comparison.

---

## Environment Variables

All prefixed with `ATHERIA_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ATHERIA_ENVIRONMENT` | development | dev / staging / production |
| `ATHERIA_DATABASE_URL` | postgresql+asyncpg://...localhost | DB connection |
| `ATHERIA_AWS_REGION` | us-east-1 | AWS region |
| `ATHERIA_BEDROCK_MODEL_ID` | anthropic.claude-sonnet-4-20250514 | Default model |
| `ATHERIA_EVIDENCE_BUCKET` | atheria-evidence-dev | S3 bucket name |
| `ATHERIA_COGNITO_USER_POOL_ID` | — | Cognito pool |
| `ATHERIA_COGNITO_APP_CLIENT_ID` | — | Cognito client |
| `ATHERIA_CORS_ORIGINS` | ["http://localhost:5173"] | Allowed origins |
| `ATHERIA_LOG_LEVEL` | INFO | Log verbosity |
| `ATHERIA_LOG_FORMAT` | json | json or console |

---

## Golden Fixtures

Three hand-authored cases for development and testing:

| File | Scenario | Key features |
|------|----------|--------------|
| `golden_case_01_fully_populated.json` | Non-serious, complete | All fields populated, MedDRA coded (hypoaesthesia), narrative generated, coverage passed |
| `golden_case_02_sparse_with_unknowns.json` | Serious, incomplete | Missing age/dose/outcome, escalated fields, seriousness by rule, follow-up questions generated |
| `golden_case_03_escalation.json` | German physician report, serious | Hepatotoxicity, translated verbatims, rule traces with explicit "we do not guess" escalation |

These demonstrate the three demo beats that matter:
- **Beat 4:** Click any field → see the source sentence (evidence spans)
- **Beat 6:** "SERIOUS — hospitalisation. Rule ser_003 v4.2.0. Basis: this sentence."
- **Beat 7:** "Life-threatening status could not be determined — we escalate rather than guess."
