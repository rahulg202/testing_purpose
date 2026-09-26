"""Investigation pipeline: statistics detect -> AI extracts -> guardrails verify -> rules decide -> human approves."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from . import MINUTES_PER_CASE
from . import dataset, guardrails, llm as prompts, rules, stats
from .llm import LLM
from .rag import KnowledgeBase
from .store import Store, cache_key, sha256

SYSTEM = "system"


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


class Copilot:
    def __init__(self, llm: LLM, store: Store, reports: list[dict] | None = None) -> None:
        self.llm, self.store = llm, store
        self.reports = reports if reports is not None else dataset.as_dicts(dataset.generate())
        self.pairs = {p.signal_id: p for p in stats.compute_all(self.reports)}
        self._kb: dict[str, KnowledgeBase] = {}

    # ------------------------------------------------------------ signals
    def signals(self, only_flagged: bool = True) -> list[dict]:
        out = []
        for p in self.pairs.values():  # already ranked by PRR
            if only_flagged and not p.is_signal:
                continue
            inv = self.store.load_investigation(p.signal_id)
            out.append({**p.to_dict(), "investigation_status": inv["status"] if inv else "not_started"})
        return out

    def _pair(self, signal_id: str):
        if signal_id not in self.pairs:
            raise NotFound(f"unknown signal {signal_id}")
        return self.pairs[signal_id]

    def _state(self, signal_id: str) -> dict:
        st = self.store.load_investigation(signal_id)
        if not st:
            raise NotFound("investigation not started")
        return st

    # ------------------------------------------------------- extraction
    def _extract(self, report: dict) -> dict:
        key = cache_key(self.llm.model_id, prompts.EXTRACT_PROMPT_VERSION, report["narrative"])
        raw = self.store.cache_get(key)
        from_cache = raw is not None
        error = None
        if raw is None:
            try:
                raw = self.llm.structured(prompts.EXTRACT_SYSTEM, f"CASE NARRATIVE:\n{report['narrative']}",
                                          "record_facts", prompts.EXTRACT_SCHEMA, max_tokens=1200)
            except Exception as e:  # fail loudly per case (Req 11.2)
                error = f"llm_error: {type(e).__name__}: {e}"[:300]
        ext, dropped = None, []
        if error is None:
            clean, dropped = guardrails.sanitize_lists(raw)
            ext, error = guardrails.validate_schema(clean)
            if ext is not None and not from_cache:
                self.store.cache_put(key, "extraction", raw)  # only schema-valid output is cached
        result = {"cache_key": key, "from_cache": from_cache, "error": error}
        if ext is None:
            # schema_valid is False for rejected output, None when no output arrived (LLM error)
            schema_valid = False if error and error.startswith("schema") else None
            result.update(facts=None, guardrail={"schema_valid": schema_valid,
                                                 "quotes_verified": 0, "quotes_rejected": 0})
        else:
            result.update(guardrails.verify_extraction(ext, report["narrative"]))
            result["guardrail"]["malformed_items_dropped"] = len(dropped)
            result["guardrail"]["quotes_rejected"] += len(dropped)
            result["facts"]["malformed_items"] = dropped
        return result

    def investigate(self, signal_id: str, actor: str = "analyst") -> dict:
        pair = self._pair(signal_id)
        previous = self.store.load_investigation(signal_id) or {}
        if previous.get("status") == "completed":
            raise Invalid("investigation is signed off; re-running would discard the sign-off")
        prev_overrides = {c["report_id"]: c["override"] for c in previous.get("cases", []) if c.get("override")}
        reports = sorted((r for r in self.reports if r["drug"] == pair.drug and r["event"] == pair.event),
                         key=lambda r: r["report_id"])
        t0 = time.perf_counter()
        with ThreadPoolExecutor(8) as pool:  # concurrent extraction (Req 3.5)
            results = list(pool.map(self._extract, reports))
        ai_seconds = time.perf_counter() - t0

        cases = []
        for rep, res in zip(reports, results):
            self.store.audit("ai_extraction", SYSTEM, {
                "signal_id": signal_id, "report_id": rep["report_id"], "model_id": self.llm.model_id,
                "prompt_version": prompts.EXTRACT_PROMPT_VERSION, "cache_key": res["cache_key"],
                "from_cache": res["from_cache"], "error": res["error"], "guardrail": res["guardrail"]})
            if res["facts"] is None:
                rule = {"category": "Unassessable", "rule_id": "CAU-00", "ruleset": rules.CAUSALITY_RULESET,
                        "version": rules.CAUSALITY_VERSION,
                        "explanation": f"Extraction failed and nothing was accepted ({res['error']}). Human review required."}
            else:
                rule = rules.assess_causality(res["facts"])
            self.store.audit("rule_evaluation", SYSTEM, {"signal_id": signal_id, "report_id": rep["report_id"], **rule})
            override = prev_overrides.get(rep["report_id"])
            cases.append({**rep, **{k: res[k] for k in ("facts", "guardrail", "error", "from_cache", "cache_key")},
                          "rule": rule, "override": override,
                          "effective_category": override["category"] if override else rule["category"]})

        state = {
            "signal_id": signal_id, "stats": pair.to_dict(), "cases": cases, "status": "in_review",
            "summary": None, "signoff": None,
            "versions": {"model_id": self.llm.model_id, "extract_prompt": prompts.EXTRACT_PROMPT_VERSION,
                         "causality_rules": f"{rules.CAUSALITY_RULESET} v{rules.CAUSALITY_VERSION}",
                         "recommendation_rules": f"{rules.RECOMMENDATION_RULESET} v{rules.RECOMMENDATION_VERSION}"},
            "metrics": self._metrics(cases, ai_seconds),
        }
        self._recommend(state)
        self.store.save_investigation(signal_id, state)
        self._kb.pop(signal_id, None)
        return state

    def _metrics(self, cases: list[dict], ai_seconds: float) -> dict:
        g = [c["guardrail"] for c in cases]
        return {
            "cases_processed": len(cases),
            "ai_seconds": round(ai_seconds, 2),
            "llm_calls": sum(1 for c in cases if not c["from_cache"]),
            "cache_hits": sum(1 for c in cases if c["from_cache"]),
            "extraction_failures": sum(1 for c in cases if c["facts"] is None),
            "facts_extracted": sum(x["quotes_verified"] for x in g),
            "quotes_verified": sum(x["quotes_verified"] for x in g),
            "quotes_rejected": sum(x["quotes_rejected"] for x in g),
            "minutes_per_case_assumption": MINUTES_PER_CASE,
            "manual_minutes_saved_estimate": len(cases) * MINUTES_PER_CASE,
        }

    def _recommend(self, state: dict) -> None:
        rec = rules.recommend(state["stats"], [c["effective_category"] for c in state["cases"]])
        state["recommendation"] = rec
        self.store.audit("rule_evaluation", SYSTEM, {"signal_id": state["signal_id"], "scope": "signal", **rec})

    def get(self, signal_id: str) -> dict:
        return self._state(signal_id)

    # ---------------------------------------------------- human in the loop
    def override(self, signal_id: str, report_id: str, category: str, reason: str, actor: str) -> dict:
        st = self._state(signal_id)
        if st["status"] == "completed":
            raise Invalid("investigation is signed off; no further changes")
        if category not in rules.CATEGORIES:
            raise Invalid(f"category must be one of {rules.CATEGORIES}")
        if not reason or not reason.strip():
            raise Invalid("an override requires a reason")
        if not actor or not actor.strip():
            raise Invalid("reviewer name is required")
        case = next((c for c in st["cases"] if c["report_id"] == report_id), None)
        if case is None:
            raise NotFound(f"case {report_id} not in this signal")
        before = case["effective_category"]
        case["override"] = {"category": category, "reason": reason.strip(), "actor": actor.strip()}
        case["effective_category"] = category
        self.store.audit("human_override", actor.strip(), {"signal_id": signal_id, "report_id": report_id,
                                                           "from": before, "to": category, "reason": reason.strip(),
                                                           "rule_category": case["rule"]["category"]})
        self._recommend(st)  # recompute immediately (Req 6.2)
        self.store.save_investigation(signal_id, st)
        self._kb.pop(signal_id, None)
        return st

    def clear_override(self, signal_id: str, report_id: str, actor: str) -> dict:
        st = self._state(signal_id)
        if st["status"] == "completed":
            raise Invalid("investigation is signed off; no further changes")
        case = next((c for c in st["cases"] if c["report_id"] == report_id), None)
        if case is None:
            raise NotFound(report_id)
        case["override"] = None
        case["effective_category"] = case["rule"]["category"]
        self.store.audit("human_override_cleared", actor or "reviewer", {"signal_id": signal_id, "report_id": report_id})
        self._recommend(st)
        self.store.save_investigation(signal_id, st)
        self._kb.pop(signal_id, None)
        return st

    def draft_summary(self, signal_id: str) -> dict:
        st = self._state(signal_id)
        data = {
            "signal": {k: st["stats"][k] for k in ("drug", "event", "a", "prr", "ror", "ror_lo", "ror_hi", "chi2", "is_signal")},
            "recommendation": {k: st["recommendation"][k] for k in ("recommendation", "rule_id", "inputs")},
            "cases": [{
                "id": c["report_id"], "age": c["age"], "sex": c["sex"], "causality": c["effective_category"],
                "human_override": bool(c["override"]),
                "onset_days": c["facts"]["time_to_onset"]["value"] if c["facts"] else None,
                "dechallenge": c["facts"]["dechallenge"]["value"] if c["facts"] else "extraction_failed",
                "rechallenge": c["facts"]["rechallenge"]["value"] if c["facts"] else "extraction_failed",
                "alternative_causes": [a["cause"] for a in c["facts"]["alternative_causes"]] if c["facts"] else [],
            } for c in st["cases"]],
        }
        out = self.llm.structured(prompts.SUMMARY_SYSTEM, "DATA:\n" + json.dumps(data), "draft_summary",
                                  prompts.SUMMARY_SCHEMA, max_tokens=900)
        text = str(out.get("summary", "")).strip()
        check = guardrails.check_summary_citations(text, {c["report_id"] for c in st["cases"]})
        st["summary"] = {"text": text, "citations": check, "label": "AI draft – requires human approval",
                         "model_id": self.llm.model_id, "prompt_version": prompts.SUMMARY_PROMPT_VERSION,
                         "edited": False}
        self.store.audit("ai_summary", SYSTEM, {"signal_id": signal_id, "model_id": self.llm.model_id,
                                                "prompt_version": prompts.SUMMARY_PROMPT_VERSION,
                                                "summary_sha256": sha256(text), "citations": check})
        self.store.save_investigation(signal_id, st)
        return st

    def signoff(self, signal_id: str, actor: str, decision: str, summary_text: str,
                reason: str = "", final_recommendation: str = "") -> dict:
        st = self._state(signal_id)
        if st["status"] == "completed":
            raise Invalid("already signed off")
        if not actor or not actor.strip():
            raise Invalid("reviewer name is required for sign-off")
        if decision not in ("accept", "override"):
            raise Invalid("decision must be 'accept' or 'override'")
        if decision == "override" and (not reason.strip() or not final_recommendation.strip()):
            raise Invalid("overriding the recommendation requires a final recommendation and a reason")
        final = st["recommendation"]["recommendation"] if decision == "accept" else final_recommendation.strip()
        text = (summary_text or "").strip()
        if st["summary"] is not None:
            st["summary"]["edited"] = text != st["summary"]["text"]
            st["summary"]["final_text"] = text
        st["signoff"] = {"actor": actor.strip(), "decision": decision, "final_recommendation": final,
                         "reason": reason.strip(), "rule_recommendation": st["recommendation"]["recommendation"],
                         "summary_sha256": sha256(text)}
        st["status"] = "completed"
        ev = self.store.audit("human_signoff", actor.strip(), {"signal_id": signal_id, **st["signoff"]})
        st["signoff"]["ts"] = ev["ts"]
        st["signoff"]["audit_hash"] = ev["hash"]
        self.store.save_investigation(signal_id, st)
        return st

    # ------------------------------------------------------------ chatbot
    def _kb_for(self, signal_id: str) -> KnowledgeBase:
        if signal_id not in self._kb:
            st = self._state(signal_id)
            self._kb[signal_id] = KnowledgeBase(signal_id, st["cases"], self.llm, self.store)
        return self._kb[signal_id]

    def chat(self, signal_id: str, question: str, actor: str = "reviewer") -> dict:
        question = (question or "").strip()
        if not question:
            raise Invalid("question is required")
        st = self._state(signal_id)
        kb = self._kb_for(signal_id)
        ret = kb.retrieve(question)
        result = {"question": question, "retrieval": {"cases": ret["cases"], "best_score": ret["best_score"],
                                                      "chunk_ids": [c["chunk_id"] for c in ret["chunks"]]},
                  "model_id": self.llm.model_id, "prompt_version": prompts.CHAT_PROMPT_VERSION,
                  "label": "Assistant – read-only, not a decision-maker"}
        if not ret["relevant"]:
            result.update(answer="I could not find supporting evidence for that in this signal's cases.",
                          no_evidence=True, citations=[], rejected_citations=[], grounding="no_evidence")
        else:
            rec = st["recommendation"]
            context = [f"SIGNAL: {st['stats']['drug']} + {st['stats']['event']}; cases={st['stats']['a']}; "
                       f"PRR={st['stats']['prr']}; rule-computed recommendation (read-only): {rec['recommendation']}; "
                       f"causality distribution: {json.dumps(rec['inputs']['distribution'])}"]
            context += ["CASE SUMMARY (orientation only, do not quote) " + kb.summaries[rid] for rid in ret["cases"]]
            context += ["NARRATIVE EVIDENCE (quote only from these lines):"]
            context += [f"[{c['case_id']}] {c['text']}" for c in ret["chunks"]]
            out = self.llm.structured(prompts.CHAT_SYSTEM, "CONTEXT:\n" + "\n".join(context) + f"\n\nQUESTION: {question}",
                                      "answer", prompts.CHAT_SCHEMA, max_tokens=800)
            ok, bad = guardrails.verify_citations(list(out.get("citations") or []), kb.narratives)
            no_ev = bool(out.get("no_evidence"))
            grounding = "no_evidence" if no_ev else ("grounded" if ok else "unsupported")
            result.update(answer=str(out.get("answer", "")), no_evidence=no_ev, citations=ok,
                          rejected_citations=bad, grounding=grounding)
        self.store.audit("chat_exchange", actor, {
            "signal_id": signal_id, "question": question, "retrieved_chunk_ids": result["retrieval"]["chunk_ids"],
            "model_id": self.llm.model_id, "prompt_version": prompts.CHAT_PROMPT_VERSION,
            "answer": result["answer"], "citations": result["citations"],
            "rejected_citations": result["rejected_citations"], "grounding": result["grounding"]})
        return result

    def kb_stats(self, signal_id: str) -> dict:
        return self._kb_for(signal_id).stats()
