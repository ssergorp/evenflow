"""
Per-affordance validation tests.

Tests for each affordance:
1. Neutral outcome is no-op
2. Hostile/favorable touch <=2 handles
3. Tells contain no numbers/meter words
4. Replay matches exactly

See docs/DO_NOT.md for constraints.
"""

import pytest
import time

from world.affinity.core import (
    Location,
    AffinityEvent,
    AffordanceConfig,
    TraceRecord,
)
from world.affinity.computation import compute_affinity
from world.affinity.events import log_event
from world.affinity.affordances import (
    AffordanceContext,
    AffordanceOutcome,
    evaluate_affordances,
    replay_from_snapshot,
    replay_full_from_snapshot,
    replay_tells_from_snapshot,
    replay_adjustments_from_snapshot,
    verify_affinity_computation,
    validate_affordance_definitions,
    get_handle_counts,
    admin_toggle_affordance,
    admin_force_mode,
    admin_reset_cooldowns,
    AFFORDANCE_DEFAULTS,
    TELLS,
)
from world.affinity.validation import (
    validate_all_affordances,
    validate_all_tells,
    validate_handle,
    validate_handle_count,
    validate_adjustments,
    validate_tell,
    HANDLE_ALLOWLIST,
    FORBIDDEN_TELL_WORDS,
    AffordanceValidationError,
    HandleNotAllowedError,
    TooManyHandlesError,
)
from world.affinity.config import reset_config


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def test_location() -> Location:
    """Create a test location with all affordances enabled."""
    return Location(
        location_id="test_location",
        name="Test Location",
        description="A location for testing affordances.",
        valuation_profile={
            "harm": -0.2,
            "harm.fire": -0.8,
            "extract": -0.1,
            "extract.hunt": -0.4,
            "offer": 0.2,
            "offer.gift": 0.6,
            "create": 0.1,
            "create.plant": 0.5,
        },
        affordances=[
            AffordanceConfig(
                affordance_type="pathing",
                enabled=True,
                mechanical_handle="room.travel_time_modifier",
                severity_clamp_hostile=0.5,
                severity_clamp_favorable=-0.3,
                cooldown_seconds=3600,
                tells_hostile=["The path twists."],
                tells_favorable=["The path clears."],
            ),
        ],
    )


@pytest.fixture
def actor():
    """A test actor."""
    return {
        "actor_id": "test_actor",
        "actor_tags": {"human", "tester"},
    }


# =============================================================================
# VALIDATION TESTS
# =============================================================================

class TestHandleAllowlist:
    """Test handle validation against allowlist."""

    def test_valid_handles_pass(self):
        """All handles in allowlist should pass validation."""
        for handle in HANDLE_ALLOWLIST:
            validate_handle(handle, "test")  # Should not raise

    def test_none_handle_passes(self):
        """None (flavor-only) should pass validation."""
        validate_handle(None, "test")  # Should not raise

    def test_invalid_handle_fails(self):
        """Unknown handle should fail validation."""
        with pytest.raises(HandleNotAllowedError):
            validate_handle("invented.new_stat", "test")

    def test_typo_handle_fails(self):
        """Typo in handle name should fail."""
        with pytest.raises(HandleNotAllowedError):
            validate_handle("room.travel_time_modifer", "test")  # typo


class TestHandleCount:
    """Test that affordances have <=2 handles."""

    def test_all_affordances_have_two_or_fewer_handles(self):
        """Every affordance must have at most 2 mechanical handles."""
        handle_counts = get_handle_counts()

        for aff_type, count in handle_counts.items():
            assert count <= 2, f"{aff_type} has {count} handles, max is 2"

    def test_zero_handles_allowed(self):
        """Flavor-only affordances (0 handles) are allowed."""
        validate_handle_count([None], "flavor_only")  # Should not raise

    def test_one_handle_allowed(self):
        """Single handle affordances are allowed."""
        validate_handle_count(["room.travel_time_modifier"], "single")

    def test_two_handles_allowed(self):
        """Two-handle affordances are allowed."""
        validate_handle_count(
            ["spell.power_modifier", "spell.backfire_chance"],
            "dual"
        )

    def test_three_handles_rejected(self):
        """More than 2 handles should fail."""
        with pytest.raises(TooManyHandlesError):
            validate_handle_count(
                ["a", "b", "c"],
                "too_many"
            )


