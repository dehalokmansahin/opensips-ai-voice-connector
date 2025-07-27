-- PostgreSQL Database Initialization for OpenSIPS AI Voice Connector
-- Banking IVR Voice Assistant System

-- Create databases
CREATE DATABASE opensips_dev OWNER opensips;
CREATE DATABASE opensips_test OWNER opensips;

-- Connect to main database
\c opensips;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "hstore";

-- Session Management Tables
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id VARCHAR(255) UNIQUE NOT NULL,
    caller_number VARCHAR(50) NOT NULL,
    called_number VARCHAR(50) NOT NULL,
    session_start TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    session_end TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'ended', 'failed')),
    ai_provider VARCHAR(50),
    conversation_turns INTEGER DEFAULT 0,
    total_duration_seconds INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Conversation Context Tables
CREATE TABLE conversation_contexts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    context_data JSONB NOT NULL,
    context_type VARCHAR(50) NOT NULL CHECK (context_type IN ('customer_auth', 'intent', 'banking_data', 'conversation_state')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(session_id, context_type)
);

-- Banking Integration Tables
CREATE TABLE customer_authentications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    customer_id VARCHAR(100),
    account_number VARCHAR(50),
    phone_verification BOOLEAN DEFAULT FALSE,
    auth_status VARCHAR(20) DEFAULT 'pending' CHECK (auth_status IN ('pending', 'authenticated', 'failed', 'expired')),
    auth_method VARCHAR(50),
    auth_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE banking_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    transaction_type VARCHAR(50) NOT NULL,
    request_data JSONB,
    response_data JSONB,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'timeout')),
    processing_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- AI Service Performance Tables
CREATE TABLE ai_service_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    service_name VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    latency_ms INTEGER NOT NULL,
    input_size INTEGER,
    output_size INTEGER,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- System Health Tables
CREATE TABLE service_health_checks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,
    health_status VARCHAR(20) NOT NULL CHECK (health_status IN ('healthy', 'unhealthy', 'degraded')),
    response_time_ms INTEGER,
    details JSONB,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Audit Tables for Banking Compliance
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    user_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Performance
CREATE INDEX idx_sessions_call_id ON sessions(call_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);

CREATE INDEX idx_conversation_contexts_session_id ON conversation_contexts(session_id);
CREATE INDEX idx_conversation_contexts_type ON conversation_contexts(context_type);
CREATE INDEX idx_conversation_contexts_expires_at ON conversation_contexts(expires_at);

CREATE INDEX idx_customer_auth_session_id ON customer_authentications(session_id);
CREATE INDEX idx_customer_auth_customer_id ON customer_authentications(customer_id);
CREATE INDEX idx_customer_auth_status ON customer_authentications(auth_status);

CREATE INDEX idx_banking_transactions_session_id ON banking_transactions(session_id);
CREATE INDEX idx_banking_transactions_type ON banking_transactions(transaction_type);
CREATE INDEX idx_banking_transactions_status ON banking_transactions(status);

CREATE INDEX idx_ai_metrics_session_id ON ai_service_metrics(session_id);
CREATE INDEX idx_ai_metrics_service ON ai_service_metrics(service_name);
CREATE INDEX idx_ai_metrics_created_at ON ai_service_metrics(created_at);

CREATE INDEX idx_health_checks_service ON service_health_checks(service_name);
CREATE INDEX idx_health_checks_checked_at ON service_health_checks(checked_at);

CREATE INDEX idx_audit_logs_session_id ON audit_logs(session_id);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

-- Functions for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for automatic timestamp updates
CREATE TRIGGER update_sessions_updated_at BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Data retention functions for compliance
CREATE OR REPLACE FUNCTION cleanup_expired_contexts()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM conversation_contexts 
    WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Sample data for development
INSERT INTO sessions (call_id, caller_number, called_number, ai_provider) VALUES
('test-call-001', '+905551234567', '444-BANK', 'llama-local'),
('test-call-002', '+905557654321', '444-BANK', 'openai-cloud');

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO opensips;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO opensips;

-- Create read-only user for monitoring
CREATE USER opensips_readonly WITH PASSWORD 'readonly_password';
GRANT CONNECT ON DATABASE opensips TO opensips_readonly;
GRANT USAGE ON SCHEMA public TO opensips_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO opensips_readonly;

-- Commit the transaction
COMMIT;

-- Success message
\echo 'Database initialization completed successfully!'