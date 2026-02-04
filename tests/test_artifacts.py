"""
Tests for artifact pressure system.

See world/affinity/artifacts.py for implementation.
"""

import time

from world.affinity.core import Artifact, BearerRecord, PressureRule
from world.affinity.artifacts import (
    update_bearer_trace,
    evaluate_pressure,
    compute_influence,
    get_bearer_history,
    set_current_bearer,
)


def create_test_artifact():
    """Create a basic test artifact."""
    return Artifact(
        artifact_id="cursed_ring",
        name="Cursed Ring",
        description="A ring that binds to its bearer",
        origin_tags={"ancient", "cursed"},
        valuation_profile={"harm": 0.5, "power": 0.8},
    )


def test_update_bearer_trace_creates_record():
    """First bearer update should create bearer record."""
    artifact = create_test_artifact()
    now = time.time()

    update_bearer_trace(artifact, "actor_1", elapsed_seconds=3600, now=now)

    assert "actor_1" in artifact.bearer_traces
    record = artifact.bearer_traces["actor_1"]
    assert record.bearer_id == "actor_1"
    assert record.accumulated_time == 3600
    assert record.last_carried == now


def test_update_bearer_trace_accumulates_time():
    """Multiple updates should accumulate time."""
    artifact = create_test_artifact()
    now = time.time()

    # First update
    update_bearer_trace(artifact, "actor_1", elapsed_seconds=3600, now=now)

    # Second update
    update_bearer_trace(artifact, "actor_1", elapsed_seconds=7200, now=now + 7200)

    record = artifact.bearer_traces["actor_1"]
    assert record.accumulated_time == 3600 + 7200  # 10800 seconds = 3 hours


def test_influence_grows_with_time():
    """Influence should grow as bearer carries artifact longer."""
    artifact = create_test_artifact()
    now = time.time()

    # Carry for 1 hour (should have minimal influence)
    update_bearer_trace(artifact, "actor_1", elapsed_seconds=3600, now=now)
    influence_1h = artifact.bearer_traces["actor_1"].intensity

    # Carry for additional 6 hours (7 hours total)
    update_bearer_trace(artifact, "actor_1", elapsed_seconds=6 * 3600, now=now + 6 * 3600)
    influence_7h = artifact.bearer_traces["actor_1"].intensity

    assert influence_7h > influence_1h
    assert 0.0 <= influence_1h <= 1.0
    assert 0.0 <= influence_7h <= 1.0


def test_influence_maxes_at_one():
    """Influence should not exceed 1.0."""
    artifact = create_test_artifact()
    now = time.time()

    # Carry for 30 days (well beyond 7-day max)
    update_bearer_trace(artifact, "actor_1", elapsed_seconds=30 * 86400, now=now)

    influence = artifact.bearer_traces["actor_1"].intensity
    assert influence == 1.0


def test_multiple_bearers_tracked_independently():
    """Different bearers should have independent records."""
    artifact = create_test_artifact()
    now = time.time()

    update_bearer_trace(artifact, "actor_1", elapsed_seconds=3600, now=now)
    update_bearer_trace(artifact, "actor_2", elapsed_seconds=7200, now=now)

    assert "actor_1" in artifact.bearer_traces
    assert "actor_2" in artifact.bearer_traces
    assert artifact.bearer_traces["actor_1"].accumulated_time == 3600
    assert artifact.bearer_traces["actor_2"].accumulated_time == 7200


def test_evaluate_pressure_returns_none_for_no_bearer():
    """Pressure should not trigger for non-bearer."""
    artifact = create_test_artifact()
    artifact.pressure_vectors.append(
        PressureRule(
            trigger="bearer_action",
            condition="any",
            effect_type="desire_amplification",
            intensity_base=0.5,
            scales_with_influence=False,
            cooldown_seconds=3600,
            severity_clamp=0.3,
        )
    )

    result = evaluate_pressure(artifact, "unknown_actor", {})

    assert result is None


def test_evaluate_pressure_returns_rule_for_bearer():
    """Pressure should trigger for bearer with sufficient influence."""
    artifact = create_test_artifact()
    now = time.time()

    # Add pressure rule
    rule = PressureRule(
        trigger="bearer_action",
        condition="any",
        effect_type="desire_amplification",
        intensity_base=0.5,
        scales_with_influence=False,  # Don't require influence for this test
        cooldown_seconds=3600,
        severity_clamp=0.3,
    )
    artifact.pressure_vectors.append(rule)

    # Create bearer record
    update_bearer_trace(artifact, "actor_1", elapsed_seconds=3600, now=now)

    result = evaluate_pressure(artifact, "actor_1", {}, now=now)

    assert result is not None
    assert result.effect_type == "desire_amplification"


