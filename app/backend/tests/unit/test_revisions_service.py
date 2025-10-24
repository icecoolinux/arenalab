"""
Unit tests for RevisionsService.

Tests the business logic of revision operations.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from services.revisions_service import RevisionsService, RevisionError
from models import RevisionBody


class TestRevisionsService:
    """Test cases for RevisionsService."""

    @pytest.fixture
    def service(self, mock_db):
        """Create a RevisionsService instance with mocked database."""
        with patch('services.revisions_service.revisions') as mock_revisions, \
             patch('services.revisions_service.runs') as mock_runs, \
             patch('services.revisions_service.experiments') as mock_experiments:

            # Configure mocks to use the mock database
            mock_revisions.find_many = mock_db.revisions.find
            mock_revisions.find_one = mock_db.revisions.find_one
            mock_revisions.create_revision = mock_db.revisions.insert_one
            mock_revisions.update_one = mock_db.revisions.update_one
            mock_revisions.delete_one = mock_db.revisions.delete_one
            mock_revisions.toggle_favorite = MagicMock(return_value=True)

            mock_runs.find_many = mock_db.runs.find
            mock_runs.delete_one = mock_db.runs.delete_one

            mock_experiments.find_one = mock_db.experiments.find_one

            service = RevisionsService()
            service.revisions_db = mock_revisions
            service.runs_db = mock_runs
            service.experiments_db = mock_experiments

            return service

    @pytest.fixture
    def sample_revision(self):
        """Sample revision for testing."""
        return {
            "_id": "test_rev_id",
            "experiment_id": "test_exp_id",
            "name": "Test Revision",
            "description": "Test description",
            "yaml_path": "experiments/test-exp_test_exp_id/revisions/test-revision_test_rev_id/config.yaml",
            "environment_id": "test_env_id",
            "cli_flags": {"time_scale": 20},
            "parent_revision_id": "",
            "parent_run_id": "",
            "created_at": datetime(2024, 1, 1),
            "is_favorite": False
        }

    @pytest.fixture
    def sample_experiment(self):
        """Sample experiment for testing."""
        return {
            "_id": "test_exp_id",
            "name": "Test Experiment",
            "description": "Test experiment",
            "tags": [],
            "created_at": datetime(2024, 1, 1)
        }

    def test_list_revisions_empty(self, service):
        """Test listing revisions when none exist."""
        result = service.list_revisions()
        assert result == []

    def test_list_revisions_with_data(self, service, sample_revision, mock_db):
        """Test listing revisions with sample data."""
        mock_db.revisions.insert_one(sample_revision)

        result = service.list_revisions()
        assert len(result) == 1
        assert result[0]["name"] == "Test Revision"

    def test_list_revisions_filtered_by_experiment(self, service, sample_revision, mock_db):
        """Test filtering revisions by experiment ID."""
        mock_db.revisions.insert_one(sample_revision)
        # Add another revision for different experiment
        other_rev = sample_revision.copy()
        other_rev["_id"] = "other_rev_id"
        other_rev["experiment_id"] = "other_exp_id"
        mock_db.revisions.insert_one(other_rev)

        result = service.list_revisions(experiment_id="test_exp_id")
        assert len(result) == 1
        assert result[0]["experiment_id"] == "test_exp_id"

    def test_list_revisions_sorting(self, service, mock_db):
        """Test that revisions are sorted by created_at descending."""
        rev1 = {"experiment_id": "exp1", "name": "Rev1", "created_at": datetime(2024, 1, 1)}
        rev2 = {"experiment_id": "exp1", "name": "Rev2", "created_at": datetime(2024, 1, 2)}
        rev3 = {"experiment_id": "exp1", "name": "Rev3", "created_at": datetime(2024, 1, 3)}

        mock_db.revisions.insert_many([rev1, rev2, rev3])

        result = service.list_revisions()
        assert len(result) == 3
        assert result[0]["name"] == "Rev3"  # Most recent first
        assert result[2]["name"] == "Rev1"  # Oldest last

    def test_get_revision_exists(self, service, sample_revision, mock_db):
        """Test getting an existing revision."""
        mock_db.revisions.insert_one(sample_revision)

        result = service.get_revision("test_rev_id")
        assert result is not None
        assert result["name"] == "Test Revision"

    def test_get_revision_not_found(self, service):
        """Test getting a non-existent revision."""
        result = service.get_revision("nonexistent_id")
        assert result is None

    @patch('services.revisions_service.ensure_revision_structure')
    @patch('services.revisions_service.get_revision_path')
    @patch('services.revisions_service.new_file')
    def test_create_revision_success(self, mock_new_file, mock_get_path, mock_ensure_structure,
                                     service, sample_experiment, mock_db):
        """Test successful revision creation."""
        mock_db.experiments.insert_one(sample_experiment)
        mock_get_path.return_value = "experiments/test-experiment_test_exp_id/revisions/new-rev_new_id"

        revision_data = RevisionBody(
            experiment_id="test_exp_id",
            name="New Revision",
            description="New description",
            yaml="behaviors:\n  TestBehavior:\n    trainer_type: ppo",
            environment_id="test_env_id",
            cli_flags={"time_scale": 20},
            parent_revision_id="",
            parent_run_id=""
        )

        result = service.create_revision(revision_data)

        assert result is not None
        mock_ensure_structure.assert_called_once()
        mock_new_file.assert_called_once()

    def test_create_revision_experiment_not_found(self, service):
        """Test revision creation fails when experiment doesn't exist."""
        revision_data = RevisionBody(
            experiment_id="nonexistent_exp",
            name="New Revision",
            description="New description",
            yaml="behaviors:\n  TestBehavior:\n    trainer_type: ppo",
            environment_id="test_env_id",
            cli_flags={},
            parent_revision_id="",
            parent_run_id=""
        )

        with pytest.raises(RevisionError) as exc_info:
            service.create_revision(revision_data)
        assert exc_info.value.status_code == 404

    def test_update_results_success(self, service, sample_revision, mock_db):
        """Test updating revision results."""
        mock_db.revisions.insert_one(sample_revision)

        result = service.update_results("test_rev_id", "New results text")

        assert result is not None
        # Verify update was called with correct parameters
        updated = mock_db.revisions.find_one({"_id": "test_rev_id"})
        assert updated["results_text"] == "New results text"

    def test_update_results_not_found(self, service):
        """Test updating results for non-existent revision."""
        with pytest.raises(RevisionError) as exc_info:
            service.update_results("nonexistent_id", "New results")
        assert exc_info.value.status_code == 404

    def test_toggle_favorite_success(self, service, sample_revision, mock_db):
        """Test toggling revision favorite status."""
        mock_db.revisions.insert_one(sample_revision)

        result = service.toggle_favorite("test_rev_id")

        assert result is not None
        # Verify toggle was called
        service.revisions_db.toggle_favorite.assert_called_with("test_rev_id")

    def test_toggle_favorite_not_found(self, service):
        """Test toggling favorite for non-existent revision."""
        with pytest.raises(RevisionError) as exc_info:
            service.toggle_favorite("nonexistent_id")
        assert exc_info.value.status_code == 404

    @patch('services.revisions_service.check_revision_dependencies')
    def test_check_dependencies_no_warnings(self, mock_check_deps, service, sample_revision, mock_db):
        """Test checking dependencies when there are none."""
        mock_db.revisions.insert_one(sample_revision)
        mock_check_deps.return_value = []

        result = service.check_dependencies("test_rev_id")
        assert result["has_warnings"] == False
        assert result["warnings"] == []

    @patch('services.revisions_service.check_revision_dependencies')
    def test_check_dependencies_with_warnings(self, mock_check_deps, service, sample_revision, mock_db):
        """Test checking dependencies when revision has runs."""
        mock_db.revisions.insert_one(sample_revision)
        mock_check_deps.return_value = [
            {"warning_type": "revision_runs", "message": "5 run(s) belong to this revision"}
        ]

        result = service.check_dependencies("test_rev_id")
        assert result["has_warnings"] == True
        assert len(result["warnings"]) > 0

    @patch('services.revisions_service.check_revision_dependencies')
    @patch('services.revisions_service.move_revision_to_trash')
    def test_delete_revision_no_dependencies(self, mock_move_trash, mock_check_deps,
                                             service, sample_revision, sample_experiment, mock_db):
        """Test deleting a revision with no dependencies."""
        mock_db.revisions.insert_one(sample_revision)
        mock_db.experiments.insert_one(sample_experiment)
        mock_check_deps.return_value = []
        mock_move_trash.return_value = ["experiments/test-exp_test_exp_id/revisions/test-revision_test_rev_id"]

        result = service.delete_revision("test_rev_id", confirmed=False)

        assert result["deleted_id"] == "test_rev_id"
        assert "moved_to_trash" in result
        # Verify revision was deleted from DB
        assert mock_db.revisions.find_one({"_id": "test_rev_id"}) is None

    @patch('services.revisions_service.check_revision_dependencies')
    def test_delete_revision_with_unconfirmed_dependencies(self, mock_check_deps,
                                                           service, sample_revision, sample_experiment, mock_db):
        """Test that deleting a revision with dependencies requires confirmation."""
        mock_db.revisions.insert_one(sample_revision)
        mock_db.experiments.insert_one(sample_experiment)
        mock_check_deps.return_value = [
            {"warning_type": "revision_runs", "message": "5 run(s) belong to this revision"}
        ]

        with pytest.raises(RevisionError) as exc_info:
            service.delete_revision("test_rev_id", confirmed=False)

        assert exc_info.value.status_code == 409
        assert "dependencies" in str(exc_info.value).lower()
        # Verify revision was NOT deleted
        assert mock_db.revisions.find_one({"_id": "test_rev_id"}) is not None

    @patch('services.revisions_service.check_revision_dependencies')
    @patch('services.revisions_service.move_revision_to_trash')
    def test_delete_revision_with_confirmed_dependencies(self, mock_move_trash, mock_check_deps,
                                                         service, sample_revision, sample_experiment, mock_db):
        """Test deleting a revision with dependencies when confirmed."""
        mock_db.revisions.insert_one(sample_revision)
        mock_db.experiments.insert_one(sample_experiment)
        mock_check_deps.return_value = [
            {"warning_type": "revision_runs", "message": "5 run(s) belong to this revision"}
        ]
        mock_move_trash.return_value = ["experiments/test-exp_test_exp_id/revisions/test-revision_test_rev_id"]

        result = service.delete_revision("test_rev_id", confirmed=True)

        assert result["deleted_id"] == "test_rev_id"
        assert result["warnings"] is not None
        # Verify revision was deleted despite warnings
        assert mock_db.revisions.find_one({"_id": "test_rev_id"}) is None

    def test_delete_revision_not_found(self, service):
        """Test deleting a non-existent revision."""
        with pytest.raises(RevisionError) as exc_info:
            service.delete_revision("nonexistent_id")
        assert exc_info.value.status_code == 404
