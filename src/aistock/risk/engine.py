from __future__ import annotations

from aistock.common.types import RiskDecision, RiskResult, TradeSignal
from aistock.config.settings import FileConfig


def evaluate_signal(signal: TradeSignal, file_config: FileConfig, daily_trade_count: int) -> RiskResult:
    if daily_trade_count >= file_config.risk.max_daily_trades:
        return RiskResult(
            symbol=signal.symbol,
            decision=RiskDecision.REJECT,
            adjusted_weight=0.0,
            message="max daily trade limit reached",
        )

    if signal.target_weight > file_config.risk.max_single_position_pct:
        return RiskResult(
            symbol=signal.symbol,
            decision=RiskDecision.ADJUST,
            adjusted_weight=file_config.risk.max_single_position_pct,
            message="weight capped by single-position limit",
        )

    return RiskResult(
        symbol=signal.symbol,
        decision=RiskDecision.ALLOW,
        adjusted_weight=signal.target_weight,
        message="approved",
    )
