from __future__ import annotations

from aistock.common.types import Prediction, SignalAction, TradeSignal
from aistock.config.settings import FileConfig


def generate_signals(predictions: list[Prediction], file_config: FileConfig) -> list[TradeSignal]:
    ranked = sorted(predictions, key=lambda item: item.score, reverse=True)
    chosen = ranked[: file_config.strategy.top_n]

    signals: list[TradeSignal] = []
    for item in chosen:
        action = SignalAction.BUY if item.confidence >= file_config.risk.min_confidence_score else SignalAction.HOLD
        target_weight = min(file_config.risk.max_single_position_pct, item.confidence / 10)
        signals.append(
            TradeSignal(
                symbol=item.symbol,
                action=action,
                target_weight=target_weight,
                reason=f"score={item.score:.3f}, confidence={item.confidence:.3f}",
            )
        )
    return signals
