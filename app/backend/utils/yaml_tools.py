"""
YAML and configuration utilities for ML-Agents.

Provides tools for:
- YAML parsing and serialization with comment preservation
- Deep dictionary merging
- ML-Agents configuration validation
- Hyperparameter injection into nested structures
"""

import yaml
from typing import Dict, Any, Optional, List
from ruamel.yaml import YAML
import copy
import logging

logger = logging.getLogger(__name__)


def merge_flags(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
	"""Merge two flag dictionaries (shallow merge)."""
	out = dict(defaults or {})
	out.update(overrides or {})
	return out


def ensure_yaml(text: str) -> str:
	"""Validate YAML text can be parsed."""
	_ = yaml.safe_load(text)
	return text


def load_yaml_with_comments(file_path: str) -> tuple:
	"""
	Load YAML file preserving comments and formatting.

	Returns:
		tuple: (config_dict, yaml_handler) for later saving with preserved comments
	"""
	yaml_handler = YAML()
	yaml_handler.preserve_quotes = True
	yaml_handler.default_flow_style = False
	yaml_handler.width = 4096  # Prevent line wrapping

	try:
		with open(file_path, 'r') as f:
			config = yaml_handler.load(f)
		return config, yaml_handler
	except Exception as e:
		logger.error(f"Error loading YAML with comments from {file_path}: {e}")
		# Fallback to standard yaml
		with open(file_path, 'r') as f:
			config = yaml.safe_load(f)
		return config, yaml_handler


def save_yaml_with_comments(config: dict, file_path: str, yaml_handler: YAML = None):
	"""
	Save YAML file preserving comments and formatting.

	Args:
		config: Configuration dictionary
		file_path: Path to save YAML file
		yaml_handler: Optional YAML handler from load_yaml_with_comments()
	"""
	if yaml_handler is None:
		yaml_handler = YAML()
		yaml_handler.preserve_quotes = True
		yaml_handler.default_flow_style = False
		yaml_handler.width = 4096

	try:
		with open(file_path, 'w') as f:
			yaml_handler.dump(config, f)
	except Exception as e:
		logger.error(f"Error saving YAML with comments to {file_path}: {e}")
		raise


def deep_merge_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
	"""
	Deep merge two dictionaries recursively.

	Args:
		base: Base dictionary
		updates: Updates to merge into base

	Returns:
		Merged dictionary (base is not modified)

	Example:
		base = {"a": {"b": 1, "c": 2}}
		updates = {"a": {"c": 3, "d": 4}}
		result = {"a": {"b": 1, "c": 3, "d": 4}}
	"""
	result = copy.deepcopy(base)

	for key, value in updates.items():
		if key in result and isinstance(result[key], dict) and isinstance(value, dict):
			# Recursively merge nested dictionaries
			result[key] = deep_merge_dict(result[key], value)
		else:
			# Override or add new key
			result[key] = copy.deepcopy(value)

	return result


def get_behavior_names(config: Dict[str, Any]) -> List[str]:
	"""
	Extract behavior names from ML-Agents config.

	Args:
		config: ML-Agents configuration dictionary

	Returns:
		List of behavior names
	"""
	if "behaviors" in config and isinstance(config["behaviors"], dict):
		return list(config["behaviors"].keys())
	return []


def merge_hyperparameters_into_config(
	base_config: Dict[str, Any],
	hyperparameters: Dict[str, Any],
	behavior_name: Optional[str] = None
) -> Dict[str, Any]:
	"""
	Merge hyperparameters into ML-Agents config at correct nested location.

	Args:
		base_config: Base ML-Agents configuration
		hyperparameters: Hyperparameters to merge (e.g., {"learning_rate": 0.001})
		behavior_name: Specific behavior to update, or None to update all behaviors

	Returns:
		Updated configuration with hyperparameters merged

	Example:
		config = merge_hyperparameters_into_config(
			base_config,
			{"learning_rate": 0.001, "batch_size": 128},
			behavior_name="EnemyBehavior"
		)
		# Result: config["behaviors"]["EnemyBehavior"]["hyperparameters"]["learning_rate"] = 0.001
	"""
	result = copy.deepcopy(base_config)

	# Ensure behaviors section exists
	if "behaviors" not in result or not isinstance(result["behaviors"], dict):
		logger.warning("Config has no 'behaviors' section, cannot merge hyperparameters")
		return result

	# Determine which behaviors to update
	if behavior_name:
		behavior_names = [behavior_name] if behavior_name in result["behaviors"] else []
		if not behavior_names:
			logger.warning(f"Behavior '{behavior_name}' not found in config")
	else:
		# Update all behaviors
		behavior_names = list(result["behaviors"].keys())

	# Merge hyperparameters into each behavior
	for name in behavior_names:
		if "hyperparameters" not in result["behaviors"][name]:
			result["behaviors"][name]["hyperparameters"] = {}

		# Merge hyperparameters
		result["behaviors"][name]["hyperparameters"].update(hyperparameters)
		logger.debug(f"Merged hyperparameters into behavior '{name}': {hyperparameters}")

	return result


def validate_mlagents_config(config: Dict[str, Any]) -> bool:
	"""
	Validate ML-Agents configuration structure.

	Args:
		config: Configuration dictionary to validate

	Returns:
		True if valid, raises ValueError if invalid
	"""
	if not isinstance(config, dict):
		raise ValueError("Config must be a dictionary")

	# Check for behaviors section
	if "behaviors" not in config:
		raise ValueError("Config missing required 'behaviors' section")

	if not isinstance(config["behaviors"], dict):
		raise ValueError("'behaviors' must be a dictionary")

	if len(config["behaviors"]) == 0:
		raise ValueError("'behaviors' section is empty")

	# Validate each behavior has required fields
	for behavior_name, behavior_config in config["behaviors"].items():
		if not isinstance(behavior_config, dict):
			raise ValueError(f"Behavior '{behavior_name}' must be a dictionary")

		# Check for trainer_type
		if "trainer_type" not in behavior_config:
			logger.warning(f"Behavior '{behavior_name}' missing 'trainer_type'")

	return True