"""
Vertical slice acceptance tests for the affinity system.

Tests the golden path: whispering_woods location with pathing affordance.

See docs/vertical_slice.md for the complete implementation checklist.
"""

import math
import time
import pytest

from world.affinity.core import (
    Location,
    AffinityEvent,
    AffordanceConfig,
    SaturationState,
)
from world.affinity.computation import (
    get_decayed_value,
    get_valuation,
    compute_affinity,
    get_threshold_label,
)
from world.affinity.events import log_event
from world.affinity.affordances import (
    AffordanceContext,
    evaluate_affordances,
    replay_from_snapshot,
)
from world.affinity.config import get_config, reset_config


# --- Test Fixtures ---

@pytest.fixture
def whispering_woods() -> Location:
    """
    Create the canonical test location.
    See world/locations/whispering_woods.yaml
    """
    return Location(
        location_id="whispering_woods",
        name="The Whispering Woods",
        description="An ancient forest where the trees seem to watch and remember.",
        valuation_profile={
            # Category defaults (soft, ±0.1-0.2)
            "harm": -0.15,
            "extract": -0.1,
            "offer": 0.15,
            "create": 0.1,
            # Specific strong opinions (±0.3-0.8)
            "harm.fire": -0.8,
            "harm.poison": -0.5,
            "extract.hunt": -0.4,
            "extract.harvest": -0.2,
            "offer.gift": 0.5,
            "offer.sacrifice": 0.3,
            "create.plant": 0.6,
            "create.ritual": 0.4,
        },
        affordances=[
            AffordanceConfig(
                affordance_type="pathing",
                enabled=True,
                mechanical_handle="room.travel_time_modifier",
                severity_clamp_hostile=0.5,
                severity_clamp_favorable=-0.3,
                cooldown_seconds=3600,
                tells_hostile=[
                    "The path seems to twist away from you.",
                    "Branches catch at your pack.",
                ],
                tells_favorable=[
                    "A clear path opens through the underbrush.",
                    "The trees seem to lean aside.",
                ],
            ),
        ],
    )


@pytest.fixture
def actor_human_hunter():
    """A human hunter actor."""
    return {
        "actor_id": "player_0042",
        "actor_tags": {"human", "hunter", "outsider"},
    }


@pytest.fixture
def actor_elf_druid():
    """An elf druid actor."""
    return {
        "actor_id": "player_0099",
        "actor_tags": {"elf", "druid"},
    }


# --- Decay Math Tests ---

class TestDecayMath:
    """Test exponential decay computation."""

    def test_no_decay_at_zero_time(self):
        """Value should be unchanged at t=0."""
        from world.affinity.core import TraceRecord

        trace = TraceRecord(
            accumulated=1.0,
            last_updated=time.time(),
            event_count=1,
        )

        # At creation time, should be full value
        result = get_decayed_value(trace, half_life_seconds=86400)
        assert result == pytest.approx(1.0, rel=0.01)

    def test_half_value_at_half_life(self):
        """Value should be ~50% after one half-life."""
        from world.affinity.core import TraceRecord

        half_life = 86400  # 1 day in seconds
        trace = TraceRecord(
            accumulated=1.0,
            last_updated=time.time() - half_life,  # 1 day ago
            event_count=1,
        )

        result = get_decayed_value(trace, half_life_seconds=half_life)
        assert result == pytest.approx(0.5, rel=0.01)

    def test_quarter_value_at_two_half_lives(self):
        """Value should be ~25% after two half-lives."""
        from world.affinity.core import TraceRecord

        half_life = 86400  # 1 day in seconds
        trace = TraceRecord(
            accumulated=1.0,
            last_updated=time.time() - (2 * half_life),  # 2 days ago
            event_count=1,
        )

        result = get_decayed_value(trace, half_life_seconds=half_life)
        assert result == pytest.approx(0.25, rel=0.01)


# --- Valuation Fallback Tests ---

class TestValuationFallback:
    """Test valuation lookup with exact/category/default fallback."""

    def test_exact_match(self, whispering_woods):
        """Exact event type should match."""
        result = get_valuation(whispering_woods.valuation_profile, "harm.fire")
        assert result == -0.8

    def test_category_fallback(self, whispering_woods):
        """Unknown event should fall back to category."""
        # harm.magical is not defined, should fall back to harm: -0.15
        result = get_valuation(whispering_woods.valuation_profile, "harm.magical")
        assert result == -0.15

    def test_default_zero(self, whispering_woods):
        """Completely unknown event should return 0.0."""
        result = get_valuation(whispering_woods.valuation_profile, "trade.fair")
        assert result == 0.0


# --- Neutral / No-Op Tests ---

class TestNeutralOutcome:
    """Test that neutral affinity produces no-op outcome."""

    def test_empty_location_is_neutral(self, whispering_woods, actor_human_hunter):
        """A location with no traces should be neutral."""
        affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
        )

        assert affinity == pytest.approx(0.0, abs=0.01)
        assert get_threshold_label(affinity) == "neutral"

    def test_neutral_produces_no_adjustments(self, whispering_woods, actor_human_hunter):
        """Neutral affinity should produce no mechanical adjustments."""
        reset_config()

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
        )

        outcome = evaluate_affordances(ctx)

        assert outcome.triggered is False
        assert outcome.adjustments == {}
        assert outcome.tells == []
        assert outcome.trace.threshold_crossed == "neutral"


