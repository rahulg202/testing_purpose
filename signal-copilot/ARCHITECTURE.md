# Architecture — AI Signal Investigation Copilot

> **The idea in one line:** Statistics detect, AI extracts, code verifies, rules decide, a human approves. The AI never makes a regulatory decision. It only reads text and reports facts with quotes, and plain code checks those quotes.

These diagrams describe the prototype as built (FastAPI + SQLite + AWS Bedrock, Nova Lite + Titan v2).

---

## 1. High-Level System Architecture

Component view: the browser talks to a FastAPI app, which drives one `Copilot` service over five deterministic/AI stages, backed by SQLite (cache + state + hash-chained audit) and AWS Bedrock (Nova Lite for generation, Titan v2 for embeddings).

```mermaid
flowchart TB
    subgraph Client["Browser (single user, 127.0.0.1)"]
        UI["Pages: Signals · Case Evidence · Review/Sign-off · Chat · Audit"]
    end

    subgraph App["FastAPI app (app.py)"]
        API["HTTP routes"]
    end

    subgraph Core["Copilot service (service.py)"]
        direction TB
        STATS["1. stats.py<br/>PRR · ROR 95% CI · Yates chi2 · Evans<br/><i>deterministic detection</i>"]
        LLMX["2. llm.py<br/>Nova Lite, temp 0, forced schema<br/><i>AI fact extraction</i>"]
        GUARD["3. guardrails.py<br/>schema + verbatim-quote + negation<br/><i>deterministic verification</i>"]
        RULES["4. rules.py<br/>cau_001 v1.1.0 · rec_001 v1.0.0<br/><i>versioned decision rules</i>"]
        HUMAN["5. Human<br/>override w/ reason · edit · sign-off"]
        RAG["rag.py<br/>two-tier vector retrieval (chat)"]
    end

    subgraph Data["SQLite (store.py — data/copilot.db)"]
        CACHE[("cache<br/>extractions + embeddings")]
        INV[("investigations<br/>state")]
        AUDIT[("audit<br/>hash-chained")]
    end

    subgraph Bedrock["AWS Bedrock (ap-south-1)"]
        NOVA["Nova Lite<br/>generation"]
        TITAN["Titan Text Embeddings v2<br/>512-d, normalised"]
    end

    DATASET["dataset.py<br/>synthetic FAERS-style<br/>1,152 reports, fixed seed"]

    UI <--> API
    API --> STATS --> LLMX --> GUARD --> RULES --> HUMAN
    API --> RAG
    DATASET --> STATS

    LLMX -->|structured tool call| NOVA
    RAG -->|embed| TITAN
    RAG -->|answer| NOVA

    LLMX <-->|read/write| CACHE
    RAG <-->|read/write| CACHE
    Core -->|read/write| INV
    Core -->|append only| AUDIT
```

---

## 2. Data Retrieval Architecture (RAG)

The chat is scoped to a single signal's cases. Retrieval is **two-tier**: summary vectors first pick the most relevant *cases*, then chunk (sentence) vectors inside those cases pick the *evidence*. A hybrid score mixes cosine similarity with keyword overlap, a relevance gate refuses to answer when nothing is similar enough, and every citation the model returns is re-checked against the source narrative before it is shown.

```mermaid
flowchart TB
    Q["User question (scoped to one signal)"]

    subgraph Build["KnowledgeBase build (per signal, cached)"]
        CASES["Signal cases + verified facts"]
        SUMS["Tier-1: one summary vector per case<br/>case_summary_text()"]
        CHUNKS["Tier-2: sentence chunks with char offsets<br/>sentence_chunks()"]
        EMB["Titan v2 embeddings<br/>ThreadPool x8, cached by content hash"]
        CASES --> SUMS --> EMB
        CASES --> CHUNKS --> EMB
    end

    subgraph Retrieve["retrieve(question)"]
        QEMB["Embed question (Titan v2)"]
        T1["Tier 1: rank cases by hybrid score<br/>top 10 cases"]
        T2["Tier 2: rank chunks within chosen cases<br/>top 14 chunks"]
        GATE{"best cosine >= 0.1 ?<br/>(relevance gate)"}
        QEMB --> T1 --> T2 --> GATE
    end

    HYBRID["hybrid = 0.7·cosine + 0.3·keyword overlap"]
    T1 -.uses.-> HYBRID
    T2 -.uses.-> HYBRID

    REFUSE["Refuse: 'no supporting evidence'<br/>(no LLM call)"]
    subgraph Answer["Grounded answer"]
        CTX["Build context:<br/>signal stats + case summaries + narrative chunks"]
        GEN["Nova Lite → answer + citations"]
        VERIFY["verify_citations():<br/>case in KB AND quote found in narrative"]
        OUT["Answer + verified citations<br/>(link to source case)<br/>rejected citations dropped"]
        CTX --> GEN --> VERIFY --> OUT
    end

    Q --> QEMB
    EMB -.vectors.-> Retrieve
    GATE -- no --> REFUSE
    GATE -- yes --> CTX
    OUT --> AUDITLOG["Audit: chat_exchange<br/>(question, chunk ids, citations, grounding)"]
```

