"""Smoke tests for agent-cost-allocator-mcp."""
import sys, os, inspect, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    open_ledger,
    record_charge,
    tenant_chargeback_summary,
    full_ledger_summary,
    product_breakdown,
    list_ledgers,
    _LEDGERS,
)


def test_open_ledger_returns_id():
    _LEDGERS.clear()
    r = open_ledger(period_label="2026-05")
    assert r["ledger_id"].startswith("ledger_")
    assert r["period_label"] == "2026-05"


def test_record_charge_attributes_to_tenant():
    _LEDGERS.clear()
    r = open_ledger()
    lid = r["ledger_id"]
    record_charge(lid, "customer_A", "claude-opus-4.7", 1000, 200, product_code="compliance-scan")
    summary = tenant_chargeback_summary(lid, "customer_A")
    # 1200 / 1000 * 0.040 = 0.048
    assert abs(summary["total_cost"] - 0.048) < 0.001
    assert summary["total_calls"] == 1


def test_multiple_tenants_segregated():
    _LEDGERS.clear()
    r = open_ledger()
    lid = r["ledger_id"]
    record_charge(lid, "A", "claude-opus-4.7", 1000, 0)
    record_charge(lid, "B", "claude-haiku-4.5", 5000, 100)
    s_a = tenant_chargeback_summary(lid, "A")
    s_b = tenant_chargeback_summary(lid, "B")
    assert s_a["total_cost"] != s_b["total_cost"]
    assert s_a["total_cost"] > s_b["total_cost"]  # opus more expensive even with fewer tokens


def test_full_ledger_summary_orders_by_cost():
    _LEDGERS.clear()
    r = open_ledger()
    lid = r["ledger_id"]
    record_charge(lid, "small", "ollama-local", 1000, 100)  # £0
    record_charge(lid, "big", "claude-opus-4.7", 100000, 50000)  # ~£6
    s = full_ledger_summary(lid)
    assert s["tenants"][0]["tenant_id"] == "big"


def test_product_breakdown():
    _LEDGERS.clear()
    r = open_ledger()
    lid = r["ledger_id"]
    record_charge(lid, "A", "claude-opus-4.7", 1000, 200, product_code="compliance-scan")
    record_charge(lid, "B", "gpt-5", 2000, 500, product_code="compliance-scan")
    record_charge(lid, "A", "claude-haiku-4.5", 10000, 1000, product_code="bias-check")
    p = product_breakdown(lid, "compliance-scan")
    assert p["total_calls"] == 2
    assert len(p["by_tenant"]) == 2


def test_signed_summary_has_signature():
    _LEDGERS.clear()
    r = open_ledger()
    lid = r["ledger_id"]
    record_charge(lid, "X", "claude-opus-4.7", 500, 100)
    s = tenant_chargeback_summary(lid, "X")
    assert "signature" in s
    assert s["verify_url"] == "https://verify.meok.ai"


def test_unknown_ledger_error():
    r = tenant_chargeback_summary("does_not_exist", "any")
    assert "error" in r


def test_list_ledgers():
    _LEDGERS.clear()
    open_ledger(period_label="2026-05")
    open_ledger(period_label="2026-06")
    r = list_ledgers()
    assert r["count"] == 2


def test_ollama_local_free():
    _LEDGERS.clear()
    r = open_ledger()
    lid = r["ledger_id"]
    record_charge(lid, "any", "ollama-local", 1000000, 500000)
    s = tenant_chargeback_summary(lid, "any")
    assert s["total_cost"] == 0.0


if __name__ == "__main__":
    g = dict(globals())
    fns = [v for k, v in g.items() if k.startswith("test_") and inspect.isfunction(v)]
    p = f = 0
    for fn in fns:
        try:
            fn(); print(f"✓ {fn.__name__}"); p += 1
        except Exception as e:
            print(f"✗ {fn.__name__}: {type(e).__name__}: {e}"); traceback.print_exc(); f += 1
    print(f"\n{p} passed, {f} failed")
