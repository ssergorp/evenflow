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
class ScarEvent:
    """
    High-intensity event preserved as long-term landmark.

    Scars represent "the time the forest burned" or "the massacre at the crossroads."
    They decay very slowly (half-life: 1 year).

    See spec §4.7
    """
    event_type: str                # Category only (e.g., "harm" not "harm.fire")
    actor_tags: Set[str]           # Institutional tags only
    intensity: float               # Original intensity (>0.7)
    timestamp: float               # When it happened
    half_life_seconds: float       # 365 days * 86400 = 31536000


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

    # Scars: High-intensity long-term landmarks
    scars: List['ScarEvent'] = field(default_factory=list)


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


@dataclass
class BearerRecord:
    """
    Record of time spent carrying an artifact.

    See spec §2.3
    """
    bearer_id: str
    accumulated_time: float  # seconds
    last_carried: float      # timestamp
    intensity: float         # how much it has influenced this bearer


@dataclass
class PressureRule:
    """
    How an artifact influences its bearer.

    See spec §5.2
    """
    trigger: str                    # "bearer_action", "bearer_state", "proximity"
    condition: str                  # Expression evaluated against context
    effect_type: str                # From pressure type vocabulary
    intensity_base: float           # 0.0–1.0
    scales_with_influence: bool     # Grows as artifact learns bearer?
    cooldown_seconds: int           # Minimum time between triggers
    severity_clamp: float           # Maximum effect magnitude


@dataclass
class Artifact:
    """
    Mobile object that carries pressure and learns its bearer.

    See docs/affinity_spec.md §2.3
    """
    artifact_id: str
    name: str
    description: str

    # Origin and biases
    origin_tags: Set[str] = field(default_factory=set)
    valuation_profile: Dict[str, float] = field(default_factory=dict)

    # Bearer learning
    bearer_traces: Dict[str, BearerRecord] = field(default_factory=dict)
    current_bearer: Optional[str] = None

    # Pressure mechanics
    pressure_vectors: List[PressureRule] = field(default_factory=list)
    influence_accumulator: float = 0.0

    # Housekeeping
    last_tick: float = 0.0


@dataclass
class Institution:
    """
    Virtual entity representing distributed cultural patterns.

    No physical presence, but persists and drifts over time.
    See docs/affinity_spec.md §2.4
    """
    institution_id: str
    name: str
    description: str

    # Affiliation
    affiliated_tags: Set[str] = field(default_factory=set)

    # Cached stance (slowly drifts)
    cached_stance: Dict[str, float] = field(default_factory=dict)  # actor_tag → affinity

    # Drift parameters
    drift_rate: float = 0.1      # How quickly it updates from constituents
    inertia: float = 0.9         # Resistance to rapid change
    half_life_days: float = 90.0 # Institutional memory is long

    # Housekeeping
    last_computed: float = 0.0


@dataclass
class AffordanceTriggerLog:
    """
    Record of when and why an affordance triggered.

    Admin-only debugging data.
    See docs/affinity_spec.md §6.4
    """
    location_id: str
    affordance_type: str
    actor_id: str
    actor_tags: Set[str]
    timestamp: float

    # Computed values
    raw_affinity: float
    normalized_affinity: float
    threshold_band: str  # "hostile", "neutral", etc.

    # Top contributing traces (for "why")
    top_traces: List[Tuple[str, float]] = field(default_factory=list)  # (trace_key, value)

    # Snapshot for replay
    snapshot: Dict = field(default_factory=dict)  # Full state at trigger time
