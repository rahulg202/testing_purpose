"""Property-based + unit tests for the deterministic core (no network)."""

from __future__ import annotations

import hashlib
import json
import math

import pytest
from hypothesis import given, settings, strategies as st

from signal_copilot import dataset, guardrails, rules, stats
from signal_copilot.service import Copilot, Invalid
from signal_copilot.store import Store


class FakeLLM:
    """Deterministic stand-in. Quotes real text, plus one invented quote to exercise the guardrail."""

    model_id = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def structured(self, system, user, tool, schema, max_tokens=1500):
        self.calls += 1
        if tool == "record_facts":
            text = user.split("\n", 1)[1]
            first = text.split(".")[0]
            return {"time_to_onset": {"days": None}, "temporal_relationship": {"value": "plausible", "quote": first},
                    "dechallenge": {"value": "positive", "quote": "this sentence was never in the narrative"},
                    "rechallenge": {"value": "unknown"}, "alternative_causes": [], "data_gaps": ["dose"]}
        if tool == "draft_summary":
            return {"summary": "Cases R-00001 and R-99999 were reviewed."}
        return {"answer": "x", "no_evidence": False, "citations": [{"case_id": "R-99999", "quote": "nope"}]}

    def embed(self, text):
        h = hashlib.sha256(text.encode()).digest()
        v = [b - 127.5 for b in h] * 16
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v]


# ------------------------------------------------------------- dataset
def test_dataset_reproducible_and_has_planted_signals():
    a, b = dataset.as_dicts(dataset.generate()), dataset.as_dicts(dataset.generate())
    assert a == b and len(a) >= 1000
    flagged = {p.signal_id for p in stats.compute_all(a) if p.is_signal}
    assert {"Hepatrix__Hepatotoxicity", "Dormyl__Pancreatitis"} <= flagged
    assert {f"{d}__{e}" for d, e, _, _ in dataset.EXTRA_SIGNALS} <= flagged
    assert len(flagged) >= 7


# --------------------------------------------------------------- stats
cells = st.integers(min_value=0, max_value=500)


@given(cells, cells, cells, cells)
def test_stats_pure_and_formula(a, b, c, d):
    s1, s2 = stats.compute_pair("X", "Y", a, b, c, d), stats.compute_pair("X", "Y", a, b, c, d)
    assert s1 == s2
    if min(a, b, c, d) > 0:
        assert s1.prr == pytest.approx((a / (a + b)) / (c / (c + d)), rel=1e-3, abs=1e-3)
        assert s1.ror == pytest.approx(a * d / (b * c), rel=1e-3, abs=1e-3)
        assert s1.ror_lo <= s1.ror <= s1.ror_hi + 1e-3
    assert s1.is_signal == (s1.prr >= 2 and s1.chi2 >= 4 and a >= 3)


# ---------------------------------------------------------- guardrails
@given(st.text(min_size=5, max_size=200), st.data())
@settings(max_examples=200)
def test_located_quote_maps_back_to_source(text, data):
    i = data.draw(st.integers(0, len(text) - 1))
    j = data.draw(st.integers(i + 1, len(text)))
    span = guardrails.locate_quote(text[i:j], text)
    if span:  # a verified quote always maps to a region that normalises to the quote
        n = lambda s: " ".join(s.lower().split())  # noqa: E731
        assert n(text[span[0]:span[1]]) == n(text[i:j].strip().strip('"').strip())


@given(st.text(alphabet="abcdefgh ", min_size=1, max_size=60))
def test_invented_quote_is_never_verified(narr):
    assert guardrails.locate_quote("zzzq invented", narr) is None


def test_failed_quote_downgrades_to_unknown():
    ext = guardrails.Extraction.model_validate({
        "time_to_onset": {"days": 5, "quote": "made up"}, "temporal_relationship": {"value": "plausible", "quote": "took  the DRUG"},
        "dechallenge": {"value": "positive", "quote": "made up"}, "rechallenge": {"value": "unknown"},
        "alternative_causes": [{"cause": "alcohol", "quote": "not there"}]})
    out = guardrails.verify_extraction(ext, "She took the drug and felt ill.")
    f = out["facts"]
    assert f["temporal_relationship"]["status"] == "verified"
    assert f["dechallenge"] == {**f["dechallenge"], "value": "unknown", "status": "unverified"}
    assert f["time_to_onset"]["value"] is None and f["alternative_causes"] == []
    assert out["guardrail"] == {"schema_valid": True, "quotes_verified": 1, "quotes_rejected": 3}


def test_schema_invalid_is_rejected():
    ext, err = guardrails.validate_schema({"temporal_relationship": {"value": "definitely caused it"}})
    assert ext is None and err.startswith("schema_invalid")


# --------------------------------------------------------------- rules
fact_combo = st.fixed_dictionaries({
    "temporal_relationship": st.fixed_dictionaries({"value": st.sampled_from(["plausible", "implausible", "unknown"])}),
    "dechallenge": st.fixed_dictionaries({"value": st.sampled_from(["positive", "negative", "not_done", "unknown"])}),
    "rechallenge": st.fixed_dictionaries({"value": st.sampled_from(["positive", "negative", "not_done", "unknown"])}),
    "alternative_causes": st.lists(st.just({"cause": "x"}), max_size=3)})


