"""
RunService - Business logic for run management and ML-Agents process orchestration.

Handles run CRUD operations, process management, and related business rules.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from db import runs, experiments, revisions
from models import RunBody
from runner import launch_run, create_run, execute_run, restart_run, stop_run, get_run_status, get_active_runs, get_run_logs, get_effective_run_status, check_process_health, get_stale_runs, force_kill_run
from utils.file_tools import read_file, new_file, ensure_workspace_path


class RunError(Exception):
    """Custom exception for run-related errors."""
    pass


class RunService:
    """Service for managing runs and their business logic."""
    
    def __init__(self):
        self.runs_db = runs
        self.experiments_db = experiments
        self.revisions_db = revisions
    
    def list_runs(
        self, 
        revision_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List runs with optional filtering and pagination.
        
        Args:
            revision_id: Filter by revision ID
            experiment_id: Filter by experiment ID
            status: Filter by run status
            limit: Maximum number of runs to return
            offset: Number of runs to skip
            
        Returns:
            Dictionary with runs list, total count, and pagination info
            
        Raises:
            RunError: If validation fails
        """
        try:
            # Validate pagination
            if limit > 1000:
                raise RunError("Limit cannot exceed 1000")
            if offset < 0:
                raise RunError("Offset cannot be negative")
            
            # Build query (exclude status filtering from DB query)
            query = {}
            if revision_id:
                query["revision_id"] = revision_id
            if experiment_id:
                query["experiment_id"] = experiment_id
            
            # Validate status if provided
            if status:
                valid_statuses = ["created", "pending", "running", "succeeded", "failed", "stopped"]
                if status not in valid_statuses:
                    raise RunError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
            
            # Get all runs (without status filter in DB)
            all_runs = self.runs_db.find_many(query)
            
            # Apply live status to all runs and filter by status
            filtered_runs = []
            for run in all_runs:
                # Override with live status
                run["status"] = get_effective_run_status(run["_id"])
                
                # Apply status filter if specified
                if not status or run["status"] == status:
                    filtered_runs.append(run)
            
            # Sort by created_at descending
            filtered_runs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
            
            # Apply pagination
            items = filtered_runs[offset:offset + limit]
            total_count = len(filtered_runs)
            
            return {
                "runs": items,
                "total": total_count,
                "limit": limit,
                "offset": offset
            }
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to list runs: {str(e)}") from e
    
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single run by ID with live status.
        
        Args:
            run_id: The run ID to retrieve
            
        Returns:
            Run document with live status or None if not found
        """
        run = self.runs_db.find_one({"_id": run_id})
        if not run:
            return None
        
        # Override status with live status from centralized function
        run["status"] = get_effective_run_status(run_id)
        return run
    
    def create_run(self, run_data: RunBody, auto_start: bool = True) -> Dict[str, Any]:
        """
        Create a new ML-Agents run, optionally starting execution.

        Args:
            run_data: Validated run data from request body
            auto_start: Whether to automatically start execution (default: True for backwards compatibility)

        Returns:
            Created run document

        Raises:
            RunError: If run creation or launch fails
        """
        try:
            # Validate related entities exist
            experiment = self.experiments_db.find_one({"_id": run_data.experiment_id})
            if not experiment:
                raise RunError(f"Experiment {run_data.experiment_id} not found")

            revision = self.revisions_db.find_one({"_id": run_data.revision_id})
            if not revision:
                raise RunError(f"Revision {run_data.revision_id} not found")

            try:
                if auto_start:
                    # Launch run (create and execute)
                    run_id = launch_run(
                        experiment=experiment,
                        revision=revision,
                        yaml_text=run_data.yaml,
                        cli_flags=run_data.cli_flags,
                        description=run_data.description,
                        results_text=run_data.results_text,
                        parent_run_id=run_data.parent_run_id,
                        parent_revision_id=run_data.parent_revision_id
                    )
                else:
                    # Create run without starting execution
                    run_id = create_run(
                        experiment=experiment,
                        revision=revision,
                        yaml_text=run_data.yaml,
                        cli_flags=run_data.cli_flags,
                        description=run_data.description,
                        results_text=run_data.results_text,
                        parent_run_id=run_data.parent_run_id,
                        parent_revision_id=run_data.parent_revision_id
                    )
            except Exception as e:
                action = "launch" if auto_start else "create"
                raise RunError(f"Failed to {action} ML-Agents run: {str(e)}") from e

            # Get the created run document
            created_run = self.get_run(run_id)
            if not created_run:
                raise RunError(f"Failed to retrieve created run {run_id}")

            return created_run

        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to create run: {str(e)}") from e
    
    def execute_run(self, run_id: str) -> Dict[str, Any]:
        """
        Execute an existing run that was created but not started.
        
        Args:
            run_id: ID of run to execute
            
        Returns:
            Updated run document with execution information
            
        Raises:
            RunError: If run doesn't exist, is already running, or execution fails
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")
            
            # Check if run can be executed
            current_status = get_effective_run_status(run_id)
            if current_status == "running":
                raise RunError(f"Run {run_id} is already running")
            elif current_status not in ["created", "succeeded", "failed", "stopped"]:
                raise RunError(f"Run {run_id} cannot be executed (status: {current_status})")
            
            # Execute the run
            success = execute_run(run_id)
            if not success:
                raise RunError(f"Failed to execute run {run_id}")
            
            # Return updated run document
            updated_run = self.get_run(run_id)
            return updated_run
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to execute run: {str(e)}") from e
    
    def restart_run(self, run_id: str, mode: str = None) -> Dict[str, Any]:
        """
        Restart an existing run, cleaning execution artifacts but preserving immutable config.

        Args:
            run_id: ID of run to restart
            mode: Optional restart mode - 'resume' or 'force'

        Returns:
            Updated run document with restart information

        Raises:
            RunError: If run doesn't exist or restart fails
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")

            # Restart the run with the specified mode
            success = restart_run(run_id, mode=mode)
            if not success:
                raise RunError(f"Failed to restart run {run_id}")

            # Return updated run document
            updated_run = self.get_run(run_id)
            return updated_run

        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to restart run: {str(e)}") from e
    
    def stop_run(self, run_id: str) -> Dict[str, str]:
        """
        Stop a running ML-Agents process.
        
        Args:
            run_id: ID of run to stop
            
        Returns:
            Dictionary with stop operation result
            
        Raises:
            RunError: If run doesn't exist or stop fails
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")
            
            # Check if run is actually running using centralized status
            current_status = get_effective_run_status(run_id)
            if current_status not in ["running", "pending", "starting"]:
                raise RunError(f"Run {run_id} is not currently active (status: {current_status})")
            
            # Stop the process
            success = stop_run(run_id)
            if not success:
                raise RunError(f"Failed to stop run {run_id}")
            
            return {"message": f"Run {run_id} stopped successfully"}
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to stop run: {str(e)}") from e

    def check_run_health(self, run_id: str) -> Dict[str, Any]:
        """
        Check if a run appears to be stuck or unhealthy.

        Args:
            run_id: ID of run to check

        Returns:
            Dictionary with health status information

        Raises:
            RunError: If check fails
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")

            # Check process health
            health_info = check_process_health(run_id)
            return health_info

        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to check run health: {str(e)}") from e

    def force_kill_run(self, run_id: str) -> bool:
        """
        Force kill a stuck run that won't respond to normal stop.

        Args:
            run_id: ID of run to force kill

        Returns:
            True if successful, False otherwise

        Raises:
            RunError: If run doesn't exist or force kill fails
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")

            # Force kill the process
            success = force_kill_run(run_id)
            return success

        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to force kill run: {str(e)}") from e

    def get_stale_runs(self) -> List[Dict[str, Any]]:
        """
        Get list of all potentially stuck/stale runs.

        Returns:
            List of stale runs with health information

        Raises:
            RunError: If check fails
        """
        try:
            stale_runs = get_stale_runs()
            return stale_runs

        except Exception as e:
            raise RunError(f"Failed to get stale runs: {str(e)}") from e

    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        """
        Get current status for a run in frontend-compatible format.
        
        Args:
            run_id: ID of run
            
        Returns:
            Dictionary with status and timestamps for frontend merge
        """
        try:
            # Get run from database
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")
            
            # Return simple object that frontend can merge
            return {
                "status": run.get("status"),  # Already has live status from get_run()
                "started_at": run.get("started_at"),
                "ended_at": run.get("ended_at")
            }
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to get run status: {str(e)}") from e
    
    def get_run_logs(self, run_id: str, max_lines: int = 20000) -> List[str]:  # High limit to show comprehensive run logs
        """
        Get recent log lines for a run.

        Args:
            run_id: ID of run
            max_lines: Maximum number of lines to return

        Returns:
            List of log lines

        Raises:
            RunError: If run doesn't exist
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")
            
            # Get logs from runner
            logs = get_run_logs(run_id, max_lines)
            return logs
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to get run logs: {str(e)}") from e
    
    def get_run_config(self, run_id: str) -> Dict[str, Any]:
        """
        Get the YAML configuration for a run.
        
        Args:
            run_id: ID of run
            
        Returns:
            Dictionary with YAML content and metadata
            
        Raises:
            RunError: If run doesn't exist or config can't be read
        """
        try:
            # Get run from database
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")
            
            yaml_path = run.get("yaml_path")
            if not yaml_path:
                raise RunError(f"Run {run_id} has no YAML configuration path")
            
            # Read YAML content (convert to absolute path for file access)
            try:
                yaml_content = read_file(yaml_path)  # read_file now handles relative paths
            except FileNotFoundError:
                # Try to use snapshot if file is missing
                yaml_content = run.get("yaml_snapshot", "")
                if not yaml_content:
                    raise RunError(f"YAML configuration not found for run {run_id}")
            
            return {
                "run_id": run_id,
                "yaml_path": yaml_path,  # Return relative path to frontend
                "yaml_content": yaml_content,
                "cli_flags": run.get("cli_flags", {}),
                "cli_flags_snapshot": run.get("cli_flags_snapshot", {})
            }
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to get run config: {str(e)}") from e
    
    def update_run_results(self, run_id: str, results_text: str) -> Dict[str, Any]:
        """
        Update the results text for a run.
        
        Args:
            run_id: ID of run to update
            results_text: Results text to save
            
        Returns:
            Updated run document
            
        Raises:
            RunError: If run doesn't exist or update fails
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")
            
            # Update results
            updates = {
                "results_text": results_text,
                "updated_at": datetime.utcnow()
            }
            
            success = self.runs_db.update_one({"_id": run_id}, updates)
            if not success:
                raise RunError("Failed to update run results")
            
            # Return updated run
            updated_run = self.get_run(run_id)
            return updated_run
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to update run results: {str(e)}") from e
    
    def toggle_run_favorite(self, run_id: str) -> Dict[str, Any]:
        """
        Toggle the favorite status of a run.
        
        Args:
            run_id: ID of run to toggle favorite status
            
        Returns:
            Updated run document with new favorite status
            
        Raises:
            RunError: If run doesn't exist or toggle fails
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")
            
            # Toggle favorite status using database method
            success = self.runs_db.toggle_favorite(run_id)
            if not success:
                raise RunError("Failed to toggle run favorite status")
            
            # Return updated run
            updated_run = self.get_run(run_id)
            return updated_run
            
        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to toggle run favorite: {str(e)}") from e

    def get_tensorboard_url(self, run_id: str) -> Optional[str]:
        """
        Get TensorBoard URL for a run using regex input filtering.

        Args:
            run_id: ID of run to get TensorBoard URL for

        Returns:
            TensorBoard URL string with regexInput parameter, or None if run doesn't exist

        Raises:
            RunError: If run doesn't exist
        """
        try:
            # Verify run exists
            run = self.get_run(run_id)
            if not run:
                raise RunError(f"Run {run_id} not found")

            # Return simplified TensorBoard URL with regex input filtering
            return f"/tb?darkMode=true&runFilter={run_id}#scalars&regexInput={run_id}"

        except RunError:
            raise
        except Exception as e:
            raise RunError(f"Failed to get TensorBoard URL: {str(e)}") from e