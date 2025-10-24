from fastapi import APIRouter, Depends, HTTPException, status, Body, Query
from typing import List, Dict, Any
from auth import get_current_user
from models import ExperimentBody, ExperimentResponse
from services.experiments_service import ExperimentService, ExperimentError
from utils.dependency_checks import check_experiment_dependencies, format_warnings_response
from utils.trash import move_experiment_to_trash
from db import revisions, runs

router = APIRouter(prefix="/experiments", tags=["experiments"])

# Service instance
experiment_service = ExperimentService()


@router.get("", response_model=List[ExperimentResponse])
async def list_experiments(user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    """
    List all experiments, sorted by creation date.
    
    Returns a list of all experiments in the system, ordered by creation date 
    with the most recent first. Each experiment includes basic metadata
    like name, description, tags, and timestamps.
    
    **Example Response:**
    ```json
    [
        {
            "_id": "exp_123",
            "name": "3D Ball Training", 
            "description": "Basic PPO training for 3D Ball environment",
            "tags": ["ppo", "3dball", "basic"],
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z"
        }
    ]
    ```
    """
    return experiment_service.list_experiments()


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    body: ExperimentBody = Body(
        example={
            "name": "New ML Experiment",
            "description": "Training agents for my custom environment",
            "tags": ["custom", "experiment", "v1"]
        }
    ),
    user=Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create a new experiment.
    
    Creates a new experiment container that will hold revisions and runs.
    The experiment name must be unique and will serve as the primary
    identifier for organizing related training runs.
    
    **Request Body:**
    - `name`: Unique name for the experiment (required)
    - `description`: Optional description of the experiment's purpose
    - `tags`: Optional list of tags for categorization
    
    **Returns:** The created experiment with generated ID and timestamps
    """
    try:
        return experiment_service.create_experiment(body)
    except ExperimentError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str, user=Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get a specific experiment by ID.
    
    Retrieves detailed information about a single experiment including
    all metadata, timestamps, and configuration details.
    
    **Path Parameters:**
    - `experiment_id`: Unique identifier of the experiment
    
    **Returns:** Complete experiment details
    
    **Errors:**
    - `404`: Experiment not found
    """
    experiment = experiment_service.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


@router.get("/{experiment_id}/stats")
async def get_experiment_stats(experiment_id: str, user=Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get comprehensive statistics for an experiment.
    
    Returns detailed statistics including revision count, run count,
    run status breakdown, and other metrics useful for understanding
    the experiment's progress and history.
    
    **Path Parameters:**
    - `experiment_id`: Unique identifier of the experiment
    
    **Returns:**
    ```json
    {
        "experiment_id": "exp_123",
        "revision_count": 5,
        "run_count": 23,
        "run_status_breakdown": {
            "completed": 15,
            "failed": 3,
            "running": 2,
            "stopped": 3
        },
        "created_at": "2024-01-01T12:00:00Z",
        "updated_at": "2024-01-02T15:30:00Z"
    }
    ```
    
    **Errors:**
    - `404`: Experiment not found
    """
    try:
        return experiment_service.get_experiment_stats(experiment_id)
    except ExperimentError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{experiment_id}/results")
async def update_experiment_results(experiment_id: str, results_text: str, user=Depends(get_current_user)) -> Dict[str, Any]:
    """
    Update the results text for an experiment.
    
    Allows updating notes or findings about an experiment's overall results.
    This is useful for documenting high-level conclusions and insights.
    
    **Path Parameters:**
    - `experiment_id`: Unique identifier of the experiment
    
    **Query Parameters:**
    - `results_text`: The updated results text content
    
    **Returns:** The updated experiment with new results text
    
    **Errors:**
    - `404`: Experiment not found
    """
    try:
        return experiment_service.update_experiment_results(experiment_id, results_text)
    except ExperimentError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{experiment_id}/favorite")
async def toggle_experiment_favorite(experiment_id: str, user=Depends(get_current_user)) -> Dict[str, Any]:
    """
    Toggle the favorite status of an experiment.
    
    Switches the experiment's favorite status between true and false.
    This is useful for marking important experiments for easy identification.
    
    **Path Parameters:**
    - `experiment_id`: Unique identifier of the experiment
    
    **Returns:** The updated experiment with new favorite status
    
    **Errors:**
    - `404`: Experiment not found
    """
    try:
        return experiment_service.toggle_experiment_favorite(experiment_id)
    except ExperimentError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{experiment_id}/dependencies")
async def check_experiment_dependencies_endpoint(experiment_id: str, user=Depends(get_current_user)) -> Dict[str, Any]:
    """Check dependencies for an experiment before deletion."""
    experiment = experiment_service.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    warnings = check_experiment_dependencies(experiment_id)
    return format_warnings_response(warnings)


@router.delete("/{experiment_id}")
async def delete_experiment(
    experiment_id: str,
    confirmed: bool = Query(False),
    user=Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Delete an experiment by moving it to trash along with all related data.

    First call without confirmed=true will check for dependencies and return warnings.
    If warnings exist, client must call again with confirmed=true to proceed.

    Moves to trash:
    - All associated revisions
    - All associated runs
    - All related files (YAML configs, logs, TensorBoard data)
    - All artifacts and checkpoints

    **Path Parameters:**
    - `experiment_id`: Unique identifier of the experiment to delete

    **Query Parameters:**
    - `confirmed`: Set to true to confirm deletion after reviewing warnings

    **Returns:** Summary of deleted items and warnings

    **Errors:**
    - `404`: Experiment not found
    - `409`: Dependencies exist and confirmed=false
    """
    # Get experiment info
    experiment = experiment_service.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    # Check dependencies
    warnings = check_experiment_dependencies(experiment_id)

    # If not confirmed and there are warnings, return 409 Conflict
    if not confirmed and warnings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Experiment has dependencies. Set confirmed=true to proceed with deletion.",
                **format_warnings_response(warnings)
            }
        )

    # Get all related data counts before deletion
    revision_docs = revisions.find_many({"experiment_id": experiment_id})
    run_docs = runs.find_many({"experiment_id": experiment_id})

    # Move experiment directory to trash
    moved_paths = []
    try:
        moved_paths = move_experiment_to_trash(
            experiment_id,
            experiment.get("name", "unknown")
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to move experiment to trash: {e}")

    # Delete all revisions from database
    revision_count = 0
    for revision in revision_docs:
        if revisions.delete_one({"_id": revision["_id"]}):
            revision_count += 1

    # Delete all runs from database
    run_count = 0
    for run in run_docs:
        if runs.delete_one({"_id": run["_id"]}):
            run_count += 1

    # Delete the experiment from database
    try:
        experiment_deleted = experiment_service.experiments_db.delete_one({"_id": experiment_id})
    except Exception as e:
        raise HTTPException(500, f"Failed to delete experiment from database: {str(e)}")

    return {
        "message": "Experiment moved to trash successfully",
        "deleted_id": experiment_id,
        "moved_to_trash": moved_paths,
        "deleted_counts": {
            "experiments": 1 if experiment_deleted else 0,
            "revisions": revision_count,
            "runs": run_count
        },
        "warnings": format_warnings_response(warnings) if warnings else None
    }
