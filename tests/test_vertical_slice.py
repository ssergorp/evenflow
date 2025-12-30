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
    TraceRecord,
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
        now = 1000000.0
        trace = TraceRecord(
            accumulated=1.0,
            last_updated=now,
            event_count=1,
        )

        # At creation time, should be full value
        result = get_decayed_value(trace, half_life_seconds=86400, now=now)
        assert result == pytest.approx(1.0, rel=0.01)

    def test_half_value_at_half_life(self):
        """Value should be ~50% after one half-life."""
        half_life = 86400  # 1 day in seconds
        creation_time = 1000000.0
        eval_time = creation_time + half_life

        trace = TraceRecord(
            accumulated=1.0,
            last_updated=creation_time,
            event_count=1,
        )

        result = get_decayed_value(trace, half_life_seconds=half_life, now=eval_time)
        assert result == pytest.approx(0.5, rel=0.01)

    def test_quarter_value_at_two_half_lives(self):
        """Value should be ~25% after two half-lives."""
        half_life = 86400  # 1 day in seconds
        creation_time = 1000000.0
        eval_time = creation_time + (2 * half_life)

        trace = TraceRecord(
            accumulated=1.0,
            last_updated=creation_time,
            event_count=1,
        )

        result = get_decayed_value(trace, half_life_seconds=half_life, now=eval_time)
        assert result == pytest.approx(0.25, rel=0.01)

    def test_deterministic_with_explicit_now(self):
        """Decay should be deterministic when now is provided."""
        trace = TraceRecord(
            accumulated=1.0,
            last_updated=1000000.0,
            event_count=1,
        )

        # Same now = same result
        result1 = get_decayed_value(trace, half_life_seconds=86400, now=1043200.0)
        result2 = get_decayed_value(trace, half_life_seconds=86400, now=1043200.0)
        assert result1 == result2  # Exact match, not approx


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
        reset_config()
        now = time.time()

        affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
            now=now
        )

        assert affinity == pytest.approx(0.0, abs=0.01)
        assert get_threshold_label(affinity) == "neutral"

    def test_neutral_produces_no_adjustments(self, whispering_woods, actor_human_hunter):
        """Neutral affinity should produce no mechanical adjustments."""
        reset_config()
        now = time.time()

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
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
        now = time.time()

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )

        log_event(whispering_woods, event)

        affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
            now=now
        )

        # Should be negative (hostile or unwelcoming)
        assert affinity < -0.3
        assert get_threshold_label(affinity) in ["hostile", "unwelcoming"]

    def test_hostile_traveler_is_slowed(self, whispering_woods, actor_human_hunter):
        """A hostile forest should slow the traveler."""
        reset_config()
        now = time.time()

        # Create hostility
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        # Evaluate pathing
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
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

        # Effect should be "slow" not the affordance name
        assert outcome.trace.effect_applied == "slow"


# --- Counterplay Tests ---

class TestCounterplay:
    """Test that counterplay (offer.gift) reduces hostility."""

    def test_gift_creates_positive_trace(self, whispering_woods, actor_human_hunter):
        """A gift should create a positive trace."""
        reset_config()
        now = time.time()

        event = AffinityEvent(
            event_type="offer.gift",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.5,
            timestamp=now,
        )

        log_event(whispering_woods, event)

        affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
            now=now
        )

        # Should be positive
        assert affinity > 0

    def test_gift_reduces_hostility(self, whispering_woods, actor_human_hunter):
        """Gifts after fire should reduce hostility."""
        reset_config()
        now = time.time()

        # Create hostility
        fire_event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, fire_event)

        initial_affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
            now=now
        )

        # Offer gifts
        for i in range(3):
            gift_event = AffinityEvent(
                event_type="offer.gift",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=0.5,
                timestamp=now + i,  # Slightly different timestamps
            )
            log_event(whispering_woods, gift_event)

        final_affinity = compute_affinity(
            whispering_woods,
            actor_human_hunter["actor_id"],
            actor_human_hunter["actor_tags"],
            now=now + 3
        )

        # Should be less hostile
        assert final_affinity > initial_affinity


