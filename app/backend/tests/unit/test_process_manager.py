"""
Unit tests for process_manager module.

Tests process monitoring, stopping, force killing, and status tracking.
"""

import pytest
import time
import threading
from unittest.mock import MagicMock, patch, call
from datetime import datetime

from runner.process_manager import (
    monitor_process_health,
    get_run_logs,
    stop_run,
    force_kill_run,
    get_run_status,
    get_active_runs,
    RUN_PROCS,
    RUN_STATUS,
    RUN_THREADS
)


@pytest.fixture(autouse=True)
def clean_process_state():
    """Clean process state before and after each test."""
    RUN_PROCS.clear()
    RUN_STATUS.clear()
    RUN_THREADS.clear()
    yield
    RUN_PROCS.clear()
    RUN_STATUS.clear()
    RUN_THREADS.clear()


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
    with patch('runner.process_manager.get_db') as mock_get_db:
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        yield mock_db_instance


@pytest.mark.unit
class TestMonitorProcessHealth:
    """Test process health monitoring."""

    @patch('runner.process_manager.time.sleep')
    def test_monitor_process_success(self, mock_sleep, mock_process, mock_db):
        """Test monitoring a process that completes successfully."""
        run_id = "run_001"

        # Simulate process running for 3 checks then completing
        poll_calls = [None, None, None, 0]
        mock_process.poll.side_effect = poll_calls
        mock_process.returncode = 0

        monitor_process_health(run_id, mock_process)

        # Check final status
        assert RUN_STATUS[run_id] == "succeeded"

    @patch('runner.process_manager.time.sleep')
    def test_monitor_process_failure(self, mock_sleep, mock_process, mock_db):
        """Test monitoring a process that fails."""
        run_id = "run_002"

        # Simulate process running then failing
        # First few calls return None (running), then return 1 (failed)
        poll_returns = [None, None, None, 1]
        mock_process.poll.side_effect = poll_returns
        mock_process.returncode = 1

        monitor_process_health(run_id, mock_process)

        # Check final status
        assert RUN_STATUS[run_id] == "failed"

        # Verify database was updated for failure
        mock_db.runs.update_one.assert_called_once()
        update_call = mock_db.runs.update_one.call_args
        assert update_call[0][0] == {"_id": run_id}
        assert update_call[0][1]["$set"]["status"] == "failed"

    @patch('runner.process_manager.time.sleep')
    def test_monitor_process_killed(self, mock_sleep, mock_process, mock_db):
        """Test monitoring a process that was killed by signal."""
        run_id = "run_003"

        # Negative return code indicates killed by signal
        poll_returns = [None, None, None, -9]
        mock_process.poll.side_effect = poll_returns
        mock_process.returncode = -9

        monitor_process_health(run_id, mock_process)

        assert RUN_STATUS[run_id] == "killed"

        # Verify database was updated
        mock_db.runs.update_one.assert_called_once()

    @patch('runner.process_manager.time.sleep')
    def test_monitor_process_user_stopped(self, mock_sleep, mock_process, mock_db):
        """Test that user-initiated stop is preserved."""
        run_id = "run_004"

        # Mock DB showing user stopped the run
        mock_db.runs.find_one.return_value = {"_id": run_id, "status": "stopped"}

        poll_calls = [None, 0]
        mock_process.poll.side_effect = poll_calls
        mock_process.returncode = 0

        monitor_process_health(run_id, mock_process)

        # Status should remain "stopped" not "succeeded"
        assert RUN_STATUS[run_id] == "stopped"

    @patch('runner.process_manager.time.sleep')
    def test_monitor_process_error_state(self, mock_sleep, mock_process, mock_db):
        """Test monitoring handles process dying without return code."""
        run_id = "run_005"

        # Process dies but returncode is None
        poll_calls = [None, None, None]
        mock_process.poll.side_effect = poll_calls
        mock_process.returncode = None

        monitor_process_health(run_id, mock_process)

        assert RUN_STATUS[run_id] == "error"

    @patch('runner.process_manager.time.sleep')
    def test_monitor_process_exception_handling(self, mock_sleep, mock_process, mock_db):
        """Test that monitoring handles exceptions gracefully."""
        run_id = "run_006"

        # Simulate exception during polling
        mock_process.poll.side_effect = Exception("Polling error")

        monitor_process_health(run_id, mock_process)

        # Should set error status
        assert RUN_STATUS[run_id] == "error"


@pytest.mark.unit
class TestGetRunLogs:
    """Test log retrieval functionality."""

    def test_get_run_logs_success(self):
        """Test successful log retrieval."""
        run_id = "run_001"
        max_lines = 100

        def mock_run_dir_getter(rid):
            return f"/workspace/runs/{rid}"

        with patch('utils.file_tools.LogStreamer') as mock_streamer_class:
            mock_streamer = MagicMock()
            mock_streamer.tail_lines.return_value = ["line1", "line2", "line3"]
            mock_streamer_class.return_value = mock_streamer

            logs = get_run_logs(run_id, max_lines, mock_run_dir_getter)

            assert logs == ["line1", "line2", "line3"]
            mock_streamer.tail_lines.assert_called_once_with(100)

    def test_get_run_logs_exception(self):
        """Test log retrieval handles exceptions."""
        run_id = "run_002"

        def mock_run_dir_getter(rid):
            raise Exception("Directory not found")

        logs = get_run_logs(run_id, 100, mock_run_dir_getter)

        # Should return empty list on error
        assert logs == []


