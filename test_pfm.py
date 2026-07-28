"""Sanity tests for the PFM layer. Run with: python test_pfm.py"""

import pfm


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def test_desk_totals_consistent():
    desk = pfm.desk_overview()
    assert desk["totals"]["clients"] == len(pfm.PORTFOLIOS)
    assert approx(desk["totals"]["aum"], sum(p.value for p in pfm.PORTFOLIOS.values()), tol=1.0)


def test_retail_blocked_instrument_breaches():
    detail = pfm.portfolio_detail("PF-2003")  # Retail client holding SLV
    suit = next(r for r in detail["restrictions"] if r["rule_id"] == "SUIT-RET")
    assert suit["status"] == pfm.BREACH
    assert "SLV" in suit["measured"]


def test_private_client_has_no_retail_rule():
    detail = pfm.portfolio_detail("PF-2001")
    assert all(r["rule_id"] != "SUIT-RET" for r in detail["restrictions"])


def test_low_cash_discretionary_flags_liquidity():
    detail = pfm.portfolio_detail("PF-2006")  # 0.9% cash on a discretionary mandate
    liq = next(r for r in detail["restrictions"] if r["rule_id"] == "LIQ-CASH")
    assert liq["status"] in {pfm.WARNING, pfm.BREACH}


def test_concentration_rule_flags_single_line():
    detail = pfm.portfolio_detail("PF-2004")  # NVDA ~32.8% of the book
    con = next(r for r in detail["restrictions"] if r["rule_id"] == "CON-POS")
    assert con["status"] == pfm.BREACH
    assert "NVDA" in con["measured"]


def test_rebalance_orders_are_self_financing():
    result = pfm.rebalance_portfolio("PF-2001")
    net = sum(o["amount"] for o in result["orders"])
    assert abs(net) < 2.0, net


def test_rebalance_lands_on_model_targets():
    result = pfm.rebalance_portfolio("PF-2001")
    model = pfm.TARGET_MODELS["MDL-BAL"]
    for row in result["classes_after"]:
        target = model.targets.get(row["asset_class"], 0.0) * 100
        assert abs(row["after"] - target) < 0.5, (row, target)


def test_rebalance_clears_liquidity_flag():
    # PF-2006 breaches min-cash today; the model rebalance restores the buffer.
    result = pfm.rebalance_portfolio("PF-2006")
    liq = next(r for r in result["pre_trade_check"] if r["rule_id"] == "LIQ-CASH")
    assert liq["status"] == pfm.PASS


def test_weights_after_applies_orders():
    pf = pfm.PORTFOLIOS["PF-2006"]
    before = pf.weights().get(pfm.CASH, 0.0)
    after = pfm._weights_after(pf, [{"instrument": pfm.CASH, "amount": 100_000}])
    assert after[pfm.CASH] > before


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
