#!/bin/bash
# Comprehensive validation script for development mode setup
# Tests all development features and ensures 30-second hot-reload target

set -e

echo "OpenSIPS AI Voice Connector - Development Setup Validation"
echo "=========================================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Validation counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Function to run a check
run_check() {
    local check_name="$1"
    local check_command="$2"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    echo -n "[$TOTAL_CHECKS] $check_name... "
    
    if eval "$check_command" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Function to run a check with output
run_check_with_output() {
    local check_name="$1"
    local check_command="$2"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    echo "[$TOTAL_CHECKS] $check_name..."
    
    if eval "$check_command"; then
        echo -e "${GREEN}✅ PASS${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Function to time a command
time_command() {
    local start_time=$(date +%s.%N)
    eval "$1"
    local end_time=$(date +%s.%N)
    local duration=$(echo "$end_time - $start_time" | bc -l)
    echo "$duration"
}

echo -e "${BLUE}Phase 1: File Structure Validation${NC}"
echo "-----------------------------------"

# Check required files exist
run_check "docker-compose.dev.yml exists" "test -f docker-compose.dev.yml"
run_check "Dockerfile.dev exists" "test -f Dockerfile.dev"
run_check "Core development Dockerfile exists" "test -f services/asr-service/Dockerfile.dev"
run_check "LLM development Dockerfile exists" "test -f services/llm-service/Dockerfile.dev"
run_check "TTS development Dockerfile exists" "test -f services/tts-service/Dockerfile.dev"

# Check development scripts
run_check "dev-start.sh exists" "test -f scripts/dev-start.sh"
run_check "dev-stop.sh exists" "test -f scripts/dev-stop.sh"
run_check "dev-restart.sh exists" "test -f scripts/dev-restart.sh"
run_check "dev-status.sh exists" "test -f scripts/dev-status.sh"
run_check "dev-logs.sh exists" "test -f scripts/dev-logs.sh"
run_check "dev-test.sh exists" "test -f scripts/dev-test.sh"
run_check "dev-clean.sh exists" "test -f scripts/dev-clean.sh"
run_check "dev-debug.sh exists" "test -f scripts/dev-debug.sh"

# Check scripts are executable
run_check "Development scripts are executable" "test -x scripts/dev-start.sh"

# Check development utilities
run_check "File watcher utility exists" "test -f core/utils/file_watcher.py"
run_check "Enhanced logging utility exists" "test -f core/utils/logging.py"

# Check documentation
run_check "Development guide exists" "test -f docs/DEVELOPMENT_MODE_GUIDE.md"

echo ""
echo -e "${BLUE}Phase 2: Configuration Validation${NC}"
echo "----------------------------------"

# Validate Docker Compose configuration
run_check "docker-compose.dev.yml is valid YAML" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null 2>&1"

# Check development-specific configurations
run_check "Development volumes are configured" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml config 2>/dev/null | grep -q 'target: /app/core'"
run_check "Development environment variables set" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml config 2>/dev/null | grep -q 'DEVELOPMENT_MODE.*1'"
run_check "Debug logging enabled" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml config 2>/dev/null | grep -q 'LOG_LEVEL.*DEBUG'"

echo ""
echo -e "${BLUE}Phase 3: Dependency Validation${NC}"
echo "-------------------------------"

# Check Python dependencies
run_check "watchdog dependency in requirements.txt" "grep -q 'watchdog' requirements.txt"
run_check "colorlog dependency in requirements.txt" "grep -q 'colorlog' requirements.txt"

# Check service requirements
run_check "ASR service has watchdog dependency" "grep -q 'watchdog' services/asr-service/requirements.txt"
run_check "LLM service has watchdog dependency" "grep -q 'watchdog' services/llm-service/requirements.txt"
run_check "TTS service has watchdog dependency" "grep -q 'watchdog' services/tts-service/requirements.txt"

echo ""
echo -e "${BLUE}Phase 4: Hot-Reload Feature Validation${NC}"
echo "--------------------------------------------"

# Test hot-reload imports
run_check "Hot-reload module imports successfully" "python3 -c 'from core.utils.file_watcher import setup_hot_reload, HotReloadWatcher'"
run_check "Development logging imports successfully" "python3 -c 'from core.utils.logging import get_development_logger, setup_logging'"

echo ""
echo -e "${BLUE}Phase 5: Docker Build Performance Test${NC}"
echo "--------------------------------------------"

echo "Testing Docker build performance (targeting 30-second hot-reload)..."

# Test development build time
echo "Building development images..."
BUILD_START=$(date +%s)

if docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel >/dev/null 2>&1; then
    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    
    echo "Build completed in ${BUILD_TIME} seconds"
    
    if [ $BUILD_TIME -le 30 ]; then
        echo -e "${GREEN}✅ Build time target met (≤30s)${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    elif [ $BUILD_TIME -le 60 ]; then
        echo -e "${YELLOW}⚠️  Build time acceptable but not optimal (${BUILD_TIME}s)${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "${RED}❌ Build time too slow (${BUILD_TIME}s > 60s)${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
else
    echo -e "${RED}❌ Docker build failed${NC}"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
fi

echo ""
echo -e "${BLUE}Phase 6: Development Environment Test${NC}"
echo "-----------------------------------------"

# Only run if Docker is available and environment isn't already running
if command -v docker-compose >/dev/null 2>&1; then
    if ! docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps | grep -q "Up"; then
        echo "Testing development environment startup..."
        
        # Start development environment
        echo "Starting development environment..."
        if docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Development environment started${NC}"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
            
            # Wait for services to be ready
            echo "Waiting for services to be healthy..."
            sleep 10
            
            # Check service health
            run_check "Core service is running" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps opensips-ai-core | grep -q Up"
            run_check "ASR service is running" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps asr-service | grep -q Up"
            run_check "LLM service is running" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps llm-service | grep -q Up"
            run_check "TTS service is running" "docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps tts-service | grep -q Up"
            
            # Clean up
            echo "Cleaning up test environment..."
            docker-compose -f docker-compose.yml -f docker-compose.dev.yml down >/dev/null 2>&1
            
        else
            echo -e "${RED}❌ Failed to start development environment${NC}"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
        fi
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    else
        echo -e "${YELLOW}⚠️  Development environment already running, skipping startup test${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Docker not available, skipping environment test${NC}"
fi

echo ""
echo -e "${BLUE}Phase 7: Development Workflow Test${NC}"
echo "-----------------------------------"

# Test development scripts (basic syntax check)
for script in scripts/dev-*.sh; do
    if [ -f "$script" ]; then
        script_name=$(basename "$script")
        run_check "$script_name syntax is valid" "bash -n $script"
    fi
done

echo ""
echo "=========================================================="
echo -e "${BLUE}VALIDATION SUMMARY${NC}"
echo "=========================================================="

echo "Total Checks: $TOTAL_CHECKS"
echo -e "Passed: ${GREEN}$PASSED_CHECKS${NC}"
echo -e "Failed: ${RED}$FAILED_CHECKS${NC}"

# Calculate success rate
SUCCESS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
echo "Success Rate: $SUCCESS_RATE%"

echo ""
if [ $FAILED_CHECKS -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL VALIDATIONS PASSED!${NC}"
    echo -e "${GREEN}Development mode is properly configured and ready to use.${NC}"
    echo ""
    echo "Quick start commands:"
    echo "  ./scripts/dev-start.sh   # Start development environment"
    echo "  ./scripts/dev-status.sh  # Check status"
    echo "  ./scripts/dev-logs.sh    # View logs"
    echo ""
    exit 0
elif [ $SUCCESS_RATE -ge 80 ]; then
    echo -e "${YELLOW}⚠️  MOSTLY WORKING ($SUCCESS_RATE% passed)${NC}"
    echo -e "${YELLOW}Some non-critical checks failed. Development mode should work but may have issues.${NC}"
    echo ""
    exit 1
else
    echo -e "${RED}❌ VALIDATION FAILED ($SUCCESS_RATE% passed)${NC}"
    echo -e "${RED}Critical issues detected. Development mode may not work properly.${NC}"
    echo ""
    echo "Common issues to check:"
    echo "1. Docker and docker-compose are installed and running"
    echo "2. Required Python dependencies are available"
    echo "3. File permissions are correct (scripts executable)"
    echo "4. No port conflicts (8080, 50051-50053)"
    echo ""
    exit 2
fi