"""
Tests for persistence layer.

See world/affinity/persistence.py for implementation.
"""

import json
import tempfile
import time
from pathlib import Path

from world.affinity.core import Location, TraceRecord, SaturationState
from world.affinity.persistence import (
    serialize_location_state,
    deserialize_location_state,
    save_location_state,
    load_location_state,
    _encode_trace_record,
    _decode_trace_record,
    _encode_traces_with_tuple_keys,
    _decode_traces_with_tuple_keys,
)


def create_test_location_with_traces():
    """Create a location with some trace data for testing."""
    location = Location(
        location_id="test_woods",
        name="Test Woods",
        description="A test location",
        valuation_profile={"harm.fire": -0.8, "offer.gift": 0.5},
    )

    # Add some personal traces
    location.personal_traces[("actor_123", "harm.fire")] = TraceRecord(
        accumulated=1.5,
        last_updated=1000.0,
        event_count=3,
        is_scar=False,
    )
    location.personal_traces[("actor_456", "offer.gift")] = TraceRecord(
        accumulated=0.8,
        last_updated=2000.0,
        event_count=1,
        is_scar=False,
    )

    # Add some group traces
    location.group_traces[("human", "harm.fire")] = TraceRecord(
        accumulated=2.0,
        last_updated=1500.0,
        event_count=5,
        is_scar=True,
    )

    # Add some behavior traces
    location.behavior_traces["harm.fire"] = TraceRecord(
        accumulated=3.0,
        last_updated=1800.0,
        event_count=10,
        is_scar=False,
    )

    # Set saturation
    location.saturation = SaturationState(
        personal=0.3,
        group=0.5,
        behavior=0.2,
    )

    # Set cooldowns
    location.cooldowns = {
        "pathing:actor_123": 5000.0,
        "encounter:actor_456": 6000.0,
    }

    # Set last_tick
    location.last_tick = 4000.0

    return location


def test_encode_decode_trace_record():
    """TraceRecord should encode and decode correctly."""
    original = TraceRecord(
        accumulated=1.5,
        last_updated=1000.0,
        event_count=3,
        is_scar=True,
    )

    encoded = _encode_trace_record(original)
    decoded = _decode_trace_record(encoded)

    assert decoded.accumulated == original.accumulated
    assert decoded.last_updated == original.last_updated
    assert decoded.event_count == original.event_count
    assert decoded.is_scar == original.is_scar


def test_tuple_key_encoding():
    """Tuple keys should encode/decode correctly."""
    traces = {
        ("actor_123", "harm.fire"): TraceRecord(1.0, 1000.0, 1),
        ("actor_456", "offer.gift"): TraceRecord(0.5, 2000.0, 2),
    }

    encoded = _encode_traces_with_tuple_keys(traces)
    decoded = _decode_traces_with_tuple_keys(encoded)

    assert decoded == traces
    assert ("actor_123", "harm.fire") in decoded
    assert decoded[("actor_123", "harm.fire")].accumulated == 1.0


def test_event_type_with_double_colon():
    """Event types containing :: should not break encoding."""
    traces = {
        ("actor_123", "custom::event::type"): TraceRecord(1.0, 1000.0, 1),
    }

    encoded = _encode_traces_with_tuple_keys(traces)
    decoded = _decode_traces_with_tuple_keys(encoded)

    assert decoded == traces
    assert ("actor_123", "custom::event::type") in decoded


def test_serialize_deserialize_round_trip():
    """Serialization round-trip should preserve all data."""
    original = create_test_location_with_traces()

    # Serialize
    state_data = serialize_location_state(original)

    # Create fresh location with same ID
    fresh = Location(
        location_id=original.location_id,
        name=original.name,
        description=original.description,
        valuation_profile=original.valuation_profile,
    )

    # Deserialize
    deserialize_location_state(state_data, fresh)

    # Verify traces match
    assert fresh.personal_traces == original.personal_traces
    assert fresh.group_traces == original.group_traces
    assert fresh.behavior_traces == original.behavior_traces

    # Verify saturation matches
    assert fresh.saturation.personal == original.saturation.personal
    assert fresh.saturation.group == original.saturation.group
    assert fresh.saturation.behavior == original.saturation.behavior

    # Verify cooldowns match
    assert fresh.cooldowns == original.cooldowns

    # Verify last_tick matches
    assert fresh.last_tick == original.last_tick


