# OpenSIPS AI Voice Connector - Testing Framework

This document describes the comprehensive unit testing framework implemented for the OpenSIPS AI Voice Connector project.

## Overview

The testing framework provides comprehensive coverage for all services and core components with:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test service interactions and compatibility
- **Async/Await Support**: Full support for async gRPC patterns
- **Coverage Reporting**: 90% coverage threshold with detailed reports
- **Parallel Execution**: Fast test execution with pytest-xdist
- **Mocking**: Comprehensive mocking for external dependencies

## Test Structure

```
├── tests/                          # Global test configuration and utilities
│   ├── __init__.py
│   ├── conftest.py                 # Global fixtures and configuration
│   ├── utils.py                    # Test utilities and helpers
│   ├── integration/                # Integration tests
│   │   ├── __init__.py
│   │   └── test_service_integration.py
│   └── test_framework_validation.py
├── core/tests/                     # Core component tests
│   └── __init__.py
├── services/
│   ├── asr-service/tests/          # ASR service tests
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_asr_engine.py
│   │   └── test_asr_grpc_service.py
│   ├── llm-service/tests/          # LLM service tests
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_llm_engine.py
│   │   └── test_llm_grpc_service.py
│   └── tts-service/tests/          # TTS service tests
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_tts_engine.py
│       └── test_tts_grpc_service.py
├── scripts/                        # Test execution scripts
│   ├── run_tests.py
│   └── test_coverage.py
├── pytest.ini                     # Pytest configuration
├── run_tests.bat                   # Windows test runner
├── run_tests.sh                    # Unix test runner
└── TESTING.md                      # This documentation
```

## Running Tests

### Quick Start

```bash
# Run all tests with coverage
python scripts/run_tests.py --coverage

# Run tests for specific service
python scripts/run_tests.py --service asr --coverage

# Run tests in parallel
python scripts/run_tests.py --parallel --coverage
```

### Using Platform Scripts

**Windows:**
```cmd
run_tests.bat --coverage --parallel
```

**Unix/Linux/macOS:**
```bash
./run_tests.sh --coverage --parallel
```

### Direct pytest Usage

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov=services --cov-report=term-missing --cov-report=html

# Run specific test types
pytest -m unit                    # Unit tests only
pytest -m integration            # Integration tests only
pytest -m grpc                   # gRPC-related tests only

# Run specific service tests
pytest services/asr-service/tests/
pytest services/llm-service/tests/
pytest services/tts-service/tests/

# Run tests in parallel
pytest -n auto                   # Use all CPU cores
pytest -n 4                      # Use 4 workers
```

## Test Categories

### Unit Tests (`@pytest.mark.unit`)

Test individual components in isolation:

- **ASR Engine Tests**: Vosk model loading, audio processing, recognition
- **LLM Engine Tests**: Model loading, text generation, streaming
- **TTS Engine Tests**: Piper model loading, audio synthesis, chunking
- **gRPC Service Tests**: Service implementations, request handling, error cases

### Integration Tests (`@pytest.mark.integration`)

Test component interactions:

- **Service Integration**: gRPC client compatibility
- **Configuration Integration**: Settings and environment variables
- **Pipeline Integration**: End-to-end data flow
- **Protocol Compatibility**: Protobuf message compatibility

### Specialized Markers

- `@pytest.mark.grpc`: Tests requiring gRPC services
- `@pytest.mark.audio`: Tests involving audio processing
- `@pytest.mark.slow`: Tests that may take more than 10 seconds
- `@pytest.mark.network`: Tests requiring network connectivity

## Test Fixtures

### Global Fixtures (tests/conftest.py)

- `mock_config`: Mock configuration for services
- `mock_logger`: Mock logger instance
- `sample_audio_data`: Generated audio data for testing
- `sample_text`: Sample text for processing
- `grpc_channel`: Mock gRPC channel
- `mock_*_stub`: Mock gRPC service stubs

### Service-Specific Fixtures

**ASR Service:**
- `mock_vosk_model`: Mock Vosk model
- `mock_vosk_recognizer`: Mock Vosk recognizer
- `sample_audio_chunk`: Audio data for testing

**LLM Service:**
- `mock_llama_model`: Mock Llama model
- `sample_llm_request`: Sample request data
- `banking_context`: Banking conversation context

**TTS Service:**
- `mock_piper_voice`: Mock Piper voice
- `sample_tts_request`: Sample synthesis request
- `turkish_text_samples`: Turkish text for testing

## Test Utilities

### TestDataFactory

```python
from tests.utils import TestDataFactory

# Create sample audio data
audio = TestDataFactory.create_audio_data(sample_rate=16000, duration=1.0)

# Create conversation history
history = TestDataFactory.create_conversation_history()

# Create session context
context = TestDataFactory.create_session_context()
```

### AsyncMockHelper

```python
from tests.utils import AsyncMockHelper

# Create async iterator
async_iter = AsyncMockHelper.create_async_iterator(['item1', 'item2'])

# Create gRPC stream response
stream = AsyncMockHelper.create_grpc_stream_response([response1, response2])
```

### GrpcTestHelper

```python
from tests.utils import GrpcTestHelper

# Create mock health response
health = GrpcTestHelper.create_health_response("SERVING", "OK")

# Create mock transcription response
transcription = GrpcTestHelper.create_transcription_response("hello world")

# Create mock synthesis response
synthesis = GrpcTestHelper.create_synthesis_response(audio_data)
```

## Coverage Requirements

### Coverage Threshold

- **Minimum Coverage**: 90%
- **Coverage Scope**: `core/` and `services/` directories
- **Reports**: Terminal, XML, and HTML formats

### Coverage Analysis

```bash
# Run coverage analysis
python scripts/test_coverage.py

