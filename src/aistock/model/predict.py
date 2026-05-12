from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

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


def load_model_metadata(metadata_path: str | Path) -> dict:
    path = Path(metadata_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_scores(raw_scores) -> list[float]:
    if len(raw_scores) == 0:
        return []

    min_score = float(min(raw_scores))
    max_score = float(max(raw_scores))
    denominator = max(max_score - min_score, 1e-9)
    return [float((value - min_score) / denominator) for value in raw_scores]


def predict_feature_frame(
    feature_df: pd.DataFrame,
    model_path: str | Path,
    metadata_path: str | Path,
) -> pd.DataFrame:
    import lightgbm as lgb  # deferred import: only load when actually predicting

    if feature_df.empty:
        return feature_df.copy()

    metadata = load_model_metadata(metadata_path)
    feature_columns: list[str] = metadata["feature_columns"]
    booster = lgb.Booster(model_file=str(model_path))

    scoring_frame = feature_df.copy()
    raw_scores = booster.predict(scoring_frame[feature_columns].copy())
    normalized_scores = _normalize_scores(raw_scores)

    scoring_frame["predicted_return"] = raw_scores
    scoring_frame["score"] = normalized_scores
    scoring_frame["confidence"] = [
        min(1.0, max(0.0, 0.5 + score / 2)) for score in normalized_scores
    ]
    return scoring_frame


def predict_from_model(
    feature_df: pd.DataFrame,
    model_path: str | Path,
    metadata_path: str | Path,
    symbol_column: str = "ts_code",
) -> list[Prediction]:
    if feature_df.empty:
        return []

    latest_df = (
        feature_df.sort_values([symbol_column, "trade_date"])
        .groupby(symbol_column, as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    scored_df = predict_feature_frame(latest_df, model_path=model_path, metadata_path=metadata_path)

    predictions: list[Prediction] = []
    for _, row in scored_df.iterrows():
        predictions.append(
            Prediction(
                symbol=str(row[symbol_column]),
                score=float(row["score"]),
                predicted_return=float(row["predicted_return"]),
                confidence=float(row["confidence"]),
            )
        )

    return predictions
