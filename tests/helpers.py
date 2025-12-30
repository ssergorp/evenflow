"""
Test helpers for deterministic affordance testing.

Provides utilities to:
1. Seed traces with exact values to reach target affinities
2. Compute required trace values using inverse math
3. Override affordance config for determinism
"""

import math
from typing import Dict, Optional, Set

from world.affinity.core import Location, TraceRecord
from world.affinity.config import get_config
from world.affinity.affordances import AFFORDANCE_DEFAULTS


# =============================================================================
# TRACE SEEDING HELPERS
# =============================================================================

def seed_personal_trace(
    location: Location,
    actor_id: str,
    event_type: str,
    accumulated: float,
    timestamp: float
) -> None:
    """
    Seed a personal trace with an exact accumulated value.

    Args:
        location: Location to modify
        actor_id: Actor ID for the trace
        event_type: Event type (e.g., "harm.fire")
        accumulated: Exact accumulated value to set
        timestamp: Timestamp for last_updated
    """
    location.personal_traces[(actor_id, event_type)] = TraceRecord(
        accumulated=accumulated,
        last_updated=timestamp,
        event_count=1,
        is_scar=False
    )


def seed_group_trace(
    location: Location,
    group_tag: str,
    event_type: str,
    accumulated: float,
    timestamp: float
) -> None:
    """
    Seed a group trace with an exact accumulated value.

    Args:
        location: Location to modify
        group_tag: Group tag (e.g., "human")
        event_type: Event type (e.g., "harm.fire")
        accumulated: Exact accumulated value to set
        timestamp: Timestamp for last_updated
    """
    location.group_traces[(group_tag, event_type)] = TraceRecord(
        accumulated=accumulated,
        last_updated=timestamp,
        event_count=1,
        is_scar=False
    )


def seed_behavior_trace(
    location: Location,
    event_type: str,
    accumulated: float,
    timestamp: float
) -> None:
    """
    Seed a behavior trace with an exact accumulated value.

    Args:
        location: Location to modify
        event_type: Event type (e.g., "harm.fire")
        accumulated: Exact accumulated value to set
        timestamp: Timestamp for last_updated
    """
    location.behavior_traces[event_type] = TraceRecord(
        accumulated=accumulated,
        last_updated=timestamp,
        event_count=1,
        is_scar=False
    )


# =============================================================================
# INVERSE MATH: COMPUTE REQUIRED TRACE VALUE
# =============================================================================

def compute_required_personal_trace(
    target_affinity: float,
    valuation: float,
    affinity_scale: Optional[float] = None,
    channel_weight: Optional[float] = None
) -> float:
    """
    Compute the accumulated trace value needed to reach a target affinity.

    Uses inverse of: affinity = tanh(raw / scale)
    Where: raw = channel_weight * (accumulated * valuation)

    Assumes only personal channel contributes (for simplicity).

    Args:
        target_affinity: Desired affinity value (e.g., -0.4)
        valuation: Valuation for the event type (e.g., -0.8 for harm.fire)
        affinity_scale: Scale factor (default: from config)
        channel_weight: Personal channel weight (default: from config)

    Returns:
        Required accumulated trace value

    Example:
        >>> # To get affinity = -0.4 with harm.fire (valuation=-0.8)
        >>> accumulated = compute_required_personal_trace(-0.4, -0.8)
        >>> # accumulated ≈ 10.6
    """
    config = get_config()
    scale = affinity_scale or config.affinity_scale
    weight = channel_weight or config.channel_weights.personal

    # Clamp target to valid tanh range
    target_affinity = max(-0.999, min(0.999, target_affinity))

    # Inverse tanh: raw = atanh(affinity) * scale
    raw = math.atanh(target_affinity) * scale

    # raw = weight * (accumulated * valuation)
    # accumulated = raw / (weight * valuation)
    if weight * valuation == 0:
        raise ValueError("Cannot compute trace: weight or valuation is zero")

    return raw / (weight * valuation)


def compute_required_combined_trace(
    target_affinity: float,
    valuation: float,
    actor_tags: Set[str],
    affinity_scale: Optional[float] = None
) -> Dict[str, float]:
    """
    Compute trace values for all channels to reach target affinity.

    Returns accumulated values for personal, group (per tag), and behavior.

    Args:
        target_affinity: Desired affinity value
        valuation: Valuation for the event type
        actor_tags: Actor's group tags
        affinity_scale: Scale factor (default: from config)

    Returns:
        Dict with keys: "personal", "group", "behavior" -> accumulated values
    """
    config = get_config()
    scale = affinity_scale or config.affinity_scale

    target_affinity = max(-0.999, min(0.999, target_affinity))
    raw = math.atanh(target_affinity) * scale

    # Distribute raw across channels proportionally to weights
    weights = config.channel_weights
    total_weight = weights.personal + weights.group * len(actor_tags) + weights.behavior

    personal_raw = raw * (weights.personal / total_weight)
    group_raw = raw * (weights.group / total_weight)  # Per tag
    behavior_raw = raw * (weights.behavior / total_weight)

    return {
        "personal": personal_raw / valuation if valuation != 0 else 0,
        "group": group_raw / valuation if valuation != 0 else 0,
        "behavior": behavior_raw / valuation if valuation != 0 else 0,
    }


# =============================================================================
# CONFIG OVERRIDES FOR DETERMINISM
# =============================================================================

def get_affordance_threshold(affordance_type: str, direction: str) -> float:
    """
    Get the threshold for an affordance from AFFORDANCE_DEFAULTS.

    Args:
        affordance_type: e.g., "pathing"
        direction: "hostile" or "favorable"

    Returns:
        Threshold value
    """
    defaults = AFFORDANCE_DEFAULTS.get(affordance_type, {})
    if direction == "hostile":
        return defaults.get("hostile_threshold", -0.3)
    else:
        return defaults.get("favorable_threshold", 0.3)


def override_affordance_probability(affordance_type: str, probability: float) -> None:
    """
    Override base_probability for an affordance (for deterministic testing).

    NOTE: This modifies the global AFFORDANCE_DEFAULTS dict.
    Call restore_affordance_defaults() after test.

    Args:
        affordance_type: e.g., "pathing"
        probability: New probability (use 1.0 for always-trigger)
    """
    if affordance_type in AFFORDANCE_DEFAULTS:
        AFFORDANCE_DEFAULTS[affordance_type]["base_probability"] = probability


# Store original probabilities for restoration
_original_probabilities: Dict[str, float] = {}


def set_deterministic_probabilities() -> None:
    """Set all affordance probabilities to 1.0 for deterministic testing."""
    global _original_probabilities
    _original_probabilities = {}

    for aff_type, config in AFFORDANCE_DEFAULTS.items():
        _original_probabilities[aff_type] = config.get("base_probability", 1.0)
        config["base_probability"] = 1.0


def restore_affordance_defaults() -> None:
    """Restore original affordance probabilities."""
    global _original_probabilities

    for aff_type, prob in _original_probabilities.items():
        if aff_type in AFFORDANCE_DEFAULTS:
            AFFORDANCE_DEFAULTS[aff_type]["base_probability"] = prob

    _original_probabilities = {}
