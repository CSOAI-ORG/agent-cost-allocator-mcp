#!/usr/bin/env python3
"""
Agent Cost Allocator MCP — multi-tenant LLM cost attribution
============================================================

By MEOK AI Labs · https://meok.ai · MIT
<!-- mcp-name: io.github.CSOAI-ORG/agent-cost-allocator-mcp -->

WHAT THIS DOES
--------------
Splits ONE agent's spend across MANY tenants for chargeback billing.

Agentic SaaS providers run one agent that serves N customers. Without cost
attribution, you can't bill customer A for £X and customer B for £Y based
on actual LLM usage. This MCP solves that:

  1. Open a tenant ledger
  2. When the agent does work, tag the call with tenant_id
  3. Aggregate cost per tenant per period
  4. Emit signed chargeback summaries customers (and your accountants) trust

Companion to agent-token-budget-mcp (per-session caps) — that MCP stops the
spending, this MCP attributes it back to who caused it.

USE CASES
---------
- Multi-tenant agent SaaS — bill customer-level usage
- Internal IT cross-charging across departments
- Reseller white-label — split MEOK gateway costs across resellers' customers
- Customer support — "agent used £X across N tickets"
- Per-product cost-of-goods tracking

PRICING
-------
Free MIT self-host · £29/mo Starter · £79/mo Pro · A2A Substrate £499/mo
(https://meok.ai/a2a) · Universe £1,499/mo.
"""

from __future__ import annotations
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("agent-cost-allocator")
_HMAC_SECRET = os.environ.get("MEOK_HMAC_SECRET", "")


# Cost rates per 1K tokens (refresh quarterly).
COST_PER_1K_GBP = {
    "claude-opus-4.7":   0.040,
    "claude-sonnet-4.6": 0.012,
    "claude-haiku-4.5":  0.003,
    "gpt-5":             0.035,
    "gpt-5-mini":        0.010,
    "gemini-2.5-pro":    0.020,
    "gemini-2.5-flash":  0.004,
    "llama-3.3-70b":     0.002,
    "step-3.6-flash":    0.001,
    "ollama-local":      0.000,
    "default":           0.025,
}


# In-memory ledger. Production: KV / Postgres.
# {ledger_id: {currency, period_start, calls: [...], tenants: {tenant_id: {tokens_in, tokens_out, cost_gbp, calls, products}}}}
_LEDGERS: dict[str, dict] = {}


