"""
RevisionsService - Business logic for revision management.

Handles revision CRUD operations, YAML management, and related business rules.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from db import revisions, runs, experiments
from models import RevisionBody
from utils.file_tools import paths, new_file, ensure_revision_structure, get_revision_path
from utils.dependency_checks import check_revision_dependencies, format_warnings_response
from utils.trash import move_revision_to_trash
import logging

logger = logging.getLogger(__name__)


class RevisionError(Exception):
    """Custom exception for revision-related errors."""
    def __init__(self, message: str, status_code: int = 400, detail: Dict[str, Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {"message": message}


class RevisionsService:
    """Service for managing revisions and their business logic."""

    def __init__(self):
        self.revisions_db = revisions
        self.runs_db = runs
        self.experiments_db = experiments

    def list_revisions(self, experiment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all revisions, optionally filtered by experiment.

        Args:
            experiment_id: Optional experiment ID to filter by

        Returns:
            List of revision documents sorted by created_at descending
        """
        if experiment_id:
            revs = self.revisions_db.find_many({"experiment_id": experiment_id})
        else:
            revs = self.revisions_db.find_many()
        # Sort by created_at descending
        revs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
        return revs

    def get_revision(self, revision_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single revision by ID.

        Args:
            revision_id: The revision ID to retrieve

        Returns:
            Revision document or None if not found
        """
        return self.revisions_db.find_one({"_id": revision_id})

    def create_revision(self, revision_data: RevisionBody) -> Dict[str, Any]:
        """
        Create a new revision with YAML configuration and directory structure.

        Args:
            revision_data: Validated revision data from request body

        Returns:
            Created revision document

        Raises:
            RevisionError: If revision creation fails
        """
        try:
            yaml_content = revision_data.yaml

            # Get experiment name for directory structure
            experiment = self.experiments_db.find_one({"_id": revision_data.experiment_id})
            if not experiment:
                raise RevisionError(f"Experiment {revision_data.experiment_id} not found", status_code=404)

            experiment_name = experiment.get("name", "unknown")

            # Create revision using the collection method (without yaml_path initially)
            rev_id = self.revisions_db.create_revision(
                experiment_id=revision_data.experiment_id,
                name=revision_data.name,
                description=revision_data.description,
                parent_revision_id=revision_data.parent_revision_id,
                parent_run_id=revision_data.parent_run_id,
                yaml_path="",  # Will be updated after directory structure is created
                environment_id=revision_data.environment_id,
                cli_flags=revision_data.cli_flags
            )

            # Create the revision directory structure with names
            ensure_revision_structure(revision_data.experiment_id, rev_id, experiment_name, revision_data.name)

            # Get the directory from the relative path with names
            revision_path = get_revision_path(revision_data.experiment_id, rev_id, experiment_name, revision_data.name)
            new_file(revision_path, "config.yaml", yaml_content)

            # Update the revision with the correct yaml_path (store relative path)
            self.revisions_db.update_one({"_id": rev_id}, {"yaml_path": revision_path + '/config.yaml'})

            # Get the created revision with updated path
            created_rev = self.revisions_db.find_one({"_id": rev_id})

            return created_rev

        except RevisionError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in create_revision: {e}")
            raise RevisionError(f"Failed to create revision: {str(e)}") from e

    def update_results(self, revision_id: str, results_text: str) -> Dict[str, Any]:
        """
        Update the results text for a revision.

        Args:
            revision_id: ID of revision to update
            results_text: Results text to save

        Returns:
            Updated revision document

        Raises:
            RevisionError: If revision doesn't exist or update fails
        """
        try:
            updated_revision = self.revisions_db.update_one({"_id": revision_id}, {"results_text": results_text})
            if not updated_revision:
                raise RevisionError(f"Revision {revision_id} not found", status_code=404)
            return self.revisions_db.find_one({"_id": revision_id})
        except RevisionError:
            raise
        except Exception as e:
            raise RevisionError(f"Error updating revision results: {str(e)}") from e

    def toggle_favorite(self, revision_id: str) -> Dict[str, Any]:
        """
        Toggle the favorite status of a revision.

        Args:
            revision_id: ID of revision to toggle favorite status

        Returns:
            Updated revision document with new favorite status

        Raises:
            RevisionError: If revision doesn't exist or toggle fails
        """
        try:
            revision = self.revisions_db.find_one({"_id": revision_id})
            if not revision:
                raise RevisionError(f"Revision {revision_id} not found", status_code=404)

            success = self.revisions_db.toggle_favorite(revision_id)
            if not success:
                raise RevisionError("Failed to toggle revision favorite status", status_code=400)

            return self.revisions_db.find_one({"_id": revision_id})
        except RevisionError:
            raise
        except Exception as e:
            raise RevisionError(f"Error toggling revision favorite: {str(e)}") from e

    def check_dependencies(self, revision_id: str) -> Dict[str, Any]:
        """
        Check dependencies for a revision before deletion.

        Args:
            revision_id: The revision ID

        Returns:
            Dictionary with dependency warnings

        Raises:
            RevisionError: If revision doesn't exist
        """
        rev = self.get_revision(revision_id)
        if not rev:
            raise RevisionError(f"Revision {revision_id} not found", status_code=404)

        warnings = check_revision_dependencies(revision_id)
        return format_warnings_response(warnings)

    def delete_revision(
        self,
        revision_id: str,
        confirmed: bool = False
    ) -> Dict[str, Any]:
        """
        Delete a revision by moving it to trash.

        Args:
            revision_id: ID of revision to delete
            confirmed: Whether user confirmed deletion with warnings

        Returns:
            Dictionary with deletion results and warnings

        Raises:
            RevisionError: If revision doesn't exist or has unconfirmed dependencies
        """
        # Get revision info
        rev = self.get_revision(revision_id)
        if not rev:
            raise RevisionError(f"Revision {revision_id} not found", status_code=404)

        # Get experiment info for directory structure
        experiment = self.experiments_db.find_one({"_id": rev.get("experiment_id")})
        experiment_name = experiment.get("name", "unknown") if experiment else "unknown"

        # Check dependencies
        warnings = check_revision_dependencies(revision_id)

        # If not confirmed and there are warnings, raise error with 409 status
        if not confirmed and warnings:
            error_detail = {
                "message": "Revision has dependencies. Set confirmed=true to proceed with deletion.",
                **format_warnings_response(warnings)
            }
            raise RevisionError(
                "Revision has dependencies",
                status_code=409,
                detail=error_detail
            )

        # Move to trash
        moved_paths = []
        try:
            moved_paths = move_revision_to_trash(
                rev.get("experiment_id"),
                revision_id,
                experiment_name,
                rev.get("name", "unnamed")
            )
        except Exception as e:
            logger.error(f"Failed to move revision to trash: {e}")

        # Delete associated runs from database (they're already in trash via directory move)
        associated_runs = self.runs_db.find_many({"revision_id": revision_id})
        for run in associated_runs:
            self.runs_db.delete_one({"_id": run["_id"]})

        # Delete from database
        deleted = self.revisions_db.delete_one({"_id": revision_id})
        if not deleted:
            raise RevisionError("Failed to delete revision from database", status_code=500)

        return {
            "message": "Revision moved to trash successfully",
            "deleted_id": revision_id,
            "moved_to_trash": moved_paths,
            "deleted_runs": len(associated_runs),
            "warnings": format_warnings_response(warnings) if warnings else None
        }
