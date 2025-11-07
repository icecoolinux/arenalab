"""
Process management for ML-Agents training runs.

Handles subprocess lifecycle, termination, and log streaming.
"""
import os
import time
import signal
import logging
import subprocess
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from config import (
    PROCESS_GRACEFUL_SHUTDOWN_TIMEOUT,
    PROCESS_FORCE_KILL_TIMEOUT,
    HEALTH_CHECK_INTERVAL_STARTUP,
    HEALTH_CHECK_INTERVAL_RUNNING,
    HEALTH_CHECK_STARTUP_DURATION
)
from db import get_db

logger = logging.getLogger(__name__)

# Global process state
RUN_PROCS: Dict[str, subprocess.Popen] = {}
RUN_STATUS: Dict[str, str] = {}
RUN_THREADS: Dict[str, threading.Thread] = {}


def monitor_process_health(run_id: str, proc: subprocess.Popen) -> None:
    """Monitor process health and update status with improved error handling"""
    try:
        # Initial status
        RUN_STATUS[run_id] = "starting"
        logger.info(f"Starting health monitoring for process {run_id} (PID: {proc.pid})")

        # Monitor with more frequent checks initially
        startup_checks = 0
        max_startup_checks = HEALTH_CHECK_STARTUP_DURATION // HEALTH_CHECK_INTERVAL_STARTUP

        while proc.poll() is None:
            # More frequent checks during startup
            if startup_checks < max_startup_checks:
                time.sleep(HEALTH_CHECK_INTERVAL_STARTUP)
                startup_checks += 1
                # Check again after sleep before updating status
                if proc.poll() is None:
                    RUN_STATUS[run_id] = "starting"
            else:
                time.sleep(HEALTH_CHECK_INTERVAL_RUNNING)
                # Check again after sleep before updating status
                if proc.poll() is None:
                    RUN_STATUS[run_id] = "running"

            # Verify process is still accessible
            try:
                proc.poll()  # This will update returncode if process died
            except Exception as e:
                logger.warning(f"Error polling process {run_id}: {e}")
                break

        # Process has finished or died
        return_code = proc.returncode

        # Check if this was a user-initiated stop before setting final status
        db = get_db()
        current_db_status = None
        try:
            run_doc = db.runs.find_one({"_id": run_id})
            if run_doc:
                current_db_status = run_doc.get("status")
        except Exception as e:
            logger.warning(f"Error checking DB status for {run_id}: {e}")

        # If DB already shows "stopped", preserve that status (user-initiated)
        if current_db_status == "stopped":
            status = "stopped"
            logger.info(f"Process {run_id} preserving user-initiated stopped status")
        else:
            # Determine final status based on return code and timing
            if return_code is None:
                status = "error"  # Process died unexpectedly
                logger.error(f"Process {run_id} died without return code")
            elif return_code == 0:
                status = "succeeded"
                logger.info(f"Process {run_id} completed successfully")
            elif return_code < 0:
                status = "killed"  # Process was killed by signal
                logger.warning(f"Process {run_id} was killed by signal {-return_code}")
            else:
                status = "failed"  # Process failed with error code
                logger.error(f"Process {run_id} failed with return code {return_code}")

        RUN_STATUS[run_id] = status
        logger.info(f"Process {run_id} monitoring completed with status: {status}")

        # Immediately update database with failure status to avoid showing stale "starting"/"running" status
        if status in ["failed", "error", "killed"]:
            try:
                db.runs.update_one(
                    {"_id": run_id},
                    {"$set": {"status": status, "ended_at": datetime.now(timezone.utc), "return_code": return_code}}
                )
                logger.info(f"Immediately updated database for failed run {run_id} with status: {status}")
            except Exception as db_error:
                logger.error(f"Failed to immediately update database for {run_id}: {db_error}")

    except Exception as e:
        logger.error(f"Critical error monitoring process {run_id}: {e}")
        RUN_STATUS[run_id] = "error"
    finally:
        # Ensure cleanup happens even if monitoring fails
        logger.debug(f"Health monitoring cleanup for {run_id}")


def get_run_logs(run_id: str, max_lines: int, run_dir_getter) -> List[str]:
    """Get recent log lines for a specific run"""
    try:
        run_dir = run_dir_getter(run_id)
        stdout_log = f"{run_dir}/stdout.log"
        from utils.file_tools import LogStreamer
        streamer = LogStreamer(stdout_log)
        return streamer.tail_lines(max_lines)
    except Exception as e:
        logger.error(f"Error reading logs for run {run_id}: {e}")
        return []


