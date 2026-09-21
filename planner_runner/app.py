from __future__ import annotations
import os
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from planning import plan_request

try:
    from opentelemetry import propagate, trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    provider=TracerProvider(resource=Resource.create({"service.name":os.getenv("OTEL_SERVICE_NAME","aurelian-planner"),"service.namespace":"aurelian"}))
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT","")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/")+"/v1/traces")))
    trace.set_tracer_provider(provider)
    tracer=trace.get_tracer("aurelian.planner")
except Exception:
    propagate=trace=tracer=None

app=FastAPI(title="Aurelian No-Secret Planner")

class PlanIn(BaseModel):
    request: str = Field(min_length=3,max_length=3000)

@app.get('/health')
def health():
    return {"status":"ok","secret_mounts":False,"database_access":False,"egress":"isolated-network"}

@app.post('/plan')
def plan(request:Request, body:PlanIn):
    parent=propagate.extract(dict(request.headers)) if propagate else None
    if tracer:
        with tracer.start_as_current_span("planner.plan",context=parent):
            p=plan_request(body.request)
    else:
        p=plan_request(body.request)
    return {"tool":p.tool,"args":p.args,"fallback":p.fallback}