# Generate detailed report
python scripts/test_coverage.py --run-tests

# View HTML report
open htmlcov/index.html
```

### Coverage Reports

- **Terminal Report**: Shows line-by-line coverage
- **XML Report**: `coverage.xml` for CI/CD integration
- **HTML Report**: `htmlcov/index.html` for detailed analysis

## Mocking Strategy

### External Dependencies

All external dependencies are mocked:

- **Vosk Models**: Mock model loading and recognition
- **Llama Models**: Mock model loading and generation
- **Piper Models**: Mock voice loading and synthesis
- **gRPC Channels**: Mock network communication
- **File System**: Mock model files and configurations

### Mock Patterns

```python
# Service engine mocking
@patch('service_module.ExternalEngine')
def test_with_mocked_engine(mock_engine):
    mock_engine.return_value.process.return_value = "result"
    # Test implementation

# Async method mocking
@pytest.mark.asyncio
async def test_async_method():
    mock_service = AsyncMock()
    mock_service.process.return_value = "async_result"
    result = await mock_service.process()
    assert result == "async_result"

# gRPC streaming mocking
async def mock_stream():
    for item in ["chunk1", "chunk2", "chunk3"]:
        yield item

mock_service.stream_method = mock_stream
```

## Async Testing

### Async Test Functions

```python
@pytest.mark.asyncio
async def test_async_function():
    """Test async functionality."""
    result = await async_function()
    assert result == expected_value
```

### Async Fixtures

```python
@pytest.fixture
async def async_service():
    """Async fixture for service setup."""
    service = await create_service()
    yield service
    await service.cleanup()
```

### Async Context Managers

```python
@pytest.mark.asyncio
async def test_async_context():
    async with mock_grpc_channel() as channel:
        # Test with channel
        assert channel is not None
```

## Performance Testing

### Performance Helpers

```python
from tests.utils import PerformanceTestHelper

@pytest.mark.asyncio
async def test_performance():
    result, execution_time = await PerformanceTestHelper.measure_execution_time(
        async_operation()
    )
    
    # Assert performance requirements
    PerformanceTestHelper.assert_execution_time(execution_time, max_time=1.0)
```

### Timeout Testing

```python
from tests.utils import AsyncTestCase

@pytest.mark.asyncio
async def test_with_timeout():
    result = await AsyncTestCase.run_with_timeout(
        long_running_operation(),
        timeout=5.0
    )
    assert result == expected_value
```

## Continuous Integration

### CI Configuration

```yaml
# Example GitHub Actions configuration
- name: Run Tests
  run: |
    python scripts/run_tests.py --coverage --parallel --fail-fast
    
- name: Upload Coverage
  uses: codecov/codecov-action@v1
  with:
    file: ./coverage.xml
```

### Coverage Reports

- **XML Format**: Compatible with most CI/CD systems
- **Badge Generation**: Coverage badges for README
- **Trend Analysis**: Coverage trend tracking

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure all dependencies are installed
   pip install -r requirements.txt
   ```

2. **Async Test Issues**
   ```bash
   # Ensure pytest-asyncio is installed
   pip install pytest-asyncio
   ```

3. **Coverage Issues**
   ```bash
   # Ensure pytest-cov is installed
   pip install pytest-cov
   ```

4. **Parallel Execution Issues**
   ```bash
   # Ensure pytest-xdist is installed
   pip install pytest-xdist
   ```

### Debug Mode

```bash
# Run tests with verbose output and no capture
pytest -v -s

# Run specific test with debugging
pytest -v -s tests/test_specific.py::test_function_name

# Run with Python debugger
pytest --pdb
```

## Best Practices

### Writing Tests

1. **Test Structure**: Arrange, Act, Assert
2. **Test Independence**: Each test should be independent
3. **Meaningful Names**: Use descriptive test names
4. **Mock External**: Mock all external dependencies
5. **Test Edge Cases**: Include error conditions and edge cases

### Async Testing

1. **Use pytest.mark.asyncio**: Mark async test functions
2. **Await All Async**: Properly await all async operations
3. **Mock Async Dependencies**: Use AsyncMock for async mocks
4. **Timeout Protection**: Set reasonable timeouts

### Performance

1. **Parallel Execution**: Use `-n auto` for faster testing
2. **Test Selection**: Use markers to run specific test subsets
3. **Mock Heavy Operations**: Mock expensive operations
4. **Cleanup Resources**: Properly cleanup test resources

## Examples

### Complete Test Example

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_asr_service_streaming(asr_service_impl, mock_grpc_context, sample_audio_chunk):
    """Test ASR service streaming recognition."""
    
    # Arrange
    async def request_generator():
        config_request = asr_service_pb2.StreamingRecognizeRequest()
        config_request.config.sample_rate = 16000
        yield config_request
        
        audio_request = asr_service_pb2.StreamingRecognizeRequest()
        audio_request.audio_data = sample_audio_chunk
        yield audio_request
    
    # Mock the engine response
    with patch.object(asr_service_impl.vosk_engine, 'process_audio_chunk') as mock_process:
        mock_process.return_value = {"text": "hello world"}
        
        # Act
        responses = []
        async for response in asr_service_impl.StreamingRecognize(
            request_generator(), 
            mock_grpc_context
        ):
            responses.append(response)
        
        # Assert
        assert len(responses) > 0
        assert any(r.result.text == "hello world" for r in responses)
        mock_process.assert_called_once()
```

This testing framework ensures comprehensive coverage and reliability for the OpenSIPS AI Voice Connector services.