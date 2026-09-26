"""Signal-scoped knowledge base + two-tier vector retrieval (Requirement 12).

Tier 1: one summary vector per case  -> pick the most relevant cases.
Tier 2: chunk vectors (narrative sentences, char offsets) within those cases.
Embeddings are cached by content hash, so rebuilding a KB is free and reproducible.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from . import EMBED_MODEL_ID
from .llm import LLM
from .store import Store, cache_key

TOP_CASES = 10
TOP_CHUNKS = 14
MIN_RELEVANCE = 0.1  # best semantic score below this => refuse without calling the LLM (Req 12.7)
LEXICAL_WEIGHT = 0.3  # hybrid score = (1-w)*cosine + w*keyword overlap

_SENT = re.compile(r"[^.;!?]+[.;!?]?")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an the of to in on for and or with was were is are did do does had has have what which who how when why "
            "cases case patient patients drug any after before this that these those there their it be by from".split())


def _terms(text: str) -> set[str]:
    return {w[:6] for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def lexical(q_terms: set[str], text: str) -> float:
    return len(q_terms & _terms(text)) / len(q_terms) if q_terms else 0.0


def sentence_chunks(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in _SENT.finditer(text):
        s, e = m.start(), m.end()
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e - s >= 3:
            spans.append((s, e))
    return spans


def case_summary_text(case: dict) -> str:
    f = case["facts"]
    alts = ", ".join(a["cause"] for a in f.get("alternative_causes", [])) or "none verified"
    onset = f["time_to_onset"]["value"]
    return (f"{case['report_id']}: {case['age']}{case['sex']}, {case['drug']}, {case['event']}, "
            f"{'serious' if case['serious'] else 'non-serious'}. Onset: {onset if onset is not None else 'unknown'} days. "
            f"Temporal: {f['temporal_relationship']['value']}. Dechallenge: {f['dechallenge']['value']}. "
            f"Rechallenge: {f['rechallenge']['value']}. Alternative causes: {alts}. "
            f"Causality: {case['effective_category']}.")


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalised by Titan


class KnowledgeBase:
    def __init__(self, signal_id: str, cases: list[dict], llm: LLM, store: Store) -> None:
        self.signal_id = signal_id
        self.llm, self.store = llm, store
        self.narratives = {c["report_id"]: c["narrative"] for c in cases if c.get("facts")}
        self.summaries = {c["report_id"]: case_summary_text(c) for c in cases if c.get("facts")}
        self.chunks = [{"chunk_id": f"{rid}#{i}", "case_id": rid, "span": [s, e], "text": text[s:e]}
                       for rid, text in self.narratives.items() for i, (s, e) in enumerate(sentence_chunks(text))]
        texts = list(self.summaries.values()) + [c["text"] for c in self.chunks]
        with ThreadPoolExecutor(8) as pool:
            vecs = list(pool.map(self._embed, texts))
        n = len(self.summaries)
        self.summary_vecs = dict(zip(self.summaries.keys(), vecs[:n]))
        for c, v in zip(self.chunks, vecs[n:]):
            c["vec"] = v

    def _embed(self, text: str) -> list[float]:
        key = cache_key(EMBED_MODEL_ID, "embed_512_norm", text)
        hit = self.store.cache_get(key)
        if hit is not None:
            return hit
        vec = self.llm.embed(text)
        self.store.cache_put(key, "embedding", vec)
        return vec

    def retrieve(self, question: str) -> dict:
        q = self._embed(question)
        qt = _terms(question)
        w = LEXICAL_WEIGHT

        def hybrid(vec: list[float], text: str) -> float:
            return (1 - w) * _dot(q, vec) + w * lexical(qt, text)

        # Tier 1: summary vectors pick the cases
        cases = sorted(self.summary_vecs, key=lambda rid: -hybrid(self.summary_vecs[rid], self.summaries[rid]))[:TOP_CASES]
        chosen = set(cases)
        # Tier 2: chunk vectors inside those cases pick the evidence
        scored = sorted(((hybrid(c["vec"], c["text"]), _dot(q, c["vec"]), c) for c in self.chunks if c["case_id"] in chosen),
                        key=lambda t: -t[0])
        top = [{**{k: v for k, v in c.items() if k != "vec"}, "score": round(s, 4)} for s, _, c in scored[:TOP_CHUNKS]]
        best_semantic = max((cos for _, cos, _ in scored), default=0.0)
        return {"cases": cases, "chunks": top, "best_score": round(best_semantic, 4),
                "relevant": best_semantic >= MIN_RELEVANCE}

    def stats(self) -> dict:
        return {"cases": len(self.summaries), "chunks": len(self.chunks), "summary_vectors": len(self.summary_vecs)}