@pytest.mark.unit
class TestStopRun:
    """Test graceful run stopping."""

    def test_stop_run_success(self, mock_process, mock_db):
        """Test successfully stopping a running process."""
        run_id = "run_001"
        RUN_PROCS[run_id] = mock_process
        RUN_STATUS[run_id] = "running"

        mock_port_deallocator = MagicMock()

        result = stop_run(run_id, mock_port_deallocator)

        assert result == True
        mock_process.terminate.assert_called_once()
        mock_port_deallocator.assert_called_once_with(run_id)
        # Process should be removed from tracking
        assert run_id not in RUN_PROCS
        assert run_id not in RUN_STATUS

    def test_stop_run_no_process(self, mock_db):
        """Test stopping when no process is running."""
        run_id = "run_002"
        mock_port_deallocator = MagicMock()

        result = stop_run(run_id, mock_port_deallocator)

        assert result == False

    def test_stop_run_already_terminated(self, mock_process, mock_db):
        """Test stopping process that already terminated."""
        run_id = "run_003"
        mock_process.poll.return_value = 0  # Already terminated
        mock_process.returncode = 0
        RUN_PROCS[run_id] = mock_process

        mock_port_deallocator = MagicMock()

        result = stop_run(run_id, mock_port_deallocator)

        assert result == True
        # Should not call terminate on already-dead process
        mock_process.terminate.assert_not_called()

    @patch('runner.process_manager.os.name', 'posix')
    @patch('runner.process_manager.os.getpgid')
    @patch('runner.process_manager.os.killpg')
    def test_stop_run_unix_process_group(self, mock_killpg, mock_getpgid, mock_db, mock_process):
        """Test stopping process group on Unix systems."""
        run_id = "run_004"
        mock_getpgid.return_value = 12345
        RUN_PROCS[run_id] = mock_process

        mock_port_deallocator = MagicMock()

        stop_run(run_id, mock_port_deallocator)

        # Should kill entire process group
        mock_getpgid.assert_called_with(mock_process.pid)
        mock_killpg.assert_called()

    @patch('runner.process_manager.PROCESS_GRACEFUL_SHUTDOWN_TIMEOUT', 2)
    def test_stop_run_graceful_timeout_then_force_kill(self, mock_process, mock_db):
        """Test force kill after graceful shutdown timeout."""
        run_id = "run_005"
        RUN_PROCS[run_id] = mock_process

        # Simulate timeout on wait, then success on kill
        import subprocess
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 2), None]

        mock_port_deallocator = MagicMock()

        result = stop_run(run_id, mock_port_deallocator)

        # Should call terminate first
        mock_process.terminate.assert_called_once()
        # Then force kill after timeout
        mock_process.kill.assert_called_once()

    def test_stop_run_updates_database(self, mock_process, mock_db):
        """Test that stopping updates database status."""
        run_id = "run_006"
        RUN_PROCS[run_id] = mock_process

        mock_port_deallocator = MagicMock()

        stop_run(run_id, mock_port_deallocator)

        # Verify database update
        mock_db.runs.update_one.assert_called()
        update_call = mock_db.runs.update_one.call_args[0]
        assert update_call[0] == {"_id": run_id}
        assert "status" in update_call[1]["$set"]

    def test_stop_run_orphaned_process(self, mock_db):
        """Test handling orphaned runs (in DB but no process)."""
        run_id = "run_007"
        # No process in RUN_PROCS

        with patch('runner.run_lifecycle.get_effective_run_status') as mock_get_status:
            mock_get_status.return_value = "running"
            mock_port_deallocator = MagicMock()

            result = stop_run(run_id, mock_port_deallocator)

            # Should update DB to stopped
            assert result == True
            mock_db.runs.update_one.assert_called()