def test_pressure_requires_influence_when_scaled():
    """Pressure with scales_with_influence should require minimum influence."""
    artifact = create_test_artifact()
    now = time.time()

    # Add pressure rule that requires influence
    rule = PressureRule(
        trigger="bearer_action",
        condition="any",
        effect_type="fatigue_timing",
        intensity_base=0.5,
        scales_with_influence=True,  # Requires influence
        cooldown_seconds=3600,
        severity_clamp=0.3,
    )
    artifact.pressure_vectors.append(rule)

    # Create bearer with minimal time (low influence)
    update_bearer_trace(artifact, "actor_1", elapsed_seconds=60, now=now)  # 1 minute

    result = evaluate_pressure(artifact, "actor_1", {}, now=now)

    # Should not trigger because influence too low
    assert result is None


def test_compute_influence():
    """compute_influence should return bearer intensity."""
    artifact = create_test_artifact()
    now = time.time()

    update_bearer_trace(artifact, "actor_1", elapsed_seconds=7 * 86400, now=now)  # 7 days

    influence = compute_influence(artifact, "actor_1", now)

    assert influence == 1.0


def test_compute_influence_no_bearer():
    """compute_influence should return 0 for non-bearer."""
    artifact = create_test_artifact()

    influence = compute_influence(artifact, "unknown_actor")

    assert influence == 0.0


def test_get_bearer_history():
    """get_bearer_history should return bearer record if exists."""
    artifact = create_test_artifact()
    now = time.time()

    update_bearer_trace(artifact, "actor_1", elapsed_seconds=3600, now=now)

    history = get_bearer_history(artifact, "actor_1")

    assert history is not None
    assert history.bearer_id == "actor_1"
    assert history.accumulated_time == 3600


def test_get_bearer_history_none_for_unknown():
    """get_bearer_history should return None for unknown bearer."""
    artifact = create_test_artifact()

    history = get_bearer_history(artifact, "unknown_actor")

    assert history is None


def test_set_current_bearer():
    """set_current_bearer should update current bearer."""
    artifact = create_test_artifact()
    now = time.time()

    set_current_bearer(artifact, "actor_1", now)

    assert artifact.current_bearer == "actor_1"
    assert "actor_1" in artifact.bearer_traces


def test_set_current_bearer_to_none():
    """set_current_bearer with None should clear current bearer."""
    artifact = create_test_artifact()
    now = time.time()

    set_current_bearer(artifact, "actor_1", now)
    set_current_bearer(artifact, None, now)

    assert artifact.current_bearer is None


def test_pressure_rule_properties():
    """PressureRule should have all required properties."""
    rule = PressureRule(
        trigger="bearer_state",
        condition="low_health",
        effect_type="dependency_curve",
        intensity_base=0.7,
        scales_with_influence=True,
        cooldown_seconds=14400,  # 4 hours
        severity_clamp=0.25,
    )

    assert rule.trigger == "bearer_state"
    assert rule.condition == "low_health"
    assert rule.effect_type == "dependency_curve"
    assert rule.intensity_base == 0.7
    assert rule.scales_with_influence is True
    assert rule.cooldown_seconds == 14400
    assert rule.severity_clamp == 0.25


def test_artifact_can_have_multiple_pressure_vectors():
    """Artifact should support multiple pressure rules."""
    artifact = create_test_artifact()

    artifact.pressure_vectors.append(
        PressureRule(
            trigger="bearer_action",
            condition="combat",
            effect_type="desire_amplification",
            intensity_base=0.5,
            scales_with_influence=True,
            cooldown_seconds=3600,
            severity_clamp=0.3,
        )
    )

    artifact.pressure_vectors.append(
        PressureRule(
            trigger="bearer_state",
            condition="resting",
            effect_type="fatigue_timing",
            intensity_base=0.4,
            scales_with_influence=False,
            cooldown_seconds=7200,
            severity_clamp=0.2,
        )
    )

    assert len(artifact.pressure_vectors) == 2