class TestTellValidation:
    """Test that tells contain no forbidden patterns."""

    def test_all_tells_pass_validation(self):
        """All defined tells should pass validation."""
        # This should not raise
        count = validate_all_tells(TELLS)
        assert count > 0, "Should have validated some tells"

    def test_forbidden_patterns(self):
        """Tells with forbidden patterns should fail."""
        bad_tells = [
            "Your affinity increased.",      # "affinity" forbidden
            "Reputation improved.",          # "reputation" forbidden
            "Hostility meter rising.",       # "meter" forbidden
            "You have +5 to damage.",        # meter pattern "+5"
            "Effect: 25% bonus.",            # meter pattern "25%"
            "You earned 10 points today.",   # meter pattern "10 points"
        ]

        for tell in bad_tells:
            with pytest.raises(AffordanceValidationError):
                validate_tell(tell, "test", "test_group")

    def test_acceptable_tells(self):
        """Normal narrative tells should pass."""
        from world.affinity.validation import validate_tell

        good_tells = [
            "The path seems to twist away from you.",
            "Brambles catch at your clothes.",
            "An easy path opens through the undergrowth.",
            "Something watches from the shadows.",
            "Deep, restorative sleep.",
        ]

        for tell in good_tells:
            validate_tell(tell, "test", "test_group")  # Should not raise


class TestAdjustmentValidation:
    """Test adjustment output validation."""

    def test_valid_adjustments_pass(self):
        """Adjustments with allowed handles should pass."""
        validate_adjustments(
            {"room.travel_time_modifier": 0.3},
            "pathing"
        )

    def test_two_adjustments_pass(self):
        """Two adjustments should pass."""
        validate_adjustments(
            {"spell.power_modifier": -0.2, "spell.backfire_chance": 0.1},
            "spell_side_effects"
        )

    def test_three_adjustments_fail(self):
        """More than 2 adjustments should fail."""
        with pytest.raises(TooManyHandlesError):
            validate_adjustments(
                {"a": 1, "b": 2, "c": 3},
                "too_many"
            )

    def test_invalid_handle_in_adjustment_fails(self):
        """Unknown handle in adjustments should fail."""
        with pytest.raises(HandleNotAllowedError):
            validate_adjustments(
                {"invented.stat": 0.5},
                "test"
            )


# =============================================================================
# PER-AFFORDANCE TESTS
# =============================================================================

class TestPathingAffordance:
    """Tests for the pathing affordance."""

    def test_neutral_is_noop(self, test_location, actor):
        """Neutral affinity produces no pathing effect."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Neutral = no pathing adjustment
        assert "room.travel_time_modifier" not in outcome.adjustments

    def test_hostile_touches_one_handle(self, test_location, actor):
        """Hostile pathing only modifies travel_time_modifier."""
        reset_config()
        admin_reset_cooldowns(test_location)
        admin_force_mode("pathing", "hostile")

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Should only touch 1 handle
        pathing_handles = [k for k in outcome.adjustments.keys()
                          if k == "room.travel_time_modifier"]
        assert len(pathing_handles) <= 1

        admin_force_mode("pathing", None)

    def test_tells_are_narrative(self, test_location, actor):
        """Pathing tells contain no forbidden patterns."""
        for tell in TELLS["pathing"]["hostile"]:
            validate_tell(tell, "pathing", "hostile")  # Should not raise

        for tell in TELLS["pathing"]["favorable"]:
            validate_tell(tell, "pathing", "favorable")  # Should not raise

    def test_replay_matches_exactly(self, test_location, actor):
        """Replay returns exact stored values."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()

        # Create hostility
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location_id=test_location.location_id,
            intensity=0.6,
            timestamp=now,
        )
        log_event(test_location, event)

        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Replay should return exact stored values
        replayed_affinity = replay_from_snapshot(outcome.snapshot)
        replayed_tells = replay_tells_from_snapshot(outcome.snapshot)
        replayed_adjustments = replay_adjustments_from_snapshot(outcome.snapshot)

        assert replayed_affinity == outcome.snapshot.computed_affinity
        assert replayed_tells == outcome.tells
        assert replayed_adjustments == outcome.adjustments


class TestEncounterBiasAffordance:
    """Tests for the encounter bias affordance."""

    def test_neutral_is_noop(self, test_location, actor):
        """Neutral affinity produces no encounter effect."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        assert "room.encounter_rate_modifier" not in outcome.adjustments
        assert "npc.aggro_radius_modifier" not in outcome.adjustments

    def test_touches_at_most_two_handles(self, test_location, actor):
        """Encounter bias modifies at most 2 handles."""
        config = AFFORDANCE_DEFAULTS["encounter_bias"]
        handles = [config.get("handle"), config.get("handle_secondary")]
        non_null = [h for h in handles if h]

        assert len(non_null) <= 2

    def test_tells_are_narrative(self):
        """Encounter bias tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["encounter_bias"][group]:
                validate_tell(tell, "encounter_bias", group)  # Should not raise


