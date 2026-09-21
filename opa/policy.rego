package aurelian.authz

default decision = {"allowed": false, "requires_approval": false, "approval_tier": "none", "risk": "unknown", "reason": "default deny"}

role_level = {"viewer":0,"operator":1,"admin":2,"executive":3}
action_risk = {
  "search_knowledge":"low", "get_service_health":"low", "list_inventory":"low", "recommend_reorders":"low",
  "get_customer_profile":"low", "get_order_backlog":"low", "send_notice":"medium", "restart_service":"medium",
  "change_product_price":"high", "issue_refund":"high", "disable_user_account":"high"
}
min_level = {"low":0,"medium":1,"high":1}
approval = {"low":"none","medium":"team","high":"executive_mfa"}

decision = out {
  risk := action_risk[input.action]
  role_level[input.role] >= min_level[risk]
  not injection_side_effect(risk)
  tier := approval[risk]
  out := {"allowed": tier == "none", "requires_approval": tier != "none", "approval_tier": tier, "risk": risk, "reason": sprintf("OPA: %s risk / %s approval", [risk,tier])}
}

injection_side_effect(risk) {
  input.input_risk != "low"
  risk != "low"
}
