# Test Strategy and Standards

### Testing Philosophy
- **Approach:** Test-driven development for critical components
- **Coverage Goals:** 90% line coverage for business logic, 80% overall
- **Test Pyramid:** 70% unit, 20% integration, 10% end-to-end

### Test Types and Organization

#### Unit Tests
- **Framework:** pytest 7.4.3 with asyncio support
- **File Convention:** `test_*.py` files parallel to source code
- **Location:** Each service has its own `tests/` directory
- **Mocking Library:** pytest-mock for dependency mocking
- **Coverage Requirement:** 90% for services, 80% for utilities

#### Integration Tests
- **Scope:** Service-to-service communication via gRPC
- **Location:** `tests/integration/` in project root
- **Test Infrastructure:**
  - **PostgreSQL:** Testcontainers for isolated database testing
  - **Redis:** Redis container for cache testing
  - **gRPC Services:** In-process servers for fast testing

#### End-to-End Tests
- **Framework:** pytest with custom voice assistant test utilities
- **Scope:** Complete voice call scenarios using SIP test clients
- **Environment:** Dedicated test environment with all services deployed
- **Test Data:** Synthetic audio files and mock banking responses

### Test Data Management
- **Strategy:** Factory pattern for test data generation
- **Fixtures:** Shared fixtures in `shared/testing/` for common data
- **Factories:** Audio sample factories, session factories, banking data factories
- **Cleanup:** Automatic cleanup after each test with proper resource disposal
