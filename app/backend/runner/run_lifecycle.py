"""
Run lifecycle management for ML-Agents training.

Handles run creation, execution, restart logic, and status management.
"""
import os
import uuid
import subprocess
import threading
import signal
import logging
import shutil
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from pathlib import Path

from db import get_db
from utils.yaml_tools import ensure_yaml
from utils.file_tools import new_file, ensure_run_structure, to_relative_path, ensure_workspace_path
from utils.env_tools import find_environment_executable
from exceptions import RunnerError, ValidationError, ProcessError

from .port_manager import allocate_ports, deallocate_ports
from .process_manager import (
    RUN_PROCS, RUN_STATUS, RUN_THREADS,
    monitor_process_health, stop_run as pm_stop_run
)

logger = logging.getLogger(__name__)
WORKSPACE = os.getenv("WORKSPACE", "/workspace")


def _get_run_directory(run_id: str) -> str:
    """Get the run directory path by looking up run metadata from database"""
    try:
        db = get_db()
        run_doc = db.runs.find_one({"_id": run_id})
        if not run_doc:
            # Fallback for legacy runs or runs not in database
            return f"{WORKSPACE}/runs/{run_id}"

        experiment_id = run_doc.get("experiment_id")
        revision_id = run_doc.get("revision_id")

        if experiment_id and revision_id:
            return ensure_run_structure(experiment_id, revision_id, run_id)
        else:
            # Fallback for runs without proper metadata
            return f"{WORKSPACE}/runs/{run_id}"
    except Exception:
        # Fallback on any error
        return f"{WORKSPACE}/runs/{run_id}"


def _resolve_environment_path(env_path: str, executable_file: str = None) -> str:
    """
    Resolve environment path to executable.
    Handles both old single-file paths and new directory-based paths with separate executable files.
    """
    try:
        if not env_path:
            raise ValidationError("Environment path is required")

        # Check if path exists
        if not os.path.exists(env_path):
            raise ValidationError(f"Environment path does not exist: {env_path}")

        # If it's a file and executable, return as is (legacy support)
        if os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            logger.info(f"Using environment file: {env_path}")
            return env_path

        # If it's a directory, construct path from env_path + executable_file
        if os.path.isdir(env_path):
            if executable_file:
                # Construct full executable path
                full_executable_path = os.path.join(env_path, executable_file)
                if os.path.exists(full_executable_path) and os.access(full_executable_path, os.X_OK):
                    logger.info(f"Using environment executable: {full_executable_path}")
                    return full_executable_path
                else:
                    logger.warning(f"Executable file not found or not executable: {full_executable_path}")

            # Fall back to trying to find executable (legacy compatibility)
            executable_relative = find_environment_executable(env_path)
            if executable_relative:
                full_executable_path = os.path.join(env_path, executable_relative)
                if os.path.exists(full_executable_path) and os.access(full_executable_path, os.X_OK):
                    logger.info(f"Found environment executable: {full_executable_path}")
                    return full_executable_path

            # Fall back to directory path (some ML-Agents setups work with directories)
            logger.warning(f"No executable found in {env_path}, using directory path")
            return env_path

        # If we get here, path exists but is neither executable file nor directory
        logger.warning(f"Environment path is not executable or directory: {env_path}")
        return env_path

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error resolving environment path: {e}")
        raise ValidationError(f"Error resolving environment path: {e}")


