from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from fastapi.websockets import WebSocket
from auth import get_current_user
from models import RunBody
from services.runs_service import RunService, RunError
from utils.file_tools import LogStreamer, ensure_workspace_path
from utils.dependency_checks import check_run_dependencies, format_warnings_response
from utils.trash import move_run_to_trash
from db import runs, revisions, experiments

router = APIRouter(prefix="/runs", tags=["runs"])

# Service instance
run_service = RunService()


@router.get("")
async def list_runs(
    revision_id: str | None = None, 
    experiment_id: str | None = None,
    status: str | None = None, 
    limit: int = 100, 
    offset: int = 0, 
    user=Depends(get_current_user)
):
    """List runs with optional filtering and pagination."""
    try:
        return run_service.list_runs(revision_id, experiment_id, status, limit, offset)
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_run(body: RunBody, auto_start: bool = True, user=Depends(get_current_user)):
    """Create a new ML-Agents run, optionally starting execution immediately."""
    try:
        return run_service.create_run(body, auto_start=auto_start)
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{run_id}")
async def get_run(run_id: str, user=Depends(get_current_user)):
    """Get a specific run by ID."""
    run = run_service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/status")
async def get_run_status(run_id: str, user=Depends(get_current_user)):
    """Get current status and metrics for a run."""
    try:
        return run_service.get_run_status(run_id)
    except RunError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/logs")
async def get_run_logs(run_id: str, max_lines: int = 20000, user=Depends(get_current_user)):  # High limit to show comprehensive run logs
    """Get recent log lines for a run."""
    try:
        logs = run_service.get_run_logs(run_id, max_lines)
        # Join log lines with newlines and return as plain text
        return Response(content="\n".join(logs), media_type="text/plain")
    except RunError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/config")
async def get_run_config(run_id: str, user=Depends(get_current_user)):
    """Get the YAML configuration for a run."""
    try:
        return run_service.get_run_config(run_id)
    except RunError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/execute")
