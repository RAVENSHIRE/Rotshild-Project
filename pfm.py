"""Avaloq-style Portfolio Management (PFM) layer — a conceptual clone.

Mirrors the Avaloq Core Platform PFM object model and business logic without
any proprietary code:

* **Business Partner (BP)** — Retail / Private / Institutional clients.
* **Container (Portfolio)** — the account holding positions, tagged with a
  service type: *Discretionary* (bank decides) or *Advisory* (client decides).
* **Positions & Instruments** — holdings valued in CHF; instrument metadata
  (asset class, dual mandate) comes from the data layer.
* **Target Models** — strategy templates (e.g. Balanced 60/40) at asset-class
  level.
* **Restriction Engine** — pre-trade / post-trade compliance checks returning
  PASS / WARNING / BREACH verdicts per rule.
* **Rebalancing Engine** — computes the buy/sell orders that move a container
  back to its target model, then re-runs the restriction engine on the
  simulated post-trade book.

Pure Python + dataclasses; no I/O. Deliberately importable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data import asset_class, mandate

CASH = "CASH"


def _class_of(instrument: str) -> str:
    return "Cash" if instrument.upper() == CASH else asset_class(instrument)


def _mandate_of(instrument: str) -> str:
    return "Diversifying Assets" if instrument.upper() == CASH else mandate(instrument)


# --------------------------------------------------------------------------- #
# Object model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BusinessPartner:
    bp_id: str
    name: str
    segment: str          # Retail | Private | Institutional
    domicile: str


@dataclass(frozen=True)
class Position:
    instrument: str
    market_value: float   # CHF


@dataclass(frozen=True)
class TargetModel:
    model_id: str
    name: str
    targets: dict[str, float]   # asset class -> weight fraction, sums to 1


@dataclass
class Portfolio:
    portfolio_id: str
    bp_id: str
    name: str
    service_type: str     # Discretionary | Advisory
    currency: str
    model_id: str
    positions: list[Position] = field(default_factory=list)

    @property
    def value(self) -> float:
        return sum(p.market_value for p in self.positions)

    def weights(self) -> dict[str, float]:
        total = self.value
        if total <= 0:
            return {}
        return {p.instrument: p.market_value / total for p in self.positions}

    def class_weights(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for instrument, w in self.weights().items():
            cls = _class_of(instrument)
            out[cls] = out.get(cls, 0.0) + w
        return out


# --------------------------------------------------------------------------- #
# Restriction engine
# --------------------------------------------------------------------------- #
PASS, WARNING, BREACH = "PASS", "WARNING", "BREACH"

# Instruments a Retail client may not hold (complexity / suitability rules).
RETAIL_BLOCKED: set[str] = {"BTC-USD", "SLV", "DBC"}

# Asset-class ceilings per target model (the "max 15% in X"-style rules).
CLASS_CEILINGS: dict[str, dict[str, float]] = {
    "MDL-CONS": {"Equities": 0.30, "Alternatives": 0.10},
    "MDL-BAL":  {"Equities": 0.70, "Alternatives": 0.15},
    "MDL-GRW":  {"Equities": 0.90, "Alternatives": 0.20},
    "MDL-INC":  {"Equities": 0.40, "Alternatives": 0.10},
}

MIN_CASH_DISCRETIONARY = 0.02   # discretionary mandates keep >= 2% cash
MAX_SINGLE_POSITION = 0.25      # any single-name line <= 25% (warn from 20%)
WARN_SINGLE_POSITION = 0.20

# Collective instruments (broad funds/ETFs) are internally diversified and
# therefore exempt from the single-position concentration rule.
COLLECTIVES: set[str] = {
    "SPY", "AGG", "BND", "IEF", "LQD", "TLT", "GLD", "SLV", "DBC", "VNQ",
}


@dataclass(frozen=True)
class RestrictionResult:
    rule_id: str
    description: str
    status: str           # PASS | WARNING | BREACH
    measured: str         # human-readable measured value
    limit: str            # human-readable limit
    detail: str = ""


def _weights_after(portfolio: Portfolio, orders: list[dict] | None) -> dict[str, float]:
    """Instrument weights after applying ``orders`` (CHF amounts, signed)."""
    values = {p.instrument: p.market_value for p in portfolio.positions}
    for order in orders or []:
        instrument = order["instrument"].upper()
        values[instrument] = values.get(instrument, 0.0) + order["amount"]
    values = {k: v for k, v in values.items() if v > 1e-6}
    total = sum(values.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in values.items()}


def check_restrictions(
    bp: BusinessPartner,
    portfolio: Portfolio,
    orders: list[dict] | None = None,
) -> list[RestrictionResult]:
    """Run every applicable restriction against the (simulated) book.

    With ``orders`` this is a pre-trade check on the post-trade book; without,
    it audits current holdings.
    """
    weights = _weights_after(portfolio, orders)
    results: list[RestrictionResult] = []

    # Rule 1 — asset-class ceilings from the assigned target model.
    ceilings = CLASS_CEILINGS.get(portfolio.model_id, {})
    class_w: dict[str, float] = {}
    for instrument, w in weights.items():
        cls = _class_of(instrument)
        class_w[cls] = class_w.get(cls, 0.0) + w
    for cls, ceiling in ceilings.items():
        measured = class_w.get(cls, 0.0)
        if measured > ceiling + 1e-9:
            status = BREACH
        elif measured > ceiling * 0.9:
            status = WARNING
        else:
            status = PASS
        results.append(RestrictionResult(
            rule_id=f"CLS-{cls[:3].upper()}",
            description=f"Max {cls} exposure",
            status=status,
            measured=f"{measured * 100:.1f}%",
            limit=f"≤ {ceiling * 100:.0f}%",
            detail=f"{cls} allocation vs the {portfolio.model_id} ceiling.",
        ))

    # Rule 2 — instruments blocked for Retail clients.
    if bp.segment == "Retail":
        held_blocked = sorted(i for i in weights if i.upper() in RETAIL_BLOCKED)
        results.append(RestrictionResult(
            rule_id="SUIT-RET",
            description="Retail suitability (blocked instruments)",
            status=BREACH if held_blocked else PASS,
            measured=", ".join(held_blocked) or "none held",
            limit=f"blocked: {', '.join(sorted(RETAIL_BLOCKED))}",
            detail="Complex instruments are not permitted for Retail clients.",
        ))

    # Rule 3 — minimum cash buffer on discretionary mandates.
    if portfolio.service_type == "Discretionary":
        cash = weights.get(CASH, 0.0)
        if cash < MIN_CASH_DISCRETIONARY - 1e-9:
            status = BREACH if cash < MIN_CASH_DISCRETIONARY / 2 else WARNING
        else:
            status = PASS
        results.append(RestrictionResult(
            rule_id="LIQ-CASH",
            description="Minimum cash buffer (discretionary)",
            status=status,
            measured=f"{cash * 100:.1f}%",
            limit=f"≥ {MIN_CASH_DISCRETIONARY * 100:.0f}%",
            detail="Discretionary mandates keep a liquidity buffer for fees and redemptions.",
        ))

    # Rule 4 — single-position concentration (single-name lines only).
    worst_instrument, worst_w = None, 0.0
    for instrument, w in weights.items():
        if instrument.upper() in {CASH, *COLLECTIVES}:
            continue
        if w > worst_w:
            worst_instrument, worst_w = instrument, w
    if worst_w > MAX_SINGLE_POSITION + 1e-9:
        status = BREACH
    elif worst_w > WARN_SINGLE_POSITION:
        status = WARNING
    else:
        status = PASS
    results.append(RestrictionResult(
        rule_id="CON-POS",
        description="Single-position concentration",
        status=status,
        measured=f"{worst_instrument or '—'} {worst_w * 100:.1f}%",
        limit=f"≤ {MAX_SINGLE_POSITION * 100:.0f}%",
        detail=f"Warning above {WARN_SINGLE_POSITION * 100:.0f}%.",
    ))

    return results


def worst_status(results: list[RestrictionResult]) -> str:
    if any(r.status == BREACH for r in results):
        return BREACH
    if any(r.status == WARNING for r in results):
        return WARNING
    return PASS


# --------------------------------------------------------------------------- #
# Rebalancing engine
# --------------------------------------------------------------------------- #
def rebalance_to_model(
    portfolio: Portfolio, model: TargetModel
) -> list[dict]:
    """Orders (CHF, signed) that move the container back to its target model.

    The model is defined at asset-class level; within a class the target is
    distributed pro-rata across the instruments already held (bottom-up: the
    security selection is preserved, only sizing changes). A class in the
    model with no held instrument accrues to cash.
    """
    total = portfolio.value
    if total <= 0:
        return []

    weights = portfolio.weights()
    by_class: dict[str, dict[str, float]] = {}
    for instrument, w in weights.items():
        by_class.setdefault(_class_of(instrument), {})[instrument] = w

    orders: list[dict] = []
    unallocated = 0.0
    for cls, target_cls_w in model.targets.items():
        held = by_class.get(cls, {})
        cls_total = sum(held.values())
        if not held:
            unallocated += target_cls_w
            continue
        for instrument, w in held.items():
            share = w / cls_total if cls_total > 0 else 1.0 / len(held)
            target_w = target_cls_w * share
            delta = (target_w - w) * total
            if abs(delta) > 1.0:
                orders.append({
                    "instrument": instrument,
                    "asset_class": cls,
                    "mandate": _mandate_of(instrument),
                    "side": "BUY" if delta > 0 else "SELL",
                    "amount": round(delta, 2),
                })

    # Classes not in the model at all → sell down to zero.
    for cls, held in by_class.items():
        if cls in model.targets:
            continue
        for instrument, w in held.items():
            delta = -w * total
            if abs(delta) > 1.0:
                orders.append({
                    "instrument": instrument,
                    "asset_class": cls,
                    "mandate": _mandate_of(instrument),
                    "side": "SELL",
                    "amount": round(delta, 2),
                })

    # Any target weight that had no holdable instrument lands in cash, so the
    # order list stays self-financing (net ≈ 0 including the cash leg).
    net = sum(o["amount"] for o in orders)
    if abs(net) > 1.0 or unallocated > 0:
        cash_delta = round(-net, 2)
        if abs(cash_delta) > 1.0:
            orders.append({
                "instrument": CASH,
                "asset_class": "Cash",
                "mandate": "Diversifying Assets",
                "side": "BUY" if cash_delta > 0 else "SELL",
                "amount": cash_delta,
            })
    return orders


# --------------------------------------------------------------------------- #
# Seeded book — the demo "bank"
# --------------------------------------------------------------------------- #
TARGET_MODELS: dict[str, TargetModel] = {
    "MDL-CONS": TargetModel("MDL-CONS", "Conservative 30/60",
                            {"Equities": 0.30, "Fixed Income": 0.60, "Alternatives": 0.05, "Cash": 0.05}),
    "MDL-BAL":  TargetModel("MDL-BAL", "Balanced 60/40",
                            {"Equities": 0.60, "Fixed Income": 0.30, "Alternatives": 0.06, "Cash": 0.04}),
    "MDL-GRW":  TargetModel("MDL-GRW", "Growth 80/20",
                            {"Equities": 0.80, "Fixed Income": 0.12, "Alternatives": 0.05, "Cash": 0.03}),
    "MDL-INC":  TargetModel("MDL-INC", "Income 30/65",
                            {"Equities": 0.30, "Fixed Income": 0.65, "Cash": 0.05}),
}

BUSINESS_PARTNERS: dict[str, BusinessPartner] = {
    "BP-1001": BusinessPartner("BP-1001", "Familie Berger", "Private", "CH"),
    "BP-1002": BusinessPartner("BP-1002", "Helvetia Pension Trust", "Institutional", "CH"),
    "BP-1003": BusinessPartner("BP-1003", "M. Rossi", "Retail", "IT"),
    "BP-1004": BusinessPartner("BP-1004", "A. Keller", "Private", "CH"),
    "BP-1005": BusinessPartner("BP-1005", "Stiftung Aurora", "Institutional", "DE"),
    "BP-1006": BusinessPartner("BP-1006", "J. Müller", "Retail", "CH"),
}

PORTFOLIOS: dict[str, Portfolio] = {
    # Balanced discretionary book that has drifted equity-heavy.
    "PF-2001": Portfolio("PF-2001", "BP-1001", "Berger Family Mandate", "Discretionary", "CHF", "MDL-BAL", [
        Position("AAPL", 2_300_000), Position("MSFT", 2_500_000), Position("NESN.SW", 1_900_000),
        Position("NVDA", 1_800_000), Position("TLT", 1_700_000), Position("AGG", 1_200_000),
        Position("GLD", 600_000), Position(CASH, 400_000),
    ]),
    # Income mandate, close to model.
    "PF-2002": Portfolio("PF-2002", "BP-1002", "Helvetia Fixed Income Core", "Discretionary", "CHF", "MDL-INC", [
        Position("SPY", 24_000_000), Position("AGG", 28_000_000), Position("LQD", 18_000_000),
        Position("IEF", 10_000_000), Position(CASH, 6_000_000),
    ]),
    # Retail advisory holding a blocked instrument → suitability breach.
    "PF-2003": Portfolio("PF-2003", "BP-1003", "Rossi Growth Deposit", "Advisory", "CHF", "MDL-GRW", [
        Position("NVDA", 150_000), Position("AAPL", 90_000), Position("SLV", 60_000),
        Position("IEF", 60_000), Position(CASH, 40_000),
    ]),
    # Private advisory, concentrated single line → concentration warning/breach.
    "PF-2004": Portfolio("PF-2004", "BP-1004", "Keller Opportunity", "Advisory", "CHF", "MDL-GRW", [
        Position("NVDA", 1_050_000), Position("MSFT", 700_000), Position("GOOGL", 650_000),
        Position("TLT", 500_000), Position(CASH, 300_000),
    ]),
    # Conservative foundation, equity ceiling under pressure (warning zone).
    "PF-2005": Portfolio("PF-2005", "BP-1005", "Aurora Endowment", "Discretionary", "CHF", "MDL-CONS", [
        Position("NESN.SW", 3_900_000), Position("ROG.SW", 2_800_000), Position("AGG", 8_200_000),
        Position("TLT", 4_800_000), Position("GLD", 1_400_000), Position(CASH, 1_600_000),
    ]),
    # Retail discretionary with a thin cash buffer → liquidity warning.
    "PF-2006": Portfolio("PF-2006", "BP-1006", "Müller Savings Mandate", "Discretionary", "CHF", "MDL-BAL", [
        Position("SPY", 520_000), Position("AGG", 310_000), Position("GLD", 62_000),
        Position(CASH, 12_000),
    ]),
}


# --------------------------------------------------------------------------- #
# Serialisation for the API layer
# --------------------------------------------------------------------------- #
def _portfolio_summary(pf: Portfolio) -> dict:
    bp = BUSINESS_PARTNERS[pf.bp_id]
    model = TARGET_MODELS[pf.model_id]
    results = check_restrictions(bp, pf)
    class_w = pf.class_weights()
    max_drift = max(
        (abs(class_w.get(cls, 0.0) - w) for cls, w in model.targets.items()),
        default=0.0,
    )
    return {
        "bp_id": bp.bp_id, "client": bp.name, "segment": bp.segment, "domicile": bp.domicile,
        "portfolio_id": pf.portfolio_id, "portfolio": pf.name,
        "service_type": pf.service_type, "model": model.name, "model_id": model.model_id,
        "aum": pf.value, "max_drift": max_drift * 100,
        "compliance": worst_status(results),
        "breaches": sum(1 for r in results if r.status == BREACH),
        "warnings": sum(1 for r in results if r.status == WARNING),
    }


def desk_overview() -> dict:
    """Aggregated PFM-desk view across every Business Partner."""
    clients = [_portfolio_summary(pf) for pf in PORTFOLIOS.values()]
    total_aum = sum(c["aum"] for c in clients)
    discretionary = sum(c["aum"] for c in clients if c["service_type"] == "Discretionary")
    return {
        "clients": clients,
        "totals": {
            "aum": total_aum,
            "clients": len(clients),
            "discretionary_share": (discretionary / total_aum * 100) if total_aum else 0.0,
            "breaches": sum(c["breaches"] for c in clients),
            "warnings": sum(c["warnings"] for c in clients),
        },
    }


def portfolio_detail(portfolio_id: str) -> dict:
    pf = PORTFOLIOS.get(portfolio_id)
    if pf is None:
        raise KeyError(f"Unknown portfolio {portfolio_id}")
    bp = BUSINESS_PARTNERS[pf.bp_id]
    model = TARGET_MODELS[pf.model_id]
    weights = pf.weights()
    class_w = pf.class_weights()
    classes = sorted(set(class_w) | set(model.targets))
    return {
        **_portfolio_summary(pf),
        "positions": [
            {
                "instrument": p.instrument,
                "asset_class": _class_of(p.instrument),
                "mandate": _mandate_of(p.instrument),
                "value": p.market_value,
                "weight": weights.get(p.instrument, 0.0) * 100,
            }
            for p in sorted(pf.positions, key=lambda p: -p.market_value)
        ],
        "classes": [
            {
                "asset_class": cls,
                "current": class_w.get(cls, 0.0) * 100,
                "target": model.targets.get(cls, 0.0) * 100,
                "drift": (class_w.get(cls, 0.0) - model.targets.get(cls, 0.0)) * 100,
            }
            for cls in classes
        ],
        "restrictions": [r.__dict__ for r in check_restrictions(bp, pf)],
    }


def rebalance_portfolio(portfolio_id: str) -> dict:
    """Model rebalancing proposal + pre-trade compliance on the simulated book."""
    pf = PORTFOLIOS.get(portfolio_id)
    if pf is None:
        raise KeyError(f"Unknown portfolio {portfolio_id}")
    bp = BUSINESS_PARTNERS[pf.bp_id]
    model = TARGET_MODELS[pf.model_id]
    orders = rebalance_to_model(pf, model)
    post = check_restrictions(bp, pf, orders)
    after = _weights_after(pf, orders)
    class_after: dict[str, float] = {}
    for instrument, w in after.items():
        cls = _class_of(instrument)
        class_after[cls] = class_after.get(cls, 0.0) + w
    return {
        "portfolio_id": pf.portfolio_id,
        "model": model.name,
        "orders": orders,
        "pre_trade_check": [r.__dict__ for r in post],
        "verdict": worst_status(post),
        "classes_after": [
            {
                "asset_class": cls,
                "after": class_after.get(cls, 0.0) * 100,
                "target": model.targets.get(cls, 0.0) * 100,
            }
            for cls in sorted(set(class_after) | set(model.targets))
        ],
    }