def _validate_run_params(experiment: dict, revision: dict, yaml_text: str) -> str:
    """
    Validate run parameters before launching.

    Args:
        experiment: Experiment document
        revision: Revision document
        yaml_text: YAML configuration content

    Returns:
        Resolved environment executable path

    Raises:
        ValidationError: If validation fails
    """
    if not experiment:
        raise ValidationError("Experiment data is required")

    if not yaml_text or not yaml_text.strip():
        raise ValidationError("YAML configuration is required")

    # Validate critical experiment fields
    if "_id" not in experiment:
        raise ValidationError("Experiment must have an _id")

    # Validate revision
    if not revision:
        raise ValidationError("Revision data is required")

    if "_id" not in revision:
        raise ValidationError("Revision must have an _id")

    # Get environment path from revision's environment_id
    environment_id = revision.get("environment_id")
    if not environment_id:
        raise ValidationError(f"Revision {revision['_id']} has no environment_id")

    # Fetch environment to get env_path and executable_file
    try:
        db = get_db()
        environment = db.environments.find_one({"_id": environment_id})
        if not environment:
            raise ValidationError(f"Environment {environment_id} not found")

        env_path = environment.get("env_path")
        executable_file = environment.get("executable_file")

        if not env_path:
            raise ValidationError(f"Environment {environment_id} has no env_path")

        # Convert env_path to use current WORKSPACE (handles dev vs prod differences)
        env_path = ensure_workspace_path(to_relative_path(env_path))

    except Exception as e:
        logger.error(f"Error fetching environment path: {e}")
        raise ValidationError(f"Error fetching environment path: {e}")

    # Use the resolver to validate and get proper executable path
    try:
        resolved_path = _resolve_environment_path(env_path, executable_file)
        return resolved_path
    except ValidationError as e:
        logger.error(f"Environment validation failed: {e}")
        raise


def create_run(
    experiment: dict,
    revision: dict,
    yaml_text: str,
    cli_flags: dict,
    description: str = "",
    results_text: str = "",
    parent_run_id: Optional[str] = None,
    parent_revision_id: Optional[str] = None,
    enabled_plugins: List[dict] = None
) -> str:
    """
    Create a new ML-Agents run without executing it (immutable).

    Args:
        experiment: Experiment document
        revision: Revision document
        yaml_text: YAML configuration content
        cli_flags: CLI flags for mlagents-learn (time_scale, no_graphics, num_envs, etc.)
        description: Run description
        results_text: Run results notes
        parent_run_id: Optional parent run ID
        parent_revision_id: Optional parent revision ID
        enabled_plugins: Optional list of enabled plugins for this run

    Returns:
        Created run ID

    Raises:
        RunnerError: If run creation fails
        ValidationError: If validation fails
    """
    try:
        # Validate input parameters and get resolved environment path
        resolved_env_path = _validate_run_params(experiment, revision, yaml_text)

        db = get_db()
        run_id = str(uuid.uuid4())
        logger.info(f"Creating new run {run_id} for experiment {experiment.get('_id')}")

        try:
            # Get experiment and revision IDs
            experiment_id = experiment.get('_id')
            revision_id = revision.get('_id')

            if not experiment_id or not revision_id:
                raise RunnerError("experiment_id and revision_id are required for run creation")

            # Get names for directory structure
            experiment_name = experiment.get('name', 'unknown')
            revision_name = revision.get('name', 'unknown')

            # Create run directory structure using the new path format with names
            run_dir = ensure_run_structure(experiment_id, revision_id, run_id, experiment_name, revision_name)
            logger.info(f"Created run directory: {run_dir}")

            # Validate and write YAML configuration
            yaml_text = ensure_yaml(yaml_text)
            yaml_path = f"{run_dir}/config.yaml"
            new_file(run_dir, "config.yaml", yaml_text)

            # Setup log directories and results directory
            # ML-Agents creates {results_dir}/{run_name}/ so we will pass run_dir as results_dir
            # and use "results" as run_name to get content in run_dir/results/
            tb_logdir = f"{run_dir}/results"  # This is where content will actually end up
            stdout_log = f"{run_dir}/stdout.log"
            # Note: results directory will be created by mlagents-learn when invoked with --run-id=results
            # Do not pre-create the directory here

        except Exception as e:
            logger.error(f"Failed to setup run directories for {run_id}: {e}")
            raise RunnerError(f"Failed to setup run directories: {e}") from e

        try:
            # Create run document (status: "created", not executed yet)
            run_doc = {
                "_id": run_id,
                "revision_id": str(revision_id),
                "experiment_id": str(experiment_id),
                "parent_revision_id": parent_revision_id or "",
                "parent_run_id": parent_run_id or "",
                "status": "created",  # Not executed yet
                "yaml_path": to_relative_path(yaml_path),
                "yaml_snapshot": yaml_text,  # Immutable snapshot
                "cli_flags": cli_flags,
                "cli_flags_snapshot": cli_flags.copy(),  # Immutable snapshot
                "resolved_env_path": to_relative_path(resolved_env_path),  # Store relative path
                "tb_logdir": to_relative_path(tb_logdir),
                "stdout_log_path": to_relative_path(stdout_log),
                "artifacts_dir": to_relative_path(run_dir),
                "description": description,
                "results_text": results_text,
                "enabled_plugins": enabled_plugins or [],
                "created_at": datetime.now(timezone.utc),
                "started_at": None,  # Will be set when executed
                "ended_at": None,
                "execution_count": 0,  # New field
                "last_restarted_at": None,  # New field
                "process_id": None,  # Will be set when executed
                "command": ""  # Will be set when executed
            }
            db.runs.insert_one(run_doc)
            logger.info(f"Run document created in database for {run_id}")

        except Exception as e:
            logger.error(f"Failed to create run document for {run_id}: {e}")
            raise RunnerError(f"Failed to create run document: {e}") from e

        return run_id

    except Exception as e:
        logger.error(f"Unexpected error in create_run: {e}")
        raise


