#!/usr/bin/env python3
"""
Test execution script for OpenSIPS AI Voice Connector
Provides comprehensive test execution with coverage reporting
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
import time


def main():
    """Main test execution function."""
    parser = argparse.ArgumentParser(description="Run tests for OpenSIPS AI Voice Connector")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage reporting")
    parser.add_argument("--parallel", "-p", action="store_true", help="Run tests in parallel")
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--service", choices=["asr", "llm", "tts", "core"], help="Run tests for specific service")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--fail-fast", "-x", action="store_true", help="Stop on first failure")
    parser.add_argument("--html-report", action="store_true", help="Generate HTML coverage report")
    
    args = parser.parse_args()
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add coverage if requested
    if args.coverage:
        cmd.extend([
            "--cov=core",
            "--cov=services",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml",
            "--cov-fail-under=90"
        ])
        
        if args.html_report:
            cmd.append("--cov-report=html:htmlcov")
    
    # Add parallel execution
    if args.parallel:
        cpu_count = os.cpu_count() or 2
        cmd.extend(["-n", str(min(cpu_count, 4))])  # Limit to 4 workers max
    
    # Add test type filtering
    if args.unit:
        cmd.extend(["-m", "unit"])
    elif args.integration:
        cmd.extend(["-m", "integration"])
    
    # Add service-specific filtering
    if args.service:
        if args.service == "core":
            cmd.extend(["core/tests/", "tests/"])
        else:
            cmd.append(f"services/{args.service}-service/tests/")
    
    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    
    # Add fail-fast
    if args.fail_fast:
        cmd.append("-x")
    
    # Add other pytest options
    cmd.extend([
        "--tb=short",
        "--asyncio-mode=auto",
        "--timeout=30"
    ])
    
    print("Running OpenSIPS AI Voice Connector Tests")
    print("=" * 50)
    print(f"Command: {' '.join(cmd)}")
    print()
    
    # Run the tests
    start_time = time.time()
    try:
        result = subprocess.run(cmd, check=False)
        execution_time = time.time() - start_time
        
        print()
        print("=" * 50)
        print(f"Test execution completed in {execution_time:.2f} seconds")
        
        if result.returncode == 0:
            print("✅ All tests passed!")
        else:
            print(f"❌ Tests failed with exit code {result.returncode}")
        
        # Show coverage summary if coverage was enabled
        if args.coverage and result.returncode == 0:
            print()
            print("Coverage report generated:")
            print("- Terminal report: shown above")
            print("- XML report: coverage.xml")
            if args.html_report:
                print("- HTML report: htmlcov/index.html")
        
        return result.returncode
        
    except KeyboardInterrupt:
        print("\n❌ Test execution interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())