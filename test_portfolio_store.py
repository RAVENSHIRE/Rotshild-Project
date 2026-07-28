"""Sanity tests for normalized holdings persistence. Run with: python test_portfolio_store.py"""

from __future__ import annotations

import importlib
import os
import tempfile


def _load_store(tmp_path: str):
    os.environ["PORTFOLIO_DB_PATH"] = tmp_path
    import portfolio_store

    return importlib.reload(portfolio_store)


def test_seed_and_list():
    with tempfile.TemporaryDirectory() as td:
        ps = _load_store(f"{td}/portfolio.db")
        ps.init_db()
        rows = ps.list_holdings(include_inactive=False)
        assert rows, "expected seeded holdings"
        assert all("ticker" in r for r in rows)


def test_upsert_and_get():
    with tempfile.TemporaryDirectory() as td:
        ps = _load_store(f"{td}/portfolio.db")
        ps.init_db()
        ps.upsert_holding(
            {
                "ticker": "NESN.SW",
                "asset_name": "Nestle SA",
                "quantity": 120.0,
                "portfolio_bucket": ps.BUCKET_DIVERSIFY,
                "sector": "Consumer Staples",
                "sub_sector": "Packaged Food",
                "currency": "CHF",
            }
        )
        row = ps.get_holding("NESN.SW")
        assert row["asset_name"] == "Nestle SA"
        assert row["quantity"] == 120.0
        assert row["portfolio_bucket"] == ps.BUCKET_DIVERSIFY


def test_add_ticker_workflow_and_price_update():
    with tempfile.TemporaryDirectory() as td:
        ps = _load_store(f"{td}/portfolio.db")
        ps.init_db()
        row = ps.add_ticker_workflow(
            {
                "ticker": "XLF",
                "asset_name": "Financial Select Sector SPDR",
                "quantity": 800.0,
                "portfolio_bucket": ps.BUCKET_RETURN,
                "sector": "Financials",
                "sub_sector": "Banks",
                "currency": "USD",
            }
        )
        assert row["ticker"] == "XLF"

        ps.mark_price_updates({"XLF": 41.25})
        updated = ps.get_holding("XLF")
        assert updated["current_price"] == 41.25
        assert updated["last_updated"]


def test_deactivate_holding():
    with tempfile.TemporaryDirectory() as td:
        ps = _load_store(f"{td}/portfolio.db")
        ps.init_db()
        ps.deactivate_holding("AAPL")
        active = {r["ticker"] for r in ps.list_holdings(include_inactive=False)}
        assert "AAPL" not in active


def test_sector_lookup_validation():
    with tempfile.TemporaryDirectory() as td:
        ps = _load_store(f"{td}/portfolio.db")
        ps.init_db()
        lookup = ps.sector_lookup()
        assert "Technology" in lookup
        assert "Semiconductors" in lookup["Technology"]

        try:
            ps.upsert_holding(
                {
                    "ticker": "TEST1",
                    "asset_name": "Test Name",
                    "quantity": 1,
                    "portfolio_bucket": ps.BUCKET_RETURN,
                    "sector": "Technology",
                    "sub_sector": "NotAllowed",
                    "currency": "USD",
                }
            )
            raise AssertionError("expected ValueError for invalid sub-sector")
        except ValueError as exc:
            assert "not valid for sector" in str(exc)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
