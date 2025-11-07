"""
Runner module for ML-Agents process management.

This module provides process orchestration, port management, health monitoring,
and run lifecycle management for ML-Agents training runs.
"""
from .run_lifecycle import (
    create_run,
    execute_run,
    launch_run,
    restart_run,
    get_run_status,
    get_effective_run_status,
    get_active_runs,
    cleanup_all_runs
)
from .port_manager import deallocate_ports
from .process_manager import RUN_PROCS

# Wrapper functions for backward compatibility
def stop_run(run_id: str) -> bool:
    """Stop a running process"""
    from .process_manager import stop_run as pm_stop_run
    return pm_stop_run(run_id, deallocate_ports)


def force_kill_run(run_id: str) -> bool:
    """Force kill a stuck process"""
    from .process_manager import force_kill_run as pm_force_kill
    return pm_force_kill(run_id, deallocate_ports)


def get_run_logs(run_id: str, max_lines: int = 20000) -> list:
    """Get log lines for a run"""
    from .process_manager import get_run_logs as pm_get_logs
    from .run_lifecycle import _get_run_directory
    return pm_get_logs(run_id, max_lines, _get_run_directory)


def check_process_health(run_id: str) -> dict:
    """Check process health"""
    from .health_monitor import check_process_health as hm_check
    return hm_check(run_id)


def get_stale_runs() -> list:
    """Get list of stale runs"""
    from .health_monitor import get_stale_runs as hm_get_stale
    return hm_get_stale(RUN_PROCS, check_process_health)


__all__ = [
    # Run lifecycle
    "create_run",
    "execute_run",
    "launch_run",
    "restart_run",
    "get_run_status",
    "get_effective_run_status",
    "get_active_runs",
    "cleanup_all_runs",
    # Process management
    "stop_run",
    "force_kill_run",
    "get_run_logs",
    # Health monitoring
    "check_process_health",
    "get_stale_runs",
]
