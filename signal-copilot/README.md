# AI Signal Investigation Copilot

Pharmacovigilance signal investigation, with the slow manual work automated and every decision kept deterministic and signed off by a human.

**Statistics detect → AI extracts (verified) → Rules decide → Humans approve.**

## Run (one command)

```bash
cd signal-copilot
../.venv/bin/pip install fastapi==0.115.14 uvicorn==0.34.3 boto3==1.43.75 pydantic==2.13.4 hypothesis==6.112.1 pytest
../.venv/bin/python -m signal_copilot        # http://127.0.0.1:8100
../.venv/bin/python -m pytest -q             # 15 tests, no network
```

You need AWS credentials with Bedrock access in `ap-south-1` (Nova Lite for generation, Titan Text Embeddings v2 for retrieval).
Delete `data/copilot.db` to reset the cache and audit trail.

## Pages

| URL | Page |
|---|---|
| `/` | Signals: every drug–event pair, drug filter, investigate any pair |
| `/signal/{id}` | Overview: metrics, rule recommendation, filterable case list |
| `/signal/{id}/case/{report}` | Case evidence: verified facts, source highlight (`?s=&e=` offsets), override, prev/next |
| `/signal/{id}/review` | AI draft summary, citation check, edit, sign-off |
| `/signal/{id}/chat` | Ask the evidence (RAG); citations link to the case page |
| `/audit` | Hash-chained audit trail with chain verification |

## How it works

| Stage | Who decides | Module |
|---|---|---|
| Synthetic FAERS-style dataset (fixed seed, 1,152 reports; causal features only in narratives) | code | `dataset.py` |
| PRR, ROR 95% CI, Yates χ², Evans flagging | deterministic statistics | `stats.py` |
| Per-case fact extraction (onset, de/rechallenge, alternative and excluded causes, gaps) | Nova Lite, temperature 0, forced tool schema | `llm.py` |
| Level 1 guardrails: versioned prompts ("facts only, quote verbatim, unknown over inference") | prompt | `llm.py` |
| Level 2 guardrails: schema validation, verbatim-quote check with char offsets, negation reclassifier, citation checks | deterministic code | `guardrails.py` |
| Causality per case (`cau_001 v1.1.0`) and signal recommendation (`rec_001 v1.0.0`) | versioned pure rules | `rules.py` |
| Draft summary (case IDs checked against the signal) | Nova Lite, labelled "AI draft" | `service.py` |
| Override with reason, editable summary, sign-off | human | UI + `service.py` |
| Hash-chained audit, extraction and embedding cache (replay needs zero LLM calls) | code | `store.py` |
| RAG chatbot: summary vectors pick cases, chunk vectors pick sentences, hybrid lexical score, relevance gate, verified citations | Titan embeddings + Nova Lite | `rag.py` |

## Assumptions

Synthetic data and fictional drugs. The causality rule is WHO-UMC-inspired but not clinically validated. The time-saved figure assumes 15 min of manual review per case. This is a single-user local prototype: there is **no authentication** and it binds to 127.0.0.1 only.

## Next steps

- Multi-format ingestion into the same KB: PDFs via pymupdf4llm, scanned images via Tesseract OCR, Excel, and database connectors.
- Bedrock prompt caching (`cachePoint`) for the static extraction prompt, which was tested and works on Nova Lite.
- Authentication and e-signature, MedDRA coding, and E2B export.
