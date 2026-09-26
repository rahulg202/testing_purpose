"""Deterministic disproportionality statistics (Requirement 2). Pure functions, no AI."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass

EVANS = {"prr_min": 2.0, "chi2_min": 4.0, "a_min": 3}


@dataclass(frozen=True)
class PairStats:
    signal_id: str
    drug: str
    event: str
    a: int  # drug & event
    b: int  # drug & other events
    c: int  # other drugs & event
    d: int  # other drugs & other events
    prr: float
    ror: float
    ror_lo: float
    ror_hi: float
    chi2: float
    is_signal: bool

    def to_dict(self) -> dict:
        return asdict(self)


def signal_id(drug: str, event: str) -> str:
    return f"{drug}__{event}"


def compute_pair(drug: str, event: str, a: int, b: int, c: int, d: int) -> PairStats:
    # Haldane-Anscombe 0.5 correction only when a zero cell would break the ratios
    aa, bb, cc, dd = (a, b, c, d) if min(a, b, c, d) > 0 else (a + 0.5, b + 0.5, c + 0.5, d + 0.5)
    prr = (aa / (aa + bb)) / (cc / (cc + dd))
    ror = (aa * dd) / (bb * cc)
    se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    ror_lo, ror_hi = math.exp(math.log(ror) - 1.96 * se), math.exp(math.log(ror) + 1.96 * se)
    # Pearson chi-square with Yates continuity correction (as used with Evans criteria)
    n = a + b + c + d
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    chi2 = 0.0 if denom == 0 else n * max(0.0, abs(a * d - b * c) - n / 2) ** 2 / denom
    is_signal = prr >= EVANS["prr_min"] and chi2 >= EVANS["chi2_min"] and a >= EVANS["a_min"]
    r = lambda x: round(x, 4)  # noqa: E731
    return PairStats(signal_id(drug, event), drug, event, a, b, c, d,
                     r(prr), r(ror), r(ror_lo), r(ror_hi), r(chi2), is_signal)


def compute_all(reports: list[dict]) -> list[PairStats]:
    """Every drug-event pair with >=1 report, sorted by PRR desc (ties by id)."""
    n = len(reports)
    pair = Counter((r["drug"], r["event"]) for r in reports)
    drug_n = Counter(r["drug"] for r in reports)
    event_n = Counter(r["event"] for r in reports)
    out = []
    for (drug, event), a in pair.items():
        b = drug_n[drug] - a
        c = event_n[event] - a
        d = n - a - b - c
        out.append(compute_pair(drug, event, a, b, c, d))
    return sorted(out, key=lambda s: (-s.prr, s.signal_id))
