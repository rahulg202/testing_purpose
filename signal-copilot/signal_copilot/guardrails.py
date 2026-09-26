"""Level 2 system guardrails (Requirement 4, 7.2, 12.6).

Deterministic, non-LLM code. The model cannot argue its way past these checks.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------- schemas ---

Temporal = Literal["plausible", "implausible", "unknown"]
Challenge = Literal["positive", "negative", "not_done", "unknown"]


class QuotedValue(BaseModel):
    value: str
    quote: str | None = None


class AltCause(BaseModel):
    cause: str
    quote: str


class Onset(BaseModel):
    days: int | None = None
    quote: str | None = None


class TemporalFact(BaseModel):
    value: Temporal
    quote: str | None = None


class ChallengeFact(BaseModel):
    value: Challenge
    quote: str | None = None


class Extraction(BaseModel):
    """The forced output schema. Anything that doesn't conform is rejected."""

    time_to_onset: Onset
    temporal_relationship: TemporalFact
    dechallenge: ChallengeFact
    rechallenge: ChallengeFact
    alternative_causes: list[AltCause] = Field(default_factory=list)
    excluded_causes: list[AltCause] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


def _valid_item(x: object) -> bool:
    return isinstance(x, dict) and isinstance(x.get("cause"), str) and x["cause"].strip() != "" \
        and isinstance(x.get("quote"), str) and x["quote"].strip() != ""


def sanitize_lists(raw: object) -> tuple[object, list[dict]]:
    """Drop malformed cause items individually (e.g. {"cause": null}) instead of failing the whole case.

    Dropped items are returned so they are counted as rejected claims, never silently lost.
    Top-level fields are NOT repaired: they still go through strict validation.
    """
    if not isinstance(raw, dict):
        return raw, []
    raw = dict(raw)
    dropped: list[dict] = []
    for key in ("alternative_causes", "excluded_causes"):
        items = raw.get(key)
        if items is None:
            raw[key] = []
        elif isinstance(items, list):
            raw[key] = [x for x in items if _valid_item(x)]
            dropped += [{"field": key, "item": x} for x in items if not _valid_item(x)]
    if isinstance(raw.get("data_gaps"), list):
        raw["data_gaps"] = [x for x in raw["data_gaps"] if isinstance(x, str) and x.strip()]
    return raw, dropped


def validate_schema(raw: object) -> tuple[Extraction | None, str | None]:
    try:
        return Extraction.model_validate(raw), None
    except ValidationError as e:
        return None, f"schema_invalid: {e.error_count()} error(s): " + "; ".join(
            f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:5])


# ------------------------------------------------------ quote verification ---

_QUOTE_CHARS = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def _normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Lower-case, unify quotes, collapse whitespace. Returns index map norm->orig."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text.translate(_QUOTE_CHARS)):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def locate_quote(quote: str | None, source: str) -> tuple[int, int] | None:
    """Return (start, end) char offsets of quote in source, or None if not present.

    source[start:end] is the exact original text the quote matched.
    """
    if not quote:
        return None
    q, _ = _normalise_with_map(quote.strip().strip('"').strip())
    if len(q) < 3:
        return None
    s, idx = _normalise_with_map(source)
    pos = s.find(q)
    if pos < 0:
        return None
    return idx[pos], idx[pos + len(q) - 1] + 1


_NEGATION = re.compile(r"\b(negative|denied|denies|no|not|none|without|unremarkable|ruled out|excluded|absent)\b", re.I)


def is_negated(quote: str) -> bool:
    """Deterministic check: the evidence describes a cause being ruled out, not present."""
    return bool(_NEGATION.search(quote))


# ------------------------------------------------------- apply to extraction ---

def verify_extraction(ext: Extraction, narrative: str) -> dict:
    """Verify every quote. Failed quote => fact downgraded to unknown + unverified."""
    facts: dict = {}
    verified = rejected = 0

    def single(name: str, value, quote: str | None, unknown_value) -> None:
        nonlocal verified, rejected
        is_unknown = value in (None, "unknown")
        if is_unknown:
            facts[name] = {"value": unknown_value, "status": "unknown", "quote": None, "span": None}
            return
        span = locate_quote(quote, narrative)
        if span:
            verified += 1
            facts[name] = {"value": value, "status": "verified", "quote": narrative[span[0]:span[1]], "span": list(span)}
        else:
            rejected += 1
            facts[name] = {"value": unknown_value, "status": "unverified", "quote": None, "span": None,
                           "rejected_value": value, "rejected_quote": quote}

    single("time_to_onset", ext.time_to_onset.days, ext.time_to_onset.quote, None)
    single("temporal_relationship", ext.temporal_relationship.value, ext.temporal_relationship.quote, "unknown")
    single("dechallenge", ext.dechallenge.value, ext.dechallenge.quote, "unknown")
    single("rechallenge", ext.rechallenge.value, ext.rechallenge.quote, "unknown")

    alts, rejected_alts, excluded = [], [], []
    for alt, is_excluded in [(a, False) for a in ext.alternative_causes] + [(a, True) for a in ext.excluded_causes]:
        span = locate_quote(alt.quote, narrative)
        if not span:
            rejected += 1
            rejected_alts.append({"cause": alt.cause, "status": "unverified", "rejected_quote": alt.quote})
            continue
        verified += 1
        item = {"cause": alt.cause, "status": "verified", "quote": narrative[span[0]:span[1]], "span": list(span)}
        if is_excluded:
            excluded.append(item)
        elif is_negated(item["quote"]):
            # System guardrail: model filed a ruled-out finding as an alternative cause
            excluded.append({**item, "reclassified_by": "negation_guardrail"})
        else:
            alts.append(item)
    facts["alternative_causes"] = alts
    facts["excluded_causes"] = excluded
    facts["rejected_alternative_causes"] = rejected_alts
    facts["data_gaps"] = list(ext.data_gaps)
    return {"facts": facts, "guardrail": {"schema_valid": True, "quotes_verified": verified, "quotes_rejected": rejected}}


# ------------------------------------------------------- citation checks ---

CASE_ID_RE = re.compile(r"R-\d{5}")


def check_summary_citations(text: str, valid_ids: set[str]) -> dict:
    cited = sorted(set(CASE_ID_RE.findall(text)))
    return {"cited": cited, "valid": [c for c in cited if c in valid_ids],
            "invalid": [c for c in cited if c not in valid_ids]}


def verify_citations(citations: list[dict], narratives: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Chatbot citations: the case must be in THIS signal's KB and the quote must be in it."""
    ok, bad = [], []
    for c in citations:
        cid, quote = str(c.get("case_id", "")), c.get("quote")
        if cid not in narratives:
            bad.append({**c, "reason": "case not in this signal's knowledge base"})
            continue
        span = locate_quote(quote, narratives[cid])
        if span:
            ok.append({"case_id": cid, "quote": narratives[cid][span[0]:span[1]], "span": list(span)})
        else:
            bad.append({**c, "reason": "quote not found in source narrative"})
    return ok, bad
