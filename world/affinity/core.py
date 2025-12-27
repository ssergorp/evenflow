"""
Core data structures for the affinity system.

See docs/affinity_spec.md §2-4 for specification.
See docs/contract_examples.md for JSON shapes.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple, Optional, List
import time


@dataclass
class TraceRecord:
    """
    A single correlation stored in an entity's memory.
    The dict key carries identity; this stores only accumulated state.

    See spec §4.1
    """
    accumulated: float
    last_updated: float
    event_count: int
    is_scar: bool = False


@dataclass
class SaturationState:
    """
    Per-channel saturation tracking.
    A location saturated by commerce is not deaf to violence.

    See spec §4.5
    """
    personal: float = 0.0  # 0.0–1.0
    group: float = 0.0     # 0.0–1.0
    behavior: float = 0.0  # 0.0–1.0


@dataclass
class AffinityEvent:
    """
    Atomic unit of affinity change.

    See spec §3, docs/contract_examples.md §1
    """
    event_type: str                    # From controlled vocabulary (e.g., "harm.fire")
    actor_id: str                      # Who initiated
    actor_tags: Set[str]               # Categorical markers at time of event
    location_id: str                   # Where it happened
    intensity: float                   # 0.0–1.0, magnitude of action
    timestamp: float = field(default_factory=time.time)
    target_id: Optional[str] = None    # Affected entity, if any
    context_tags: Set[str] = field(default_factory=set)  # Additional qualifiers


@dataclass
class AffordanceConfig:
    """Configuration for a single affordance type."""
    affordance_type: str
    enabled: bool
    mechanical_handle: Optional[str]   # None = "flavor only"
    severity_clamp_hostile: float      # Max positive modifier (hostile effect)
    severity_clamp_favorable: float    # Max negative modifier (favorable effect)
    cooldown_seconds: int
    tells_hostile: List[str]
    tells_favorable: List[str]


@dataclass
class Location:
    """
    A persistent place that accumulates memory.

    See spec §2.2
    """
    location_id: str
    name: str
    description: str

    # Three-channel trace storage
    # Keys: (actor_id, event_type) for personal, (actor_tag, event_type) for group
    personal_traces: Dict[Tuple[str, str], TraceRecord] = field(default_factory=dict)
    group_traces: Dict[Tuple[str, str], TraceRecord] = field(default_factory=dict)
    behavior_traces: Dict[str, TraceRecord] = field(default_factory=dict)

    # This place's values (NOT global EVENT_WEIGHTS - see DO_NOT.md)
    valuation_profile: Dict[str, float] = field(default_factory=dict)

    # Per-channel saturation
    saturation: SaturationState = field(default_factory=SaturationState)

    # Housekeeping timestamp
    last_tick: float = 0.0

    # Affordances active in this location
    affordances: List[AffordanceConfig] = field(default_factory=list)

    # Cooldown tracking: key -> expiry timestamp
    cooldowns: Dict[str, float] = field(default_factory=dict)


@dataclass
class MoodBand:
    """
    Cached affinity range for quick lookups.

    CRITICAL: Derived cache, disposable, never authoritative.
    Can be deleted and recomputed from traces at any time.

    See spec §4.8
    """
    actor_tag: str
    affinity_range: Tuple[float, float]  # (min, max) from recent samples
    dominant_emotion: str                 # "hostile", "wary", "neutral", "warm", "aligned"
    last_updated: float
