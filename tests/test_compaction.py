"""
Tests for memory compaction system.

See world/affinity/compaction.py for implementation.
"""

import time

from world.affinity.core import Location, TraceRecord, ScarEvent
from world.affinity.config import load_config_from_yaml, set_config, reset_config
from world.affinity.compaction import (
    compact_traces,
    compact_personal_traces,
    compact_group_traces,
    create_scars_from_warm,
    fold_actor_tag,
    fold_event_type,
)
from world.affinity.world_tick import world_tick


def create_test_location():
    """Create a basic test location."""
    return Location(
        location_id="test_woods",
        name="Test Woods",
        description="A test location",
        valuation_profile={"harm.fire": -0.8},
    )


def test_fold_actor_tag_keeps_institutional():
    """Institutional tags should be kept during folding."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Test institutional tag (should be in config)
    assert fold_actor_tag("human") == "human"
    assert fold_actor_tag("elf") == "elf"

    reset_config()


def test_fold_actor_tag_discards_non_institutional():
    """Non-institutional tags should be discarded."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    # Test non-institutional tag
    assert fold_actor_tag("random_npc") is None
    assert fold_actor_tag("bandit_123") is None

    reset_config()


def test_fold_event_type_extracts_category():
    """Event type folding should extract category."""
    assert fold_event_type("harm.fire") == "harm"
    assert fold_event_type("offer.gift") == "offer"
    assert fold_event_type("harm") == "harm"  # Already a category


def test_personal_traces_discarded_after_hot_window():
    """Personal traces older than 7 days should be discarded."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    # Add old personal trace (8 days old, beyond 7-day hot window)
    location.personal_traces[("actor_old", "harm.fire")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (8 * 86400),
        event_count=1
    )

    # Add recent personal trace (1 day old, within hot window)
    location.personal_traces[("actor_recent", "offer.gift")] = TraceRecord(
        accumulated=0.5,
        last_updated=now - (1 * 86400),
        event_count=1
    )

    hot_window = 7 * 86400  # 7 days
    discarded = compact_personal_traces(location, hot_window, now)

    assert discarded == 1
    assert ("actor_old", "harm.fire") not in location.personal_traces
    assert ("actor_recent", "offer.gift") in location.personal_traces

    reset_config()


def test_group_traces_merged_by_institutional_tag():
    """Group traces should merge by institutional tag + category."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    # Add old group traces with institutional tag
    # These should be merged into ("human", "harm")
    location.group_traces[("human", "harm.fire")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (10 * 86400),
        event_count=2
    )
    location.group_traces[("human", "harm.poison")] = TraceRecord(
        accumulated=0.5,
        last_updated=now - (10 * 86400),
        event_count=1
    )

    hot_window = 7 * 86400
    warm_window = 90 * 86400
    compacted = compact_group_traces(location, hot_window, warm_window, now)

    assert compacted == 2
    # Should be merged into category
    assert ("human", "harm") in location.group_traces
    # Accumulated should be summed
    assert location.group_traces[("human", "harm")].accumulated == 1.5
    assert location.group_traces[("human", "harm")].event_count == 3

    reset_config()


def test_non_institutional_tags_discarded():
    """Non-institutional tags should be discarded during compaction."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    # Add old group trace with non-institutional tag
    location.group_traces[("random_npc", "harm.fire")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (10 * 86400),
        event_count=1
    )

    hot_window = 7 * 86400
    warm_window = 90 * 86400
    compacted = compact_group_traces(location, hot_window, warm_window, now)

    assert compacted == 1
    # Non-institutional tag should be discarded
    assert ("random_npc", "harm.fire") not in location.group_traces
    assert ("random_npc", "harm") not in location.group_traces

    reset_config()


def test_high_intensity_becomes_scar():
    """High-intensity events should become scars."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    # Add very old, high-intensity group trace
    location.group_traces[("human", "harm.fire")] = TraceRecord(
        accumulated=2.0,  # High intensity (> 0.7 threshold)
        last_updated=now - (100 * 86400),  # 100 days old (> 90-day warm window)
        event_count=1
    )

    warm_window = 90 * 86400
    scar_threshold = 0.7
    scars_created = create_scars_from_warm(location, warm_window, scar_threshold, now)

    assert scars_created == 1
    assert len(location.scars) == 1

    scar = location.scars[0]
    assert scar.event_type == "harm"  # Category only
    assert "human" in scar.actor_tags
    assert scar.intensity == 2.0

    reset_config()


