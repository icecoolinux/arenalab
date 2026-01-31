"""
Simple Plugin API for ultra-easy plugin development.

This module provides a clean, simple interface for plugin developers.
Plugins are just functions that receive context and api objects.
"""

import logging
import copy
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from db import get_db
from services.revisions_service import RevisionsService

# Import from refactored modules
from plugins.core.context import PluginContext
from plugins.core.runs import SimpleRun, create_run, stop_run, wait, wait_for_completion
from plugins.core.metrics import get_metrics
from plugins.core.revisions import (
    create_revision,
    create_revision_with_hyperparameters,
    create_revision_with_config_updates
)
from plugins.core.llm import is_llm_available, llm
from plugins.core.database import add_plugin_log

logger = logging.getLogger(__name__)

# ANSI color codes for console logging
LOG_COLORS = {
    "DEBUG": "\033[36m",    # Cyan
    "INFO": "\033[32m",     # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",    # Red
    "RESET": "\033[0m"      # Reset
}

# Re-export for backward compatibility
__all__ = ['PluginContext', 'PluginAPI', 'SimpleRun']


class PluginAPI:
    """Simple API for plugin operations."""

    def __init__(self, context: PluginContext):
        self.context = context
        self.db = get_db()
        self.revisions_service = RevisionsService()

    def get_run(self, run_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Get run document from database.

        Args:
            run_id: Run ID to fetch. If None, uses context.target_id

        Returns:
            Run document or None if not found
        """
        if run_id is None:
            if self.context.scope == 'run':
                run_id = self.context.target_id
            else:
                raise ValueError("run_id must be provided when not in run scope")

        return self.db.runs.find_one({"_id": run_id})

    def get_metrics(self, run_id: str = None, metric_names: List[str] = None) -> Dict[str, Any]:
        """
        Get training metrics from TensorBoard via its data API.

        Args:
            run_id: Run ID to fetch metrics for. If None, uses context.target_id
            metric_names: List of specific metrics to fetch. If None, fetches all available

        Returns:
            Dictionary with metric data: {
                "scalars": {metric_name: [(step, value, wall_time), ...]},
                "latest": {metric_name: value},
                "summary": {metric_name: {"min": x, "max": y, "mean": z, "latest": w}}
            }
        """
        if run_id is None:
            if self.context.scope == 'run':
                run_id = self.context.target_id
            else:
                raise ValueError("run_id must be provided when not in run scope")

        return get_metrics(self.db, run_id, metric_names)

    def stop_run(self, run_id: str = None) -> bool:
        """
        Stop a running training process.

        Args:
            run_id: Run ID to stop. If None, uses context.target_id

        Returns:
            True if stopped successfully, False otherwise
        """
        return stop_run(self, run_id)

    def create_run(self, config: Dict[str, Any], description: str = "") -> SimpleRun:
        """
        Create a new run with given configuration and execute it.

        Args:
            config: CLI flags for mlagents-learn (time_scale, no_graphics, num_envs, etc.)
                   NOTE: This is NOT for hyperparameters. Use create_revision_with_hyperparameters()
                   to create a revision with new hyperparameters, then create a run from that revision.
            description: Run description

        Returns:
            SimpleRun object for the created run
        """
        return create_run(self, config, description)

    def create_revision_with_hyperparameters(
        self,
        name: str,
        hyperparameters: Dict[str, Any],
        behavior_name: str = None,
        notes: str = ""
    ) -> str:
        """
        Create a new revision with hyperparameter updates.

        This is the recommended method for plugins that tune hyperparameters.
        Properly merges hyperparameters into the nested ML-Agents config structure.

        Args:
            name: Name for the new revision
            hyperparameters: Dict of hyperparameters to update (e.g., {"learning_rate": 0.001})
            behavior_name: Specific behavior to update, or None to update all behaviors
            notes: Description or notes for the revision

        Returns:
            Created revision ID

        Example:
            api.create_revision_with_hyperparameters(
                name="PBT_Gen1_Best",
                hyperparameters={"learning_rate": 0.001, "batch_size": 128},
                notes="Best performer from generation 1"
            )
        """
        return create_revision_with_hyperparameters(self, name, hyperparameters, behavior_name, notes)

    def create_revision_with_config_updates(
        self,
        name: str,
        config_updates: Dict[str, Any],
        merge_strategy: str = "deep",
        notes: str = ""
    ) -> str:
        """
        Create a new revision with custom configuration updates.

        For advanced use cases requiring updates beyond hyperparameters.

        Args:
            name: Name for the new revision
            config_updates: Dictionary of config updates to merge
            merge_strategy: "deep" (recursive merge) or "shallow" (top-level merge)
            notes: Description or notes for the revision

        Returns:
            Created revision ID

        Example:
            api.create_revision_with_config_updates(
                name="BiggerNetwork",
                config_updates={
                    "behaviors": {
                        "EnemyBehavior": {
                            "network_settings": {
                                "hidden_units": 256,
                                "num_layers": 3
                            }
                        }
                    }
                }
            )
        """
        return create_revision_with_config_updates(self, name, config_updates, merge_strategy, notes)

    def create_revision(
        self,
        name: str,
        config: Dict[str, Any],
        notes: str = "",
        yaml_content: str = None,
        parent_revision_id: str = None,
        parent_run_id: str = None,
        environment_id: str = None
    ) -> str:
        """
        Create a new experiment revision (low-level method).

        NOTE: For hyperparameter tuning, use create_revision_with_hyperparameters() instead.
        This method uses RevisionsService for proper revision creation.
        """
        return create_revision(
            self, name, config, notes,
            yaml_content, parent_revision_id, parent_run_id, environment_id
        )

    def wait(
        self,
        seconds: int = None,
        minutes: int = None,
        steps: int = None,
        monitor_run: bool = True,
        check_interval: float = 1.0
    ):
        """
        Wait for specified time or steps, with optional early exit if current run completes.

        Args:
            seconds: Wait time in seconds
            minutes: Wait time in minutes
            steps: Wait time based on training steps (approximated)
            monitor_run: If True and in 'run' scope, exits early when the run completes (default: True)
            check_interval: Polling interval in seconds (default: 1.0)
        """
        wait(self, seconds, minutes, steps, monitor_run, check_interval)

    def wait_for_completion(self, runs: List[SimpleRun], timeout_minutes: int = 60):
        """Wait for runs to complete."""
        wait_for_completion(self, runs, timeout_minutes)

    def get_experiment_data(self) -> Dict[str, Any]:
        """Get experiment data and history."""
        experiment_id = self.context.target_id
        if self.context.scope != 'experiment':
            run = self.db.runs.find_one({"_id": self.context.target_id})
            experiment_id = run["experiment_id"]

        # Get experiment
        experiment = self.db.experiments.find_one({"_id": experiment_id})

        # Get all runs for this experiment
        runs = list(self.db.runs.find({"experiment_id": experiment_id}))

        # Get all revisions
        revisions = list(self.db.revisions.find({"experiment_id": experiment_id}))

        return {
            "experiment": experiment,
            "runs": runs,
            "revisions": revisions
        }

    def add_note(self, message: str, target_type: str = "run"):
        """Add a note to experiment or run results_text field."""
        timestamp = datetime.now(timezone.utc)
        formatted_note = f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"

        if target_type == "experiment" or self.context.scope == "experiment":
            # Add to experiment results_text
            experiment_id = self.context.target_id
            if self.context.scope != 'experiment':
                run = self.db.runs.find_one({"_id": self.context.target_id})
                experiment_id = run["experiment_id"]

            # Append to results_text
            experiment = self.db.experiments.find_one({"_id": experiment_id})
            current_text = experiment.get("results_text", "")
            new_text = current_text + formatted_note

            self.db.experiments.update_one(
                {"_id": experiment_id},
                {"$set": {"results_text": new_text}}
            )
        else:
            # Add to run results_text
            run_id = self.context.target_id
            run = self.db.runs.find_one({"_id": run_id})
            current_text = run.get("results_text", "")
            new_text = current_text + formatted_note

            self.db.runs.update_one(
                {"_id": run_id},
                {"$set": {"results_text": new_text}}
            )

    def mutate_config(self, base_config: Dict[str, Any], mutation_rate: float = 0.2) -> Dict[str, Any]:
        """Create a mutated version of a configuration."""
        new_config = copy.deepcopy(base_config)

        # Simple mutation strategy for numeric values
        for key, value in new_config.items():
            if isinstance(value, (int, float)) and random.random() < mutation_rate:
                if isinstance(value, int):
                    new_config[key] = int(value * (1 + random.uniform(-0.2, 0.2)))
                else:
                    new_config[key] = value * (1 + random.uniform(-0.2, 0.2))

        return new_config

    def is_llm_available(self) -> bool:
        """
        Check if LLM is available (API keys configured).

        Returns:
            True if API keys are configured in database or environment
        """
        return is_llm_available(self)

    def llm(self, prompt: str, context_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Query LLM with a prompt and optional context data.

        Args:
            prompt: The prompt/question to send to the LLM
            context_data: Optional dictionary of context data to include in the prompt

        Returns:
            LLM response text

        Raises:
            RuntimeError: If LLM is not available or API call fails
        """
        return llm(self, prompt, context_data)

    def log(self, message: str, level: str = "INFO", metadata: Optional[Dict[str, Any]] = None):
        """
        Log a message from the plugin.

        This method provides centralized logging for plugins:
        - Prints to console with colored output
        - Saves to MongoDB for frontend retrieval
        - Associates logs with the current plugin execution

        Args:
            message: The log message
            level: Log level (DEBUG, INFO, WARNING, ERROR). Default: INFO
            metadata: Optional dictionary with additional context/data

        Example:
            api.log("Training started", level="INFO")
            api.log("Stuck detection triggered", level="WARNING", metadata={"step": 1000})
            api.log("Failed to fetch metrics", level="ERROR")
        """
        level = level.upper()
        if level not in LOG_COLORS:
            level = "INFO"

        # Print to console with color
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        color = LOG_COLORS.get(level, "")
        reset = LOG_COLORS["RESET"]
        plugin_name = self.context.plugin_name

        # Format: [TIMESTAMP] [PLUGIN_NAME] LEVEL: message
        console_message = f"[{timestamp}] [{plugin_name}] {color}{level}{reset}: {message}"
        print(console_message)

        # Save to MongoDB if execution_id is available
        if self.context.execution_id:
            try:
                add_plugin_log(
                    execution_id=self.context.execution_id,
                    level=level,
                    message=message,
                    metadata=metadata
                )
            except Exception as e:
                # Don't fail the plugin if logging fails
                logger.error(f"Failed to save plugin log to database: {e}")
