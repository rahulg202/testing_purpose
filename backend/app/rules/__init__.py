"""Deterministic, versioned rule interpreters.

The core thesis of Atheria: the AI proposes, a versioned deterministic rules
engine decides, a qualified human approves. Rules in this package are pure
functions over extracted facts. They never guess: when an input cannot be
determined they escalate rather than fabricate a value, and every decision
emits a ``RuleEvaluation`` trace answering "which rule decided this, and why".
"""
