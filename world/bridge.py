"""
Bridge between the affinity engine and the Evennia game layer.

Pure Python with no Evennia imports, so it can be tested with pytest.
typeclasses/ and commands/ call into this module; the engine in
world/affinity/ stays unaware of Evennia.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set

import yaml

from world.affinity.affordances import (
    AffordanceContext,
    AffordanceOutcome,
    evaluate_affordances,
)
from world.affinity.computation import compute_affinity, get_threshold_label
from world.affinity.config import load_event_intensity
from world.affinity.core import AffinityEvent, Location, SaturationState, TraceRecord
from world.affinity.events import log_event

LOCATIONS_DIR = Path(__file__).resolve().parent / "locations"

# Affordances asked about when someone leaves a room, and when they arrive
DEPART_AFFORDANCES: FrozenSet[str] = frozenset({"pathing", "misleading_navigation"})
ARRIVE_AFFORDANCES: FrozenSet[str] = frozenset(
    {"ambient_messaging", "weather_microclimate", "animal_messengers", "encounter_bias"}
)


@dataclass(frozen=True)
class Action:
    """A player verb that leaves a memory trace."""
    event_type: str
    affordances: FrozenSet[str]   # what the place may answer with afterwards
    self_msg: str
    room_msg: str                 # "{actor}" is replaced with the actor's name


ACTIONS: Dict[str, Action] = {
    "burn": Action(
        "harm.fire",
        frozenset({"ambient_messaging", "animal_messengers"}),
        "You set a fire in the undergrowth. Smoke curls up and drifts away.",
        "{actor} sets a fire in the undergrowth. Smoke curls up and drifts away.",
    ),
    "plant": Action(
        "create.plant",
        frozenset({"ambient_messaging", "weather_microclimate"}),
        "You press a seed into the soil and cover it carefully.",
        "{actor} kneels and plants something in the soil.",
    ),
    "offer": Action(
        "offer.gift",
        frozenset({"ambient_messaging", "animal_messengers"}),
        "You leave a small offering and step back.",
        "{actor} leaves a small offering.",
    ),
    "hunt": Action(
        "extract.hunt",
        frozenset({"resource_scarcity", "animal_messengers"}),
        "You stalk through the brush and bring down a small animal.",
        "{actor} returns from the brush carrying a kill.",
    ),
    "forage": Action(
        "extract.harvest",
        frozenset({"resource_scarcity", "loot_quality"}),
        "You search the ground for anything useful.",
        "{actor} searches the ground, gathering what they can.",
    ),
}

# Resting leaves no trace; the place only answers
REST_AFFORDANCES: FrozenSet[str] = frozenset({"rest_quality"})


# =============================================================================
# LOCATIONS
# =============================================================================

def load_location_spec(location_id: str) -> Dict[str, Any]:
    """Read world/locations/<location_id>.yaml."""
    path = LOCATIONS_DIR / f"{location_id}.yaml"
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if spec.get("location_id") != location_id:
        raise ValueError(f"{path} declares location_id {spec.get('location_id')!r}")
    return spec


def new_location(spec: Dict[str, Any]) -> Location:
    """Build an empty-memory Location from a location spec."""
    return Location(
        location_id=spec["location_id"],
        name=spec["name"],
        description=spec.get("description", "").strip(),
        valuation_profile=dict(spec.get("valuation_profile", {})),
    )


def _trace_to_state(trace: TraceRecord) -> List[Any]:
    return [trace.accumulated, trace.last_updated, trace.event_count, trace.is_scar]


def _trace_from_state(state: Iterable[Any]) -> TraceRecord:
    accumulated, last_updated, event_count, is_scar = list(state)
    return TraceRecord(accumulated, last_updated, event_count, is_scar)


def location_to_state(location: Location) -> Dict[str, Any]:
    """
    Serialize a Location's memory to plain lists/dicts for storage.

    Plain data (not a pickled Location) survives class renames and is safe
    to store in an Evennia Attribute. Configured affordances are not stored;
    they come from the engine config.
    """
    return {
        "location_id": location.location_id,
        "name": location.name,
        "description": location.description,
        "valuation_profile": dict(location.valuation_profile),
        "personal": [[a, e, _trace_to_state(t)] for (a, e), t in location.personal_traces.items()],
        "group": [[g, e, _trace_to_state(t)] for (g, e), t in location.group_traces.items()],
        "behavior": [[e, _trace_to_state(t)] for e, t in location.behavior_traces.items()],
        "saturation": [
            location.saturation.personal,
            location.saturation.group,
            location.saturation.behavior,
        ],
        "last_tick": location.last_tick,
        "cooldowns": dict(location.cooldowns),
    }


def location_from_state(state: Dict[str, Any]) -> Location:
    """Inverse of location_to_state."""
    location = Location(
        location_id=state["location_id"],
        name=state["name"],
        description=state["description"],
        valuation_profile=dict(state["valuation_profile"]),
        last_tick=state.get("last_tick", 0.0),
        cooldowns=dict(state.get("cooldowns", {})),
    )
    for actor_id, event_type, trace in state.get("personal", []):
        location.personal_traces[(actor_id, event_type)] = _trace_from_state(trace)
    for tag, event_type, trace in state.get("group", []):
        location.group_traces[(tag, event_type)] = _trace_from_state(trace)
    for event_type, trace in state.get("behavior", []):
        location.behavior_traces[event_type] = _trace_from_state(trace)
    personal, group, behavior = list(state.get("saturation", [0.0, 0.0, 0.0]))
    location.saturation = SaturationState(personal, group, behavior)
    return location


# =============================================================================
# ACTIONS AND RESPONSES
# =============================================================================

_INTENSITY: Optional[Dict[str, float]] = None


def typical_intensity(event_type: str) -> float:
    """Typical intensity for an event type, from config `event_intensity`."""
    global _INTENSITY
    if _INTENSITY is None:
        _INTENSITY = load_event_intensity()
    return _INTENSITY[event_type]


def perform(
    location: Location,
    actor_id: str,
    actor_tags: Set[str],
    verb: str,
    now: Optional[float] = None,
) -> AffordanceOutcome:
    """
    Record a player action in the location's memory, then let the place answer.

    Returns the outcome of evaluating the affordances relevant to the verb.
    """
    action = ACTIONS[verb]
    now = time.time() if now is None else now
    log_event(location, AffinityEvent(
        event_type=action.event_type,
        actor_id=actor_id,
        actor_tags=set(actor_tags),
        location_id=location.location_id,
        intensity=typical_intensity(action.event_type),
        timestamp=now,
    ))
    return respond(location, actor_id, actor_tags, verb, action.affordances, now=now)


def respond(
    location: Location,
    actor_id: str,
    actor_tags: Set[str],
    action_type: str,
    affordances: Iterable[str],
    *,
    adjacent_rooms: Optional[List[str]] = None,
    now: Optional[float] = None,
) -> AffordanceOutcome:
    """Evaluate a subset of affordances for an actor in a location."""
    return evaluate_affordances(AffordanceContext(
        actor_id=actor_id,
        actor_tags=set(actor_tags),
        location=location,
        action_type=action_type,
        action_target=None,
        timestamp=time.time() if now is None else now,
        adjacent_rooms=adjacent_rooms,
        affordances=set(affordances),
    ))


def travel_delay(outcome: AffordanceOutcome, travel_seconds: float) -> float:
    """
    Extra seconds a departure takes, from pathing's travel-time modifier.

    Only slowdowns delay; a favorable (negative) modifier is already as fast
    as moving gets in a text world, so it shows up through tells alone.
    """
    modifier = outcome.adjustments.get("room.travel_time_modifier", 0.0)
    return max(0.0, modifier) * travel_seconds


# =============================================================================
# ADMIN
# =============================================================================

def explain(
    location: Location,
    actor_id: str,
    actor_tags: Set[str],
    now: Optional[float] = None,
    limit: int = 5,
) -> List[str]:
    """Admin-only lines explaining how a place feels about an actor, and why."""
    from world.affinity.affordances import _compute_contributing_traces

    now = time.time() if now is None else now
    affinity = compute_affinity(location, actor_id, set(actor_tags), now)
    lines = [
        f"{location.name} toward {actor_id} {sorted(actor_tags)}: "
        f"{affinity:+.3f} ({get_threshold_label(affinity)})"
    ]
    contributions = _compute_contributing_traces(location, actor_id, set(actor_tags), now)
    if not contributions:
        lines.append("  no memories involving this actor")
    for c in contributions[:limit]:
        lines.append(
            f"  {c.channel:<8} {c.trace_key:<36} decayed={c.decayed_value:.2f} "
            f"x valuation={c.valuation:+.2f} -> {c.weighted_contribution:+.3f}"
        )
    return lines


def explain_outcome(outcome: AffordanceOutcome) -> List[str]:
    """Admin-only lines describing why an affordance did or did not trigger."""
    t = outcome.trace
    lines = [
        f"at {t.location_id}: affinity {t.computed_affinity:+.3f} ({t.threshold_crossed}), "
        f"triggered: {t.affordance_type}" + (f" -> {t.effect_applied}" if t.effect_applied else ""),
    ]
    if outcome.adjustments:
        lines.append("  adjustments: " + ", ".join(
            f"{k}={v:+.3f}" for k, v in outcome.adjustments.items()
        ))
    if outcome.redirect_target:
        lines.append(f"  redirected to {outcome.redirect_target}")
    for c in t.contributing_traces[:5]:
        lines.append(f"  {c.channel:<8} {c.trace_key:<36} {c.weighted_contribution:+.3f}")
    return lines


def age(location: Location, seconds: float) -> None:
    """
    Admin/testing: make every memory and cooldown `seconds` older.

    Lets you watch a place forgive (or forget) without waiting real days.
    """
    for trace in list(location.personal_traces.values()) + list(
        location.group_traces.values()
    ) + list(location.behavior_traces.values()):
        trace.last_updated -= seconds
    for key in location.cooldowns:
        location.cooldowns[key] -= seconds
