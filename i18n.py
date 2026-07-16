"""Minimal EN/DE localisation for the dashboard."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "app_title": {
        "EN": "Rotshild Quant Dashboard",
        "DE": "Rotshild Quant-Dashboard",
    },
    "app_subtitle": {
        "EN": "Private Banking · Portfolio Analytics",
        "DE": "Private Banking · Portfolio-Analytik",
    },
    "config": {"EN": "Configuration", "DE": "Konfiguration"},
    "language": {"EN": "Language", "DE": "Sprache"},
    "tickers": {"EN": "Ticker Symbols", "DE": "Tickersymbole"},
    "tickers_help": {
        "EN": "Comma-separated, e.g. AAPL, MSFT, TLT, GLD",
        "DE": "Kommagetrennt, z. B. AAPL, MSFT, TLT, GLD",
    },
    "benchmark": {"EN": "Benchmark", "DE": "Benchmark"},
    "risk_free": {"EN": "Risk-free rate (annual)", "DE": "Risikofreier Zins (p.a.)"},
    "lookback": {"EN": "Look-back (trading days)", "DE": "Rückschau (Handelstage)"},
    "use_live": {"EN": "Use live market data", "DE": "Live-Marktdaten verwenden"},
    "nav": {"EN": "Navigation", "DE": "Navigation"},
    "market_overview": {"EN": "Market Overview", "DE": "Marktübersicht"},
    "quant_risk": {"EN": "Quant Risk & CAPM", "DE": "Quant-Risiko & CAPM"},
    "rebalancing": {"EN": "Rebalancing Engine", "DE": "Rebalancing-Engine"},
    "export": {"EN": "Avaloq/VBA Export", "DE": "Avaloq/VBA-Export"},
    "cagr": {"EN": "CAGR", "DE": "CAGR"},
    "max_drawdown": {"EN": "Max Drawdown", "DE": "Max. Drawdown"},
    "sharpe": {"EN": "Sharpe Ratio", "DE": "Sharpe-Ratio"},
    "sortino": {"EN": "Sortino Ratio", "DE": "Sortino-Ratio"},
    "vs_benchmark": {"EN": "vs benchmark", "DE": "ggü. Benchmark"},
    "portfolio": {"EN": "Portfolio", "DE": "Portfolio"},
    "cumulative_perf": {
        "EN": "Cumulative Performance (rebased to 100)",
        "DE": "Kumulative Wertentwicklung (indexiert auf 100)",
    },
    "select_asset": {"EN": "Instrument for CAPM analysis", "DE": "Instrument für CAPM-Analyse"},
    "rolling_beta": {"EN": "Rolling 63-Day Beta", "DE": "Rollierendes 63-Tage-Beta"},
    "annualized_alpha": {"EN": "Annualized Alpha", "DE": "Annualisiertes Alpha"},
    "current_beta": {"EN": "Current Beta", "DE": "Aktuelles Beta"},
    "current_alpha": {"EN": "Current Alpha (ann.)", "DE": "Aktuelles Alpha (p.a.)"},
    "allocation": {"EN": "Asset Allocation", "DE": "Vermögensallokation"},
    "portfolio_value": {"EN": "Portfolio value (CHF)", "DE": "Portfoliowert (CHF)"},
    "weights_editor": {
        "EN": "Current vs Target Weights (edit target %)",
        "DE": "Aktuelle vs. Zielgewichte (Ziel-% bearbeiten)",
    },
    "calculate_trades": {"EN": "Calculate Optimal Trades", "DE": "Optimale Trades berechnen"},
    "proposed_trades": {"EN": "Proposed Trades", "DE": "Vorgeschlagene Trades"},
    "buy": {"EN": "BUY", "DE": "KAUF"},
    "sell": {"EN": "SELL", "DE": "VERKAUF"},
    "hold": {"EN": "HOLD", "DE": "HALTEN"},
    "export_intro": {
        "EN": "Export the proposed trades for downstream systems.",
        "DE": "Exportieren Sie die vorgeschlagenen Trades für nachgelagerte Systeme.",
    },
    "download_csv": {"EN": "Download CSV (Avaloq)", "DE": "CSV herunterladen (Avaloq)"},
    "copy_vba": {"EN": "VBA array (paste into Excel macro)", "DE": "VBA-Array (in Excel-Makro einfügen)"},
    "synthetic_banner": {
        "EN": "Live market data unavailable in this environment — showing "
              "reproducible **synthetic** data with a realistic CAPM structure.",
        "DE": "Live-Marktdaten in dieser Umgebung nicht verfügbar — es werden "
              "reproduzierbare **synthetische** Daten mit realistischer "
              "CAPM-Struktur angezeigt.",
    },
    "live_banner": {
        "EN": "Live market data — Yahoo Finance.",
        "DE": "Live-Marktdaten — Yahoo Finance.",
    },
    "data_source": {"EN": "Data source", "DE": "Datenquelle"},
    "period_covered": {"EN": "Period", "DE": "Zeitraum"},
    "run_rebalance_first": {
        "EN": "Run the Rebalancing Engine and calculate trades first.",
        "DE": "Führen Sie zuerst die Rebalancing-Engine aus und berechnen Sie die Trades.",
    },
}


def tr(key: str, lang: str) -> str:
    """Translate ``key`` into ``lang`` (EN/DE), falling back to the key itself."""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("EN", key))
