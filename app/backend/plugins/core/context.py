"""
Plugin context for passing state and settings to plugins.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class PluginContext:
    """Context object passed to plugins with current state and settings."""
    plugin_name: str
    scope: str  # 'experiment', 'run', 'revision'
    target_id: str  # experiment_id, run_id, or revision_id
    settings: Dict[str, Any]
    execution_id: str = None  # Unique identifier for this plugin execution
    generation: int = 0
    should_stop: bool = False
    metadata: Dict[str, Any] = None

    def should_continue(self) -> bool:
        """Check if plugin should continue running."""
        return not self.should_stop
