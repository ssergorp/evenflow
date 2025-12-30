"""
Validation for affordance definitions.

Ensures:
1. Each affordance has at most 2 mechanical handles
2. All handles are from the allowlist (existing game variables)
3. No invented stats

See docs/DO_NOT.md #3, #4
"""

from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# HANDLE ALLOWLIST
# =============================================================================
# These are the ONLY mechanical handles affordances may touch.
# Each corresponds to an existing game variable - do NOT invent new stats.
#
# Format: "system.variable_modifier"
#
# If you need a new handle, it must already exist in the game engine.
# Add it here ONLY after confirming the game supports it.

HANDLE_ALLOWLIST: Set[str] = {
    # Room/Location modifiers
    "room.travel_time_modifier",
    "room.encounter_rate_modifier",
    "room.redirect_target",

    # NPC modifiers
    "npc.aggro_radius_modifier",
    "npc.disposition_modifier",

    # Spell modifiers
    "spell.power_modifier",
    "spell.backfire_chance",
    "spell.cost_modifier",

    # Harvest/Resource modifiers
    "harvest.yield_modifier",
    "harvest.quality_modifier",

    # Rest modifiers
    "rest.healing_modifier",
    "rest.duration_modifier",

    # Loot modifiers
    "loot.quality_modifier",
    "loot.quantity_modifier",

    # Actor modifiers (rare, use sparingly)
    "actor.stamina_modifier",
    "actor.luck_modifier",

    # Action modifiers
    "action.skill_modifier",
}


# =============================================================================
# VALIDATION ERRORS
# =============================================================================

class AffordanceValidationError(Exception):
    """Raised when affordance validation fails."""
    pass


class HandleNotAllowedError(AffordanceValidationError):
    """Raised when an affordance uses a handle not in the allowlist."""
    pass


class TooManyHandlesError(AffordanceValidationError):
    """Raised when an affordance touches more than 2 handles."""
    pass


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_handle(handle: Optional[str], affordance_type: str) -> None:
    """
    Validate a single handle is in the allowlist.

    Args:
        handle: The handle to validate (None is allowed for flavor-only)
        affordance_type: Name of the affordance (for error messages)

    Raises:
        HandleNotAllowedError: If handle is not in HANDLE_ALLOWLIST
    """
    if handle is None:
        return  # Flavor-only affordances are allowed

    if handle not in HANDLE_ALLOWLIST:
        raise HandleNotAllowedError(
            f"Affordance '{affordance_type}' uses handle '{handle}' which is not in "
            f"HANDLE_ALLOWLIST. Add it to the allowlist only if it exists in the game engine."
        )


def validate_handle_count(handles: List[Optional[str]], affordance_type: str) -> None:
    """
    Validate affordance has at most 2 mechanical handles.

    Args:
        handles: List of handles (may include None)
        affordance_type: Name of the affordance (for error messages)

    Raises:
        TooManyHandlesError: If more than 2 non-None handles
    """
    non_null_handles = [h for h in handles if h is not None]

    if len(non_null_handles) > 2:
        raise TooManyHandlesError(
            f"Affordance '{affordance_type}' touches {len(non_null_handles)} handles: "
            f"{non_null_handles}. Maximum allowed is 2 (see DO_NOT.md #3)."
        )


def validate_affordance_config(
    affordance_type: str,
    config: Dict
) -> Tuple[List[str], int]:
    """
    Validate a complete affordance configuration.

    Args:
        affordance_type: Name of the affordance
        config: Configuration dict with 'handle' and optionally 'handle_secondary'

    Returns:
        Tuple of (list of handles, handle count)

    Raises:
        AffordanceValidationError: If validation fails
    """
    handles = []

    # Primary handle
    primary = config.get("handle")
    handles.append(primary)
    validate_handle(primary, affordance_type)

    # Secondary handle (optional)
    secondary = config.get("handle_secondary")
    if secondary is not None:
        handles.append(secondary)
        validate_handle(secondary, affordance_type)

    # Count check
    validate_handle_count(handles, affordance_type)

    return handles, len([h for h in handles if h is not None])


