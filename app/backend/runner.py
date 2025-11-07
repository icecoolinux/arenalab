"""
Backward compatibility module - re-exports from runner package.

This module maintains backward compatibility with code that imports from `runner` directly.
The actual implementation has been split into focused modules under the `runner/` package:
- runner/run_lifecycle.py - Run creation, execution, restart logic
- runner/process_manager.py - Process control and log streaming
- runner/port_manager.py - Port allocation for ML-Agents
- runner/health_monitor.py - Health checks and stale run detection
"""
from runner import (
    # Run lifecycle
    create_run,
    execute_run,
    launch_run,
    restart_run,
    get_run_status,
    get_effective_run_status,
    get_active_runs,
    cleanup_all_runs,
    # Process management
    stop_run,
    force_kill_run,
    get_run_logs,
    # Health monitoring
    check_process_health,
    get_stale_runs,
)

__all__ = [
    "create_run",
    "execute_run",
    "launch_run",
    "restart_run",
    "get_run_status",
    "get_effective_run_status",
    "get_active_runs",
    "cleanup_all_runs",
    "stop_run",
    "force_kill_run",
    "get_run_logs",
    "check_process_health",
    "get_stale_runs",
]
