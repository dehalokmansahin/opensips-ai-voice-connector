# Database Schema

The system uses PostgreSQL for persistent data and Redis for high-performance caching.

### PostgreSQL Schema

```sql
-- Call sessions table
CREATE TABLE call_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    caller_phone VARCHAR(20) NOT NULL,
    call_start_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    call_end_time TIMESTAMP WITH TIME ZONE,
    sip_call_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('ACTIVE', 'COMPLETED', 'FAILED', 'INTERRUPTED')),
    ai_provider_config JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Conversation context history
CREATE TABLE conversation_contexts (
    context_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    conversation_history JSONB NOT NULL DEFAULT '[]',
    current_intent VARCHAR(100),
    customer_data JSONB,
    last_updated TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Banking transactions
CREATE TABLE banking_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    customer_id VARCHAR(100),
    transaction_type VARCHAR(50) NOT NULL,
    authentication_status VARCHAR(20) NOT NULL CHECK (authentication_status IN ('PENDING', 'VERIFIED', 'FAILED')),
    query_parameters JSONB,
    response_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_call_sessions_status ON call_sessions(status);
CREATE INDEX idx_call_sessions_start_time ON call_sessions(call_start_time);
CREATE INDEX idx_conversation_contexts_session_id ON conversation_contexts(session_id);
CREATE INDEX idx_conversation_contexts_expires_at ON conversation_contexts(expires_at);
CREATE INDEX idx_banking_transactions_session_id ON banking_transactions(session_id);
CREATE INDEX idx_banking_transactions_customer_id ON banking_transactions(customer_id);

-- Auto-update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_call_sessions_updated_at 
    BEFORE UPDATE ON call_sessions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### Redis Cache Structure

```yaml