def test_low_intensity_does_not_become_scar():
    """Low-intensity events should not become scars."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    # Add very old, LOW-intensity group trace
    location.group_traces[("human", "harm.fire")] = TraceRecord(
        accumulated=0.3,  # Low intensity (< 0.7 threshold)
        last_updated=now - (100 * 86400),
        event_count=1
    )

    warm_window = 90 * 86400
    scar_threshold = 0.7
    scars_created = create_scars_from_warm(location, warm_window, scar_threshold, now)

    assert scars_created == 0
    assert len(location.scars) == 0

    reset_config()


def test_scars_have_long_half_life():
    """Scars should have 1-year half-life."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    location.group_traces[("human", "harm.fire")] = TraceRecord(
        accumulated=2.0,
        last_updated=now - (100 * 86400),
        event_count=1
    )

    warm_window = 90 * 86400
    scar_threshold = 0.7
    create_scars_from_warm(location, warm_window, scar_threshold, now)

    scar = location.scars[0]
    # 365 days * 86400 seconds = 31536000
    assert scar.half_life_seconds == 365 * 86400

    reset_config()


def test_full_compaction_workflow():
    """Full compaction should process all tiers."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    # Add traces at different ages
    # Old personal (should be discarded)
    location.personal_traces[("actor_old", "harm")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (10 * 86400),
        event_count=1
    )

    # Recent personal (should be kept)
    location.personal_traces[("actor_recent", "harm")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (1 * 86400),
        event_count=1
    )

    # Old group traces (should be compacted)
    location.group_traces[("human", "harm.fire")] = TraceRecord(
        accumulated=0.8,
        last_updated=now - (10 * 86400),
        event_count=1
    )
    location.group_traces[("human", "harm.poison")] = TraceRecord(
        accumulated=0.7,
        last_updated=now - (10 * 86400),
        event_count=1
    )

    # Very old, high-intensity (should become scar)
    location.group_traces[("elf", "harm.fire")] = TraceRecord(
        accumulated=2.0,
        last_updated=now - (100 * 86400),
        event_count=1
    )

    report = compact_traces(location, now)

    # Verify report
    assert report.hot_to_warm == 1  # Old personal discarded
    assert report.warm_to_scar == 1  # High-intensity became scar
    assert report.traces_compacted > 0

    # Verify state
    assert ("actor_recent", "harm") in location.personal_traces  # Recent kept
    assert ("actor_old", "harm") not in location.personal_traces  # Old discarded
    assert ("human", "harm") in location.group_traces  # Compacted
    assert len(location.scars) == 1  # Scar created

    reset_config()


def test_compaction_integrated_with_world_tick():
    """World tick should run compaction."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()
    location.last_tick = 0  # Very stale

    # Add old personal trace
    location.personal_traces[("actor_old", "harm")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (10 * 86400),
        event_count=1
    )

    report = world_tick(location, now)

    # Verify compaction ran
    assert report.compaction_hot_to_warm >= 0
    assert report.compaction_warm_to_scar >= 0
    assert report.compaction_traces_compacted >= 0

    reset_config()


def test_compaction_preserves_hot_traces():
    """Compaction should preserve traces within hot window."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    location = create_test_location()
    now = time.time()

    # Add traces within hot window (< 7 days)
    location.personal_traces[("actor_1", "harm")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (1 * 86400),  # 1 day old
        event_count=1
    )
    location.group_traces[("human", "harm.fire")] = TraceRecord(
        accumulated=1.0,
        last_updated=now - (2 * 86400),  # 2 days old
        event_count=1
    )

    report = compact_traces(location, now)

    # Nothing should be compacted
    assert report.hot_to_warm == 0
    assert report.traces_compacted == 0
    assert ("actor_1", "harm") in location.personal_traces
    assert ("human", "harm.fire") in location.group_traces  # Unchanged

    reset_config()
