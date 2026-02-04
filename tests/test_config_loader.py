"""
Tests for YAML config loader.

See world/affinity/config.py for implementation.
"""

import pytest
import tempfile
from pathlib import Path

from world.affinity.config import (
    load_config_from_yaml,
    AffinityConfig,
    HalfLives,
    ChannelWeights,
)


def test_load_default_yaml():
    """Default YAML should load successfully."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")

    assert isinstance(config, AffinityConfig)
    assert config.half_lives.location.personal == 7
    assert config.half_lives.location.group == 30
    assert config.half_lives.location.behavior == 90
    assert config.channel_weights.personal == 0.5
    assert config.channel_weights.group == 0.35
    assert config.channel_weights.behavior == 0.15
    assert config.affinity_scale == 10.0


def test_missing_file_raises():
    """Missing file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config_from_yaml("nonexistent.yaml")


def test_invalid_yaml_raises():
    """Malformed YAML should raise ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("{ invalid yaml syntax: [")
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Failed to parse YAML"):
            load_config_from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_missing_required_field():
    """Missing required field should raise ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""
half_lives:
  location:
    personal: 7
    group: 30
    # missing behavior field
""")
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Missing required field"):
            load_config_from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_non_dict_root_raises():
    """YAML file with non-dict root should raise ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("- just\n- a\n- list\n")
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="YAML root must be a dictionary"):
            load_config_from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_has_correct_types():
    """Loaded config should have correct types."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")

    assert isinstance(config.half_lives, HalfLives)
    assert isinstance(config.channel_weights, ChannelWeights)
    assert isinstance(config.institutional_tags, set)
    assert isinstance(config.world_tick_interval, int)
    assert isinstance(config.affinity_scale, float)


def test_institutional_tags_loaded_as_set():
    """Institutional tags should be loaded as a set."""
    config = load_config_from_yaml("config/affinity_defaults.yaml")

    assert isinstance(config.institutional_tags, set)
    assert "human" in config.institutional_tags
    assert "elf" in config.institutional_tags
