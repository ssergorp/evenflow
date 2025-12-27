"""
Event logging for the affinity system.

See docs/affinity_spec.md §3 for event ontology.
"""

import time
from world.affinity.core import AffinityEvent, Location, TraceRecord, SaturationState
from world.affinity.config import get_config
from world.affinity.computation import get_decayed_value


def _get_saturation_for_channel(saturation: SaturationState, channel: str) -> float:
    """Get saturation value for a specific channel."""
    if channel == "personal":
        return saturation.personal
    elif channel == "group":
        return saturation.group
    elif channel == "behavior":
        return saturation.behavior
    return 0.0


def _apply_saturation(intensity: float, saturation: float) -> float:
    """
    Apply saturation dampening to intensity.

    See spec §4.4:
        effective_intensity = raw_intensity * (1 - saturation^2)
    """
    return intensity * (1 - saturation ** 2)


def _update_trace(
    trace: TraceRecord,
    intensity: float,
    timestamp: float,
    half_life_seconds: float
) -> None:
    """
    Update a trace with a new event.

    See spec §4.4: Decay existing value, then add new intensity.
    """
    # Decay existing value to present
    decayed = get_decayed_value(trace, half_life_seconds)

    # Add new intensity
    trace.accumulated = decayed + intensity
    trace.last_updated = timestamp
    trace.event_count += 1


def _create_trace(intensity: float, timestamp: float) -> TraceRecord:
    """Create a new trace record."""
    return TraceRecord(
        accumulated=intensity,
        last_updated=timestamp,
        event_count=1,
        is_scar=False
    )


def log_event(location: Location, event: AffinityEvent) -> None:
    """
    Log an affinity event to a location's memory.

    Updates all three channels:
    - Personal: (actor_id, event_type)
    - Group: (actor_tag, event_type) for each tag
    - Behavior: event_type

    See spec §4.4

    Args:
        location: The location to update
        event: The affinity event to log
    """
    config = get_config()
    timestamp = event.timestamp

    # Convert half-lives from days to seconds
    personal_half_life = config.half_lives.location.personal * 86400
    group_half_life = config.half_lives.location.group * 86400
    behavior_half_life = config.half_lives.location.behavior * 86400

    # --- Personal Channel ---
    personal_key = (event.actor_id, event.event_type)
    personal_intensity = _apply_saturation(
        event.intensity,
        location.saturation.personal
    )

    if personal_key in location.personal_traces:
        _update_trace(
            location.personal_traces[personal_key],
            personal_intensity,
            timestamp,
            personal_half_life
        )
    else:
        location.personal_traces[personal_key] = _create_trace(
            personal_intensity,
            timestamp
        )

    # --- Group Channel ---
    group_intensity = _apply_saturation(
        event.intensity,
        location.saturation.group
    )

    for tag in event.actor_tags:
        group_key = (tag, event.event_type)
        if group_key in location.group_traces:
            _update_trace(
                location.group_traces[group_key],
                group_intensity,
                timestamp,
                group_half_life
            )
        else:
            location.group_traces[group_key] = _create_trace(
                group_intensity,
                timestamp
            )

    # --- Behavior Channel ---
    behavior_key = event.event_type
    behavior_intensity = _apply_saturation(
        event.intensity,
        location.saturation.behavior
    )

    if behavior_key in location.behavior_traces:
        _update_trace(
            location.behavior_traces[behavior_key],
            behavior_intensity,
            timestamp,
            behavior_half_life
        )
    else:
        location.behavior_traces[behavior_key] = _create_trace(
            behavior_intensity,
            timestamp
        )
