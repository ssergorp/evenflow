"""
Admin commands for affinity debugging.

These are not full Evennia commands, but the logic that would
be called by Evennia command handlers.

See docs/affinity_spec.md §6.4
"""

from typing import Optional, List, Tuple, Set
import time

from world.affinity.core import Location, AffordanceTriggerLog
from world.affinity.computation import compute_affinity
from world.affinity.config import get_config


def get_top_contributing_traces(
    location: Location,
    actor_id: str,
    actor_tags: Set[str],
    n: int = 5,
    now: Optional[float] = None
) -> List[Tuple[str, float]]:
    """
    Get top N traces contributing to affinity.

    Args:
        location: Location to analyze
        actor_id: Actor ID
        actor_tags: Actor tags
        n: Number of top traces to return
        now: Current timestamp

    Returns:
        List of (trace_key, value) tuples
    """
    if now is None:
        now = time.time()

    config = get_config()
    traces = []

    # Convert half-lives to seconds
    from world.affinity.computation import get_decayed_value

    personal_half_life = config.half_lives.location.personal * 86400
    group_half_life = config.half_lives.location.group * 86400

    # Get personal traces for this actor
    for key, trace in location.personal_traces.items():
        if key[0] == actor_id:
            value = get_decayed_value(trace, personal_half_life, now)
            traces.append((f"personal:{key[0]}:{key[1]}", value))

    # Get group traces for actor tags
    for key, trace in location.group_traces.items():
        if key[0] in actor_tags:
            value = get_decayed_value(trace, group_half_life, now)
            traces.append((f"group:{key[0]}:{key[1]}", value))

    # Sort by absolute value (most influential)
    traces.sort(key=lambda x: abs(x[1]), reverse=True)

    return traces[:n]


def cmd_affinity_inspect(
    location: Location,
    actor_id: str,
    actor_tags: Set[str],
    now: Optional[float] = None
) -> str:
    """
    Admin command: affinity/inspect <location>

    Show current affinity toward caller and top traces.

    Args:
        location: Location to inspect
        actor_id: Actor ID
        actor_tags: Actor tags
        now: Current timestamp

    Returns:
        Formatted string for admin display
    """
    if now is None:
        now = time.time()

    affinity = compute_affinity(location, actor_id, actor_tags, now)
    top_traces = get_top_contributing_traces(location, actor_id, actor_tags, n=5, now=now)

    output = []
    output.append(f"Affinity Inspection: {location.name}")
    output.append(f"  Location ID: {location.location_id}")
    output.append(f"  Actor: {actor_id}")
    output.append(f"  Tags: {', '.join(actor_tags)}")
    output.append(f"  Affinity: {affinity:.3f}")
    output.append("")
    output.append("Top Contributing Traces:")

    if top_traces:
        for trace_key, value in top_traces:
            valence = "positive" if value > 0 else "negative"
            output.append(f"  {trace_key}: {value:.3f} ({valence})")
    else:
        output.append("  (no traces found)")

    output.append("")
    output.append(f"Total traces: {len(location.personal_traces)} personal, "
                  f"{len(location.group_traces)} group, {len(location.behavior_traces)} behavior")
    output.append(f"Scars: {len(location.scars)}")

    return "\n".join(output)


def cmd_affinity_why(
    trigger_log: AffordanceTriggerLog
) -> str:
    """
    Admin command: affinity/why <trigger_id>

    Explain why an affordance triggered.

    Args:
        trigger_log: Trigger log to explain

    Returns:
        Formatted explanation
    """
    output = []
    output.append(f"Affordance Trigger: {trigger_log.affordance_type}")
    output.append(f"  Location: {trigger_log.location_id}")
    output.append(f"  Actor: {trigger_log.actor_id}")
    output.append(f"  Tags: {', '.join(trigger_log.actor_tags)}")
    output.append(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(trigger_log.timestamp))}")
    output.append(f"  Raw affinity: {trigger_log.raw_affinity:.3f}")
    output.append(f"  Normalized affinity: {trigger_log.normalized_affinity:.3f}")
    output.append(f"  Threshold band: {trigger_log.threshold_band}")
    output.append("")
    output.append("Contributing Traces:")

    if trigger_log.top_traces:
        for trace_key, value in trigger_log.top_traces:
            output.append(f"  {trace_key}: {value:.3f}")
    else:
        output.append("  (no trace data available)")

    return "\n".join(output)


