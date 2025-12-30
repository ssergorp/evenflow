"""
Deterministic affordance test helpers.

Utilities to:
1) Seed traces with exact values to reach target affinities
2) Compute required trace values using inverse math
3) Override affordance config deterministically (no global leakage)
4) Freeze time to eliminate decay drift
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import replace
from typing import Dict, Iterable, Iterator, Optional, Tuple

from world.affinity.core import Location, TraceRecord, AffordanceConfig
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
    timestamp: float,
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
        is_scar=False,
    )


def seed_group_trace(
    location: Location,
    group_tag: str,
    event_type: str,
    accumulated: float,
    timestamp: float,
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
        is_scar=False,
    )


def seed_behavior_trace(
    location: Location,
    event_type: str,
    accumulated: float,
    timestamp: float,
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
        is_scar=False,
    )


# =============================================================================
# INVERSE MATH
# =============================================================================

def _atanh_clamped(x: float) -> float:
    """Clamp x to valid atanh range and compute."""
    x = max(-0.999, min(0.999, x))
    return math.atanh(x)


def compute_required_personal_trace(
    target_affinity: float,
    valuation: float,
    *,
    affinity_scale: Optional[float] = None,
    channel_weight: Optional[float] = None,
) -> float:
    """
    Compute the accumulated trace value needed to reach a target affinity.

    Assumes ONLY personal channel contributes (for simplicity).

    Uses inverse of: affinity = tanh(raw / scale)
    Where: raw = Wp * (accumulated * valuation)

    Args:
        target_affinity: Desired affinity value (e.g., -0.4)
        valuation: Valuation for the event type (e.g., -0.8 for harm.fire)
        affinity_scale: Scale factor (default: from config)
        channel_weight: Personal channel weight (default: from config)

    Returns:
        Required accumulated trace value

    Example:
        >>> accumulated = compute_required_personal_trace(-0.4, -0.8)
        >>> # accumulated ≈ 10.6
    """
    config = get_config()
    scale = config.affinity_scale if affinity_scale is None else affinity_scale
    weight = config.channel_weights.personal if channel_weight is None else channel_weight

    raw = _atanh_clamped(target_affinity) * scale
    denom = weight * valuation
    if denom == 0:
        raise ValueError("Cannot compute required trace: weight or valuation is zero.")
    return raw / denom


def compute_required_traces_for_tags(
    target_affinity: float,
    valuation: float,
    *,
    tags_to_seed: Iterable[str] = (),
    include_behavior: bool = False,
    affinity_scale: Optional[float] = None,
) -> Dict[str, float]:
    """
    Compute accumulated values for multiple channels to reach target affinity.

    Returns:
        Dict with keys:
        - "personal": accumulated value for personal channel
        - "group_per_tag": accumulated value per group tag (apply to each tag)
        - "behavior": accumulated value for behavior (if include_behavior=True)

    This avoids silently assuming you seed every actor tag.

    Args:
        target_affinity: Desired affinity value
        valuation: Valuation for the event type
        tags_to_seed: Which group tags will be seeded
        include_behavior: Whether to include behavior channel
        affinity_scale: Scale factor (default: from config)
    """
    config = get_config()
    scale = config.affinity_scale if affinity_scale is None else affinity_scale

    raw_total = _atanh_clamped(target_affinity) * scale

    tags = list(tags_to_seed)
    wp = config.channel_weights.personal
    wg = config.channel_weights.group
    wb = config.channel_weights.behavior if include_behavior else 0.0

    total_weight = wp + (wg * len(tags)) + wb
    if total_weight == 0:
        raise ValueError("Total weight is zero, cannot distribute raw.")

    personal_raw = raw_total * (wp / total_weight)
    group_raw_per_tag = raw_total * (wg / total_weight) if tags else 0.0
    behavior_raw = raw_total * (wb / total_weight) if include_behavior else 0.0

    if valuation == 0:
        raise ValueError("Valuation is zero, cannot backsolve accumulated values.")

    return {
        "personal": personal_raw / valuation,
        "group_per_tag": group_raw_per_tag / valuation,
        "behavior": behavior_raw / valuation if include_behavior else 0.0,
    }


# =============================================================================
# THRESHOLD LOOKUPS (prefer location config over globals)
# =============================================================================

def get_thresholds(location: Location, affordance_type: str) -> Tuple[float, float]:
    """
    Get hostile and favorable thresholds for an affordance.

    Prefers location.affordances config, falls back to AFFORDANCE_DEFAULTS.

    Args:
        location: Location to check
        affordance_type: e.g., "pathing"

    Returns:
        (hostile_threshold, favorable_threshold)
    """
    # Check location-specific affordances first
    for aff in location.affordances:
        if aff.affordance_type == affordance_type:
            # Use getattr with fallback for optional fields
            hostile = getattr(aff, 'hostile_threshold', None)
            favorable = getattr(aff, 'favorable_threshold', None)
            if hostile is not None and favorable is not None:
                return (hostile, favorable)

    # Fall back to AFFORDANCE_DEFAULTS
    defaults = AFFORDANCE_DEFAULTS.get(affordance_type, {})
    return (
        defaults.get("hostile_threshold", -0.3),
        defaults.get("favorable_threshold", 0.3),
    )


# =============================================================================
# DETERMINISTIC OVERRIDES (context managers, no global mutation)
# =============================================================================

@contextmanager
def deterministic_affordance(
    location: Location,
    affordance_type: str,
    *,
    force_probability: float = 1.0,
    disable_others: bool = True,
) -> Iterator[None]:
    """
    Context manager for deterministic affordance testing.

    Temporarily modifies:
    - The target affordance probability to 1.0
    - All other affordance probabilities to 0.0 (if disable_others=True)

    Args:
        location: Location to modify
        affordance_type: The affordance to make deterministic
        force_probability: Probability to set (default 1.0 = always trigger)
        disable_others: If True, set probability=0 for all other affordances

    Usage:
        with deterministic_affordance(location, "pathing"):
            outcome = evaluate_affordances(ctx)
            assert outcome.triggered is True
    """
    # Store original probabilities for ALL affordances
    original_probs: Dict[str, float] = {}
    for aff_name, config in AFFORDANCE_DEFAULTS.items():
        original_probs[aff_name] = config.get("base_probability", 1.0)

    try:
        # Set target affordance to force_probability
        if affordance_type in AFFORDANCE_DEFAULTS:
            AFFORDANCE_DEFAULTS[affordance_type]["base_probability"] = force_probability

        # If disable_others, set all others to 0
        if disable_others:
            for aff_name in AFFORDANCE_DEFAULTS:
                if aff_name != affordance_type:
                    AFFORDANCE_DEFAULTS[aff_name]["base_probability"] = 0.0

        yield

    finally:
        # Restore all original probabilities
        for aff_name, prob in original_probs.items():
            if aff_name in AFFORDANCE_DEFAULTS:
                AFFORDANCE_DEFAULTS[aff_name]["base_probability"] = prob


@contextmanager
def freeze_time(monkeypatch, fixed_time: float) -> Iterator[float]:
    """
    Context manager to freeze time.time() to a fixed value.

    Prevents decay drift in tests that assert strict equality.

    Args:
        monkeypatch: pytest's monkeypatch fixture
        fixed_time: The fixed timestamp to return

    Usage:
        def test_something(monkeypatch, location):
            with freeze_time(monkeypatch, 1_700_000_000.0) as now:
                seed_personal_trace(location, actor, event, value, now)
                # time.time() will return 1_700_000_000.0
    """
    import time as time_module
    monkeypatch.setattr(time_module, "time", lambda: fixed_time)
    yield fixed_time
