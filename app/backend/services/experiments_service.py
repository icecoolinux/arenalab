"""
ExperimentService - Business logic for experiment management.

Handles experiment CRUD operations, validation, and related business rules.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from db import experiments, revisions, runs
from models import ExperimentModel, ExperimentBody
from utils.file_tools import delete_files
from runner import get_effective_run_status


class ExperimentError(Exception):
    """Custom exception for experiment-related errors."""
    pass


class ExperimentService:
    """Service for managing experiments and their business logic."""
    
    def __init__(self):
        self.experiments_db = experiments
        self.revisions_db = revisions
        self.runs_db = runs
    
    def list_experiments(self) -> List[Dict[str, Any]]:
        """
        Get all experiments sorted by creation date.
        
        Returns:
            List of experiment documents sorted by created_at descending
        """
        exps = self.experiments_db.find_many()
        # Sort by created_at descending
        exps.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
        return exps
    
    def get_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single experiment by ID.
        
        Args:
            experiment_id: The experiment ID to retrieve
            
        Returns:
            Experiment document or None if not found
        """
        return self.experiments_db.find_one({"_id": experiment_id})
    
    def create_experiment(self, experiment_data: ExperimentBody) -> Dict[str, Any]:
        """
        Create a new experiment with validation.
        
        Args:
            experiment_data: Validated experiment data from request body
            
        Returns:
            Created experiment document
            
        Raises:
            ExperimentError: If experiment creation fails
        """
        try:
            # Check if experiment with same name already exists
            existing = self.experiments_db.find_by_name(experiment_data.name)
            if existing:
                raise ExperimentError(f"Experiment with name '{experiment_data.name}' already exists")
            
            # Create the experiment
            experiment_id = self.experiments_db.create_experiment(
                name=experiment_data.name,
                description=experiment_data.description,
                tags=experiment_data.tags,
                enabled_plugins=experiment_data.enabled_plugins
            )
            
            # Return the created experiment
            created_experiment = self.experiments_db.find_one({"_id": experiment_id})
            if not created_experiment:
                raise ExperimentError("Failed to retrieve created experiment")
                
            return created_experiment
            
        except Exception as e:
            if isinstance(e, ExperimentError):
                raise
            raise ExperimentError(f"Failed to create experiment: {str(e)}") from e
    
    def delete_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """
        Delete an experiment and all its related data.
        
        This includes:
        - All revisions belonging to the experiment
        - All runs belonging to the experiment  
        - Associated files (YAML configs, logs, tensorboard data)
        
        Args:
            experiment_id: ID of experiment to delete
            
        Returns:
            Dictionary with deletion counts for each entity type
            
        Raises:
            ExperimentError: If experiment doesn't exist or deletion fails
        """
        try:
            # Verify experiment exists
            experiment = self.get_experiment(experiment_id)
            if not experiment:
                raise ExperimentError(f"Experiment {experiment_id} not found")
            
            # Get all related data before deletion
            revision_docs = self.revisions_db.find_many({"experiment_id": experiment_id})
            run_docs = self.runs_db.find_many({"experiment_id": experiment_id})
            
            # Collect file paths to delete
            files_to_delete = []
            
            # Add revision YAML files
            files_to_delete.extend([
                rev.get("yaml_path") for rev in revision_docs 
                if rev.get("yaml_path")
            ])
            
            # Add run files
            files_to_delete.extend([
                run.get("yaml_path") for run in run_docs 
                if run.get("yaml_path")
            ])
            files_to_delete.extend([
                run.get("tb_logdir") for run in run_docs 
                if run.get("tb_logdir")
            ])
            files_to_delete.extend([
                run.get("stdout_log_path") for run in run_docs 
                if run.get("stdout_log_path")
            ])
            
            # Delete files from filesystem
            delete_files(files_to_delete)
            
            # Delete database records
            revision_count = 0
            for revision in revision_docs:
                if self.revisions_db.delete_one({"_id": revision["_id"]}):
                    revision_count += 1
            
            run_count = 0
            for run in run_docs:
                if self.runs_db.delete_one({"_id": run["_id"]}):
                    run_count += 1
            
            # Delete the experiment itself
            experiment_deleted = self.experiments_db.delete_one({"_id": experiment_id})
            
            return {
                "deleted_counts": {
                    "experiments": 1 if experiment_deleted else 0,
                    "revisions": revision_count,
                    "runs": run_count,
                    "files_cleaned": len([f for f in files_to_delete if f])
                }
            }
            
        except ExperimentError:
            raise
        except Exception as e:
            raise ExperimentError(f"Failed to delete experiment: {str(e)}") from e
    
    def update_experiment(self, experiment_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an experiment's metadata.
        
        Args:
            experiment_id: ID of experiment to update
            updates: Dictionary of fields to update
            
        Returns:
            Updated experiment document
            
        Raises:
            ExperimentError: If experiment doesn't exist or update fails
        """
        try:
            # Verify experiment exists
            experiment = self.get_experiment(experiment_id)
            if not experiment:
                raise ExperimentError(f"Experiment {experiment_id} not found")
            
            # Add updated_at timestamp
            updates["updated_at"] = datetime.utcnow()
            
            # Perform update
            success = self.experiments_db.update_one({"_id": experiment_id}, updates)
            if not success:
                raise ExperimentError("No changes were made to the experiment")
            
            # Return updated experiment
            updated_experiment = self.get_experiment(experiment_id)
            return updated_experiment
            
        except ExperimentError:
            raise
        except Exception as e:
            raise ExperimentError(f"Failed to update experiment: {str(e)}") from e
    
    def update_experiment_results(self, experiment_id: str, results_text: str) -> Dict[str, Any]:
        """
        Update an experiment's results text.
        
        Args:
            experiment_id: ID of experiment to update
            results_text: The new results text content
            
        Returns:
            Updated experiment document
            
        Raises:
            ExperimentError: If experiment doesn't exist or update fails
        """
        try:
            # Verify experiment exists
            experiment = self.get_experiment(experiment_id)
            if not experiment:
                raise ExperimentError(f"Experiment {experiment_id} not found")
            
            # Update results text and timestamp
            updates = {
                "results_text": results_text,
                "updated_at": datetime.utcnow()
            }
            
            # Perform update
            success = self.experiments_db.update_one({"_id": experiment_id}, updates)
            if not success:
                raise ExperimentError("Failed to update experiment results")
            
            # Return updated experiment
            updated_experiment = self.get_experiment(experiment_id)
            return updated_experiment
            
        except ExperimentError:
            raise
        except Exception as e:
            raise ExperimentError(f"Failed to update experiment results: {str(e)}") from e
    
    def get_experiment_stats(self, experiment_id: str) -> Dict[str, Any]:
        """
        Get statistics for an experiment.
        
        Args:
            experiment_id: ID of experiment
            
        Returns:
            Dictionary with experiment statistics
        """
        try:
            experiment = self.get_experiment(experiment_id)
            if not experiment:
                raise ExperimentError(f"Experiment {experiment_id} not found")
            
            # Get counts
            revision_count = len(self.revisions_db.find_many({"experiment_id": experiment_id}))
            run_count = len(self.runs_db.find_many({"experiment_id": experiment_id}))
            
            # Get run status breakdown using centralized status
            runs = self.runs_db.find_many({"experiment_id": experiment_id})
            status_counts = {}
            for run in runs:
                # Use centralized status function for accurate counts
                status = get_effective_run_status(run["_id"])
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "experiment_id": experiment_id,
                "revision_count": revision_count,
                "run_count": run_count,
                "run_status_breakdown": status_counts,
                "created_at": experiment.get("created_at"),
                "updated_at": experiment.get("updated_at")
            }
            
        except ExperimentError:
            raise
        except Exception as e:
            raise ExperimentError(f"Failed to get experiment stats: {str(e)}") from e
    
    def toggle_experiment_favorite(self, experiment_id: str) -> Dict[str, Any]:
        """
        Toggle the favorite status of an experiment.
        
        Args:
            experiment_id: ID of experiment to toggle favorite status
            
        Returns:
            Updated experiment document with new favorite status
            
        Raises:
            ExperimentError: If experiment doesn't exist or toggle fails
        """
        try:
            # Verify experiment exists
            experiment = self.get_experiment(experiment_id)
            if not experiment:
                raise ExperimentError(f"Experiment {experiment_id} not found")
            
            # Toggle favorite status using database method
            success = self.experiments_db.toggle_favorite(experiment_id)
            if not success:
                raise ExperimentError("Failed to toggle experiment favorite status")
            
            # Return updated experiment
            updated_experiment = self.get_experiment(experiment_id)
            return updated_experiment
            
        except ExperimentError:
            raise
        except Exception as e:
            raise ExperimentError(f"Failed to toggle experiment favorite: {str(e)}") from e