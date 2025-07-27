"""Common service utilities"""

from .service_base import BaseService, ServiceConfig

__all__ = [
    "BaseService",
    "ServiceConfig",
]

# Note: ServiceRegistry moved to core/grpc_clients/service_registry.py
# for unified service discovery pattern