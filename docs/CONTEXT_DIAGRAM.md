# Atheria — Level 0 Context Diagram

A Level 0 (context) diagram treats the whole platform as a **single process** and
shows only what crosses its boundary: who sends data in, what external services
it depends on, who consumes its output, and what it stores.

For the internal breakdown, see [ARCHITECTURE.md](ARCHITECTURE.md). For the
engineering detail, see [HANDOVER.md](HANDOVER.md).

---

## Scope note: what is and is not in this repository

| Component | In this repo? | Model / provider |
|---|---|---|
| Web form intake | **Yes** | — |
| PubMed literature intake | **Yes** | — |
| Triage + validity rules | **Yes** | Amazon Bedrock, Nova Lite |
| Reviewer inbox | **Yes** | — |
| **Voice agent** (conversational complaint capture) | **No — separate service** | Anthropic API, Claude Haiku 4.5 |
| Email intake | **No — planned** | — |

The voice agent is a **separate deployment** that calls the Anthropic API
directly rather than going through this codebase's Bedrock provider layer. It is
shown in the diagram because it is a real intake channel from the platform's
point of view, but it is drawn with a dashed boundary to make its separateness
explicit. It reaches Atheria the same way any other channel does: by producing a
`SourceRecord` through an intake endpoint.

---

## Level 0 diagram

```mermaid
graph TB
    %% ---------- External entities: data sources ----------
    HCP["Healthcare Professional<br/>physician · pharmacist · nurse"]
    PATIENT["Patient / Consumer"]
    NCBI["NCBI PubMed<br/>E-utilities API"]

    %% ---------- Voice agent: separate service ----------
    subgraph VOICE ["Voice Agent — SEPARATE SERVICE, not in this repo"]
        direction TB
        VA["Conversational Intake Bot<br/>Anthropic API · Claude Haiku 4.5"]
    end

    %% ---------- The system ----------
    ATHERIA(("<b>0</b><br/><b>ATHERIA</b><br/>PV Intelligence Platform<br/>ICSR Identification"))

    %% ---------- External services ----------
    BEDROCK["Amazon Bedrock<br/>Nova Lite<br/>reads source text"]

    %% ---------- Consumers ----------
    REVIEWER["Safety Reviewer<br/>qualified human"]
    MGMT["PV Management"]

    %% ---------- Data stores ----------
    DB[("Case Store<br/>source records · triage results<br/>audit chain · pipeline runs")]
    VAULT[("Evidence Vault<br/>immutable raw content<br/>SHA-256 hashed")]

    %% ---------- Future ----------
    SAFETYDB["Customer Safety Database<br/>Argus · LifeSphere · Vault Safety<br/><i>future</i>"]
    REGULATOR["Regulators<br/>EMA · FDA<br/><i>future</i>"]

    %% ---------- Inbound flows ----------
    HCP -->|"adverse event report<br/>via web form"| ATHERIA
    PATIENT -->|"adverse event report<br/>via web form"| ATHERIA
    PATIENT -.->|"spoken / chat<br/>complaint"| VA
    HCP -.->|"spoken / chat<br/>complaint"| VA
    VA ==>|"structured complaint<br/>→ SourceRecord"| ATHERIA
    NCBI -->|"article titles<br/>+ abstracts"| ATHERIA
    ATHERIA -->|"literature<br/>search query"| NCBI

    %% ---------- AI flow ----------
    ATHERIA -->|"source text<br/>+ versioned prompt"| BEDROCK
    BEDROCK -->|"4 ICSR criteria<br/>+ verbatim evidence quotes"| ATHERIA

    %% ---------- Storage flows ----------
    ATHERIA -->|"raw content<br/>write-once"| VAULT
    VAULT -->|"stored evidence"| ATHERIA
    ATHERIA -->|"determinations<br/>+ audit events"| DB
    DB -->|"work queue<br/>+ decision history"| ATHERIA

    %% ---------- Outbound flows ----------
    ATHERIA -->|"ICSR determination<br/>+ evidence + rule trace"| REVIEWER
    REVIEWER -->|"accept · edit · escalate"| ATHERIA
    ATHERIA -->|"volumes · outcomes<br/>· escalation rates"| MGMT
    ATHERIA -.->|"approved case<br/><i>not built</i>"| SAFETYDB
    ATHERIA -.->|"E2B(R3) submission<br/><i>not built</i>"| REGULATOR

    classDef system fill:#1e3a8a,stroke:#1e3a8a,color:#fff,stroke-width:2px
    classDef external fill:#f1f5f9,stroke:#64748b,color:#0f172a
    classDef store fill:#fef9c3,stroke:#ca8a04,color:#0f172a
    classDef ai fill:#dcfce7,stroke:#16a34a,color:#0f172a
    classDef future fill:#f8fafc,stroke:#cbd5e1,color:#64748b,stroke-dasharray: 5 5
    classDef voice fill:#fae8ff,stroke:#a21caf,color:#0f172a,stroke-dasharray: 4 4

    class ATHERIA system
    class HCP,PATIENT,NCBI,REVIEWER,MGMT external
    class DB,VAULT store
    class BEDROCK ai
    class VA voice
    class SAFETYDB,REGULATOR future
```

---

## The same diagram in plain text

For anywhere Mermaid does not render.