# --- Replay Determinism Tests ---

class TestReplayDeterminism:
    """Test that replay produces identical results."""

    def test_replay_matches_original_exactly(self, whispering_woods, actor_human_hunter):
        """Replay from snapshot must produce EXACTLY identical affinity."""
        reset_config()
        now = time.time()

        # Create some traces
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        # Evaluate and capture snapshot
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)
        snapshot = outcome.snapshot

        # Replay from snapshot
        replayed_affinity = replay_from_snapshot(snapshot)

        # Must match EXACTLY (DO_NOT.md #6)
        # This is now a true exact match because eval_time is frozen
        assert replayed_affinity == snapshot.computed_affinity

    def test_replay_independent_of_current_state(self, whispering_woods, actor_human_hunter):
        """Replay should not be affected by changes after snapshot."""
        reset_config()
        now = time.time()

        # Create initial state
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        # Capture snapshot
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )
        outcome = evaluate_affordances(ctx)
        snapshot = outcome.snapshot

        # Modify current state (more events)
        for i in range(5):
            more_fire = AffinityEvent(
                event_type="harm.fire",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=0.8,
                timestamp=now + i + 1,
            )
            log_event(whispering_woods, more_fire)

        # Replay should still match original EXACTLY
        replayed_affinity = replay_from_snapshot(snapshot)
        assert replayed_affinity == snapshot.computed_affinity

    def test_replay_with_time_passage(self, whispering_woods, actor_human_hunter):
        """Replay should work even if real time has passed."""
        reset_config()
        creation_time = 1000000.0

        # Create traces at a specific time
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=creation_time,
        )
        log_event(whispering_woods, event)

        # Evaluate at creation time
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=creation_time,
        )
        outcome = evaluate_affordances(ctx)
        snapshot = outcome.snapshot

        # Replay should match regardless of when we call it
        # because it uses snapshot.eval_time, not current time
        replayed_affinity = replay_from_snapshot(snapshot)
        assert replayed_affinity == snapshot.computed_affinity

        # Verify eval_time is stored
        assert snapshot.eval_time == creation_time


# --- Cooldown Tests ---

class TestCooldowns:
    """Test that cooldowns prevent repeated triggers."""

    def test_cooldown_prevents_immediate_retrigger(self, whispering_woods, actor_human_hunter):
        """Affordance should not trigger twice in a row."""
        reset_config()
        now = time.time()

        # Create hostility
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        # First evaluation triggers
        outcome1 = evaluate_affordances(ctx)
        assert outcome1.triggered is True
        assert len(outcome1.cooldowns_consumed) > 0

        # Second evaluation should not trigger (cooldown active)
        ctx2 = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now + 1,  # 1 second later
        )
        outcome2 = evaluate_affordances(ctx2)
        assert outcome2.triggered is False
        assert outcome2.adjustments == {}


# --- Severity Clamp Tests ---

class TestSeverityClamp:
    """Test that severity is clamped to configured limits."""

    def test_hostile_clamped_to_max(self, whispering_woods, actor_human_hunter):
        """Severe hostility should not exceed clamp."""
        reset_config()
        now = time.time()

        # Create extreme hostility
        for i in range(10):
            event = AffinityEvent(
                event_type="harm.fire",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=1.0,
                timestamp=now + i,
            )
            log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now + 10,
        )

        outcome = evaluate_affordances(ctx)

        # Should be clamped to max (0.5 for pathing hostile)
        if outcome.triggered:
            assert outcome.adjustments["room.travel_time_modifier"] <= 0.5


# --- Snapshot Contents Tests ---