def _sign(payload: dict) -> str:
    if not _HMAC_SECRET:
        return "unsigned-no-key-configured"
    return hmac.new(_HMAC_SECRET.encode(), json.dumps(payload, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calc_cost(model: str, in_tok: int, out_tok: int) -> float:
    rate = COST_PER_1K_GBP.get(model, COST_PER_1K_GBP["default"])
    return ((in_tok + out_tok) / 1000.0) * rate


# ────────────────────────────────────────────────────────────────────────
# Tools
# ────────────────────────────────────────────────────────────────────────

@mcp.tool()
def open_ledger(
    ledger_id: Optional[str] = None,
    currency: str = "GBP",
    period_label: Optional[str] = None,
) -> dict:
    """
    Open a new cost-attribution ledger for a billing period.

    Args:
        ledger_id: Optional explicit ID. Auto-generated if omitted.
        currency: ISO 4217. Default GBP.
        period_label: Optional label, e.g. "2026-05" for monthly.

    Returns:
        {ledger_id, currency, period_label, started_at}
    """
    lid = ledger_id or f"ledger_{int(time.time())}_{os.urandom(4).hex()}"
    _LEDGERS[lid] = {
        "ledger_id": lid,
        "currency": currency.upper(),
        "period_label": period_label or datetime.now(timezone.utc).strftime("%Y-%m"),
        "started_at": _ts(),
        "calls": [],
        "tenants": {},
    }
    return {
        "ledger_id": lid,
        "currency": currency.upper(),
        "period_label": _LEDGERS[lid]["period_label"],
        "started_at": _LEDGERS[lid]["started_at"],
        "hint": "Call record_charge() after every billable agent action with tenant_id + model + tokens.",
    }


@mcp.tool()
def record_charge(
    ledger_id: str,
    tenant_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    product_code: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """
    Record a billable LLM call against a tenant.

    Args:
        ledger_id: From open_ledger().
        tenant_id: The customer / department / reseller charged.
        model: Model ID for rate lookup.
        input_tokens / output_tokens: Token counts.
        product_code: Optional product/feature tag (e.g. "compliance-scan", "report-gen").
        note: Free-text.

    Returns:
        {charge_id, cost_gbp, tenant_running_total_gbp}
    """
    led = _LEDGERS.get(ledger_id)
    if not led:
        return {"error": "unknown_ledger"}

    cost = _calc_cost(model, input_tokens, output_tokens)
    cid = f"charge_{int(time.time())}_{os.urandom(4).hex()}"
    entry = {
        "charge_id": cid,
        "ts": _ts(),
        "tenant_id": tenant_id,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": round(cost, 6),
        "product_code": product_code,
        "note": note,
    }
    led["calls"].append(entry)

    t = led["tenants"].setdefault(tenant_id, {"tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0, "products": {}})
    t["tokens_in"] += input_tokens
    t["tokens_out"] += output_tokens
    t["cost"] = round(t["cost"] + cost, 6)
    t["calls"] += 1
    if product_code:
        p = t["products"].setdefault(product_code, {"cost": 0.0, "calls": 0})
        p["cost"] = round(p["cost"] + cost, 6)
        p["calls"] += 1

    return {
        "charge_id": cid,
        "cost": round(cost, 6),
        "tenant_running_total": round(t["cost"], 6),
        "tenant_call_count": t["calls"],
        "currency": led["currency"],
    }


@mcp.tool()
def tenant_chargeback_summary(ledger_id: str, tenant_id: str) -> dict:
    """
    Signed chargeback summary for one tenant — ready to attach to an invoice.

    Args:
        ledger_id: From open_ledger().
        tenant_id: Tenant to summarise.

    Returns:
        {tenant_id, total_cost, breakdown, signed_attestation}
    """
    led = _LEDGERS.get(ledger_id)
    if not led:
        return {"error": "unknown_ledger"}
    t = led["tenants"].get(tenant_id)
    if not t:
        return {"error": "unknown_tenant", "tenant_id": tenant_id}

    summary = {
        "ledger_id": ledger_id,
        "tenant_id": tenant_id,
        "period_label": led["period_label"],
        "currency": led["currency"],
        "total_cost": round(t["cost"], 6),
        "total_calls": t["calls"],
        "total_input_tokens": t["tokens_in"],
        "total_output_tokens": t["tokens_out"],
        "product_breakdown": t.get("products", {}),
        "ts": _ts(),
    }
    sig = _sign(summary)
    return {**summary, "signature": sig, "verify_url": "https://verify.meok.ai"}


@mcp.tool()
def full_ledger_summary(ledger_id: str) -> dict:
    """
    Full ledger summary across all tenants + grand total.

    Returns:
        {ledger_id, period_label, currency, total_cost, tenants, top_n}
    """
    led = _LEDGERS.get(ledger_id)
    if not led:
        return {"error": "unknown_ledger"}

    tenants_list = []
    grand_total = 0.0
    for tid, t in led["tenants"].items():
        tenants_list.append({
            "tenant_id": tid,
            "cost": round(t["cost"], 6),
            "calls": t["calls"],
            "tokens_in": t["tokens_in"],
            "tokens_out": t["tokens_out"],
            "product_breakdown": t.get("products", {}),
        })
        grand_total += t["cost"]

    tenants_sorted = sorted(tenants_list, key=lambda x: x["cost"], reverse=True)

    summary = {
        "ledger_id": ledger_id,
        "period_label": led["period_label"],
        "currency": led["currency"],
        "total_cost": round(grand_total, 6),
        "tenant_count": len(tenants_sorted),
        "tenants": tenants_sorted,
        "top_5_tenants_by_cost": tenants_sorted[:5],
        "total_calls": sum(t["calls"] for t in led["tenants"].values()),
        "ts": _ts(),
    }
    sig = _sign(summary)
    return {**summary, "signature": sig, "verify_url": "https://verify.meok.ai"}


@mcp.tool()
def product_breakdown(ledger_id: str, product_code: str) -> dict:
    """
    Cost of one product across all tenants — for COGS / product-economics analysis.

    Args:
        ledger_id: From open_ledger().
        product_code: e.g. "compliance-scan", "report-gen".

    Returns:
        {product_code, total_cost, by_tenant, average_per_call}
    """
    led = _LEDGERS.get(ledger_id)
    if not led:
        return {"error": "unknown_ledger"}

    by_tenant = {}
    total_cost = 0.0
    total_calls = 0
    for tid, t in led["tenants"].items():
        p = t.get("products", {}).get(product_code)
        if p:
            by_tenant[tid] = {"cost": p["cost"], "calls": p["calls"]}
            total_cost += p["cost"]
            total_calls += p["calls"]

    return {
        "product_code": product_code,
        "total_cost": round(total_cost, 6),
        "total_calls": total_calls,
        "tenant_count": len(by_tenant),
        "average_per_call": round(total_cost / max(total_calls, 1), 6),
        "by_tenant": by_tenant,
        "currency": led["currency"],
    }


@mcp.tool()
def list_ledgers() -> dict:
    """List all open ledger IDs + period labels."""
    return {
        "count": len(_LEDGERS),
        "ledgers": [
            {"ledger_id": lid, "period_label": led["period_label"], "currency": led["currency"], "tenant_count": len(led["tenants"])}
            for lid, led in _LEDGERS.items()
        ],
    }


if __name__ == "__main__":
    mcp.run()
