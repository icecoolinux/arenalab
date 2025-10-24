"""
Unit tests for ExperimentService.

Tests the business logic of experiment operations.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from services.experiments_service import ExperimentService, ExperimentError
from models import ExperimentBody


class TestExperimentService:
    """Test cases for ExperimentService."""
    
    @pytest.fixture
    def service(self, mock_db):
        """Create an ExperimentService instance with mocked database."""
        with patch('services.experiments_service.experiments') as mock_experiments, \
             patch('services.experiments_service.revisions') as mock_revisions, \
             patch('services.experiments_service.runs') as mock_runs:
            
            # Configure mocks to use the mock database
            mock_experiments.find_many = mock_db.experiments.find
            mock_experiments.find_one = mock_db.experiments.find_one
            mock_experiments.find_by_name = lambda name: mock_db.experiments.find_one({"name": name})
            mock_experiments.create_experiment = mock_db.experiments.insert_one
            mock_experiments.update_one = mock_db.experiments.update_one
            mock_experiments.delete_one = mock_db.experiments.delete_one
            
            mock_revisions.find_many = mock_db.revisions.find
            mock_revisions.delete_one = mock_db.revisions.delete_one
            
            mock_runs.find_many = mock_db.runs.find
            mock_runs.delete_one = mock_db.runs.delete_one
            
            service = ExperimentService()
            service.experiments_db = mock_experiments
            service.revisions_db = mock_revisions
            service.runs_db = mock_runs
            
            return service
    
    def test_list_experiments_empty(self, service):
        """Test listing experiments when none exist."""
        result = service.list_experiments()
        assert result == []
    
    def test_list_experiments_with_data(self, service, sample_experiment, mock_db):
        """Test listing experiments with sample data."""
        # Add sample experiment
        mock_db.experiments.insert_one(sample_experiment)
        
        result = service.list_experiments()
        assert len(result) == 1
        assert result[0]["name"] == "Test Experiment"
    
    def test_list_experiments_sorting(self, service, mock_db):
        """Test that experiments are sorted by created_at descending."""
        # Add multiple experiments with different dates
        exp1 = {"name": "First", "created_at": datetime(2024, 1, 1)}
        exp2 = {"name": "Second", "created_at": datetime(2024, 1, 2)}
        exp3 = {"name": "Third", "created_at": datetime(2024, 1, 3)}
        
        mock_db.experiments.insert_many([exp1, exp2, exp3])
        
        result = service.list_experiments()
        assert len(result) == 3
        assert result[0]["name"] == "Third"  # Most recent first
        assert result[2]["name"] == "First"  # Oldest last
    
    def test_get_experiment_exists(self, service, sample_experiment, mock_db):
        """Test getting an existing experiment."""
        mock_db.experiments.insert_one(sample_experiment)
        
        result = service.get_experiment("test_experiment_id")
        assert result is not None
        assert result["name"] == "Test Experiment"
    
    def test_get_experiment_not_exists(self, service):
        """Test getting a non-existent experiment."""
        result = service.get_experiment("nonexistent_id")
        assert result is None
    
    def test_create_experiment_success(self, service):
        """Test successful experiment creation."""
        experiment_data = ExperimentBody(
            name="New Experiment",
            description="A new test experiment",
            tags=["test"]
        )
        
        with patch.object(service.experiments_db, 'find_by_name', return_value=None), \
             patch.object(service.experiments_db, 'create_experiment', return_value="new_exp_id"), \
             patch.object(service.experiments_db, 'find_one', 
                         return_value={"_id": "new_exp_id", "name": "New Experiment"}):
            
            result = service.create_experiment(experiment_data)
            
            assert result["_id"] == "new_exp_id"
            assert result["name"] == "New Experiment"
    
    def test_create_experiment_duplicate_name(self, service):
        """Test creating experiment with duplicate name."""
        experiment_data = ExperimentBody(
            name="Existing Experiment",
            description="This should fail",
            tags=[]
        )
        
        with patch.object(service.experiments_db, 'find_by_name', 
                         return_value={"name": "Existing Experiment"}):
            
            with pytest.raises(ExperimentError, match="already exists"):
                service.create_experiment(experiment_data)
    
    def test_delete_experiment_success(self, service, mock_db, sample_experiment):
        """Test successful experiment deletion."""
        # Setup data
        mock_db.experiments.insert_one(sample_experiment)
        
        # Mock file cleanup
        with patch('services.experiments_service.delete_files') as mock_delete_files:
            mock_delete_files.return_value = {"deleted": 2, "errors": 0}
            
            result = service.delete_experiment("test_experiment_id")
            
            assert result["deleted_counts"]["experiments"] == 1
            assert result["deleted_counts"]["revisions"] == 0
            assert result["deleted_counts"]["runs"] == 0
    
    def test_delete_experiment_not_found(self, service):
        """Test deleting non-existent experiment."""
        with pytest.raises(ExperimentError, match="not found"):
            service.delete_experiment("nonexistent_id")
    
    def test_delete_experiment_with_children(self, service, mock_db, sample_experiment):
        """Test deleting experiment that has revisions and runs."""
        # Setup data
        mock_db.experiments.insert_one(sample_experiment)
        mock_db.revisions.insert_one({
            "_id": "rev1", 
            "experiment_id": "test_experiment_id",
            "yaml_path": "/test/rev.yaml"
        })
        mock_db.runs.insert_one({
            "_id": "run1", 
            "experiment_id": "test_experiment_id",
            "yaml_path": "/test/run.yaml",
            "tb_logdir": "/test/tb",
            "stdout_log_path": "/test/stdout.log"
        })
        
        with patch('services.experiments_service.delete_files') as mock_delete_files:
            mock_delete_files.return_value = {"deleted": 4, "errors": 0}
            
            result = service.delete_experiment("test_experiment_id")
            
            assert result["deleted_counts"]["experiments"] == 1
            assert result["deleted_counts"]["revisions"] == 1
            assert result["deleted_counts"]["runs"] == 1
            assert result["deleted_counts"]["files_cleaned"] == 4
            
            # Verify delete_files was called with correct paths
            mock_delete_files.assert_called_once()
            called_files = mock_delete_files.call_args[0][0]
            assert "/test/rev.yaml" in called_files
            assert "/test/run.yaml" in called_files
            assert "/test/tb" in called_files
            assert "/test/stdout.log" in called_files
    
    def test_get_experiment_stats(self, service, mock_db, sample_experiment):
        """Test getting experiment statistics."""
        # Setup data
        mock_db.experiments.insert_one(sample_experiment)
        mock_db.revisions.insert_one({"experiment_id": "test_experiment_id"})
        mock_db.runs.insert_many([
            {"experiment_id": "test_experiment_id", "status": "completed"},
            {"experiment_id": "test_experiment_id", "status": "failed"},
            {"experiment_id": "test_experiment_id", "status": "running"}
        ])
        
        result = service.get_experiment_stats("test_experiment_id")
        
        assert result["experiment_id"] == "test_experiment_id"
        assert result["revision_count"] == 1
        assert result["run_count"] == 3
        assert result["run_status_breakdown"] == {
            "completed": 1,
            "failed": 1,
            "running": 1
        }
    
    def test_get_experiment_stats_not_found(self, service):
        """Test getting stats for non-existent experiment."""
        with pytest.raises(ExperimentError, match="not found"):
            service.get_experiment_stats("nonexistent_id")
    
    @pytest.mark.parametrize("field,value", [
        ("description", "Updated description"),
        ("tags", ["updated", "tags"]),
    ])
    def test_update_experiment_success(self, service, mock_db, sample_experiment, field, value):
        """Test successful experiment updates."""
        mock_db.experiments.insert_one(sample_experiment)
        
        with patch.object(service.experiments_db, 'update_one', return_value=True):
            result = service.update_experiment("test_experiment_id", {field: value})
            
            assert result is not None
            # The updated result would come from get_experiment which uses mock_db
    
    def test_update_experiment_not_found(self, service):
        """Test updating non-existent experiment."""
        with pytest.raises(ExperimentError, match="not found"):
            service.update_experiment("nonexistent_id", {"description": "test"})