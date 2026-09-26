# AI Signal Investigation Copilot

### The idea in one line
> **Statistics detect, AI extracts, code verifies, rules decide, a human approves.** The AI never makes a regulatory decision. It only reads text and reports facts with quotes, and plain code checks those quotes.

---

## Industry
**Pharmacovigilance** — drug safety monitoring for pharma companies and drug regulators.

---

## Problem Statement
Drug safety teams must catch harmful side effects before they hurt patients. The raw material is a flood of free-text adverse-event reports (FAERS / E2B). For every drug–event pair, a safety physician has to read each case narrative, pull out the facts that establish causality — symptom onset timing, dechallenge/rechallenge, alternative causes, data gaps — and judge whether it is a real safety signal.

Today this is **slow, manual, and inconsistent**. One signal can take hours of reading, and the judgement varies from reviewer to reviewer. It is a regulated, high-stakes task where a wrong or unexplained decision is unacceptable.

---

## Why This (why AI, why now)
- LLMs are genuinely good at the hard part: reading messy clinical narratives and pulling out structured facts. That is exactly the bottleneck.
- But in a regulated domain you **cannot** let a black-box model decide, or invent facts. A model that just "summarises" reports is not usable for a regulatory call.
- So the winning move is to use AI only where it is strong — reading and extraction — and keep every decision deterministic, cited, and signed off by a human.

---

## How We Solve It
A copilot that automates the slow reading work while keeping every decision explainable, reproducible, and owned by a human.

| Stage | Who decides |
|---|---|
| Detect candidate signals (PRR, ROR 95% CI, Yates χ², Evans flagging) | **Deterministic statistics** |
| Extract clinical facts per case, each with a verbatim quote | **AI** (Nova Lite, temp 0, forced schema) |
| Check every quote is real (char offsets), reject anything unbacked | **Plain code** (guardrails) |
| Assess causality & recommend on the signal | **Versioned rules** (WHO-UMC-inspired) |
| Draft summary, override with reason, sign off | **Human** |
| Audit everything, hash-chained and replayable | **Code** |

**The core safeguard — two layers of guardrails:**
- **Level 1 (prompt):** "facts only, quote verbatim, prefer *unknown* over inference."
- **Level 2 (code):** every AI-stated fact must be backed by a verbatim quote at real character offsets in the source text, or it is thrown out.

This is why the AI can help without ever being trusted to decide.

---

## What Runs Today (prototype)
A local FastAPI app over a synthetic FAERS-style dataset (fixed seed, 1,152 reports):
- **Signals** → statistical metrics per drug–event pair
- **Case evidence** → verified facts with the exact source text highlighted
- **Review & sign-off** → editable AI draft with a citation check + human signature
- **Ask-the-evidence chat** → RAG answers with citations linking back to the source case
- **Audit trail** → hash-chained, verifiable

*15 tests pass, no network calls. Synthetic data, fictional drugs; causality rule is WHO-UMC-inspired but not clinically validated.*

---

## What We'd Build Next
- Multi-format ingestion into the same knowledge base: PDFs, scanned images (OCR), Excel, database connectors.
- Bedrock prompt caching for the static extraction prompt (tested, works).
- Authentication + e-signature, MedDRA coding, and E2B export for real regulatory workflows.
