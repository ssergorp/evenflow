"""
Deterministic affordance test helpers.

Utilities to:
1) Seed traces with exact values to reach target affinities
2) Compute required trace values using inverse math
3) Override affordance config deterministically (patched, then restored)
4) Freeze time to eliminate decay drift
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Dict, Iterable, Iterator, Optional, Tuple

from world.affinity.core import Location, TraceRecord
from world.affinity.config import get_config
from world.affinity.affordances import AFFORDANCE_DEFAULTS, _AFFORDANCE_REGISTRY


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

    if valuation == 0:
        raise ValueError("Valuation is zero, cannot backsolve accumulated values.")

    # raw = sum(W_channel * accumulated_channel * valuation). Split raw across
    # channels in proportion to weight, then divide each share back out by its
    # own weight. Every seeded channel ends up with the same accumulated value.
    accumulated = raw_total / (total_weight * valuation)

    return {
        "personal": accumulated,
        "group_per_tag": accumulated if tags else 0.0,
        "behavior": accumulated if include_behavior else 0.0,
    }


# =============================================================================
# THRESHOLD LOOKUPS
# =============================================================================

def get_thresholds(affordance_type: str) -> Tuple[float, float]:
    """
    Get hostile and favorable thresholds for an affordance.

    Reads AFFORDANCE_DEFAULTS, the same source the evaluators use, so seeded
    affinities land on the side of the threshold the engine actually checks.

    Args:
        affordance_type: e.g., "pathing"

    Returns:
        (hostile_threshold, favorable_threshold)

    Raises:
        KeyError: if affordance_type is unknown
    """
    defaults = AFFORDANCE_DEFAULTS[affordance_type]
    return (defaults["hostile_threshold"], defaults["favorable_threshold"])


# =============================================================================
# DETERMINISTIC OVERRIDES (context managers, restored on exit)
# =============================================================================

@contextmanager
def deterministic_affordance(
    affordance_type: str,
    *,
    force_probability: float = 1.0,
    disable_others: bool = True,
) -> Iterator[None]:
    """
    Context manager for deterministic affordance testing.

    Temporarily patches module-level affordance state and restores it on exit:
    - AFFORDANCE_DEFAULTS[affordance_type]["base_probability"] = force_probability
    - every other affordance disabled in the registry (if disable_others=True).
      Disabling via the registry also covers misleading_navigation, whose
      redirect roll ignores base_probability.

    Not safe for tests that run concurrently in threads.

    Args:
        affordance_type: The affordance to make deterministic
        force_probability: Probability to set (default 1.0 = always trigger)
        disable_others: If True, disable all other affordances

    Raises:
        KeyError: if affordance_type is unknown

    Usage:
        with deterministic_affordance("pathing"):
            outcome = evaluate_affordances(ctx)
            assert outcome.triggered is True
    """
    if affordance_type not in AFFORDANCE_DEFAULTS:
        raise KeyError(f"Unknown affordance: {affordance_type!r}")

    original_prob = AFFORDANCE_DEFAULTS[affordance_type]["base_probability"]
    original_registry = dict(_AFFORDANCE_REGISTRY)

    try:
        AFFORDANCE_DEFAULTS[affordance_type]["base_probability"] = force_probability
        if disable_others:
            for aff_name in _AFFORDANCE_REGISTRY:
                _AFFORDANCE_REGISTRY[aff_name] = aff_name == affordance_type
        yield
    finally:
        AFFORDANCE_DEFAULTS[affordance_type]["base_probability"] = original_prob
        _AFFORDANCE_REGISTRY.clear()
        _AFFORDANCE_REGISTRY.update(original_registry)


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
