"""Persistence layer for normalized portfolio holdings.

The dashboard stores one holding per instrument row (ticker as key), plus a
catalog table for onboarding new tickers with bucket/sector classifications.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("PORTFOLIO_DB_PATH", str(ROOT / "portfolio.db")))

BUCKET_RETURN = "Return Assets"
BUCKET_DIVERSIFY = "Diversifying Assets"
VALID_BUCKETS = {BUCKET_RETURN, BUCKET_DIVERSIFY}

SECTOR_SUBSECTOR_MAP: dict[str, list[str]] = {
    "Technology": ["Consumer Hardware", "Software & Cloud", "Semiconductors"],
    "Fixed Income": ["Long Government Bonds", "Government Bonds", "Investment Grade Credit"],
    "Alternatives": ["Precious Metals", "Listed Real Estate", "Commodities"],
    "Financials": ["Banks", "Insurance", "Asset Managers"],
    "Consumer Staples": ["Packaged Food", "Beverages", "Household Products"],
    "Healthcare": ["Pharma", "Biotech", "Medical Devices"],
    "Unclassified": ["Unclassified"],
}

_TICKER_RE = re.compile(r"^[A-Z0-9.=\-]{1,20}$")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_bucket(bucket: str | None) -> str:
    raw = (bucket or "").strip()
    if raw.lower() in {"return", "return asset", "return assets"}:
        return BUCKET_RETURN
    if raw.lower() in {"diversifying", "diversifying asset", "diversifying assets"}:
        return BUCKET_DIVERSIFY
    if raw in VALID_BUCKETS:
        return raw
    raise ValueError("bucket must be 'Return Assets' or 'Diversifying Assets'")


def _normalize_ticker(ticker: str | None) -> str:
    value = (ticker or "").strip().upper()
    if not value or not _TICKER_RE.match(value):
        raise ValueError("ticker is invalid (use e.g. AAPL, NESN.SW, BTC-USD)")
    return value


def _normalize_currency(currency: str | None) -> str:
    value = (currency or "CHF").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("currency must be a 3-letter ISO code like CHF or USD")
    return value


def _normalize_sector_pair(sector: str | None, sub_sector: str | None) -> tuple[str, str]:
    sec = (sector or "Unclassified").strip() or "Unclassified"
    sub = (sub_sector or "Unclassified").strip() or "Unclassified"
    allowed = SECTOR_SUBSECTOR_MAP.get(sec)
    if allowed is not None and sub not in allowed:
        raise ValueError(
            f"sub_sector '{sub}' is not valid for sector '{sec}'. Allowed: {', '.join(allowed)}"
        )
    return sec, sub


def _to_holding_dict(row: sqlite3.Row) -> dict:
    return {
        "ticker": row["ticker"],
        "asset_name": row["asset_name"],
        "current_price": row["last_price"],
        "quantity": float(row["quantity"]),
        "portfolio_bucket": row["bucket"],
        "sector": row["sector"],
        "sub_sector": row["sub_sector"],
        "currency": row["currency"],
        "last_updated": row["last_updated"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holdings (
              ticker TEXT PRIMARY KEY,
              asset_name TEXT NOT NULL,
              quantity REAL NOT NULL CHECK(quantity >= 0),
              bucket TEXT NOT NULL,
              sector TEXT NOT NULL,
              sub_sector TEXT NOT NULL,
              currency TEXT NOT NULL,
              last_price REAL,
              last_updated TEXT,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticker_catalog (
              ticker TEXT PRIMARY KEY,
              asset_name TEXT NOT NULL,
              bucket TEXT NOT NULL,
              sector TEXT NOT NULL,
              sub_sector TEXT NOT NULL,
              currency TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        _seed_if_empty(conn)


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    count = int(conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0])
    if count > 0:
        return

    now = _now_iso()
    seed = [
        ("AAPL", "Apple Inc.", 3500.0, BUCKET_RETURN, "Technology", "Consumer Hardware", "USD", now, now),
        ("MSFT", "Microsoft Corp.", 2800.0, BUCKET_RETURN, "Technology", "Software & Cloud", "USD", now, now),
        ("NVDA", "NVIDIA Corp.", 1200.0, BUCKET_RETURN, "Technology", "Semiconductors", "USD", now, now),
        ("TLT", "iShares 20+ Year Treasury", 4200.0, BUCKET_DIVERSIFY, "Fixed Income", "Long Government Bonds", "USD", now, now),
        ("GLD", "SPDR Gold Shares", 1400.0, BUCKET_DIVERSIFY, "Alternatives", "Precious Metals", "USD", now, now),
    ]
    conn.executemany(
        """
        INSERT INTO holdings(
          ticker, asset_name, quantity, bucket, sector, sub_sector, currency,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        seed,
    )
    conn.executemany(
        """
        INSERT INTO ticker_catalog(
          ticker, asset_name, bucket, sector, sub_sector, currency,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
          asset_name=excluded.asset_name,
          bucket=excluded.bucket,
          sector=excluded.sector,
          sub_sector=excluded.sub_sector,
          currency=excluded.currency,
          updated_at=excluded.updated_at
        """,
        [(t, n, b, s, ss, c, now, now) for (t, n, _q, b, s, ss, c, _ca, _ua) in seed],
    )


