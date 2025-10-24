"""
Unit tests for EnvironmentsService.

Tests the business logic of environment operations.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from services.environments_service import EnvironmentsService, EnvironmentError


class TestEnvironmentsService:
    """Test cases for EnvironmentsService."""

    @pytest.fixture
    def service(self, mock_db):
        """Create an EnvironmentsService instance with mocked database."""
        with patch('services.environments_service.environments') as mock_environments, \
             patch('services.environments_service.revisions') as mock_revisions:

            # Configure mocks to use the mock database
            mock_environments.find_many = mock_db.environments.find
            mock_environments.find_one = mock_db.environments.find_one
            mock_environments.create_environment = mock_db.environments.insert_one
            mock_environments.update_one = mock_db.environments.update_one
            mock_environments.update_environment_paths = MagicMock(return_value=True)
            mock_environments.delete_one = mock_db.environments.delete_one

            mock_revisions.find_many = mock_db.revisions.find

            service = EnvironmentsService()
            service.environments_db = mock_environments
            service.revisions_db = mock_revisions

            return service

    @pytest.fixture
    def sample_environment(self):
        """Sample environment for testing."""
        return {
            "_id": "test_env_id",
            "name": "TestEnv",
            "version": 1,
            "description": "Test environment",
            "env_path": "envs/TestEnv_v1_test_env_id",
            "executable_file": "TestEnv.x86_64",
            "created_at": datetime(2024, 1, 1),
            "original_filename": "TestEnv.zip",
            "file_format": "zip",
            "compressed_file_path": "envs/TestEnv_v1_test_env_id/TestEnv.zip",
            "git_commit_url": None
        }

    def test_list_environments_empty(self, service):
        """Test listing environments when none exist."""
        result = service.list_environments()
        assert result == []

    def test_list_environments_with_data(self, service, sample_environment, mock_db):
        """Test listing environments with sample data."""
        # Add sample environment
        mock_db.environments.insert_one(sample_environment)

        result = service.list_environments()
        assert len(result) == 1
        assert result[0]["name"] == "TestEnv"

    def test_list_environments_sorting(self, service, mock_db):
        """Test that environments are sorted by created_at descending."""
        # Add multiple environments with different dates
        env1 = {"name": "Env1", "version": 1, "created_at": datetime(2024, 1, 1)}
        env2 = {"name": "Env2", "version": 1, "created_at": datetime(2024, 1, 2)}
        env3 = {"name": "Env3", "version": 1, "created_at": datetime(2024, 1, 3)}

        mock_db.environments.insert_many([env1, env2, env3])

        result = service.list_environments()
        assert len(result) == 3
        assert result[0]["name"] == "Env3"  # Most recent first
        assert result[2]["name"] == "Env1"  # Oldest last

    def test_get_environment_exists(self, service, sample_environment, mock_db):
        """Test getting an existing environment."""
        mock_db.environments.insert_one(sample_environment)

        result = service.get_environment("test_env_id")
        assert result is not None
        assert result["name"] == "TestEnv"
        assert result["version"] == 1

    def test_get_environment_not_found(self, service):
        """Test getting a non-existent environment."""
        result = service.get_environment("nonexistent_id")
        assert result is None

    @patch('services.environments_service.get_environment_info')
    def test_get_environment_info_success(self, mock_get_info, service, sample_environment, mock_db):
        """Test getting detailed environment information."""
        mock_db.environments.insert_one(sample_environment)
        mock_get_info.return_value = {"exists": True, "executable": "TestEnv.x86_64"}

        result = service.get_environment_info("test_env_id")
        assert result["environment"]["name"] == "TestEnv"
        assert "filesystem_info" in result

    @patch('services.environments_service.get_environment_info')
    def test_get_environment_info_not_found(self, mock_get_info, service):
        """Test getting info for non-existent environment."""
        with pytest.raises(EnvironmentError) as exc_info:
            service.get_environment_info("nonexistent_id")
        assert exc_info.value.status_code == 404

    @patch('services.environments_service.check_environment_dependencies')
    def test_check_dependencies_no_warnings(self, mock_check_deps, service, sample_environment, mock_db):
        """Test checking dependencies when there are none."""
        mock_db.environments.insert_one(sample_environment)
        mock_check_deps.return_value = []

        result = service.check_dependencies("test_env_id")
        assert result["has_warnings"] == False
        assert result["warnings"] == []

    @patch('services.environments_service.check_environment_dependencies')
    def test_check_dependencies_with_warnings(self, mock_check_deps, service, sample_environment, mock_db):
        """Test checking dependencies when environment is in use."""
        mock_db.environments.insert_one(sample_environment)
        mock_check_deps.return_value = [
            {"warning_type": "environment_revisions", "message": "1 revision(s) use this environment"}
        ]

        result = service.check_dependencies("test_env_id")
        assert result["has_warnings"] == True
        assert len(result["warnings"]) > 0

    @patch('services.environments_service.check_environment_dependencies')
    @patch('services.environments_service.move_environment_to_trash')
    def test_delete_environment_no_dependencies(self, mock_move_trash, mock_check_deps,
                                                 service, sample_environment, mock_db):
        """Test deleting an environment with no dependencies."""
        mock_db.environments.insert_one(sample_environment)
        mock_check_deps.return_value = []
        mock_move_trash.return_value = ["envs/TestEnv_v1_test_env_id"]

        result = service.delete_environment("test_env_id", confirmed=False)

        assert result["deleted_id"] == "test_env_id"
        assert "moved_to_trash" in result
        # Verify environment was deleted from DB
        assert mock_db.environments.find_one({"_id": "test_env_id"}) is None

    @patch('services.environments_service.check_environment_dependencies')
    def test_delete_environment_with_unconfirmed_dependencies(self, mock_check_deps,
                                                               service, sample_environment, mock_db):
        """Test that deleting an environment with dependencies requires confirmation."""
        mock_db.environments.insert_one(sample_environment)
        mock_check_deps.return_value = [
            {"warning_type": "environment_revisions", "message": "1 revision(s) use this environment"}
        ]

        with pytest.raises(EnvironmentError) as exc_info:
            service.delete_environment("test_env_id", confirmed=False)

        assert exc_info.value.status_code == 409
        assert "dependencies" in str(exc_info.value).lower()
        # Verify environment was NOT deleted
        assert mock_db.environments.find_one({"_id": "test_env_id"}) is not None

    @patch('services.environments_service.check_environment_dependencies')
    @patch('services.environments_service.move_environment_to_trash')
    def test_delete_environment_with_confirmed_dependencies(self, mock_move_trash, mock_check_deps,
                                                            service, sample_environment, mock_db):
        """Test deleting an environment with dependencies when confirmed."""
        mock_db.environments.insert_one(sample_environment)
        mock_check_deps.return_value = [
            {"warning_type": "environment_revisions", "message": "1 revision(s) use this environment"}
        ]
        mock_move_trash.return_value = ["envs/TestEnv_v1_test_env_id"]

        result = service.delete_environment("test_env_id", confirmed=True)

        assert result["deleted_id"] == "test_env_id"
        assert result["warnings"] is not None
        # Verify environment was deleted despite warnings
        assert mock_db.environments.find_one({"_id": "test_env_id"}) is None

    def test_delete_environment_not_found(self, service):
        """Test deleting a non-existent environment."""
        with pytest.raises(EnvironmentError) as exc_info:
            service.delete_environment("nonexistent_id")
        assert exc_info.value.status_code == 404
