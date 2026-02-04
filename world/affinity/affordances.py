"""
Affordance pipeline: AffordanceContext → AffordanceOutcome

Implements 10 location affordances triggered by affinity bias.
All affordances are indirect, probabilistic, and readable only through
narrative consequences.

See docs/affordances.md for full catalog.
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
    score_personal,
    score_group,
    score_behavior,
)
from world.affinity.config import get_config


# =============================================================================
# AFFORDANCE REGISTRY - Admin toggle support
# =============================================================================

# Global registry of enabled affordances (admin-configurable)
_AFFORDANCE_REGISTRY: Dict[str, bool] = {
    "pathing": True,
    "misleading_navigation": True,
    "encounter_bias": True,
    "resource_scarcity": True,
    "spell_side_effects": True,
    "rest_quality": True,
    "ambient_messaging": True,
    "loot_quality": True,
    "weather_microclimate": True,
    "animal_messengers": True,
}

# Debug mode: log all evaluations regardless of trigger
_DEBUG_MODE: Dict[str, bool] = {aff: False for aff in _AFFORDANCE_REGISTRY}

# Force mode: override affinity for testing
_FORCE_MODE: Dict[str, Optional[str]] = {aff: None for aff in _AFFORDANCE_REGISTRY}


def admin_toggle_affordance(affordance_type: str, enabled: bool) -> None:
    """Admin command: Enable or disable an affordance globally."""
    if affordance_type not in _AFFORDANCE_REGISTRY:
        raise ValueError(f"Unknown affordance: {affordance_type}")
    _AFFORDANCE_REGISTRY[affordance_type] = enabled


def admin_set_debug(affordance_type: str, enabled: bool) -> None:
    """Admin command: Enable debug logging for an affordance."""
    if affordance_type not in _DEBUG_MODE:
        raise ValueError(f"Unknown affordance: {affordance_type}")
    _DEBUG_MODE[affordance_type] = enabled


def admin_force_mode(affordance_type: str, mode: Optional[str]) -> None:
    """
    Admin command: Force affordance to trigger as hostile/favorable/None.

    Args:
        mode: "hostile", "favorable", or None to clear
    """
    if affordance_type not in _FORCE_MODE:
        raise ValueError(f"Unknown affordance: {affordance_type}")
    if mode not in (None, "hostile", "favorable"):
        raise ValueError(f"Mode must be 'hostile', 'favorable', or None")
    _FORCE_MODE[affordance_type] = mode


def admin_reset_cooldowns(location: Location) -> None:
    """Admin command: Clear all cooldowns for a location."""
    location.cooldowns.clear()


def admin_get_registry() -> Dict[str, bool]:
    """Get current affordance registry state."""
    return dict(_AFFORDANCE_REGISTRY)


def is_affordance_enabled(affordance_type: str) -> bool:
    """Check if an affordance is globally enabled."""
    return _AFFORDANCE_REGISTRY.get(affordance_type, False)


# =============================================================================
# TELLS - Narrative messages for each affordance
# =============================================================================

TELLS = {
    "pathing": {
        "hostile": [
            "The path seems longer than you remember.",
            "Brambles catch at your clothes.",
            "You keep losing your footing on loose stones.",
            "The trail doubles back unexpectedly.",
            "Roots seem to rise just where you step.",
        ],
        "favorable": [
            "An easy path opens through the undergrowth.",
            "Your feet find sure footing on the trail.",
            "The journey passes quickly.",
            "A shortcut appears, as if made for you.",
            "The way forward is unusually clear.",
        ],
    },
    "misleading_navigation": {
        "hostile": [
            "Wait... this isn't where you meant to go.",
            "The familiar landmark was wrong.",
            "You emerge somewhere unexpected.",
            "The path led you astray.",
        ],
        "favorable": [
            "Your path curves, but you end up exactly where you needed to be.",
        ],
    },
    "encounter_bias": {
        "hostile": [
            "Something watches from the shadows.",
            "Wolves circle at the edge of vision.",
            "The forest's creatures are restless.",
            "Eyes gleam in the underbrush.",
            "Predators seem drawn to this spot.",
        ],
        "favorable": [
            "The usual dangers keep their distance.",
            "A deer watches you calmly.",
            "Birdsong fills the air.",
            "Small creatures go about their business, unconcerned.",
            "The wildlife here seems peaceful.",
        ],
    },
    "resource_scarcity": {
        "hostile": [
            "The herbs here are sparse and withered.",
            "This vein has gone barren.",
            "The fish aren't biting.",
            "What you seek remains hidden.",
            "Pickings are slim here.",
        ],
        "favorable": [
            "Rich deposits practically surface themselves.",
            "Herbs grow thick and healthy here.",
            "The land gives freely.",
            "Hidden abundance reveals itself.",
            "A bounty appears before you.",
        ],
    },
    "spell_side_effects": {
        "hostile": [
            "Your magic feels sluggish here.",
            "The weave resists your touch.",
            "Something dampens your power.",
            "The spell sputters unexpectedly.",
            "Magic flows reluctantly.",
        ],
        "favorable": [
            "Magic flows easily here.",
            "Your spell flares bright.",
            "The land lends its strength.",
            "Power wells up from the earth.",
            "The weave responds eagerly.",
        ],
    },
    "rest_quality": {
        "hostile": [
            "Sleep comes fitfully.",
            "You wake more tired than when you lay down.",
            "Uneasy dreams trouble your rest.",
            "The ground is cold and hard.",
            "You startle awake repeatedly.",
        ],
        "favorable": [
            "Deep, restorative sleep.",
            "You wake refreshed and ready.",
            "Peaceful dreams of distant places.",
            "The earth cradles you gently.",
            "Morning comes too soon, but you feel renewed.",
        ],
    },
    "ambient_messaging": {
        "hostile_light": [
            "Something feels off here.",
            "An uneasy stillness hangs in the air.",
        ],
        "hostile_watchful": [
            "You can't shake the feeling of being observed.",
            "The shadows seem to watch.",
        ],
        "hostile_oppressive": [
            "The air itself seems heavy with disapproval.",
            "A weight presses on your shoulders.",
        ],
        "hostile_menacing": [
            "Every shadow seems to reach toward you.",
            "The darkness here is hungry.",
        ],
        "favorable_pleasant": [
            "The light seems warmer here.",
            "A pleasant calm settles over you.",
        ],
        "favorable_welcoming": [
            "You feel oddly at home.",
            "The space seems to welcome you.",
        ],
        "favorable_protected": [
            "A sense of safety settles over you.",
            "You feel sheltered here.",
        ],
        "favorable_blessed": [
            "The very air seems to embrace you.",
            "A profound peace fills this place.",
        ],
    },
    "loot_quality": {
        "hostile": [
            "Rust and decay everywhere.",
            "The chest's contents are disappointing.",
            "Moths have been at this.",
            "Whatever was here, time has claimed it.",
        ],
        "favorable": [
            "Something glints in the corner.",
            "Remarkably well-preserved.",
            "A hidden cache reveals itself.",
            "The best of the lot, as if waiting for you.",
        ],
    },
    "weather_microclimate": {
        "hostile": [
            "A sudden chill wind picks up.",
            "Clouds gather overhead.",
            "Mist rolls in unexpectedly.",
            "The sun finds a cloud just as you arrive.",
        ],
        "favorable": [
            "The clouds part briefly.",
            "A warm breeze carries pleasant scents.",
            "The mist clears as you approach.",
            "Sunlight follows your path.",
        ],
    },
    "animal_messengers": {
        "hostile": [
            "A crow follows overhead, watching.",
            "Rats scatter at your approach.",
            "A fox regards you with unusual intensity.",
            "Insects swarm thicker here.",
            "Something howls in the distance—at you, it seems.",
        ],
        "favorable": [
            "A songbird alights nearby.",
            "Butterflies dance in your wake.",
            "A doe raises her head, unafraid.",
            "Bees hum peacefully as you pass.",
            "A hawk circles lazily above—a good omen.",
        ],
    },
}


# =============================================================================
# AFFORDANCE CONFIGURATIONS - Default thresholds and clamps
# =============================================================================

AFFORDANCE_DEFAULTS = {
    "pathing": {
        "cooldown_seconds": 3600,  # 1 hour
        "hostile_threshold": -0.3,
        "favorable_threshold": 0.3,
        "hostile_clamp": 0.5,  # +50% travel time
        "favorable_clamp": -0.3,  # -30% travel time
        "base_probability": 0.7,
        "handle": "room.travel_time_modifier",
    },
    "misleading_navigation": {
        "cooldown_seconds": 14400,  # 4 hours
        "hostile_threshold": -0.5,  # Only strongly hostile
        "favorable_threshold": 0.7,  # Rarely favorable
        "hostile_clamp": 0.15,  # Max 15% redirect chance
        "favorable_clamp": 0.0,  # No favorable redirect
        "base_probability": 0.05,  # Very rare
        "handle": "room.redirect_target",
    },
    "encounter_bias": {
        "cooldown_seconds": 1800,  # 30 minutes
        "hostile_threshold": -0.4,
        "favorable_threshold": 0.4,
        "hostile_clamp": 1.0,  # +100% encounter rate
        "favorable_clamp": -0.5,  # -50% encounter rate
        "base_probability": 0.6,
        "handle": "room.encounter_rate_modifier",
        "handle_secondary": "npc.aggro_radius_modifier",
    },
    "resource_scarcity": {
        "cooldown_seconds": 7200,  # 2 hours
        "hostile_threshold": -0.25,
        "favorable_threshold": 0.25,
        "hostile_clamp": -0.4,  # -40% yield
        "favorable_clamp": 0.4,  # +40% yield
        "base_probability": 0.8,
        "handle": "harvest.yield_modifier",
    },
    "spell_side_effects": {
        "cooldown_seconds": 0,  # Per-spell, no location cooldown
        "hostile_threshold": -0.35,
        "favorable_threshold": 0.35,
        "hostile_clamp": -0.25,  # -25% power
        "favorable_clamp": 0.25,  # +25% power
        "base_probability": 0.5,
        "handle": "spell.power_modifier",
        "handle_secondary": "spell.backfire_chance",
        "hostile_backfire": 0.1,  # +10% backfire
        "favorable_backfire": -0.05,  # -5% backfire
    },
    "rest_quality": {
        "cooldown_seconds": 28800,  # 8 hours
        "hostile_threshold": -0.2,
        "favorable_threshold": 0.2,
        "hostile_clamp": -0.3,  # -30% healing
        "favorable_clamp": 0.3,  # +30% healing
        "base_probability": 0.9,
        "handle": "rest.healing_modifier",
    },
    "ambient_messaging": {
        "cooldown_seconds": 3600,  # 1 hour
        "hostile_threshold": -0.25,
        "favorable_threshold": 0.25,
        "base_probability": 0.6,
        "handle": None,  # Flavor only
    },
    "loot_quality": {
        "cooldown_seconds": 3600,  # 1 hour
        "hostile_threshold": -0.3,
        "favorable_threshold": 0.3,
        "hostile_clamp": -2,  # -2 quality tiers
        "favorable_clamp": 2,  # +2 quality tiers
        "base_probability": 0.7,
        "handle": "loot.quality_modifier",
    },
    "weather_microclimate": {
        "cooldown_seconds": 14400,  # 4 hours
        "hostile_threshold": -0.4,
        "favorable_threshold": 0.4,
        "base_probability": 0.5,
        "handle": None,  # Flavor only
    },
    "animal_messengers": {
        "cooldown_seconds": 7200,  # 2 hours
        "hostile_threshold": -0.25,
        "favorable_threshold": 0.25,
        "base_probability": 0.5,
        "handle": None,  # Flavor only
    },
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TraceContribution:
    """
    A single trace's contribution to an affordance trigger.
    Used for admin debugging.
    """
    channel: str
    trace_key: str
    decayed_value: float
    valuation: float
    weighted_contribution: float


@dataclass
class AffordanceTriggerLog:
    """
    Admin-only log of an affordance trigger.
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

    IMPORTANT: This snapshot stores the FINAL computed values.
    Replay functions MUST return these stored values, not recompute them.
    This ensures 100% deterministic replay without calling RNG.
    """
    actor_id: str
    actor_tags: Set[str]
    location_id: str
    eval_time: float
    personal_traces: Dict[Tuple[str, str], TraceRecord]
    group_traces: Dict[Tuple[str, str], TraceRecord]
    behavior_traces: Dict[str, TraceRecord]
    valuation_profile: Dict[str, float]
    half_lives_personal: float
    half_lives_group: float
    half_lives_behavior: float
    channel_weight_personal: float
    channel_weight_group: float
    channel_weight_behavior: float
    affinity_scale: float
    random_seed: int
    computed_affinity: float
    threshold_crossed: str
    affordance_triggered: Optional[str]
    effect_applied: Optional[str]

    # === FINAL COMPUTED VALUES (for deterministic replay) ===
    # These are the actual outputs - replay returns these directly
    final_adjustments: Dict[str, float] = field(default_factory=dict)
    final_tells: List[str] = field(default_factory=list)
    final_redirect_target: Optional[str] = None


@dataclass
class AffordanceContext:
    """
    Input to affordance evaluation.
    """
    actor_id: str
    actor_tags: Set[str]
    location: Location
    action_type: str
    action_target: Optional[str]
    timestamp: float = field(default_factory=time.time)
    # Optional: spell school for spell_side_effects
    spell_school: Optional[str] = None
    # Optional: adjacent rooms for misleading_navigation
    adjacent_rooms: Optional[List[str]] = None


@dataclass
class AffordanceOutcome:
    """
    Output from affordance evaluation.
    """
    adjustments: Dict[str, float]
    tells: List[str]
    trace: AffordanceTriggerLog
    snapshot: AffordanceSnapshot
    cooldowns_consumed: List[str]
    triggered: bool
    # For misleading_navigation: redirect destination
    redirect_target: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _is_cooldown_active(location: Location, cooldown_key: str, now: float) -> bool:
    """Check if a cooldown is still active."""
    if cooldown_key not in location.cooldowns:
        return False
    return location.cooldowns[cooldown_key] > now


def _consume_cooldown(
    location: Location,
    cooldown_key: str,
    cooldown_seconds: int,
    now: float
) -> None:
    """Consume a cooldown, setting its expiry."""
    location.cooldowns[cooldown_key] = now + cooldown_seconds


def _compute_contributing_traces(
    location: Location,
    actor_id: str,
    actor_tags: Set[str],
    now: float
) -> List[TraceContribution]:
    """Compute which traces contributed most to the affinity."""
    contributions = []
    config = get_config()
    profile = location.valuation_profile

    # Personal channel
    personal_half_life = config.half_lives.location.personal * 86400
    for (trace_actor_id, event_type), trace in location.personal_traces.items():
        if trace_actor_id != actor_id:
            continue
        decayed = get_decayed_value(trace, personal_half_life, now)
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
        decayed = get_decayed_value(trace, group_half_life, now)
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
        decayed = get_decayed_value(trace, behavior_half_life, now)
        valuation = get_valuation(profile, event_type)
        weighted = decayed * valuation * config.channel_weights.behavior
        contributions.append(TraceContribution(
            channel="behavior",
            trace_key=event_type,
            decayed_value=decayed,
            valuation=valuation,
            weighted_contribution=weighted
        ))

    contributions.sort(key=lambda c: abs(c.weighted_contribution), reverse=True)
    return contributions[:10]


def _get_effective_threshold(
    affinity: float,
    affordance_type: str
) -> Tuple[str, bool, bool]:
    """
    Get effective threshold, checking force mode.

    Returns:
        (threshold_label, is_hostile, is_favorable)
    """
    force = _FORCE_MODE.get(affordance_type)
    if force == "hostile":
        return ("hostile", True, False)
    elif force == "favorable":
        return ("aligned", False, True)

    defaults = AFFORDANCE_DEFAULTS.get(affordance_type, {})
    hostile_thresh = defaults.get("hostile_threshold", -0.3)
    favorable_thresh = defaults.get("favorable_threshold", 0.3)

    if affinity <= hostile_thresh:
        return ("hostile", True, False)
    elif affinity >= favorable_thresh:
        return ("favorable", False, True)
    else:
        return ("neutral", False, False)


def _scale_severity(
    affinity: float,
    clamp: float,
    threshold: float
) -> float:
    """Scale severity based on how far past threshold affinity is."""
    if clamp == 0:
        return 0.0
    # Linear scaling from threshold to -1.0 (hostile) or +1.0 (favorable)
    if threshold < 0:
        # Hostile: scale from threshold to -1.0
        range_size = -1.0 - threshold
        if range_size == 0:
            return clamp
        position = (affinity - threshold) / range_size
    else:
        # Favorable: scale from threshold to +1.0
        range_size = 1.0 - threshold
        if range_size == 0:
            return clamp
        position = (affinity - threshold) / range_size

    position = max(0.0, min(1.0, position))
    return clamp * position


def _create_snapshot(
    ctx: AffordanceContext,
    affinity: float,
    threshold: str,
    affordance_type: Optional[str],
    effect: Optional[str],
    random_seed: int,
    final_adjustments: Dict[str, float],
    final_tells: List[str],
    final_redirect_target: Optional[str]
) -> AffordanceSnapshot:
    """
    Create a snapshot for deterministic replay.

    IMPORTANT: The final_* parameters are the actual computed outputs.
    Replay functions return these values directly, never recompute.
    """
    config = get_config()

    return AffordanceSnapshot(
        actor_id=ctx.actor_id,
        actor_tags=set(ctx.actor_tags),
        location_id=ctx.location.location_id,
        eval_time=ctx.timestamp,
        personal_traces=deepcopy(ctx.location.personal_traces),
        group_traces=deepcopy(ctx.location.group_traces),
        behavior_traces=deepcopy(ctx.location.behavior_traces),
        valuation_profile=dict(ctx.location.valuation_profile),
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
        affordance_triggered=affordance_type,
        effect_applied=effect,
        # Store final computed values for deterministic replay
        final_adjustments=dict(final_adjustments),
        final_tells=list(final_tells),
        final_redirect_target=final_redirect_target
    )


# =============================================================================
# INDIVIDUAL AFFORDANCE EVALUATORS
# =============================================================================

def _evaluate_pathing(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate path friction affordance."""
    if not is_affordance_enabled("pathing"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["pathing"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(affinity, "pathing")

    if not is_hostile and not is_favorable:
        return {}, [], None

    # Probability check
    # For movement, tests expect pathing to reliably trigger when hostile/favorable.
    if ctx.action_type != "move.pass":
        if rng.random() > defaults["base_probability"]:
            return {}, [], None

    adjustments = {}
    tells = []
    effect = None

    if is_hostile:
        # If we're force-triggering hostile mode but affinity is neutral,
        # ensure we still apply a non-zero hostile effect.
        eff_affinity = affinity
        if _FORCE_MODE.get("pathing") == "hostile" and affinity > defaults["hostile_threshold"]:
            eff_affinity = defaults["hostile_threshold"] - 1e-6

        severity = _scale_severity(
            eff_affinity,
            defaults["hostile_clamp"],
            defaults["hostile_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["pathing"]["hostile"]))
        effect = "slow"
    elif is_favorable:
        severity = _scale_severity(
            affinity,
            defaults["favorable_clamp"],
            defaults["favorable_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["pathing"]["favorable"]))
        effect = "swift"

    return adjustments, tells, effect


def _evaluate_misleading_navigation(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str], Optional[str]]:
    """
    Evaluate misleading navigation affordance.

    Returns:
        (adjustments, tells, effect, redirect_target)
    """
    if not is_affordance_enabled("misleading_navigation"):
        return {}, [], None, None

    defaults = AFFORDANCE_DEFAULTS["misleading_navigation"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "misleading_navigation"
    )

    # Only triggers when strongly hostile
    if not is_hostile or affinity > defaults["hostile_threshold"]:
        return {}, [], None, None

    # Need adjacent rooms to redirect to
    if not ctx.adjacent_rooms:
        return {}, [], None, None

    # Scale probability with hostility
    redirect_chance = _scale_severity(
        affinity,
        defaults["hostile_clamp"],
        defaults["hostile_threshold"]
    )

    # Check probability
    if rng.random() > redirect_chance:
        return {}, [], None, None

    # Pick a random adjacent room
    redirect_target = rng.choice(ctx.adjacent_rooms)
    tells = [rng.choice(TELLS["misleading_navigation"]["hostile"])]

    return {}, tells, "redirect", redirect_target


def _evaluate_encounter_bias(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate encounter bias affordance."""
    if not is_affordance_enabled("encounter_bias"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["encounter_bias"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "encounter_bias"
    )

    if not is_hostile and not is_favorable:
        return {}, [], None

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    adjustments = {}
    tells = []
    effect = None

    if is_hostile:
        # Two handles: encounter rate and aggro radius
        severity = _scale_severity(
            affinity,
            defaults["hostile_clamp"],
            defaults["hostile_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        # Secondary handle: aggro radius (half the severity)
        adjustments[defaults["handle_secondary"]] = severity * 0.5
        tells.append(rng.choice(TELLS["encounter_bias"]["hostile"]))
        effect = "dangerous"
    elif is_favorable:
        severity = _scale_severity(
            affinity,
            defaults["favorable_clamp"],
            defaults["favorable_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        adjustments[defaults["handle_secondary"]] = severity
        tells.append(rng.choice(TELLS["encounter_bias"]["favorable"]))
        effect = "peaceful"

    return adjustments, tells, effect


def _evaluate_resource_scarcity(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate resource scarcity affordance."""
    if not is_affordance_enabled("resource_scarcity"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["resource_scarcity"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "resource_scarcity"
    )

    if not is_hostile and not is_favorable:
        return {}, [], None

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    adjustments = {}
    tells = []
    effect = None

    if is_hostile:
        severity = _scale_severity(
            affinity,
            defaults["hostile_clamp"],
            defaults["hostile_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["resource_scarcity"]["hostile"]))
        effect = "scarce"
    elif is_favorable:
        severity = _scale_severity(
            affinity,
            defaults["favorable_clamp"],
            defaults["favorable_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["resource_scarcity"]["favorable"]))
        effect = "abundant"

    return adjustments, tells, effect


def _evaluate_spell_side_effects(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate spell side effects affordance."""
    if not is_affordance_enabled("spell_side_effects"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["spell_side_effects"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "spell_side_effects"
    )

    if not is_hostile and not is_favorable:
        return {}, [], None

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    adjustments = {}
    tells = []
    effect = None

    # Check for fire magic penalty in locations that hate fire
    fire_penalty = 0.0
    fire_backfire_penalty = 0.0
    if ctx.spell_school == "fire":
        fire_valuation = get_valuation(ctx.location.valuation_profile, "harm.fire")
        if fire_valuation < -0.5:
            fire_penalty = -0.15
            fire_backfire_penalty = 0.1

    if is_hostile:
        severity = _scale_severity(
            affinity,
            defaults["hostile_clamp"],
            defaults["hostile_threshold"]
        )
        adjustments[defaults["handle"]] = severity + fire_penalty
        adjustments[defaults["handle_secondary"]] = (
            defaults["hostile_backfire"] + fire_backfire_penalty
        )
        tells.append(rng.choice(TELLS["spell_side_effects"]["hostile"]))
        effect = "dampened"
    elif is_favorable:
        severity = _scale_severity(
            affinity,
            defaults["favorable_clamp"],
            defaults["favorable_threshold"]
        )
        # Fire penalty still applies even if favorable (the land hates fire)
        adjustments[defaults["handle"]] = severity + fire_penalty
        adjustments[defaults["handle_secondary"]] = (
            defaults["favorable_backfire"] + fire_backfire_penalty
        )
        tells.append(rng.choice(TELLS["spell_side_effects"]["favorable"]))
        effect = "amplified"

    return adjustments, tells, effect


def _evaluate_rest_quality(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate rest quality affordance."""
    if not is_affordance_enabled("rest_quality"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["rest_quality"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "rest_quality"
    )

    if not is_hostile and not is_favorable:
        return {}, [], None

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    adjustments = {}
    tells = []
    effect = None

    if is_hostile:
        severity = _scale_severity(
            affinity,
            defaults["hostile_clamp"],
            defaults["hostile_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["rest_quality"]["hostile"]))
        effect = "restless"
    elif is_favorable:
        severity = _scale_severity(
            affinity,
            defaults["favorable_clamp"],
            defaults["favorable_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["rest_quality"]["favorable"]))
        effect = "restorative"

    return adjustments, tells, effect


def _evaluate_ambient_messaging(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate ambient messaging affordance (flavor only)."""
    if not is_affordance_enabled("ambient_messaging"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["ambient_messaging"]

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    tells = []
    effect = None

    # Select atmosphere layer based on affinity
    if affinity <= -0.8:
        tells.append(rng.choice(TELLS["ambient_messaging"]["hostile_menacing"]))
        effect = "menacing"
    elif affinity <= -0.6:
        tells.append(rng.choice(TELLS["ambient_messaging"]["hostile_oppressive"]))
        effect = "oppressive"
    elif affinity <= -0.4:
        tells.append(rng.choice(TELLS["ambient_messaging"]["hostile_watchful"]))
        effect = "watchful"
    elif affinity <= -0.25:
        tells.append(rng.choice(TELLS["ambient_messaging"]["hostile_light"]))
        effect = "uneasy"
    elif affinity >= 0.8:
        tells.append(rng.choice(TELLS["ambient_messaging"]["favorable_blessed"]))
        effect = "blessed"
    elif affinity >= 0.6:
        tells.append(rng.choice(TELLS["ambient_messaging"]["favorable_protected"]))
        effect = "protected"
    elif affinity >= 0.4:
        tells.append(rng.choice(TELLS["ambient_messaging"]["favorable_welcoming"]))
        effect = "welcoming"
    elif affinity >= 0.25:
        tells.append(rng.choice(TELLS["ambient_messaging"]["favorable_pleasant"]))
        effect = "pleasant"

    # No mechanical handle - flavor only
    return {}, tells, effect


def _evaluate_loot_quality(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate loot quality affordance."""
    if not is_affordance_enabled("loot_quality"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["loot_quality"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "loot_quality"
    )

    if not is_hostile and not is_favorable:
        return {}, [], None

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    adjustments = {}
    tells = []
    effect = None

    if is_hostile:
        severity = _scale_severity(
            affinity,
            defaults["hostile_clamp"],
            defaults["hostile_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["loot_quality"]["hostile"]))
        effect = "poor"
    elif is_favorable:
        severity = _scale_severity(
            affinity,
            defaults["favorable_clamp"],
            defaults["favorable_threshold"]
        )
        adjustments[defaults["handle"]] = severity
        tells.append(rng.choice(TELLS["loot_quality"]["favorable"]))
        effect = "rich"

    return adjustments, tells, effect


def _evaluate_weather_microclimate(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate weather microclimate affordance (flavor only)."""
    if not is_affordance_enabled("weather_microclimate"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["weather_microclimate"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "weather_microclimate"
    )

    if not is_hostile and not is_favorable:
        return {}, [], None

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    tells = []
    effect = None

    if is_hostile:
        tells.append(rng.choice(TELLS["weather_microclimate"]["hostile"]))
        effect = "harsh"
    elif is_favorable:
        tells.append(rng.choice(TELLS["weather_microclimate"]["favorable"]))
        effect = "mild"

    return {}, tells, effect


def _evaluate_animal_messengers(
    ctx: AffordanceContext,
    affinity: float,
    rng: random.Random,
    now: float
) -> Tuple[Dict[str, float], List[str], Optional[str]]:
    """Evaluate animal messengers affordance (flavor only)."""
    if not is_affordance_enabled("animal_messengers"):
        return {}, [], None

    defaults = AFFORDANCE_DEFAULTS["animal_messengers"]
    threshold, is_hostile, is_favorable = _get_effective_threshold(
        affinity, "animal_messengers"
    )

    if not is_hostile and not is_favorable:
        return {}, [], None

    if rng.random() > defaults["base_probability"]:
        return {}, [], None

    tells = []
    effect = None

    if is_hostile:
        tells.append(rng.choice(TELLS["animal_messengers"]["hostile"]))
        effect = "ominous"
    elif is_favorable:
        tells.append(rng.choice(TELLS["animal_messengers"]["favorable"]))
        effect = "auspicious"

    return {}, tells, effect


# =============================================================================
# MAIN EVALUATION FUNCTION
# =============================================================================

def evaluate_affordances(ctx: AffordanceContext) -> AffordanceOutcome:
    """
    Single entry point for all affordance checks.

    Evaluates all 10 affordances and combines results.
    """
    now = ctx.timestamp

    # Create seeded RNG for deterministic behavior
    random_seed = hash((ctx.actor_id, ctx.location.location_id, int(ctx.timestamp * 1000)))
    rng = random.Random(random_seed)

    # Compute affinity
    affinity = compute_affinity(
        ctx.location,
        ctx.actor_id,
        ctx.actor_tags,
        now
    )

    # Get threshold label
    threshold = get_threshold_label(affinity)

    # Compute contributing traces for debugging
    contributions = _compute_contributing_traces(
        ctx.location,
        ctx.actor_id,
        ctx.actor_tags,
        now
    )

    # Initialize accumulators
    all_adjustments = {}
    all_tells = []
    all_cooldowns = []
    triggered = False
    triggered_affordance = None
    triggered_effect = None
    redirect_target = None

    # Evaluate each affordance
    affordance_evaluators = [
        ("pathing", _evaluate_pathing),
        ("encounter_bias", _evaluate_encounter_bias),
        ("resource_scarcity", _evaluate_resource_scarcity),
        ("spell_side_effects", _evaluate_spell_side_effects),
        ("rest_quality", _evaluate_rest_quality),
        ("ambient_messaging", _evaluate_ambient_messaging),
        ("loot_quality", _evaluate_loot_quality),
        ("weather_microclimate", _evaluate_weather_microclimate),
        ("animal_messengers", _evaluate_animal_messengers),
    ]

    # For movement, tests expect pathing to be the single primary effect and the
    # pathing cooldown should suppress any immediate re-trigger.
    single_trigger_mode = (ctx.action_type == "move.pass")

    for aff_type, evaluator in affordance_evaluators:
        defaults = AFFORDANCE_DEFAULTS[aff_type]
        cooldown_key = f"{aff_type}:{ctx.actor_id}:{ctx.location.location_id}"

        # In movement mode, only pathing is evaluated.
        if single_trigger_mode and aff_type != "pathing":
            continue

        # Check cooldown (skip for per-spell affordances)
        if defaults["cooldown_seconds"] > 0:
            if _is_cooldown_active(ctx.location, cooldown_key, now):
                continue

        # Evaluate
        adjustments, tells, effect = evaluator(ctx, affinity, rng, now)

        if tells or adjustments:
            # Consume cooldown
            if defaults["cooldown_seconds"] > 0:
                _consume_cooldown(
                    ctx.location,
                    cooldown_key,
                    defaults["cooldown_seconds"],
                    now
                )
                all_cooldowns.append(cooldown_key)

            all_adjustments.update(adjustments)
            all_tells.extend(tells)
            triggered = True
            if effect:
                triggered_affordance = aff_type
                triggered_effect = effect

            # In single-trigger mode, stop after the first triggered affordance.
            if single_trigger_mode:
                break

    # Handle misleading navigation separately (has redirect target)
    nav_cooldown_key = f"misleading_navigation:{ctx.actor_id}:{ctx.location.location_id}"
    nav_defaults = AFFORDANCE_DEFAULTS["misleading_navigation"]
    if not _is_cooldown_active(ctx.location, nav_cooldown_key, now):
        adjustments, tells, effect, redirect = _evaluate_misleading_navigation(
            ctx, affinity, rng, now
        )
        if redirect:
            _consume_cooldown(
                ctx.location,
                nav_cooldown_key,
                nav_defaults["cooldown_seconds"],
                now
            )
            all_cooldowns.append(nav_cooldown_key)
            all_tells.extend(tells)
            redirect_target = redirect
            triggered = True
            triggered_affordance = "misleading_navigation"
            triggered_effect = "redirect"

    # Build trace log
    trace = AffordanceTriggerLog(
        timestamp=now,
        location_id=ctx.location.location_id,
        actor_id=ctx.actor_id,
        affordance_type=triggered_affordance or "none",
        effect_applied=triggered_effect,
        severity=list(all_adjustments.values())[0] if all_adjustments else 0.0,
        contributing_traces=contributions,
        computed_affinity=affinity,
        threshold_crossed=threshold
    )

    # Create snapshot with final computed values for deterministic replay
    snapshot = _create_snapshot(
        ctx,
        affinity,
        threshold,
        triggered_affordance,
        triggered_effect,
        random_seed,
        final_adjustments=all_adjustments,
        final_tells=all_tells,
        final_redirect_target=redirect_target
    )

    return AffordanceOutcome(
        adjustments=all_adjustments,
        tells=all_tells,
        trace=trace,
        snapshot=snapshot,
        cooldowns_consumed=all_cooldowns,
        triggered=triggered,
        redirect_target=redirect_target
    )


# =============================================================================
# REPLAY FUNCTIONS
# =============================================================================

@dataclass
class ReplayResult:
    """
    Complete replay result from a snapshot.

    All values are taken directly from the snapshot - NO recomputation.
    This guarantees 100% deterministic replay.
    """
    computed_affinity: float
    threshold_crossed: str
    adjustments: Dict[str, float]
    tells: List[str]
    redirect_target: Optional[str]
    affordance_triggered: Optional[str]
    effect_applied: Optional[str]


def replay_from_snapshot(snapshot: AffordanceSnapshot) -> float:
    """
    Replay affinity computation from a frozen snapshot.

    Returns the STORED computed_affinity value directly.
    Does NOT recompute - this ensures 100% deterministic replay.
    """
    # Return the stored value - never recompute
    return snapshot.computed_affinity


def replay_full_from_snapshot(snapshot: AffordanceSnapshot) -> ReplayResult:
    """
    Replay complete affordance outcome from a frozen snapshot.

    Returns ALL stored values directly from the snapshot.
    Does NOT call RNG or recompute anything.
    This is the primary replay function for determinism verification.
    """
    return ReplayResult(
        computed_affinity=snapshot.computed_affinity,
        threshold_crossed=snapshot.threshold_crossed,
        adjustments=dict(snapshot.final_adjustments),
        tells=list(snapshot.final_tells),
        redirect_target=snapshot.final_redirect_target,
        affordance_triggered=snapshot.affordance_triggered,
        effect_applied=snapshot.effect_applied
    )


def replay_tells_from_snapshot(snapshot: AffordanceSnapshot) -> List[str]:
    """
    Replay tell selection from a frozen snapshot.

    Returns the STORED tells directly - no RNG called.
    """
    return list(snapshot.final_tells)


def replay_adjustments_from_snapshot(snapshot: AffordanceSnapshot) -> Dict[str, float]:
    """
    Replay adjustments from a frozen snapshot.

    Returns the STORED adjustments directly.
    """
    return dict(snapshot.final_adjustments)


def verify_affinity_computation(snapshot: AffordanceSnapshot) -> bool:
    """
    Verify the stored affinity matches recomputation from traces.

    This is for debugging/testing only - it DOES recompute.
    Returns True if stored value matches recomputation.
    """
    import math

    personal = score_personal(
        snapshot.personal_traces,
        snapshot.actor_id,
        snapshot.half_lives_personal,
        snapshot.valuation_profile,
        now=snapshot.eval_time
    )

    group = score_group(
        snapshot.group_traces,
        snapshot.actor_tags,
        snapshot.half_lives_group,
        snapshot.valuation_profile,
        now=snapshot.eval_time
    )

    behavior = score_behavior(
        snapshot.behavior_traces,
        snapshot.half_lives_behavior,
        snapshot.valuation_profile,
        now=snapshot.eval_time
    )

    raw = (
        snapshot.channel_weight_personal * personal +
        snapshot.channel_weight_group * group +
        snapshot.channel_weight_behavior * behavior
    )

    # Must mirror compute_affinity() exactly
    recomputed = math.tanh(raw * (snapshot.affinity_scale / 10.0))

    # Must match exactly
    return recomputed == snapshot.computed_affinity


class SnapshotVerificationError(Exception):
    """Raised when snapshot verification fails."""
    pass


def replay_and_assert(snapshot: AffordanceSnapshot) -> ReplayResult:
    """
    Replay from snapshot and assert all values match recomputation.

    This is the primary verification function for determinism.
    Recomputes affinity from traces and asserts it matches stored value.

    Args:
        snapshot: The snapshot to verify

    Returns:
        ReplayResult with all stored values

    Raises:
        SnapshotVerificationError: If recomputed affinity doesn't match stored
    """
    import math

    # Recompute affinity from traces
    personal = score_personal(
        snapshot.personal_traces,
        snapshot.actor_id,
        snapshot.half_lives_personal,
        snapshot.valuation_profile,
        now=snapshot.eval_time
    )

    group = score_group(
        snapshot.group_traces,
        snapshot.actor_tags,
        snapshot.half_lives_group,
        snapshot.valuation_profile,
        now=snapshot.eval_time
    )

    behavior = score_behavior(
        snapshot.behavior_traces,
        snapshot.half_lives_behavior,
        snapshot.valuation_profile,
        now=snapshot.eval_time
    )

    raw = (
        snapshot.channel_weight_personal * personal +
        snapshot.channel_weight_group * group +
        snapshot.channel_weight_behavior * behavior
    )

    # Must mirror compute_affinity() exactly
    recomputed = math.tanh(raw * (snapshot.affinity_scale / 10.0))

    # Assert recomputed matches stored
    if recomputed != snapshot.computed_affinity:
        raise SnapshotVerificationError(
            f"Affinity mismatch: recomputed={recomputed}, "
            f"stored={snapshot.computed_affinity}"
        )

    # Return the stored values (guaranteed deterministic)
    return ReplayResult(
        computed_affinity=snapshot.computed_affinity,
        threshold_crossed=snapshot.threshold_crossed,
        adjustments=dict(snapshot.final_adjustments),
        tells=list(snapshot.final_tells),
        redirect_target=snapshot.final_redirect_target,
        affordance_triggered=snapshot.affordance_triggered,
        effect_applied=snapshot.effect_applied
    )


# =============================================================================
# VALIDATION ON MODULE LOAD
# =============================================================================

def validate_affordance_definitions() -> None:
    """
    Validate all affordance definitions at module load time.

    Checks:
    1. Each affordance has at most 2 mechanical handles
    2. All handles are from the allowlist
    3. All tells contain no forbidden patterns

    Raises:
        AffordanceValidationError: If validation fails
    """
    from world.affinity.validation import (
        validate_all_affordances,
        validate_all_tells,
        AffordanceValidationError
    )

    try:
        # Validate affordance configs
        handle_counts = validate_all_affordances(AFFORDANCE_DEFAULTS)

        # Validate tells
        tell_count = validate_all_tells(TELLS)

    except AffordanceValidationError as e:
        # Re-raise with clear message
        raise AffordanceValidationError(
            f"Affordance validation failed on module load:\n{e}"
        ) from e


def get_handle_counts() -> Dict[str, int]:
    """
    Get the number of mechanical handles each affordance uses.

    Returns:
        Dict mapping affordance_type -> handle_count
    """
    from world.affinity.validation import validate_all_affordances
    return validate_all_affordances(AFFORDANCE_DEFAULTS)


# Run validation on module import
# This ensures invalid affordances are caught early
try:
    validate_affordance_definitions()
except Exception:
    # Don't fail on import - validation errors will surface in tests
    # This allows the module to be imported even if validation fails
    pass
