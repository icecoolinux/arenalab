"""
Simple plugin runner for background execution.

Manages plugin lifecycle, status tracking, and execution.
"""

import threading
import time
import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum

from .api import PluginContext, PluginAPI
from .registry import get_plugin_function, get_plugin
from db import get_db
from .database import plugin_executions

logger = logging.getLogger(__name__)


class PluginStatus(Enum):
    """Plugin execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    PAUSED = "paused"


@dataclass
class PluginExecution:
    """Information about a running plugin instance."""
    plugin_name: str
    target_id: str  # experiment_id, run_id, or revision_id
    scope: str
    settings: Dict[str, Any] = field(default_factory=dict)
    status: PluginStatus = PluginStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    thread: Optional[threading.Thread] = None
    context: Optional[PluginContext] = None
    generation: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "plugin_name": self.plugin_name,
            "target_id": self.target_id,
            "scope": self.scope,
            "settings": self.settings,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "generation": self.generation,
            "metadata": self.metadata
        }


class SimplePluginRunner:
    """Manages execution of simple plugins."""
    
    def __init__(self):
        self._executions: Dict[str, PluginExecution] = {}
        self._lock = threading.Lock()
        self.db = get_db()
    
    def _generate_execution_id(self, plugin_name: str, target_id: str) -> str:
        """Generate unique execution ID."""
        return f"{plugin_name}_{target_id}_{int(time.time())}"
    
    def start_plugin(self, 
                    plugin_name: str,
                    target_id: str,
                    scope: str,
                    settings: Dict[str, Any] = None) -> str:
        """
        Start a plugin execution.
        
        Args:
            plugin_name: Name of the plugin to run
            target_id: ID of target (experiment_id, run_id, revision_id)
            scope: Plugin scope ('experiment', 'run', 'revision')
            settings: Plugin-specific settings
        
        Returns:
            Execution ID for tracking
        """
        plugin_info = get_plugin(plugin_name)
        if not plugin_info:
            raise ValueError(f"Plugin '{plugin_name}' not found")
        
        if plugin_info.scope != scope:
            raise ValueError(f"Plugin '{plugin_name}' scope mismatch. Expected {plugin_info.scope}, got {scope}")
        
        settings = settings or {}
        execution_id = self._generate_execution_id(plugin_name, target_id)
        
        # Create execution record
        execution = PluginExecution(
            plugin_name=plugin_name,
            target_id=target_id,
            scope=scope,
            settings=settings
        )
        
        with self._lock:
            self._executions[execution_id] = execution
        
        # Create context
        context = PluginContext(
            plugin_name=plugin_name,
            scope=scope,
            target_id=target_id,
            settings=settings,
            metadata={}
        )
        execution.context = context
        
        # Start execution thread
        thread = threading.Thread(
            target=self._run_plugin,
            args=(execution_id, plugin_name, context),
            daemon=True
        )
        execution.thread = thread
        thread.start()
        
        logger.info(f"Started plugin '{plugin_name}' execution {execution_id}")
        return execution_id
    
    def _run_plugin(self, execution_id: str, plugin_name: str, context: PluginContext):
        """Run plugin in background thread."""
        execution = self._executions.get(execution_id)
        if not execution:
            return
        
        try:
            # Update status
            execution.status = PluginStatus.RUNNING
            execution.started_at = datetime.now(timezone.utc)
            execution.error_message = None  # Clear any previous error message

            # Save execution to database
            self._save_execution_to_db(execution_id, execution)
            
            # Get plugin function
            plugin_function = get_plugin_function(plugin_name)
            if not plugin_function:
                raise ValueError(f"Plugin function '{plugin_name}' not found")
            
            # Create API
            api = PluginAPI(context)
            
            # Run plugin
            logger.info(f"Executing plugin '{plugin_name}' for {context.scope} {context.target_id}")
            plugin_function(context, api)
            
            # Mark as completed
            execution.status = PluginStatus.COMPLETED
            execution.completed_at = datetime.now(timezone.utc)
            
            logger.info(f"Plugin '{plugin_name}' execution {execution_id} completed successfully")
            
        except Exception as e:
            execution.status = PluginStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.now(timezone.utc)
            
            logger.error(f"Plugin '{plugin_name}' execution {execution_id} failed: {e}")
            logger.debug(f"Plugin error traceback: {traceback.format_exc()}")
        
        finally:
            # Update database
            self._save_execution_to_db(execution_id, execution)
    
    def stop_plugin(self, execution_id: str) -> bool:
        """Stop a running plugin."""
        execution = self._executions.get(execution_id)
        if not execution:
            return False
        
        if execution.context:
            execution.context.should_stop = True
        
        execution.status = PluginStatus.STOPPED
        execution.completed_at = datetime.now(timezone.utc)
        
        self._save_execution_to_db(execution_id, execution)
        logger.info(f"Stopped plugin execution {execution_id}")
        return True
    
    def pause_plugin(self, execution_id: str) -> bool:
        """Pause a running plugin."""
        execution = self._executions.get(execution_id)
        if not execution:
            return False
        
        execution.status = PluginStatus.PAUSED
        # Note: Actual pausing implementation would depend on plugin cooperation
        
        self._save_execution_to_db(execution_id, execution)
        logger.info(f"Paused plugin execution {execution_id}")
        return True
    
    def get_execution(self, execution_id: str) -> Optional[PluginExecution]:
        """Get execution info by ID from memory or database."""
        # First check in-memory executions (for active runs)
        if execution_id in self._executions:
            return self._executions[execution_id]

        # Fall back to database (for completed runs or after restart)
        try:
            doc = plugin_executions.collection.find_one({"execution_id": execution_id})
            if doc:
                # Return the raw document (it will be converted by the API endpoint)
                return doc
        except Exception as e:
            logger.error(f"Error fetching execution from database: {e}")

        return None
    
    def get_executions_for_target(self, target_id: str, scope: str = None) -> List[PluginExecution]:
        """Get all executions for a target (experiment, run, etc)."""
        executions = []
        for execution in self._executions.values():
            if execution.target_id == target_id:
                if scope is None or execution.scope == scope:
                    executions.append(execution)
        return executions
    
    def get_active_executions(self) -> List[PluginExecution]:
        """Get all active (running) executions."""
        return [ex for ex in self._executions.values() 
                if ex.status == PluginStatus.RUNNING]
    
    def cleanup_completed_executions(self, max_age_hours: int = 24):
        """Clean up old completed executions."""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        
        to_remove = []
        for exec_id, execution in self._executions.items():
            if (execution.status in [PluginStatus.COMPLETED, PluginStatus.FAILED, PluginStatus.STOPPED] 
                and execution.completed_at 
                and execution.completed_at.timestamp() < cutoff_time):
                to_remove.append(exec_id)
        
        with self._lock:
            for exec_id in to_remove:
                del self._executions[exec_id]
        
        logger.info(f"Cleaned up {len(to_remove)} old plugin executions")
    
    def _save_execution_to_db(self, execution_id: str, execution: PluginExecution):
        """Save execution state to database."""
        try:
            doc = {
                "execution_id": execution_id,
                "plugin_name": execution.plugin_name,
                "target_id": execution.target_id,
                "scope": execution.scope,
                "status": execution.status.value,
                "settings": execution.settings,
                "started_at": execution.started_at,
                "completed_at": execution.completed_at,
                "generation": execution.generation,
                "metadata": execution.metadata,
                "updated_at": datetime.now(timezone.utc)
            }

            # Only include error_message if it's not None
            if execution.error_message is not None:
                doc["error_message"] = execution.error_message

            # Build update operation
            update_op = {"$set": doc}

            # If error_message is None, explicitly unset it in the database
            if execution.error_message is None:
                update_op["$unset"] = {"error_message": ""}

            # Upsert to plugin_executions collection
            plugin_executions.collection.update_one(
                {"execution_id": execution_id},
                update_op,
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error saving plugin execution to database: {e}")
    
    def load_executions_from_db(self):
        """Load active executions from database (for service restart)."""
        try:
            active_docs = list(plugin_executions.collection.find({
                "status": {"$in": ["running", "pending"]}
            }))
            
            for doc in active_docs:
                # Mark as failed if they were running when service stopped
                plugin_executions.collection.update_one(
                    {"execution_id": doc["execution_id"]},
                    {"$set": {
                        "status": "failed",
                        "error_message": "Service was restarted",
                        "completed_at": datetime.now(timezone.utc)
                    }}
                )
            
            logger.info(f"Marked {len(active_docs)} orphaned plugin executions as failed")
            
        except Exception as e:
            logger.error(f"Error loading plugin executions from database: {e}")


# Global runner instance
_global_runner = SimplePluginRunner()


def start_plugin(plugin_name: str, target_id: str, scope: str, settings: Dict[str, Any] = None) -> str:
    """Start a plugin execution."""
    return _global_runner.start_plugin(plugin_name, target_id, scope, settings)


def stop_plugin(execution_id: str) -> bool:
    """Stop a plugin execution."""
    return _global_runner.stop_plugin(execution_id)


def get_execution(execution_id: str) -> Optional[PluginExecution]:
    """Get execution info."""
    return _global_runner.get_execution(execution_id)


def get_executions_for_target(target_id: str, scope: str = None) -> List[PluginExecution]:
    """Get executions for a target."""
    return _global_runner.get_executions_for_target(target_id, scope)


def get_active_executions() -> List[PluginExecution]:
    """Get all active executions."""
    return _global_runner.get_active_executions()


def cleanup_old_executions(max_age_hours: int = 24):
    """Clean up old executions."""
    return _global_runner.cleanup_completed_executions(max_age_hours)


# Initialize runner on import
_global_runner.load_executions_from_db()