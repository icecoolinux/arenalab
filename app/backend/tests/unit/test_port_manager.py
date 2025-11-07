"""
Unit tests for port_manager module.

Tests port allocation, deallocation, and conflict resolution.
"""

import pytest
from unittest.mock import patch

from runner.port_manager import allocate_ports, deallocate_ports, get_allocated_ports, RUN_PORTS


@pytest.fixture(autouse=True)
def clean_port_state():
    """Clean port state before and after each test."""
    RUN_PORTS.clear()
    yield
    RUN_PORTS.clear()


@pytest.mark.unit
class TestPortAllocation:
    """Test port allocation functionality."""

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 10)
    def test_allocate_ports_first_run(self):
        """Test allocating ports for the first run."""
        run_id = "run_001"
        num_envs = 5

        base_port = allocate_ports(run_id, num_envs)

        # Should get PORT_BASE
        assert base_port == 5000
        # Should be stored in RUN_PORTS
        assert run_id in RUN_PORTS
        assert RUN_PORTS[run_id] == (5000, 5)

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 10)
    def test_allocate_ports_multiple_runs(self):
        """Test allocating ports for multiple concurrent runs."""
        # First run
        port1 = allocate_ports("run_001", 5)
        assert port1 == 5000

        # Second run - should get next available range
        # run_001 uses 5000-5004, with spacing 10, next available is 5015
        port2 = allocate_ports("run_002", 3)
        assert port2 == 5015

        # Third run
        port3 = allocate_ports("run_003", 2)
        assert port3 == 5028

        # Verify all runs are tracked
        assert len(RUN_PORTS) == 3

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 10)
    def test_allocate_ports_fills_gaps(self):
        """Test that port allocation fills gaps when runs are deallocated."""
        # Allocate three runs
        port1 = allocate_ports("run_001", 5)
        port2 = allocate_ports("run_002", 3)
        port3 = allocate_ports("run_003", 2)

        assert port1 == 5000
        assert port2 == 5015
        assert port3 == 5028

        # Deallocate middle run
        deallocate_ports("run_002")

        # Allocate new run - should use the gap left by run_002
        port4 = allocate_ports("run_004", 2)
        # run_004 (2 envs) should fit in the gap (5015-5024)
        assert port4 == 5015

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 10)
    def test_allocate_ports_reallocation_same_run(self):
        """Test reallocating ports for the same run."""
        run_id = "run_001"

        # Initial allocation
        port1 = allocate_ports(run_id, 5)
        assert port1 == 5000

        # Reallocate same run (should replace)
        port2 = allocate_ports(run_id, 3)

        # Should still be in RUN_PORTS with new allocation
        assert run_id in RUN_PORTS
        assert RUN_PORTS[run_id][1] == 3

    @patch('runner.port_manager.PORT_BASE', 5000)
    def test_allocate_ports_zero_envs(self):
        """Test allocating ports with zero environments."""
        run_id = "run_001"
        base_port = allocate_ports(run_id, 0)

        assert base_port == 5000
        assert RUN_PORTS[run_id] == (5000, 0)


@pytest.mark.unit
class TestPortDeallocation:
    """Test port deallocation functionality."""

    @patch('runner.port_manager.PORT_BASE', 5000)
    def test_deallocate_ports_success(self):
        """Test successful port deallocation."""
        run_id = "run_001"
        allocate_ports(run_id, 5)

        # Verify allocated
        assert run_id in RUN_PORTS

        # Deallocate
        deallocate_ports(run_id)

        # Verify removed
        assert run_id not in RUN_PORTS

    def test_deallocate_ports_nonexistent_run(self):
        """Test deallocating ports for non-existent run (should not error)."""
        # Should not raise error
        deallocate_ports("nonexistent_run")

    @patch('runner.port_manager.PORT_BASE', 5000)
    def test_deallocate_ports_twice(self):
        """Test deallocating ports twice (idempotent)."""
        run_id = "run_001"
        allocate_ports(run_id, 5)

        deallocate_ports(run_id)
        assert run_id not in RUN_PORTS

        # Deallocate again - should not error
        deallocate_ports(run_id)
        assert run_id not in RUN_PORTS