# --- Hostile / Slow Traveler Tests ---

class TestHostileOutcome:
    """Test that hostile affinity slows travelers."""

    def test_fire_creates_hostility(self, whispering_woods, actor_human_hunter):
        """A fire event should create negative affinity."""
        reset_config()

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
        )

        log_event(whispering_woods, event)

        affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
        )

        # Should be negative (hostile or unwelcoming)
        assert affinity < -0.3
        assert get_threshold_label(affinity) in ["hostile", "unwelcoming"]

    def test_hostile_traveler_is_slowed(self, whispering_woods, actor_human_hunter):
        """A hostile forest should slow the traveler."""
        reset_config()

        # Create hostility
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
        )
        log_event(whispering_woods, event)

        # Evaluate pathing
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
        )

        outcome = evaluate_affordances(ctx)

        # Should be slowed
        assert outcome.triggered is True
        assert "room.travel_time_modifier" in outcome.adjustments
        assert outcome.adjustments["room.travel_time_modifier"] > 0  # Positive = slower
        assert len(outcome.tells) > 0
        # Tell should be narrative, not a meter (DO_NOT.md #2)
        assert "affinity" not in outcome.tells[0].lower()
        assert "%" not in outcome.tells[0]


# --- Counterplay Tests ---

class TestCounterplay:
    """Test that counterplay (offer.gift) reduces hostility."""

    def test_gift_creates_positive_trace(self, whispering_woods, actor_human_hunter):
        """A gift should create a positive trace."""
        reset_config()

        event = AffinityEvent(
            event_type="offer.gift",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.5,
        )

        log_event(whispering_woods, event)

        affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
        )

        # Should be positive
        assert affinity > 0

    def test_gift_reduces_hostility(self, whispering_woods, actor_human_hunter):
        """Gifts after fire should reduce hostility."""
        reset_config()

        # Create hostility
        fire_event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
        )
        log_event(whispering_woods, fire_event)

        initial_affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
        )

        # Offer gifts
        for _ in range(3):
            gift_event = AffinityEvent(
                event_type="offer.gift",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=0.5,
            )
            log_event(whispering_woods, gift_event)

        final_affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
        )

        # Should be less hostile
        assert final_affinity > initial_affinity


# --- Replay Determinism Tests ---

class TestReplayDeterminism:
    """Test that replay produces identical results."""

    def test_replay_matches_original(self, whispering_woods, actor_human_hunter):
        """Replay from snapshot must produce identical affinity."""
        reset_config()

        # Create some traces
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
        )
        log_event(whispering_woods, event)

        # Evaluate and capture snapshot
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
        )

        outcome = evaluate_affordances(ctx)
        snapshot = outcome.snapshot

        # Replay from snapshot
        replayed_affinity = replay_from_snapshot(snapshot)

        # Must match exactly (DO_NOT.md #6)
        assert replayed_affinity == pytest.approx(
            snapshot.computed_affinity,
            abs=1e-10  # Exact match, not approximate
        )

    def test_replay_independent_of_current_state(self, whispering_woods, actor_human_hunter):
        """Replay should not be affected by changes after snapshot."""
        reset_config()

        # Create initial state
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
        )
        log_event(whispering_woods, event)

        # Capture snapshot
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
        )
        outcome = evaluate_affordances(ctx)
        snapshot = outcome.snapshot

        # Modify current state (more events)
        for _ in range(5):
            more_fire = AffinityEvent(
                event_type="harm.fire",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=0.8,
            )
            log_event(whispering_woods, more_fire)

        # Replay should still match original
        replayed_affinity = replay_from_snapshot(snapshot)
        assert replayed_affinity == pytest.approx(
            snapshot.computed_affinity,
            abs=1e-10
        )


# --- Cooldown Tests ---

class TestCooldowns:
    """Test that cooldowns prevent repeated triggers."""

    def test_cooldown_prevents_immediate_retrigger(self, whispering_woods, actor_human_hunter):
        """Affordance should not trigger twice in a row."""
        reset_config()

        # Create hostility
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
        )
        log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
        )

        # First evaluation triggers
        outcome1 = evaluate_affordances(ctx)
        assert outcome1.triggered is True
        assert len(outcome1.cooldowns_consumed) > 0

        # Second evaluation should not trigger (cooldown active)
        outcome2 = evaluate_affordances(ctx)
        assert outcome2.triggered is False
        assert outcome2.adjustments == {}


# --- Severity Clamp Tests ---

class TestSeverityClamp:
    """Test that severity is clamped to configured limits."""

    def test_hostile_clamped_to_max(self, whispering_woods, actor_human_hunter):
        """Severe hostility should not exceed clamp."""
        reset_config()

        # Create extreme hostility
        for _ in range(10):
            event = AffinityEvent(
                event_type="harm.fire",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=1.0,
            )
            log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
        )

        outcome = evaluate_affordances(ctx)

        # Should be clamped to max (0.5 for pathing hostile)
        if outcome.triggered:
            assert outcome.adjustments["room.travel_time_modifier"] <= 0.5
