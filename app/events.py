import asyncio
import json
from collections import defaultdict
from .tracing import current_trace_id


class EventBus:
    """SSE fanout only.

    This bus does not execute privileged work. Side-effecting actions are always
    executed synchronously through the control plane after just-in-time policy
    evaluation; events are observational telemetry only.
    """
    def __init__(self):
        self.queues = defaultdict(list)

    async def publish(self, tenant_id: str, event: dict):
        event = dict(event)
        tid = current_trace_id()
        if tid:
            event.setdefault("trace_id", tid)
        dead = []
        for q in list(self.queues[tenant_id]):
            try:
                q.put_nowait(event)
            except Exception:
                dead.append(q)
        for q in dead:
            if q in self.queues[tenant_id]:
                self.queues[tenant_id].remove(q)

    async def stream(self, tenant_id: str):
        q = asyncio.Queue(maxsize=100)
        self.queues[tenant_id].append(q)
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"
        finally:
            if q in self.queues[tenant_id]:
                self.queues[tenant_id].remove(q)


bus = EventBus()
