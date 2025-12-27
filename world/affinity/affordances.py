"""
Affordance pipeline: AffordanceContext → AffordanceOutcome

See docs/affinity_spec.md §5 for specification.
See docs/DO_NOT.md for hard constraints.
"""

import random
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from world.affinity.core import (
    Location,
    TraceRecord,
    AffordanceConfig,
)
from world.affinity.computation import (
    compute_affinity,
    get_threshold_label,
    get_decayed_value,
    get_valuation,
)
from world.affinity.config import get_config


@dataclass
class TraceContribution:
    """
    A single trace's contribution to an affordance trigger.
    Used for admin debugging.

    See spec §6.4
    """
    channel: str           # "personal", "group", "behavior"
    trace_key: str         # String representation of the key
    decayed_value: float   # Value at trigger time
    valuation: float       # From entity's profile
    weighted_contribution: float


@dataclass
class AffordanceTriggerLog:
    """
    Admin-only log of an affordance trigger.

    See spec §6.4
    """
    timestamp: float
    location_id: str
    actor_id: str
    affordance_type: str
    effect_applied: Optional[str]
    severity: float
    contributing_traces: List[TraceContribution]
    computed_affinity: float
    threshold_crossed: str


@dataclass
class AffordanceSnapshot:
    """
    Complete state for deterministic replay.

    MUST include everything needed to reproduce the exact computation.
    See spec §6.4, docs/DO_NOT.md #6

    Store this with each AffordanceTriggerLog.
    """
    # Input state at trigger time
    actor_id: str
    actor_tags: Set[str]
    location_id: str

    # Trace state (frozen at trigger time)
    personal_traces: Dict[Tuple[str, str], TraceRecord]
    group_traces: Dict[Tuple[str, str], TraceRecord]
    behavior_traces: Dict[str, TraceRecord]

    # Entity config (frozen)
    valuation_profile: Dict[str, float]
    half_lives_personal: float
    half_lives_group: float
    half_lives_behavior: float
    channel_weight_personal: float
    channel_weight_group: float
    channel_weight_behavior: float
    affinity_scale: float

    # Random seed if any stochastic elements
    random_seed: Optional[int]

    # Computed results (for verification)
    computed_affinity: float
    threshold_crossed: str
    affordance_triggered: Optional[str]


@dataclass
class AffordanceContext:
    """
    Input to affordance evaluation.

    See spec §5.6
    """
    actor_id: str
    actor_tags: Set[str]
    location: Location
    action_type: str               # What the actor is doing
    action_target: Optional[str]   # Target of action, if any
    timestamp: float = field(default_factory=time.time)


@dataclass
class AffordanceOutcome:
    """
    Output from affordance evaluation.

    See spec §5.6, docs/contract_examples.md §3
    """
    # Mechanical adjustments (handle → delta)
    # Max 2 handles per affordance (see DO_NOT.md #3)
    adjustments: Dict[str, float]

    # Narrative tells (strings for player-facing output)
    # NO meters, NO numbers, NO "forest says..." (see DO_NOT.md #2, #5)
    tells: List[str]

    # Admin trace payload (for debugging)
    trace: AffordanceTriggerLog

    # Snapshot for deterministic replay
    snapshot: AffordanceSnapshot

    # Cooldown tokens consumed
    cooldowns_consumed: List[str]

    # Whether any affordance actually fired
    triggered: bool


def _is_cooldown_active(location: Location, cooldown_key: str) -> bool:
    """Check if a cooldown is still active."""
    if cooldown_key not in location.cooldowns:
        return False
    return location.cooldowns[cooldown_key] > time.time()


def _consume_cooldown(
    location: Location,
    cooldown_key: str,
    cooldown_seconds: int
) -> None:
    """Consume a cooldown, setting its expiry."""
    location.cooldowns[cooldown_key] = time.time() + cooldown_seconds


