from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class Plan:
    tool: str
    args: dict
    fallback: bool = False


def plan_request(request: str) -> Plan:
    r = request.lower()
    if any(k in r for k in ["disable user", "disable account", "suspend user"]):
        m = re.search(r"(?:user|account)\s+([\w.@+-]+)", request, re.I)
        return Plan("disable_user_account", {"user": m.group(1) if m else "demo.user@meridian.demo"})
    if "refund" in r:
        o = re.search(r"ord[-\s]?(\d+)", request, re.I)
        a = re.search(r"\$\s*(\d+(?:\.\d+)?)", request)
        return Plan("issue_refund", {"order_code": f"ORD-{o.group(1)}" if o else "ORD-1001", "amount": float(a.group(1)) if a else 0})
    if any(k in r for k in ["change price", "set price", "update price"]):
        s = re.search(r"([A-Z]{3}-\d{3})", request, re.I)
        p = re.search(r"\$\s*(\d+(?:\.\d+)?)", request)
        return Plan("change_product_price", {"sku": s.group(1).upper() if s else "AUR-101", "new_price": float(p.group(1)) if p else 199.0})
    if any(k in r for k in ["reorder", "restock", "low stock", "inventory risk"]):
        return Plan("recommend_reorders", {})
    if "inventory" in r or "stock" in r:
        s = re.search(r"([A-Z]{3}-\d{3})", request, re.I)
        return Plan("list_inventory", {"sku": s.group(1).upper() if s else ""})
    if any(k in r for k in ["order backlog", "open orders", "unfulfilled", "orders delayed"]):
        return Plan("get_order_backlog", {})
    if "customer" in r:
        c = re.search(r"CUST-\d{3}", request, re.I)
        return Plan("get_customer_profile", {"customer_code": c.group(0).upper() if c else "CUST-001"})
    if "restart" in r:
        return Plan("restart_service", {"service": "core-api"})
    if any(k in r for k in ["health", "status", "latency", "uptime"]):
        return Plan("get_service_health", {"service": "core-api"})
    if any(k in r for k in ["notify", "send notice", "alert ops"]):
        return Plan("send_notice", {"channel": "ops", "message": request[:1000]})
    return Plan("search_knowledge", {"query": request[:3000], "environment": "production"}, True)