def execute_run(run_id: str, restart_mode: str = None) -> bool:
    """Execute an existing run using its immutable configuration

    Args:
        run_id: ID of the run to execute
        restart_mode: Optional restart mode - 'resume' or 'force'
    """
    try:
        db = get_db()

        # Get run from database
        run_doc = db.runs.find_one({"_id": run_id})
        if not run_doc:
            raise RunnerError(f"Run {run_id} not found")

        # Check if run is already executing
        if run_id in RUN_PROCS:
            raise RunnerError(f"Run {run_id} is already executing")

        logger.info(f"Executing run {run_id}")

        # Get immutable configuration from run document
        yaml_text = run_doc.get("yaml_snapshot")
        cli_flags = run_doc.get("cli_flags_snapshot", {})
        experiment_id = run_doc.get("experiment_id")
        resolved_env_path = ensure_workspace_path(run_doc.get("resolved_env_path", ""))

        if not yaml_text or not experiment_id:
            raise RunnerError(f"Run {run_id} missing required configuration")

        if not resolved_env_path:
            raise RunnerError(f"Run {run_id} missing resolved environment path")

        # Get experiment data
        experiment = db.experiments.find_one({"_id": experiment_id})
        if not experiment:
            raise RunnerError(f"Experiment {experiment_id} not found")

        try:
            # Get paths from run document
            run_dir = ensure_workspace_path(run_doc.get("artifacts_dir", ""))
            yaml_path = ensure_workspace_path(run_doc.get("yaml_path", ""))
            stdout_log = ensure_workspace_path(run_doc.get("stdout_log_path", ""))

            # Setup results directory for ML-Agents
            results_base_dir = run_dir  # ML-Agents will create run_dir/{run_name}/

            # Clear/recreate stdout log for fresh execution
            with open(stdout_log, "w", encoding="utf-8"):
                pass  # Create empty file

            # Build mlagents-learn command using resolved environment path
            # Use "results" as run_name so ML-Agents creates content in results/ directory
            run_name = "results"
            time_scale = str(cli_flags.get("time_scale", 20))
            no_graphics = cli_flags.get("no_graphics", True)
            num_envs = int(cli_flags.get("num_envs", 1))  # Default to 1 environment

            # Extract additional CLI flags
            seed = int(cli_flags.get("seed", -1))
            torch_device = cli_flags.get("torch_device", "auto")
            width = int(cli_flags.get("width", 84))
            height = int(cli_flags.get("height", 84))
            quality_level = int(cli_flags.get("quality_level", 5))

            # Allocate ports for this run
            base_port = allocate_ports(run_id, num_envs)

            cmd = [
                "mlagents-learn", yaml_path,
                f"--run-id={run_name}",
                f"--env={resolved_env_path}",
                f"--time-scale={time_scale}",
                f"--base-port={base_port}",
                f"--num-envs={num_envs}",
            ]
            if no_graphics:
                cmd.append("--no-graphics")

            # Add results directory for ML-Agents output
            if results_base_dir:
                cmd.append(f"--results-dir={results_base_dir}")

            # Add additional CLI flags
            if seed != -1:
                cmd.append(f"--seed={seed}")

            # Map 'auto' to default behavior (don't specify flag)
            if torch_device and torch_device.lower() != "auto":
                cmd.append(f"--torch-device={torch_device}")

            cmd.append(f"--width={width}")
            cmd.append(f"--height={height}")
            cmd.append(f"--quality-level={quality_level}")

            # Add restart mode flags if specified
            if restart_mode == 'resume':
                cmd.append("--resume")
                logger.info(f"Adding --resume flag for run {run_id}")
            elif restart_mode == 'force':
                cmd.append("--force")
                logger.info(f"Adding --force flag for run {run_id}")

            logger.info(f"Constructed command: {' '.join(cmd)}")

        except Exception as e:
            logger.error(f"Failed to construct command for {run_id}: {e}")
            raise RunnerError(f"Failed to construct command: {e}") from e

        try:
            # Setup environment variables
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")

            # Write command header to log file first
            with open(stdout_log, "w", encoding="utf-8") as out:
                out.write(f"=== ML-Agents Training Run ===\n")
                out.write(f"Run ID: {run_id}\n")
                out.write(f"Command: {' '.join(cmd)}\n")
                out.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
                out.write(f"{'=' * 50}\n\n")

            # Launch subprocess with proper error handling (append mode to preserve header)
            with open(stdout_log, "a", buffering=1) as out:
                proc = subprocess.Popen(
                    cmd,
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd='.',
                    preexec_fn=os.setsid if os.name != 'nt' else None
                )

            # Store process reference and initial status
            RUN_PROCS[run_id] = proc
            RUN_STATUS[run_id] = "starting"
            logger.info(f"Process started for run {run_id} with PID {proc.pid}")

        except Exception as e:
            logger.error(f"Failed to start process for {run_id}: {e}")
            # Cleanup on failure
            RUN_PROCS.pop(run_id, None)
            RUN_STATUS.pop(run_id, None)
            deallocate_ports(run_id)  # Release allocated ports on failure
            raise ProcessError(f"Failed to start process: {e}") from e

        try:
            # Update run document with execution info
            execution_count = run_doc.get("execution_count", 0) + 1
            now = datetime.now(timezone.utc)

            update_data = {
                "status": "running",
                "started_at": now if execution_count == 1 else run_doc.get("started_at"),  # Keep first start time
                "last_restarted_at": now if execution_count > 1 else None,
                "ended_at": None,
                "execution_count": execution_count,
                "process_id": proc.pid,
                "command": ' '.join(cmd)
            }

            db.runs.update_one({"_id": run_id}, {"$set": update_data})
            logger.info(f"Run document updated for execution {run_id}")

        except Exception as e:
            logger.error(f"Failed to update run document for {run_id}: {e}")
            # Cleanup on database failure
            if run_id in RUN_PROCS:
                RUN_PROCS[run_id].terminate()
                RUN_PROCS.pop(run_id, None)
            RUN_STATUS.pop(run_id, None)
            deallocate_ports(run_id)  # Release allocated ports on database failure
            raise RunnerError(f"Failed to update run document: {e}") from e

        # Start monitoring thread
        def process_waiter():
            final_status = "error"
            return_code = None

            try:
                monitor_process_health(run_id, proc)
                # Get return code - process should already be finished from monitoring
                return_code = proc.returncode
                if return_code is None:
                    # Process still running somehow, wait briefly
                    try:
                        return_code = proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Process {run_id} still running after monitoring completed")
                        return_code = None

                final_status = RUN_STATUS.get(run_id, "unknown")

                if final_status == "unknown":
                    final_status = "succeeded" if return_code == 0 else "failed"

                logger.info(f"Run {run_id} process waiter completed with status: {final_status}, return_code: {return_code}")

            except Exception as e:
                logger.error(f"Error in process waiter for {run_id}: {e}")
                final_status = "error"
            finally:
                # Capture end time when process actually finishes
                ended_at = datetime.now(timezone.utc)

                try:
                    current_run_doc = db.runs.find_one({"_id": run_id})
                    current_db_status = current_run_doc.get("status") if current_run_doc else None

                    if current_db_status == "stopped":
                        final_status = "stopped"
                        logger.info(f"Preserving user-initiated stopped status for run {run_id}")

                    update_data = {
                        "status": final_status,
                        "ended_at": ended_at
                    }
                    if return_code is not None:
                        update_data["return_code"] = return_code

                    db.runs.update_one({"_id": run_id}, {"$set": update_data})
                    logger.info(f"Updated database for run {run_id} with final status: {final_status}")
                except Exception as db_error:
                    logger.error(f"Failed to update database for run {run_id}: {db_error}")

                try:
                    RUN_PROCS.pop(run_id, None)
                    RUN_STATUS.pop(run_id, None)
                    RUN_THREADS.pop(run_id, None)
                    deallocate_ports(run_id)  # Release allocated ports
                    logger.debug(f"Cleaned up process references for run {run_id}")
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up process references for {run_id}: {cleanup_error}")

        thread = threading.Thread(target=process_waiter, daemon=True)
        thread.start()
        RUN_THREADS[run_id] = thread

        # Auto-start enabled run-scoped plugins
        try:
            # Get plugins from both run document (run-specific) and experiment (experiment-wide)
            run_plugins = run_doc.get("enabled_plugins", [])
            experiment_plugins = [p for p in experiment.get("enabled_plugins", []) if p.get("scope") == "run"]

            # Combine both lists, prioritizing run-specific plugins
            all_plugins = run_plugins + experiment_plugins

            if all_plugins:
                from plugins import start_plugin
                logger.info(f"Starting {len(all_plugins)} run-scoped plugins for run {run_id}")

                for plugin_config in all_plugins:
                    try:
                        plugin_name = plugin_config.get("name")
                        plugin_settings = plugin_config.get("settings", {})

                        execution_id = start_plugin(
                            plugin_name=plugin_name,
                            target_id=run_id,
                            scope="run",
                            settings=plugin_settings
                        )
                        logger.info(f"Started plugin '{plugin_name}' for run {run_id} (execution_id: {execution_id})")
                    except Exception as plugin_error:
                        logger.error(f"Failed to start plugin '{plugin_config.get('name')}': {plugin_error}")
        except Exception as plugin_startup_error:
            logger.error(f"Error during plugin startup for run {run_id}: {plugin_startup_error}")

        return True

    except Exception as e:
        logger.error(f"Unexpected error in execute_run: {e}")
        raise