def cmd_affinity_replay(
    trigger_log: AffordanceTriggerLog
) -> str:
    """
    Admin command: affinity/replay <trigger_id>

    Replay affordance evaluation from snapshot.
    Verifies computation is deterministic.

    Args:
        trigger_log: Trigger log with snapshot

    Returns:
        Comparison of original vs replayed results
    """
    output = []
    output.append(f"Replay Verification: {trigger_log.affordance_type}")
    output.append(f"  Original affinity: {trigger_log.normalized_affinity:.3f}")

    # For MVP, we don't have full replay implementation
    # In full version, would reconstruct location state from snapshot
    # and re-run affordance evaluation
    output.append("  Replayed affinity: [replay not yet implemented]")
    output.append("")
    output.append("Snapshot available: " + ("Yes" if trigger_log.snapshot else "No"))

    if trigger_log.snapshot:
        output.append(f"Snapshot keys: {', '.join(trigger_log.snapshot.keys())}")

    return "\n".join(output)


def cmd_affinity_history(
    location: Location,
    actor_id: str,
    limit: int = 10
) -> str:
    """
    Admin command: affinity/history <location> <actor>

    Show history of events for an actor at a location.

    Args:
        location: Location to query
        actor_id: Actor ID
        limit: Maximum number of events to show

    Returns:
        Formatted history
    """
    output = []
    output.append(f"Event History: {location.name}")
    output.append(f"  Actor: {actor_id}")
    output.append("")

    # Get all traces for this actor
    personal_traces = [
        (key, trace) for key, trace in location.personal_traces.items()
        if key[0] == actor_id
    ]

    if not personal_traces:
        output.append("  (no personal history found)")
    else:
        # Sort by last_updated (most recent first)
        personal_traces.sort(key=lambda x: x[1].last_updated, reverse=True)

        output.append("Personal Traces:")
        for i, (key, trace) in enumerate(personal_traces[:limit]):
            event_type = key[1]
            output.append(f"  {i+1}. {event_type}")
            output.append(f"     Accumulated: {trace.accumulated:.3f}")
            output.append(f"     Events: {trace.event_count}")
            output.append(f"     Last updated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(trace.last_updated))}")

    return "\n".join(output)


def cmd_affinity_summary(
    location: Location
) -> str:
    """
    Admin command: affinity/summary <location>

    Show summary statistics for a location.

    Args:
        location: Location to summarize

    Returns:
        Formatted summary
    """
    output = []
    output.append(f"Location Summary: {location.name}")
    output.append(f"  ID: {location.location_id}")
    output.append("")

    # Trace counts
    output.append("Trace Counts:")
    output.append(f"  Personal: {len(location.personal_traces)}")
    output.append(f"  Group: {len(location.group_traces)}")
    output.append(f"  Behavior: {len(location.behavior_traces)}")
    output.append(f"  Scars: {len(location.scars)}")
    output.append("")

    # Saturation
    output.append("Saturation:")
    output.append(f"  Personal: {location.saturation.personal:.3f}")
    output.append(f"  Group: {location.saturation.group:.3f}")
    output.append(f"  Behavior: {location.saturation.behavior:.3f}")
    output.append("")

    # Cooldowns
    output.append(f"Active Cooldowns: {len(location.cooldowns)}")

    # Last tick
    if location.last_tick > 0:
        tick_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(location.last_tick))
        output.append(f"Last Tick: {tick_time}")
    else:
        output.append("Last Tick: never")

    return "\n".join(output)