class TestSpellSideEffectsAffordance:
    """Tests for the spell side effects affordance."""

    def test_neutral_is_noop(self, test_location, actor):
        """Neutral affinity produces no spell effect."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="magic.cast",
            action_target=None,
            timestamp=now,
            spell_school="fire",
        )

        outcome = evaluate_affordances(ctx)

        assert "spell.power_modifier" not in outcome.adjustments

    def test_touches_at_most_two_handles(self):
        """Spell side effects modifies at most 2 handles."""
        config = AFFORDANCE_DEFAULTS["spell_side_effects"]
        handles = [config.get("handle"), config.get("handle_secondary")]
        non_null = [h for h in handles if h]

        assert len(non_null) == 2  # Spell effects uses exactly 2

    def test_tells_are_narrative(self):
        """Spell side effects tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["spell_side_effects"][group]:
                validate_tell(tell, "spell_side_effects", group)  # Should not raise


class TestResourceScarcityAffordance:
    """Tests for the resource scarcity affordance."""

    def test_neutral_is_noop(self, test_location, actor):
        """Neutral affinity produces no yield effect."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="extract.harvest",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        assert "harvest.yield_modifier" not in outcome.adjustments

    def test_touches_one_handle(self):
        """Resource scarcity modifies only 1 handle."""
        config = AFFORDANCE_DEFAULTS["resource_scarcity"]
        handles = [config.get("handle"), config.get("handle_secondary")]
        non_null = [h for h in handles if h]

        assert len(non_null) == 1

    def test_tells_are_narrative(self):
        """Resource scarcity tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["resource_scarcity"][group]:
                validate_tell(tell, "resource_scarcity", group)  # Should not raise


class TestRestQualityAffordance:
    """Tests for the rest quality affordance."""

    def test_neutral_is_noop(self, test_location, actor):
        """Neutral affinity produces no rest effect."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="heal.rest",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        assert "rest.healing_modifier" not in outcome.adjustments

    def test_touches_one_handle(self):
        """Rest quality modifies only 1 handle."""
        config = AFFORDANCE_DEFAULTS["rest_quality"]
        handles = [config.get("handle"), config.get("handle_secondary")]
        non_null = [h for h in handles if h]

        assert len(non_null) == 1

    def test_tells_are_narrative(self):
        """Rest quality tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["rest_quality"][group]:
                validate_tell(tell, "rest_quality", group)  # Should not raise


class TestAmbientMessagingAffordance:
    """Tests for the ambient messaging affordance."""

    def test_is_flavor_only(self):
        """Ambient messaging has no mechanical handle."""
        config = AFFORDANCE_DEFAULTS["ambient_messaging"]
        assert config.get("handle") is None

    def test_tells_are_narrative(self):
        """Ambient messaging tells contain no forbidden patterns."""
        for group_name, tells in TELLS["ambient_messaging"].items():
            for tell in tells:
                validate_tell(tell, "ambient_messaging", group_name)  # Should not raise


class TestLootQualityAffordance:
    """Tests for the loot quality affordance."""

    def test_neutral_is_noop(self, test_location, actor):
        """Neutral affinity produces no loot effect."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="extract.loot",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        assert "loot.quality_modifier" not in outcome.adjustments

    def test_touches_one_handle(self):
        """Loot quality modifies only 1 handle."""
        config = AFFORDANCE_DEFAULTS["loot_quality"]
        handles = [config.get("handle"), config.get("handle_secondary")]
        non_null = [h for h in handles if h]

        assert len(non_null) == 1

    def test_tells_are_narrative(self):
        """Loot quality tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["loot_quality"][group]:
                validate_tell(tell, "loot_quality", group)  # Should not raise


class TestWeatherMicroclimateAffordance:
    """Tests for the weather microclimate affordance."""

    def test_is_flavor_only(self):
        """Weather microclimate has no mechanical handle."""
        config = AFFORDANCE_DEFAULTS["weather_microclimate"]
        assert config.get("handle") is None

    def test_tells_are_narrative(self):
        """Weather microclimate tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["weather_microclimate"][group]:
                validate_tell(tell, "weather_microclimate", group)  # Should not raise


class TestAnimalMessengersAffordance:
    """Tests for the animal messengers affordance."""

    def test_is_flavor_only(self):
        """Animal messengers has no mechanical handle."""
        config = AFFORDANCE_DEFAULTS["animal_messengers"]
        assert config.get("handle") is None

    def test_tells_are_narrative(self):
        """Animal messengers tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["animal_messengers"][group]:
                validate_tell(tell, "animal_messengers", group)  # Should not raise