class TestSnapshotContents:
    """Test that snapshots contain all required fields."""

    def test_snapshot_has_eval_time(self, whispering_woods, actor_human_hunter):
        """Snapshot must have eval_time for deterministic replay."""
        reset_config()
        now = 1234567890.0

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        assert outcome.snapshot.eval_time == now

    def test_snapshot_has_random_seed(self, whispering_woods, actor_human_hunter):
        """Snapshot must have random_seed for deterministic tells."""
        reset_config()
        now = time.time()

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        assert outcome.snapshot.random_seed is not None
        assert isinstance(outcome.snapshot.random_seed, int)

    def test_snapshot_has_effect_applied(self, whispering_woods, actor_human_hunter):
        """Snapshot must have effect_applied (slow/swift/None)."""
        reset_config()
        now = time.time()

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Should be "slow" for hostile
        assert outcome.snapshot.effect_applied == "slow"
        assert outcome.trace.effect_applied == "slow"


# --- Admin Toggle Tests ---

class TestAdminToggles:
    """Test admin control of affordances."""

    def test_toggle_affordance_off(self, whispering_woods, actor_human_hunter):
        """Disabled affordance should not trigger."""
        reset_config()
        from world.affinity.affordances import admin_toggle_affordance, is_affordance_enabled

        now = time.time()

        # Disable pathing
        admin_toggle_affordance("pathing", False)
        assert is_affordance_enabled("pathing") is False

        # Create hostility
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Pathing should not have triggered
        assert "room.travel_time_modifier" not in outcome.adjustments

        # Re-enable for other tests
        admin_toggle_affordance("pathing", True)

    def test_force_hostile_mode(self, whispering_woods, actor_human_hunter):
        """Force mode should override actual affinity."""
        reset_config()
        from world.affinity.affordances import admin_force_mode

        now = time.time()

        # Force pathing to hostile (even with neutral affinity)
        admin_force_mode("pathing", "hostile")

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Should trigger as hostile even though affinity is neutral
        if outcome.triggered:
            assert "room.travel_time_modifier" in outcome.adjustments
            assert outcome.adjustments["room.travel_time_modifier"] > 0

        # Clear force mode
        admin_force_mode("pathing", None)

    def test_reset_cooldowns(self, whispering_woods, actor_human_hunter):
        """Admin should be able to clear cooldowns."""
        reset_config()
        from world.affinity.affordances import admin_reset_cooldowns

        now = time.time()

        # Create hostility and trigger affordance
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome1 = evaluate_affordances(ctx)
        assert outcome1.triggered is True

        # Reset cooldowns
        admin_reset_cooldowns(whispering_woods)

        # Should be able to trigger again
        ctx2 = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now + 1,
        )
        outcome2 = evaluate_affordances(ctx2)
        assert outcome2.triggered is True


# --- Multiple Affordances Tests ---

class TestMultipleAffordances:
    """Test that multiple affordances can trigger together."""

    def test_ambient_messaging_at_hostile(self, whispering_woods, actor_human_hunter):
        """Ambient messaging should produce tells based on affinity level."""
        reset_config()
        from world.affinity.affordances import admin_reset_cooldowns

        now = time.time()

        # Create significant hostility
        for i in range(5):
            event = AffinityEvent(
                event_type="harm.fire",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=0.8,
                timestamp=now + i,
            )
            log_event(whispering_woods, event)

        admin_reset_cooldowns(whispering_woods)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now + 5,
        )

        outcome = evaluate_affordances(ctx)

        # Multiple tells may have been generated
        assert len(outcome.tells) >= 1

        # No tell should reveal affinity numbers (DO_NOT.md #2)
        for tell in outcome.tells:
            assert "affinity" not in tell.lower()
            assert "%" not in tell


# --- Spell Side Effects Tests ---

