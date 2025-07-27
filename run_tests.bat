@echo off
REM Windows batch script to run OpenSIPS AI Voice Connector tests

echo OpenSIPS AI Voice Connector - Test Execution
echo =============================================

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM Check if required packages are installed
python -c "import pytest" >nul 2>&1
if errorlevel 1 (
    echo Error: pytest is not installed. Run: pip install -r requirements.txt
    exit /b 1
)

REM Set default arguments
set TEST_ARGS=

REM Parse command line arguments
:parse_args
if "%1"=="" goto run_tests
if "%1"=="--coverage" (
    set TEST_ARGS=%TEST_ARGS% --coverage
    shift
    goto parse_args
)
if "%1"=="--parallel" (
    set TEST_ARGS=%TEST_ARGS% --parallel
    shift
    goto parse_args
)
if "%1"=="--unit" (
    set TEST_ARGS=%TEST_ARGS% --unit
    shift
    goto parse_args
)
if "%1"=="--integration" (
    set TEST_ARGS=%TEST_ARGS% --integration
    shift
    goto parse_args
)
if "%1"=="--service" (
    set TEST_ARGS=%TEST_ARGS% --service %2
    shift
    shift
    goto parse_args
)
if "%1"=="--verbose" (
    set TEST_ARGS=%TEST_ARGS% --verbose
    shift
    goto parse_args
)
if "%1"=="--help" (
    echo Usage: run_tests.bat [options]
    echo.
    echo Options:
    echo   --coverage      Run with coverage reporting
    echo   --parallel      Run tests in parallel
    echo   --unit          Run only unit tests
    echo   --integration   Run only integration tests
    echo   --service NAME  Run tests for specific service (asr, llm, tts, core)
    echo   --verbose       Verbose output
    echo   --help          Show this help message
    exit /b 0
)
shift
goto parse_args

:run_tests
REM Run the Python test script
python scripts\run_tests.py %TEST_ARGS%

echo.
echo Test execution completed.
echo Check the output above for results and coverage information.