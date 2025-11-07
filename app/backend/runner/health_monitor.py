"""
Health monitoring for ML-Agents training processes.

Provides health checks and stale run detection for active training processes.
"""
import os
import time
import logging
from typing import Dict, List, Any
from datetime import datetime, timezone
from config import HEALTH_CHECK_RUNTIME_THRESHOLD, HEALTH_CHECK_STUCK_THRESHOLD
from db import get_db

logger = logging.getLogger(__name__)


def check_process_health(run_id: str, run_procs: Dict = None, run_dir_getter=None) -> dict:
    """
    Check if a process appears to be stuck or unhealthy.
    Returns health status information.

    Args:
        run_id: Run identifier
        run_procs: Dictionary of active processes
        run_dir_getter: Function to get run directory path
    """
    try:
        # Import process state if not provided
        if run_procs is None:
            from .process_manager import RUN_PROCS
            run_procs = RUN_PROCS
        if run_dir_getter is None:
            from .run_lifecycle import _get_run_directory
            run_dir_getter = _get_run_directory

        proc = run_procs.get(run_id)
        if not proc:
            return {
                "healthy": False,
                "reason": "Process not found in active runs",
                "stuck": False
            }

        # Check if process is still running
        if proc.poll() is not None:
            return {
                "healthy": False,
                "reason": f"Process exited with code {proc.returncode}",
                "stuck": False
            }

        # Check log file activity
        try:
            run_dir = run_dir_getter(run_id)
            stdout_log = f"{run_dir}/stdout.log"

            if not os.path.exists(stdout_log):
                return {
                    "healthy": True,
                    "reason": "Log file not yet created (early startup)",
                    "stuck": False
                }

            # Check when log was last modified
            log_mtime = os.path.getmtime(stdout_log)
            current_time = time.time()
            seconds_since_update = current_time - log_mtime

            # Get run start time from database
            db = get_db()
            run_doc = db.runs.find_one({"_id": run_id})
            if not run_doc:
                return {
                    "healthy": False,
                    "reason": "Run not found in database",
                    "stuck": False
                }

            started_at = run_doc.get("started_at")
            if started_at:
                # Ensure timezone-aware comparison (MongoDB returns naive UTC datetimes)
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                runtime_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            else:
                runtime_seconds = 0

            # Consider stuck if:
            # - Process has been running > threshold (past startup)
            # - No log activity for > threshold
            is_stuck = runtime_seconds > HEALTH_CHECK_RUNTIME_THRESHOLD and seconds_since_update > HEALTH_CHECK_STUCK_THRESHOLD

            return {
                "healthy": not is_stuck,
                "reason": f"No log activity for {int(seconds_since_update)} seconds" if is_stuck else "Process appears healthy",
                "stuck": is_stuck,
                "pid": proc.pid,
                "runtime_seconds": int(runtime_seconds),
                "seconds_since_log_update": int(seconds_since_update),
                "log_size_bytes": os.path.getsize(stdout_log)
            }

        except Exception as e:
            logger.error(f"Error checking process health for {run_id}: {e}")
            return {
                "healthy": False,
                "reason": f"Error checking health: {str(e)}",
                "stuck": False
            }

    except Exception as e:
        logger.error(f"Unexpected error in check_process_health for {run_id}: {e}")
        return {
            "healthy": False,
            "reason": f"Unexpected error: {str(e)}",
            "stuck": False
        }


def get_stale_runs(run_procs: Dict, health_checker) -> List[dict]:
    """
    Get list of all active runs that appear to be stuck/stale.

    Args:
        run_procs: Dictionary of active processes
        health_checker: Function to check process health
    """
    stale_runs = []
    for run_id in list(run_procs.keys()):
        health = health_checker(run_id)
        if health.get("stuck"):
            stale_runs.append({
                "run_id": run_id,
                "health": health
            })
    return stale_runs
