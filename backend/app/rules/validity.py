"""Validity rule interpreter — the ICSR minimum-criteria decision (val_001).

A valid ICSR requires four minimum criteria to be present (ICH E2D / GVP
Module VI):

    1. An identifiable patient
    2. An identifiable reporter
    3. A suspect medicinal product
    4. An adverse event

This module owns that decision. It is a pure function over the four extracted
flags: no I/O, no model calls, no randomness. Same inputs plus same
``RULE_SET_VERSION`` always yield the same outcome, which is what makes
decisions replayable years later during an inspection.

The AI never calls this outcome. It only reports what the source says; this
rule decides. That boundary is the point.
"""

from __future__ import annotations

from dataclasses import dataclass

from atheria_contracts.canonical_case import RuleEvaluation
from atheria_contracts.enums import ICSROutcome
from atheria_contracts.source_record import ICSRElements

# ---------------------------------------------------------------------------
# Rule set identity. Bump RULE_SET_VERSION whenever the logic below changes so
# historical decisions remain attributable to the exact rules that made them.
# ---------------------------------------------------------------------------
RULE_ID = "val_001"
RULE_SET_VERSION = "1.0.0"

#: The four minimum criteria, in reporting order.
CRITERIA: tuple[str, ...] = (
    "identifiable_patient",
    "identifiable_reporter",
    "suspect_product",
    "adverse_event",
)

#: Without these two there is no safety signal at all, so the record cannot
#: even be a *potential* ICSR.
CORE_CRITERIA: tuple[str, ...] = ("suspect_product", "adverse_event")

_QUOTE_LIMIT = 80


@dataclass(frozen=True)
class ValidityDecision:
    """Outcome of the validity rule plus its full decision trace."""

    outcome: ICSROutcome
    trace: RuleEvaluation

    @property
    def is_valid_icsr(self) -> bool:
        """True only for a complete, valid ICSR."""
        return self.outcome is ICSROutcome.VALID_ICSR

    @property
    def requires_human_review(self) -> bool:
        """True when we deliberately escalated instead of guessing."""
        return self.outcome is ICSROutcome.POTENTIAL_ICSR


def _present_map(elements: ICSRElements) -> dict[str, bool]:
    """Flatten the four criteria into ``{criterion: present}``."""
    return {name: bool(getattr(elements, name).present) for name in CRITERIA}


def _input_provenance(elements: ICSRElements) -> dict[str, str]:
    """Summarise the basis for each criterion.

    Answers "why did we believe this element was present?" in a form a reviewer
    can read directly in the UI.
    """
    provenance: dict[str, str] = {}
    for name in CRITERIA:
        element = getattr(elements, name)
        span = element.evidence_span
        if element.present and span is not None and span.quote:
            quote = span.quote
            if len(quote) > _QUOTE_LIMIT:
                quote = quote[: _QUOTE_LIMIT - 3] + "..."
            provenance[name] = f"present — evidence: '{quote}'"
        elif element.present:
            provenance[name] = "present — asserted without an evidence span"
        else:
            provenance[name] = "ABSENT — not found in the source text"
    return provenance


def _humanise(names: list[str]) -> str:
    """Render criterion names for an explanation sentence."""
    pretty = [name.replace("_", " ") for name in names]
    if len(pretty) == 1:
        return pretty[0]
    return ", ".join(pretty[:-1]) + f" and {pretty[-1]}"


def evaluate_validity(elements: ICSRElements) -> ValidityDecision:
    """Decide whether the four ICSR criteria amount to a valid ICSR.

    Decision table (val_001 v1.0.0):

    ==========================================  ==================
    Condition                                   Outcome
    ==========================================  ==================
    All four criteria present                   ``VALID_ICSR``
    Suspect product or adverse event absent     ``NON_ICSR``
    Product + event present, patient or
    reporter absent                             ``POTENTIAL_ICSR``
    ==========================================  ==================

    The third branch is the "we do not guess" path: a genuine safety signal
    exists but the record is incomplete, so it is escalated for follow-up
    rather than being asserted valid or silently discarded.
    """
    present = _present_map(elements)
    missing = [name for name in CRITERIA if not present[name]]
    missing_core = [name for name in CORE_CRITERIA if not present[name]]
    fired: list[str] = []

    if not missing:
        outcome = ICSROutcome.VALID_ICSR
        fired.append("val_001_all_criteria_present")
        explanation = (
            f"VALID ICSR. Rule {RULE_ID} v{RULE_SET_VERSION}. All four minimum "
            "criteria are present: identifiable patient, identifiable reporter, "
            "suspect product, and adverse event."
        )
    elif missing_core:
        outcome = ICSROutcome.NON_ICSR
        fired.append("val_001_missing_core_element")
        explanation = (
            f"NON-ICSR. Rule {RULE_ID} v{RULE_SET_VERSION}. Missing core "
            f"element(s): {_humanise(missing_core)}. Without both a suspect "
            "product and an adverse event there is no reportable safety signal."
        )
    else:
        outcome = ICSROutcome.POTENTIAL_ICSR
        fired.append("val_001_incomplete_escalate")
        explanation = (
            f"POTENTIAL ICSR. Rule {RULE_ID} v{RULE_SET_VERSION}. A suspect "
            "product and an adverse event are both present, but "
            f"{_humanise(missing)} could not be established from the source. "
            "We do not guess — escalating for human review and follow-up rather "
            "than asserting or discarding validity."
        )

    trace = RuleEvaluation(
        rule_id=RULE_ID,
        rule_set_version=RULE_SET_VERSION,
        inputs=dict(present),
        input_provenance=_input_provenance(elements),
        fired_rules=fired,
        explanation=explanation,
        outcome=outcome.value,
    )
    return ValidityDecision(outcome=outcome, trace=trace)
