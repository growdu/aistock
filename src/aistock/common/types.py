from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class RiskDecision(str, Enum):
    ALLOW = "ALLOW"
    ADJUST = "ADJUST"
    REJECT = "REJECT"


@dataclass(slots=True)
class Prediction:
    symbol: str
    score: float
    predicted_return: float
    confidence: float


@dataclass(slots=True)
class TradeSignal:
    symbol: str
    action: SignalAction
    target_weight: float
    predicted_return: float
    confidence: float  # 0.0–1.0, 用于 position sizing
    reason: str


@dataclass(slots=True)
class RiskResult:
    symbol: str
    decision: RiskDecision
    adjusted_weight: float
    message: str
