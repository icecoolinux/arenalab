"""
Unit tests for the plugin system.

Tests plugin registration, function-based plugins, and execution.
"""

import pytest
from unittest.mock import patch, MagicMock

from plugins.core.registry import register_plugin, get_plugin, _global_registry, validate_plugin_settings
from plugins.core.api import PluginContext, PluginAPI


def test_plugin_registration():
    """Test that plugins can be registered with the @plugin decorator."""

    @register_plugin("test_plugin", "experiment", "Test plugin for unit tests")
    def test_plugin(context, api):
        return "test executed"

    # Check that plugin was registered
    assert "test_plugin" in _global_registry.list_plugins()

    # Check that we can get plugin info
    plugin_info = get_plugin("test_plugin")
    assert plugin_info is not None
    assert plugin_info.name == "test_plugin"
    assert plugin_info.scope == "experiment"


def test_plugin_function_execution():
    """Test that plugin functions can be executed."""
    
    executed = []
    
    def simple_plugin(context, api):
        executed.append(f"Plugin {context.plugin_name} executed")
        return "success"
    
    register_plugin("simple_test", simple_plugin, "run", "Simple test plugin")
    
    # Create context and API
    context = PluginContext(
        plugin_name="simple_test",
        scope="run", 
        target_id="test_run_id",
        settings={}
    )
    
    api = PluginAPI(context)
    
    # Execute plugin function
    plugin_info = get_plugin("simple_test")
    result = plugin_info.function(context, api)
    
    assert result == "success"
    assert len(executed) == 1
    assert "simple_test" in executed[0]


def test_plugin_context():
    """Test plugin context object."""
    context = PluginContext(
        plugin_name="test",
        scope="experiment",
        target_id="exp_123",
        settings={"param": "value"},
        generation=5
    )
    
    assert context.plugin_name == "test"
    assert context.scope == "experiment"
    assert context.target_id == "exp_123"
    assert context.settings["param"] == "value"
    assert context.generation == 5
    assert context.should_continue() == True  # should_stop defaults to False


@patch('plugins.simple_api.get_database')
def test_plugin_api_basic(mock_get_db):
    """Test basic PluginAPI functionality."""
    # Mock database
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    context = PluginContext(
        plugin_name="test",
        scope="experiment", 
        target_id="exp_123",
        settings={}
    )
    
    api = PluginAPI(context)
    
    # Test that API was created with proper context
    assert api.context == context
    assert api.db == mock_db


def test_ultra_simple_plugin_example():
    """Test the ultra-simple plugin example from documentation."""
    
    executed_steps = []
    
    def ultra_simple_example(context, api):
        # This simulates the example from the documentation
        executed_steps.append("create_run")
        executed_steps.append("wait_for_completion") 
        executed_steps.append("create_revision")
        return "completed"
    
    register_plugin("ultra_simple", ultra_simple_example, "experiment", "Ultra simple example")
    
    context = PluginContext("ultra_simple", "experiment", "exp_123", {})
    api = PluginAPI(context)
    
    plugin_info = get_plugin("ultra_simple")
    result = plugin_info.function(context, api)
    
    assert result == "completed"
    assert executed_steps == ["create_run", "wait_for_completion", "create_revision"]


def test_plugin_settings_validation():
    """Test plugin settings validation."""

    # Register plugin with settings schema
    def plugin_with_settings(context, api):
        pass

    register_plugin(
        "settings_test",
        plugin_with_settings,
        "run",
        "Test plugin with settings",
        settings_schema={
            "required_param": {"type": "int", "required": True},
            "optional_param": {"type": "string", "default": "default_value"}
        }
    )
    
    # Test valid settings
    valid_settings = {"required_param": 42, "optional_param": "custom"}
    assert validate_plugin_settings("settings_test", valid_settings) == True
    
    # Test invalid settings (missing required param)
    invalid_settings = {"optional_param": "custom"}
    assert validate_plugin_settings("settings_test", invalid_settings) == False