def list_holdings(*, include_inactive: bool = False) -> list[dict]:
    where = "" if include_inactive else "WHERE is_active = 1"
    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, asset_name, quantity, bucket, sector, sub_sector,
                   currency, last_price, last_updated, is_active,
                   created_at, updated_at
            FROM holdings
            {where}
            ORDER BY bucket ASC, ticker ASC
            """
        ).fetchall()
    return [_to_holding_dict(r) for r in rows]


def upsert_holding(holding: dict) -> dict:
    ticker = _normalize_ticker(holding.get("ticker"))
    asset_name = (holding.get("asset_name") or ticker).strip()
    if not asset_name:
        raise ValueError("asset_name is required")
    quantity = float(holding.get("quantity", 0.0))
    if quantity < 0:
        raise ValueError("quantity must be >= 0")
    bucket = _normalize_bucket(holding.get("portfolio_bucket") or holding.get("bucket"))
    sector, sub_sector = _normalize_sector_pair(holding.get("sector"), holding.get("sub_sector"))
    currency = _normalize_currency(holding.get("currency"))
    is_active = 0 if holding.get("is_active") is False else 1
    now = _now_iso()

    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO holdings(
              ticker, asset_name, quantity, bucket, sector, sub_sector,
              currency, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
              asset_name=excluded.asset_name,
              quantity=excluded.quantity,
              bucket=excluded.bucket,
              sector=excluded.sector,
              sub_sector=excluded.sub_sector,
              currency=excluded.currency,
              is_active=excluded.is_active,
              updated_at=excluded.updated_at
            """,
            (
                ticker,
                asset_name,
                quantity,
                bucket,
                sector,
                sub_sector,
                currency,
                is_active,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO ticker_catalog(
              ticker, asset_name, bucket, sector, sub_sector, currency,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
              asset_name=excluded.asset_name,
              bucket=excluded.bucket,
              sector=excluded.sector,
              sub_sector=excluded.sub_sector,
              currency=excluded.currency,
              updated_at=excluded.updated_at
            """,
            (ticker, asset_name, bucket, sector, sub_sector, currency, now, now),
        )

    return get_holding(ticker)


def get_holding(ticker: str) -> dict:
    t = _normalize_ticker(ticker)
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT ticker, asset_name, quantity, bucket, sector, sub_sector,
                   currency, last_price, last_updated, is_active,
                   created_at, updated_at
            FROM holdings
            WHERE ticker = ?
            """,
            (t,),
        ).fetchone()
    if row is None:
        raise ValueError(f"holding '{t}' not found")
    return _to_holding_dict(row)


def deactivate_holding(ticker: str) -> None:
    t = _normalize_ticker(ticker)
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE holdings SET is_active=0, updated_at=? WHERE ticker=?",
            (_now_iso(), t),
        )
        if cur.rowcount == 0:
            raise ValueError(f"holding '{t}' not found")


def mark_price_updates(prices: dict[str, float | None], updated_at: str | None = None) -> None:
    ts = updated_at or _now_iso()
    with _conn() as conn:
        for ticker, price in prices.items():
            t = _normalize_ticker(ticker)
            if price is None:
                continue
            conn.execute(
                """
                UPDATE holdings
                SET last_price = ?, last_updated = ?, updated_at = ?
                WHERE ticker = ?
                """,
                (float(price), ts, ts, t),
            )


def list_ticker_catalog() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT ticker, asset_name, bucket, sector, sub_sector, currency,
                   created_at, updated_at
            FROM ticker_catalog
            ORDER BY ticker ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def sector_lookup() -> dict[str, list[str]]:
    """Lookup map for UI dropdowns and backend validation parity."""
    return {k: list(v) for k, v in SECTOR_SUBSECTOR_MAP.items()}


def add_ticker_workflow(payload: dict) -> dict:
    """Register ticker metadata and optionally create/overwrite a holding row."""
    ticker = _normalize_ticker(payload.get("ticker"))
    asset_name = (payload.get("asset_name") or ticker).strip() or ticker
    bucket = _normalize_bucket(payload.get("portfolio_bucket") or payload.get("bucket"))
    sector = (payload.get("sector") or "Unclassified").strip() or "Unclassified"
    sub_sector = (payload.get("sub_sector") or "Unclassified").strip() or "Unclassified"
    currency = _normalize_currency(payload.get("currency"))
    quantity = float(payload.get("quantity", 0.0))
    if quantity < 0:
        raise ValueError("quantity must be >= 0")

    row = upsert_holding(
        {
            "ticker": ticker,
            "asset_name": asset_name,
            "quantity": quantity,
            "portfolio_bucket": bucket,
            "sector": sector,
            "sub_sector": sub_sector,
            "currency": currency,
            "is_active": True,
        }
    )
    return row
