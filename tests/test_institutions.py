"""
Tests for institution drift system.

See world/affinity/institutions.py for implementation.
"""

import time

from world.affinity.core import Institution, Location, AffinityEvent, TraceRecord
from world.affinity.config import load_config_from_yaml, set_config, reset_config
from world.affinity.events import log_event
from world.affinity.institutions import (
    update_institution,
    query_institution_stance,
    should_refresh_institution,
    query_constituent_affinity,
    compute_institutional_memory_decay,
)


def create_test_institution():
    """Create a basic test institution."""
    return Institution(
        institution_id="elven_culture",
        name="Elven Culture",
        description="Distributed pattern of elven traditions",
        affiliated_tags={"elf", "forest"},
    )


def create_test_location_with_affinity():
    """Create a location with some affinity."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = Location(
        location_id="forest",
        name="Forest",
        description="An elven forest",
        valuation_profile={"harm.fire": -0.8},
    )

    now = time.time()

    # Add some traces to create affinity
    event = AffinityEvent(
        event_type="harm.fire",
        actor_id="human_warrior",
        actor_tags={"human"},
        location_id="forest",
        intensity=0.5,
        timestamp=now,
    )
    log_event(location, event)

    reset_config()
    return location


def test_institution_creation():
    """Institution should be created with default values."""
    institution = create_test_institution()

    assert institution.institution_id == "elven_culture"
    assert institution.drift_rate == 0.1
    assert institution.inertia == 0.9
    assert len(institution.cached_stance) == 0
    assert institution.last_computed == 0.0


def test_query_constituent_affinity():
    """Should compute average affinity from constituents."""
    institution = create_test_institution()
    location = create_test_location_with_affinity()
    now = time.time()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    affinity = query_constituent_affinity(
        institution,
        [location],
        "human",
        now
    )

    # Should have negative affinity due to harm event
    assert affinity < 0
    assert -1.0 <= affinity <= 1.0

    reset_config()


def test_update_institution_drifts_slowly():
    """Institution should drift slowly toward constituent affinity."""
    institution = create_test_institution()
    location = create_test_location_with_affinity()
    now = time.time()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Set initial cached stance
    institution.cached_stance["human"] = 0.5  # Positive

    # Update institution (constituent has negative affinity)
    update_institution(institution, [location], {"human"}, now)

    # After one update, should drift toward negative but not fully
    new_stance = institution.cached_stance["human"]

    # Should move toward negative (constituent affinity)
    assert new_stance < 0.5
    # But not all the way (due to inertia)
    assert new_stance > -1.0

    reset_config()


def test_multiple_updates_converge():
    """Multiple updates should slowly converge to constituent affinity."""
    institution = create_test_institution()
    location = create_test_location_with_affinity()
    now = time.time()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Set initial cached stance far from constituent
    institution.cached_stance["human"] = 0.9

    stances = [institution.cached_stance["human"]]

    # Update 10 times
    for i in range(10):
        update_institution(institution, [location], {"human"}, now)
        stances.append(institution.cached_stance["human"])

    # Should gradually drift toward constituent affinity
    # Each update should move closer
    for i in range(len(stances) - 1):
        # Stance should be decreasing (moving toward negative)
        assert stances[i] >= stances[i + 1]

    reset_config()


def test_inertia_resists_rapid_change():
    """High inertia should resist rapid changes."""
    institution = Institution(
        institution_id="test",
        name="Test",
        description="Test",
        drift_rate=0.1,
        inertia=0.9,  # High inertia
    )

    location = create_test_location_with_affinity()
    now = time.time()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Set cached stance
    initial_stance = 0.5
    institution.cached_stance["human"] = initial_stance

    # Single update
    update_institution(institution, [location], {"human"}, now)

    # Change should be small due to high inertia
    change = abs(institution.cached_stance["human"] - initial_stance)
    assert change < 0.2  # Less than 20% change in single update

    reset_config()


def test_query_institution_stance():
    """Should return cached stance for target."""
    institution = create_test_institution()
    institution.cached_stance["human"] = -0.3
    institution.cached_stance["dwarf"] = 0.2

    assert query_institution_stance(institution, "human") == -0.3
    assert query_institution_stance(institution, "dwarf") == 0.2


def test_query_unknown_stance_returns_zero():
    """Query for unknown tag should return 0."""
    institution = create_test_institution()

    stance = query_institution_stance(institution, "unknown")

    assert stance == 0.0


def test_should_refresh_institution():
    """Should refresh when enough time has passed."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    institution = create_test_institution()
    now = time.time()

    # Just computed
    institution.last_computed = now
    assert should_refresh_institution(institution, now) is False

    # One day later (default refresh interval)
    one_day_later = now + 86400
    assert should_refresh_institution(institution, one_day_later) is True

    reset_config()


def test_institutional_memory_decay():
    """Institutional memory should decay slowly."""
    institution = create_test_institution()
    institution.cached_stance["human"] = 1.0

    # Decay for 45 days (half of 90-day half-life)
    compute_institutional_memory_decay(institution, elapsed_days=45)

    # After half a half-life, should be at ~0.707 (sqrt(0.5))
    assert 0.6 < institution.cached_stance["human"] < 0.8


def test_institutional_memory_decays_all_stances():
    """Decay should affect all cached stances."""
    institution = create_test_institution()
    institution.cached_stance["human"] = 1.0
    institution.cached_stance["elf"] = -0.5
    institution.cached_stance["dwarf"] = 0.3

    compute_institutional_memory_decay(institution, elapsed_days=90)

    # After one half-life, all should be at ~50%
    assert 0.4 < institution.cached_stance["human"] < 0.6
    assert -0.3 < institution.cached_stance["elf"] < -0.2
    assert 0.1 < institution.cached_stance["dwarf"] < 0.2


def test_institution_with_multiple_locations():
    """Should average affinity from multiple locations."""
    institution = create_test_institution()
    now = time.time()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Create two locations with different affinities
    location1 = Location(
        location_id="forest1",
        name="Forest 1",
        description="First forest",
    )
    location1.group_traces[("human", "harm")] = TraceRecord(
        accumulated=-1.0,  # Negative
        last_updated=now,
        event_count=1
    )

    location2 = Location(
        location_id="forest2",
        name="Forest 2",
        description="Second forest",
    )
    location2.group_traces[("human", "offer")] = TraceRecord(
        accumulated=1.0,  # Positive
        last_updated=now,
        event_count=1
    )

    # Query should average both
    avg_affinity = query_constituent_affinity(
        institution,
        [location1, location2],
        "human",
        now
    )

    # Should be somewhere between negative and positive
    assert -1.0 < avg_affinity < 1.0

    reset_config()


def test_update_institution_updates_last_computed():
    """Update should set last_computed timestamp."""
    institution = create_test_institution()
    location = create_test_location_with_affinity()
    now = time.time()

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    update_institution(institution, [location], {"human"}, now)

    assert institution.last_computed == now

    reset_config()
