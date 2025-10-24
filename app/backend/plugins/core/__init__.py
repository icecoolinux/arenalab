"""
Core plugin framework components.

This module provides the infrastructure for the plugin system:
- registry: Plugin registration and discovery
- runner: Plugin execution engine
- api: Plugin API for interacting with experiments/runs
- database: Database collections for plugin data
"""

# Import all core components
from .registry import (
    register_plugin,
    get_plugin,
    get_plugin_function,
    list_plugins,
    get_plugins_info,
    get_plugins_by_scope,
    validate_plugin_settings,
    plugin,  # decorator
    PluginInfo,
    SimplePluginRegistry
)

from .runner import (
    start_plugin,
    stop_plugin,
    get_execution,
    get_executions_for_target,
    get_active_executions,
    cleanup_old_executions,
    PluginStatus,
    PluginExecution,
    SimplePluginRunner
)

from .api import (
    PluginContext,
    PluginAPI,
    SimpleRun
)

from .database import (
    plugin_executions,
    plugin_settings,
    PluginExecutionsCollection,
    PluginSettingsCollection,
    extend_existing_collections,
    add_plugin_to_experiment,
    remove_plugin_from_experiment,
    add_plugin_to_run,
    add_plugin_note,
    mark_revision_as_plugin_created,
    get_plugin_executions_for_target,
    get_experiment_plugins,
    get_run_plugins,
    get_plugin_database
)

__all__ = [
    # Registry
    "register_plugin",
    "get_plugin",
    "get_plugin_function",
    "list_plugins",
    "get_plugins_info",
    "get_plugins_by_scope",
    "validate_plugin_settings",
    "plugin",
    "PluginInfo",
    "SimplePluginRegistry",

    # Runner
    "start_plugin",
    "stop_plugin",
    "get_execution",
    "get_executions_for_target",
    "get_active_executions",
    "cleanup_old_executions",
    "PluginStatus",
    "PluginExecution",
    "SimplePluginRunner",

    # API
    "PluginContext",
    "PluginAPI",
    "SimpleRun",

    # Database
    "plugin_executions",
    "plugin_settings",
    "PluginExecutionsCollection",
    "PluginSettingsCollection",
    "extend_existing_collections",
    "add_plugin_to_experiment",
    "remove_plugin_from_experiment",
    "add_plugin_to_run",
    "add_plugin_note",
    "mark_revision_as_plugin_created",
    "get_plugin_executions_for_target",
    "get_experiment_plugins",
    "get_run_plugins",
    "get_plugin_database"
]
