"""
Affinity System - Relationship Intelligence for Evennia

This module implements the affinity system as specified in docs/affinity_spec.md.
See docs/DO_NOT.md for hard constraints on implementation.
"""

from world.affinity.core import (
    TraceRecord,
    AffinityEvent,
    Location,
    SaturationState,
)
from world.affinity.computation import (
    get_decayed_value,
    get_valuation,
    compute_affinity,
    score_personal,
    score_group,
    score_behavior,
)
from world.affinity.affordances import (
    AffordanceContext,
    AffordanceOutcome,
    AffordanceTriggerLog,
    TraceContribution,
    AffordanceSnapshot,
    evaluate_affordances,
)
from world.affinity.events import log_event

__all__ = [
    # Core data structures
    "TraceRecord",
    "AffinityEvent",
    "Location",
    "SaturationState",
    # Computation
    "get_decayed_value",
    "get_valuation",
    "compute_affinity",
    "score_personal",
    "score_group",
    "score_behavior",
    # Affordances
    "AffordanceContext",
    "AffordanceOutcome",
    "AffordanceTriggerLog",
    "TraceContribution",
    "AffordanceSnapshot",
    "evaluate_affordances",
    # Events
    "log_event",
]
