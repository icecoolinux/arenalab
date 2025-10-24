"""
Trash management utilities for soft-delete operations.

This module provides functionality to move items to a trash directory instead of
permanently deleting them, allowing for potential recovery.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from utils.file_tools import ensure_workspace_path


def get_trash_dir() -> Path:
    """
    Get the trash directory path, creating it if it doesn't exist.

    Returns:
        Path object pointing to WORKSPACE/trash
    """
    trash_dir = Path(ensure_workspace_path("trash"))
    trash_dir.mkdir(parents=True, exist_ok=True)
    return trash_dir


def move_to_trash(
    path: str,
    item_type: str,
    item_id: str,
    item_name: Optional[str] = None
) -> Optional[str]:
    """
    Move a file or directory to the trash folder with timestamp.

    Args:
        path: Absolute or workspace-relative path to move
        item_type: Type of item (experiment, revision, run, environment)
        item_id: Unique identifier of the item
        item_name: Optional human-readable name for the item

    Returns:
        The trash path where the item was moved, or None if source didn't exist
    """
    # Ensure we have absolute path
    abs_path = ensure_workspace_path(path)
    source = Path(abs_path)

    # Skip if source doesn't exist
    if not source.exists():
        return None

    # Create trash directory structure: trash/{type}/{timestamp}_{id}_{name}/
    trash_dir = get_trash_dir()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Sanitize name for filesystem
    safe_name = ""
    if item_name:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in item_name)
        safe_name = f"_{safe_name[:50]}"  # Limit length

    trash_item_dir = trash_dir / item_type / f"{timestamp}_{item_id}{safe_name}"
    trash_item_dir.mkdir(parents=True, exist_ok=True)

    # Move to trash preserving original name
    dest = trash_item_dir / source.name

    try:
        shutil.move(str(source), str(dest))
        return str(dest)
    except Exception as e:
        # Log error but don't fail the operation
        print(f"Warning: Failed to move {source} to trash: {e}")
        return None


def move_experiment_to_trash(experiment_id: str, experiment_name: str) -> list[str]:
    """
    Move an experiment's directory to trash.

    Args:
        experiment_id: The experiment ID
        experiment_name: The experiment name

    Returns:
        List of paths that were moved to trash
    """
    moved = []

    # Sanitize name to match actual directory creation
    from utils.file_tools import sanitize_name
    safe_name = sanitize_name(experiment_name)

    # Move the experiment directory (format: {name}_{id})
    exp_path = f"experiments/{safe_name}_{experiment_id}"
    trash_path = move_to_trash(exp_path, "experiments", experiment_id, experiment_name)
    if trash_path:
        moved.append(trash_path)

    return moved


def move_revision_to_trash(
    experiment_id: str,
    revision_id: str,
    experiment_name: str,
    revision_name: str
) -> list[str]:
    """
    Move a revision's directory to trash.

    Args:
        experiment_id: The parent experiment ID
        revision_id: The revision ID
        experiment_name: The experiment name
        revision_name: The revision name

    Returns:
        List of paths that were moved to trash
    """
    moved = []

    # Sanitize names to match actual directory creation
    from utils.file_tools import sanitize_name
    safe_exp_name = sanitize_name(experiment_name)
    safe_rev_name = sanitize_name(revision_name)

    # Move the revision directory (format: experiments/{exp_name}_{exp_id}/revisions/{rev_name}_{rev_id})
    rev_path = f"experiments/{safe_exp_name}_{experiment_id}/revisions/{safe_rev_name}_{revision_id}"
    trash_path = move_to_trash(rev_path, "revisions", revision_id, revision_name)
    if trash_path:
        moved.append(trash_path)

    return moved


def move_run_to_trash(
    experiment_id: str,
    revision_id: str,
    run_id: str,
    experiment_name: str,
    revision_name: str,
    run_name: str
) -> list[str]:
    """
    Move a run's directory to trash.

    Args:
        experiment_id: The parent experiment ID
        revision_id: The parent revision ID
        run_id: The run ID
        experiment_name: The experiment name
        revision_name: The revision name
        run_name: The run name

    Returns:
        List of paths that were moved to trash
    """
    moved = []

    # Sanitize names to match actual directory creation
    from utils.file_tools import sanitize_name
    safe_exp_name = sanitize_name(experiment_name)
    safe_rev_name = sanitize_name(revision_name)

    # Move the run directory (format: experiments/{exp_name}_{exp_id}/revisions/{rev_name}_{rev_id}/runs/{run_id})
    # NOTE: Runs are created with just the ID, no name appended
    run_path = f"experiments/{safe_exp_name}_{experiment_id}/revisions/{safe_rev_name}_{revision_id}/runs/{run_id}"
    trash_path = move_to_trash(run_path, "runs", run_id, run_name)
    if trash_path:
        moved.append(trash_path)

    return moved


def move_environment_to_trash(
    environment_id: str,
    environment_name: str,
    version: int
) -> list[str]:
    """
    Move an environment's directory to trash.

    Args:
        environment_id: The environment ID
        environment_name: The environment name
        version: The environment version number

    Returns:
        List of paths that were moved to trash
    """
    moved = []

    # Move the environment directory: envs/{name}_v{version}_{id}/
    env_path = f"envs/{environment_name}_v{version}_{environment_id}"
    trash_path = move_to_trash(env_path, "environments", environment_id, environment_name)
    if trash_path:
        moved.append(trash_path)

    return moved


def empty_trash(item_type: Optional[str] = None, older_than_days: Optional[int] = None) -> int:
    """
    Empty the trash directory.

    Args:
        item_type: Optional type filter (experiment, revision, run, environment)
        older_than_days: Optional age filter - only delete items older than N days

    Returns:
        Number of items deleted
    """
    trash_dir = get_trash_dir()
    deleted_count = 0

    # Determine which directories to scan
    if item_type:
        type_dirs = [trash_dir / item_type]
    else:
        type_dirs = [d for d in trash_dir.iterdir() if d.is_dir()]

    for type_dir in type_dirs:
        if not type_dir.exists():
            continue

        for item_dir in type_dir.iterdir():
            if not item_dir.is_dir():
                continue

            # Check age if specified
            if older_than_days is not None:
                try:
                    # Extract timestamp from directory name (format: YYYYMMDD_HHMMSS_...)
                    timestamp_str = "_".join(item_dir.name.split("_")[:2])
                    item_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    age_days = (datetime.utcnow() - item_time).days

                    if age_days < older_than_days:
                        continue
                except:
                    # Skip items we can't parse
                    continue

            # Delete the item
            try:
                shutil.rmtree(item_dir)
                deleted_count += 1
            except Exception as e:
                print(f"Warning: Failed to delete trash item {item_dir}: {e}")

    return deleted_count
