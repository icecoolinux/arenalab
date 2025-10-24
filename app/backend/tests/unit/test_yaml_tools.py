"""
Unit tests for YAML tools module.

Tests configuration merging and ML-Agents config utilities.
"""

import pytest
import tempfile
import os

from utils.yaml_tools import (
    merge_flags,
    deep_merge_dict,
    get_behavior_names,
    merge_hyperparameters_into_config,
    load_yaml_with_comments,
    save_yaml_with_comments,
)


@pytest.mark.unit
class TestMergeFlags:
    """Test simple flag merging."""

    def test_merge_flags_basic(self):
        """Test basic flag merging."""
        defaults = {"batch_size": 64, "learning_rate": 0.0003}
        overrides = {"learning_rate": 0.001}

        result = merge_flags(defaults, overrides)

        assert result["batch_size"] == 64
        assert result["learning_rate"] == 0.001

    def test_merge_flags_empty_overrides(self):
        """Test merging with empty overrides."""
        defaults = {"param1": "value1", "param2": "value2"}
        overrides = {}

        result = merge_flags(defaults, overrides)

        assert result == defaults

    def test_merge_flags_none_values(self):
        """Test merging with None values."""
        result = merge_flags(None, {"key": "value"})
        assert result == {"key": "value"}

        result = merge_flags({"key": "value"}, None)
        assert result == {"key": "value"}


@pytest.mark.unit
class TestDeepMergeDict:
    """Test deep dictionary merging."""

    def test_deep_merge_basic(self):
        """Test basic nested dictionary merge."""
        base = {"a": {"b": 1, "c": 2}}
        updates = {"a": {"c": 3, "d": 4}}

        result = deep_merge_dict(base, updates)

        assert result["a"]["b"] == 1  # Preserved
        assert result["a"]["c"] == 3  # Updated
        assert result["a"]["d"] == 4  # Added

    def test_deep_merge_preserves_original(self):
        """Test that original dictionaries are not modified."""
        base = {"nested": {"value": 1}}
        updates = {"nested": {"value": 2}}

        result = deep_merge_dict(base, updates)

        assert base["nested"]["value"] == 1  # Original unchanged
        assert result["nested"]["value"] == 2  # Result updated

    def test_deep_merge_multiple_levels(self):
        """Test merging deeply nested structures."""
        base = {"level1": {"level2": {"level3": {"value": 1}}}}
        updates = {"level1": {"level2": {"level3": {"value": 2, "new": 3}}}}

        result = deep_merge_dict(base, updates)

        assert result["level1"]["level2"]["level3"]["value"] == 2
        assert result["level1"]["level2"]["level3"]["new"] == 3

    def test_deep_merge_non_dict_override(self):
        """Test that non-dict values override completely."""
        base = {"key": {"nested": "value"}}
        updates = {"key": "simple_string"}

        result = deep_merge_dict(base, updates)

        assert result["key"] == "simple_string"

    def test_deep_merge_new_keys(self):
        """Test adding new top-level keys."""
        base = {"existing": "value"}
        updates = {"new": "value"}

        result = deep_merge_dict(base, updates)

        assert result["existing"] == "value"
        assert result["new"] == "value"


@pytest.mark.unit
class TestGetBehaviorNames:
    """Test extracting behavior names from config."""

    def test_get_behavior_names_basic(self):
        """Test extracting behavior names."""
        config = {
            "behaviors": {
                "3DBall": {"trainer_type": "ppo"},
                "Walker": {"trainer_type": "sac"}
            }
        }

        names = get_behavior_names(config)

        assert len(names) == 2
        assert "3DBall" in names
        assert "Walker" in names

    def test_get_behavior_names_empty(self):
        """Test with config without behaviors."""
        config = {"some_other_key": "value"}

        names = get_behavior_names(config)

        assert names == []

    def test_get_behavior_names_empty_behaviors(self):
        """Test with empty behaviors dict."""
        config = {"behaviors": {}}

        names = get_behavior_names(config)

        assert names == []


@pytest.mark.unit
class TestMergeHyperparameters:
    """Test merging hyperparameters into ML-Agents config."""

    def test_merge_hyperparameters_single_behavior(self):
        """Test merging hyperparameters for single behavior."""
        base_config = {
            "behaviors": {
                "3DBall": {
                    "trainer_type": "ppo",
                    "hyperparameters": {
                        "batch_size": 64,
                        "learning_rate": 0.0003
                    }
                }
            }
        }

        hyperparameters = {"learning_rate": 0.001, "epsilon": 0.2}

        result = merge_hyperparameters_into_config(
            base_config,
            hyperparameters,
            behavior_name="3DBall"
        )

        assert result["behaviors"]["3DBall"]["hyperparameters"]["batch_size"] == 64
        assert result["behaviors"]["3DBall"]["hyperparameters"]["learning_rate"] == 0.001
        assert result["behaviors"]["3DBall"]["hyperparameters"]["epsilon"] == 0.2

    def test_merge_hyperparameters_all_behaviors(self):
        """Test merging hyperparameters for all behaviors."""
        base_config = {
            "behaviors": {
                "3DBall": {
                    "hyperparameters": {"learning_rate": 0.0003}
                },
                "Walker": {
                    "hyperparameters": {"learning_rate": 0.0003}
                }
            }
        }

        hyperparameters = {"learning_rate": 0.001}

        result = merge_hyperparameters_into_config(
            base_config,
            hyperparameters,
            behavior_name=None  # Update all
        )

        assert result["behaviors"]["3DBall"]["hyperparameters"]["learning_rate"] == 0.001
        assert result["behaviors"]["Walker"]["hyperparameters"]["learning_rate"] == 0.001

    def test_merge_hyperparameters_preserves_other_keys(self):
        """Test that merging preserves other config keys."""
        base_config = {
            "behaviors": {
                "3DBall": {
                    "trainer_type": "ppo",
                    "network_settings": {"hidden_units": 128},
                    "hyperparameters": {"batch_size": 64}
                }
            },
            "engine_settings": {"time_scale": 20}
        }

        hyperparameters = {"learning_rate": 0.001}

        result = merge_hyperparameters_into_config(base_config, hyperparameters)

        assert result["behaviors"]["3DBall"]["trainer_type"] == "ppo"
        assert result["behaviors"]["3DBall"]["network_settings"]["hidden_units"] == 128
        assert result["engine_settings"]["time_scale"] == 20


@pytest.mark.unit
class TestYamlFileOperations:
    """Test YAML file loading and saving."""

    def test_load_and_save_yaml_with_comments(self):
        """Test loading and saving YAML preserves content."""
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("# Comment\nkey: value\nnested:\n  item: 123\n")
            temp_path = f.name

        try:
            # Load
            config, yaml_handler = load_yaml_with_comments(temp_path)
            assert config["key"] == "value"
            assert config["nested"]["item"] == 123

            # Modify and save
            config["key"] = "new_value"
            save_yaml_with_comments(config, temp_path, yaml_handler)

            # Load again
            config2, _ = load_yaml_with_comments(temp_path)
            assert config2["key"] == "new_value"
            assert config2["nested"]["item"] == 123

        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
