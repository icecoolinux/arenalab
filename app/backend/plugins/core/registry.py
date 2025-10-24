"""
Simple function-based plugin registry.

Plugins are just functions that receive (context, api) parameters.
No classes, no complex inheritance - just simple functions.
"""

import logging
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Information about a registered plugin."""
    name: str
    function: Callable
    scope: str  # 'experiment', 'run', 'revision'
    description: str
    version: str = "1.0.0"
    author: str = "unknown"
    settings_schema: Dict[str, Any] = field(default_factory=dict)
    enabled_by_default: bool = False
    tags: List[str] = field(default_factory=list)
    icon: str = "⚙️"  # Default icon emoji

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "scope": self.scope,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "settings_schema": self.settings_schema,
            "enabled_by_default": self.enabled_by_default,
            "tags": self.tags,
            "icon": self.icon
        }


class SimplePluginRegistry:
    """Simple registry for function-based plugins."""
    
    def __init__(self):
        self._plugins: Dict[str, PluginInfo] = {}
    
    def register(self,
                 name: str,
                 plugin_function: Callable,
                 scope: str,
                 description: str = "",
                 version: str = "1.0.0",
                 author: str = "unknown",
                 settings_schema: Dict[str, Any] = None,
                 enabled_by_default: bool = False,
                 tags: List[str] = None,
                 icon: str = "⚙️") -> None:
        """
        Register a plugin function.

        Args:
            name: Unique plugin identifier
            plugin_function: Function that takes (context, api) parameters
            scope: 'experiment', 'run', or 'revision'
            description: Human-readable description
            version: Plugin version
            author: Plugin author
            settings_schema: JSON schema for plugin settings
            enabled_by_default: Whether plugin is enabled by default
            tags: List of tags for categorization
            icon: Icon emoji for UI display
        """
        if name in self._plugins:
            logger.warning(f"Plugin '{name}' is already registered, overwriting")

        if scope not in ['experiment', 'run', 'revision']:
            raise ValueError(f"Invalid scope '{scope}'. Must be 'experiment', 'run', or 'revision'")

        # Validate function signature
        if not callable(plugin_function):
            raise ValueError(f"Plugin '{name}' must be a callable function")

        plugin_info = PluginInfo(
            name=name,
            function=plugin_function,
            scope=scope,
            description=description,
            version=version,
            author=author,
            settings_schema=settings_schema or {},
            enabled_by_default=enabled_by_default,
            tags=tags or [],
            icon=icon
        )

        self._plugins[name] = plugin_info
        logger.info(f"Registered plugin '{name}' (scope: {scope})")
    
    def unregister(self, name: str) -> bool:
        """Remove a plugin from registry."""
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Unregistered plugin '{name}'")
            return True
        return False
    
    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        """Get plugin info by name."""
        return self._plugins.get(name)
    
    def list_plugins(self, scope: str = None) -> List[str]:
        """List all registered plugin names, optionally filtered by scope."""
        if scope:
            return [name for name, info in self._plugins.items() if info.scope == scope]
        return list(self._plugins.keys())
    
    def get_plugins_info(self, scope: str = None) -> List[Dict[str, Any]]:
        """Get detailed info about all plugins."""
        plugins = self._plugins.values()
        if scope:
            plugins = [info for info in plugins if info.scope == scope]
        return [info.to_dict() for info in plugins]
    
    def get_plugin_function(self, name: str) -> Optional[Callable]:
        """Get the actual plugin function."""
        plugin_info = self.get_plugin(name)
        return plugin_info.function if plugin_info else None
    
    def get_plugins_by_scope(self, scope: str) -> Dict[str, PluginInfo]:
        """Get all plugins for a specific scope."""
        return {name: info for name, info in self._plugins.items() if info.scope == scope}
    
    def validate_plugin_settings(self, plugin_name: str, settings: Dict[str, Any]) -> bool:
        """Validate settings against plugin schema (basic validation)."""
        plugin_info = self.get_plugin(plugin_name)
        if not plugin_info:
            return False
        
        schema = plugin_info.settings_schema
        if not schema:
            return True  # No schema means any settings are valid
        
        # Basic validation - in production, use jsonschema library
        for key, spec in schema.items():
            if spec.get("required", False) and key not in settings:
                return False
            
            if key in settings:
                expected_type = spec.get("type")
                value = settings[key]
                
                if expected_type == "int" and not isinstance(value, int):
                    return False
                elif expected_type == "float" and not isinstance(value, (int, float)):
                    return False
                elif expected_type == "string" and not isinstance(value, str):
                    return False
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return False
        
        return True


# Global registry instance
_global_registry = SimplePluginRegistry()


def register_plugin(name: str,
                   scope: str,
                   description: str = "",
                   version: str = "1.0.0",
                   author: str = "unknown",
                   settings_schema: Dict[str, Any] = None,
                   enabled_by_default: bool = False,
                   tags: List[str] = None,
                   icon: str = "⚙️"):
    """Decorator to register a plugin in the global registry."""
    def decorator(plugin_function: Callable):
        _global_registry.register(
            name=name,
            plugin_function=plugin_function,
            scope=scope,
            description=description,
            version=version,
            author=author,
            settings_schema=settings_schema,
            enabled_by_default=enabled_by_default,
            tags=tags,
            icon=icon
        )
        return plugin_function
    return decorator


def get_plugin(name: str) -> Optional[PluginInfo]:
    """Get plugin info from global registry."""
    return _global_registry.get_plugin(name)


def get_plugin_function(name: str) -> Optional[Callable]:
    """Get plugin function from global registry."""
    return _global_registry.get_plugin_function(name)


def list_plugins(scope: str = None) -> List[str]:
    """List all registered plugins."""
    return _global_registry.list_plugins(scope)


def get_plugins_info(scope: str = None) -> List[Dict[str, Any]]:
    """Get detailed info about all plugins."""
    return _global_registry.get_plugins_info(scope)


def get_plugins_by_scope(scope: str) -> Dict[str, PluginInfo]:
    """Get all plugins for a specific scope."""
    return _global_registry.get_plugins_by_scope(scope)


def validate_plugin_settings(plugin_name: str, settings: Dict[str, Any]) -> bool:
    """Validate plugin settings against schema."""
    return _global_registry.validate_plugin_settings(plugin_name, settings)


# Decorator for easy plugin registration
def plugin(name: str,
          scope: str,
          description: str = "",
          version: str = "1.0.0",
          author: str = "unknown",
          settings_schema: Dict[str, Any] = None,
          enabled_by_default: bool = False,
          tags: List[str] = None,
          icon: str = "⚙️"):
    """
    Decorator for registering plugins.

    Usage:
        @plugin("my_plugin", "experiment", "My awesome plugin")
        def my_plugin(context, api):
            # Plugin implementation
            pass
    """
    def decorator(func):
        register_plugin(
            name=name,
            plugin_function=func,
            scope=scope,
            description=description,
            version=version,
            author=author,
            settings_schema=settings_schema,
            enabled_by_default=enabled_by_default,
            tags=tags,
            icon=icon
        )
        return func
    return decorator