def validate_all_affordances(affordance_defaults: Dict[str, Dict]) -> Dict[str, int]:
    """
    Validate all affordance configurations.

    Args:
        affordance_defaults: Dict mapping affordance_type -> config

    Returns:
        Dict mapping affordance_type -> handle_count

    Raises:
        AffordanceValidationError: If any affordance fails validation
    """
    results = {}
    errors = []

    for aff_type, config in affordance_defaults.items():
        try:
            _, count = validate_affordance_config(aff_type, config)
            results[aff_type] = count
        except AffordanceValidationError as e:
            errors.append(str(e))

    if errors:
        raise AffordanceValidationError(
            f"Affordance validation failed with {len(errors)} errors:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    return results


def get_affordance_handles(config: Dict) -> List[str]:
    """
    Extract all non-None handles from an affordance config.

    Args:
        config: Affordance configuration dict

    Returns:
        List of handle strings (excludes None)
    """
    handles = []

    if config.get("handle"):
        handles.append(config["handle"])

    if config.get("handle_secondary"):
        handles.append(config["handle_secondary"])

    return handles


# =============================================================================
# TELL VALIDATION
# =============================================================================

# Patterns that should never appear in tells (DO_NOT.md #2)
FORBIDDEN_TELL_PATTERNS: Set[str] = {
    "affinity",
    "reputation",
    "score",
    "points",
    "meter",
    "hostile",
    "favorable",
    "neutral",
    "unwelcoming",
    "aligned",
    "+",
    "-",
    "%",
}


def validate_tell(tell: str, affordance_type: str, tell_group: str) -> None:
    """
    Validate a single tell string contains no forbidden patterns.

    Args:
        tell: The narrative tell string
        affordance_type: Name of the affordance
        tell_group: Name of the tell group (e.g., "hostile", "favorable")

    Raises:
        AffordanceValidationError: If tell contains forbidden pattern
    """
    tell_lower = tell.lower()

    for pattern in FORBIDDEN_TELL_PATTERNS:
        if pattern in tell_lower:
            # Allow + and - only if not followed by numbers
            if pattern in ("+", "-"):
                # Check if it's part of a number
                import re
                if re.search(r'[+-]\d', tell):
                    raise AffordanceValidationError(
                        f"Tell in {affordance_type}.{tell_group} contains numeric pattern: '{tell}'"
                    )
            else:
                raise AffordanceValidationError(
                    f"Tell in {affordance_type}.{tell_group} contains forbidden pattern "
                    f"'{pattern}': '{tell}'"
                )


def validate_all_tells(tells_dict: Dict[str, Dict]) -> int:
    """
    Validate all tells in the TELLS dictionary.

    Args:
        tells_dict: Dict mapping affordance_type -> {group -> [tells]}

    Returns:
        Total number of tells validated

    Raises:
        AffordanceValidationError: If any tell fails validation
    """
    count = 0
    errors = []

    for aff_type, groups in tells_dict.items():
        for group_name, tells in groups.items():
            if isinstance(tells, list):
                for tell in tells:
                    try:
                        validate_tell(tell, aff_type, group_name)
                        count += 1
                    except AffordanceValidationError as e:
                        errors.append(str(e))

    if errors:
        raise AffordanceValidationError(
            f"Tell validation failed with {len(errors)} errors:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    return count


# =============================================================================
# ADJUSTMENT VALIDATION
# =============================================================================

def validate_adjustments(
    adjustments: Dict[str, float],
    affordance_type: str
) -> None:
    """
    Validate adjustments dict from an affordance outcome.

    Args:
        adjustments: Dict mapping handle -> value
        affordance_type: Name of the affordance

    Raises:
        AffordanceValidationError: If validation fails
    """
    # Check handle count
    if len(adjustments) > 2:
        raise TooManyHandlesError(
            f"Affordance '{affordance_type}' produced {len(adjustments)} adjustments. "
            f"Maximum is 2."
        )

    # Check each handle is allowed
    for handle in adjustments.keys():
        validate_handle(handle, affordance_type)
