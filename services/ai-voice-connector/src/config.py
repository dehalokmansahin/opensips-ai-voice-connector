"""
Configuration management for AI Voice Connector service
Uses Pydantic settings for type-safe configuration with environment variable support
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseModel):
    """Database configuration"""
    host: str = "postgres"
    port: int = 5432
    database: str = "opensips"
    username: str = "opensips"
    password: str = "opensips_password"
    
    @property
    def url(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class RedisConfig(BaseModel):
    """Redis configuration"""
    host: str = "redis"
    port: int = 6379
    password: Optional[str] = "redis_password"
    database: int = 0
    
    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.database}"
        return f"redis://{self.host}:{self.port}/{self.database}"


class OpenSIPSConfig(BaseModel):
    """OpenSIPS integration configuration"""
    host: str = "opensips"
    mi_port: int = 8087
    event_port: int = 8090
    sip_port: int = 5060


class AIServiceConfig(BaseModel):
    """AI service endpoints configuration"""
    vad_host: str = "vad-service"
    vad_port: int = 50052
    
    asr_host: str = "asr-service"
    asr_port: int = 50053
    
    llm_host: str = "llm-service"
    llm_port: int = 50054
    
    tts_host: str = "tts-service"
    tts_port: int = 50055
    
    session_manager_host: str = "session-manager"
    session_manager_port: int = 50056
    
    context_store_host: str = "context-store"
    context_store_port: int = 50057
    
    banking_service_host: str = "banking-service"
    banking_service_port: int = 50058


class PipelineConfig(BaseModel):
    """AI pipeline configuration"""
    # Latency targets (milliseconds)
    vad_target_latency_ms: int = 20
    asr_target_latency_ms: int = 250
    llm_target_latency_ms: int = 300
    tts_target_latency_ms: int = 200
    total_target_latency_ms: int = 700
    
    # Audio configuration
    sample_rate: int = 16000
    channels: int = 1
    audio_format: str = "pcm16"
    
    # VAD configuration
    vad_confidence: float = 0.3
    vad_start_secs: float = 0.05
    vad_stop_secs: float = 0.3
    vad_min_volume: float = 0.001
    
    # Pipeline timeouts
    pipeline_timeout_seconds: int = 30
    session_timeout_seconds: int = 300  # 5 minutes
    
    # Banking specific
    max_conversation_turns: int = 20
    conversation_language: str = "tr-TR"


class SecurityConfig(BaseModel):
    """Security configuration"""
    enable_tls: bool = False
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None
    
    # Banking security
    enable_pii_filtering: bool = True
    audit_logging: bool = True
    session_encryption: bool = True


class MonitoringConfig(BaseModel):
    """Monitoring and observability configuration"""
    enable_metrics: bool = True
    enable_health_checks: bool = True
    enable_tracing: bool = False
    
    # Health check intervals
    health_check_interval_seconds: int = 30
    external_service_timeout_seconds: int = 5
    
    # Prometheus metrics
    metrics_port: int = 8080


class Settings(BaseSettings):
    """Main application settings"""
    
    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = Field(default=False, description="Enable debug mode")
    
    # Service configuration
    service_name: str = "ai-voice-connector"
    version: str = "0.1.0"
    
    # Network configuration
    http_port: int = Field(default=8080, description="HTTP server port")
    grpc_port: int = Field(default=50051, description="gRPC server port")
    host: str = Field(default="0.0.0.0", description="Service bind address")
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    
    # Component configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    opensips: OpenSIPSConfig = Field(default_factory=OpenSIPSConfig)
    ai_services: AIServiceConfig = Field(default_factory=AIServiceConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    
    # Legacy compatibility properties
    @property
    def opensips_host(self) -> str:
        return self.opensips.host
    
    @property
    def opensips_mi_port(self) -> int:
        return self.opensips.mi_port
    
    @property
    def opensips_event_port(self) -> int:
        return self.opensips.event_port
    
    @property
    def vad_service_host(self) -> str:
        return self.ai_services.vad_host
    
    @property
    def vad_service_port(self) -> int:
        return self.ai_services.vad_port
    
    @property
    def asr_service_host(self) -> str:
        return self.ai_services.asr_host
    
    @property
    def asr_service_port(self) -> int:
        return self.ai_services.asr_port
    
    @property
    def llm_service_host(self) -> str:
        return self.ai_services.llm_host
    
    @property
    def llm_service_port(self) -> int:
        return self.ai_services.llm_port
    
    @property
    def tts_service_host(self) -> str:
        return self.ai_services.tts_host
    
    @property
    def tts_service_port(self) -> int:
        return self.ai_services.tts_port
    
    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        case_sensitive = False