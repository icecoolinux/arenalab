"""
Database schema extensions for plugin support.

Extends the existing database with plugin-related collections and adds
plugin fields to existing collections.
"""

import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pymongo import ASCENDING
from db import BaseCollection, get_db


class PluginExecutionsCollection(BaseCollection):
    """Collection for tracking plugin execution state."""
    
    def __init__(self):
        super().__init__("plugin_executions")
        # Create indexes
        self.collection.create_index([("execution_id", ASCENDING)], unique=True)
        self.collection.create_index([("target_id", ASCENDING)])
        self.collection.create_index([("plugin_name", ASCENDING)])
        self.collection.create_index([("status", ASCENDING)])
    
    def find_by_target(self, target_id: str, scope: str = None) -> List[Dict[str, Any]]:
        """Find all executions for a target."""
        query = {"target_id": target_id}
        if scope:
            query["scope"] = scope
        return self.find_many(query)
    
    def find_active(self) -> List[Dict[str, Any]]:
        """Find all active (running) executions."""
        return self.find_many({"status": {"$in": ["running", "pending"]}})
    
    def update_status(self, execution_id: str, status: str, 
                     error_message: str = None, metadata: Dict[str, Any] = None) -> bool:
        """Update execution status."""
        update_doc = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        if error_message:
            update_doc["error_message"] = error_message
        if metadata:
            update_doc["metadata"] = metadata
        if status in ["completed", "failed", "stopped"]:
            update_doc["completed_at"] = datetime.utcnow()
        
        result = self.collection.update_one(
            {"execution_id": execution_id},
            {"$set": update_doc}
        )
        return result.modified_count > 0


class PluginSettingsCollection(BaseCollection):
    """Collection for user plugin settings and preferences."""
    
    def __init__(self):
        super().__init__("plugin_settings")
        # Create indexes
        self.collection.create_index([("user_id", ASCENDING)])
        self.collection.create_index([("plugin_name", ASCENDING)])
    
    def get_user_plugin_settings(self, user_id: str, plugin_name: str) -> Dict[str, Any]:
        """Get plugin settings for a user."""
        doc = self.find_one({"user_id": user_id, "plugin_name": plugin_name})
        return doc.get("settings", {}) if doc else {}
    
    def update_user_plugin_settings(self, user_id: str, plugin_name: str, 
                                  settings: Dict[str, Any]) -> bool:
        """Update plugin settings for a user."""
        result = self.collection.update_one(
            {"user_id": user_id, "plugin_name": plugin_name},
            {
                "$set": {
                    "settings": settings,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return result.upserted_id is not None or result.modified_count > 0
    
    def get_enabled_plugins(self, user_id: str, scope: str = None) -> List[str]:
        """Get list of enabled plugins for a user."""
        query = {"user_id": user_id, "settings.enabled": True}
        if scope:
            query["scope"] = scope
        
        docs = self.find_many(query)
        return [doc["plugin_name"] for doc in docs]


def extend_existing_collections():
    """Extend existing collections with plugin-related fields."""
    db = get_db()
    
    # Add plugin-related indexes to existing collections
    try:
        # Experiments collection - for experiment-level plugins
        db.experiments.create_index([("enabled_plugins", ASCENDING)])
        
        # Runs collection - for run-level plugins and plugin-generated notes
        db.runs.create_index([("enabled_plugins", ASCENDING)])
        
        # Revisions collection - for plugin-generated revisions
        db.revisions.create_index([("created_by_plugin", ASCENDING)])
        
    except Exception as e:
        # Indexes might already exist
        pass


# Extension functions for existing collections
def add_plugin_to_experiment(experiment_id: str, plugin_name: str, settings: Dict[str, Any] = None):
    """Add a plugin to an experiment."""
    from db import experiments
    
    plugin_config = {
        "name": plugin_name,
        "enabled": True,
        "settings": settings or {},
        "enabled_at": datetime.utcnow()
    }
    
    experiments.collection.update_one(
        {"_id": experiment_id},
        {
            "$push": {"enabled_plugins": plugin_config},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )


def remove_plugin_from_experiment(experiment_id: str, plugin_name: str):
    """Remove a plugin from an experiment."""
    from db import experiments
    
    experiments.collection.update_one(
        {"_id": experiment_id},
        {
            "$pull": {"enabled_plugins": {"name": plugin_name}},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )


def add_plugin_to_run(run_id: str, plugin_name: str, settings: Dict[str, Any] = None):
    """Add a plugin to a run."""
    from db import runs
    
    plugin_config = {
        "name": plugin_name,
        "enabled": True,
        "settings": settings or {},
        "enabled_at": datetime.utcnow()
    }
    
    runs.collection.update_one(
        {"_id": run_id},
        {
            "$push": {"enabled_plugins": plugin_config},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )


def add_plugin_note(target_id: str, target_type: str, plugin_name: str, note: str):
    """Add a plugin-generated note to experiment or run."""
    from db import experiments, runs
    
    note_doc = {
        "plugin_name": plugin_name,
        "content": note,
        "timestamp": datetime.utcnow()
    }
    
    if target_type == "experiment":
        experiments.collection.update_one(
            {"_id": target_id},
            {"$push": {"plugin_notes": note_doc}}
        )
    elif target_type == "run":
        runs.collection.update_one(
            {"_id": target_id},
            {"$push": {"plugin_notes": note_doc}}
        )


def mark_revision_as_plugin_created(revision_id: str, plugin_name: str, 
                                  source_data: Dict[str, Any] = None):
    """Mark a revision as created by a plugin."""
    from db import revisions
    
    update_doc = {
        "created_by_plugin": plugin_name,
        "plugin_metadata": source_data or {}
    }
    
    revisions.collection.update_one(
        {"_id": revision_id},
        {"$set": update_doc}
    )


def get_plugin_executions_for_target(target_id: str, scope: str = None) -> List[Dict[str, Any]]:
    """Get all plugin executions for a target."""
    return plugin_executions.find_by_target(target_id, scope)


def get_experiment_plugins(experiment_id: str) -> List[Dict[str, Any]]:
    """Get enabled plugins for an experiment."""
    from db import experiments
    
    experiment = experiments.find_one({"_id": experiment_id})
    return experiment.get("enabled_plugins", []) if experiment else []


def get_run_plugins(run_id: str) -> List[Dict[str, Any]]:
    """Get enabled plugins for a run."""
    from db import runs
    
    run = runs.find_one({"_id": run_id})
    return run.get("enabled_plugins", []) if run else []


# Collection instances
plugin_executions = PluginExecutionsCollection()
plugin_settings = PluginSettingsCollection()

# Initialize database extensions
extend_existing_collections()


# Export database extension function for use in main db module
def get_plugin_database():
    """Get plugin-related database collections."""
    return {
        "plugin_executions": plugin_executions,
        "plugin_settings": plugin_settings
    }