"""Deterministic, versioned decision rules (Requirements 5, 6). No LLM involvement.

cau_001 is a simplified WHO-UMC-inspired rule set (Assumption A3), not a
validated clinical algorithm.
"""

from __future__ import annotations

from collections import Counter

CAUSALITY_RULESET = "cau_001"
CAUSALITY_VERSION = "1.1.0"  # 1.1.0: temporal derived from verified onset when not stated
RECOMMENDATION_RULESET = "rec_001"
RECOMMENDATION_VERSION = "1.0.0"

CATEGORIES = ["Certain", "Probable", "Possible", "Unlikely", "Unassessable"]

REC_THRESHOLDS = {
    "max_unassessable_share": 0.5,  # above this -> insufficient information
    "min_supportive_share": 0.5,    # Certain+Probable share of assessable cases -> validated
    "min_unlikely_share": 0.5,      # Unlikely share of assessable cases -> confounded
}


def assess_causality(facts: dict) -> dict:
    """Map verified facts to exactly one category. Total over all inputs."""
    temporal = facts.get("temporal_relationship", {}).get("value", "unknown")
    onset = facts.get("time_to_onset", {})
    derived = ""
    if temporal == "unknown" and onset.get("status") == "verified" and isinstance(onset.get("value"), int) and onset["value"] >= 0:
        # Deterministic derivation: a verified onset after drug start establishes a plausible time relationship
        temporal, derived = "plausible", f" (derived from verified onset of {onset['value']} days)"
    dech = facts.get("dechallenge", {}).get("value", "unknown")
    rech = facts.get("rechallenge", {}).get("value", "unknown")
    n_alt = len(facts.get("alternative_causes", []))
    basis = f"temporal={temporal}{derived}, dechallenge={dech}, rechallenge={rech}, verified alternative causes={n_alt}"

    if temporal == "implausible":
        rid, cat, why = "CAU-01", "Unlikely", "The time relationship to the drug is implausible."
    elif temporal == "unknown":
        rid, cat, why = "CAU-02", "Unassessable", "The time relationship could not be established from verified evidence; we do not guess."
    elif n_alt >= 2 and dech != "positive":
        rid, cat, why = "CAU-03", "Unlikely", "Two or more verified alternative causes and no positive dechallenge."
    elif n_alt >= 1:
        rid, cat, why = "CAU-04", "Possible", "Plausible timing, but a verified alternative cause could explain the event."
    elif dech == "positive" and rech == "positive":
        rid, cat, why = "CAU-05", "Certain", "Plausible timing, positive dechallenge and positive rechallenge, no alternative cause."
    elif dech == "positive":
        rid, cat, why = "CAU-06", "Probable", "Plausible timing and positive dechallenge, no alternative cause."
    else:
        rid, cat, why = "CAU-07", "Possible", "Plausible timing, no alternative cause, but dechallenge not positive or not reported."
    return {"category": cat, "rule_id": rid, "ruleset": CAUSALITY_RULESET, "version": CAUSALITY_VERSION,
            "explanation": f"{why} Facts: {basis}."}


def recommend(stats: dict, categories: list[str]) -> dict:
    """Signal-level recommendation from statistics + effective causality distribution."""
    dist = Counter(categories)
    n = len(categories)
    assessable = n - dist["Unassessable"]
    unassessable_share = dist["Unassessable"] / n if n else 1.0
    supportive = (dist["Certain"] + dist["Probable"]) / assessable if assessable else 0.0
    unlikely = dist["Unlikely"] / assessable if assessable else 0.0
    t = REC_THRESHOLDS
    if n == 0 or unassessable_share > t["max_unassessable_share"]:
        rid, rec = "REC-01", "Insufficient information – request follow-up"
    elif stats.get("is_signal") and supportive >= t["min_supportive_share"]:
        rid, rec = "REC-02", "Validated – escalate to Safety Review Committee"
    elif unlikely >= t["min_unlikely_share"]:
        rid, rec = "REC-03", "Not confirmed – confounded, continue monitoring"
    else:
        rid, rec = "REC-04", "Inconclusive – continue monitoring and request follow-up"
    return {
        "recommendation": rec, "rule_id": rid, "ruleset": RECOMMENDATION_RULESET,
        "version": RECOMMENDATION_VERSION, "thresholds": t,
        "inputs": {"n_cases": n, "distribution": {c: dist[c] for c in CATEGORIES},
                   "unassessable_share": round(unassessable_share, 3),
                   "supportive_share": round(supportive, 3), "unlikely_share": round(unlikely, 3),
                   "is_signal": bool(stats.get("is_signal")), "prr": stats.get("prr")},
    }
