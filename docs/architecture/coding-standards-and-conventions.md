# Coding Standards and Conventions

### Existing Standards Compliance
**Code Style:** Follow existing Python PEP 8 style guide, maintain existing import organization patterns, preserve existing error handling patterns

**Linting Rules:** Extend existing linting configuration for new services, maintain consistency with current code quality standards

**Testing Patterns:** Follow existing pytest patterns, extend existing test organization structure, maintain existing test coverage requirements

**Documentation Style:** Follow existing docstring patterns, maintain README structure for new services

### Enhancement-Specific Standards
- **Intent Classification Standards:** Consistent confidence score handling (0.0-1.0 range), standardized intent label naming conventions
- **Test Scenario Format Standards:** JSON schema validation for test steps, consistent timeout and retry handling
- **API Response Standards:** Standardized error response format across all new services

### Critical Integration Rules
- **Existing API Compatibility:** Preserve ASR/TTS service interfaces unchanged during integration
- **Database Integration:** Use SQLite transactions for all test data operations, maintain data consistency across service boundaries
- **Error Handling Integration:** Implement graceful degradation when external IVR systems are unreachable, maintain existing error logging patterns
- **Logging Consistency:** Extend existing structured logging approach to new services, maintain log level configuration patterns