@given(fact_combo)
def test_causality_total_and_deterministic(f):
    r1, r2 = rules.assess_causality(f), rules.assess_causality(f)
    assert r1 == r2 and r1["category"] in rules.CATEGORIES and r1["rule_id"].startswith("CAU-")


@given(st.lists(st.sampled_from(rules.CATEGORIES), max_size=40), st.booleans())
def test_recommendation_deterministic(cats, sig):
    assert rules.recommend({"is_signal": sig}, cats) == rules.recommend({"is_signal": sig}, list(cats))


# ------------------------------------------------------------ audit
def test_audit_chain_detects_tampering():
    s = Store()
    for i in range(5):
        s.audit("x", "a", {"i": i})
    assert s.verify_chain()["valid"]
    s._db.execute("UPDATE audit SET payload=? WHERE seq=3", (json.dumps({"i": 99}),))
    assert s.verify_chain() == {"valid": False, "events": 5, "broken_at_seq": 3}


# ------------------------------------------------------ end-to-end (fake LLM)
@pytest.fixture
def cp():
    return Copilot(FakeLLM(), Store())


def test_replay_uses_cache_and_is_identical(cp):
    sid = "Hepatrix__Hepatotoxicity"
    s1 = cp.investigate(sid)
    calls = cp.llm.calls
    s2 = cp.investigate(sid)
    assert cp.llm.calls == calls and s2["metrics"]["llm_calls"] == 0
    assert [c["facts"] for c in s1["cases"]] == [c["facts"] for c in s2["cases"]]
    assert s1["metrics"]["quotes_rejected"] == len(s1["cases"])  # the invented quote was caught every time


def test_override_requires_reason_and_recomputes(cp):
    sid = "Dormyl__Pancreatitis"
    st_ = cp.investigate(sid)
    rid = st_["cases"][0]["report_id"]
    with pytest.raises(Invalid):
        cp.override(sid, rid, "Certain", "  ", "Dr A")
    for c in st_["cases"]:
        st_ = cp.override(sid, c["report_id"], "Unlikely", "confounded by alcohol", "Dr A")
    assert st_["recommendation"]["rule_id"] == "REC-03"


def test_signoff_required_and_summary_citations_checked(cp):
    sid = "Hepatrix__Hepatotoxicity"
    cp.investigate(sid)
    st_ = cp.draft_summary(sid)
    assert "R-99999" in st_["summary"]["citations"]["invalid"]
    assert st_["status"] == "in_review"
    with pytest.raises(Invalid):
        cp.signoff(sid, "", "accept", "text")
    with pytest.raises(Invalid):
        cp.signoff(sid, "Dr A", "override", "text")
    assert cp.signoff(sid, "Dr A", "accept", "final text")["status"] == "completed"
    with pytest.raises(Invalid):
        cp.investigate(sid)  # a signed-off investigation cannot be silently reset
    assert cp.store.verify_chain()["valid"]


def test_chat_strips_citations_outside_signal(cp):
    sid = "Hepatrix__Hepatotoxicity"
    cp.investigate(sid)
    import signal_copilot.rag as rag
    rag.MIN_RELEVANCE = -1.0  # force the LLM path with the fake embedder
    r = cp.chat(sid, "what happened?")
    assert r["citations"] == [] and r["rejected_citations"] and r["grounding"] == "unsupported"


def test_negated_alternative_cause_is_reclassified():
    ext = guardrails.Extraction.model_validate({
        "time_to_onset": {"days": None}, "temporal_relationship": {"value": "unknown"},
        "dechallenge": {"value": "unknown"}, "rechallenge": {"value": "unknown"},
        "alternative_causes": [{"cause": "alcohol", "quote": "the patient denied alcohol use"},
                               {"cause": "gallstones", "quote": "revealed multiple gallstones"}]})
    f = guardrails.verify_extraction(ext, "Tests done; the patient denied alcohol use. CT revealed multiple gallstones.")["facts"]
    assert [a["cause"] for a in f["alternative_causes"]] == ["gallstones"]
    assert f["excluded_causes"][0]["reclassified_by"] == "negation_guardrail"


def test_verified_onset_derives_plausible_timing():
    f = {"temporal_relationship": {"value": "unknown"}, "time_to_onset": {"value": 28, "status": "verified"},
         "dechallenge": {"value": "unknown"}, "rechallenge": {"value": "unknown"},
         "alternative_causes": [{"cause": "a"}, {"cause": "b"}]}
    assert rules.assess_causality(f)["rule_id"] == "CAU-03"
    f["time_to_onset"]["status"] = "unverified"
    assert rules.assess_causality(f)["rule_id"] == "CAU-02"


def test_malformed_list_items_dropped_not_whole_case():
    raw = {"time_to_onset": {"days": None}, "temporal_relationship": {"value": "unknown"},
           "dechallenge": {"value": "unknown"}, "rechallenge": {"value": "unknown"},
           "alternative_causes": [{"cause": None, "quote": None}], "excluded_causes": [{"cause": None}],
           "data_gaps": ["onset"]}
    clean, dropped = guardrails.sanitize_lists(raw)
    ext, err = guardrails.validate_schema(clean)
    assert err is None and ext.alternative_causes == [] and len(dropped) == 2
    # top-level fields are still strict
    bad, _ = guardrails.sanitize_lists({**raw, "dechallenge": {"value": "caused it"}})
    assert guardrails.validate_schema(bad)[0] is None