def _compute_contributing_traces(
    location: Location,
    actor_id: str,
    actor_tags: Set[str]
) -> List[TraceContribution]:
    """
    Compute which traces contributed most to the affinity.
    Used for admin debugging.
    """
    contributions = []
    config = get_config()
    profile = location.valuation_profile

    # Personal channel
    personal_half_life = config.half_lives.location.personal * 86400
    for (trace_actor_id, event_type), trace in location.personal_traces.items():
        if trace_actor_id != actor_id:
            continue
        decayed = get_decayed_value(trace, personal_half_life)
        valuation = get_valuation(profile, event_type)
        weighted = decayed * valuation * config.channel_weights.personal
        contributions.append(TraceContribution(
            channel="personal",
            trace_key=f"({trace_actor_id}, {event_type})",
            decayed_value=decayed,
            valuation=valuation,
            weighted_contribution=weighted
        ))

    # Group channel
    group_half_life = config.half_lives.location.group * 86400
    for (trace_tag, event_type), trace in location.group_traces.items():
        if trace_tag not in actor_tags:
            continue
        decayed = get_decayed_value(trace, group_half_life)
        valuation = get_valuation(profile, event_type)
        weighted = decayed * valuation * config.channel_weights.group
        contributions.append(TraceContribution(
            channel="group",
            trace_key=f"({trace_tag}, {event_type})",
            decayed_value=decayed,
            valuation=valuation,
            weighted_contribution=weighted
        ))

    # Behavior channel
    behavior_half_life = config.half_lives.location.behavior * 86400
    for event_type, trace in location.behavior_traces.items():
        decayed = get_decayed_value(trace, behavior_half_life)
        valuation = get_valuation(profile, event_type)
        weighted = decayed * valuation * config.channel_weights.behavior
        contributions.append(TraceContribution(
            channel="behavior",
            trace_key=event_type,
            decayed_value=decayed,
            valuation=valuation,
            weighted_contribution=weighted
        ))

    # Sort by absolute contribution
    contributions.sort(key=lambda c: abs(c.weighted_contribution), reverse=True)

    return contributions[:10]  # Top 10


def _create_snapshot(
    ctx: AffordanceContext,
    affinity: float,
    threshold: str,
    affordance_type: Optional[str],
    random_seed: Optional[int] = None
) -> AffordanceSnapshot:
    """
    Create a snapshot for deterministic replay.

    See DO_NOT.md #6: Snapshot = frozen state = deterministic verification.
    """
    config = get_config()

    return AffordanceSnapshot(
        actor_id=ctx.actor_id,
        actor_tags=set(ctx.actor_tags),  # Copy
        location_id=ctx.location.location_id,

        # Deep copy traces so snapshot is frozen
        personal_traces=deepcopy(ctx.location.personal_traces),
        group_traces=deepcopy(ctx.location.group_traces),
        behavior_traces=deepcopy(ctx.location.behavior_traces),

        valuation_profile=dict(ctx.location.valuation_profile),

        # Frozen config
        half_lives_personal=config.half_lives.location.personal * 86400,
        half_lives_group=config.half_lives.location.group * 86400,
        half_lives_behavior=config.half_lives.location.behavior * 86400,
        channel_weight_personal=config.channel_weights.personal,
        channel_weight_group=config.channel_weights.group,
        channel_weight_behavior=config.channel_weights.behavior,
        affinity_scale=config.affinity_scale,

        random_seed=random_seed,

        computed_affinity=affinity,
        threshold_crossed=threshold,
        affordance_triggered=affordance_type
    )


