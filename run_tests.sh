#!/bin/bash
# Unix shell script to run OpenSIPS AI Voice Connector tests

set -e

echo "OpenSIPS AI Voice Connector - Test Execution"
echo "============================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if required packages are installed
if ! python3 -c "import pytest" &> /dev/null; then
    echo "Error: pytest is not installed. Run: pip install -r requirements.txt"
    exit 1
fi

# Function to show help
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --coverage      Run with coverage reporting"
    echo "  --parallel      Run tests in parallel"
    echo "  --unit          Run only unit tests"
    echo "  --integration   Run only integration tests"
    echo "  --service NAME  Run tests for specific service (asr, llm, tts, core)"
    echo "  --verbose       Verbose output"
    echo "  --help          Show this help message"
}

# Parse command line arguments
TEST_ARGS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage)
            TEST_ARGS="$TEST_ARGS --coverage"
            shift
            ;;
        --parallel)
            TEST_ARGS="$TEST_ARGS --parallel"
            shift
            ;;
        --unit)
            TEST_ARGS="$TEST_ARGS --unit"
            shift
            ;;
        --integration)
            TEST_ARGS="$TEST_ARGS --integration"
            shift
            ;;
        --service)
            TEST_ARGS="$TEST_ARGS --service $2"
            shift 2
            ;;
        --verbose)
            TEST_ARGS="$TEST_ARGS --verbose"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Run the Python test script
python3 scripts/run_tests.py $TEST_ARGS

echo ""
echo "Test execution completed."
echo "Check the output above for results and coverage information."