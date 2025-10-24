"""
Pytest configuration and fixtures.

This module provides common fixtures and configuration for all tests.
"""

import pytest
import asyncio
import tempfile
import shutil
import os
from unittest.mock import MagicMock, patch
from typing import Generator, Dict, Any
from fastapi.testclient import TestClient
from httpx import AsyncClient
import mongomock

# Patch pymongo.MongoClient with mongomock before any imports
import sys
import pymongo
_original_mongoclient = pymongo.MongoClient
pymongo.MongoClient = mongomock.MongoClient

# Now safe to import application components
from auth import create_access_token
try:
    from app import app
    from db import get_db
    from auth import get_current_user
    from models import UserModel
except Exception as e:
    # If app import fails in pure unit tests, that's ok
    print(f"Warning: Could not import app components: {e}")
    app = None
    get_db = None
    get_current_user = None
    UserModel = None


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db():
    """Provide a mock MongoDB database for testing."""
    client = mongomock.MongoClient()
    db = client["test_mlagents_lab"]
    
    # Create indexes like the real database
    db.experiments.create_index([("name", 1)], unique=False)
    db.runs.create_index([("experiment_id", 1)])
    db.users.create_index([("email", 1)], unique=True)
    db.revisions.create_index([("experiment_id", 1)])
    db.environments.create_index([("name", 1)])
    
    return db


@pytest.fixture
def mock_workspace():
    """Provide a temporary workspace directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_user() -> Dict[str, Any]:
    """Provide a test user."""
    return {
        "_id": "test_user_id",
        "email": "test@example.com",
        "name": "Test User",
        "role": "admin",
        "password_hash": "$hashed_password$",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00",
        "last_login": None
    }


@pytest.fixture
def auth_token(test_user) -> str:
    """Provide a valid JWT token for testing."""
    return create_access_token({"sub": test_user["email"], "user_id": test_user["_id"]})


@pytest.fixture
def authenticated_headers(auth_token) -> Dict[str, str]:
    """Provide headers with valid authentication."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def test_client():
    """Provide a test client for the FastAPI app."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_client():
    """Provide an async test client for the FastAPI app."""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def override_dependencies(mock_db, test_user):
    """Override app dependencies for testing."""
    def override_get_db():
        return mock_db

    async def override_get_current_user():
        return test_user

    # Override dependencies
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    yield mock_db  # Return the db so tests can use it

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sample_experiment():
    """Provide a sample experiment for testing."""
    return {
        "_id": "test_experiment_id",
        "name": "Test Experiment",
        "description": "A test experiment for unit testing",
        "tags": ["test", "unit"],
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00"
    }


@pytest.fixture
def sample_run():
    """Provide a sample run for testing."""
    return {
        "_id": "test_run_id",
        "revision_id": "test_revision_id",
        "experiment_id": "test_experiment_id",
        "parent_revision_id": "parent_revision_id",
        "parent_run_id": "parent_run_id",
        "created_at": "2024-01-01T00:00:00",
        "started_at": None,
        "ended_at": None,
        "yaml_path": "/test/path/config.yaml",
        "cli_flags": {"time_scale": 20, "no_graphics": True},
        "tb_logdir": "/test/tb_logs",
        "stdout_log_path": "/test/logs/stdout.log",
        "description": "Test run",
        "results_text": "",
        "status": "created"
    }


@pytest.fixture
def sample_yaml_config():
    """Provide a sample YAML configuration."""
    return """
behaviors:
  ExampleAgent:
    trainer_type: ppo
    hyperparameters:
      batch_size: 1024
      buffer_size: 10240
      learning_rate: 3.0e-4
      beta: 5.0e-4
      epsilon: 0.2
      lambd: 0.99
      num_epoch: 3
      learning_rate_schedule: linear
    network_settings:
      normalize: false
      hidden_units: 128
      num_layers: 2
    reward_signals:
      extrinsic:
        gamma: 0.99
        strength: 1.0
    max_steps: 500000
    time_horizon: 64
    summary_freq: 50000
"""


@pytest.fixture
def mock_subprocess():
    """Mock subprocess operations."""
    with patch('subprocess.Popen') as mock_popen:
        # Create a mock process
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.poll.return_value = None
        mock_process.wait.return_value = 0
        mock_process.terminate.return_value = None
        mock_process.kill.return_value = None
        
        mock_popen.return_value = mock_process
        yield mock_process


@pytest.fixture
def mock_file_operations():
    """Mock file system operations."""
    with patch('os.makedirs'), \
         patch('os.path.exists', return_value=True), \
         patch('builtins.open'), \
         patch('shutil.rmtree'):
        yield


@pytest.fixture
def populated_db(mock_db, sample_experiment, sample_run):
    """Provide a database with sample data."""
    # Add sample data
    mock_db.experiments.insert_one(sample_experiment)
    mock_db.runs.insert_one(sample_run)
    
    # Add test user
    mock_db.users.insert_one({
        "_id": "test_user_id",
        "email": "test@example.com",
        "name": "Test User",
        "role": "admin",
        "password_hash": "$hashed_password$",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00"
    })
    
    return mock_db


# Utility functions for tests
class TestHelpers:
    """Helper functions for tests."""
    
    @staticmethod
    def create_mock_process(pid: int = 12345, returncode: int = 0):
        """Create a mock subprocess.Popen object."""
        mock_process = MagicMock()
        mock_process.pid = pid
        mock_process.returncode = returncode
        mock_process.poll.return_value = None if returncode is None else returncode
        return mock_process
    
    @staticmethod
    def assert_valid_uuid(uuid_string: str):
        """Assert that a string is a valid UUID."""
        import uuid
        try:
            uuid.UUID(uuid_string)
            return True
        except ValueError:
            return False


@pytest.fixture
def helpers():
    """Provide test helper functions."""
    return TestHelpers()