def _evaluate_pathing(
    ctx: AffordanceContext,
    affordance_config: AffordanceConfig,
    affinity: float,
    threshold: str
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """
    Evaluate the pathing affordance.

    See spec §5.1: Pathing
    - Handle: room.travel_time_modifier
    - Hostile: paths twist, travel takes longer
    - Favorable: shortcuts appear, travel is swift
    """
    adjustments = {}
    tells = []
    effect = None

    # Check threshold
    if threshold == "hostile":
        # +50% max, scaled by how hostile
        severity = min(
            affordance_config.severity_clamp_hostile,
            abs(affinity) * affordance_config.severity_clamp_hostile / 0.7
        )
        adjustments[affordance_config.mechanical_handle] = severity
        tells.append(random.choice(affordance_config.tells_hostile))
        effect = "slow"

    elif threshold == "unwelcoming":
        # Smaller effect for unwelcoming
        severity = min(
            affordance_config.severity_clamp_hostile * 0.5,
            abs(affinity) * affordance_config.severity_clamp_hostile / 0.7
        )
        adjustments[affordance_config.mechanical_handle] = severity
        tells.append(random.choice(affordance_config.tells_hostile))
        effect = "slow"

    elif threshold == "favorable":
        # Negative modifier = faster travel
        severity = max(
            affordance_config.severity_clamp_favorable,
            -abs(affinity) * abs(affordance_config.severity_clamp_favorable) / 0.7
        )
        adjustments[affordance_config.mechanical_handle] = severity
        tells.append(random.choice(affordance_config.tells_favorable))
        effect = "swift"

    elif threshold == "aligned":
        # Full favorable effect
        adjustments[affordance_config.mechanical_handle] = affordance_config.severity_clamp_favorable
        tells.append(random.choice(affordance_config.tells_favorable))
        effect = "swift"

    # Neutral: no effect
    return adjustments, tells, effect


def evaluate_affordances(ctx: AffordanceContext) -> AffordanceOutcome:
    """
    Single entry point for all affordance checks.

    See spec §5.6:
    1. Compute affinity for actor in location
    2. Check thresholds
    3. Check cooldowns
    4. Apply severity clamps
    5. Return mechanical + narrative + trace

    Args:
        ctx: The affordance context

    Returns:
        AffordanceOutcome with adjustments, tells, trace, and snapshot
    """
    # 1. Compute affinity
    affinity = compute_affinity(
        ctx.location,
        ctx.actor_id,
        ctx.actor_tags
    )

    # 2. Check threshold
    threshold = get_threshold_label(affinity)

    # Compute contributing traces for debugging
    contributions = _compute_contributing_traces(
        ctx.location,
        ctx.actor_id,
        ctx.actor_tags
    )

    # Initialize outcome
    all_adjustments = {}
    all_tells = []
    all_cooldowns = []
    triggered = False
    triggered_affordance = None

    # 3-4. Evaluate each enabled affordance
    for aff_config in ctx.location.affordances:
        if not aff_config.enabled:
            continue

        # Check cooldown
        cooldown_key = f"{aff_config.affordance_type}:{ctx.actor_id}:{ctx.location.location_id}"
        if _is_cooldown_active(ctx.location, cooldown_key):
            continue

        # Evaluate based on affordance type
        if aff_config.affordance_type == "pathing":
            adjustments, tells, effect = _evaluate_pathing(
                ctx, aff_config, affinity, threshold
            )

            if adjustments:
                # Consume cooldown
                _consume_cooldown(ctx.location, cooldown_key, aff_config.cooldown_seconds)
                all_cooldowns.append(cooldown_key)

                # Merge results (max 2 handles enforced by config validation)
                all_adjustments.update(adjustments)
                all_tells.extend(tells)
                triggered = True
                triggered_affordance = aff_config.affordance_type

    # 5. Build trace log
    trace = AffordanceTriggerLog(
        timestamp=ctx.timestamp,
        location_id=ctx.location.location_id,
        actor_id=ctx.actor_id,
        affordance_type=triggered_affordance or "none",
        effect_applied=triggered_affordance,
        severity=list(all_adjustments.values())[0] if all_adjustments else 0.0,
        contributing_traces=contributions,
        computed_affinity=affinity,
        threshold_crossed=threshold
    )

    # Create snapshot for replay
    snapshot = _create_snapshot(
        ctx,
        affinity,
        threshold,
        triggered_affordance
    )

    return AffordanceOutcome(
        adjustments=all_adjustments,
        tells=all_tells,
        trace=trace,
        snapshot=snapshot,
        cooldowns_consumed=all_cooldowns,
        triggered=triggered
    )


def replay_from_snapshot(snapshot: AffordanceSnapshot) -> float:
    """
    Replay affinity computation from a frozen snapshot.

    MUST return identical result to original computation.
    See DO_NOT.md #6: Non-deterministic replay is forbidden.

    Args:
        snapshot: Frozen state at trigger time

    Returns:
        Recomputed affinity (must match snapshot.computed_affinity)
    """
    from world.affinity.computation import (
        score_personal,
        score_group,
        score_behavior,
    )
    import math

    # Use ONLY snapshot data, never current state
    personal = score_personal(
        snapshot.personal_traces,
        snapshot.actor_id,
        snapshot.half_lives_personal,
        snapshot.valuation_profile
    )

    group = score_group(
        snapshot.group_traces,
        snapshot.actor_tags,
        snapshot.half_lives_group,
        snapshot.valuation_profile
    )

    behavior = score_behavior(
        snapshot.behavior_traces,
        snapshot.half_lives_behavior,
        snapshot.valuation_profile
    )

    raw = (
        snapshot.channel_weight_personal * personal +
        snapshot.channel_weight_group * group +
        snapshot.channel_weight_behavior * behavior
    )

    return math.tanh(raw / snapshot.affinity_scale)
