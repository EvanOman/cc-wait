"""OpenTelemetry tracing setup."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = "cc-wait"
SERVICE_VERSION = "0.2.0"

_tracer: trace.Tracer | None = None


def setup_tracing(
    service_name: str = SERVICE_NAME,
    endpoint: str | None = None,
) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing.

    Args:
        service_name: Name of the service for tracing
        endpoint: OTLP endpoint (default: from OTEL_EXPORTER_ENDPOINT env var or localhost:4317)

    Returns:
        Configured tracer instance
    """
    global _tracer

    if _tracer is not None:
        return _tracer

    # Get endpoint from env or default
    endpoint = endpoint or os.environ.get("OTEL_EXPORTER_ENDPOINT", "http://localhost:4317")
    otel_enabled = os.environ.get("OTEL_ENABLED", "true").lower() in ("1", "true", "yes")

    # Create resource with service info
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": SERVICE_VERSION,
        }
    )

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    if otel_enabled:
        # Add OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global provider
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer(service_name, SERVICE_VERSION)
    return _tracer


def get_tracer() -> trace.Tracer:
    """Get the configured tracer, initializing if needed."""
    global _tracer
    if _tracer is None:
        return setup_tracing()
    return _tracer


@contextmanager
def create_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """
    Create a tracing span as a context manager.

    Usage:
        with create_span("fetch_usage", {"user": "evan"}) as span:
            result = fetch_data()
            span.set_attribute("result_count", len(result))
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span
