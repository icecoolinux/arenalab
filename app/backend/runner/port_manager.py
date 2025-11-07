"""
Port allocation manager for ML-Agents environments.

Manages dynamic port allocation to avoid conflicts between concurrent training runs.
"""
import threading
import logging
from typing import Dict, Tuple
from config import PORT_BASE, PORT_SPACING

logger = logging.getLogger(__name__)

# Port allocation state
RUN_PORTS: Dict[str, Tuple[int, int]] = {}  # Maps run_id to (base_port, num_envs)
PORT_LOCK = threading.Lock()  # Lock for thread-safe port allocation


def allocate_ports(run_id: str, num_envs: int) -> int:
    """
    Allocate a port range for a run.

    Args:
        run_id: Run identifier
        num_envs: Number of environments (determines port range size)

    Returns:
        base_port: Starting port for this run

    Raises:
        RuntimeError: If unable to allocate ports
    """
    with PORT_LOCK:
        # Find all currently allocated port ranges
        allocated_ranges = []
        for other_run_id, (base, envs) in RUN_PORTS.items():
            if other_run_id != run_id:
                # Each run uses ports [base, base + envs - 1], add spacing
                allocated_ranges.append((base, base + envs + PORT_SPACING - 1))

        # Sort ranges by start port
        allocated_ranges.sort()

        # Find first available port range
        candidate_port = PORT_BASE
        for start, end in allocated_ranges:
            if candidate_port + num_envs + PORT_SPACING <= start:
                # Found a gap before this range
                break
            # Try after this range
            candidate_port = end + 1

        # Allocate the port range
        RUN_PORTS[run_id] = (candidate_port, num_envs)
        logger.info(f"Allocated ports {candidate_port}-{candidate_port + num_envs - 1} for run {run_id} ({num_envs} envs)")

        return candidate_port


def deallocate_ports(run_id: str) -> None:
    """
    Deallocate ports for a completed run.

    Args:
        run_id: Run identifier
    """
    with PORT_LOCK:
        if run_id in RUN_PORTS:
            base_port, num_envs = RUN_PORTS.pop(run_id)
            logger.info(f"Deallocated ports {base_port}-{base_port + num_envs - 1} for run {run_id}")


def get_allocated_ports(run_id: str) -> Tuple[int, int]:
    """
    Get allocated ports for a run.

    Args:
        run_id: Run identifier

    Returns:
        Tuple of (base_port, num_envs) or (0, 0) if not allocated
    """
    with PORT_LOCK:
        return RUN_PORTS.get(run_id, (0, 0))
