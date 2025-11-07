"""
Simple Plugin API for ultra-easy plugin development.

This module provides a clean, simple interface for plugin developers.
Plugins are just functions that receive context and api objects.
"""

import time
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from dataclasses import dataclass

from db import get_db
from utils.file_tools import sanitize_name
from services.revisions_service import RevisionsService
from models import RevisionBody

logger = logging.getLogger(__name__)


@dataclass
class PluginContext:
    """Context object passed to plugins with current state and settings."""
    plugin_name: str
    scope: str  # 'experiment', 'run', 'revision'
    target_id: str  # experiment_id, run_id, or revision_id
    settings: Dict[str, Any]
    generation: int = 0
    should_stop: bool = False
    metadata: Dict[str, Any] = None
    
    def should_continue(self) -> bool:
        """Check if plugin should continue running."""
        return not self.should_stop


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
        import requests

        if run_id is None:
            if self.context.scope == 'run':
                run_id = self.context.target_id
            else:
                raise ValueError("run_id must be provided when not in run scope")

        try:
            # Query TensorBoard data API directly (TensorBoard is already running and indexing experiments)
            from config import TENSORBOARD_HOST, TENSORBOARD_PATH_PREFIX

            # Build base URL with path prefix (if configured)
            tb_prefix = TENSORBOARD_PATH_PREFIX.rstrip('/')
            tb_base_url = f"{TENSORBOARD_HOST}{tb_prefix}/data"

            # Get available tags for this run
            tags_url = f"{tb_base_url}/plugin/scalars/tags"
            tags_response = requests.get(tags_url, timeout=5)

            # If failed and we have a prefix, try without prefix as fallback
            if tags_response.status_code != 200 and tb_prefix:
                logger.debug(f"Run {run_id}: TensorBoard API with prefix failed (status {tags_response.status_code}), trying without prefix")
                tb_base_url = f"{TENSORBOARD_HOST}/data"
                tags_url = f"{tb_base_url}/plugin/scalars/tags"
                tags_response = requests.get(tags_url, timeout=5)

            if tags_response.status_code != 200:
                logger.debug(f"Run {run_id}: TensorBoard API returned {tags_response.status_code}")
                return {"scalars": {}, "latest": {}, "summary": {}}

            # TensorBoard returns data organized by run name
            tags_data = tags_response.json()

            # Find our run in the TensorBoard data (run_id might be nested in path)
            matching_runs = [run_name for run_name in tags_data.keys() if run_id in run_name]

            if not matching_runs:
                logger.debug(f"Run {run_id}: No data found in TensorBoard yet")
                return {"scalars": {}, "latest": {}, "summary": {}}

            # Use the first matching run
            tb_run_name = matching_runs[0]
            available_tags = list(tags_data[tb_run_name].keys())

            if not available_tags:
                logger.debug(f"Run {run_id}: No scalar tags available yet")
                return {"scalars": {}, "latest": {}, "summary": {}}

            # Filter by requested metrics if specified
            tags_to_fetch = metric_names if metric_names else available_tags

            scalars = {}
            latest = {}
            summary = {}

            # Fetch data for each tag
            for tag in tags_to_fetch:
                if tag not in available_tags:
                    continue

                try:
                    scalars_url = f"{tb_base_url}/plugin/scalars/scalars"
                    params = {"run": tb_run_name, "tag": tag}
                    scalar_response = requests.get(scalars_url, params=params, timeout=5)

                    if scalar_response.status_code != 200:
                        continue

                    data_points = scalar_response.json()
                    if not data_points:
                        continue

                    # Convert to our format: [(step, value, wall_time), ...]
                    data = [(point[1], point[2], point[0]) for point in data_points]  # [wall_time, step, value]
                    scalars[tag] = data

                    # Get latest value
                    latest[tag] = data[-1][1] if data else 0

                    # Calculate summary statistics
                    values = [point[1] for point in data]
                    if values:
                        summary[tag] = {
                            "min": min(values),
                            "max": max(values),
                            "mean": sum(values) / len(values),
                            "latest": values[-1],
                            "count": len(values)
                        }

                except Exception as e:
                    logger.warning(f"Error fetching tag {tag} for run {run_id}: {e}")
                    continue

            # Filter out stale metrics from TensorBoard cache after run restart
            run_doc = self.get_run(run_id)
            if run_doc and run_doc.get("last_cleanup_at"):
                last_cleanup_at = run_doc["last_cleanup_at"]
                # Convert to timestamp for comparison
                cleanup_timestamp = last_cleanup_at.timestamp() if hasattr(last_cleanup_at, 'timestamp') else last_cleanup_at

                # Filter scalars: keep only metrics newer than last cleanup
                filtered_scalars = {}
                for tag, data_points in scalars.items():
                    # Filter data points: (step, value, wall_time)
                    fresh_points = [(step, value, wall_time) for step, value, wall_time in data_points
                                   if wall_time >= cleanup_timestamp]
                    if fresh_points:
                        filtered_scalars[tag] = fresh_points

                # If no fresh metrics, return empty (prevents plugin confusion from stale cache)
                if not filtered_scalars:
                    logger.debug(f"Run {run_id}: All metrics are stale (older than last_cleanup_at), returning empty")
                    return {"scalars": {}, "latest": {}, "summary": {}}

                # Recalculate latest and summary from filtered data
                scalars = filtered_scalars
                latest = {}
                summary = {}
                for tag, data in scalars.items():
                    latest[tag] = data[-1][1] if data else 0
                    values = [point[1] for point in data]
                    if values:
                        summary[tag] = {
                            "min": min(values),
                            "max": max(values),
                            "mean": sum(values) / len(values),
                            "latest": values[-1],
                            "count": len(values)
                        }

            return {
                "scalars": scalars,
                "latest": latest,
                "summary": summary
            }

        except requests.exceptions.RequestException as e:
            logger.warning(f"TensorBoard API not available: {e}")
            return {"scalars": {}, "latest": {}, "summary": {}}
        except Exception as e:
            logger.error(f"Error fetching metrics from TensorBoard: {e}")
            return {"error": str(e), "scalars": {}, "latest": {}, "summary": {}}

    def stop_run(self, run_id: str = None) -> bool:
        """
        Stop a running training process.

        Args:
            run_id: Run ID to stop. If None, uses context.target_id

        Returns:
            True if stopped successfully, False otherwise
        """
        from runner import stop_run as runner_stop_run

        if run_id is None:
            if self.context.scope == 'run':
                run_id = self.context.target_id
            else:
                raise ValueError("run_id must be provided when not in run scope")

        logger.info(f"Plugin {self.context.plugin_name} stopping run {run_id}")
        return runner_stop_run(run_id)

    def create_run(self, config: Dict[str, Any], description: str = "") -> 'SimpleRun':
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
        try:
            # Import runner here to avoid circular imports
            from runner import create_run, execute_run

            # Get experiment and revision info
            if self.context.scope == 'experiment':
                experiment_id = self.context.target_id
                # Get latest revision for this experiment
                revision = self.db.revisions.find_one(
                    {"experiment_id": experiment_id},
                    sort=[("created_at", -1)]
                )
            else:
                # For run-scoped plugins, get experiment info from the run
                run = self.db.runs.find_one({"_id": self.context.target_id})
                experiment_id = run["experiment_id"]
                revision_id = run["revision_id"]
                revision = self.db.revisions.find_one({"_id": revision_id})

            if not revision:
                raise ValueError(f"No revision found for experiment {experiment_id}. Please create a revision first before running this plugin.")

            # Get experiment details
            experiment = self.db.experiments.find_one({"_id": experiment_id})
            if not experiment:
                raise ValueError(f"Could not find experiment {experiment_id}")

            # Get YAML configuration from revision
            yaml_path = revision.get("yaml_path", "")
            if yaml_path:
                # Read YAML content from file
                from utils.file_tools import ensure_workspace_path
                yaml_full_path = ensure_workspace_path(yaml_path)
                try:
                    with open(yaml_full_path, 'r') as f:
                        yaml_text = f.read()
                except Exception as e:
                    logger.error(f"Error reading YAML from {yaml_full_path}: {e}")
                    raise ValueError(f"Could not read YAML configuration: {e}")
            else:
                raise ValueError("Revision has no YAML configuration")

            # Prepare description
            run_description = description or f"Created by {self.context.plugin_name}"

            # Create run using runner (creates DB record and directory structure)
            # config contains only CLI flags (time_scale, no_graphics, num_envs, etc.)
            run_id = create_run(
                experiment=experiment,
                revision=revision,
                yaml_text=yaml_text,
                cli_flags=config,
                description=run_description
            )

            # Execute the run immediately
            execute_run(run_id)

            logger.info(f"Plugin {self.context.plugin_name} created and executed run {run_id}")
            return SimpleRun(run_id, self)

        except Exception as e:
            logger.error(f"Error creating/executing run in plugin {self.context.plugin_name}: {e}")
            raise
    
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
        try:
            from utils.file_tools import ensure_workspace_path
            from utils.yaml_tools import (
                load_yaml_with_comments,
                merge_hyperparameters_into_config,
                validate_mlagents_config
            )
            from io import StringIO

            # Get experiment ID
            experiment_id = self.context.target_id
            if self.context.scope != 'experiment':
                run = self.db.runs.find_one({"_id": self.context.target_id})
                experiment_id = run["experiment_id"]

            experiment = self.db.experiments.find_one({"_id": experiment_id})
            if not experiment:
                raise ValueError(f"Experiment {experiment_id} not found")

            # Get latest revision
            latest_revision = self.db.revisions.find_one(
                {"experiment_id": experiment_id},
                sort=[("created_at", -1)]
            )
            if not latest_revision:
                raise ValueError(
                    f"No parent revision found for experiment {experiment_id}. "
                    "Create an initial revision first."
                )

            parent_revision_id = str(latest_revision["_id"])
            environment_id = latest_revision.get("environment_id")

            # Load parent YAML with comment preservation
            parent_yaml_path = ensure_workspace_path(latest_revision["yaml_path"])
            base_config, yaml_handler = load_yaml_with_comments(parent_yaml_path)

            # Merge hyperparameters into correct nested location
            updated_config = merge_hyperparameters_into_config(
                base_config,
                hyperparameters,
                behavior_name
            )

            # Validate the updated config
            validate_mlagents_config(updated_config)

            # Convert config to YAML string (preserve comments if possible)
            yaml_stream = StringIO()
            yaml_handler.dump(updated_config, yaml_stream)
            yaml_content = yaml_stream.getvalue()

            # Create RevisionBody for service
            revision_body = RevisionBody(
                experiment_id=experiment_id,
                name=name,
                description=notes or f"Auto-generated by {self.context.plugin_name}",
                parent_revision_id=parent_revision_id,
                parent_run_id="",
                yaml=yaml_content,
                cli_flags=hyperparameters,
                environment_id=environment_id
            )

            # Use service to create revision (handles all directory creation and DB operations)
            created_revision = self.revisions_service.create_revision(revision_body)
            revision_id = created_revision["_id"]

            logger.info(f"Plugin {self.context.plugin_name} created revision {revision_id} with hyperparameters")
            return revision_id

        except Exception as e:
            logger.error(f"Error creating revision with hyperparameters in plugin {self.context.plugin_name}: {e}")
            raise

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
        try:
            from utils.file_tools import ensure_workspace_path
            from utils.yaml_tools import (
                load_yaml_with_comments,
                deep_merge_dict,
                validate_mlagents_config
            )
            from io import StringIO

            # Get experiment ID
            experiment_id = self.context.target_id
            if self.context.scope != 'experiment':
                run = self.db.runs.find_one({"_id": self.context.target_id})
                experiment_id = run["experiment_id"]

            experiment = self.db.experiments.find_one({"_id": experiment_id})
            if not experiment:
                raise ValueError(f"Experiment {experiment_id} not found")

            # Get latest revision
            latest_revision = self.db.revisions.find_one(
                {"experiment_id": experiment_id},
                sort=[("created_at", -1)]
            )
            if not latest_revision:
                raise ValueError(
                    f"No parent revision found for experiment {experiment_id}. "
                    "Create an initial revision first."
                )

            parent_revision_id = str(latest_revision["_id"])
            environment_id = latest_revision.get("environment_id")

            # Load parent YAML with comment preservation
            parent_yaml_path = ensure_workspace_path(latest_revision["yaml_path"])
            base_config, yaml_handler = load_yaml_with_comments(parent_yaml_path)

            # Merge based on strategy
            if merge_strategy == "deep":
                updated_config = deep_merge_dict(base_config, config_updates)
            else:
                # Shallow merge
                updated_config = dict(base_config)
                updated_config.update(config_updates)

            # Validate the updated config
            validate_mlagents_config(updated_config)

            # Convert config to YAML string (preserve comments if possible)
            yaml_stream = StringIO()
            yaml_handler.dump(updated_config, yaml_stream)
            yaml_content = yaml_stream.getvalue()

            # Create RevisionBody for service
            revision_body = RevisionBody(
                experiment_id=experiment_id,
                name=name,
                description=notes or f"Auto-generated by {self.context.plugin_name}",
                parent_revision_id=parent_revision_id,
                parent_run_id="",
                yaml=yaml_content,
                cli_flags=config_updates,
                environment_id=environment_id
            )

            # Use service to create revision (handles all directory creation and DB operations)
            created_revision = self.revisions_service.create_revision(revision_body)
            revision_id = created_revision["_id"]

            logger.info(f"Plugin {self.context.plugin_name} created revision {revision_id} with config updates")
            return revision_id

        except Exception as e:
            logger.error(f"Error creating revision with config updates in plugin {self.context.plugin_name}: {e}")
            raise

    def create_revision(self, name: str, config: Dict[str, Any], notes: str = "",
                       yaml_content: str = None, parent_revision_id: str = None,
                       parent_run_id: str = None, environment_id: str = None) -> str:
        """
        Create a new experiment revision (low-level method).

        NOTE: For hyperparameter tuning, use create_revision_with_hyperparameters() instead.
        This method uses RevisionsService for proper revision creation.
        """
        try:
            from utils.file_tools import ensure_workspace_path
            from utils.yaml_tools import (
                load_yaml_with_comments,
                deep_merge_dict,
                validate_mlagents_config
            )
            from io import StringIO
            import yaml as yaml_lib

            # Get experiment ID
            experiment_id = self.context.target_id
            if self.context.scope != 'experiment':
                run = self.db.runs.find_one({"_id": self.context.target_id})
                experiment_id = run["experiment_id"]

            experiment = self.db.experiments.find_one({"_id": experiment_id})
            if not experiment:
                raise ValueError(f"Experiment {experiment_id} not found")

            # If no parent revision specified, try to get the latest one
            if not parent_revision_id:
                latest_revision = self.db.revisions.find_one(
                    {"experiment_id": experiment_id},
                    sort=[("created_at", -1)]
                )
                parent_revision_id = str(latest_revision["_id"]) if latest_revision else None

            # Get environment_id from parent revision if not provided
            if not environment_id:
                if parent_revision_id:
                    parent_rev = self.db.revisions.find_one({"_id": parent_revision_id})
                    environment_id = parent_rev.get("environment_id") if parent_rev else None

                if not environment_id:
                    raise ValueError(
                        f"Cannot create revision: no environment_id provided and no parent revision found. "
                        "Please create an initial revision for the experiment first."
                    )

            # Prepare YAML content
            if not yaml_content:
                # Load parent revision and merge with new config
                if parent_revision_id:
                    parent_rev = self.db.revisions.find_one({"_id": parent_revision_id})
                    if parent_rev and parent_rev.get("yaml_path"):
                        parent_yaml_path = ensure_workspace_path(parent_rev["yaml_path"])
                        try:
                            base_config, yaml_handler = load_yaml_with_comments(parent_yaml_path)
                        except Exception as e:
                            logger.warning(f"Could not load parent YAML with comments: {e}, using basic load")
                            with open(parent_yaml_path, 'r') as f:
                                base_config = yaml_lib.safe_load(f) or {}
                            yaml_handler = None
                    else:
                        base_config = {}
                        yaml_handler = None
                else:
                    base_config = {}
                    yaml_handler = None

                # Deep merge configs
                updated_config = deep_merge_dict(base_config, config)

                # Validate config
                try:
                    validate_mlagents_config(updated_config)
                except Exception as e:
                    logger.warning(f"Config validation warning: {e}")

                # Convert to YAML string
                if yaml_handler:
                    yaml_stream = StringIO()
                    yaml_handler.dump(updated_config, yaml_stream)
                    yaml_content = yaml_stream.getvalue()
                else:
                    yaml_content = yaml_lib.dump(updated_config, default_flow_style=False)

            # Create RevisionBody for service
            revision_body = RevisionBody(
                experiment_id=experiment_id,
                name=name,
                description=notes or f"Auto-generated by {self.context.plugin_name}",
                parent_revision_id=parent_revision_id or "",
                parent_run_id=parent_run_id or "",
                yaml=yaml_content,
                cli_flags=config,
                environment_id=environment_id
            )

            # Use service to create revision (handles all directory creation and DB operations)
            created_revision = self.revisions_service.create_revision(revision_body)
            revision_id = created_revision["_id"]

            logger.info(f"Plugin {self.context.plugin_name} created revision {revision_id}")
            return revision_id

        except Exception as e:
            logger.error(f"Error creating revision in plugin {self.context.plugin_name}: {e}")
            raise
    
    def wait(self, seconds: int = None, minutes: int = None, steps: int = None,
             monitor_run: bool = True, check_interval: float = 1.0):
        """
        Wait for specified time or steps, with optional early exit if current run completes.

        Args:
            seconds: Wait time in seconds
            minutes: Wait time in minutes
            steps: Wait time based on training steps (approximated)
            monitor_run: If True and in 'run' scope, exits early when the run completes (default: True)
            check_interval: Polling interval in seconds (default: 1.0)
        """
        # Calculate total wait time in seconds
        if seconds:
            wait_time = seconds
        elif minutes:
            wait_time = minutes * 60
        elif steps:
            wait_time = steps / 100  # Rough approximation
        else:
            return  # No wait time specified

        start_time = time.time()

        # Determine if we should monitor a run
        should_monitor = monitor_run and self.context.scope == 'run'
        run_id = self.context.target_id if should_monitor else None

        # Non-blocking wait with periodic checks
        while time.time() - start_time < wait_time:
            # Check if monitored run has completed
            if should_monitor and run_id:
                run = self.db.runs.find_one({"_id": run_id})
                if run:
                    status = run.get("status")
                    if status not in ["running", "starting"]:
                        logger.info(f"Run {run_id} completed with status '{status}'. Exiting wait early.")
                        return

            # Sleep for check_interval or remaining time, whichever is smaller
            remaining = wait_time - (time.time() - start_time)
            sleep_time = min(check_interval, remaining)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def wait_for_completion(self, runs: List['SimpleRun'], timeout_minutes: int = 60):
        """Wait for runs to complete."""
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        while time.time() - start_time < timeout_seconds:
            all_completed = True
            for run in runs:
                if run.is_running():
                    all_completed = False
                    break
            
            if all_completed:
                break
                
            time.sleep(10)  # Check every 10 seconds
    
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
    
    def mutate_config(self, base_config: Dict[str, Any], 
                     mutation_rate: float = 0.2) -> Dict[str, Any]:
        """Create a mutated version of a configuration."""
        import random
        import copy
        
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
            True if ANTHROPIC_API_KEY or OPENAI_API_KEY is set
        """
        import os
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))

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
        import os
        import json

        if not self.is_llm_available():
            raise RuntimeError(
                "LLM not available. Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
            )

        # Prepare full prompt with context if provided
        full_prompt = prompt
        if context_data:
            context_str = json.dumps(context_data, indent=2, default=str)
            full_prompt = f"{prompt}\n\nContext Data:\n```json\n{context_str}\n```"
        print(full_prompt)
        # Try Anthropic first (Claude)
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_key)

                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2048,
                    messages=[
                        {"role": "user", "content": full_prompt}
                    ]
                )

                return response.content[0].text

            except ImportError:
                logger.warning("anthropic library not installed. Install with: pip install anthropic")
            except Exception as e:
                logger.error(f"Error calling Anthropic API: {e}")
                raise RuntimeError(f"Anthropic API error: {e}")

        # Fall back to OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=openai_key)

                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "user", "content": full_prompt}
                    ],
                    max_tokens=2048
                )

                return response.choices[0].message.content

            except ImportError:
                logger.warning("openai library not installed. Install with: pip install openai")
            except Exception as e:
                logger.error(f"Error calling OpenAI API: {e}")
                raise RuntimeError(f"OpenAI API error: {e}")

        raise RuntimeError("No LLM library available. Install with: pip install anthropic or pip install openai")


class SimpleRun:
    """Simple wrapper around run data for plugin convenience."""
    
    def __init__(self, run_id: str, api: PluginAPI):
        self.run_id = run_id
        self.api = api
    
    def is_running(self) -> bool:
        """Check if run is still active."""
        run = self.api.db.runs.find_one({"_id": self.run_id})
        return run and run.get("status") in ["running", "starting"]
    
    def is_completed(self) -> bool:
        """Check if run completed successfully."""
        run = self.api.db.runs.find_one({"_id": self.run_id})
        return run and run.get("status") == "completed"
    
    def get_status(self) -> str:
        """Get current run status."""
        run = self.api.db.runs.find_one({"_id": self.run_id})
        return run.get("status", "unknown") if run else "not_found"
    
    def get_reward(self, metric_name: str = "Environment/Cumulative Reward") -> Optional[float]:
        """
        Extract latest reward from TensorBoard metrics.

        Args:
            metric_name: Name of the reward metric (default: "Environment/Cumulative Reward")

        Returns:
            Latest reward value or None if not found
        """
        metrics = self.api.get_metrics(self.run_id, metric_names=[metric_name])
        if "latest" in metrics and metric_name in metrics["latest"]:
            return metrics["latest"][metric_name]
        return None
    
    def get_logs(self, last_lines: int = 100) -> List[str]:
        """Get recent log lines from run."""
        run = self.api.db.runs.find_one({"_id": self.run_id})
        if not run or not run.get("stdout_log_path"):
            return []
        
        try:
            with open(run["stdout_log_path"], 'r') as f:
                lines = f.readlines()
                return [line.strip() for line in lines[-last_lines:]]
        except Exception:
            return []
    
    def add_note(self, message: str):
        """Add note to this run."""
        self.api.add_note(message, target_type="run")
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get run configuration."""
        run = self.api.db.runs.find_one({"_id": self.run_id})
        return run.get("cli_flags", {}) if run else {}

    def get_metrics(self, metric_names: List[str] = None) -> Dict[str, Any]:
        """
        Get training metrics from TensorBoard.

        Args:
            metric_names: List of specific metrics to fetch. If None, fetches all available

        Returns:
            Dictionary with metric data from TensorBoard
        """
        return self.api.get_metrics(self.run_id, metric_names)

    def stop(self) -> bool:
        """
        Stop this run.

        Returns:
            True if stopped successfully
        """
        return self.api.stop_run(self.run_id)

    def is_stuck(self, metric_name: str = "Environment/Cumulative Reward",
                 window_size: int = 10, variance_threshold: float = 1e-6) -> bool:
        """
        Detect if training is stuck (no progress).

        Args:
            metric_name: Metric to check for progress
            window_size: Number of recent data points to analyze
            variance_threshold: Minimum variance to consider as progress

        Returns:
            True if training appears stuck
        """
        metrics = self.api.get_metrics(self.run_id, metric_names=[metric_name])

        if "scalars" not in metrics or metric_name not in metrics["scalars"]:
            return False  # Can't determine, assume not stuck

        data = metrics["scalars"][metric_name]
        if len(data) < window_size:
            return False  # Not enough data yet

        # Get recent values
        recent_values = [value for _, value, _ in data[-window_size:]]

        # Calculate variance
        mean = sum(recent_values) / len(recent_values)
        variance = sum((x - mean) ** 2 for x in recent_values) / len(recent_values)

        return variance < variance_threshold