def stop_run(run_id: str, port_deallocator) -> bool:
    """Stop a running process gracefully with enhanced error handling and cleanup"""
    try:
        proc = RUN_PROCS.get(run_id)
        if not proc:
            logger.warning(f"No active process found for run {run_id}")
            # Check if it appears to be running according to centralized status
            try:
                # Import here to avoid circular dependency
                from .run_lifecycle import get_effective_run_status
                current_status = get_effective_run_status(run_id)
                if current_status in ["running", "pending"]:
                    # This is an orphaned run - update database to reflect that process is no longer active
                    db = get_db()
                    db.runs.update_one(
                        {"_id": run_id},
                        {"$set": {"status": "stopped", "ended_at": datetime.now(timezone.utc)}}
                    )
                    logger.info(f"Updated orphaned run {run_id} status to stopped")
                    return True
            except Exception as db_e:
                logger.error(f"Error checking status for run {run_id}: {db_e}")
            return False

        logger.info(f"Stopping run {run_id} (PID: {proc.pid})")

        # Verify process is still alive before attempting to stop it
        try:
            if proc.poll() is not None:
                logger.info(f"Process {run_id} already terminated with code {proc.returncode}")
                # Process already dead, just cleanup
                RUN_PROCS.pop(run_id, None)
                RUN_STATUS.pop(run_id, None)
                return True
        except Exception as e:
            logger.warning(f"Error checking process status for {run_id}: {e}")

        # Attempt graceful termination
        termination_successful = False
        try:
            if os.name != 'nt':
                # Unix-like systems: Kill entire process group
                try:
                    pgid = os.getpgid(proc.pid)
                    logger.info(f"Terminating process group {pgid} for run {run_id}")
                    os.killpg(pgid, signal.SIGTERM)  # Send SIGTERM to entire process group
                    logger.debug(f"Sent SIGTERM to process group {pgid}")
                except (OSError, ProcessLookupError) as e:
                    logger.warning(f"Could not get process group for {run_id}: {e}, falling back to process termination")
                    proc.terminate()
            else:
                # Windows: Fall back to process termination
                proc.terminate()
                logger.debug(f"Sent SIGTERM to process {run_id}")

            # Wait for graceful shutdown with timeout
            try:
                proc.wait(timeout=PROCESS_GRACEFUL_SHUTDOWN_TIMEOUT)
                logger.info(f"Process {run_id} terminated gracefully")
                termination_successful = True
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't respond to SIGTERM
                logger.warning(f"Process {run_id} did not respond to SIGTERM, sending SIGKILL")
                try:
                    if os.name != 'nt':
                        # Unix-like: Force kill entire process group
                        try:
                            pgid = os.getpgid(proc.pid)
                            logger.info(f"Force killing process group {pgid} for run {run_id}")
                            os.killpg(pgid, signal.SIGKILL)  # Send SIGKILL to entire process group
                        except (OSError, ProcessLookupError):
                            proc.kill()  # Fallback to process kill
                    else:
                        proc.kill()  # Windows: Force kill process

                    proc.wait(timeout=PROCESS_FORCE_KILL_TIMEOUT)
                    logger.info(f"Process {run_id} force killed")
                    termination_successful = True
                except Exception as kill_e:
                    logger.error(f"Error force killing process {run_id}: {kill_e}")
                    termination_successful = False
        except Exception as term_e:
            logger.error(f"Error terminating process {run_id}: {term_e}")
            termination_successful = False

        # Update database regardless of termination success
        try:
            db = get_db()
            update_data = {
                "status": "stopped" if termination_successful else "error",
                "ended_at": datetime.now(timezone.utc)
            }
            db.runs.update_one({"_id": run_id}, {"$set": update_data})
            logger.info(f"Updated database for run {run_id} with status: {update_data['status']}")
        except Exception as db_e:
            logger.error(f"Failed to update database for stopped run {run_id}: {db_e}")

        # Always attempt cleanup of process references
        try:
            RUN_PROCS.pop(run_id, None)
            RUN_STATUS.pop(run_id, None)

            # Handle monitoring thread cleanup
            thread = RUN_THREADS.pop(run_id, None)
            if thread and thread.is_alive():
                logger.debug(f"Monitoring thread for {run_id} will cleanup automatically")

            port_deallocator(run_id)  # Release allocated ports
            logger.debug(f"Cleaned up process references for run {run_id}")
        except Exception as cleanup_e:
            logger.error(f"Error during cleanup for run {run_id}: {cleanup_e}")

        return termination_successful

    except Exception as e:
        logger.error(f"Unexpected error stopping run {run_id}: {e}")
        # Attempt emergency cleanup
        try:
            RUN_PROCS.pop(run_id, None)
            RUN_STATUS.pop(run_id, None)
            RUN_THREADS.pop(run_id, None)
            port_deallocator(run_id)  # Release allocated ports in emergency cleanup
        except:
            pass  # Ignore cleanup errors in emergency case
        return False


def force_kill_run(run_id: str, port_deallocator) -> bool:
    """
    Force kill a run immediately without graceful shutdown.
    Use this for stuck processes that won't respond to normal stop.
    """
    try:
        proc = RUN_PROCS.get(run_id)
        if not proc:
            logger.warning(f"Cannot force kill {run_id}: process not found")
            return False

        logger.warning(f"Force killing run {run_id} (PID: {proc.pid})")

        # Force kill entire process group
        try:
            if os.name != 'nt':
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
                logger.info(f"Sent SIGKILL to process group {pgid}")
            else:
                proc.kill()
                logger.info(f"Sent kill signal to process {proc.pid}")
        except (OSError, ProcessLookupError) as e:
            logger.warning(f"Process {run_id} may already be dead: {e}")

        # Update database
        try:
            db = get_db()
            db.runs.update_one(
                {"_id": run_id},
                {"$set": {
                    "status": "killed",
                    "ended_at": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"Updated database for force-killed run {run_id}")
        except Exception as db_error:
            logger.error(f"Failed to update database for {run_id}: {db_error}")

        # Cleanup
        RUN_PROCS.pop(run_id, None)
        RUN_STATUS.pop(run_id, None)
        RUN_THREADS.pop(run_id, None)
        port_deallocator(run_id)

        return True

    except Exception as e:
        logger.error(f"Error force killing run {run_id}: {e}")
        return False


def get_run_status(run_id: str) -> Optional[str]:
    """Get current status of a run"""
    return RUN_STATUS.get(run_id)


def get_active_runs() -> List[str]:
    """Get list of currently active run IDs"""
    return list(RUN_PROCS.keys())
