"""
Tests for world/bridge.py, the engine <-> Evennia glue.

These run without Evennia: the bridge is plain Python by design.
"""

import pytest

from world import bridge
from world.affinity.affordances import AFFORDANCE_DEFAULTS, AffordanceContext, evaluate_affordances
from world.affinity.computation import compute_affinity
from world.affinity.config import load_event_intensity, reset_config
from world.affinity.core import AffinityEvent
from world.affinity.events import log_event

from tests.helpers import deterministic_affordance

NOW = 1_700_000_000.0
TAGS = {"human", "outsider"}
LOCATION_IDS = ["hollowmere", "forest_edge", "whispering_woods", "old_grove", "riverbank"]


@pytest.fixture(autouse=True)
def _config():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def woods():
    return bridge.new_location(bridge.load_location_spec("whispering_woods"))


class TestLocationFiles:
    """Every starter location file loads and uses known event types."""

    @pytest.mark.parametrize("location_id", LOCATION_IDS)
    def test_spec_loads(self, location_id):
        spec = bridge.load_location_spec(location_id)
        assert spec["name"]
        assert spec["valuation_profile"]
        assert spec["travel_seconds"] >= 0

    @pytest.mark.parametrize("location_id", LOCATION_IDS)
    def test_valuations_use_known_event_types(self, location_id):
        known = set(load_event_intensity())
        categories = {key.split(".")[0] for key in known}
        for key in bridge.load_location_spec(location_id)["valuation_profile"]:
            assert key in known or key in categories, f"{location_id}: unknown event type {key}"

    def test_every_action_has_an_intensity(self):
        for action in bridge.ACTIONS.values():
            assert bridge.typical_intensity(action.event_type) > 0


class TestStateRoundTrip:
    """Memory survives serialization to plain data."""

    def test_round_trip(self, woods):
        bridge.perform(woods, "#1", TAGS, "burn", now=NOW)
        bridge.perform(woods, "#1", TAGS, "offer", now=NOW + 1)
        woods.cooldowns["pathing:#1:whispering_woods"] = NOW + 3600

        state = bridge.location_to_state(woods)
        restored = bridge.location_from_state(state)

        assert bridge.location_to_state(restored) == state
        assert compute_affinity(restored, "#1", TAGS, NOW + 2) == compute_affinity(woods, "#1", TAGS, NOW + 2)


class TestPerform:
    """Actions accumulate memory in the room."""

    def test_repeated_fires_turn_the_woods(self, woods):
        for i in range(8):
            bridge.perform(woods, "#1", TAGS, "burn", now=NOW + i)
        hostile_threshold = AFFORDANCE_DEFAULTS["pathing"]["hostile_threshold"]
        assert compute_affinity(woods, "#1", TAGS, NOW + 8) < hostile_threshold

    def test_group_memory_reaches_strangers_with_same_tags(self, woods):
        for i in range(8):
            bridge.perform(woods, "#1", TAGS, "burn", now=NOW + i)
        assert compute_affinity(woods, "#99", TAGS, NOW + 8) < 0
        assert compute_affinity(woods, "#99", {"elf"}, NOW + 8) > compute_affinity(woods, "#99", TAGS, NOW + 8)

    def test_age_lets_a_place_forgive(self, woods):
        for i in range(8):
            bridge.perform(woods, "#1", TAGS, "burn", now=NOW + i)
        before = compute_affinity(woods, "#1", TAGS, NOW + 8)
        bridge.age(woods, 30 * 86400)
        assert before < compute_affinity(woods, "#1", TAGS, NOW + 8) < 0


class TestTravelDelay:
    """Only a hostile pathing roll slows departures."""

    def test_hostile_pathing_delays(self, woods):
        for i in range(10):
            bridge.perform(woods, "#1", TAGS, "burn", now=NOW + i)
        with deterministic_affordance("pathing"):
            outcome = bridge.respond(woods, "#1", TAGS, "move.depart", bridge.DEPART_AFFORDANCES, now=NOW + 10)
        assert bridge.travel_delay(outcome, 10) > 0

    def test_neutral_place_does_not_delay(self, woods):
        outcome = bridge.respond(woods, "#1", TAGS, "move.depart", bridge.DEPART_AFFORDANCES, now=NOW)
        assert bridge.travel_delay(outcome, 10) == 0


class TestAffordanceFilter:
    """AffordanceContext.affordances limits which affordances are rolled."""

    def test_only_requested_affordances_trigger(self, woods):
        for i in range(10):
            bridge.perform(woods, "#1", TAGS, "burn", now=NOW + i)
        with deterministic_affordance("rest_quality", disable_others=False):
            outcome = bridge.respond(woods, "#1", TAGS, "move.depart", {"pathing"}, now=NOW + 10)
        assert "rest.healing_modifier" not in outcome.adjustments
        assert outcome.trace.affordance_type in ("pathing", "none")


class TestLogEventDecay:
    """log_event decays existing traces to the event's time, not the wall clock."""

    def test_backdated_events_accumulate(self, woods):
        for i in range(3):
            log_event(woods, AffinityEvent("harm.fire", "#1", set(), "whispering_woods", 0.5, timestamp=NOW + i))
        assert woods.personal_traces[("#1", "harm.fire")].accumulated == pytest.approx(1.5, abs=1e-4)  # a few seconds of decay; the old bug gave 0.5
