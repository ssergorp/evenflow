"""
Configuration for the affinity system.

All tunable parameters live here, not in code.
See docs/affinity_spec.md §7 for specification.
"""

import os
import yaml
from dataclasses import dataclass
from pathlib import Path
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


def load_config_from_yaml(yaml_path: str) -> AffinityConfig:
    """
    Load affinity configuration from YAML file.

    Args:
        yaml_path: Path to affinity_defaults.yaml

    Returns:
        Fully validated AffinityConfig instance

    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ValueError: If YAML structure invalid or missing required fields
        yaml.YAMLError: If YAML parsing fails

    See docs/affinity_spec.md §7 for configuration schema.
    """
    # Load YAML file
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        raise FileNotFoundError(f"Config file not found: {yaml_path}")

    with open(yaml_file, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML: {e}")

    if not isinstance(data, dict):
        raise ValueError("YAML root must be a dictionary")

    # Build nested dataclasses
    try:
        half_lives = HalfLives(
            location=EntityHalfLives(
                personal=float(data["half_lives"]["location"]["personal"]),
                group=float(data["half_lives"]["location"]["group"]),
                behavior=float(data["half_lives"]["location"]["behavior"]),
            ),
            artifact=EntityHalfLives(
                personal=float(data["half_lives"]["artifact"]["personal"]),
                group=float(data["half_lives"]["artifact"]["group"]),
                behavior=float(data["half_lives"]["artifact"]["behavior"]),
            ),
            npc=EntityHalfLives(
                personal=float(data["half_lives"]["npc"]["personal"]),
                group=float(data["half_lives"]["npc"]["group"]),
                behavior=float(data["half_lives"]["npc"]["behavior"]),
            ),
        )

        channel_weights = ChannelWeights(
            personal=float(data["channel_weights"]["personal"]),
            group=float(data["channel_weights"]["group"]),
            behavior=float(data["channel_weights"]["behavior"]),
        )

        saturation_capacity = SaturationCapacity(
            personal=int(data["saturation_capacity"]["personal"]),
            group=int(data["saturation_capacity"]["group"]),
            behavior=int(data["saturation_capacity"]["behavior"]),
        )

        compaction = CompactionConfig(
            hot_window_days=int(data["compaction"]["hot_window_days"]),
            warm_window_days=int(data["compaction"]["warm_window_days"]),
            scar_intensity_threshold=float(data["compaction"]["scar_intensity_threshold"]),
            scar_half_life_days=int(data["compaction"]["scar_half_life_days"]),
            prune_threshold=float(data["compaction"]["prune_threshold"]),
        )

        institutions = InstitutionConfig(
            drift_rate=float(data["institutions"]["drift_rate"]),
            inertia=float(data["institutions"]["inertia"]),
            half_life_days=int(data["institutions"]["half_life_days"]),
            refresh_interval=int(data["institutions"]["refresh_interval_seconds"]),
        )

        institutional_tags = set(data["institutional_tags"])

        return AffinityConfig(
            half_lives=half_lives,
            channel_weights=channel_weights,
            saturation_capacity=saturation_capacity,
            world_tick_interval=int(data["world_tick"]["interval_seconds"]),
            compaction=compaction,
            institutions=institutions,
            institutional_tags=institutional_tags,
            affinity_scale=float(data["affinity_scale"]),
        )
    except KeyError as e:
        raise ValueError(f"Missing required field in YAML: {e}")
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid value in YAML: {e}")