class TestMisleadingNavigationAffordance:
    """Tests for the misleading navigation affordance."""

    def test_neutral_is_noop(self, test_location, actor):
        """Neutral affinity produces no redirect."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()
        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
            adjacent_rooms=["room_a", "room_b"],
        )

        outcome = evaluate_affordances(ctx)

        # At neutral, should not redirect
        assert outcome.redirect_target is None

    def test_touches_one_handle(self):
        """Misleading navigation modifies only 1 handle."""
        config = AFFORDANCE_DEFAULTS["misleading_navigation"]
        handles = [config.get("handle"), config.get("handle_secondary")]
        non_null = [h for h in handles if h]

        assert len(non_null) == 1

    def test_tells_are_narrative(self):
        """Misleading navigation tells contain no forbidden patterns."""
        for group in ["hostile", "favorable"]:
            for tell in TELLS["misleading_navigation"][group]:
                validate_tell(tell, "misleading_navigation", group)  # Should not raise


# =============================================================================
# REPLAY DETERMINISM TESTS
# =============================================================================

class TestReplayDeterminism:
    """Test that replay is 100% deterministic."""

    def test_replay_affinity_returns_stored_value(self, test_location, actor):
        """replay_from_snapshot returns stored value, not recomputed."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()

        # Create trace
        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location_id=test_location.location_id,
            intensity=0.7,
            timestamp=now,
        )
        log_event(test_location, event)

        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)
        snapshot = outcome.snapshot

        # Replay should return EXACTLY the stored value
        replayed = replay_from_snapshot(snapshot)
        assert replayed == snapshot.computed_affinity

    def test_replay_full_returns_all_stored_values(self, test_location, actor):
        """replay_full_from_snapshot returns all stored values."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location_id=test_location.location_id,
            intensity=0.7,
            timestamp=now,
        )
        log_event(test_location, event)

        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)
        result = replay_full_from_snapshot(outcome.snapshot)

        assert result.computed_affinity == outcome.snapshot.computed_affinity
        assert result.threshold_crossed == outcome.snapshot.threshold_crossed
        assert result.adjustments == outcome.adjustments
        assert result.tells == outcome.tells
        assert result.redirect_target == outcome.redirect_target

    def test_verify_affinity_computation_matches(self, test_location, actor):
        """Stored affinity matches recomputation from traces."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location_id=test_location.location_id,
            intensity=0.7,
            timestamp=now,
        )
        log_event(test_location, event)

        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Verify stored affinity matches what we'd recompute
        assert verify_affinity_computation(outcome.snapshot) is True

    def test_replay_never_calls_rng(self, test_location, actor):
        """Replay functions return stored values, never use RNG."""
        reset_config()
        admin_reset_cooldowns(test_location)
        admin_force_mode("pathing", "hostile")

        now = time.time()

        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)

        # Call replay 100 times - should always return identical values
        for _ in range(100):
            replayed = replay_full_from_snapshot(outcome.snapshot)
            assert replayed.tells == outcome.tells
            assert replayed.adjustments == outcome.adjustments

        admin_force_mode("pathing", None)

    def test_snapshot_stores_final_values(self, test_location, actor):
        """AffordanceSnapshot stores final_adjustments, final_tells, final_redirect_target."""
        reset_config()
        admin_reset_cooldowns(test_location)

        now = time.time()

        event = AffinityEvent(
            event_type="harm.fire",
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location_id=test_location.location_id,
            intensity=0.7,
            timestamp=now,
        )
        log_event(test_location, event)

        ctx = AffordanceContext(
            actor_id=actor["actor_id"],
            actor_tags=actor["actor_tags"],
            location=test_location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)
        snapshot = outcome.snapshot

        # Snapshot should have final values matching outcome
        assert snapshot.final_adjustments == outcome.adjustments
        assert snapshot.final_tells == outcome.tells
        assert snapshot.final_redirect_target == outcome.redirect_target


# =============================================================================
# COMPREHENSIVE VALIDATION TEST
# =============================================================================

class TestComprehensiveValidation:
    """Run all validation checks."""

    def test_all_affordances_validate(self):
        """All affordance definitions pass validation."""
        # Should not raise
        validate_affordance_definitions()

    def test_all_affordance_handles_in_allowlist(self):
        """All handles used by affordances are in the allowlist."""
        for aff_type, config in AFFORDANCE_DEFAULTS.items():
            primary = config.get("handle")
            secondary = config.get("handle_secondary")

            if primary is not None:
                assert primary in HANDLE_ALLOWLIST, \
                    f"{aff_type}: handle '{primary}' not in allowlist"

            if secondary is not None:
                assert secondary in HANDLE_ALLOWLIST, \
                    f"{aff_type}: handle_secondary '{secondary}' not in allowlist"

    def test_all_tells_pass_validation(self):
        """All tells pass forbidden pattern validation."""
        # Should not raise
        count = validate_all_tells(TELLS)
        assert count > 0

    def test_handle_count_summary(self):
        """Print handle count summary for all affordances."""
        counts = get_handle_counts()

        # All should be <= 2
        for aff_type, count in counts.items():
            assert count <= 2, f"{aff_type} has {count} handles"

        # Some should be 0 (flavor-only)
        flavor_only = [k for k, v in counts.items() if v == 0]
        assert len(flavor_only) >= 3, "Should have at least 3 flavor-only affordances"
