# Plugin Development Guide

> **⚠️ Important Notice:** The plugin system will be available in the **next version** of ArenaLab.

This guide covers creating custom plugins for ArenaLab. **The plugin system is ultra-simple: write a function, control experiments.**

## Quick Start

Create a plugin file in `app/backend/plugins/`:

```python
from .core import register_plugin

@register_plugin(
    name="my_plugin",
    scope="experiment",
    description="My awesome plugin",
    icon="🚀"
)
def my_plugin(context, api):
    """My plugin implementation."""

    # Create revision with new hyperparameters
    api.create_revision_with_hyperparameters(
        name="Test-Config",
        hyperparameters={"learning_rate": 0.001, "batch_size": 64},
        notes="Testing hyperparameters"
    )

    # Create and run training from that revision
    run = api.create_run(
        config={},  # CLI flags (empty for default behavior)
        description="Testing hyperparameters"
    )
    api.wait_for_completion([run])

    # Save good results as new revision
    if run.get_reward() > 100:
        api.create_revision_with_hyperparameters(
            name="Auto-Optimized",
            hyperparameters={"learning_rate": 0.001, "batch_size": 64},
            notes=f"Reward: {run.get_reward()}"
        )
```

**That's it!** The plugin is automatically discovered. Drop file in `plugins/` directory and it works. Delete file to remove plugin.

## Plugin System

**Function-based architecture:**
- ✅ No base classes to inherit
- ✅ No abstract methods
- ✅ Simple signature: `(context, api)`

**How it works:**
1. Auto-discovery: Scans `plugins/` for `*_plugin.py` files
2. Registration: `@register_plugin` decorator registers functions
3. Execution: Plugin runs with `PluginContext` and `PluginAPI`

**Scopes:**
- **`experiment`**: Controls entire experiment. *Use for*: PBT, hyperparameter sweeping
- **`run`**: Operates on individual runs. *Use for*: Performance monitoring, early stopping
- **`revision`**: Works with configs. *Use for*: Config validation

## Plugin API

### Creating Runs
```python
# Create a run with CLI flags (NOT hyperparameters!)
# CLI flags: time_scale, no_graphics, num_envs, etc.
run = api.create_run(
    config={},  # Empty for default behavior
    description="Testing"
)

# To change hyperparameters, create a revision FIRST:
api.create_revision_with_hyperparameters(
    name="New-Config",
    hyperparameters={"learning_rate": 0.001, "batch_size": 64}
)
# Then create a run from that new revision
run = api.create_run(config={}, description="Testing new hyperparameters")
```

### Creating Revisions
```python
# For hyperparameter tuning (recommended)
api.create_revision_with_hyperparameters(
    name="PBT_Gen1",
    hyperparameters={"learning_rate": 0.001, "batch_size": 1024},
    notes="Best performer"
)

# For advanced config changes
api.create_revision_with_config_updates(
    name="BiggerNetwork",
    config_updates={
        "behaviors": {
            "MyBehavior": {"network_settings": {"hidden_units": 512}}
        }
    }
)
```

### Synchronization
```python
# Wait for runs to complete
api.wait_for_completion(runs, timeout_minutes=30)

# Wait for time
api.wait(minutes=5)
api.wait(seconds=30)
```

### Working with Runs
```python
run.is_running()      # Check status
run.is_completed()    # Check if done
run.get_reward()      # Get metric (NOTE: currently returns placeholder data)
run.get_logs(last_lines=50)  # Get logs
```

**⚠️ Important:** The `get_reward()` method currently returns placeholder/fake data for demonstration purposes. In production, this needs to be implemented to parse actual metrics from TensorBoard event files.

### Notes
```python
api.add_note("Started sweep")  # Add to experiment
```

## Example: Hyperparameter Sweeper

```python
@register_plugin(
    name="sweeper",
    scope="experiment",
    description="Hyperparameter sweep",
    icon="🔍",
    settings_schema={
        "learning_rates": {"type": "list", "default": [0.0001, 0.0003, 0.001]},
        "batch_sizes": {"type": "list", "default": [16, 32, 64]}
    }
)
def sweeper_plugin(context, api):
    lrs = context.settings.get("learning_rates")
    batch_sizes = context.settings.get("batch_sizes")

    best_reward = -float('inf')
    best_hyperparameters = None

    for lr in lrs:
        for bs in batch_sizes:
            if context.should_stop:
                break

            # Create revision with these hyperparameters
            hyperparameters = {"learning_rate": lr, "batch_size": bs}
            api.create_revision_with_hyperparameters(
                name=f"Sweep_LR{lr}_BS{bs}",
                hyperparameters=hyperparameters
            )

            # Create run from that revision
            run = api.create_run({})
            api.wait_for_completion([run])

            reward = run.get_reward()
            if reward > best_reward:
                best_reward = reward
                best_hyperparameters = hyperparameters
                api.create_revision_with_hyperparameters(
                    name=f"Best_LR{lr}_BS{bs}",
                    hyperparameters=best_hyperparameters
                )

    api.add_note(f"✅ Best: {best_hyperparameters} (reward={best_reward:.2f})")
```

## Best Practices

1. **Check for initial revision** - Plugins need a base revision:
   ```python
   revision = api.db.revisions.find_one({"experiment_id": experiment_id})
   if not revision:
       raise ValueError("No revision found")
   ```

2. **Respect stop signal** - Always check `context.should_stop` in loops

3. **Use appropriate methods**:
   - Hyperparameter tuning → `create_revision_with_hyperparameters()`
   - Structural changes → `create_revision_with_config_updates()`

4. **Add notes** - Use emojis: ✅ ⚠️ ❌ 📊
   ```python
   api.add_note("✅ Best config found")
   ```

5. **Handle errors**:
   ```python
   try:
       run = api.create_run({})  # Empty CLI flags
   except Exception as e:
       api.add_note(f"❌ Error: {e}")
       raise
   ```

6. **Provide settings schema** - Makes plugins configurable via UI

7. **Keep focused** - Each plugin should do one thing well

## Built-in Plugins

Example plugins in `app/backend/plugins/`:

- **`pbt_plugin.py`** - Population-Based Training
- **`hyperparameter_sweeper_plugin.py`** - Grid search
- **`performance_monitor_plugin.py`** - Real-time monitoring
- **`auto_analyzer_plugin.py`** - Experiment analysis

Use these as templates for your own plugins.
