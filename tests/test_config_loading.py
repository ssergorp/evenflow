"""
Config loading tests.

config/affinity_defaults.yaml is the single source of tunable parameters.
These tests pin the loader's behavior and catch drift between the YAML
and the engine.
"""

import pytest
import yaml

from world.affinity.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    get_config,
    load_affordance_defaults,
    load_config,
    load_config_file,
    reset_config,
)
from world.affinity.affordances import (
    AFFORDANCE_DEFAULTS,
    TELLS,
    _AFFORDANCE_REGISTRY,
    validate_affordance_definitions,
)
from world.affinity.validation import AffordanceValidationError


@pytest.fixture
def raw_yaml():
    """The default YAML file as a dict, for building variants."""
    with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write(tmp_path, data):
    path = tmp_path / "affinity.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class TestDefaultConfig:
    """The default config comes from the YAML file."""

    def test_default_config_matches_yaml(self, raw_yaml):
        reset_config()
        config = get_config()

        assert config.half_lives.location.personal == raw_yaml["half_lives"]["location"]["personal"]
        assert config.channel_weights.group == raw_yaml["channel_weights"]["group"]
        assert config.affinity_scale == raw_yaml["affinity_scale"]
        assert config.world_tick_interval == raw_yaml["world_tick"]["interval_seconds"]
        assert config.institutional_tags == set(raw_yaml["institutional_tags"])

    def test_affordance_defaults_match_yaml(self, raw_yaml):
        for name, entry in raw_yaml["affordances"].items():
            assert AFFORDANCE_DEFAULTS[name]["hostile_threshold"] == entry["hostile_threshold"]
            assert AFFORDANCE_DEFAULTS[name]["base_probability"] == entry["base_probability"]
            assert _AFFORDANCE_REGISTRY[name] == entry["enabled"]

    def test_yaml_only_keys_are_dropped(self):
        for cfg in load_affordance_defaults().values():
            assert "tells" not in cfg
            assert "scales_with_affinity" not in cfg


class TestDrift:
    """YAML affordance names must match the engine exactly."""

    def test_yaml_affordances_match_engine(self):
        assert set(AFFORDANCE_DEFAULTS) == set(TELLS)
        assert set(_AFFORDANCE_REGISTRY) == set(TELLS)

    def test_unknown_affordance_fails_validation(self, monkeypatch):
        monkeypatch.setitem(AFFORDANCE_DEFAULTS, "encounter_rate", dict(AFFORDANCE_DEFAULTS["encounter_bias"]))
        with pytest.raises(AffordanceValidationError, match="unknown in config.*encounter_rate"):
            validate_affordance_definitions()

    def test_missing_affordance_fails_validation(self, monkeypatch):
        monkeypatch.delitem(AFFORDANCE_DEFAULTS, "loot_quality")
        with pytest.raises(AffordanceValidationError, match="missing from config.*loot_quality"):
            validate_affordance_definitions()


class TestLoaderErrors:
    """Bad config files fail loudly with a clear message."""

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope.yaml")

    def test_missing_section(self, tmp_path, raw_yaml):
        del raw_yaml["channel_weights"]
        with pytest.raises(ConfigError, match="channel_weights"):
            load_config(_write(tmp_path, raw_yaml))

    def test_affordance_missing_required_key(self, tmp_path, raw_yaml):
        del raw_yaml["affordances"]["pathing"]["hostile_threshold"]
        with pytest.raises(ConfigError, match="pathing is missing hostile_threshold"):
            load_affordance_defaults(_write(tmp_path, raw_yaml))


class TestLoadConfigFile:
    """load_config_file swaps the active config; reset_config restores it."""

    def test_load_and_reset(self, tmp_path, raw_yaml):
        reset_config()
        default_scale = get_config().affinity_scale
        raw_yaml["affinity_scale"] = default_scale * 2

        try:
            load_config_file(_write(tmp_path, raw_yaml))
            assert get_config().affinity_scale == default_scale * 2
        finally:
            reset_config()

        assert get_config().affinity_scale == default_scale