def test_serialize_includes_location_id():
    """Serialized state should include location_id for validation."""
    location = Location(
        location_id="test_woods",
        name="Test Woods",
        description="Test",
    )

    state_data = serialize_location_state(location)

    assert "location_id" in state_data
    assert state_data["location_id"] == "test_woods"


def test_serialize_includes_saved_at():
    """Serialized state should include saved_at timestamp."""
    location = Location(
        location_id="test_woods",
        name="Test Woods",
        description="Test",
    )

    before = time.time()
    state_data = serialize_location_state(location)
    after = time.time()

    assert "saved_at" in state_data
    assert before <= state_data["saved_at"] <= after


def test_deserialize_location_id_mismatch_raises():
    """Deserializing into wrong location should raise."""
    state_data = {
        "location_id": "woods_a",
        "personal_traces": {},
        "group_traces": {},
        "behavior_traces": {},
        "saturation": {"personal": 0.0, "group": 0.0, "behavior": 0.0},
        "cooldowns": {},
        "last_tick": 0.0,
    }

    location = Location(
        location_id="woods_b",
        name="Woods B",
        description="Different location",
    )

    try:
        deserialize_location_state(state_data, location)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "State mismatch" in str(e)


def test_save_creates_directory():
    """Save should create data directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        location = Location(
            location_id="test",
            name="Test",
            description="Test",
        )

        data_dir = f"{tmpdir}/nested/path"
        save_location_state(location, data_dir=data_dir)

        assert Path(f"{data_dir}/test.json").exists()


def test_save_load_round_trip():
    """Save and load should preserve location state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original = create_test_location_with_traces()

        # Save
        save_location_state(original, data_dir=tmpdir)

        # Load into fresh location
        fresh = Location(
            location_id=original.location_id,
            name=original.name,
            description=original.description,
            valuation_profile=original.valuation_profile,
        )

        loaded = load_location_state(fresh, data_dir=tmpdir)

        assert loaded is True
        assert fresh.personal_traces == original.personal_traces
        assert fresh.saturation.personal == original.saturation.personal
        assert fresh.last_tick == original.last_tick


def test_load_nonexistent_file():
    """Loading nonexistent state should return False, not error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        location = Location(
            location_id="test",
            name="Test",
            description="Test",
        )

        result = load_location_state(location, data_dir=tmpdir)

        assert result is False


def test_atomic_write():
    """Save should use atomic write (temp file + rename)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        location = Location(
            location_id="test",
            name="Test",
            description="Test",
        )

        save_location_state(location, data_dir=tmpdir)

        # Temp file should be cleaned up
        temp_files = list(Path(tmpdir).glob("*.tmp"))
        assert len(temp_files) == 0

        # Final file should exist
        final_file = Path(tmpdir) / "test.json"
        assert final_file.exists()


def test_saved_json_is_valid():
    """Saved JSON should be valid and readable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        location = create_test_location_with_traces()

        save_location_state(location, data_dir=tmpdir)

        # Read the JSON file directly
        json_file = Path(tmpdir) / f"{location.location_id}.json"
        with open(json_file, 'r') as f:
            data = json.load(f)

        assert data["location_id"] == location.location_id
        assert "personal_traces" in data
        assert "saturation" in data


def test_empty_location_serialization():
    """Empty location (no traces) should serialize correctly."""
    location = Location(
        location_id="empty",
        name="Empty",
        description="No traces",
    )

    state_data = serialize_location_state(location)

    assert state_data["personal_traces"] == {}
    assert state_data["group_traces"] == {}
    assert state_data["behavior_traces"] == {}
    assert state_data["cooldowns"] == {}