def restart_run(run_id: str, mode: str = None) -> bool:
    """Restart an existing run, cleaning execution artifacts but preserving immutable config

    Args:
        run_id: ID of the run to restart
        mode: Optional restart mode - 'resume' or 'force'
    """
    try:
        db = get_db()

        # Get run from database
        run_doc = db.runs.find_one({"_id": run_id})
        if not run_doc:
            raise RunnerError(f"Run {run_id} not found")

        # Stop run if it's currently executing
        if run_id in RUN_PROCS:
            logger.info(f"Stopping currently running process for restart {run_id}")
            pm_stop_run(run_id, deallocate_ports)
            # Wait a moment for cleanup
            import time
            time.sleep(1)

        logger.info(f"Restarting run {run_id} with mode={mode}")

        # Clean execution artifacts (skip if resuming)
        if mode != 'resume':
            try:
                stdout_log_path = ensure_workspace_path(run_doc.get("stdout_log_path", ""))
                tb_logdir = ensure_workspace_path(run_doc.get("tb_logdir", ""))

                # Record cleanup timestamp for stale metric detection
                cleanup_timestamp = datetime.now(timezone.utc)

                # Clear stdout log
                if os.path.exists(stdout_log_path):
                    with open(stdout_log_path, "w", encoding="utf-8"):
                        pass  # Create empty file

                # Clear results directory for fresh metrics
                if os.path.exists(tb_logdir):
                    shutil.rmtree(tb_logdir)
                    os.makedirs(tb_logdir, exist_ok=True)

                # Clear results_text and plugin_notes in database
                db.runs.update_one(
                    {"_id": run_id},
                    {"$set": {
                        "results_text": "",
                        "plugin_notes": [],
                        "last_cleanup_at": cleanup_timestamp
                    }}
                )

                # Delete all plugin execution records for this run
                result = db.plugin_executions.delete_many({"target_id": run_id})
                if result.deleted_count > 0:
                    logger.info(f"Deleted {result.deleted_count} plugin execution records for run {run_id}")

                logger.info(f"Cleaned execution artifacts for run {run_id}")

                # Wait briefly for TensorBoard to detect file changes
                import time
                time.sleep(1)

            except Exception as e:
                logger.warning(f"Error cleaning artifacts for run {run_id}: {e}")
                # Continue with restart even if cleanup fails
        else:
            logger.info(f"Skipping artifact cleanup for resume mode")

        # Execute the run with existing immutable configuration
        success = execute_run(run_id, restart_mode=mode)

        if success:
            logger.info(f"Successfully restarted run {run_id}")

        return success

    except Exception as e:
        logger.error(f"Unexpected error in restart_run: {e}")
        raise


