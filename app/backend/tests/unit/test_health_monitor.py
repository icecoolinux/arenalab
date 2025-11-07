"""
Unit tests for health_monitor module.

Tests health checking and stale run detection.
"""

import pytest
import os
import time
import tempfile
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from runner.health_monitor import check_process_health, get_stale_runs


@pytest.fixture
def mock_process():
    """Create a mock subprocess.Popen object."""
    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = None
    proc.poll.return_value = None
    return proc


@pytest.fixture
def mock_db():
    """Mock database connection."""
    with patch('runner.health_monitor.get_db') as mock_get_db:
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        yield mock_db_instance


@pytest.fixture
def temp_log_file():
    """Create a temporary log file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write("Test log content\n")
        temp_path = f.name
    yield temp_path
    try:
        os.unlink(temp_path)
    except:
        pass


@pytest.mark.unit
class TestCheckProcessHealth:
    """Test process health checking."""

    def test_check_health_process_not_found(self):
        """Test health check when process is not in active runs."""
        run_procs = {}  # Empty, no active processes
        result = check_process_health("run_001", run_procs=run_procs)

        assert result["healthy"] == False
        assert result["stuck"] == False
        assert "not found" in result["reason"].lower()

    def test_check_health_process_exited(self, mock_process):
        """Test health check when process has exited."""
        run_id = "run_001"
        mock_process.poll.return_value = 0
        mock_process.returncode = 0
        run_procs = {run_id: mock_process}

        result = check_process_health(run_id, run_procs=run_procs)

        assert result["healthy"] == False
        assert result["stuck"] == False
        assert "exited" in result["reason"].lower()

    def test_check_health_log_file_not_created(self, mock_process, mock_db):
        """Test health check when log file doesn't exist yet (early startup)."""
        run_id = "run_001"
        run_procs = {run_id: mock_process}

        def mock_run_dir_getter(rid):
            return "/nonexistent/path"

        result = check_process_health(
            run_id,
            run_procs=run_procs,
            run_dir_getter=mock_run_dir_getter
        )

        assert result["healthy"] == True
        assert result["stuck"] == False
        assert "early startup" in result["reason"].lower()

    @patch('runner.health_monitor.HEALTH_CHECK_RUNTIME_THRESHOLD', 60)
    @patch('runner.health_monitor.HEALTH_CHECK_STUCK_THRESHOLD', 300)
    def test_check_health_process_healthy(self, mock_process, mock_db, temp_log_file):
        """Test health check for a healthy running process."""
        run_id = "run_002"
        run_procs = {run_id: mock_process}

        # Mock recent start time
        started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        mock_db.runs.find_one.return_value = {
            "_id": run_id,
            "started_at": started_at
        }

        # Touch the log file to make it recent
        os.utime(temp_log_file, None)

        def mock_run_dir_getter(rid):
            return os.path.dirname(temp_log_file)

        # Mock to make stdout.log point to our temp file
        with patch('runner.health_monitor.os.path.exists', return_value=True), \
             patch('runner.health_monitor.os.path.getmtime', return_value=time.time()), \
             patch('runner.health_monitor.os.path.getsize', return_value=1024):

            result = check_process_health(
                run_id,
                run_procs=run_procs,
                run_dir_getter=mock_run_dir_getter
            )

        assert result["healthy"] == True
        assert result["stuck"] == False
        assert "healthy" in result["reason"].lower()
        assert result["pid"] == 12345

    @patch('runner.health_monitor.HEALTH_CHECK_RUNTIME_THRESHOLD', 60)
    @patch('runner.health_monitor.HEALTH_CHECK_STUCK_THRESHOLD', 300)
    def test_check_health_process_stuck(self, mock_process, mock_db, temp_log_file):
        """Test health check detecting a stuck process."""
        run_id = "run_003"
        run_procs = {run_id: mock_process}

        # Mock old start time (process has been running for a while)
        started_at = datetime.now(timezone.utc) - timedelta(seconds=600)
        mock_db.runs.find_one.return_value = {
            "_id": run_id,
            "started_at": started_at
        }

        # Make log file old (no recent activity)
        old_time = time.time() - 400  # 400 seconds ago

        def mock_run_dir_getter(rid):
            return os.path.dirname(temp_log_file)

        with patch('runner.health_monitor.os.path.exists', return_value=True), \
             patch('runner.health_monitor.os.path.getmtime', return_value=old_time), \
             patch('runner.health_monitor.os.path.getsize', return_value=1024):

            result = check_process_health(
                run_id,
                run_procs=run_procs,
                run_dir_getter=mock_run_dir_getter
            )

        assert result["healthy"] == False
        assert result["stuck"] == True
        assert "no log activity" in result["reason"].lower()
        assert result["seconds_since_log_update"] == 400

    @patch('runner.health_monitor.HEALTH_CHECK_RUNTIME_THRESHOLD', 60)
    @patch('runner.health_monitor.HEALTH_CHECK_STUCK_THRESHOLD', 300)
    def test_check_health_startup_period_not_stuck(self, mock_process, mock_db, temp_log_file):
        """Test that process during startup period is not considered stuck."""
        run_id = "run_004"
        run_procs = {run_id: mock_process}

        # Mock very recent start time (still in startup)
        started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_db.runs.find_one.return_value = {
            "_id": run_id,
            "started_at": started_at
        }

        # Even if log is old, shouldn't be considered stuck during startup
        old_time = time.time() - 400

        def mock_run_dir_getter(rid):
            return os.path.dirname(temp_log_file)

        with patch('runner.health_monitor.os.path.exists', return_value=True), \
             patch('runner.health_monitor.os.path.getmtime', return_value=old_time), \
             patch('runner.health_monitor.os.path.getsize', return_value=1024):

            result = check_process_health(
                run_id,
                run_procs=run_procs,
                run_dir_getter=mock_run_dir_getter
            )

        # Not stuck because runtime < threshold (30 < 60)
        assert result["stuck"] == False

    def test_check_health_run_not_in_database(self, mock_process):
        """Test health check when run is not found in database."""
        run_id = "run_005"
        run_procs = {run_id: mock_process}

        with patch('runner.health_monitor.get_db') as mock_get_db:
            mock_db = MagicMock()
            mock_db.runs.find_one.return_value = None
            mock_get_db.return_value = mock_db

            def mock_run_dir_getter(rid):
                return "/fake/path"

            with patch('runner.health_monitor.os.path.exists', return_value=True):
                result = check_process_health(
                    run_id,
                    run_procs=run_procs,
                    run_dir_getter=mock_run_dir_getter
                )

        assert result["healthy"] == False
        assert "not found in database" in result["reason"].lower()

    def test_check_health_timezone_aware_comparison(self, mock_process, mock_db, temp_log_file):
        """Test that timezone-aware datetime comparison works correctly."""
        run_id = "run_006"
        run_procs = {run_id: mock_process}

        # Mock start time without timezone (naive datetime)
        started_at_naive = datetime.now() - timedelta(seconds=120)
        mock_db.runs.find_one.return_value = {
            "_id": run_id,
            "started_at": started_at_naive  # Naive datetime (no tzinfo)
        }

        def mock_run_dir_getter(rid):
            return os.path.dirname(temp_log_file)

        with patch('runner.health_monitor.os.path.exists', return_value=True), \
             patch('runner.health_monitor.os.path.getmtime', return_value=time.time()), \
             patch('runner.health_monitor.os.path.getsize', return_value=1024):

            # Should not raise error about timezone comparison
            result = check_process_health(
                run_id,
                run_procs=run_procs,
                run_dir_getter=mock_run_dir_getter
            )

        # Should complete successfully
        assert "runtime_seconds" in result

    def test_check_health_exception_handling(self, mock_process):
        """Test that health check handles exceptions gracefully."""
        run_id = "run_007"
        run_procs = {run_id: mock_process}

        def mock_run_dir_getter(rid):
            raise Exception("Directory error")

        result = check_process_health(
            run_id,
            run_procs=run_procs,
            run_dir_getter=mock_run_dir_getter
        )

        assert result["healthy"] == False
        assert "error" in result["reason"].lower()


