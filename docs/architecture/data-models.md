# Data Models

The core data models represent the essential entities for session management, conversation context, and banking integration.

### CallSession

**Purpose:** Manages the lifecycle and metadata of individual voice calls

**Key Attributes:**
- session_id: UUID - Unique identifier for correlation across services
- caller_phone: string - Originating phone number
- call_start_time: timestamp - Session initiation time
- call_end_time: timestamp - Session termination time (nullable)
- sip_call_id: string - OpenSIPS call identifier
- status: enum - ACTIVE, COMPLETED, FAILED, INTERRUPTED
- ai_provider_config: JSON - Selected AI providers for this session

**Relationships:**
- One-to-many with ConversationContext
- One-to-many with BankingTransaction

### ConversationContext

**Purpose:** Stores conversation memory and AI processing state for context-aware responses

**Key Attributes:**
- context_id: UUID - Unique context identifier
- session_id: UUID - Foreign key to CallSession
- conversation_history: JSON - Array of message exchanges
- current_intent: string - Detected user intent (e.g., "card_delivery_inquiry")
- customer_data: JSON - Cached customer information for session
- last_updated: timestamp - Context modification time
- expires_at: timestamp - TTL for context cleanup

**Relationships:**
- Many-to-one with CallSession
- References customer data from banking systems

### BankingTransaction

**Purpose:** Tracks banking-specific operations and customer authentication within voice sessions

**Key Attributes:**
- transaction_id: UUID - Unique transaction identifier
- session_id: UUID - Foreign key to CallSession
- customer_id: string - Banking system customer identifier
- transaction_type: enum - CARD_INQUIRY, BALANCE_CHECK, etc.
- authentication_status: enum - PENDING, VERIFIED, FAILED
- query_parameters: JSON - Structured query data
- response_data: JSON - Banking system response
- created_at: timestamp - Transaction initiation time

**Relationships:**
- Many-to-one with CallSession
- References external banking system entities
