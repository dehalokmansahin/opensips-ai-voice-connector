# Security

### Input Validation
- **Validation Library:** Pydantic for data validation and serialization
- **Validation Location:** At gRPC service boundaries before processing
- **Required Rules:**
  - All external inputs MUST be validated against schemas
  - Audio input size limits (max 1MB per chunk)
  - Text input sanitization for prompt injection prevention

### Authentication & Authorization
- **Auth Method:** TLS client certificates for inter-service communication
- **Session Management:** JWT tokens for API access with short TTL
- **Required Patterns:**
  - mTLS for all gRPC communication
  - Customer authentication through banking system integration

### Secrets Management
- **Development:** Environment variables with `.env` files (not committed)
- **Production:** Kubernetes secrets with external secret management
- **Code Requirements:**
  - NEVER hardcode secrets or API keys
  - Access via configuration service only
  - No secrets in logs or error messages

### API Security
- **Rate Limiting:** Token bucket algorithm, 100 requests/minute per client
- **CORS Policy:** Restricted to authorized domains only
- **Security Headers:** HSTS, CSP, X-Frame-Options for any HTTP endpoints
- **HTTPS Enforcement:** TLS 1.3 minimum for all external communication

### Data Protection
- **Encryption at Rest:** AES-256 for database encryption
- **Encryption in Transit:** TLS 1.3 for all network communication
- **PII Handling:** No customer PII stored in logs or metrics
- **Logging Restrictions:** Exclude audio data, customer details, authentication tokens