@pytest.mark.unit
class TestGetStaleRuns:
    """Test stale run detection."""

    def test_get_stale_runs_none(self, mock_process):
        """Test getting stale runs when none are stuck."""
        run_procs = {
            "run_001": mock_process,
            "run_002": mock_process
        }

        def mock_health_checker(run_id):
            return {"stuck": False, "healthy": True}

        stale = get_stale_runs(run_procs, mock_health_checker)

        assert stale == []

    def test_get_stale_runs_multiple(self, mock_process):
        """Test detecting multiple stale runs."""
        run_procs = {
            "run_001": mock_process,
            "run_002": mock_process,
            "run_003": mock_process
        }

        def mock_health_checker(run_id):
            # Make run_001 and run_003 stuck
            if run_id in ["run_001", "run_003"]:
                return {
                    "stuck": True,
                    "healthy": False,
                    "reason": "No log activity"
                }
            return {"stuck": False, "healthy": True}

        stale = get_stale_runs(run_procs, mock_health_checker)

        assert len(stale) == 2
        stale_ids = [run["run_id"] for run in stale]
        assert "run_001" in stale_ids
        assert "run_003" in stale_ids
        assert "run_002" not in stale_ids

    def test_get_stale_runs_health_info_included(self, mock_process):
        """Test that stale runs include health information."""
        run_procs = {"run_001": mock_process}

        health_info = {
            "stuck": True,
            "healthy": False,
            "reason": "No log activity for 400 seconds",
            "seconds_since_log_update": 400
        }

        def mock_health_checker(run_id):
            return health_info

        stale = get_stale_runs(run_procs, mock_health_checker)

        assert len(stale) == 1
        assert stale[0]["run_id"] == "run_001"
        assert stale[0]["health"] == health_info

    def test_get_stale_runs_empty_run_procs(self):
        """Test getting stale runs when no processes are running."""
        run_procs = {}

        def mock_health_checker(run_id):
            return {"stuck": True}

        stale = get_stale_runs(run_procs, mock_health_checker)

        assert stale == []


