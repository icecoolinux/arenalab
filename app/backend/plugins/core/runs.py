"""
Run operations and SimpleRun wrapper class for plugins.
"""

import logging
import time
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.core.api import PluginAPI

logger = logging.getLogger(__name__)


class SimpleRun:
    """Simple wrapper around run data for plugin convenience."""

    def __init__(self, run_id: str, api: 'PluginAPI'):
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


def create_run(
    api: 'PluginAPI',
    config: Dict[str, Any],
    description: str = ""
) -> SimpleRun:
    """
    Create a new run with given configuration and execute it.

    Args:
        api: PluginAPI instance
        config: CLI flags for mlagents-learn (time_scale, no_graphics, num_envs, etc.)
               NOTE: This is NOT for hyperparameters. Use create_revision_with_hyperparameters()
               to create a revision with new hyperparameters, then create a run from that revision.
        description: Run description

    Returns:
        SimpleRun object for the created run
    """
    try:
        # Import runner here to avoid circular imports
        from runner import create_run as runner_create_run, execute_run

        # Get experiment and revision info
        if api.context.scope == 'experiment':
            experiment_id = api.context.target_id
            # Get latest revision for this experiment
            revision = api.db.revisions.find_one(
                {"experiment_id": experiment_id},
                sort=[("created_at", -1)]
            )
        else:
            # For run-scoped plugins, get experiment info from the run
            run = api.db.runs.find_one({"_id": api.context.target_id})
            experiment_id = run["experiment_id"]
            revision_id = run["revision_id"]
            revision = api.db.revisions.find_one({"_id": revision_id})

        if not revision:
            raise ValueError(f"No revision found for experiment {experiment_id}. Please create a revision first before running this plugin.")

        # Get experiment details
        experiment = api.db.experiments.find_one({"_id": experiment_id})
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
        run_description = description or f"Created by {api.context.plugin_name}"

        # Create run using runner (creates DB record and directory structure)
        # config contains only CLI flags (time_scale, no_graphics, num_envs, etc.)
        run_id = runner_create_run(
            experiment=experiment,
            revision=revision,
            yaml_text=yaml_text,
            cli_flags=config,
            description=run_description
        )

        # Execute the run immediately
        execute_run(run_id)

        logger.info(f"Plugin {api.context.plugin_name} created and executed run {run_id}")
        return SimpleRun(run_id, api)

    except Exception as e:
        logger.error(f"Error creating/executing run in plugin {api.context.plugin_name}: {e}")
        raise


def stop_run(api: 'PluginAPI', run_id: str = None) -> bool:
    """
    Stop a running training process.

    Args:
        api: PluginAPI instance
        run_id: Run ID to stop. If None, uses context.target_id

    Returns:
        True if stopped successfully, False otherwise
    """
    from runner import stop_run as runner_stop_run

    if run_id is None:
        if api.context.scope == 'run':
            run_id = api.context.target_id
        else:
            raise ValueError("run_id must be provided when not in run scope")

    logger.info(f"Plugin {api.context.plugin_name} stopping run {run_id}")
    return runner_stop_run(run_id)


def wait_for_completion(
    api: 'PluginAPI',
    runs: List[SimpleRun],
    timeout_minutes: int = 60
):
    """
    Wait for runs to complete.

    Args:
        api: PluginAPI instance
        runs: List of SimpleRun objects to wait for
        timeout_minutes: Maximum time to wait in minutes
    """
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


def wait(
    api: 'PluginAPI',
    seconds: int = None,
    minutes: int = None,
    steps: int = None,
    monitor_run: bool = True,
    check_interval: float = 1.0
):
    """
    Wait for specified time or steps, with optional early exit if current run completes.

    Args:
        api: PluginAPI instance
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
    should_monitor = monitor_run and api.context.scope == 'run'
    run_id = api.context.target_id if should_monitor else None

    # Non-blocking wait with periodic checks
    while time.time() - start_time < wait_time:
        # Check if monitored run has completed
        if should_monitor and run_id:
            run = api.db.runs.find_one({"_id": run_id})
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
