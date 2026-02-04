"""
Institution system: distributed cultural patterns.

See docs/affinity_spec.md §5.3
"""

from typing import Dict, List, Set
import time

from world.affinity.core import Institution, Location
from world.affinity.config import get_config
from world.affinity.computation import compute_affinity


def query_constituent_affinity(
    institution: Institution,
    locations: List[Location],
    target_tag: str,
    now: float
) -> float:
    """
    Query current affinity from constituent entities.

    Aggregates affinity from all locations affiliated with this institution.

    Args:
        institution: Institution to query
        locations: List of constituent locations
        target_tag: Actor tag to compute affinity toward
        now: Current timestamp

    Returns:
        Average affinity across constituents

    See docs/affinity_spec.md §2.4
    """
    total_affinity = 0.0
    count = 0

    for location in locations:
        # Check if location is affiliated
        # (In a full implementation, would check location tags)
        # For now, assume all provided locations are affiliated

        # Compute affinity for this target tag
        affinity = compute_affinity(
            location,
            actor_id=None,  # No specific actor
            actor_tags={target_tag},
            now=now
        )

        total_affinity += affinity
        count += 1

    if count == 0:
        return 0.0

    return total_affinity / count


def update_institution(
    institution: Institution,
    constituent_locations: List[Location],
    target_tags: Set[str],
    now: float
) -> None:
    """
    Update institution's cached stance from constituents.

    Uses drift_rate and inertia to slowly adjust stance.
    Institutions are slow to change, creating persistent cultural patterns.

    Args:
        institution: Institution to update
        constituent_locations: List of locations contributing to institution
        target_tags: Actor tags to update stance for
        now: Current timestamp

    See docs/affinity_spec.md §2.4
    """
    for target_tag in target_tags:
        # Query current constituent affinity
        fresh_affinity = query_constituent_affinity(
            institution,
            constituent_locations,
            target_tag,
            now
        )

        # Get cached value
        cached = institution.cached_stance.get(target_tag, 0.0)

        # Drift toward fresh value
        # Formula: new = inertia * old + drift_rate * fresh
        # With default values (0.9, 0.1): heavily weighted toward old value
        new_stance = (
            institution.inertia * cached +
            institution.drift_rate * fresh_affinity
        )

        institution.cached_stance[target_tag] = new_stance

    institution.last_computed = now


def query_institution_stance(
    institution: Institution,
    target_tag: str
) -> float:
    """
    Query institution's current stance toward a target.

    Returns cached stance (not real-time constituent query).

    Args:
        institution: Institution to query
        target_tag: Actor tag to query stance for

    Returns:
        Cached affinity toward target tag
    """
    return institution.cached_stance.get(target_tag, 0.0)


def should_refresh_institution(
    institution: Institution,
    now: float
) -> bool:
    """
    Check if institution should be refreshed.

    Institutions update on a schedule (default: daily).

    Args:
        institution: Institution to check
        now: Current timestamp

    Returns:
        True if refresh is due
    """
    config = get_config()
    time_since_last = now - institution.last_computed

    return time_since_last >= config.institutions.refresh_interval


def get_affiliated_locations(
    institution: Institution,
    all_locations: List[Location]
) -> List[Location]:
    """
    Get locations affiliated with this institution.

    In a full implementation, would check location tags against
    institution.affiliated_tags.

    Args:
        institution: Institution to find affiliates for
        all_locations: All locations to check

    Returns:
        List of affiliated locations
    """
    # For now, simplified: return all locations
    # Full implementation would check:
    # - Location has any tag in institution.affiliated_tags
    # - Or location explicitly lists institution affiliation
    return all_locations


def compute_institutional_memory_decay(
    institution: Institution,
    elapsed_days: float
) -> None:
    """
    Apply slow decay to institutional memory.

    Institutions forget very slowly (90-day half-life by default).

    Args:
        institution: Institution to decay
        elapsed_days: Time elapsed in days
    """
    # Decay factor: 0.5 ^ (elapsed / half_life)
    decay_factor = 0.5 ** (elapsed_days / institution.half_life_days)

    for tag in institution.cached_stance:
        institution.cached_stance[tag] *= decay_factor