@pytest.mark.unit
class TestHealthCheckEdgeCases:
    """Test edge cases and boundary conditions."""

    @patch('runner.health_monitor.HEALTH_CHECK_RUNTIME_THRESHOLD', 60)
    @patch('runner.health_monitor.HEALTH_CHECK_STUCK_THRESHOLD', 300)
    def test_check_health_exactly_at_threshold(self, mock_process, mock_db, temp_log_file):
        """Test health check exactly at stuck threshold."""
        run_id = "run_001"
        run_procs = {run_id: mock_process}

        # Exactly at runtime threshold
        started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        mock_db.runs.find_one.return_value = {
            "_id": run_id,
            "started_at": started_at
        }

        # Exactly at stuck threshold
        threshold_time = time.time() - 300

        def mock_run_dir_getter(rid):
            return os.path.dirname(temp_log_file)

        with patch('runner.health_monitor.os.path.exists', return_value=True), \
             patch('runner.health_monitor.os.path.getmtime', return_value=threshold_time), \
             patch('runner.health_monitor.os.path.getsize', return_value=1024):

            result = check_process_health(
                run_id,
                run_procs=run_procs,
                run_dir_getter=mock_run_dir_getter
            )

        # At exactly threshold, should not be considered stuck yet (> not >=)
        assert result["stuck"] == False

    def test_check_health_no_started_at(self, mock_process, mock_db, temp_log_file):
        """Test health check when run has no started_at timestamp."""
        run_id = "run_002"
        run_procs = {run_id: mock_process}

        mock_db.runs.find_one.return_value = {
            "_id": run_id
            # No started_at field
        }

        def mock_run_dir_getter(rid):
            return os.path.dirname(temp_log_file)

        with patch('runner.health_monitor.os.path.exists', return_value=True), \
             patch('runner.health_monitor.os.path.getmtime', return_value=time.time()), \
             patch('runner.health_monitor.os.path.getsize', return_value=1024):

            result = check_process_health(
                run_id,
                run_procs=run_procs,
                run_dir_getter=mock_run_dir_getter
            )

        # Should handle gracefully with runtime_seconds = 0
        assert result["runtime_seconds"] == 0
        assert result["stuck"] == False

    def test_check_health_zero_size_log(self, mock_process, mock_db, temp_log_file):
        """Test health check with zero-size log file."""
        run_id = "run_003"
        run_procs = {run_id: mock_process}

        started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        mock_db.runs.find_one.return_value = {
            "_id": run_id,
            "started_at": started_at
        }

        def mock_run_dir_getter(rid):
            return os.path.dirname(temp_log_file)

        with patch('runner.health_monitor.os.path.exists', return_value=True), \
             patch('runner.health_monitor.os.path.getmtime', return_value=time.time()), \
             patch('runner.health_monitor.os.path.getsize', return_value=0):

            result = check_process_health(
                run_id,
                run_procs=run_procs,
                run_dir_getter=mock_run_dir_getter
            )

        # Should still work with zero-size log
        assert "log_size_bytes" in result
        assert result["log_size_bytes"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
