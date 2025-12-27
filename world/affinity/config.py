"""
Configuration for the affinity system.

All tunable parameters live here, not in code.
See docs/affinity_spec.md §7 for specification.
"""

from dataclasses import dataclass
from typing import Set


@dataclass
class EntityHalfLives:
    """Half-lives in days for each channel of an entity type."""
    personal: float
    group: float
    behavior: float


@dataclass
class HalfLives:
    """Half-life configuration for all entity types."""
    location: EntityHalfLives
    artifact: EntityHalfLives
    npc: EntityHalfLives


@dataclass
class ChannelWeights:
    """Weights for blending affinity channels."""
    personal: float
    group: float
    behavior: float


@dataclass
class SaturationCapacity:
    """Base capacities for saturation calculation."""
    personal: int
    group: int
    behavior: int


@dataclass
class CompactionConfig:
    """Memory compaction thresholds."""
    hot_window_days: int
    warm_window_days: int
    scar_intensity_threshold: float
    scar_half_life_days: int
    prune_threshold: float


@dataclass
class InstitutionConfig:
    """Institution behavior settings."""
    drift_rate: float
    inertia: float
    half_life_days: int
    refresh_interval: int  # seconds


@dataclass
class AffinityConfig:
    """Complete affinity system configuration."""
    half_lives: HalfLives
    channel_weights: ChannelWeights
    saturation_capacity: SaturationCapacity
    world_tick_interval: int  # seconds
    compaction: CompactionConfig
    institutions: InstitutionConfig
    institutional_tags: Set[str]
    affinity_scale: float


# Default configuration - matches docs/affinity_spec.md §7.1
_DEFAULT_CONFIG = AffinityConfig(
    half_lives=HalfLives(
        location=EntityHalfLives(personal=7, group=30, behavior=90),
        artifact=EntityHalfLives(personal=3, group=14, behavior=30),
        npc=EntityHalfLives(personal=1, group=7, behavior=14),
    ),
    channel_weights=ChannelWeights(
        personal=0.5,
        group=0.35,
        behavior=0.15,
    ),
    saturation_capacity=SaturationCapacity(
        personal=50,
        group=100,
        behavior=200,
    ),
    world_tick_interval=3600,  # 1 hour
    compaction=CompactionConfig(
        hot_window_days=7,
        warm_window_days=90,
        scar_intensity_threshold=0.7,
        scar_half_life_days=365,
        prune_threshold=0.01,
    ),
    institutions=InstitutionConfig(
        drift_rate=0.1,
        inertia=0.9,
        half_life_days=90,
        refresh_interval=86400,  # 1 day
    ),
    # Configurable per-world: fantasy (elf, dwarf), modern (corporate, union), etc.
    institutional_tags={"human", "elf", "dwarf", "orc", "imperial", "rebel"},
    affinity_scale=10.0,
)

# Active configuration (can be replaced at runtime)
_active_config: AffinityConfig = _DEFAULT_CONFIG


def get_config() -> AffinityConfig:
    """Get the active affinity configuration."""
    return _active_config


def set_config(config: AffinityConfig) -> None:
    """Set the active affinity configuration."""
    global _active_config
    _active_config = config


def reset_config() -> None:
    """Reset to default configuration."""
    global _active_config
    _active_config = _DEFAULT_CONFIG
