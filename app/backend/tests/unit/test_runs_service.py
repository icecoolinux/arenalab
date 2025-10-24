"""
Unit tests for RunService.

Tests run management business logic.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from services.runs_service import RunService, RunError
from models import RunBody


@pytest.mark.unit
class TestRunService:
    """Test cases for RunService."""

    @pytest.fixture
    def service(self, mock_db):
        """Create RunService instance with mocked database."""
        with patch('services.runs_service.runs') as mock_runs, \
             patch('services.runs_service.experiments') as mock_experiments, \
             patch('services.runs_service.revisions') as mock_revisions:

            # Configure mocks
            mock_runs.find_many = mock_db.runs.find
            mock_runs.find_one = mock_db.runs.find_one
            mock_experiments.find_one = mock_db.experiments.find_one
            mock_revisions.find_one = mock_db.revisions.find_one

            service = RunService()
            service.runs_db = mock_runs
            service.experiments_db = mock_experiments
            service.revisions_db = mock_revisions

            return service

    @pytest.fixture
    def sample_run(self):
        """Provide a sample run document."""
        return {
            "_id": "test_run_id",
            "name": "Test Run",
            "experiment_id": "exp_123",
            "revision_id": "rev_456",
            "status": "created",
            "created_at": datetime(2024, 1, 1),
            "yaml_path": "/workspace/test.yaml",
            "tb_logdir": "/workspace/tb",
            "stdout_log_path": "/workspace/stdout.log"
        }


class TestListRuns(TestRunService):
    """Test list_runs functionality."""

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_empty(self, mock_status, service):
        """Test listing runs when none exist."""
        mock_status.return_value = "created"

        result = service.list_runs()

        assert result["runs"] == []
        assert result["total"] == 0

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_with_data(self, mock_status, service, mock_db, sample_run):
        """Test listing runs with sample data."""
        mock_status.return_value = "created"
        mock_db.runs.insert_one(sample_run)

        result = service.list_runs()

        assert len(result["runs"]) == 1
        assert result["runs"][0]["name"] == "Test Run"
        assert result["total"] == 1

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_with_limit(self, mock_status, service, mock_db):
        """Test pagination with limit."""
        mock_status.return_value = "created"

        # Insert multiple runs
        for i in range(5):
            mock_db.runs.insert_one({
                "_id": f"run_{i}",
                "name": f"Run {i}",
                "created_at": datetime(2024, 1, i + 1)
            })

        result = service.list_runs(limit=3)

        assert len(result["runs"]) == 3
        assert result["total"] == 5
        assert result["limit"] == 3

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_with_offset(self, mock_status, service, mock_db):
        """Test pagination with offset."""
        mock_status.return_value = "created"

        # Insert runs
        for i in range(5):
            mock_db.runs.insert_one({
                "_id": f"run_{i}",
                "name": f"Run {i}",
                "created_at": datetime(2024, 1, i + 1)
            })

        result = service.list_runs(limit=2, offset=2)

        assert len(result["runs"]) == 2
        assert result["offset"] == 2

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_filter_by_experiment(self, mock_status, service, mock_db):
        """Test filtering runs by experiment_id."""
        mock_status.return_value = "created"

        mock_db.runs.insert_one({"_id": "run1", "experiment_id": "exp1"})
        mock_db.runs.insert_one({"_id": "run2", "experiment_id": "exp2"})

        result = service.list_runs(experiment_id="exp1")

        assert len(result["runs"]) == 1
        assert result["runs"][0]["_id"] == "run1"

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_filter_by_revision(self, mock_status, service, mock_db):
        """Test filtering runs by revision_id."""
        mock_status.return_value = "created"

        mock_db.runs.insert_one({"_id": "run1", "revision_id": "rev1"})
        mock_db.runs.insert_one({"_id": "run2", "revision_id": "rev2"})

        result = service.list_runs(revision_id="rev1")

        assert len(result["runs"]) == 1
        assert result["runs"][0]["_id"] == "run1"

    def test_list_runs_limit_too_high(self, service):
        """Test that limit validation works."""
        with pytest.raises(RunError, match="cannot exceed 1000"):
            service.list_runs(limit=1001)

    def test_list_runs_negative_offset(self, service):
        """Test that offset validation works."""
        with pytest.raises(RunError, match="cannot be negative"):
            service.list_runs(offset=-1)

    def test_list_runs_invalid_status(self, service):
        """Test that status validation works."""
        with pytest.raises(RunError, match="Invalid status"):
            service.list_runs(status="invalid_status")

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_valid_status(self, mock_status, service, mock_db):
        """Test filtering by valid status."""
        mock_status.side_effect = lambda run_id: "running" if run_id == "run1" else "failed"

        mock_db.runs.insert_one({"_id": "run1", "status": "created"})
        mock_db.runs.insert_one({"_id": "run2", "status": "created"})

        result = service.list_runs(status="running")

        assert len(result["runs"]) == 1
        assert result["runs"][0]["_id"] == "run1"


class TestGetRun(TestRunService):
    """Test get_run functionality."""

    @patch('services.runs_service.get_effective_run_status')
    def test_get_run_exists(self, mock_status, service, mock_db, sample_run):
        """Test getting an existing run."""
        mock_status.return_value = "running"
        mock_db.runs.insert_one(sample_run)

        result = service.get_run("test_run_id")

        assert result is not None
        assert result["name"] == "Test Run"
        assert result["status"] == "running"  # Live status

    def test_get_run_not_found(self, service):
        """Test getting non-existent run."""
        result = service.get_run("nonexistent_id")

        assert result is None


class TestRunValidation(TestRunService):
    """Test run validation logic."""

    def test_validate_status_valid(self, service):
        """Test valid status values."""
        valid_statuses = ["created", "pending", "running", "succeeded", "failed", "stopped"]

        for status in valid_statuses:
            # Should not raise error
            try:
                service.list_runs(status=status, limit=0)
            except RunError as e:
                if "Invalid status" in str(e):
                    pytest.fail(f"Status '{status}' should be valid")

    def test_pagination_validation(self, service):
        """Test pagination parameter validation."""
        # Valid values should work
        try:
            service.list_runs(limit=100, offset=0)
            service.list_runs(limit=1, offset=999)
        except RunError as e:
            pytest.fail(f"Valid pagination should not raise error: {e}")

    @patch('services.runs_service.get_effective_run_status')
    def test_list_runs_sorting(self, mock_status, service, mock_db):
        """Test that runs are sorted by created_at descending."""
        mock_status.return_value = "created"

        run1 = {"_id": "run1", "created_at": datetime(2024, 1, 1)}
        run2 = {"_id": "run2", "created_at": datetime(2024, 1, 3)}
        run3 = {"_id": "run3", "created_at": datetime(2024, 1, 2)}

        mock_db.runs.insert_many([run1, run2, run3])

        result = service.list_runs()

        # Should be sorted newest first
        assert result["runs"][0]["_id"] == "run2"  # Jan 3
        assert result["runs"][1]["_id"] == "run3"  # Jan 2
        assert result["runs"][2]["_id"] == "run1"  # Jan 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
