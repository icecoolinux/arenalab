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
    
    def wait(self, seconds: int = None, minutes: int = None, steps: int = None):
        """Wait for specified time or steps."""
        if seconds:
            time.sleep(seconds)
        elif minutes:
            time.sleep(minutes * 60)
        elif steps:
            # For steps, we simulate by waiting proportional time
            # In real implementation, this would monitor actual training steps
            time.sleep(steps / 100)  # Rough approximation
    
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
    
    def add_note(self, message: str, target_type: str = "experiment"):
        """Add a note to experiment or run."""
        timestamp = datetime.now(timezone.utc).isoformat()
        note = f"[{timestamp}] {self.context.plugin_name}: {message}"
        
        if target_type == "experiment" or self.context.scope == "experiment":
            # Add to experiment notes
            experiment_id = self.context.target_id
            if self.context.scope != 'experiment':
                run = self.db.runs.find_one({"_id": self.context.target_id})
                experiment_id = run["experiment_id"]
            
            self.db.experiments.update_one(
                {"_id": experiment_id},
                {"$push": {"plugin_notes": note}}
            )
        else:
            # Add to run notes
            run_id = self.context.target_id
            self.db.runs.update_one(
                {"_id": run_id},
                {"$push": {"plugin_notes": note}}
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
    
    def analyze_with_llm(self, text: str) -> str:
        """Analyze text with LLM (placeholder for future LLM integration)."""
        # Placeholder implementation
        # In real implementation, this would call OpenAI/Claude/etc
        return f"Analysis of text ({len(text)} chars): Basic pattern analysis would go here."


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
    
    def get_reward(self) -> float:
        """Extract reward/performance from run (placeholder)."""
        # Placeholder implementation
        # In real implementation, this would parse TensorBoard logs or training output
        return 100.0 + hash(self.run_id) % 100  # Fake performance for demo
    
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