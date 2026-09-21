import json
import pytest
from app.agent import engine
from app.auth import Principal
from app.audit import verify_chain,utcnow
from app.database import db
from app.policy import evaluate

operator=Principal("operator@test","meridian","operator",{"read","operate"},False)
executive=Principal("exec@test","meridian","executive",{"read","operate","approve:team","approve:executive"},True)

async def make_task(request, p=operator):
    now=utcnow(); tid=await db.insert_returning_id("INSERT INTO tasks(tenant_id,request,actor,role,status,workflow_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(p.tenant_id,request,p.sub,p.role,"running","CREATED",now,now)); return tid

@pytest.mark.asyncio
async def test_read_workflow_is_checkpointed_and_audited():
    tid=await make_task("Which products need reorder?")
    result=await engine.run(tid,"Which products need reorder?",operator)
    assert result["status"]=="completed"
    cps=await db.fetchall("SELECT node FROM workflow_checkpoints WHERE tenant_id=? AND task_id=? ORDER BY id",("meridian",tid))
    nodes=[x["node"] for x in cps]
    assert nodes[:3]==["INPUT_GUARD","PLAN","POLICY"]
    assert "JIT_POLICY" in nodes and "EXECUTE" in nodes and "VERIFY" in nodes
    assert (await verify_chain("meridian"))["valid"] is True

@pytest.mark.asyncio
async def test_high_risk_write_requires_executive_mfa_approval():
    d=await evaluate("change_product_price",operator,"production","low")
    assert d.requires_approval and d.approval_tier=="executive_mfa"
    tid=await make_task("Change price AUR-101 to $999")
    result=await engine.run(tid,"Change price AUR-101 to $999",operator)
    assert result["status"]=="pending_approval"
    a=await db.fetchone("SELECT * FROM approvals WHERE tenant_id=? AND id=?",("meridian",result["approval_id"]))
    assert a["approval_tier"]=="executive_mfa"

@pytest.mark.asyncio
async def test_reversible_write_can_rollback():
    before=await db.fetchone("SELECT price FROM products WHERE tenant_id=? AND sku=?",("meridian","AUR-101"))
    tid=await make_task("direct approved write",executive)
    done=await engine.execute_approved(tid,"change_product_price",{"sku":"AUR-101","new_price":999},executive,approval_tier="executive_mfa",input_risk="low")
    assert done["status"]=="completed"
    changed=await db.fetchone("SELECT price FROM products WHERE tenant_id=? AND sku=?",("meridian","AUR-101")); assert changed["price"]==999
    rb=await engine.rollback(tid,executive); assert rb["status"]=="rolled_back"
    after=await db.fetchone("SELECT price FROM products WHERE tenant_id=? AND sku=?",("meridian","AUR-101")); assert after["price"]==before["price"]
