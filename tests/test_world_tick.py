"""
Tests for world tick system.

See world/affinity/world_tick.py for implementation.
"""

import time

from world.affinity.core import Location, TraceRecord, SaturationState
from world.affinity.world_tick import (
    world_tick,
    prune_traces,
    clear_expired_cooldowns,
    decay_saturation,
    TickReport,
)


def create_test_location():
    """Create a basic test location."""
    return Location(
        location_id="test_woods",
        name="Test Woods",
        description="A test location",
        valuation_profile={"harm.fire": -0.8},
    )


def test_prune_traces_below_threshold():
    """Traces decayed below threshold should be removed."""
    location = create_test_location()
    now = time.time()

    # Add trace that will decay below threshold
    # With 7-day half-life, after 30 days this will be heavily decayed
    location.personal_traces[("actor_1", "harm.fire")] = TraceRecord(
        accumulated=0.01,  # Very small
        last_updated=now - (30 * 86400),  # 30 days ago
        event_count=1
    )

    # Prune with threshold 0.01
    pruned = prune_traces(location, threshold=0.01, now=now)

    assert pruned > 0
    assert ("actor_1", "harm.fire") not in location.personal_traces


def test_prune_keeps_above_threshold():
    """Traces above threshold should be kept."""
    location = create_test_location()
    now = time.time()

    # Add trace with high value that won't decay much
    location.personal_traces[("actor_1", "harm.fire")] = TraceRecord(
        accumulated=10.0,  # High value
        last_updated=now - (1 * 86400),  # 1 day ago
        event_count=1
    )

    pruned = prune_traces(location, threshold=0.01, now=now)

    assert pruned == 0
    assert ("actor_1", "harm.fire") in location.personal_traces


def test_prune_all_trace_types():
    """Pruning should work on personal, group, and behavior traces."""
    location = create_test_location()
    now = time.time()

    # Add old traces to all channels
    old_time = now - (90 * 86400)  # 90 days ago

    location.personal_traces[("actor_1", "harm")] = TraceRecord(0.001, old_time, 1)
    location.group_traces[("human", "harm")] = TraceRecord(0.001, old_time, 1)
    location.behavior_traces["harm"] = TraceRecord(0.001, old_time, 1)

    pruned = prune_traces(location, threshold=0.01, now=now)

    assert pruned == 3
    assert len(location.personal_traces) == 0
    assert len(location.group_traces) == 0
    assert len(location.behavior_traces) == 0


def test_clear_expired_cooldowns():
    """Expired cooldowns should be removed."""
    location = create_test_location()
    now = time.time()

    location.cooldowns = {
        "pathing:actor_1": now - 100,  # Expired 100s ago
        "pathing:actor_2": now + 100,  # Still active
    }

    cleared = clear_expired_cooldowns(location, now)

    assert cleared == 1
    assert "pathing:actor_1" not in location.cooldowns
    assert "pathing:actor_2" in location.cooldowns


def test_clear_cooldowns_exact_time():
    """Cooldown at exact expiry time should be cleared."""
    location = create_test_location()
    now = time.time()

    location.cooldowns = {
        "pathing:actor_1": now,  # Expires exactly now
    }

    cleared = clear_expired_cooldowns(location, now)

    assert cleared == 1
    assert "pathing:actor_1" not in location.cooldowns


def test_saturation_decay():
    """Saturation should decrease over time when no events."""
    location = create_test_location()
    location.saturation.personal = 0.5

    # Decay for 10 days
    changed = decay_saturation(location, elapsed_days=10)

    assert changed is True
    assert location.saturation.personal < 0.5
    assert location.saturation.personal > 0.0  # Should not hit floor yet


def test_saturation_decay_all_channels():
    """Saturation decay should work on all channels."""
    location = create_test_location()
    location.saturation.personal = 0.5
    location.saturation.group = 0.6
    location.saturation.behavior = 0.4

    changed = decay_saturation(location, elapsed_days=10)

    assert changed is True
    assert location.saturation.personal < 0.5
    assert location.saturation.group < 0.6
    assert location.saturation.behavior < 0.4


def test_saturation_decay_no_change_at_floor():
    """Saturation at floor should not change."""
    location = create_test_location()
    location.saturation.personal = 0.0
    location.saturation.group = 0.0
    location.saturation.behavior = 0.0

    changed = decay_saturation(location, elapsed_days=10)

    assert changed is False


def test_world_tick_skips_if_too_soon():
    """Tick should be no-op if called too soon."""
    location = create_test_location()
    now = time.time()
    location.last_tick = now - 100  # 100 seconds ago (< 3600)

    report = world_tick(location, now)

    assert report.traces_pruned == 0
    assert report.cooldowns_cleared == 0
    assert report.saturation_decayed is False


def test_world_tick_updates_last_tick():
    """Tick should update last_tick timestamp."""
    location = create_test_location()
    location.last_tick = 0  # Very stale
    now = time.time()

    world_tick(location, now)

    assert location.last_tick == now


def test_world_tick_performs_cleanup():
    """Tick should perform all cleanup operations."""
    location = create_test_location()
    now = time.time()
    location.last_tick = 0  # Very stale

    # Add old trace
    location.personal_traces[("actor_1", "harm")] = TraceRecord(
        accumulated=0.001,
        last_updated=now - (90 * 86400),
        event_count=1
    )

    # Add expired cooldown
    location.cooldowns["pathing:actor_1"] = now - 100

    # Set saturation
    location.saturation.personal = 0.5

    report = world_tick(location, now)

    assert report.traces_pruned >= 1
    assert report.cooldowns_cleared >= 1
    assert report.saturation_decayed is True


def test_tick_report_structure():
    """TickReport should have all expected fields."""
    location = create_test_location()
    location.last_tick = 0

    report = world_tick(location)

    assert isinstance(report, TickReport)
    assert report.location_id == location.location_id
    assert isinstance(report.timestamp, float)
    assert isinstance(report.traces_pruned, int)
    assert isinstance(report.cooldowns_cleared, int)
    assert isinstance(report.saturation_decayed, bool)
    assert isinstance(report.time_since_last_tick, float)


def test_tick_deterministic_with_now():
    """Tick with explicit now parameter should be deterministic."""
    location1 = create_test_location()
    location1.last_tick = 1000.0

    location2 = create_test_location()
    location2.last_tick = 1000.0

    now = 10000.0

    report1 = world_tick(location1, now)
    report2 = world_tick(location2, now)

    assert report1.timestamp == report2.timestamp
    assert report1.time_since_last_tick == report2.time_since_last_tick


def test_repeated_tick_is_noop():
    """Calling tick twice in quick succession should be no-op."""
    location = create_test_location()
    location.last_tick = 0
    now = time.time()

    # First tick
    report1 = world_tick(location, now)
    assert report1.time_since_last_tick >= 3600

    # Second tick immediately after
    report2 = world_tick(location, now + 1)
    assert report2.time_since_last_tick < 3600
    assert report2.traces_pruned == 0