def launch_run(
    experiment: dict,
    revision: dict,
    yaml_text: str,
    cli_flags: dict,
    description: str = "",
    results_text: str = "",
    parent_run_id: Optional[str] = None,
    parent_revision_id: Optional[str] = None,
    enabled_plugins: List[dict] = None
) -> str:
    """
    Launch a new ML-Agents training run (create and execute).

    Args:
        experiment: Experiment document
        revision: Revision document
        yaml_text: YAML configuration content
        cli_flags: CLI flags for mlagents-learn
        description: Run description
        results_text: Run results notes
        parent_run_id: Optional parent run ID
        parent_revision_id: Optional parent revision ID
        enabled_plugins: Optional list of enabled plugins for this run

    Returns:
        Created run ID

    Raises:
        RunnerError: If run creation or execution fails
    """
    try:
        # Create the run first
        run_id = create_run(
            experiment=experiment,
            revision=revision,
            yaml_text=yaml_text,
            cli_flags=cli_flags,
            description=description,
            results_text=results_text,
            parent_run_id=parent_run_id,
            parent_revision_id=parent_revision_id,
            enabled_plugins=enabled_plugins
        )

        # Then execute it
        execute_run(run_id)

        return run_id

    except Exception as e:
        logger.error(f"Unexpected error in launch_run: {e}")
        raise


