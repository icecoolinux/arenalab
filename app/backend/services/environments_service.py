"""
EnvironmentsService - Business logic for environment management.

Handles environment CRUD operations, file processing, validation, and related business rules.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from db import environments, revisions
from utils.env_tools import process_environment_upload, get_environment_info, EnvExtractionError
from utils.dependency_checks import check_environment_dependencies, format_warnings_response
from utils.trash import move_environment_to_trash
import logging

logger = logging.getLogger(__name__)


class EnvironmentError(Exception):
    """Custom exception for environment-related errors."""
    def __init__(self, message: str, status_code: int = 400, detail: Dict[str, Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {"message": message}


class EnvironmentsService:
    """Service for managing environments and their business logic."""

    def __init__(self):
        self.environments_db = environments
        self.revisions_db = revisions

    def list_environments(self) -> List[Dict[str, Any]]:
        """
        Get all environments sorted by creation date.

        Returns:
            List of environment documents sorted by created_at descending
        """
        envs = self.environments_db.find_many()
        # Sort by created_at descending
        envs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
        return envs

    def get_environment(self, environment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single environment by ID.

        Args:
            environment_id: The environment ID to retrieve

        Returns:
            Environment document or None if not found
        """
        return self.environments_db.find_one({"_id": environment_id})

    def upload_environment(
        self,
        file,
        name: str,
        description: str = "",
        git_commit_url: str = ""
    ) -> Dict[str, Any]:
        """
        Upload and process a compressed environment file.

        Args:
            file: Uploaded file object
            name: Environment name
            description: Optional description
            git_commit_url: Optional git commit URL

        Returns:
            Created environment document with file paths

        Raises:
            EnvironmentError: If upload or extraction fails
        """
        try:
            # Validate file size (limit to 1GB)
            MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
            file.file.seek(0, 2)  # Seek to end
            file_size = file.file.tell()
            file.file.seek(0)  # Reset to beginning

            if file_size > MAX_FILE_SIZE:
                raise EnvironmentError(
                    f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
                )

            # Create environment record first to get ID and version
            env_id = self.environments_db.create_environment(
                name=name,
                description=description,
                file_info={"original_filename": file.filename},
                git_commit_url=git_commit_url.strip() if git_commit_url.strip() else None
            )

            # Get the created environment to get version number
            created_env = self.environments_db.find_one({"_id": env_id})
            version = created_env["version"]

            try:
                # Process the uploaded file
                env_path, executable_file, compressed_file_path, original_filename, file_format = process_environment_upload(
                    file, version, env_id, name
                )

                # Update environment record with file paths
                self.environments_db.update_environment_paths(
                    env_id, env_path, executable_file, compressed_file_path, original_filename, file_format
                )

                # Return updated environment
                updated_env = self.environments_db.find_one({"_id": env_id})
                return updated_env

            except EnvExtractionError as e:
                # Cleanup database record on extraction failure
                self.environments_db.delete_one({"_id": env_id})
                raise EnvironmentError(str(e)) from e

        except EnvironmentError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in upload_environment: {e}")
            raise EnvironmentError(f"Failed to upload environment: {str(e)}") from e

    def get_environment_info(self, environment_id: str) -> Dict[str, Any]:
        """
        Get detailed information about an environment including filesystem status.

        Args:
            environment_id: The environment ID

        Returns:
            Dictionary with environment and filesystem info

        Raises:
            EnvironmentError: If environment doesn't exist
        """
        env = self.get_environment(environment_id)
        if not env:
            raise EnvironmentError(f"Environment {environment_id} not found", status_code=404)

        # Get filesystem information
        env_info = get_environment_info(env.get("env_path", ""))

        return {
            "environment": env,
            "filesystem_info": env_info
        }

    def check_dependencies(self, environment_id: str) -> Dict[str, Any]:
        """
        Check dependencies for an environment before deletion.

        Args:
            environment_id: The environment ID

        Returns:
            Dictionary with dependency warnings

        Raises:
            EnvironmentError: If environment doesn't exist
        """
        env = self.get_environment(environment_id)
        if not env:
            raise EnvironmentError(f"Environment {environment_id} not found", status_code=404)

        warnings = check_environment_dependencies(environment_id)
        return format_warnings_response(warnings)

    def delete_environment(
        self,
        environment_id: str,
        confirmed: bool = False
    ) -> Dict[str, Any]:
        """
        Delete an environment by moving it to trash.

        Args:
            environment_id: ID of environment to delete
            confirmed: Whether user confirmed deletion with warnings

        Returns:
            Dictionary with deletion results and warnings

        Raises:
            EnvironmentError: If environment doesn't exist or has unconfirmed dependencies
        """
        # Get environment info
        env = self.get_environment(environment_id)
        if not env:
            raise EnvironmentError(f"Environment {environment_id} not found", status_code=404)

        # Check dependencies
        warnings = check_environment_dependencies(environment_id)

        # If not confirmed and there are warnings, raise error with 409 status
        if not confirmed and warnings:
            error_detail = {
                "message": "Environment has dependencies. Set confirmed=true to proceed with deletion.",
                **format_warnings_response(warnings)
            }
            raise EnvironmentError(
                "Environment has dependencies",
                status_code=409,
                detail=error_detail
            )

        # Move to trash
        moved_paths = []
        try:
            moved_paths = move_environment_to_trash(
                environment_id,
                env.get("name", "unknown"),
                env.get("version", 1)
            )
        except Exception as e:
            logger.error(f"Failed to move environment to trash: {e}")

        # Delete from database
        deleted = self.environments_db.delete_one({"_id": environment_id})
        if not deleted:
            raise EnvironmentError("Failed to delete environment from database", status_code=500)

        return {
            "message": "Environment moved to trash successfully",
            "deleted_id": environment_id,
            "moved_to_trash": moved_paths,
            "warnings": format_warnings_response(warnings) if warnings else None
        }
