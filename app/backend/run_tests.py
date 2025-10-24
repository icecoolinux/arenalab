#!/usr/bin/env python3
"""
Test runner script for ArenaLab backend.

This script provides convenient commands to run different types of tests.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and print status."""
    print(f"\n{'='*50}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*50}")
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    return result.returncode


def run_unit_tests():
    """Run unit tests only."""
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/unit/",
        "-v",
        "--tb=short",
        "-m", "unit"
    ]
    return run_command(cmd, "Unit Tests")


def run_integration_tests():
    """Run integration tests only."""
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/integration/",
        "-v", 
        "--tb=short",
        "-m", "integration"
    ]
    return run_command(cmd, "Integration Tests")


def run_all_tests():
    """Run all tests with coverage."""
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "--cov=.",
        "--cov-report=html:htmlcov",
        "--cov-report=term-missing",
        "--cov-report=xml",
        "-v"
    ]
    return run_command(cmd, "All Tests with Coverage")


def run_specific_test(test_path):
    """Run a specific test file or test function."""
    cmd = [
        sys.executable, "-m", "pytest",
        test_path,
        "-v",
        "--tb=short"
    ]
    return run_command(cmd, f"Specific Test: {test_path}")


def lint_code():
    """Run code linting (if flake8 or similar is available)."""
    try:
        cmd = ["flake8", ".", "--exclude=venv,htmlcov,tests/__pycache__"]
        return run_command(cmd, "Code Linting")
    except FileNotFoundError:
        print("flake8 not found, skipping linting")
        return 0


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="Test runner for ArenaLab backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                    # Run all tests with coverage
  python run_tests.py --unit            # Run unit tests only
  python run_tests.py --integration     # Run integration tests only
  python run_tests.py --test tests/unit/test_experiments_service.py
  python run_tests.py --lint            # Run code linting
        """
    )
    
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--test", metavar="PATH", help="Run specific test file or function")
    parser.add_argument("--lint", action="store_true", help="Run code linting")
    parser.add_argument("--no-coverage", action="store_true", help="Skip coverage reporting")
    
    args = parser.parse_args()
    
    exit_code = 0
    
    if args.lint:
        exit_code = max(exit_code, lint_code())
    elif args.unit:
        exit_code = max(exit_code, run_unit_tests())
    elif args.integration:
        exit_code = max(exit_code, run_integration_tests())
    elif args.test:
        exit_code = max(exit_code, run_specific_test(args.test))
    else:
        # Run all tests by default
        exit_code = max(exit_code, run_all_tests())
    
    if exit_code == 0:
        print(f"\n{'='*50}")
        print("✅ All tests passed!")
        print(f"{'='*50}")
    else:
        print(f"\n{'='*50}")
        print("❌ Some tests failed!")
        print(f"{'='*50}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()