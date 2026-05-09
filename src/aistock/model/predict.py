from __future__ import annotations

from typing import Iterable

from aistock.common.types import Prediction


def score_candidates(symbols: Iterable[str]) -> list[Prediction]:
    results: list[Prediction] = []
    for idx, symbol in enumerate(symbols, start=1):
        score = max(0.0, 1.0 - idx * 0.05)
        results.append(
            Prediction(
                symbol=symbol,
                score=score,
                predicted_return=score * 0.03,
                confidence=score,
            )
        )
    return results
