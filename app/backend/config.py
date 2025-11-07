"""
Configuration constants for ArenaLab backend.

This module centralizes all magic numbers and configuration values
used throughout the application.
"""
import os

# Process Management
PORT_BASE = 5000  # Starting port for ML-Agents environments
PORT_SPACING = 10  # Minimum spacing between port ranges to avoid conflicts

# Health Monitoring
HEALTH_CHECK_INTERVAL_STARTUP = 5  # Seconds between health checks during startup
HEALTH_CHECK_INTERVAL_RUNNING = 10  # Seconds between health checks during steady state
HEALTH_CHECK_STARTUP_DURATION = 60  # Seconds to consider a run in "startup" phase (12 checks * 5s)
HEALTH_CHECK_STUCK_THRESHOLD = 120  # Seconds without log activity to consider stuck
HEALTH_CHECK_RUNTIME_THRESHOLD = 120  # Seconds of runtime before checking for stuck status

# Process Termination
PROCESS_GRACEFUL_SHUTDOWN_TIMEOUT = 30  # Seconds to wait for graceful shutdown (SIGTERM)
PROCESS_FORCE_KILL_TIMEOUT = 10  # Seconds to wait after SIGKILL

# Authentication
JWT_EXPIRATION_MINUTES = 1440  # 24 hours
JWT_ALGORITHM = "HS256"

# Logging
DEFAULT_LOG_LINES = 20000  # Maximum log lines to return by default

# File Operations
MAX_FILENAME_LENGTH = 50  # Maximum length for sanitized filenames

# Pagination
MAX_PAGE_LIMIT = 1000  # Maximum items per page in list endpoints

# TensorBoard
TENSORBOARD_HOST = os.getenv("TENSORBOARD_HOST", "http://localhost:6006")
TENSORBOARD_PATH_PREFIX = os.getenv("TENSORBOARD_PATH_PREFIX", "/tb")  # Set to "" for no prefix
