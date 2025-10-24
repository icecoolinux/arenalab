"""
Dependency checking utilities for delete operations.

This module checks for dependencies before deleting items and returns warnings
about conflicts that will be resolved by the deletion.
"""
from typing import Dict, List, Any
from db import experiments, revisions, runs, environments


class DependencyWarning:
    """Represents a warning about dependencies that will be affected."""

    def __init__(self, warning_type: str, message: str, affected_items: List[Dict[str, Any]]):
        self.warning_type = warning_type
        self.message = message
        self.affected_items = affected_items

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.warning_type,
            "message": self.message,
            "affected_items": self.affected_items,
            "count": len(self.affected_items)
        }


def check_environment_dependencies(environment_id: str) -> List[DependencyWarning]:
    """
    Check if an environment is being used by any revisions.

    Args:
        environment_id: The environment ID to check

    Returns:
        List of dependency warnings
    """
    warnings = []

    # Check for revisions using this environment
    dependent_revisions = revisions.find_many({"environment_id": environment_id})

    if dependent_revisions:
        revision_info = [
            {
                "id": rev["_id"],
                "name": rev.get("name", "Unnamed"),
                "experiment_id": rev.get("experiment_id")
            }
            for rev in dependent_revisions
        ]

        warnings.append(DependencyWarning(
            warning_type="revisions_using_environment",
            message=f"{len(dependent_revisions)} revision(s) are using this environment. "
                    "Deleting this environment may break these revisions.",
            affected_items=revision_info
        ))

    return warnings


def check_revision_dependencies(revision_id: str) -> List[DependencyWarning]:
    """
    Check if a revision is a parent to other revisions or runs.

    Args:
        revision_id: The revision ID to check

    Returns:
        List of dependency warnings
    """
    warnings = []

    # Check for child revisions
    child_revisions = revisions.find_many({"parent_revision_id": revision_id})

    if child_revisions:
        revision_info = [
            {
                "id": rev["_id"],
                "name": rev.get("name", "Unnamed"),
                "experiment_id": rev.get("experiment_id")
            }
            for rev in child_revisions
        ]

        warnings.append(DependencyWarning(
            warning_type="child_revisions",
            message=f"{len(child_revisions)} revision(s) are based on this revision. "
                    "Deleting this revision will orphan child revisions.",
            affected_items=revision_info
        ))

    # Check for child runs
    child_runs = runs.find_many({"parent_revision_id": revision_id})

    if child_runs:
        run_info = [
            {
                "id": run["_id"],
                "name": run.get("name", "Unnamed"),
                "status": run.get("status", "unknown")
            }
            for run in child_runs
        ]

        warnings.append(DependencyWarning(
            warning_type="runs_from_revision",
            message=f"{len(child_runs)} run(s) belong to this revision. "
                    "These runs will also be moved to trash.",
            affected_items=run_info
        ))

    return warnings


def check_run_dependencies(run_id: str) -> List[DependencyWarning]:
    """
    Check if a run is a parent to other revisions or runs.

    Args:
        run_id: The run ID to check

    Returns:
        List of dependency warnings
    """
    warnings = []

    # Check for revisions based on this run
    dependent_revisions = revisions.find_many({"parent_run_id": run_id})

    if dependent_revisions:
        revision_info = [
            {
                "id": rev["_id"],
                "name": rev.get("name", "Unnamed"),
                "experiment_id": rev.get("experiment_id")
            }
            for rev in dependent_revisions
        ]

        warnings.append(DependencyWarning(
            warning_type="revisions_based_on_run",
            message=f"{len(dependent_revisions)} revision(s) are based on this run. "
                    "Deleting this run will orphan these revisions.",
            affected_items=revision_info
        ))

    # Check for child runs
    child_runs = runs.find_many({"parent_run_id": run_id})

    if child_runs:
        run_info = [
            {
                "id": run["_id"],
                "name": run.get("name", "Unnamed"),
                "status": run.get("status", "unknown")
            }
            for run in child_runs
        ]

        warnings.append(DependencyWarning(
            warning_type="child_runs",
            message=f"{len(child_runs)} run(s) are based on this run. "
                    "Deleting this run will orphan child runs.",
            affected_items=run_info
        ))

    return warnings


def check_experiment_dependencies(experiment_id: str) -> List[DependencyWarning]:
    """
    Check dependencies for an experiment.

    Args:
        experiment_id: The experiment ID to check

    Returns:
        List of dependency warnings
    """
    warnings = []

    # Check for revisions
    experiment_revisions = revisions.find_many({"experiment_id": experiment_id})

    if experiment_revisions:
        revision_info = [
            {
                "id": rev["_id"],
                "name": rev.get("name", "Unnamed")
            }
            for rev in experiment_revisions
        ]

        warnings.append(DependencyWarning(
            warning_type="experiment_revisions",
            message=f"{len(experiment_revisions)} revision(s) belong to this experiment. "
                    "These revisions and their runs will also be moved to trash.",
            affected_items=revision_info
        ))

    # Check for runs
    experiment_runs = runs.find_many({"experiment_id": experiment_id})

    if experiment_runs:
        run_info = [
            {
                "id": run["_id"],
                "name": run.get("name", "Unnamed"),
                "status": run.get("status", "unknown")
            }
            for run in experiment_runs
        ]

        warnings.append(DependencyWarning(
            warning_type="experiment_runs",
            message=f"{len(experiment_runs)} run(s) belong to this experiment. "
                    "These runs will also be moved to trash.",
            affected_items=run_info
        ))

    return warnings


def format_warnings_response(warnings: List[DependencyWarning]) -> Dict[str, Any]:
    """
    Format warnings into a response structure.

    Args:
        warnings: List of dependency warnings

    Returns:
        Dictionary with warnings information
    """
    return {
        "has_warnings": len(warnings) > 0,
        "warning_count": len(warnings),
        "warnings": [w.to_dict() for w in warnings]
    }
