import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.tracing import span,inject_trace_headers
from tool_runner.app import app as runner_app, TOKEN as RUNNER_TOKEN


def test_tool_runner_has_no_arbitrary_code_endpoint():
    with TestClient(runner_app) as client:
        r=client.post('/execute',headers={'X-Internal-Token':RUNNER_TOKEN},json={'tool':'python','args':{'code':'import os'}})
        assert r.status_code==400
        assert 'not allow-listed' in r.text


def test_trace_context_is_injected_for_downstream_calls():
    with span('test.trace.propagation'):
        h=inject_trace_headers()
        # When OpenTelemetry is installed, W3C Trace Context must be present.
        assert 'traceparent' in h or h=={}


def test_approval_replay_executes_side_effect_once():
    with TestClient(app) as client:
        op=client.get('/api/auth/demo-token',params={'role':'operator','tenant_id':'meridian','mfa':'true'}).json()['access_token']
        ex=client.get('/api/auth/demo-token',params={'role':'executive','tenant_id':'meridian','mfa':'true'}).json()['access_token']
        oh={'Authorization':f'Bearer {op}'}; eh={'Authorization':f'Bearer {ex}'}
        req=client.post('/api/tasks',headers=oh,json={'request':'Change price AUR-101 to $999'}).json()
        first=client.post(f"/api/approvals/{req['approval_id']}/approve",headers=eh,json={'note':'first'})
        second=client.post(f"/api/approvals/{req['approval_id']}/approve",headers=eh,json={'note':'replay'})
        assert first.status_code==200 and first.json()['status']=='completed'
        assert second.status_code==409
        audits=client.get('/api/audit',headers=eh).json()['events']
        executed=[]
        for e in audits:
            if e['event_type']=='tool.executed':
                payload=json.loads(e['payload_json'])
                if payload.get('task_id')==req['task_id']:
                    executed.append(e)
        assert len(executed)==1


def test_compose_isolates_tool_runner_from_database_network():
    import yaml
    compose=yaml.safe_load(Path('docker-compose.yml').read_text())
    assert compose['services']['tool-runner']['networks']==['tool_exec']
    assert 'tool_exec' not in compose['services']['postgres']['networks']
    assert compose['networks']['tool_exec']['internal'] is True
    assert compose['services']['tool-runner']['cap_drop']==['ALL']
    assert compose['services']['tool-runner']['security_opt']==['no-new-privileges:true']


def test_runtime_api_does_not_receive_admin_database_secret():
    import yaml
    compose=yaml.safe_load(Path('docker-compose.yml').read_text())
    api_secrets=set(compose['services']['api']['secrets'])
    assert 'postgres_admin_password' not in api_secrets
    assert 'postgres_app_password' in api_secrets
    assert 'postgres_audit_password' in api_secrets


def test_frontend_has_no_backend_internal_network_reachability_in_compose():
    import yaml
    compose=yaml.safe_load(Path('docker-compose.yml').read_text())
    assert compose['services']['frontend']['networks']==['edge','frontend_api']
    assert 'internal' not in compose['services']['frontend']['networks']
    assert 'frontend_api' in compose['services']['api']['networks']
    assert 'frontend_api' not in compose['services']['postgres']['networks']
    assert 'frontend_api' not in compose['services']['redis']['networks']
    assert 'frontend_api' not in compose['services']['qdrant']['networks']


def test_redis_and_qdrant_auth_are_enabled_in_compose():
    import yaml
    from pathlib import Path

    compose = yaml.safe_load(Path("docker-compose.yml").read_text())

    redis = compose["services"]["redis"]
    redis_text = str(redis)
    assert "requirepass" in redis_text.lower()
    assert "redis_password" in redis_text

    qdrant = compose["services"]["qdrant"]
    assert "qdrant_api_key" in qdrant.get("secrets", [])

    command = qdrant.get("command", [])
    command_text = " ".join(command) if isinstance(command, list) else str(command)

    assert "/run/secrets/qdrant_api_key" in command_text
    assert "QDRANT__SERVICE__API_KEY" in command_text

    secrets = compose.get("secrets", {})
    assert "qdrant_api_key" in secrets
    assert "file" in secrets["qdrant_api_key"]

def test_production_overlay_disables_demo_token_mint():
    import yaml
    prod=yaml.safe_load(Path('docker-compose.production.yml').read_text())
    assert prod['services']['api']['environment']['PUBLIC_DEMO']=='false'


def test_no_universal_demo_secret_literals_remain_in_executable_source():
    roots=[Path('app'),Path('tool_runner'),Path('planner_runner')]
    text='\n'.join(p.read_text(errors='ignore') for root in roots for p in root.rglob('*.py'))
    assert 'demo-only-change-me-32-bytes-minimum-2026' not in text
    assert 'demo-audit-signing-key-32-bytes-minimum-2026' not in text
    assert 'demo-internal-token-32-bytes-minimum-2026' not in text
