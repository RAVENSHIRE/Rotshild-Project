"""Two-pillar portfolio model.

The investment approach is bottom-up and blends exactly two pillars:
  - RETURN assets       -> produce long-term capital growth
  - DIVERSIFYING assets -> provide protection and diversification
"""

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


class Pillar(str, Enum):
    RETURN = "return"
    DIVERSIFYING = "diversifying"


@dataclass(frozen=True)
class Asset:
    ticker: str
    name: str
    pillar: Pillar
    weight: float  # fraction of total portfolio, 0..1


@dataclass
class Portfolio:
    assets: list[Asset] = field(default_factory=list)

    @property
    def tickers(self) -> list[str]:
        return [a.ticker for a in self.assets]

    def weights(self) -> dict[str, float]:
        return {a.ticker: a.weight for a in self.assets}

    def pillar_weight(self, pillar: Pillar) -> float:
        return sum(a.weight for a in self.assets if a.pillar == pillar)

    def by_pillar(self, pillar: Pillar) -> list[Asset]:
        return [a for a in self.assets if a.pillar == pillar]

    def validate(self) -> None:
        total = sum(a.weight for a in self.assets)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Portfolio weights sum to {total:.4f}, expected 1.0")


def drifted_weights(portfolio: Portfolio, prices: pd.DataFrame) -> dict[str, float]:
    """Current weights after price drift, assuming target weights at period start."""
    rel = prices.iloc[-1] / prices.iloc[0]
    raw = {a.ticker: a.weight * float(rel[a.ticker]) for a in portfolio.assets}
    total = sum(raw.values())
    return {t: w / total for t, w in raw.items()}


def rebalancing_trades(portfolio: Portfolio, prices: pd.DataFrame) -> pd.DataFrame:
    """Current vs target weights and the trade (in weight terms) to rebalance."""
    current = drifted_weights(portfolio, prices)
    rows = [
        {
            "Ticker": a.ticker,
            "Name": a.name,
            "Pillar": a.pillar.value,
            "Current Weight": current[a.ticker],
            "Target Weight": a.weight,
            "Trade": a.weight - current[a.ticker],
        }
        for a in portfolio.assets
    ]
    return pd.DataFrame(rows)


def demo_portfolio() -> Portfolio:
    """Illustrative starter portfolio; replace with real holdings."""
    return Portfolio(
        assets=[
            Asset("VTI", "US Total Market", Pillar.RETURN, 0.40),
            Asset("VXUS", "Intl ex-US Equity", Pillar.RETURN, 0.20),
            Asset("BND", "US Aggregate Bonds", Pillar.DIVERSIFYING, 0.25),
            Asset("GLD", "Gold", Pillar.DIVERSIFYING, 0.10),
            Asset("BIL", "T-Bills (Cash)", Pillar.DIVERSIFYING, 0.05),
        ]
    )
