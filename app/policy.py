from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import yaml
import httpx
from .auth import ROLE_LEVEL, Principal
from .config import settings

POLICY_PATH = Path(__file__).resolve().parents[1] / "policies" / "policy.yaml"
POLICY_RAW = POLICY_PATH.read_bytes()
POLICY = yaml.safe_load(POLICY_RAW)
POLICY_FINGERPRINT = hashlib.sha256(POLICY_RAW).hexdigest()
OPA_POLICY_PATH = Path(__file__).resolve().parents[1] / "opa" / "policy.rego"
OPA_POLICY_FINGERPRINT = hashlib.sha256(OPA_POLICY_PATH.read_bytes()).hexdigest() if OPA_POLICY_PATH.exists() else "unavailable"


@dataclass
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    approval_tier: str
    risk: str
    reason: str
    source: str = "local-yaml"
    policy_fingerprint: str = POLICY_FINGERPRINT


def _local_decision(action: str, principal: Principal, environment: str, input_risk: str) -> PolicyDecision:
    cfg = POLICY["actions"].get(action)
    if not cfg:
        return PolicyDecision(False, False, "none", "unknown", "Action is not registered in policy.")
    risk = cfg.get("risk", "high")
    tier = POLICY["risk_tiers"][risk]
    minimum = cfg.get("minimum_role", tier["minimum_role"])
    if ROLE_LEVEL.get(principal.role, -1) < ROLE_LEVEL.get(minimum, 99):
        return PolicyDecision(False, False, "none", risk, f"{action} requires {minimum}; requester is {principal.role}.")
    if input_risk in {"medium", "high"} and risk in {"medium", "high"} and POLICY["constraints"].get("block_side_effect_on_prompt_injection"):
        return PolicyDecision(False, False, "none", risk, "Potential prompt-injection indicators detected; side-effecting execution is blocked.")
    approval = tier.get("approval", "none")
    if environment == "production" and risk in {"medium", "high"}:
        return PolicyDecision(False, True, approval, risk, f"{risk}-risk production action requires {approval} approval.")
    if approval != "none":
        return PolicyDecision(False, True, approval, risk, f"{risk}-risk action requires {approval} approval.")
    return PolicyDecision(True, False, "none", risk, "Declarative policy permits immediate execution.")


async def evaluate(action: str, principal: Principal, environment: str, input_risk: str = "low") -> PolicyDecision:
    local = _local_decision(action, principal, environment, input_risk)
    if not settings.opa_url:
        return local

    payload = {
        "input": {
            "action": action,
            "role": principal.role,
            "scopes": sorted(principal.scopes),
            "mfa": principal.mfa,
            "environment": environment,
            "input_risk": input_risk,
        }
    }
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.post(
                settings.opa_url.rstrip("/") + "/v1/data/aurelian/authz/decision",
                json=payload,
            )
            r.raise_for_status()
            d = r.json().get("result", {})
            return PolicyDecision(
                bool(d.get("allowed")),
                bool(d.get("requires_approval")),
                str(d.get("approval_tier", "none")),
                str(d.get("risk", "unknown")),
                str(d.get("reason", "OPA decision")),
                "opa",
                OPA_POLICY_FINGERPRINT,
            )
    except Exception as exc:
        # When OPA is configured, policy-engine failure is not permission. Fail
        # closed rather than silently replacing the authoritative decision with
        # a local rule set.
        return PolicyDecision(
            False,
            False,
            "none",
            local.risk,
            f"OPA unavailable; fail-closed ({type(exc).__name__}).",
            "opa-fail-closed",
            OPA_POLICY_FINGERPRINT,
        )


def approval_authorized(decision: PolicyDecision, principal: Principal) -> tuple[bool, str]:
    if not decision.requires_approval:
        return False, "Current policy no longer permits an approval-mediated execution."
    if decision.approval_tier == "team":
        return ("approve:team" in principal.scopes, "team approval scope required")
    if decision.approval_tier == "executive_mfa":
        ok = "approve:executive" in principal.scopes and principal.mfa
        return (ok, "executive scope + MFA required")
    return False, "Unknown approval tier"
