"""
Configuration for the affinity system.

All tunable parameters live in config/affinity_defaults.yaml, not in code.
This module loads that file; see docs/affinity_spec.md §7 for specification.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Union

import yaml

# Repo-root config/affinity_defaults.yaml
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "affinity_defaults.yaml"

# Every affordance entry must define these
REQUIRED_AFFORDANCE_KEYS = (
    "handle",
    "base_probability",
    "cooldown_seconds",
    "hostile_threshold",
    "favorable_threshold",
)

# YAML-only keys that the engine does not read
_NON_ENGINE_AFFORDANCE_KEYS = ("tells", "scales_with_affinity")


class ConfigError(ValueError):
    """Raised when the affinity config file is missing or malformed."""


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


# =============================================================================
# YAML LOADING
# =============================================================================

PathLike = Union[str, Path]


def _read_yaml(path: Optional[PathLike]) -> Dict[str, Any]:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"Affinity config not found: {path}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"Affinity config must be a mapping: {path}")
    return data


def _section(data: Dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ConfigError(f"Missing '{key}' in {where}")
    return data[key]


def _entity_half_lives(data: Dict[str, Any], entity: str) -> EntityHalfLives:
    hl = _section(data, entity, "half_lives")
    where = f"half_lives.{entity}"
    return EntityHalfLives(
        personal=_section(hl, "personal", where),
        group=_section(hl, "group", where),
        behavior=_section(hl, "behavior", where),
    )


def load_config(path: Optional[PathLike] = None) -> AffinityConfig:
    """
    Build an AffinityConfig from the YAML file.

    Args:
        path: YAML file to read (default: config/affinity_defaults.yaml)

    Raises:
        ConfigError: if the file is missing or a required key is absent
    """
    data = _read_yaml(path)

    half_lives = _section(data, "half_lives", "config")
    weights = _section(data, "channel_weights", "config")
    capacity = _section(data, "saturation_capacity", "config")
    compaction = _section(data, "compaction", "config")
    institutions = _section(data, "institutions", "config")
    world_tick = _section(data, "world_tick", "config")

    return AffinityConfig(
        half_lives=HalfLives(
            location=_entity_half_lives(half_lives, "location"),
            artifact=_entity_half_lives(half_lives, "artifact"),
            npc=_entity_half_lives(half_lives, "npc"),
        ),
        channel_weights=ChannelWeights(
            personal=_section(weights, "personal", "channel_weights"),
            group=_section(weights, "group", "channel_weights"),
            behavior=_section(weights, "behavior", "channel_weights"),
        ),
        saturation_capacity=SaturationCapacity(
            personal=_section(capacity, "personal", "saturation_capacity"),
            group=_section(capacity, "group", "saturation_capacity"),
            behavior=_section(capacity, "behavior", "saturation_capacity"),
        ),
        world_tick_interval=_section(world_tick, "interval_seconds", "world_tick"),
        compaction=CompactionConfig(
            hot_window_days=_section(compaction, "hot_window_days", "compaction"),
            warm_window_days=_section(compaction, "warm_window_days", "compaction"),
            scar_intensity_threshold=_section(compaction, "scar_intensity_threshold", "compaction"),
            scar_half_life_days=_section(compaction, "scar_half_life_days", "compaction"),
            prune_threshold=_section(compaction, "prune_threshold", "compaction"),
        ),
        institutions=InstitutionConfig(
            drift_rate=_section(institutions, "drift_rate", "institutions"),
            inertia=_section(institutions, "inertia", "institutions"),
            half_life_days=_section(institutions, "half_life_days", "institutions"),
            refresh_interval=_section(institutions, "refresh_interval_seconds", "institutions"),
        ),
        institutional_tags=set(_section(data, "institutional_tags", "config")),
        affinity_scale=_section(data, "affinity_scale", "config"),
    )


def load_affordance_defaults(path: Optional[PathLike] = None) -> Dict[str, Dict[str, Any]]:
    """
    Read the `affordances` section of the YAML file.

    Returns a dict of affordance_type -> engine parameters (thresholds,
    clamps, probability, cooldown, handles, enabled). YAML-only keys such
    as `tells` are dropped.

    Raises:
        ConfigError: if the section is missing or an entry lacks a required key
    """
    data = _read_yaml(path)
    section = _section(data, "affordances", "config")
    if not isinstance(section, dict) or not section:
        raise ConfigError("'affordances' must be a non-empty mapping")

    result: Dict[str, Dict[str, Any]] = {}
    for name, entry in section.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"affordances.{name} must be a mapping")
        missing = [k for k in REQUIRED_AFFORDANCE_KEYS if k not in entry]
        if missing:
            raise ConfigError(f"affordances.{name} is missing {', '.join(missing)}")
        result[name] = {
            k: v for k, v in entry.items() if k not in _NON_ENGINE_AFFORDANCE_KEYS
        }
    return result


def load_event_intensity(path: Optional[PathLike] = None) -> Dict[str, float]:
    """
    Read the typical intensity for each event type from `event_intensity`.

    Returns:
        Dict mapping "category.kind" (e.g. "harm.fire") -> typical intensity
    """
    data = _read_yaml(path)
    section = _section(data, "event_intensity", "config")
    result: Dict[str, float] = {}
    for category, kinds in section.items():
        for kind, entry in kinds.items():
            result[f"{category}.{kind}"] = _section(entry, "typical", f"event_intensity.{category}.{kind}")
    return result


def load_config_file(path: PathLike) -> AffinityConfig:
    """
    Load a YAML file and make it the active configuration.

    Only AffinityConfig is swapped. Affordance parameters are read once at
    import of world.affinity.affordances, so changing them needs a restart.
    """
    config = load_config(path)
    set_config(config)
    return config


# Default configuration, read from config/affinity_defaults.yaml at import
_DEFAULT_CONFIG = load_config()

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