def get_effective_run_status(run_id: str) -> str:
    """
    Get the true current status of a run - single source of truth.

    Args:
        run_id: ID of the run

    Returns:
        Status string: "created", "running", "succeeded", "failed", "stopped", "unknown"
    """
    # Check if run is in active processes (overrides DB status)
    if run_id in RUN_PROCS:
        return RUN_STATUS.get(run_id, "running")

    # Check DB for run status (includes created, completed, etc.)
    try:
        db = get_db()
        run_doc = db.runs.find_one({"_id": run_id})
        if run_doc:
            # Return actual DB status (created, succeeded, failed, stopped, etc.)
            return run_doc.get("status", "unknown")
    except Exception as e:
        logger.warning(f"Error checking DB status for run {run_id}: {e}")

    # Run doesn't exist in DB or error occurred
    return "unknown"


def get_run_status(run_id: str) -> Optional[str]:
    """Get current status of a run from memory"""
    return RUN_STATUS.get(run_id)


def get_active_runs() -> List[str]:
    """Get list of currently active run IDs"""
    return list(RUN_PROCS.keys())


def cleanup_all_runs() -> None:
    """Cleanup all running processes - used for graceful shutdown"""
    logger.info("Cleaning up all running processes...")
    for run_id in list(RUN_PROCS.keys()):
        pm_stop_run(run_id, deallocate_ports)
    logger.info("All processes cleaned up")


def _setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, _):
        logger.info(f"Received signal {signum}, cleaning up processes...")
        cleanup_all_runs()
        exit(0)

    if os.name != 'nt':  # Unix-like systems
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)


# Setup signal handlers when module is imported
_setup_signal_handlers()
