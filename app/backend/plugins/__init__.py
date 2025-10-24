"""
Ultra-Simple Plugin System for ArenaLab.

Write a function, control experiments. That's it!

## How to Add a Plugin

1. Create a new file in the plugins/ directory with a name ending in `_plugin.py`
2. Write a function that takes (context, api) parameters
3. Register it with the @register_plugin decorator
4. Done! The plugin will be auto-discovered and available.

Example plugin file (my_awesome_plugin.py):
```python
from .core import register_plugin

@register_plugin("my_plugin", "experiment", "My awesome plugin")
def my_plugin(context, api):
    # Create a run
    run = api.create_run({"learning_rate": 0.001})

    # Wait for completion
    api.wait_for_completion([run])

    # Create revision with best results
    api.create_revision_with_hyperparameters(
        name="Auto-Generated",
        hyperparameters=run.config
    )
```

That's literally it. No classes, no abstract methods, no complexity.
Just drop the file in the plugins/ directory and it works!

To remove a plugin, simply delete its file.
"""

import os
import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Import and export all core components
from .core import (
    register_plugin,
    get_plugin,
    get_plugin_function,
    list_plugins,
    get_plugins_info,
    get_plugins_by_scope,
    validate_plugin_settings,
    plugin,  # decorator
    start_plugin,
    stop_plugin,
    get_execution,
    get_executions_for_target,
    get_active_executions,
    PluginContext,
    PluginAPI
)

# Also initialize database schema
from .core import database

# Auto-discover and load all plugin files
def _discover_and_load_plugins():
    """
    Auto-discover and load all plugin files in the plugins directory.

    Plugin files must:
    - End with _plugin.py
    - Be in the plugins/ directory (not in subdirectories like core/)
    """
    plugins_dir = Path(__file__).parent
    plugin_files = list(plugins_dir.glob("*_plugin.py"))

    loaded_count = 0
    for plugin_file in plugin_files:
        plugin_module_name = plugin_file.stem  # filename without .py
        try:
            # Import the plugin module (this will trigger the @register_plugin decorator)
            importlib.import_module(f".{plugin_module_name}", package="plugins")
            loaded_count += 1
            logger.info(f"Loaded plugin module: {plugin_module_name}")
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_module_name}: {e}")
            logger.exception(e)

    logger.info(f"Plugin auto-discovery complete: loaded {loaded_count} plugin files")


# Run auto-discovery on import
_discover_and_load_plugins()

# Export the ultra-simple interface
__all__ = [
    # Plugin registration (the only thing developers need)
    "plugin",           # @plugin("name", "scope", "description") decorator
    "register_plugin",  # Manual registration if needed

    # Plugin discovery (for API/frontend)
    "list_plugins",
    "get_plugins_info",
    "get_plugin",

    # Plugin execution (for runtime)
    "start_plugin",
    "stop_plugin",
    "get_execution",
    "get_executions_for_target",
    "get_active_executions",

    # Core objects (for advanced users)
    "PluginContext",
    "PluginAPI"
]
