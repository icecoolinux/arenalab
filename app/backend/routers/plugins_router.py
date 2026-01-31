"""
Plugins router for managing plugin discovery, configuration, and execution.

Provides endpoints for plugin discovery, execution management, and status monitoring.

Plugin Execution Identification:
    Each plugin execution is uniquely identified by an execution_id, which is:
    - Generated when a plugin starts via /plugins/execute
    - Used consistently across all execution-specific endpoints
    - Persists in MongoDB for tracking across application restarts
    - Independent of the target resource (run, revision, or experiment)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime

from auth import get_current_user
from plugins import get_plugins_info, get_plugin, validate_plugin_settings
from plugins import (
    start_plugin, stop_plugin, get_execution,
    get_active_executions
)
from plugins.core.database import plugin_executions, plugin_settings, get_plugin_logs, get_plugin_logs_count

router = APIRouter(prefix="/plugins", tags=["plugins"])


def _serialize_execution(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB document to JSON-serializable dict."""
    serialized = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, dict):
            serialized[key] = _serialize_execution(value)
        elif isinstance(value, list):
            serialized[key] = [_serialize_execution(item) if isinstance(item, dict) else item for item in value]
        else:
            serialized[key] = value
    return serialized


class PluginExecutionRequest(BaseModel):
    """Request to start a plugin execution."""
    plugin_name: str
    target_id: str
    scope: str
    settings: Dict[str, Any] = {}


class PluginSettingsUpdate(BaseModel):
    """Request to update user plugin settings."""
    settings: Dict[str, Any]


@router.get("")
async def list_plugins(
    scope: Optional[str] = Query(None, description="Filter by scope (experiment, run, revision)"),
    user=Depends(get_current_user)
):
    """
    List all available plugins.

    Args:
        scope: Optional scope filter

    Returns:
        List of plugin information
    """
    plugins = get_plugins_info(scope)
    return {"plugins": plugins}


