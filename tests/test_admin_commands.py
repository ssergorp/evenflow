"""
Tests for admin debugging commands.

See world/affinity/admin_commands.py for implementation.
"""

import time

from world.affinity.core import Location, AffinityEvent, TraceRecord, AffordanceTriggerLog
from world.affinity.config import load_config_from_yaml, set_config, reset_config
from world.affinity.events import log_event
from world.affinity.admin_commands import (
    cmd_affinity_inspect,
    cmd_affinity_why,
    cmd_affinity_replay,
    cmd_affinity_history,
    cmd_affinity_summary,
    get_top_contributing_traces,
)


def create_test_location_with_events():
    """Create a location with some events."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = Location(
        location_id="test_woods",
        name="Test Woods",
        description="A test location",
        valuation_profile={"harm.fire": -0.8, "offer.gift": 0.5},
    )

    now = time.time()

    # Add some events
    event1 = AffinityEvent(
        event_type="harm.fire",
        actor_id="actor_1",
        actor_tags={"human"},
        location_id="test_woods",
        intensity=0.5,
        timestamp=now,
    )
    log_event(location, event1)

    event2 = AffinityEvent(
        event_type="offer.gift",
        actor_id="actor_1",
        actor_tags={"human"},
        location_id="test_woods",
        intensity=0.3,
        timestamp=now,
    )
    log_event(location, event2)

    reset_config()
    return location


def test_affinity_inspect_shows_top_traces():
    """Inspect command should show top contributing traces."""
    location = create_test_location_with_events()
    now = time.time()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    output = cmd_affinity_inspect(location, "actor_1", {"human"}, now)

    # Should contain location info
    assert "Test Woods" in output
    assert "actor_1" in output

    # Should contain affinity value
    assert "Affinity:" in output

    # Should show traces
    assert "Top Contributing Traces:" in output

    reset_config()


def test_affinity_why_explains_trigger():
    """Why command should explain affordance trigger."""
    trigger_log = AffordanceTriggerLog(
        location_id="test_woods",
        affordance_type="pathing",
        actor_id="actor_1",
        actor_tags={"human"},
        timestamp=time.time(),
        raw_affinity=-0.5,
        normalized_affinity=-0.48,
        threshold_band="unwelcoming",
        top_traces=[
            ("personal:actor_1:harm.fire", -0.3),
            ("group:human:harm", -0.2),
        ],
    )

    output = cmd_affinity_why(trigger_log)

    # Should explain trigger
    assert "pathing" in output
    assert "actor_1" in output
    assert "-0.48" in output  # normalized affinity
    assert "unwelcoming" in output

    # Should show contributing traces
    assert "harm.fire" in output


def test_affinity_replay_shows_snapshot_info():
    """Replay command should show snapshot information."""
    trigger_log = AffordanceTriggerLog(
        location_id="test_woods",
        affordance_type="pathing",
        actor_id="actor_1",
        actor_tags={"human"},
        timestamp=time.time(),
        raw_affinity=-0.5,
        normalized_affinity=-0.48,
        threshold_band="unwelcoming",
        snapshot={"location_id": "test_woods", "traces": {}},
    )

    output = cmd_affinity_replay(trigger_log)

    # Should show original affinity
    assert "-0.48" in output

    # Should indicate snapshot available
    assert "Snapshot available: Yes" in output


def test_affinity_history_shows_personal_traces():
    """History command should show personal event history."""
    location = create_test_location_with_events()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    output = cmd_affinity_history(location, "actor_1", limit=10)

    # Should show actor info
    assert "actor_1" in output

    # Should show event types
    assert "harm.fire" in output or "offer.gift" in output

    reset_config()


def test_affinity_summary_shows_stats():
    """Summary command should show location statistics."""
    location = create_test_location_with_events()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    output = cmd_affinity_summary(location)

    # Should show location info
    assert "Test Woods" in output

    # Should show trace counts
    assert "Trace Counts:" in output
    assert "Personal:" in output

    # Should show saturation
    assert "Saturation:" in output

    reset_config()


def test_get_top_contributing_traces():
    """Should return top traces by absolute value."""
    location = Location(
        location_id="test",
        name="Test",
        description="Test",
    )

    now = time.time()

    # Add traces with different values
    location.personal_traces[("actor_1", "harm")] = TraceRecord(
        accumulated=-0.5,
        last_updated=now,
        event_count=1
    )
    location.personal_traces[("actor_1", "offer")] = TraceRecord(
        accumulated=0.3,
        last_updated=now,
        event_count=1
    )
    location.group_traces[("human", "harm")] = TraceRecord(
        accumulated=-0.8,  # Largest absolute value
        last_updated=now,
        event_count=1
    )

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    top_traces = get_top_contributing_traces(location, "actor_1", {"human"}, n=5, now=now)

    # Should have traces
    assert len(top_traces) > 0

    # First should be largest absolute value
    assert "harm" in top_traces[0][0]

    reset_config()


def test_inspect_with_no_traces():
    """Inspect should handle locations with no traces."""
    location = Location(
        location_id="empty",
        name="Empty Location",
        description="No traces",
    )

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    output = cmd_affinity_inspect(location, "actor_1", {"human"}, time.time())

    # Should not crash
    assert "Empty Location" in output
    assert "no traces" in output.lower()

    reset_config()


def test_why_with_empty_traces():
    """Why command should handle empty trace list."""
    trigger_log = AffordanceTriggerLog(
        location_id="test",
        affordance_type="pathing",
        actor_id="actor_1",
        actor_tags={"human"},
        timestamp=time.time(),
        raw_affinity=0.0,
        normalized_affinity=0.0,
        threshold_band="neutral",
        top_traces=[],  # Empty
    )

    output = cmd_affinity_why(trigger_log)

    # Should not crash
    assert "pathing" in output
    assert "no trace data" in output.lower() or "Contributing Traces:" in output


def test_summary_shows_scars():
    """Summary should show scar count."""
    location = create_test_location_with_events()

    # Add a scar
    from world.affinity.core import ScarEvent
    location.scars.append(
        ScarEvent(
            event_type="harm",
            actor_tags={"human"},
            intensity=0.9,
            timestamp=time.time(),
            half_life_seconds=365 * 86400,
        )
    )

    output = cmd_affinity_summary(location)

    assert "Scars:" in output
    assert "1" in output
