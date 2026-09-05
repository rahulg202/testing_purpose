# Atheria Architecture

## System Overview

```
    UNSTRUCTURED WORLD              ATHERIA                     SYSTEM OF RECORD
  (emails, forms, social)    (where the thinking happens)    (where the record lives)

  email → extraction →       ingest → triage → extract →     Argus / LifeSphere /
  CIOMS forms, PDFs          code → assess → review →        Vault Safety
                             E2B(R3) generation               → regulators
```

Atheria is a **system of intelligence** that sits around the customer's system of record.
It does not replace Argus or any safety database — it automates the reasoning that
currently happens between receiving a source and typing the ICSR into the record system.

---

## Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  EXPERIENCE LAYER                                                │
│  React SPA · Case Workbench · Triage Inbox · Config Studio       │
├─────────────────────────────────────────────────────────────────┤
│  API LAYER                                                       │
│  FastAPI · CORS · Auth middleware · Request audit · Rate limiting │
├─────────────────────────────────────────────────────────────────┤
│  DOMAIN SERVICES                                                 │
│  Case Service · Coding Service · Rules Engine · E2B Service      │
├─────────────────────────────────────────────────────────────────┤
│  AI / AUTOMATION LAYER                                           │
│  Triage Agents · Extraction Agents · Coding Agents · Narrative   │
│  Bedrock Converse · Guardrails · Prompt Registry                 │
├─────────────────────────────────────────────────────────────────┤
│  INTEGRATION LAYER                                               │
│  Mail Connector · Document Extraction · Social Connectors        │
├─────────────────────────────────────────────────────────────────┤
│  DATA LAYER                                                      │
│  PostgreSQL (cases, audit) · S3 (evidence vault) · Config store  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow (MVP)

```
Email with CIOMS PDF
        │
        ▼
┌─── INGEST ────────────────────────────────────────┐
│  Mail connector → MIME parse → attachments         │
│  → Evidence writer (S3, SHA-256, manifest)         │
│  → SourceRecord created (Day 0 = receipt time)     │
└────────────────────────┬──────────────────────────┘
                         │
                         ▼
┌─── TRIAGE ────────────────────────────────────────┐
│  Product mention detection                         │
│  AE candidate detection                           │
│  Validity element extraction (4 criteria)          │
│  → Rule: all 4 present? → VALID ICSR             │
└────────────────────────┬──────────────────────────┘
                         │
                         ▼
┌─── EXTRACT ───────────────────────────────────────┐
│  CIOMS-I form profile (deterministic box mapping)  │
│  Free-text extraction (patient, drug, reaction)    │
│  Each field: value + EvidenceSpan + confidence     │
│  Agents never write directly → validator → Case    │
└────────────────────────┬──────────────────────────┘
                         │
                         ▼
┌─── CODE ──────────────────────────────────────────┐
│  Verbatim → LLT → PT candidate generation         │
│  Lexical + synonym search                          │
│  LLM re-ranker with coding conventions             │
│  Dictionary validation (exists, current, pinned)   │
└────────────────────────┬──────────────────────────┘
                         │
                         ▼
┌─── ASSESS ────────────────────────────────────────┐
│  Seriousness: 6 ICH criteria from extracted facts  │
│  → Deterministic rules (ser_003 v4.2.0)           │
│  Listedness: PT match against CCDS term table      │
│  Completeness: mandatory field check               │
│  *** NO LLM DECIDES — rules only ***              │
└────────────────────────┬──────────────────────────┘
                         │
                         ▼
┌─── REVIEW ────────────────────────────────────────┐
│  Workbench: source left, fields right              │
│  Auto-accepted (collapsed) / Review / Escalated    │
│  Accept / Edit / Reject with reason codes          │
│  Approve → e-signature + content hash              │
└────────────────────────┬──────────────────────────┘
                         │
                         ▼
┌─── OUTPUT ────────────────────────────────────────┐
│  E2B(R3) XML generation (~45 mandatory elements)   │
│  XSD validation + ICH business rules               │
│  → Download / hand to Argus Interchange            │
└───────────────────────────────────────────────────┘
```

---

## Three-Tier Decision Model

This is the single most important design rule in Atheria:

```
SOURCE EVIDENCE          AI PROPOSAL              DETERMINISTIC LAYER         HUMAN
(immutable, hashed)      (extraction +            (versioned rules +          (accept /
                         candidate + confidence    dictionaries +              edit /
                         + span citation)          validations)                reject)
       │                       │                        │                      │
       └───────────────────────┴────────────────────────┴──────────────────────┘
                                                                    │
                                                              APPROVED CASE
                                                              (E2B · signals)
```

| Component | What it does | What it never does |
|-----------|--------------|-------------------|
| AI (LLM) | Proposes values, extracts facts, ranks candidates | Makes regulatory determinations |
| Rules Engine | Decides seriousness, listedness, validity, reportability | Guesses when data is missing |
| Human | Approves, edits with reason codes, signs | Gets bypassed silently |

---

## Key Design Decisions (ADRs)

| # | Decision | Rationale |
|---|----------|-----------|
| ADR-002 | AI proposes, rules decide, humans approve | Regulatory defensibility |
| ADR-003 | No field without provenance or it's schema-invalid | Inspection readiness |
| ADR-004 (MVP) | In-process pipeline, not Step Functions | Velocity with 2 engineers |
| ADR-005 (MVP) | RDS t4g.small, not Aurora Serverless | Cost ($25/mo vs $100+) |
| ADR-006 (MVP) | S3 versioning, not Object Lock | Pre-pilot simplification |
| ADR-007 | New React SPA, not extend .NET Jubilant | Clean start, demo quality |
| ADR-011 | Auto-code only from approved mapping table | No AI-invented codes |
| ADR-015 | No silent defaults on regulatory determinations | Escalate rather than guess |
| ADR-022 | Agents have no write authority | All writes through validated services |

---

## Tenant Isolation

`tenant_id` appears in:
- Every database table (indexed, enforced at query layer)
- Every S3 key prefix: `{tenant_id}/{channel}/{yyyy}/{mm}/{dd}/{source_record_id}/`
- Every structured log line (via contextvars)
- Every audit event
- Every LLM invocation record

This is enforced at construction, not by convention. A query that forgets to filter
by tenant_id will return no results because the access layer adds it automatically.

---

## Audit Trail Design

The audit trail is **append-only** and **hash-chained**:

```
Event 1                    Event 2                    Event 3
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ content_hash: H1 │◄─────│ previous_hash: H1│◄─────│ previous_hash: H2│
│ previous: GENESIS│      │ content_hash: H2 │      │ content_hash: H3 │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

Each event's hash includes the previous event's hash, creating a tamper-evident
chain. If any event is modified or deleted, the chain breaks and
`verify_chain_integrity()` detects it.

Every audit event records:
- **What** changed (field_path, old_value, new_value)
- **Who** did it (actor_type: ai/rule/human/system, actor_id)
- **How** it was decided (model_id, prompt_version, rule_id, rule_set_version)
- **Why** (reason_code, rationale, confidence)
- **When** (timestamp, immutable)
- **In what context** (trace_id, request_id, case_id)
