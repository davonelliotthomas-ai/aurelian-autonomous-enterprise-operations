from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx, json, asyncio, os, sys
from .config import settings
from .secrets import secrets
from .database import db
from .rag import search
from .tracing import inject_trace_headers,current_trace_id

@dataclass(frozen=True)
class ToolSpec:
    name:str; risk:str; description:str; side_effect:bool=False

TOOLS={
 "search_knowledge":ToolSpec("search_knowledge","low","Hybrid enterprise knowledge retrieval"),
 "get_service_health":ToolSpec("get_service_health","low","Read service health"),
 "list_inventory":ToolSpec("list_inventory","low","Inspect inventory"),
 "recommend_reorders":ToolSpec("recommend_reorders","low","Analyze replenishment",False),
 "get_customer_profile":ToolSpec("get_customer_profile","low","Read customer profile"),
 "get_order_backlog":ToolSpec("get_order_backlog","low","Read backlog"),
 "send_notice":ToolSpec("send_notice","medium","Send operational notice",True),
 "restart_service":ToolSpec("restart_service","medium","Restart isolated demo service",True),
 "change_product_price":ToolSpec("change_product_price","high","Change catalog price",True),
 "issue_refund":ToolSpec("issue_refund","high","Issue demo refund",True),
 "disable_user_account":ToolSpec("disable_user_account","high","Disable demo user",True),
}

async def execute_tool(tenant_id:str,name:str,args:dict,timeout:float=4.0)->dict:
    if name=="search_knowledge": return await search(tenant_id,args.get("query",""),args.get("environment","production"),args.get("service"))
    if name=="list_inventory":
        sku=str(args.get("sku","")).upper()
        if sku: return {"product":await db.fetchone("SELECT * FROM products WHERE tenant_id=? AND sku=?",(tenant_id,sku))}
        return {"products":await db.fetchall("SELECT * FROM products WHERE tenant_id=? ORDER BY stock",(tenant_id,))}
    if name=="recommend_reorders":
        ps=await db.fetchall("SELECT * FROM products WHERE tenant_id=? ORDER BY stock",(tenant_id,)); rec=[]
        for p in ps:
            if p["stock"]<=p["reorder_point"]:
                target=max(p["reorder_point"]*3,30); rec.append({"sku":p["sku"],"name":p["name"],"current_stock":p["stock"],"recommended_units":max(target-p["stock"],0),"reason":f"Below reorder point; demand {p['demand_trend']}."})
        return {"recommendations":rec,"count":len(rec)}
    if name=="get_customer_profile":
        code=str(args.get("customer_code","CUST-001")).upper(); c=await db.fetchone("SELECT * FROM customers WHERE tenant_id=? AND customer_code=?",(tenant_id,code)); o=await db.fetchall("SELECT * FROM orders WHERE tenant_id=? AND customer_code=? ORDER BY id DESC LIMIT 5",(tenant_id,code)); return {"customer":c,"recent_orders":o}
    if name=="get_order_backlog":
        o=await db.fetchall("SELECT * FROM orders WHERE tenant_id=? AND status!='fulfilled' ORDER BY id DESC",(tenant_id,)); return {"open_orders":o,"count":len(o),"open_value":round(sum(float(x["total"]) for x in o),2)}
    if name=="get_service_health": return await _isolated(name,args,timeout)
    if name in {"send_notice","restart_service"}: return await _isolated(name,args,timeout)
    if name=="change_product_price":
        sku=str(args.get("sku","AUR-101")).upper(); new=float(args.get("new_price",0)); p=await db.fetchone("SELECT * FROM products WHERE tenant_id=? AND sku=?",(tenant_id,sku))
        if not p:return {"changed":False,"reason":"SKU not found"}
        old=float(p["price"]); await db.execute("UPDATE products SET price=? WHERE tenant_id=? AND sku=?",(new,tenant_id,sku)); return {"changed":True,"sku":sku,"old_price":old,"new_price":new,"compensation":{"tool":"change_product_price","args":{"sku":sku,"new_price":old}}}
    if name=="issue_refund":
        code=str(args.get("order_code","ORD-1001")).upper(); order=await db.fetchone("SELECT * FROM orders WHERE tenant_id=? AND order_code=?",(tenant_id,code))
        if not order:return {"refunded":False,"reason":"Order not found"}
        amount=min(float(args.get("amount") or order["total"]),float(order["total"])); return {"refunded":True,"order_code":code,"amount":round(amount,2),"mode":"simulated-financial-write","compensation":{"tool":"void_refund","args":{"order_code":code,"amount":amount}}}
    if name=="disable_user_account":
        user=str(args.get("user","unknown")); return {"user":user,"disabled":True,"mode":"simulated-identity-write","compensation":{"tool":"enable_user_account","args":{"user":user}}}
    raise ValueError(f"Unknown tool {name}")

async def _isolated(name:str,args:dict,timeout:float)->dict:
    if settings.tool_runner_url:
        headers=inject_trace_headers({"X-Internal-Token":secrets.get("INTERNAL_SERVICE_TOKEN")})
        async with httpx.AsyncClient(timeout=timeout) as c:
            r=await c.post(settings.tool_runner_url.rstrip("/")+"/execute",headers=headers,json={"tool":name,"args":args})
            r.raise_for_status()
            out=r.json()
            tid=current_trace_id()
            if tid: out.setdefault("trace_id",tid)
            return out
    # Local demo fallback: separate child process, not FastAPI process.
    proc=await asyncio.create_subprocess_exec(sys.executable,"-m","app.sandbox_worker",stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    payload=json.dumps({"tool":name,"args":args}).encode()
    try: out,err=await asyncio.wait_for(proc.communicate(payload),timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait(); raise TimeoutError(f"Tool {name} exceeded {timeout}s sandbox timeout")
    if proc.returncode!=0: raise RuntimeError(err.decode() or "sandbox tool failed")
    return json.loads(out.decode())