```
                    DATA SOURCES                                    CONSUMERS
  ┌──────────────────────────────────────┐              ┌──────────────────────────┐
  │                                      │              │                          │
  │  ┌────────────────────────┐          │              │   ┌──────────────────┐   │
  │  │ Healthcare Professional│──┐       │              │   │ Safety Reviewer  │   │
  │  │ physician · pharmacist │  │       │              │   │ qualified human  │   │
  │  └────────────────────────┘  │       │              │   └────────▲─────────┘   │
  │                              │       │              │            │             │
  │  ┌────────────────────────┐  │       │              │   determination +        │
  │  │ Patient / Consumer     │──┤       │              │   evidence + rule trace  │
  │  └────────────────────────┘  │       │              │            │             │
  │                              │       │              │   ┌────────┴─────────┐   │
  │  ╔══════════════════════════╗│       │              │   │ PV Management    │   │
  │  ║ VOICE AGENT (separate)   ║│       │              │   │ volumes/outcomes │   │
  │  ║ Anthropic · Haiku 4.5    ║├───────┤              │   └──────────────────┘   │
  │  ║ conversational capture   ║│       │              └──────────▲───────────────┘
  │  ╚══════════════════════════╝│       │                         │
  │                              │       │                         │
  │  ┌────────────────────────┐  │       │                         │
  │  │ NCBI PubMed E-utilities│◄─┤       │                         │
  │  │ titles + abstracts     │──┘       │                         │
  │  └────────────────────────┘          │                         │
  └───────────────┬──────────────────────┘                         │
                  │ reports / articles                             │
                  │ (all become SourceRecords)                     │
                  ▼                                                │
      ╔═══════════════════════════════════════════════════╗         │
      ║                        0                          ║─────────┘
      ║                    A T H E R I A                  ║
      ║           PV Intelligence Platform                ║
      ║              ICSR Identification                  ║
      ║                                                   ║
      ║   intake → evidence → AI proposes →               ║
      ║           RULES DECIDE → human reviews            ║
      ╚═══╦═══════════════════╦═══════════════════════╦═══╝
          │                   │                       │
          │ source text       │ raw content           │ determinations
          │ + prompt          │ (write-once)          │ + audit events
          ▼                   ▼                       ▼
  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐
  │ Amazon Bedrock   │  │ Evidence Vault   │  │ Case Store             │
  │ Nova Lite        │  │ immutable        │  │ source records         │
  │                  │  │ SHA-256 hashed   │  │ triage results         │
  │ returns:         │  │                  │  │ hash-chained audit     │
  │ 4 ICSR criteria  │  │ filesystem/MinIO │  │ pipeline runs          │
  │ + evidence quotes│  │ /R2              │  │ SQLite/PostgreSQL      │
  └──────────────────┘  └──────────────────┘  └────────────────────────┘

  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ NOT BUILT YET ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  Customer Safety Database (Argus/LifeSphere/Vault) · Regulators via E2B(R3)
```

---

## Data flows crossing the boundary

### Inbound

| # | From | Data | Channel class |
|---|---|---|---|
| 1 | Healthcare professional | Adverse event report (reporter, patient, product, event, narrative) | `solicited` |
| 2 | Patient / consumer | Adverse event report | `solicited` |
| 3 | **Voice agent** (separate service) | Structured complaint captured conversationally | `solicited` |
| 4 | NCBI PubMed | Article titles and abstracts | `literature` |
| 5 | Safety reviewer | Accept / edit / escalate decisions | — |

### Outbound

| # | To | Data |
|---|---|---|
| 6 | NCBI PubMed | Literature search query (`esearch`, then `efetch`) |
| 7 | Amazon Bedrock | Source text + versioned prompt + JSON output schema |
| 8 | Safety reviewer | ICSR determination, evidence spans, rule trace |
| 9 | PV management | Volumes, outcome mix, escalation rates |
| 10 | *(future)* Customer safety database | Approved case |
| 11 | *(future)* Regulators | E2B(R3) submission |

### Stored

| Store | Contents | Property |
|---|---|---|
| **Evidence Vault** | Raw inbound content, exactly as received | Write-once, SHA-256 hashed, tenant-scoped keys |
| **Case Store** | Source records, triage results, audit events, pipeline runs | Audit trail is append-only and hash-chained |

---

## Where the voice agent fits

The voice agent is a **peer intake channel**, not a layer inside Atheria:

```
Voice agent (Anthropic Haiku 4.5)          Atheria (Bedrock Nova Lite)
├─ Holds a conversation                    ├─ Reads the finished report
├─ Asks follow-up questions                ├─ Reports the 4 ICSR criteria
├─ Produces a structured complaint         ├─ Runs val_001 to decide validity
└─ Hands it over ──────────────────────►   └─ Escalates or accepts
```

Two different jobs, which is why two different models is reasonable rather than
redundant. The voice agent's task is *elicitation* — keeping a person talking
until the account is complete. Atheria's task is *determination* — deciding
whether what arrived is a reportable ICSR.

Note the deliberate division of authority: the voice agent may gather and
structure information, but it does **not** decide whether the complaint is a
valid ICSR. That decision belongs to `val_001` inside Atheria, like every other
channel. A conversational agent that also adjudicated validity would put a
regulatory determination inside an LLM, which is precisely what the architecture
avoids.

### To integrate it

The voice agent should `POST /api/v1/intake/web-form` with its collected fields.
It needs no new code on the Atheria side. If voice conversations should be
distinguishable from typed web-form submissions in reporting — and they probably
should, since channel class drives regulatory obligations — then add
`Channel.VOICE_CALL` (the enum value already exists) and a thin
`connectors/voice.py` following the `web_form.py` pattern, plus an
`/intake/voice` route. That is roughly an hour of work.

Worth deciding early: whether the **conversation transcript** is archived to the
Evidence Vault. For provenance it should be, because the transcript is the
source document that any extracted value must be traceable to.
