from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd


@dataclass(slots=True)
class TrainResult:
    model_path: str
    metadata_path: str
    feature_count: int
    row_count: int


def train_lightgbm(
    features: pd.DataFrame,
    target_column: str,
    model_path: str,
) -> TrainResult:
    frame = features.copy()
    if target_column not in frame.columns:
        raise ValueError(f"target column '{target_column}' not found; run build-features with the latest code")
    frame = frame.dropna(subset=[target_column])
    frame = frame.select_dtypes(include=["number", "bool"]).copy()
    feature_frame = frame.drop(columns=[target_column])
    if feature_frame.empty:
        raise ValueError("no numeric feature columns available for training")

    target = features[target_column]
    target = frame[target_column]
    model = lgb.LGBMRegressor(
        n_estimators=100,
        learning_rate=0.05,
        random_state=7,
        n_jobs=1,
        verbosity=-1,
    )
    model.fit(feature_frame, target)
    output_path = Path(model_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(output_path))
    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "target_column": target_column,
                "feature_columns": feature_frame.columns.tolist(),
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return TrainResult(
        model_path=str(output_path),
        metadata_path=str(metadata_path),
        feature_count=feature_frame.shape[1],
        row_count=len(frame),
    )