async def execute_run(run_id: str, user=Depends(get_current_user)):
    """Execute an existing run that was created but not started."""
    try:
        return run_service.execute_run(run_id)
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/restart")
async def restart_run(
    run_id: str,
    mode: str = Query(None, description="Restart mode: 'resume' or 'force'"),
    user=Depends(get_current_user)
):
    """Restart an existing run with the same immutable configuration.

    Args:
        run_id: ID of the run to restart
        mode: Optional restart mode - 'resume' (--resume) or 'force' (--force)
    """
    try:
        return run_service.restart_run(run_id, mode=mode)
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, user=Depends(get_current_user)):
    """Stop a running ML-Agents process."""
    try:
        return run_service.stop_run(run_id)
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{run_id}/health")
async def check_run_health(run_id: str, user=Depends(get_current_user)):
    """Check if a run appears to be stuck or unhealthy."""
    try:
        return run_service.check_run_health(run_id)
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/force-kill")
async def force_kill_run(run_id: str, user=Depends(get_current_user)):
    """Force kill a stuck run that won't respond to normal stop."""
    try:
        success = run_service.force_kill_run(run_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to force kill run")
        return {"success": True, "message": f"Run {run_id} force killed"}
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stale/check")
async def check_stale_runs(user=Depends(get_current_user)):
    """Get list of all potentially stuck/stale runs."""
    try:
        return run_service.get_stale_runs()
    except RunError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{run_id}/results")
async def update_run_results(run_id: str, results_text: str, user=Depends(get_current_user)):
    """Update the results text for a run."""
    try:
        return run_service.update_run_results(run_id, results_text)
    except RunError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{run_id}/favorite")
async def toggle_run_favorite(run_id: str, user=Depends(get_current_user)):
    """Toggle the favorite status of a run."""
    try:
        return run_service.toggle_run_favorite(run_id)
    except RunError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/tensorboard")
async def get_run_tensorboard_url(run_id: str, user=Depends(get_current_user)):
    """Get TensorBoard URL for a run if data exists."""
    try:
        tensorboard_url = run_service.get_tensorboard_url(run_id)
        return {"url": tensorboard_url, "available": tensorboard_url is not None}
    except RunError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/logs/stream")
async def stream_run_logs(run_id: str, user=Depends(get_current_user)):
    """Stream run logs in real-time."""
    try:
        # Verify run exists first
        run = run_service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        
        stdout_log_path = run.get("stdout_log_path")
        if not stdout_log_path:
            raise HTTPException(status_code=404, detail="Log file not available")
        
        # Convert relative path to absolute for file access
        abs_stdout_log_path = ensure_workspace_path(stdout_log_path)
        
        # Create log streamer with status checker
        def is_run_active():
            status_info = run_service.get_run_status(run_id)
            return status_info.get("is_active", False)
        
        streamer = LogStreamer(abs_stdout_log_path, status_checker=is_run_active)
        return StreamingResponse(streamer.stream_generator(), media_type="text/plain")
        
    except RunError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.websocket("/{run_id}/logs/ws")
async def websocket_run_logs(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()

    try:
        # Verify run exists
        run = run_service.get_run(run_id)
        if not run:
            await websocket.send_text("Error: Run not found")
            await websocket.close()
            return

        stdout_log_path = run.get("stdout_log_path")
        if not stdout_log_path:
            await websocket.send_text("Error: Log file not available")
            await websocket.close()
            return

        # Convert relative path to absolute for file access
        abs_stdout_log_path = ensure_workspace_path(stdout_log_path)

        # Create status checker
        def is_run_active():
            try:
                status_info = run_service.get_run_status(run_id)
                return status_info.get("is_active", False)
            except:
                return False

        # Stream logs via WebSocket
        streamer = LogStreamer(abs_stdout_log_path, status_checker=is_run_active)
        await streamer.stream_websocket(websocket)

    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")
    finally:
        await websocket.close()


@router.get("/{run_id}/dependencies")
async def check_run_dependencies_endpoint(run_id: str, user=Depends(get_current_user)):
    """Check dependencies for a run before deletion."""
    run = run_service.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    warnings = check_run_dependencies(run_id)
    return format_warnings_response(warnings)


@router.delete("/{run_id}")
async def delete_run(run_id: str, confirmed: bool = Query(False), user=Depends(get_current_user)):
    """
    Delete a run by moving it to trash.

    First call without confirmed=true will check for dependencies and return warnings.
    If warnings exist, client must call again with confirmed=true to proceed.
    """
    # Get run info
    run = run_service.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    # Get experiment and revision info for directory structure
    revision = revisions.find_one({"_id": run.get("revision_id")})
    experiment = experiments.find_one({"_id": run.get("experiment_id")})

    experiment_name = experiment.get("name", "unknown") if experiment else "unknown"
    revision_name = revision.get("name", "unnamed") if revision else "unnamed"

    # Check dependencies
    warnings = check_run_dependencies(run_id)

    # If not confirmed and there are warnings, return 409 Conflict
    if not confirmed and warnings:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Run has dependencies. Set confirmed=true to proceed with deletion.",
                **format_warnings_response(warnings)
            }
        )

    # Stop the run if it's active
    if run.get("status") in ["running", "pending"]:
        try:
            run_service.stop_run(run_id)
        except:
            pass  # Best effort

    # Move to trash
    moved_paths = []
    try:
        moved_paths = move_run_to_trash(
            run.get("experiment_id"),
            run.get("revision_id"),
            run_id,
            experiment_name,
            revision_name,
            run.get("name", "unnamed")
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to move run to trash: {e}")

    # Delete from database
    deleted = runs.delete_one({"_id": run_id})
    if not deleted:
        raise HTTPException(500, "Failed to delete run from database")

    return {
        "message": "Run moved to trash successfully",
        "deleted_id": run_id,
        "moved_to_trash": moved_paths,
        "warnings": format_warnings_response(warnings) if warnings else None
    }