#!/bin/bash

# Comprehensive Test Runner Script
set -e

echo "🧪 Running comprehensive test suite..."

# Check if virtual environment is active
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ Virtual environment detected: $VIRTUAL_ENV"
else
    echo "⚠️ No virtual environment detected. Consider using one."
fi

# Ensure dependencies are installed
echo "📦 Checking test dependencies..."
pip install -e ".[dev]" --quiet

# Code quality checks
echo "🔍 Running code quality checks..."

echo "  → Black code formatting check..."
black --check --diff . || {
    echo "❌ Code formatting issues found. Run 'black .' to fix."
    exit 1
}

echo "  → Ruff linting check..."
ruff check . || {
    echo "❌ Linting issues found. Run 'ruff check --fix .' to fix."
    exit 1
}

echo "  → MyPy type checking..."
mypy services/ shared/ || {
    echo "❌ Type checking issues found."
    exit 1
}

echo "✅ Code quality checks passed"

# Unit tests
echo "🧪 Running unit tests..."
pytest tests/ -v --tb=short --cov=services --cov=shared --cov-report=term-missing

# Integration tests (if services are running)
echo "🔗 Checking for running services..."
if docker-compose -f infrastructure/docker/docker-compose.dev.yml ps | grep -q "Up"; then
    echo "🧪 Running integration tests..."
    pytest tests/integration/ -v --tb=short
else
    echo "⚠️ Services not running, skipping integration tests"
    echo "   Start services with: docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d"
fi

# Performance tests (optional)
if [ "$RUN_PERFORMANCE_TESTS" = "true" ]; then
    echo "⚡ Running performance tests..."
    pytest tests/performance/ -v --tb=short
else
    echo "ℹ️ Skipping performance tests (set RUN_PERFORMANCE_TESTS=true to include)"
fi

# Security checks
if command -v bandit &> /dev/null; then
    echo "🔒 Running security checks..."
    bandit -r services/ shared/ -f json -o security-report.json || {
        echo "⚠️ Security issues found. Check security-report.json"
    }
else
    echo "ℹ️ Bandit not installed, skipping security checks"
fi

# Generate test report
echo "📊 Generating test report..."
echo "Test Summary:" > test-report.txt
echo "============" >> test-report.txt
echo "Date: $(date)" >> test-report.txt
echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'No git')" >> test-report.txt
echo "" >> test-report.txt

# Check test coverage
coverage report --show-missing >> test-report.txt 2>/dev/null || echo "Coverage report not available" >> test-report.txt

echo ""
echo "🎉 Test suite completed successfully!"
echo "📊 Test report saved to test-report.txt"
echo ""

# Display quick summary
echo "Summary:"
echo "✅ Code quality checks: PASSED"
echo "✅ Unit tests: PASSED"
if docker-compose -f infrastructure/docker/docker-compose.dev.yml ps | grep -q "Up"; then
    echo "✅ Integration tests: PASSED"
else
    echo "⚠️ Integration tests: SKIPPED (services not running)"
fi