@pytest.mark.unit
class TestGetAllocatedPorts:
    """Test retrieving allocated port information."""

    @patch('runner.port_manager.PORT_BASE', 5000)
    def test_get_allocated_ports_exists(self):
        """Test getting allocated ports for existing run."""
        run_id = "run_001"
        allocate_ports(run_id, 5)

        base_port, num_envs = get_allocated_ports(run_id)

        assert base_port == 5000
        assert num_envs == 5

    def test_get_allocated_ports_nonexistent(self):
        """Test getting allocated ports for non-existent run."""
        base_port, num_envs = get_allocated_ports("nonexistent_run")

        # Should return (0, 0) for non-existent run
        assert base_port == 0
        assert num_envs == 0


@pytest.mark.unit
class TestPortThreadSafety:
    """Test thread safety of port allocation."""

    @patch('runner.port_manager.PORT_BASE', 5000)
    def test_concurrent_allocations(self):
        """Test that concurrent allocations don't create conflicts."""
        import threading

        results = []

        def allocate_for_run(run_id, num_envs):
            port = allocate_ports(run_id, num_envs)
            results.append((run_id, port))

        # Create multiple threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=allocate_for_run, args=(f"run_{i:03d}", 3))
            threads.append(t)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Verify all allocations are unique
        ports = [port for _, port in results]
        assert len(ports) == len(set(ports)), "Ports should be unique"

        # Verify all runs are tracked
        assert len(RUN_PORTS) == 10


@pytest.mark.unit
class TestPortRangeCalculation:
    """Test port range calculation logic."""

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 10)
    def test_large_environment_count(self):
        """Test allocating ports for runs with many environments."""
        # Large number of environments
        port1 = allocate_ports("run_001", 100)
        assert port1 == 5000

        # Second run should skip the large range
        port2 = allocate_ports("run_002", 5)
        # run_001 uses 5000-5099, with spacing 10, next is 5110
        assert port2 == 5110

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 0)
    def test_zero_spacing(self):
        """Test port allocation with zero spacing."""
        port1 = allocate_ports("run_001", 5)
        assert port1 == 5000

        port2 = allocate_ports("run_002", 3)
        # With zero spacing, should be immediately after run_001
        # run_001 uses 5000-5004, run_002 starts at 5005
        assert port2 == 5005

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 10)
    def test_gap_too_small_for_allocation(self):
        """Test that allocation skips gaps that are too small."""
        # Create two runs with a small gap
        port1 = allocate_ports("run_001", 5)  # Uses 5000-5004 (+ 10 spacing = 5014)
        port2 = allocate_ports("run_002", 100)  # Uses 5015-5114 (+ 10 spacing = 5124)

        assert port1 == 5000
        assert port2 == 5015

        # Deallocate first run (creates gap of size 5 + 10 = 15)
        deallocate_ports("run_001")

        # Try to allocate run needing more than 15 ports
        # Should skip the small gap and go after run_002
        port3 = allocate_ports("run_003", 20)
        assert port3 == 5125  # After run_002's range


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('runner.port_manager.PORT_BASE', 5000)
    def test_empty_run_id(self):
        """Test allocation with empty run_id."""
        port = allocate_ports("", 5)
        assert port == 5000
        assert "" in RUN_PORTS

    @patch('runner.port_manager.PORT_BASE', 5000)
    def test_single_environment(self):
        """Test allocation for single environment."""
        port = allocate_ports("run_001", 1)
        assert port == 5000
        assert RUN_PORTS["run_001"] == (5000, 1)

    @patch('runner.port_manager.PORT_BASE', 5000)
    @patch('runner.port_manager.PORT_SPACING', 10)
    def test_multiple_deallocations_create_gaps(self):
        """Test that multiple deallocations create multiple gaps."""
        # Allocate 5 runs
        for i in range(5):
            allocate_ports(f"run_{i}", 3)

        # Deallocate odd-numbered runs
        for i in [1, 3]:
            deallocate_ports(f"run_{i}")

        # Verify remaining runs
        assert len(RUN_PORTS) == 3
        assert "run_0" in RUN_PORTS
        assert "run_2" in RUN_PORTS
        assert "run_4" in RUN_PORTS

        # New allocation should fill first gap
        port = allocate_ports("run_new", 2)
        # run_1's gap starts at 5013
        assert port == 5013


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
