from __future__ import annotations
import asyncio,json,time,hashlib
from .audit import append_audit,utcnow
from .auth import Principal
from .config import settings
from .database import db,set_tenant_context
from .events import bus
from .policy import evaluate,approval_authorized
from .security import classify_untrusted_input_async
from .tools import TOOLS,execute_tool
from .tracing import span,inject_trace_headers
from .planning import Plan,plan_request
import httpx

TERMINAL={"completed","failed","blocked","pending_approval","rolled_back","recovery_required"}

COMPENSATION_PAIRS={
 "change_product_price":"change_product_price",
 "issue_refund":"void_refund",
 "disable_user_account":"enable_user_account",
}

def _execution_key(task_id:int, phase:str, tool:str)->str:
 return f"{phase}:{task_id}:{tool}"

def _args_hash(args:dict)->str:
 return hashlib.sha256(json.dumps(args,sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest()

def _validate_compensation(original_tool:str, comp:dict)->tuple[bool,str]:
 expected=COMPENSATION_PAIRS.get(original_tool)
 if not expected:return False,"original tool has no registered compensation"
 if comp.get("tool")!=expected:return False,"compensation tool does not match original tool"
 args=comp.get("args")
 if not isinstance(args,dict):return False,"compensation args must be an object"
 required={
  "change_product_price":{"sku","new_price"},
  "void_refund":{"order_code","amount"},
  "enable_user_account":{"user"},
 }.get(expected,set())
 missing=required-set(args)
 if missing:return False,"compensation missing required args: "+",".join(sorted(missing))
 return True,"registered compensation relation validated"


def _hash_value(value)->dict:
 raw=json.dumps(value,sort_keys=True,default=str,separators=(",",":"))
 return {"sha256":hashlib.sha256(raw.encode()).hexdigest(),"bytes":len(raw.encode())}

def _safe_plan(tool:str,args:dict)->dict:
 safe={}
 for k,v in args.items():
  if k in {"query","message","user","sku","order_code","amount","new_price","customer_code","channel","service"}: safe[k+"_meta"]=_hash_value(v)
  else: safe[k]=v
 return {"tool":tool,"args":safe}

def _safe_output(output:dict)->dict:
 return {"keys":sorted(output.keys()),"output_meta":_hash_value(output)}

def _verify_output(tool:str, output:dict)->tuple[bool,str]:
 if not isinstance(output,dict): return False,"tool output is not an object"
 required={
  "search_knowledge":{"matches"},
  "get_service_health":{"status"},
  "list_inventory":set(),
  "recommend_reorders":{"recommendations"},
  "get_customer_profile":{"customer","recent_orders"},
  "get_order_backlog":{"open_orders"},
  "send_notice":{"delivered"},
  "restart_service":{"restarted"},
  "change_product_price":{"changed"},
  "issue_refund":{"refunded"},
  "disable_user_account":{"disabled"},
 }
 if tool=="list_inventory" and not ({"product","products"}&set(output)): return False,"inventory output missing product(s)"
 missing=required.get(tool,set())-set(output)
 if missing:return False,"missing output keys: "+",".join(sorted(missing))
 return True,"tool output schema satisfied"

class WorkflowEngine:
 async def plan(self,request:str)->Plan:
  if settings.planner_url:
   headers=inject_trace_headers()
   async with httpx.AsyncClient(timeout=2.0) as client:
    r=await client.post(settings.planner_url.rstrip("/")+"/plan",headers=headers,json={"request":request})
    r.raise_for_status(); d=r.json(); return Plan(str(d["tool"]),dict(d.get("args") or {}),bool(d.get("fallback")))
  return plan_request(request)

 async def checkpoint(self,tenant,task,node,attempt,state,latency):
  await db.execute("INSERT INTO workflow_checkpoints(tenant_id,task_id,node,attempt,state_json,latency_ms,created_at) VALUES(?,?,?,?,?,?,?)",(tenant,task,node,attempt,json.dumps(state,default=str),latency,utcnow()))
  await db.execute("UPDATE tasks SET workflow_state=?,updated_at=? WHERE tenant_id=? AND id=?",(node,utcnow(),tenant,task))
  await bus.publish(tenant,{"type":"workflow","task_id":task,"node":node,"attempt":attempt,"latency_ms":latency,"state":state})

 async def run(self,task_id:int,request:str,p:Principal)->dict:
  with span("workflow.run",tenant=p.tenant_id,task_id=task_id,actor=p.sub,role=p.role):
   return await self._run(task_id,request,p)

 async def _run(self,task_id:int,request:str,p:Principal)->dict:
  tenant=p.tenant_id; set_tenant_context(tenant); state={"request_sha256":hashlib.sha256(request.encode()).hexdigest(),"request_length":len(request),"actor":p.sub,"role":p.role}; steps=0
  with span("workflow.input_guard",tenant=tenant,task_id=task_id) as guard_tr:
   risk=await classify_untrusted_input_async(request)
  state["input_risk"]={"risk":risk.risk,"signals":len(risk.reasons)}
  await self.checkpoint(tenant,task_id,"INPUT_GUARD",1,state,guard_tr.get("latency_ms",0)); steps+=1
  if steps>settings.max_workflow_steps:return await self._fail(tenant,task_id,p,"step budget exceeded")
  with span("workflow.plan",tenant=tenant,task_id=task_id) as tr: plan=await self.plan(request)
  state["plan"]={**_safe_plan(plan.tool,plan.args),"fallback":plan.fallback}; await self.checkpoint(tenant,task_id,"PLAN",1,state,tr.get("latency_ms",0)); steps+=1
  await append_audit(tenant,p.sub,"agent.plan",{"task_id":task_id,**state["plan"],"input_risk":risk.risk})
  with span("workflow.policy",tenant=tenant,task_id=task_id,tool=plan.tool) as policy_tr:
   decision=await evaluate(plan.tool,p,"production",risk.risk)
  state["policy"]={"allowed":decision.allowed,"requires_approval":decision.requires_approval,"tier":decision.approval_tier,"risk":decision.risk,"reason":decision.reason,"source":decision.source,"policy_fingerprint":decision.policy_fingerprint}
  await self.checkpoint(tenant,task_id,"POLICY",1,state,policy_tr.get("latency_ms",0)); steps+=1
  await append_audit(tenant,p.sub,"policy.decision",{"task_id":task_id,"tool":plan.tool,**state["policy"]})
  if decision.requires_approval:
   aid=await db.insert_returning_id("INSERT INTO approvals(tenant_id,task_id,tool_name,args_json,actor,requester_role,approval_tier,status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(tenant,task_id,plan.tool,json.dumps(plan.args),p.sub,p.role,decision.approval_tier,"pending",decision.reason,utcnow()))
   result={"status":"pending_approval","task_id":task_id,"approval_id":aid,"tool":plan.tool,"risk":decision.risk,"approval_tier":decision.approval_tier,"reason":decision.reason}
   await self._finish(tenant,task_id,"pending_approval",result,"WAIT_APPROVAL"); await append_audit(tenant,p.sub,"approval.requested",result); return result
  if not decision.allowed:
   result={"status":"blocked","task_id":task_id,"reason":decision.reason,"input_risk":risk.risk}; await self._finish(tenant,task_id,"blocked",result,"BLOCKED"); return result
  return await self.execute_approved(task_id,plan.tool,plan.args,p,approval_tier="none",input_risk=risk.risk)

 async def execute_approved(self,task_id:int,tool:str,args:dict,p:Principal,approval_tier:str="none",input_risk:str="low")->dict:
  tenant=p.tenant_id; set_tenant_context(tenant); last=None
  exec_key=_execution_key(task_id,"primary",tool)
  existing=await db.fetchone("SELECT * FROM tool_executions WHERE tenant_id=? AND idempotency_key=?",(tenant,exec_key))
  replay_output=None
  if existing:
   if existing["status"]=="completed" and existing.get("output_json"):
    replay_output=json.loads(existing["output_json"])
   else:
    result={"status":"recovery_required","task_id":task_id,"tool":tool,"execution_status":existing["status"],"execution_key":exec_key}
    await self._finish(tenant,task_id,"recovery_required",result,"RECOVERY_REQUIRED")
    return result

  if replay_output is None:
   # Just-in-time authorization happens immediately before a new side effect.
   with span("workflow.jit_policy",tenant=tenant,task_id=task_id,tool=tool) as jit_tr:
    jit=await evaluate(tool,p,"production",input_risk)
   jit_state={"allowed":jit.allowed,"requires_approval":jit.requires_approval,"tier":jit.approval_tier,"risk":jit.risk,"reason":jit.reason,"source":jit.source,"policy_fingerprint":jit.policy_fingerprint}
   await self.checkpoint(tenant,task_id,"JIT_POLICY",1,jit_state,jit_tr.get("latency_ms",0))
   await append_audit(tenant,p.sub,"policy.jit_recheck",{"task_id":task_id,"tool":tool,**jit_state})
   if approval_tier=="none":
    if not jit.allowed:
     result={"status":"blocked","task_id":task_id,"reason":"JIT policy denied execution: "+jit.reason}
     await self._finish(tenant,task_id,"blocked",result,"JIT_BLOCKED")
     return result
   else:
    ok,reason=approval_authorized(jit,p)
    if not ok or jit.approval_tier!=approval_tier:
     result={"status":"blocked","task_id":task_id,"reason":"JIT approval authorization failed: "+reason}
     await self._finish(tenant,task_id,"blocked",result,"JIT_BLOCKED")
     return result

   claimed=await db.fetchone_write(
    "INSERT INTO tool_executions(tenant_id,task_id,phase,tool_name,idempotency_key,args_hash,status,started_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,idempotency_key) DO NOTHING RETURNING *",
    (tenant,task_id,"primary",tool,exec_key,_args_hash(args),"executing",utcnow()),
   )
   if not claimed:
    existing=await db.fetchone("SELECT * FROM tool_executions WHERE tenant_id=? AND idempotency_key=?",(tenant,exec_key))
    if existing and existing["status"]=="completed" and existing.get("output_json"):
     replay_output=json.loads(existing["output_json"])
    else:
     result={"status":"recovery_required","task_id":task_id,"tool":tool,"execution_status":existing["status"] if existing else "unknown","execution_key":exec_key}
     await self._finish(tenant,task_id,"recovery_required",result,"RECOVERY_REQUIRED")
     return result

  if replay_output is not None:
   output=replay_output; attempt=0; latency=0
   await append_audit(tenant,p.sub,"tool.execution_recovered",{"task_id":task_id,"tool":tool,"execution_key":exec_key})
  else:
   max_attempts=1 if TOOLS.get(tool) and TOOLS[tool].side_effect else settings.max_tool_retries+1
   for attempt in range(1,max_attempts+1):
    try:
     with span("workflow.execute",tenant=tenant,task_id=task_id,tool=tool,attempt=attempt) as exec_tr:
      output=await execute_tool(tenant,tool,args)
     latency=exec_tr.get("latency_ms",0)
     await db.execute("UPDATE tool_executions SET status='completed',output_json=?,completed_at=? WHERE tenant_id=? AND idempotency_key=? AND status='executing'",(json.dumps(output,default=str),utcnow(),tenant,exec_key))
     break
    except Exception as e:
     last=e
     ambiguous=bool(TOOLS.get(tool) and TOOLS[tool].side_effect)
     final=(attempt>=max_attempts)
     if final:
      state="execution_unknown" if ambiguous else "failed"
      await db.execute("UPDATE tool_executions SET status=?,error_type=?,completed_at=? WHERE tenant_id=? AND idempotency_key=? AND status='executing'",(state,type(e).__name__,utcnow(),tenant,exec_key))
      if ambiguous:
       result={"status":"recovery_required","task_id":task_id,"tool":tool,"reason":"side-effect execution outcome is indeterminate","execution_key":exec_key}
       await self._finish(tenant,task_id,"recovery_required",result,"RECOVERY_REQUIRED")
       return result
     await self.checkpoint(tenant,task_id,"EXECUTE_RETRY",attempt,{"tool":tool,"error":type(e).__name__},0)
     await asyncio.sleep(0.05*(2**(attempt-1)))
   else:
    return await self._fail(tenant,task_id,p,f"tool failed safely after retries: {type(last).__name__}")
   if last is not None and 'output' not in locals():
    return await self._fail(tenant,task_id,p,f"tool failed safely after retries: {type(last).__name__}")

  await self.checkpoint(tenant,task_id,"EXECUTE",attempt,{"tool":tool,"idempotent_replay":attempt==0,**_safe_output(output)},latency)
  if output.get("compensation"):
   prior=await db.fetchone("SELECT id FROM compensations WHERE tenant_id=? AND task_id=? AND execution_key=?",(tenant,task_id,exec_key))
   if not prior:
    await db.execute("INSERT INTO compensations(tenant_id,task_id,tool_name,compensation_json,status,execution_key,created_at) VALUES(?,?,?,?,?,?,?)",(tenant,task_id,tool,json.dumps(output["compensation"]),"available",exec_key,utcnow()))
  with span("workflow.verify",tenant=tenant,task_id=task_id,tool=tool) as verify_tr:
   verified,verify_reason=_verify_output(tool,output)
  await self.checkpoint(tenant,task_id,"VERIFY",1,{"tool":tool,"verified":verified,"reason":verify_reason},verify_tr.get("latency_ms",0))
  if not verified:
   return await self._fail(tenant,task_id,p,"verification failed: "+verify_reason)
  result={"status":"completed","task_id":task_id,"tool":tool,"output":output,"attempts":attempt,"idempotent_replay":attempt==0,"execution_key":exec_key,"trace":{"latency_ms":latency,"tokens_in":0,"tokens_out":0,"estimated_cost_usd":0.0}}
  await self._finish(tenant,task_id,"completed",result,"COMPLETE")
  await append_audit(tenant,p.sub,"tool.executed",{"task_id":task_id,"tool":tool,**_safe_output(output),"attempt":attempt,"execution_key":exec_key})
  return result

 async def rollback(self,task_id:int,p:Principal)->dict:
  set_tenant_context(p.tenant_id)
  c=await db.fetchone("SELECT * FROM compensations WHERE tenant_id=? AND task_id=? AND status='available' ORDER BY id DESC LIMIT 1",(p.tenant_id,task_id))
  if not c:return {"status":"no_compensation","task_id":task_id}
  comp=json.loads(c["compensation_json"])
  valid,validation_reason=_validate_compensation(c["tool_name"],comp)
  if not valid:return {"status":"blocked","task_id":task_id,"reason":"invalid compensation: "+validation_reason}
  task=await db.fetchone("SELECT request FROM tasks WHERE tenant_id=? AND id=?",(p.tenant_id,task_id))
  if not task:return {"status":"blocked","task_id":task_id,"reason":"originating task missing"}
  risk=await classify_untrusted_input_async(task["request"])
  if comp.get("tool") in TOOLS:
   jit=await evaluate(comp["tool"],p,"production",risk.risk)
   ok,reason=approval_authorized(jit,p) if jit.requires_approval else (jit.allowed,jit.reason)
   if not ok:return {"status":"blocked","task_id":task_id,"reason":"rollback JIT authorization failed: "+reason}
  claimed=await db.fetchone_write("UPDATE compensations SET status='executing' WHERE tenant_id=? AND id=? AND status='available' RETURNING *",(p.tenant_id,c["id"]))
  if not claimed:return {"status":"conflict","task_id":task_id,"reason":"compensation already claimed"}
  rollback_key=_execution_key(task_id,f"rollback-{c['id']}",str(comp.get("tool")))
  ex=await db.fetchone_write(
   "INSERT INTO tool_executions(tenant_id,task_id,phase,tool_name,idempotency_key,args_hash,status,started_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,idempotency_key) DO NOTHING RETURNING *",
   (p.tenant_id,task_id,"rollback",str(comp.get("tool")),rollback_key,_args_hash(comp.get("args",{})),"executing",utcnow()),
  )
  if not ex:
   await db.execute("UPDATE compensations SET status='execution_unknown' WHERE tenant_id=? AND id=? AND status='executing'",(p.tenant_id,c["id"]))
   return {"status":"recovery_required","task_id":task_id,"reason":"rollback execution already exists","execution_key":rollback_key}
  try:
   if comp.get("tool") in TOOLS:
    out=await execute_tool(p.tenant_id,comp["tool"],comp.get("args",{}))
   else:
    out={"simulated":True,"compensation":comp}
   await db.execute("UPDATE tool_executions SET status='completed',output_json=?,completed_at=? WHERE tenant_id=? AND idempotency_key=?",(json.dumps(out,default=str),utcnow(),p.tenant_id,rollback_key))
   used=await db.execute("UPDATE compensations SET status='used' WHERE tenant_id=? AND id=? AND status='executing'",(p.tenant_id,c["id"]))
   if used!=1:raise RuntimeError("compensation finalization conflict")
  except Exception as exc:
   await db.execute("UPDATE tool_executions SET status='execution_unknown',error_type=?,completed_at=? WHERE tenant_id=? AND idempotency_key=? AND status='executing'",(type(exc).__name__,utcnow(),p.tenant_id,rollback_key))
   await db.execute("UPDATE compensations SET status='execution_unknown' WHERE tenant_id=? AND id=? AND status='executing'",(p.tenant_id,c["id"]))
   await self._finish(p.tenant_id,task_id,"recovery_required",{"status":"recovery_required","execution_key":rollback_key},"RECOVERY_REQUIRED")
   raise
  await self._finish(p.tenant_id,task_id,"rolled_back",{"status":"rolled_back","output":out},"ROLLED_BACK")
  await append_audit(p.tenant_id,p.sub,"workflow.rollback",{"task_id":task_id,"compensation_tool":comp.get("tool"),"input_risk":risk.risk,"execution_key":rollback_key})
  return {"status":"rolled_back","task_id":task_id,"output":out,"execution_key":rollback_key}

 async def _finish(self,tenant,task,status,result,node):
  await db.execute("UPDATE tasks SET status=?,workflow_state=?,result_json=?,updated_at=? WHERE tenant_id=? AND id=?",(status,node,json.dumps(result,default=str),utcnow(),tenant,task)); await bus.publish(tenant,{"type":"task","task_id":task,"status":status,"node":node,"result":result})
 async def _fail(self,tenant,task,p,reason):
  result={"status":"failed_safe","task_id":task,"reason":reason}; await self._finish(tenant,task,"failed",result,"FAILED"); await append_audit(tenant,p.sub,"workflow.failed",result); return result

engine=WorkflowEngine()
