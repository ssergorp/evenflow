"""
Artifact pressure system.

See docs/affinity_spec.md §5.2
"""

from typing import Dict, Optional
import time

from world.affinity.core import Artifact, BearerRecord, PressureRule
from world.affinity.config import get_config


def update_bearer_trace(
    artifact: Artifact,
    bearer_id: str,
    elapsed_seconds: float,
    now: Optional[float] = None
) -> None:
    """
    Update bearer trace when artifact is carried.

    Tracks accumulated time and influence buildup.

    Args:
        artifact: Artifact being carried
        bearer_id: ID of bearer
        elapsed_seconds: Time elapsed since last update
        now: Current timestamp

    See docs/affinity_spec.md §2.3
    """
    if now is None:
        now = time.time()

    if bearer_id not in artifact.bearer_traces:
        artifact.bearer_traces[bearer_id] = BearerRecord(
            bearer_id=bearer_id,
            accumulated_time=0.0,
            last_carried=now,
            intensity=0.0,
        )

    record = artifact.bearer_traces[bearer_id]
    record.accumulated_time += elapsed_seconds
    record.last_carried = now

    # Influence grows with time
    # Simple curve: reaches max (1.0) after 7 days
    # TODO: More sophisticated influence curve based on artifact properties
    record.intensity = min(1.0, record.accumulated_time / (7 * 86400))


def evaluate_pressure(
    artifact: Artifact,
    bearer_id: str,
    action_context: Dict,
    now: Optional[float] = None
) -> Optional[PressureRule]:
    """
    Evaluate if any pressure rule should trigger.

    Checks bearer record and pressure vectors to determine
    if artifact should exert influence.

    Args:
        artifact: Artifact potentially exerting pressure
        bearer_id: ID of bearer
        action_context: Context about current action/state
        now: Current timestamp

    Returns:
        PressureRule if triggered, None otherwise

    See docs/affinity_spec.md §5.2
    """
    if now is None:
        now = time.time()

    if bearer_id not in artifact.bearer_traces:
        return None

    bearer_record = artifact.bearer_traces[bearer_id]

    for rule in artifact.pressure_vectors:
        # Check cooldown
        # TODO: Add cooldown tracking per rule
        # For now, simplified: assume cooldowns are tracked elsewhere

        # Check condition
        # TODO: Implement condition evaluation
        # For now, simplified: match trigger type
        if rule.trigger == "bearer_action":
            # Check if action type matches condition
            # Simplified: always match for now
            pass
        elif rule.trigger == "bearer_state":
            # Check bearer state
            pass
        elif rule.trigger == "proximity":
            # Check proximity conditions
            pass

        # Check if influence is high enough
        if rule.scales_with_influence and bearer_record.intensity < 0.1:
            # Not enough influence yet
            continue

        # For MVP: return first matching rule
        # Full implementation would evaluate all conditions and pick best match
        return rule

    return None


def compute_influence(
    artifact: Artifact,
    bearer_id: str,
    now: Optional[float] = None
) -> float:
    """
    Compute current influence level on bearer.

    Influence grows with exposure time and can affect pressure intensity.

    Args:
        artifact: Artifact exerting influence
        bearer_id: ID of bearer
        now: Current timestamp

    Returns:
        Influence level (0.0-1.0)
    """
    if now is None:
        now = time.time()

    if bearer_id not in artifact.bearer_traces:
        return 0.0

    return artifact.bearer_traces[bearer_id].intensity


def get_bearer_history(
    artifact: Artifact,
    bearer_id: str
) -> Optional[BearerRecord]:
    """
    Get bearer history for artifact.

    Args:
        artifact: Artifact to query
        bearer_id: ID of bearer

    Returns:
        BearerRecord if exists, None otherwise
    """
    return artifact.bearer_traces.get(bearer_id)


def set_current_bearer(
    artifact: Artifact,
    bearer_id: Optional[str],
    now: Optional[float] = None
) -> None:
    """
    Set current bearer of artifact.

    Updates current_bearer field and initializes bearer record if needed.

    Args:
        artifact: Artifact being carried
        bearer_id: ID of new bearer (None if dropped)
        now: Current timestamp
    """
    if now is None:
        now = time.time()

    artifact.current_bearer = bearer_id

    if bearer_id and bearer_id not in artifact.bearer_traces:
        artifact.bearer_traces[bearer_id] = BearerRecord(
            bearer_id=bearer_id,
            accumulated_time=0.0,
            last_carried=now,
            intensity=0.0,
        )
