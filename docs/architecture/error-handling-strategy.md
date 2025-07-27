# Error Handling Strategy

### General Approach

- **Error Model:** Structured exceptions with correlation IDs for tracing
- **Exception Hierarchy:** Custom banking exceptions, AI processing errors, network failures
- **Error Propagation:** gRPC status codes with detailed error messages

### Logging Standards

- **Library:** Python stdlib logging with structured JSON format
- **Format:** `{"timestamp": "ISO8601", "level": "INFO", "correlation_id": "uuid", "service": "service-name", "message": "log message"}`
- **Levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL with appropriate usage
- **Required Context:**
  - Correlation ID: UUID per request for distributed tracing
  - Service Context: Service name, version, instance ID
  - User Context: Session ID, call ID (no PII in logs)

### Error Handling Patterns

#### External API Errors
- **Retry Policy:** Exponential backoff with jitter, max 3 retries
- **Circuit Breaker:** Open after 5 consecutive failures, half-open after 30s
- **Timeout Configuration:** 5s for banking APIs, 10s for cloud AI services
- **Error Translation:** Map external error codes to internal error types

#### Business Logic Errors
- **Custom Exceptions:** BankingError, AuthenticationError, IntentNotFoundError
- **User-Facing Errors:** Friendly messages without technical details
- **Error Codes:** Structured error codes for client error handling

#### Data Consistency
- **Transaction Strategy:** Database transactions for session state changes
- **Compensation Logic:** Cleanup procedures for failed AI processing
- **Idempotency:** UUID-based idempotent operations for critical flows