def test_multiple_plugin_registration():
    """Test that multiple plugins can be registered."""

    def plugin_one(context, api):
        return "one"

    def plugin_two(context, api):
        return "two"

    register_plugin("multi_one", plugin_one, "experiment", "First plugin")
    register_plugin("multi_two", plugin_two, "run", "Second plugin")

    plugins = _global_registry.list_plugins()
    assert "multi_one" in plugins
    assert "multi_two" in plugins

    # Test that each plugin has correct info
    info_one = get_plugin("multi_one")
    info_two = get_plugin("multi_two")

    assert info_one.scope == "experiment"
    assert info_two.scope == "run"
    assert info_one.description == "First plugin"
    assert info_two.description == "Second plugin"


class TestPluginAPIRevisionMethods:
    """Test cases for PluginAPI revision creation methods using RevisionsService."""

    @pytest.fixture
    def plugin_context(self):
        """Create a plugin context for testing."""
        return PluginContext(
            plugin_name="test_plugin",
            scope="experiment",
            target_id="test_exp_id",
            settings={}
        )

    @pytest.fixture
    def mock_revisions_service(self):
        """Mock RevisionsService for testing."""
        with patch('plugins.core.api.RevisionsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_revision.return_value = {
                "_id": "created_rev_id",
                "name": "Created Revision",
                "experiment_id": "test_exp_id"
            }
            mock_service_class.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db_collections(self):
        """Mock database collections."""
        with patch('plugins.core.api.get_db') as mock_get_db:
            mock_db = MagicMock()

            # Mock experiments collection
            mock_db.experiments.find_one.return_value = {
                "_id": "test_exp_id",
                "name": "Test Experiment"
            }

            # Mock revisions collection
            mock_db.revisions.find_one.return_value = {
                "_id": "parent_rev_id",
                "experiment_id": "test_exp_id",
                "yaml_path": "experiments/test-experiment_test_exp_id/revisions/test-revision_parent_rev_id/config.yaml",
                "environment_id": "test_env_id"
            }

            mock_get_db.return_value = mock_db
            yield mock_db

    @patch('utils.file_tools.ensure_workspace_path')
    @patch('utils.yaml_tools.load_yaml_with_comments')
    @patch('utils.yaml_tools.merge_hyperparameters_into_config')
    @patch('utils.yaml_tools.validate_mlagents_config')
    def test_create_revision_with_hyperparameters_success(
        self, mock_validate, mock_merge, mock_load_yaml, mock_ensure_path,
        plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test successful creation of revision with hyperparameters."""
        # Setup mocks
        mock_ensure_path.return_value = "/workspace/experiments/test-experiment_test_exp_id/revisions/test-revision_parent_rev_id/config.yaml"
        mock_yaml_handler = MagicMock()
        # Mock the dump method to write YAML content
        def mock_dump(data, stream):
            stream.write("behaviors:\n  TestAgent:\n    hyperparameters:\n      batch_size: 1024\n      learning_rate: 0.001\n")
        mock_yaml_handler.dump = mock_dump

        mock_load_yaml.return_value = (
            {"behaviors": {"TestAgent": {"hyperparameters": {"batch_size": 512}}}},
            mock_yaml_handler
        )
        mock_merge.return_value = {
            "behaviors": {
                "TestAgent": {
                    "hyperparameters": {
                        "batch_size": 1024,
                        "learning_rate": 0.001
                    }
                }
            }
        }

        # Create API instance
        api = PluginAPI(plugin_context)

        # Call the method
        result = api.create_revision_with_hyperparameters(
            name="Test Hyperparams",
            hyperparameters={"learning_rate": 0.001, "batch_size": 1024},
            notes="Testing hyperparameters"
        )

        # Assertions
        assert result == "created_rev_id"
        mock_revisions_service.create_revision.assert_called_once()

        # Verify RevisionBody was created with correct parameters
        call_args = mock_revisions_service.create_revision.call_args[0][0]
        assert call_args.name == "Test Hyperparams"
        assert call_args.experiment_id == "test_exp_id"
        assert call_args.cli_flags == {"learning_rate": 0.001, "batch_size": 1024}
        assert "Testing hyperparameters" in call_args.description

    @patch('utils.file_tools.ensure_workspace_path')
    @patch('utils.yaml_tools.load_yaml_with_comments')
    @patch('utils.yaml_tools.merge_hyperparameters_into_config')
    @patch('utils.yaml_tools.validate_mlagents_config')
    def test_create_revision_with_hyperparameters_specific_behavior(
        self, mock_validate, mock_merge, mock_load_yaml, mock_ensure_path,
        plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test creating revision with hyperparameters for specific behavior."""
        mock_ensure_path.return_value = "/workspace/config.yaml"
        mock_yaml_handler = MagicMock()
        def mock_dump(data, stream):
            stream.write("behaviors:\n  SpecificAgent:\n    hyperparameters:\n      learning_rate: 0.001\n")
        mock_yaml_handler.dump = mock_dump
        mock_load_yaml.return_value = ({"behaviors": {}}, mock_yaml_handler)
        mock_merge.return_value = {"behaviors": {"SpecificAgent": {"hyperparameters": {"learning_rate": 0.001}}}}

        api = PluginAPI(plugin_context)

        result = api.create_revision_with_hyperparameters(
            name="Specific Behavior Test",
            hyperparameters={"learning_rate": 0.001},
            behavior_name="SpecificAgent"
        )

        assert result == "created_rev_id"
        # Verify merge was called with behavior_name
        mock_merge.assert_called_once()
        merge_call_args = mock_merge.call_args
        assert merge_call_args[0][1] == {"learning_rate": 0.001}
        assert merge_call_args[0][2] == "SpecificAgent"

    def test_create_revision_with_hyperparameters_no_parent_revision(
        self, plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test error when no parent revision exists."""
        mock_db_collections.revisions.find_one.return_value = None

        api = PluginAPI(plugin_context)

        with pytest.raises(ValueError) as exc_info:
            api.create_revision_with_hyperparameters(
                name="Test",
                hyperparameters={"learning_rate": 0.001}
            )

        assert "No parent revision found" in str(exc_info.value)

    @patch('utils.file_tools.ensure_workspace_path')
    @patch('utils.yaml_tools.load_yaml_with_comments')
    @patch('utils.yaml_tools.deep_merge_dict')
    @patch('utils.yaml_tools.validate_mlagents_config')
    def test_create_revision_with_config_updates_deep_merge(
        self, mock_validate, mock_deep_merge, mock_load_yaml, mock_ensure_path,
        plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test creating revision with config updates using deep merge."""
        mock_ensure_path.return_value = "/workspace/config.yaml"
        mock_yaml_handler = MagicMock()
        def mock_dump(data, stream):
            stream.write("behaviors:\n  Agent:\n    network_settings:\n      hidden_units: 256\n")
        mock_yaml_handler.dump = mock_dump
        mock_load_yaml.return_value = ({"behaviors": {"Agent": {}}}, mock_yaml_handler)
        mock_deep_merge.return_value = {
            "behaviors": {
                "Agent": {
                    "network_settings": {"hidden_units": 256}
                }
            }
        }

        api = PluginAPI(plugin_context)

        config_updates = {
            "behaviors": {
                "Agent": {
                    "network_settings": {"hidden_units": 256}
                }
            }
        }

        result = api.create_revision_with_config_updates(
            name="Network Update",
            config_updates=config_updates,
            merge_strategy="deep",
            notes="Bigger network"
        )

        assert result == "created_rev_id"
        mock_deep_merge.assert_called_once()
        mock_revisions_service.create_revision.assert_called_once()

    @patch('utils.file_tools.ensure_workspace_path')
    @patch('utils.yaml_tools.load_yaml_with_comments')
    @patch('utils.yaml_tools.validate_mlagents_config')
    def test_create_revision_with_config_updates_shallow_merge(
        self, mock_validate, mock_load_yaml, mock_ensure_path,
        plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test creating revision with config updates using shallow merge."""
        mock_ensure_path.return_value = "/workspace/config.yaml"
        mock_yaml_handler = MagicMock()
        def mock_dump(data, stream):
            stream.write("behaviors:\n  Agent: {}\nother_key: value\nnew_key: new_value\n")
        mock_yaml_handler.dump = mock_dump
        base_config = {"behaviors": {"Agent": {}}, "other_key": "value"}
        mock_load_yaml.return_value = (base_config, mock_yaml_handler)

        api = PluginAPI(plugin_context)

        config_updates = {"new_key": "new_value"}

        result = api.create_revision_with_config_updates(
            name="Shallow Update",
            config_updates=config_updates,
            merge_strategy="shallow"
        )

        assert result == "created_rev_id"
        # Verify service was called
        mock_revisions_service.create_revision.assert_called_once()

    @patch('utils.file_tools.ensure_workspace_path')
    @patch('utils.yaml_tools.load_yaml_with_comments')
    @patch('utils.yaml_tools.deep_merge_dict')
    @patch('utils.yaml_tools.validate_mlagents_config')
    def test_create_revision_low_level_method(
        self, mock_validate, mock_deep_merge, mock_load_yaml, mock_ensure_path,
        plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test low-level create_revision method."""
        mock_ensure_path.return_value = "/workspace/config.yaml"
        mock_yaml_handler = MagicMock()
        def mock_dump(data, stream):
            stream.write("behaviors: {}\nnew_setting: value\n")
        mock_yaml_handler.dump = mock_dump
        mock_load_yaml.return_value = ({"behaviors": {}}, mock_yaml_handler)
        mock_deep_merge.return_value = {"behaviors": {}, "new_setting": "value"}

        api = PluginAPI(plugin_context)

        result = api.create_revision(
            name="Low Level Test",
            config={"new_setting": "value"},
            notes="Testing low-level method"
        )

        assert result == "created_rev_id"
        mock_revisions_service.create_revision.assert_called_once()

        # Verify RevisionBody parameters
        call_args = mock_revisions_service.create_revision.call_args[0][0]
        assert call_args.name == "Low Level Test"
        assert call_args.cli_flags == {"new_setting": "value"}

    @patch('utils.file_tools.ensure_workspace_path')
    def test_create_revision_with_explicit_yaml_content(
        self, mock_ensure_path, plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test create_revision with explicit YAML content provided."""
        mock_ensure_path.return_value = "/workspace/config.yaml"

        api = PluginAPI(plugin_context)

        yaml_content = "behaviors:\n  Agent:\n    trainer_type: ppo"

        result = api.create_revision(
            name="Explicit YAML",
            config={},
            yaml_content=yaml_content,
            environment_id="test_env_id"
        )

        assert result == "created_rev_id"
        # Verify YAML content was passed to service
        call_args = mock_revisions_service.create_revision.call_args[0][0]
        assert call_args.yaml == yaml_content

    def test_create_revision_run_scoped_context(
        self, mock_revisions_service, mock_db_collections
    ):
        """Test revision creation from run-scoped plugin context."""
        # Create run-scoped context
        run_context = PluginContext(
            plugin_name="run_plugin",
            scope="run",
            target_id="test_run_id",
            settings={}
        )

        # Mock run lookup
        mock_db_collections.runs.find_one.return_value = {
            "_id": "test_run_id",
            "experiment_id": "test_exp_id"
        }

        with patch('utils.file_tools.ensure_workspace_path'), \
             patch('utils.yaml_tools.load_yaml_with_comments') as mock_load, \
             patch('utils.yaml_tools.deep_merge_dict') as mock_merge, \
             patch('utils.yaml_tools.validate_mlagents_config'):

            mock_yaml_handler = MagicMock()
            def mock_dump(data, stream):
                stream.write("behaviors: {}\n")
            mock_yaml_handler.dump = mock_dump
            mock_load.return_value = ({}, mock_yaml_handler)
            mock_merge.return_value = {}

            api = PluginAPI(run_context)

            result = api.create_revision(
                name="From Run Context",
                config={},
                environment_id="test_env_id"
            )

            assert result == "created_rev_id"
            # Verify experiment_id was correctly retrieved from run
            call_args = mock_revisions_service.create_revision.call_args[0][0]
            assert call_args.experiment_id == "test_exp_id"

    def test_create_revision_missing_environment_id(
        self, plugin_context, mock_revisions_service, mock_db_collections
    ):
        """Test error when environment_id cannot be determined."""
        # Mock no parent revision
        mock_db_collections.revisions.find_one.return_value = None

        api = PluginAPI(plugin_context)

        with pytest.raises(ValueError) as exc_info:
            api.create_revision(
                name="Test",
                config={}
                # No environment_id provided and no parent revision
            )

        assert "no environment_id provided" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__])