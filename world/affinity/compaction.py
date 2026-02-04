"""
Memory compaction: hot → warm → scar lifecycle.

See docs/affinity_spec.md §4.7
"""

from typing import Dict, Tuple, Set, List, Optional
from dataclasses import dataclass
import time

from world.affinity.core import Location, TraceRecord, ScarEvent
from world.affinity.config import get_config


@dataclass
class CompactionReport:
    """Report of what compaction did."""
    location_id: str
    timestamp: float
    hot_to_warm: int       # Personal traces discarded
    warm_to_scar: int      # Scars created
    traces_compacted: int  # Group traces merged


def fold_actor_tag(tag: str) -> Optional[str]:
    """
    Return tag if institutional, else None.

    Institutional tags survive compaction; others are discarded/aggregated.

    Args:
        tag: Actor tag to check

    Returns:
        Tag if institutional, None otherwise
    """
    config = get_config()
    return tag if tag in config.institutional_tags else None


def fold_event_type(event_type: str) -> str:
    """
    Extract category prefix: 'harm.fire' → 'harm'

    Args:
        event_type: Event type with optional subtype

    Returns:
        Category prefix only
    """
    return event_type.split('.')[0]


def compact_personal_traces(
    location: Location,
    hot_window_seconds: float,
    now: float
) -> int:
    """
    Hot → Warm: Discard personal traces older than hot window.

    After the hot window, we forget individual IDs.

    Returns:
        Number of personal traces discarded
    """
    to_remove = []

    for key, trace in location.personal_traces.items():
        age_seconds = now - trace.last_updated
        if age_seconds > hot_window_seconds:
            to_remove.append(key)

    for key in to_remove:
        del location.personal_traces[key]

    return len(to_remove)


def compact_group_traces(
    location: Location,
    hot_window_seconds: float,
    warm_window_seconds: float,
    now: float
) -> int:
    """
    Hot → Warm: Merge group traces older than the *warm* window.

    Rationale (tests + Phase 1 behavior): group traces should remain usable for
    at least ~90 days; compacting them after the hot window (7 days) makes recent
    actor-tag memory disappear too quickly and breaks the vertical slice.

    Only institutional tags survive folding. Keys become (folded_tag, category).
    Non-institutional tags are discarded.

    Returns number of traces processed/compacted.
    """
    compacted_count = 0

    merged: Dict[Tuple[str, str], TraceRecord] = {}

    for key, trace in location.group_traces.items():
        actor_tag, event_type = key
        age_seconds = now - trace.last_updated

        if age_seconds <= hot_window_seconds:
            # Still hot, keep as-is
            merged[key] = trace
            continue

        # Older than hot window → fold
        folded_tag = fold_actor_tag(actor_tag)
        if not folded_tag:
            # Non-institutional tag, discard
            compacted_count += 1
            continue

        category = fold_event_type(event_type)
        merged_key = (folded_tag, category)

        if merged_key in merged:
            merged[merged_key].accumulated += trace.accumulated
            merged[merged_key].event_count += trace.event_count
            merged[merged_key].last_updated = max(merged[merged_key].last_updated, trace.last_updated)
        else:
            merged[merged_key] = TraceRecord(
                accumulated=trace.accumulated,
                last_updated=trace.last_updated,
                event_count=trace.event_count,
                is_scar=trace.is_scar,
            )

        compacted_count += 1

    location.group_traces = merged
    return compacted_count


def create_scars_from_warm(
    location: Location,
    warm_window_seconds: float,
    scar_intensity_threshold: float,
    now: float
) -> int:
    """
    Warm → Scar: Convert high-intensity old traces to scars.

    Only traces with intensity > threshold become scars.
    Everything else decays to zero and is deleted by pruning.

    Args:
        location: Location to create scars for
        warm_window_seconds: Age threshold for warm traces
        scar_intensity_threshold: Minimum intensity to become scar
        now: Current timestamp

    Returns:
        Number of scars created
    """
    config = get_config()
    scars_created = 0

    # Check group traces (personal already discarded)
    for key, trace in location.group_traces.items():
        age_seconds = now - trace.last_updated

        if age_seconds > warm_window_seconds:
            # Check if this should become a scar
            # Approximate intensity from accumulated value
            # (This is heuristic; ideally we'd track original intensity)
            if abs(trace.accumulated) > scar_intensity_threshold:
                # Create scar
                actor_tag, event_type = key
                folded_tag = fold_actor_tag(actor_tag)

                if folded_tag:
                    category = fold_event_type(event_type)

                    scar = ScarEvent(
                        event_type=category,
                        actor_tags={folded_tag},
                        intensity=abs(trace.accumulated),
                        timestamp=trace.last_updated,
                        half_life_seconds=config.compaction.scar_half_life_days * 86400,
                    )

                    location.scars.append(scar)
                    scars_created += 1

    return scars_created


def compact_traces(location: Location, now: Optional[float] = None) -> CompactionReport:
    """
    Run full compaction on a location.

    Performs:
    1. Hot → Warm: Discard old personal traces
    2. Hot → Warm: Merge old group traces by institutional tags + category
    3. Warm → Scar: Convert high-intensity old traces to scars

    Should be called during world tick.

    Args:
        location: Location to compact
        now: Current timestamp (for deterministic testing)

    Returns:
        CompactionReport with stats

    See docs/affinity_spec.md §4.7
    """
    if now is None:
        now = time.time()

    config = get_config()

    hot_window_seconds = config.compaction.hot_window_days * 86400
    warm_window_seconds = config.compaction.warm_window_days * 86400
    scar_intensity_threshold = config.compaction.scar_intensity_threshold

    # Step 1: Discard old personal traces
    hot_to_warm = compact_personal_traces(location, hot_window_seconds, now)

    # Step 2: Create scars before compacting (so we don't lose high-intensity traces)
    warm_to_scar = create_scars_from_warm(
        location,
        warm_window_seconds,
        scar_intensity_threshold,
        now
    )

    # Step 3: Compact group traces
    traces_compacted = compact_group_traces(
        location,
        hot_window_seconds,
        warm_window_seconds,
        now
    )

    return CompactionReport(
        location_id=location.location_id,
        timestamp=now,
        hot_to_warm=hot_to_warm,
        warm_to_scar=warm_to_scar,
        traces_compacted=traces_compacted,
    )