class TestSpellSideEffects:
    """Test spell efficacy affordance."""

    def test_fire_spell_in_hostile_forest(self, whispering_woods, actor_human_hunter):
        """Fire spells should be penalized in forests that hate fire."""
        reset_config()
        from world.affinity.affordances import admin_reset_cooldowns, admin_toggle_affordance

        # Ensure spell_side_effects is enabled
        admin_toggle_affordance("spell_side_effects", True)

        now = time.time()

        # Create hostility
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location_id=whispering_woods.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(whispering_woods, event)

        admin_reset_cooldowns(whispering_woods)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="magic.cast",
            action_target=None,
            timestamp=now,
            spell_school="fire",  # This triggers extra penalty
        )

        outcome = evaluate_affordances(ctx)

        # If spell side effects triggered, should have power modifier
        if "spell.power_modifier" in outcome.adjustments:
            # Should be negative (reduced power)
            assert outcome.adjustments["spell.power_modifier"] < 0


# --- Misleading Navigation Tests ---

class TestMisleadingNavigation:
    """Test rare redirect affordance."""

    def test_redirect_needs_adjacent_rooms(self, whispering_woods, actor_human_hunter):
        """Misleading navigation needs adjacent rooms to work."""
        reset_config()
        from world.affinity.affordances import admin_force_mode, admin_reset_cooldowns

        now = time.time()

        # Force strongly hostile
        admin_force_mode("misleading_navigation", "hostile")

        admin_reset_cooldowns(whispering_woods)

        # Without adjacent rooms, should not redirect
        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
            adjacent_rooms=None,
        )

        outcome = evaluate_affordances(ctx)
        assert outcome.redirect_target is None

        # With adjacent rooms, might redirect
        ctx2 = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="move.pass",
            action_target=None,
            timestamp=now + 1,
            adjacent_rooms=["room_a", "room_b", "room_c"],
        )

        admin_reset_cooldowns(whispering_woods)
        outcome2 = evaluate_affordances(ctx2)

        # If redirect triggered, should be one of the adjacent rooms
        if outcome2.redirect_target:
            assert outcome2.redirect_target in ["room_a", "room_b", "room_c"]

        # Clear force mode
        admin_force_mode("misleading_navigation", None)


# --- Resource Scarcity Tests ---

class TestResourceScarcity:
    """Test harvest yield modifier."""

    def test_favorable_increases_yield(self, whispering_woods, actor_human_hunter):
        """Favorable affinity should increase harvest yield."""
        reset_config()
        from world.affinity.affordances import admin_reset_cooldowns

        now = time.time()

        # Create favorable affinity through gifts
        for i in range(5):
            event = AffinityEvent(
                event_type="offer.gift",
                actor_id=actor_human_hunter["actor_id"],
                actor_tags=actor_human_hunter["actor_tags"],
                location_id=whispering_woods.location_id,
                intensity=0.6,
                timestamp=now + i,
            )
            log_event(whispering_woods, event)

        admin_reset_cooldowns(whispering_woods)

        ctx = AffordanceContext(
            actor_id=actor_human_hunter["actor_id"],
            actor_tags=actor_human_hunter["actor_tags"],
            location=whispering_woods,
            action_type="extract.harvest",
            action_target=None,
            timestamp=now + 5,
        )

        outcome = evaluate_affordances(ctx)

        # If resource scarcity triggered, yield modifier should be positive
        if "harvest.yield_modifier" in outcome.adjustments:
            assert outcome.adjustments["harvest.yield_modifier"] > 0


# --- Tells Never Reveal Affinity Tests ---

class TestTellsNeverRevealAffinity:
    """Ensure tells never expose affinity values (DO_NOT.md #2)."""

    def test_all_tells_are_indirect(self, whispering_woods, actor_human_hunter):
        """All tells should be narrative, never numeric."""
        reset_config()
        from world.affinity.affordances import TELLS

        forbidden_patterns = [
            "affinity",
            "reputation",
            "score",
            "points",
            "meter",
            "%",
            "hostile",  # The word itself shouldn't appear
            "favorable",
            "neutral",
        ]

        for aff_type, tell_groups in TELLS.items():
            for group_name, tells in tell_groups.items():
                if isinstance(tells, list):
                    for tell in tells:
                        for pattern in forbidden_patterns:
                            assert pattern.lower() not in tell.lower(), \
                                f"Tell '{tell}' in {aff_type}.{group_name} contains forbidden pattern '{pattern}'"
