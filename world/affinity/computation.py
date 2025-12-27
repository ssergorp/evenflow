"""
Affinity computation functions.

See docs/affinity_spec.md §4.3-4.6 for specification.
"""

import math
import time
from typing import Dict, Optional, Set, Tuple

from world.affinity.core import TraceRecord, Location
from world.affinity.config import get_config


def get_decayed_value(
    trace: TraceRecord,
    half_life_seconds: float,
    now: Optional[float] = None
) -> float:
    """
    Compute current value after exponential decay.

    See spec §4.3:
        current_value = accumulated * (0.5 ^ (time_elapsed / half_life))

    Args:
        trace: The trace record to decay
        half_life_seconds: Half-life in seconds
        now: Evaluation time. If None, uses current time.
             Pass explicit value for deterministic replay.

    Returns:
        Decayed value at specified time
    """
    if now is None:
        now = time.time()
    elapsed = now - trace.last_updated
    if elapsed <= 0:
        return trace.accumulated
    decay_factor = 0.5 ** (elapsed / half_life_seconds)
    return trace.accumulated * decay_factor


def get_valuation(profile: Dict[str, float], event_type: str) -> float:
    """
    Look up valuation for an event type with category fallback.

    See spec §3.3:
        1. Exact match: "harm.fire"
        2. Category match: "harm" (prefix before first dot)
        3. Default: 0.0

    Args:
        profile: Entity's valuation profile (NOT global EVENT_WEIGHTS)
        event_type: The event type to look up

    Returns:
        Valuation weight for this event type
    """
    # Try exact match
    if event_type in profile:
        return profile[event_type]

    # Try category match
    category = event_type.split('.')[0]
    if category in profile:
        return profile[category]

    # Default: neutral
    return 0.0


def score_personal(
    traces: Dict[Tuple[str, str], TraceRecord],
    actor_id: str,
    half_life_seconds: float,
    profile: Dict[str, float],
    now: Optional[float] = None
) -> float:
    """
    Score personal channel for a specific actor.

    Keys are (actor_id, event_type) tuples.
    See spec §4.6

    Args:
        traces: Personal trace dict
        actor_id: The actor to score for
        half_life_seconds: Decay half-life
        profile: Location's valuation profile
        now: Evaluation time for deterministic replay

    Returns:
        Weighted score for personal channel
    """
    score = 0.0
    for (trace_actor_id, event_type), trace in traces.items():
        if trace_actor_id != actor_id:
            continue
        value = get_decayed_value(trace, half_life_seconds, now)
        valuation = get_valuation(profile, event_type)
        score += value * valuation
    return score


def score_group(
    traces: Dict[Tuple[str, str], TraceRecord],
    actor_tags: Set[str],
    half_life_seconds: float,
    profile: Dict[str, float],
    now: Optional[float] = None
) -> float:
    """
    Score group channel for an actor's tags.

    Keys are (actor_tag, event_type) tuples.
    See spec §4.6

    Args:
        traces: Group trace dict
        actor_tags: The actor's categorical tags
        half_life_seconds: Decay half-life
        profile: Location's valuation profile
        now: Evaluation time for deterministic replay

    Returns:
        Weighted score for group channel
    """
    score = 0.0
    for (trace_tag, event_type), trace in traces.items():
        if trace_tag not in actor_tags:
            continue
        value = get_decayed_value(trace, half_life_seconds, now)
        valuation = get_valuation(profile, event_type)
        score += value * valuation
    return score


def score_behavior(
    traces: Dict[str, TraceRecord],
    half_life_seconds: float,
    profile: Dict[str, float],
    now: Optional[float] = None
) -> float:
    """
    Score behavior channel (general place character).

    Keys are event_type strings.
    See spec §4.6

    Args:
        traces: Behavior trace dict
        half_life_seconds: Decay half-life
        profile: Location's valuation profile
        now: Evaluation time for deterministic replay

    Returns:
        Weighted score for behavior channel
    """
    score = 0.0
    for event_type, trace in traces.items():
        value = get_decayed_value(trace, half_life_seconds, now)
        valuation = get_valuation(profile, event_type)
        score += value * valuation
    return score


def compute_affinity(
    location: Location,
    actor_id: str,
    actor_tags: Set[str],
    now: Optional[float] = None
) -> float:
    """
    Compute affinity for an actor at a location.

    Blends personal, group, and behavior channels.
    Half-lives come from config, not from traces.
    Valuation comes from the location's profile (NOT global EVENT_WEIGHTS).

    See spec §4.6

    Args:
        location: The location to compute affinity for
        actor_id: The actor's unique ID
        actor_tags: The actor's categorical tags
        now: Evaluation time for deterministic replay

    Returns:
        Affinity value in range [-1.0, 1.0]
    """
    config = get_config()
    profile = location.valuation_profile

    # Convert half-lives from days to seconds
    personal_half_life = config.half_lives.location.personal * 86400
    group_half_life = config.half_lives.location.group * 86400
    behavior_half_life = config.half_lives.location.behavior * 86400

    personal = score_personal(
        location.personal_traces,
        actor_id,
        personal_half_life,
        profile,
        now
    )

    group = score_group(
        location.group_traces,
        actor_tags,
        group_half_life,
        profile,
        now
    )

    behavior = score_behavior(
        location.behavior_traces,
        behavior_half_life,
        profile,
        now
    )

    # Blend channels with configured weights
    W = config.channel_weights
    raw = W.personal * personal + W.group * group + W.behavior * behavior

    # Normalize to [-1, 1] using tanh
    return math.tanh(raw / config.affinity_scale)


def get_threshold_label(affinity: float) -> str:
    """
    Map affinity value to threshold label.

    See spec §4.9

    Args:
        affinity: Affinity value in [-1.0, 1.0]

    Returns:
        Threshold label: "hostile", "unwelcoming", "neutral", "favorable", "aligned"
    """
    if affinity <= -0.7:
        return "hostile"
    elif affinity <= -0.3:
        return "unwelcoming"
    elif affinity <= 0.3:
        return "neutral"
    elif affinity <= 0.7:
        return "favorable"
    else:
        return "aligned"