---

## 3. Investigation Pipeline (per-case sequence)

How a single "investigate this signal" request flows through the five stages, including the extraction cache (replay needs zero LLM calls) and the guardrail downgrade path.

```mermaid
sequenceDiagram
    autonumber
    actor Analyst
    participant API as FastAPI
    participant S as Copilot (service.py)
    participant DB as SQLite cache
    participant Nova as Nova Lite
    participant G as guardrails.py
    participant R as rules.py
    participant AU as Audit (hash-chained)

    Analyst->>API: investigate(signal_id)
    API->>S: run pipeline
    Note over S: stats already computed<br/>(PRR/ROR/chi2) at load
    loop each case (ThreadPool x8)
        S->>DB: cache_get(model, prompt_ver, narrative)
        alt cache miss
            S->>Nova: structured extract (temp 0, forced schema)
            Nova-->>S: raw facts + quotes
            S->>G: validate_schema + sanitize_lists
            S->>DB: cache_put (only if schema-valid)
        else cache hit
            DB-->>S: cached extraction (no LLM call)
        end
        S->>G: verify_extraction (locate every quote)
        Note over G: quote not found → fact downgraded<br/>to unknown/unverified<br/>negated cause → reclassified as excluded
        G-->>S: verified facts + counts
        S->>R: assess_causality (cau_001)
        R-->>S: category + rule_id + explanation
        S->>AU: audit ai_extraction + rule_evaluation
    end
    S->>R: recommend (rec_001, signal-level)
    S->>AU: audit rule_evaluation (signal scope)
    S-->>API: state (metrics, cases, recommendation)
    API-->>Analyst: overview page
```

---

## 4. Guardrail / Verification Decision Flow

The deterministic gate the model cannot argue past. Every AI-stated fact must resolve to a verbatim quote at real character offsets in the source, or it is downgraded and counted as rejected.

```mermaid
flowchart TD
    RAW["AI raw output for a case"] --> SAN["sanitize_lists()<br/>drop malformed cause items (counted, not lost)"]
    SAN --> SCHEMA{"validate_schema()<br/>matches forced schema?"}
    SCHEMA -- no --> REJECT["Reject case<br/>facts = null → Unassessable<br/>human review required"]
    SCHEMA -- yes --> CACHE["Cache schema-valid output"]
    CACHE --> LOOP["For each fact / cause with a value"]
    LOOP --> UNK{"value unknown / null?"}
    UNK -- yes --> KEEPUNK["Keep as 'unknown'<br/>(no quote required)"]
    UNK -- no --> LOC{"locate_quote()<br/>verbatim in narrative?"}
    LOC -- no --> DOWN["Downgrade to unknown<br/>status = unverified<br/>rejected++"]
    LOC -- yes --> NEG{"is_negated(quote)?<br/>(alt cause only)"}
    NEG -- yes --> EXCL["Reclassify as excluded cause<br/>(negation guardrail)"]
    NEG -- no --> VER["Accept: verified<br/>store exact source span<br/>verified++"]
    VER --> RULES2["→ rules.py (decides category)"]
    EXCL --> RULES2
    KEEPUNK --> RULES2
    DOWN --> RULES2
```

---

## 5. Trust & Audit Model (who is allowed to decide)

Shows the trust boundary: AI outputs are treated as untrusted until verified by code; only deterministic rules and the human produce decisions; everything is written to an append-only hash-chained log.

```mermaid
flowchart LR
    subgraph Untrusted["Untrusted (AI, must be verified)"]
        EX["Nova Lite extraction"]
        DR["Nova Lite draft summary"]
        CH["Nova Lite chat answer"]
    end

    subgraph Verify["Deterministic verification (code)"]
        QV["Verbatim quote check<br/>+ char offsets"]
        CC["Citation checks"]
    end

    subgraph Trusted["Trusted decisions"]
        ST["Statistics (PRR/ROR/chi2)"]
        RU["Versioned rules<br/>cau_001 / rec_001"]
        HU["Human override + sign-off"]
    end

    LOG[("Append-only<br/>hash-chained audit<br/>verify_chain()")]

    EX --> QV --> RU
    DR --> CC
    CH --> CC
    ST --> RU --> HU
    QV -. every fact .-> LOG
    RU -. every decision .-> LOG
    HU -. override + sign-off .-> LOG
    CC -. citations .-> LOG
```

---

### Key technical facts referenced above
- **Models:** Nova Lite (`apac.amazon.nova-lite-v1:0`) at temperature 0 with a forced tool schema; Titan Text Embeddings v2 (512-d, L2-normalised), region `ap-south-1`.
- **RAG constants:** top 10 cases, top 14 chunks, relevance gate at cosine ≥ 0.1, hybrid weight 0.3 lexical / 0.7 cosine.
- **Persistence:** SQLite (`data/copilot.db`) — content-hash cache (replay = zero LLM calls), investigation state, append-only hash-chained audit with `verify_chain()`.
- **Rules:** `cau_001 v1.1.0` (WHO-UMC-inspired causality), `rec_001 v1.0.0` (signal recommendation) — versioned and fully deterministic.