@pytest.mark.unit
class TestForceKillRun:
    """Test force killing functionality."""

    @patch('runner.process_manager.os.name', 'posix')
    @patch('runner.process_manager.os.getpgid')
    @patch('runner.process_manager.os.killpg')
    @patch('runner.process_manager.signal')
    def test_force_kill_success(self, mock_signal, mock_killpg, mock_getpgid, mock_db, mock_process):
        """Test successful force kill."""
        run_id = "run_001"
        mock_getpgid.return_value = 12345
        RUN_PROCS[run_id] = mock_process

        mock_port_deallocator = MagicMock()

        result = force_kill_run(run_id, mock_port_deallocator)

        assert result == True
        mock_killpg.assert_called_once()
        mock_port_deallocator.assert_called_once_with(run_id)
        assert run_id not in RUN_PROCS

    def test_force_kill_no_process(self, mock_db):
        """Test force kill when process doesn't exist."""
        run_id = "run_002"
        mock_port_deallocator = MagicMock()

        result = force_kill_run(run_id, mock_port_deallocator)

        assert result == False

    def test_force_kill_updates_database(self, mock_process, mock_db):
        """Test that force kill updates database with 'killed' status."""
        run_id = "run_003"
        RUN_PROCS[run_id] = mock_process

        mock_port_deallocator = MagicMock()

        force_kill_run(run_id, mock_port_deallocator)

        # Verify database update with "killed" status
        mock_db.runs.update_one.assert_called()
        update_call = mock_db.runs.update_one.call_args[0]
        assert update_call[0] == {"_id": run_id}
        assert update_call[1]["$set"]["status"] == "killed"

    @patch('runner.process_manager.os.name', 'nt')
    def test_force_kill_windows(self, mock_db, mock_process):
        """Test force kill on Windows."""
        run_id = "run_004"
        RUN_PROCS[run_id] = mock_process

        mock_port_deallocator = MagicMock()

        result = force_kill_run(run_id, mock_port_deallocator)

        # On Windows, should use proc.kill()
        mock_process.kill.assert_called_once()


@pytest.mark.unit
class TestGetRunStatus:
    """Test status retrieval."""

    def test_get_run_status_exists(self):
        """Test getting status for existing run."""
        run_id = "run_001"
        RUN_STATUS[run_id] = "running"

        status = get_run_status(run_id)

        assert status == "running"

    def test_get_run_status_not_exists(self):
        """Test getting status for non-existent run."""
        status = get_run_status("nonexistent")

        assert status is None


@pytest.mark.unit
class TestGetActiveRuns:
    """Test retrieving active runs list."""

    def test_get_active_runs_empty(self):
        """Test getting active runs when none are running."""
        active = get_active_runs()

        assert active == []

    def test_get_active_runs_multiple(self, mock_process):
        """Test getting active runs with multiple running."""
        RUN_PROCS["run_001"] = mock_process
        RUN_PROCS["run_002"] = mock_process
        RUN_PROCS["run_003"] = mock_process

        active = get_active_runs()

        assert len(active) == 3
        assert "run_001" in active
        assert "run_002" in active
        assert "run_003" in active


@pytest.mark.unit
class TestThreadSafety:
    """Test thread safety of process operations."""

    def test_concurrent_status_updates(self, mock_process):
        """Test that concurrent status updates don't cause issues."""
        results = []

        def update_status(run_id):
            RUN_STATUS[run_id] = "running"
            time.sleep(0.001)
            results.append(RUN_STATUS.get(run_id))

        threads = []
        for i in range(10):
            t = threading.Thread(target=update_status, args=(f"run_{i:03d}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All results should be "running"
        assert all(r == "running" for r in results)
        assert len(RUN_STATUS) == 10


@pytest.mark.unit
class TestCleanupBehavior:
    """Test cleanup and resource management."""

    def test_stop_run_cleans_all_references(self, mock_process, mock_db):
        """Test that stop_run cleans up all process references."""
        run_id = "run_001"
        RUN_PROCS[run_id] = mock_process
        RUN_STATUS[run_id] = "running"
        RUN_THREADS[run_id] = MagicMock()

        mock_port_deallocator = MagicMock()

        stop_run(run_id, mock_port_deallocator)

        # All references should be cleaned
        assert run_id not in RUN_PROCS
        assert run_id not in RUN_STATUS
        assert run_id not in RUN_THREADS

    def test_force_kill_cleans_all_references(self, mock_process, mock_db):
        """Test that force_kill_run cleans up all process references."""
        run_id = "run_002"
        RUN_PROCS[run_id] = mock_process
        RUN_STATUS[run_id] = "running"
        RUN_THREADS[run_id] = MagicMock()

        mock_port_deallocator = MagicMock()

        force_kill_run(run_id, mock_port_deallocator)

        # All references should be cleaned
        assert run_id not in RUN_PROCS
        assert run_id not in RUN_STATUS
        assert run_id not in RUN_THREADS


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_stop_run_exception_during_termination(self, mock_process, mock_db):
        """Test handling exception during process termination."""
        run_id = "run_001"
        RUN_PROCS[run_id] = mock_process
        mock_process.terminate.side_effect = Exception("Termination error")

        mock_port_deallocator = MagicMock()

        result = stop_run(run_id, mock_port_deallocator)

        # Should still clean up and return False
        assert result == False
        # Should still deallocate ports
        mock_port_deallocator.assert_called()

    def test_force_kill_already_dead_process(self, mock_process, mock_db):
        """Test force kill on process that's already dead."""
        run_id = "run_002"
        RUN_PROCS[run_id] = mock_process

        # Process is already dead
        import os
        with patch('runner.process_manager.os.killpg', side_effect=ProcessLookupError):
            mock_port_deallocator = MagicMock()
            result = force_kill_run(run_id, mock_port_deallocator)

        # Should still succeed and clean up
        assert result == True
        assert run_id not in RUN_PROCS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
