# Agent Cost Allocator MCP

> ## 🧱 Part of the MEOK A2A Substrate (£499/mo)
> See [meok.ai/a2a](https://meok.ai/a2a).

# Multi-tenant LLM cost attribution for chargeback billing

<!-- mcp-name: io.github.CSOAI-ORG/agent-cost-allocator-mcp -->

[![PyPI](https://img.shields.io/pypi/v/agent-cost-allocator-mcp)](https://pypi.org/project/agent-cost-allocator-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## The product

Splits one agent's spend across many tenants for chargeback billing. Without cost attribution, agentic SaaS providers can't bill customer A for £X and customer B for £Y based on real LLM usage. This MCP solves that with a signed per-tenant ledger.

Companion to `agent-token-budget-mcp` (per-session caps) — that MCP stops spending, this one attributes it back.

## Tools

| Tool | Purpose |
|---|---|
| `open_ledger(ledger_id?, currency, period_label?)` | New monthly ledger |
| `record_charge(ledger_id, tenant_id, model, input/output_tokens, product_code?)` | Record one billable call |
| `tenant_chargeback_summary(ledger_id, tenant_id)` | Signed invoice-ready summary |
| `full_ledger_summary(ledger_id)` | Grand total + tenant ranking |
| `product_breakdown(ledger_id, product_code)` | Per-product COGS across all tenants |
| `list_ledgers()` | All open ledgers |

## Use cases

- **Multi-tenant agent SaaS** — bill customer-level usage
- **Internal IT cross-charging** across departments
- **Reseller white-label** — split MEOK gateway costs across resellers' customers
- **Customer support COGS** — "agent used £X across N tickets for customer Y"
- **Per-product economics** — "compliance-scan costs us £0.04/call, sells for £0.50, gross margin 92%"

## Sister MCPs

Part of the MEOK **A2A** pack:

- `agent-token-budget-mcp` — caps spend per session
- `bft-progress-council-mcp` — halts loops
- `agent-rate-limiter-mcp` — throttle calls
- `agent-audit-logger-mcp` — hash-chained log
- `agent-commerce-protocol-mcp` — Stripe ACP for invoicing the chargebacks

Full catalogue: [meok.ai/anthropic-registry](https://meok.ai/anthropic-registry)

## Protocol coverage + Universal PAYG

| Option | Price |
|---|---|
| Self-host MIT | £0 |
| Universal PAYG | £29/mo + £0.0002/call |
| A2A Substrate | £499/mo |
| Universe | £1,499/mo |
| Defence | £4,990/mo |

Buy: https://meok.ai/a2a

## Licence

MIT. By [MEOK AI Labs](https://meok.ai) (CSOAI LTD, UK Companies House 16939677).
