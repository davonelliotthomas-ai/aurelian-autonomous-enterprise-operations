import json,sys,time
try:
 import resource
 resource.setrlimit(resource.RLIMIT_CPU,(2,2)); resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
except Exception: pass
p=json.loads(sys.stdin.read() or "{}")
tool=p.get("tool"); args=p.get("args",{})
if tool=="get_service_health": out={"service":args.get("service","core-api"),"status":"healthy","latency_ms":42,"sandbox":"subprocess"}
elif tool=="restart_service": out={"service":args.get("service","core-api"),"restarted":True,"sandbox":"subprocess","mode":"simulated-safe-lab-action"}
elif tool=="send_notice": out={"delivered":True,"channel":args.get("channel","ops"),"message":args.get("message",""),"sandbox":"subprocess","mode":"demo-sink"}
elif tool=="simulate_timeout": time.sleep(10); out={}
else: raise SystemExit("tool not allow-listed")
print(json.dumps(out))