@router.post("/execute")
async def start_plugin_execution(
    request: PluginExecutionRequest,
    user=Depends(get_current_user)
):
    """
    Start a plugin execution.

    Creates a new plugin execution with a unique execution_id that will be used
    to track this specific execution throughout its lifecycle.

    Args:
        request: Plugin execution parameters (plugin_name, target_id, scope, settings)

    Returns:
        execution_id: Unique identifier for this plugin execution
        status: Current execution status
        plugin_name: Name of the plugin being executed
        target_id: ID of the resource being processed
    """
    # Validate plugin exists
    plugin_info = get_plugin(request.plugin_name)
    if not plugin_info:
        raise HTTPException(status_code=404, detail=f"Plugin '{request.plugin_name}' not found")
    
    # Validate scope matches
    if plugin_info.scope != request.scope:
        raise HTTPException(
            status_code=400, 
            detail=f"Plugin scope mismatch. Expected '{plugin_info.scope}', got '{request.scope}'"
        )
    
    # Validate settings
    if not validate_plugin_settings(request.plugin_name, request.settings):
        raise HTTPException(status_code=400, detail="Invalid plugin settings")
    
    try:
        execution_id = start_plugin(
            plugin_name=request.plugin_name,
            target_id=request.target_id,
            scope=request.scope,
            settings=request.settings
        )
        
        return {
            "execution_id": execution_id,
            "status": "started",
            "plugin_name": request.plugin_name,
            "target_id": request.target_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start plugin: {str(e)}")


@router.get("/executions")
async def list_plugin_executions(
    target_id: Optional[str] = Query(None, description="Filter by target ID"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
    active_only: bool = Query(False, description="Show only active executions"),
    user=Depends(get_current_user)
):
    """
    List plugin executions.

    Args:
        target_id: Optional target ID filter
        scope: Optional scope filter
        active_only: Show only active executions

    Returns:
        List of executions
    """
    if active_only:
        executions = get_active_executions()
        if target_id:
            executions = [ex for ex in executions if ex.target_id == target_id]
        if scope:
            executions = [ex for ex in executions if ex.scope == scope]
    else:
        # Get all executions from database (persistent across restarts)
        query = {}
        if target_id:
            query["target_id"] = target_id
        if scope:
            query["scope"] = scope

        # Use collection directly for sorting
        cursor = plugin_executions.collection.find(query).sort("started_at", -1).limit(100)
        executions = list(cursor)

    return {"executions": [_serialize_execution(ex) if isinstance(ex, dict) else ex.to_dict() for ex in executions]}


@router.get("/executions/{execution_id}")
async def get_plugin_execution(
    execution_id: str,  # Plugin execution is uniquely identified by execution_id
    user=Depends(get_current_user)
):
    """
    Get information about a specific plugin execution.

    Each plugin execution is uniquely identified by its execution_id across
    all API operations. This endpoint retrieves the complete execution state.

    Args:
        execution_id: Unique ID of the plugin execution

    Returns:
        execution: Complete execution details including status, timestamps, and configuration
    """
    execution = get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    # Handle both PluginExecution objects and database documents
    if hasattr(execution, 'to_dict'):
        return {"execution": execution.to_dict()}
    elif isinstance(execution, dict):
        return {"execution": _serialize_execution(execution)}
    else:
        return {"execution": execution}


@router.get("/executions/{execution_id}/logs")
async def get_execution_logs(
    execution_id: str,  # Plugin execution is uniquely identified by execution_id
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs to return"),
    skip: int = Query(0, ge=0, description="Number of logs to skip (for pagination)"),
    user=Depends(get_current_user)
):
    """
    Get logs for a plugin execution.

    Each plugin execution is uniquely identified by its execution_id, which is
    generated when the plugin starts and persists throughout its lifecycle.

    Args:
        execution_id: Unique ID of the plugin execution
        level: Optional log level filter
        limit: Maximum number of logs to return (1-1000)
        skip: Number of logs to skip for pagination

    Returns:
        List of log entries with metadata
    """
    # Verify execution exists
    # Plugin executions are identified by execution_id across all operations
    execution_doc = plugin_executions.collection.find_one(
        {"execution_id": execution_id}
    )

    if not execution_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )

    # Get logs for this specific plugin execution
    logs = get_plugin_logs(execution_id, level, limit, skip)
    total = get_plugin_logs_count(execution_id, level)

    # Serialize logs
    serialized_logs = [_serialize_execution(log) for log in logs]

    return {
        "execution_id": execution_id,
        "plugin_name": execution_doc.get("plugin_name"),
        "target_id": execution_doc.get("target_id"),
        "logs": serialized_logs,
        "total": total,
        "limit": limit,
        "skip": skip,
        "level_filter": level
    }


@router.post("/executions/{execution_id}/stop")
async def stop_plugin_execution(
    execution_id: str,  # Plugin execution is uniquely identified by execution_id
    user=Depends(get_current_user)
):
    """
    Stop a running plugin execution.

    Plugin executions are identified by their unique execution_id throughout
    their lifecycle. This endpoint uses execution_id to stop the specific
    plugin execution instance.

    Args:
        execution_id: Unique ID of the plugin execution to stop

    Returns:
        status: Confirmation that execution was stopped
        execution_id: The stopped execution's ID
    """
    success = stop_plugin(execution_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    return {"status": "stopped", "execution_id": execution_id}


@router.put("/settings/{plugin_name}")
async def update_user_plugin_settings(
    plugin_name: str,
    request: PluginSettingsUpdate,
    user=Depends(get_current_user)
):
    """
    Update user settings for a plugin.
    
    Args:
        plugin_name: Name of the plugin
        request: New settings
        
    Returns:
        Success status
    """
    # Validate plugin exists
    plugin_info = get_plugin(plugin_name)
    if not plugin_info:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")
    
    # Validate settings
    if not validate_plugin_settings(plugin_name, request.settings):
        raise HTTPException(status_code=400, detail="Invalid plugin settings")
    
    success = plugin_settings.update_user_plugin_settings(
        user["id"], plugin_name, request.settings
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update settings")
    
    return {"status": "updated", "plugin_name": plugin_name}


@router.get("/settings/{plugin_name}")
async def get_user_plugin_settings(
    plugin_name: str,
    user=Depends(get_current_user)
):
    """
    Get user settings for a plugin.

    Args:
        plugin_name: Name of the plugin

    Returns:
        User settings for the plugin
    """
    plugin_info = get_plugin(plugin_name)
    if not plugin_info:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    settings = plugin_settings.get_user_plugin_settings(user["id"], plugin_name)

    return {
        "plugin_name": plugin_name,
        "settings": settings,
        "schema": plugin_info.settings_schema
    }


@router.get("/{plugin_name}")
async def get_plugin_details(
    plugin_name: str,
    user=Depends(get_current_user)
):
    """
    Get detailed information about a specific plugin.

    Args:
        plugin_name: Name of the plugin

    Returns:
        Plugin details including schema and settings
    """
    plugin_info = get_plugin(plugin_name)
    if not plugin_info:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    return {
        "plugin": plugin_info.to_dict(),
        "user_settings": plugin_settings.get_user_plugin_settings(user["id"], plugin_name)
    }