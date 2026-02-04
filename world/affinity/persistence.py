"""
Persistence layer for affinity runtime state.

Locations are split:
- YAML: Static definition (valuation, affordances)
- JSON: Runtime state (traces, saturation, cooldowns)

See docs/affinity_spec.md §8 for implementation checklist.
"""

import json
import time
from pathlib import Path
from typing import Dict, Tuple

from world.affinity.core import Location, TraceRecord, SaturationState, ScarEvent


# =============================================================================
# JSON ENCODING - Handle tuple keys and dataclasses
# =============================================================================

def _encode_trace_record(trace: TraceRecord) -> dict:
    """Convert TraceRecord to JSON-serializable dict."""
    return {
        "accumulated": trace.accumulated,
        "last_updated": trace.last_updated,
        "event_count": trace.event_count,
        "is_scar": trace.is_scar,
    }


def _decode_trace_record(data: dict) -> TraceRecord:
    """Reconstruct TraceRecord from JSON dict."""
    return TraceRecord(
        accumulated=data["accumulated"],
        last_updated=data["last_updated"],
        event_count=data["event_count"],
        is_scar=data.get("is_scar", False),
    )


def _encode_traces_with_tuple_keys(
    traces: Dict[Tuple[str, str], TraceRecord]
) -> Dict[str, dict]:
    """
    Encode dict with tuple keys to JSON.

    Tuple keys are not JSON-serializable.
    Convert (actor_id, event_type) to "actor_id::event_type".
    """
    return {
        f"{key[0]}::{key[1]}": _encode_trace_record(trace)
        for key, trace in traces.items()
    }


def _decode_traces_with_tuple_keys(
    data: Dict[str, dict]
) -> Dict[Tuple[str, str], TraceRecord]:
    """
    Decode JSON dict back to tuple-keyed dict.

    Split "actor_id::event_type" back to (actor_id, event_type).
    """
    result = {}
    for key_str, trace_data in data.items():
        parts = key_str.split("::", 1)  # maxsplit=1 in case event_type has ::
        if len(parts) != 2:
            raise ValueError(f"Invalid trace key format: {key_str}")
        key = (parts[0], parts[1])
        result[key] = _decode_trace_record(trace_data)
    return result


def _encode_behavior_traces(
    traces: Dict[str, TraceRecord]
) -> Dict[str, dict]:
    """Encode behavior traces (string keys, already JSON-safe)."""
    return {
        event_type: _encode_trace_record(trace)
        for event_type, trace in traces.items()
    }


def _decode_behavior_traces(
    data: Dict[str, dict]
) -> Dict[str, TraceRecord]:
    """Decode behavior traces."""
    return {
        event_type: _decode_trace_record(trace_data)
        for event_type, trace_data in data.items()
    }


# =============================================================================
# LOCATION STATE SERIALIZATION
# =============================================================================

def serialize_location_state(location: Location) -> dict:
    """
    Serialize location runtime state to JSON-compatible dict.

    Returns ONLY mutable state:
    - Traces (personal, group, behavior)
    - Saturation
    - Cooldowns
    - Last tick timestamp
    - Scars

    Does NOT include:
    - Static definition (name, description, valuation_profile, affordances)
    - Those come from YAML on load

    Args:
        location: Location to serialize

    Returns:
        JSON-serializable dict
    """
    return {
        "location_id": location.location_id,  # for validation
        "personal_traces": _encode_traces_with_tuple_keys(location.personal_traces),
        "group_traces": _encode_traces_with_tuple_keys(location.group_traces),
        "behavior_traces": _encode_behavior_traces(location.behavior_traces),
        "saturation": {
            "personal": location.saturation.personal,
            "group": location.saturation.group,
            "behavior": location.saturation.behavior,
        },
        "cooldowns": location.cooldowns,  # Already str → float
        "last_tick": location.last_tick,
        "scars": [
            {
                "event_type": scar.event_type,
                "actor_tags": list(scar.actor_tags),  # Set → List for JSON
                "intensity": scar.intensity,
                "timestamp": scar.timestamp,
                "half_life_seconds": scar.half_life_seconds,
            }
            for scar in location.scars
        ],
        "saved_at": time.time(),  # Metadata for debugging
    }


def deserialize_location_state(
    state_data: dict,
    location: Location
) -> None:
    """
    Load runtime state into an existing Location instance.

    Mutates the location in-place, updating:
    - personal_traces
    - group_traces
    - behavior_traces
    - saturation
    - cooldowns
    - last_tick

    Args:
        state_data: JSON dict from serialize_location_state()
        location: Location instance to update (already has YAML definition loaded)

    Raises:
        ValueError: If location_id mismatch
    """
    # Validation: ensure we're loading the right location
    if state_data.get("location_id") != location.location_id:
        raise ValueError(
            f"State mismatch: {state_data.get('location_id')} "
            f"!= {location.location_id}"
        )

    # Update traces
    location.personal_traces = _decode_traces_with_tuple_keys(
        state_data.get("personal_traces", {})
    )
    location.group_traces = _decode_traces_with_tuple_keys(
        state_data.get("group_traces", {})
    )
    location.behavior_traces = _decode_behavior_traces(
        state_data.get("behavior_traces", {})
    )

    # Update saturation
    sat_data = state_data.get("saturation", {})
    location.saturation = SaturationState(
        personal=sat_data.get("personal", 0.0),
        group=sat_data.get("group", 0.0),
        behavior=sat_data.get("behavior", 0.0),
    )

    # Update cooldowns and last_tick
    location.cooldowns = state_data.get("cooldowns", {})
    location.last_tick = state_data.get("last_tick", 0.0)

    # Update scars
    scars_data = state_data.get("scars", [])
    location.scars = [
        ScarEvent(
            event_type=scar_dict["event_type"],
            actor_tags=set(scar_dict["actor_tags"]),
            intensity=scar_dict["intensity"],
            timestamp=scar_dict["timestamp"],
            half_life_seconds=scar_dict["half_life_seconds"],
        )
        for scar_dict in scars_data
    ]


# =============================================================================
# FILE I/O
# =============================================================================

def save_location_state(location: Location, data_dir: str = "data/affinity/locations") -> None:
    """
    Save location runtime state to JSON file.

    Creates directory if it doesn't exist.
    Writes to: {data_dir}/{location_id}.json

    Args:
        location: Location to save
        data_dir: Directory for state files (relative to project root)
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    state_file = data_path / f"{location.location_id}.json"
    state_data = serialize_location_state(location)

    # Write atomically (write to temp, then rename)
    temp_file = state_file.with_suffix(".json.tmp")
    with open(temp_file, 'w') as f:
        json.dump(state_data, f, indent=2)

    temp_file.rename(state_file)


def load_location_state(
    location: Location,
    data_dir: str = "data/affinity/locations"
) -> bool:
    """
    Load location runtime state from JSON file if it exists.

    If state file doesn't exist, leaves location in initial state.

    Args:
        location: Location instance to load into (must have YAML definition loaded)
        data_dir: Directory for state files

    Returns:
        True if state was loaded, False if no state file found

    Raises:
        ValueError: If state file is corrupted or has mismatched location_id
    """
    data_path = Path(data_dir)
    state_file = data_path / f"{location.location_id}.json"

    if not state_file.exists():
        return False

    with open(state_file, 'r') as f:
        state_data = json.load(f)

    deserialize_location_state(state_data, location)
    return True
