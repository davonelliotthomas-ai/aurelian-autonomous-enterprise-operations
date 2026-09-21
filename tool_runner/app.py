from __future__ import annotations
import os, hmac
import time
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

try:
    from opentelemetry import propagate, trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace import Status, StatusCode

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": os.getenv("OTEL_SERVICE_NAME", "aurelian-tool-runner"),
                "service.namespace": "aurelian",
            }
        )
    )
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
        )
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("aurelian.tool-runner")
except Exception:
    propagate = trace = tracer = Status = StatusCode = None


app = FastAPI(title="Aurelian Isolated Tool Runner")


def _secret(name: str) -> str:
    path = Path("/run/secrets") / name.lower()
    try:
        if path.is_file():
            value=path.read_text().strip()
            if value:return value
    except OSError:
        pass
    value=os.getenv(name, "")
    if value and os.getenv("REQUIRE_SECRET_FILES", "false").lower()!="true":
        return value
    raise RuntimeError(f"required internal secret missing: {path}")



TOKEN = _secret("INTERNAL_SERVICE_TOKEN")


class Req(BaseModel):
    tool: str = Field(min_length=1, max_length=80)
    args: dict = Field(default_factory=dict)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "isolation": "dedicated-container",
        "uid": os.getuid(),
        "allowlist_only": True,
    }


@app.post("/execute")
def execute(request: Request, req: Req, x_internal_token: str = Header(default="")):
    if not hmac.compare_digest(x_internal_token, TOKEN):
        raise HTTPException(403, "invalid internal service token")

    # This runner intentionally has no arbitrary-code endpoint. Only named,
    # finite demo tools can execute. W3C trace context is reconstructed from
    # the caller so failures correlate back to the originating workflow.
    parent = propagate.extract(dict(request.headers)) if propagate else None

    def run_tool():
        if req.tool == "get_service_health":
            return {
                "service": req.args.get("service", "core-api"),
                "status": "healthy",
                "latency_ms": 42,
                "sandbox": "dedicated-container",
            }
        if req.tool == "restart_service":
            return {
                "service": req.args.get("service", "core-api"),
                "restarted": True,
                "sandbox": "dedicated-container",
                "mode": "simulated-safe-lab-action",
            }
        if req.tool == "send_notice":
            return {
                "delivered": True,
                "channel": req.args.get("channel", "ops"),
                "message": str(req.args.get("message", ""))[:1000],
                "sandbox": "dedicated-container",
                "mode": "demo-sink",
            }
        if req.tool == "simulate_timeout":
            time.sleep(10)
            return {"done": True}
        raise HTTPException(400, "tool not allow-listed")

    if not tracer:
        return run_tool()
    with tracer.start_as_current_span(
        "tool_runner.execute",
        context=parent,
        attributes={"tool.name": req.tool},
    ) as span:
        try:
            return run_tool()
        except Exception as exc:
            span.record_exception(exc)
            if Status and StatusCode:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise
