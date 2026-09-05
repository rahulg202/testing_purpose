"""Tests for the val_001 validity rule.

The rule is the regulatory decision point, so its behaviour is pinned down
exhaustively: all sixteen combinations of the four criteria, plus the shape and
content of the decision trace.
"""

from __future__ import annotations

import itertools

from atheria_contracts.enums import ICSROutcome
from atheria_contracts.provenance import EvidenceSpan, Locator
from atheria_contracts.source_record import ICSRElement, ICSRElements

from backend.app.rules.validity import (
    RULE_ID,
    RULE_SET_VERSION,
    evaluate_validity,
)


def build_elements(
    *,
    patient: bool,
    reporter: bool,
    product: bool,
    event: bool,
    with_evidence: bool = False,
) -> ICSRElements:
    def element(present: bool, label: str) -> ICSRElement:
        span = None
        if present and with_evidence:
            span = EvidenceSpan(
                source_record_id="src_1",
                evidence_ref="tenant/raw.txt",
                locator=Locator(char_start=0, char_end=10),
                quote=f"evidence for {label}",
            )
        return ICSRElement(present=present, evidence_span=span)

    return ICSRElements(
        identifiable_patient=element(patient, "patient"),
        identifiable_reporter=element(reporter, "reporter"),
        suspect_product=element(product, "product"),
        adverse_event=element(event, "event"),
    )


class TestOutcomes:
    def test_all_four_present_is_valid_icsr(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=True, reporter=True, product=True, event=True)
        )
        assert decision.outcome is ICSROutcome.VALID_ICSR
        assert decision.is_valid_icsr is True
        assert decision.requires_human_review is False
        assert decision.trace.fired_rules == ["val_001_all_criteria_present"]

    def test_missing_product_is_non_icsr(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=True, reporter=True, product=False, event=True)
        )
        assert decision.outcome is ICSROutcome.NON_ICSR
        assert decision.trace.fired_rules == ["val_001_missing_core_element"]
        assert "suspect product" in (decision.trace.explanation or "")

    def test_missing_event_is_non_icsr(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=True, reporter=True, product=True, event=False)
        )
        assert decision.outcome is ICSROutcome.NON_ICSR
        assert "adverse event" in (decision.trace.explanation or "")

    def test_missing_patient_escalates_rather_than_guessing(self) -> None:
        """A real signal with an incomplete record must escalate, not resolve."""
        decision = evaluate_validity(
            build_elements(patient=False, reporter=True, product=True, event=True)
        )
        assert decision.outcome is ICSROutcome.POTENTIAL_ICSR
        assert decision.requires_human_review is True
        assert decision.trace.fired_rules == ["val_001_incomplete_escalate"]
        assert "do not guess" in (decision.trace.explanation or "")

    def test_missing_reporter_escalates(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=True, reporter=False, product=True, event=True)
        )
        assert decision.outcome is ICSROutcome.POTENTIAL_ICSR

    def test_missing_patient_and_reporter_escalates_and_names_both(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=False, reporter=False, product=True, event=True)
        )
        assert decision.outcome is ICSROutcome.POTENTIAL_ICSR
        explanation = decision.trace.explanation or ""
        assert "identifiable patient" in explanation
        assert "identifiable reporter" in explanation

    def test_nothing_present_is_non_icsr(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=False, reporter=False, product=False, event=False)
        )
        assert decision.outcome is ICSROutcome.NON_ICSR


class TestExhaustiveTruthTable:
    def test_all_sixteen_combinations_are_deterministic_and_correct(self) -> None:
        """Core criteria dominate; otherwise completeness decides."""
        for patient, reporter, product, event in itertools.product([True, False], repeat=4):
            elements = build_elements(
                patient=patient, reporter=reporter, product=product, event=event
            )
            decision = evaluate_validity(elements)

            if not (product and event):
                expected = ICSROutcome.NON_ICSR
            elif patient and reporter:
                expected = ICSROutcome.VALID_ICSR
            else:
                expected = ICSROutcome.POTENTIAL_ICSR

            assert decision.outcome is expected, (
                f"patient={patient} reporter={reporter} product={product} event={event}"
            )
            # Exactly one rule fires for any input.
            assert len(decision.trace.fired_rules) == 1

    def test_same_input_yields_identical_trace(self) -> None:
        """Determinism: replaying the same facts reproduces the decision."""
        elements = build_elements(patient=True, reporter=False, product=True, event=True)
        first = evaluate_validity(elements)
        second = evaluate_validity(elements)
        assert first.trace.model_dump() == second.trace.model_dump()


class TestTrace:
    def test_trace_carries_rule_identity(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=True, reporter=True, product=True, event=True)
        )
        assert decision.trace.rule_id == RULE_ID
        assert decision.trace.rule_set_version == RULE_SET_VERSION
        assert decision.trace.outcome == ICSROutcome.VALID_ICSR.value

    def test_inputs_record_all_four_criteria(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=True, reporter=False, product=True, event=True)
        )
        assert decision.trace.inputs == {
            "identifiable_patient": True,
            "identifiable_reporter": False,
            "suspect_product": True,
            "adverse_event": True,
        }

    def test_provenance_quotes_evidence_when_present(self) -> None:
        decision = evaluate_validity(
            build_elements(
                patient=True, reporter=True, product=True, event=True, with_evidence=True
            )
        )
        provenance = decision.trace.input_provenance
        assert "evidence for patient" in provenance["identifiable_patient"]
        assert provenance["identifiable_patient"].startswith("present")

    def test_provenance_marks_absent_criteria(self) -> None:
        decision = evaluate_validity(
            build_elements(patient=False, reporter=True, product=True, event=True)
        )
        assert "ABSENT" in decision.trace.input_provenance["identifiable_patient"]

    def test_provenance_flags_present_without_evidence(self) -> None:
        """Presence asserted with no span is recorded honestly, not hidden."""
        decision = evaluate_validity(
            build_elements(
                patient=True, reporter=True, product=True, event=True, with_evidence=False
            )
        )
        assert "without an evidence span" in decision.trace.input_provenance["identifiable_patient"]

    def test_long_quotes_are_truncated_in_provenance(self) -> None:
        elements = ICSRElements(
            identifiable_patient=ICSRElement(
                present=True,
                evidence_span=EvidenceSpan(
                    source_record_id="src_1",
                    evidence_ref="k",
                    locator=Locator(),
                    quote="x" * 200,
                ),
            ),
            identifiable_reporter=ICSRElement(present=True),
            suspect_product=ICSRElement(present=True),
            adverse_event=ICSRElement(present=True),
        )
        decision = evaluate_validity(elements)
        assert "..." in decision.trace.input_provenance["identifiable_patient"]
