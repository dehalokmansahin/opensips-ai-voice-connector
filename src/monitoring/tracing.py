#!/usr/bin/env python3
"""
OpenTelemetry tracing setup (no-op if SDK not installed)
"""

from typing import Optional, Dict, Any

_otel_ready: bool = False


def setup_tracing(service_name: str = "opensips-ai-voice-connector", otlp_endpoint: Optional[str] = None) -> None:
    global _otel_ready
    if _otel_ready:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            exporter = ConsoleSpanExporter()

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        _otel_ready = True
    except Exception:
        _otel_ready = False


def start_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("oavc")
        span = tracer.start_as_current_span(name)
        if attributes:
            # Use context manager to set attributes after creation
            class _SpanCtx:
                def __enter__(self_inner):
                    s = span.__enter__()
                    for k, v in attributes.items():
                        try:
                            s.set_attribute(k, v)
                        except Exception:
                            pass
                    return s

                def __exit__(self_inner, exc_type, exc_value, traceback):
                    return span.__exit__(exc_type, exc_value, traceback)

            return _SpanCtx()
        return span
    except Exception:
        # Fallback no-op context manager
        class _Noop:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
        return _Noop()


