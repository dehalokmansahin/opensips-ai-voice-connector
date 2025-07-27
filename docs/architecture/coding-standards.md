# Coding Standards

### Core Standards
- **Languages & Runtimes:** Python 3.11.7 with type hints mandatory
- **Style & Linting:** Black formatter, Ruff linter, mypy type checking
- **Test Organization:** `tests/` directory parallel to `src/`, pytest framework

### Critical Rules
- **Logging:** Never use `print()` in production code - use structured logger
- **gRPC Responses:** All gRPC responses must include correlation IDs
- **Error Handling:** Catch specific exceptions, never bare `except:`
- **Audio Processing:** Always specify audio format and sample rate explicitly
- **Context Management:** Use async context managers for resource cleanup
