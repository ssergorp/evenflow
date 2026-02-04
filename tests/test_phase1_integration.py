"""
Phase 1 integration tests.

Tests the full lifecycle: config → events → tick → save → load
"""

import tempfile
import time

from world.affinity.core import Location, AffinityEvent
from world.affinity.config import load_config_from_yaml, set_config, reset_config
from world.affinity.events import log_event
from world.affinity.computation import compute_affinity
from world.affinity.world_tick import world_tick
from world.affinity.persistence import save_location_state, load_location_state


def test_phase1_full_lifecycle():
    """
    Full lifecycle: config → events → tick → save → load.

    This test verifies that all Phase 1 components work together:
    1. Config loader loads YAML
    2. Events can be logged to a location
    3. World tick prunes old traces
    4. Persistence saves and loads state correctly
    5. Affinity values are preserved through save/load
    """
    # Step 1: Load config from YAML
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Step 2: Create location
    location = Location(
        location_id="test_woods",
        name="Test Woods",
        description="Test location",
        valuation_profile={"harm.fire": -0.8, "offer.gift": 0.5},
    )

    # Step 3: Log some events
    now = time.time()

    # Recent event (should not be pruned)
    recent_event = AffinityEvent(
        event_type="harm.fire",
        actor_id="actor_recent",
        actor_tags={"human"},
        location_id="test_woods",
        intensity=0.5,
        timestamp=now - (1 * 86400),  # 1 day ago
    )
    log_event(location, recent_event)

    # Old event (should be pruned by tick)
    old_event = AffinityEvent(
        event_type="harm.fire",
        actor_id="actor_old",
        actor_tags={"human"},
        location_id="test_woods",
        intensity=0.01,  # Low intensity
        timestamp=now - (90 * 86400),  # 90 days ago
    )
    log_event(location, old_event)

    # Step 4: Compute affinity before tick
    affinity_before = compute_affinity(
        location,
        actor_id="actor_recent",
        actor_tags={"human"},
        now=now
    )

    # Step 5: World tick (should prune old trace)
    location.last_tick = 0  # Make it stale enough to tick
    report = world_tick(location, now)

    assert report.traces_pruned > 0, "Tick should have pruned old traces"

    # Step 6: Save state to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        save_location_state(location, data_dir=tmpdir)

        # Step 7: Load into fresh location
        location2 = Location(
            location_id="test_woods",
            name="Test Woods",
            description="Test location",
            valuation_profile={"harm.fire": -0.8, "offer.gift": 0.5},
        )

        loaded = load_location_state(location2, data_dir=tmpdir)
        assert loaded is True, "State should be loaded successfully"

        # Step 8: Verify state preserved
        assert location2.last_tick == location.last_tick, "last_tick should match"
        assert len(location2.personal_traces) == len(location.personal_traces), \
            "Personal traces count should match"

        # Step 9: Compute affinity after load
        affinity_after = compute_affinity(
            location2,
            actor_id="actor_recent",
            actor_tags={"human"},
            now=now
        )

        # Affinity should be approximately the same
        # (small differences due to floating point, but should be very close)
        assert abs(affinity_after - affinity_before) < 0.001, \
            f"Affinity should be preserved (before: {affinity_before}, after: {affinity_after})"

    # Cleanup
    reset_config()


def test_config_affects_tick_behavior():
    """
    Config settings should affect tick behavior.

    Verifies that prune_threshold from config is used.
    """
    # Load config
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Create location with trace
    location = Location(
        location_id="test",
        name="Test",
        description="Test",
    )

    now = time.time()

    # Add trace that should be pruned based on config threshold
    location.personal_traces[("actor", "harm")] = {
        "accumulated": 0.001,  # Below default threshold of 0.01
        "last_updated": now - (90 * 86400),
        "event_count": 1,
        "is_scar": False,
    }

    from world.affinity.core import TraceRecord
    location.personal_traces[("actor", "harm")] = TraceRecord(
        accumulated=0.001,
        last_updated=now - (90 * 86400),
        event_count=1,
        is_scar=False,
    )

    # Tick should use config threshold
    location.last_tick = 0
    report = world_tick(location, now)

    # Verify prune threshold from config was applied
    assert config.compaction.prune_threshold == 0.01
    assert report.traces_pruned >= 1

    # Cleanup
    reset_config()


def test_multiple_locations_independent():
    """
    Multiple locations should have independent state.

    Verifies that saving/loading one location doesn't affect another.
    """
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Create two locations
    location1 = Location(
        location_id="woods_a",
        name="Woods A",
        description="First woods",
    )
    location2 = Location(
        location_id="woods_b",
        name="Woods B",
        description="Second woods",
    )

    # Add different events to each
    now = time.time()

    event1 = AffinityEvent(
        event_type="harm.fire",
        actor_id="actor_1",
        actor_tags={"human"},
        location_id="woods_a",
        intensity=0.5,
        timestamp=now,
    )
    log_event(location1, event1)

    event2 = AffinityEvent(
        event_type="offer.gift",
        actor_id="actor_2",
        actor_tags={"elf"},
        location_id="woods_b",
        intensity=0.3,
        timestamp=now,
    )
    log_event(location2, event2)

    # Save both to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        save_location_state(location1, data_dir=tmpdir)
        save_location_state(location2, data_dir=tmpdir)

        # Load into fresh locations
        fresh1 = Location(location_id="woods_a", name="Woods A", description="First woods")
        fresh2 = Location(location_id="woods_b", name="Woods B", description="Second woods")

        load_location_state(fresh1, data_dir=tmpdir)
        load_location_state(fresh2, data_dir=tmpdir)

        # Verify independence
        assert len(fresh1.personal_traces) > 0
        assert len(fresh2.personal_traces) > 0

        # Check that traces are different
        assert ("actor_1", "harm.fire") in fresh1.personal_traces
        assert ("actor_2", "offer.gift") in fresh2.personal_traces
        assert ("actor_1", "harm.fire") not in fresh2.personal_traces
        assert ("actor_2", "offer.gift") not in fresh1.personal_traces

    # Cleanup
    reset_config()


def test_tick_then_save_then_load():
    """
    Ticking should affect saved state.

    Verifies that tick modifications are persisted.
    """
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = Location(
        location_id="test",
        name="Test",
        description="Test",
    )

    now = time.time()

    # Add saturation
    location.saturation.personal = 0.8

    # Tick with enough elapsed time to decay saturation
    location.last_tick = now - (10 * 86400)  # 10 days ago
    report = world_tick(location, now)

    assert report.saturation_decayed is True
    assert location.saturation.personal < 0.8

    # Save
    with tempfile.TemporaryDirectory() as tmpdir:
        save_location_state(location, data_dir=tmpdir)

        # Load
        fresh = Location(location_id="test", name="Test", description="Test")
        load_location_state(fresh, data_dir=tmpdir)

        # Verify saturation was saved
        assert fresh.saturation.personal == location.saturation.personal

    # Cleanup
    reset_config()
