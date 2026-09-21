from __future__ import annotations
from contextlib import contextmanager
from time import perf_counter
from typing import Mapping
from .config import settings

try:
    from opentelemetry import propagate, trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace import Status, StatusCode

    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        trace.set_tracer_provider(
            TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": settings.otel_service_name,
                        "service.namespace": "aurelian",
                        "service.version": settings.version,
                        "deployment.environment": settings.environment,
                    }
                )
            )
        )
    if settings.otel_endpoint:
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_endpoint.rstrip("/") + "/v1/traces")
            )
        )
    tracer = trace.get_tracer("aurelian.autonomous.ops")
except Exception:
    propagate = trace = tracer = None
    Status = StatusCode = None


def inject_trace_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    carrier = dict(headers or {})
    if propagate:
        propagate.inject(carrier)
    return carrier


def extract_trace_context(headers: Mapping[str, str]):
    if not propagate:
        return None
    return propagate.extract(dict(headers))


def current_trace_id() -> str:
    if not trace:
        return ""
    ctx = trace.get_current_span().get_span_context()
    if not ctx or not ctx.is_valid:
        return ""
    return f"{ctx.trace_id:032x}"


@contextmanager
def span(name: str, context=None, **attrs):
    start = perf_counter()
    meta = {
        "span": name,
        "attributes": attrs,
        "tokens_in": 0,
        "tokens_out": 0,
        "estimated_cost_usd": 0.0,
    }
    if not tracer:
        try:
            yield meta
        finally:
            meta["latency_ms"] = round((perf_counter() - start) * 1000, 2)
        return

    try:
        with tracer.start_as_current_span(name, context=context) as s:
            for k, v in attrs.items():
                # Never attach raw authorization, prompt, secret or document text.
                s.set_attribute(k, str(v)[:512])
            try:
                yield meta
            except Exception as exc:
                s.record_exception(exc)
                if Status and StatusCode:
                    s.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise
            finally:
                meta["latency_ms"] = round((perf_counter() - start) * 1000, 2)
                s.set_attribute("aurelian.latency_ms", meta["latency_ms"])
    finally:
        pass
