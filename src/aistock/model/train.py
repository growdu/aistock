from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import pandas as pd


@dataclass(slots=True)
class TrainResult:
    model_path: str
    feature_count: int


def train_lightgbm(
    features: pd.DataFrame,
    target_column: str,
    model_path: str,
) -> TrainResult:
    feature_frame = features.drop(columns=[target_column])
    target = features[target_column]
    model = lgb.LGBMRegressor(n_estimators=100, learning_rate=0.05, random_state=7)
    model.fit(feature_frame, target)
    model.booster_.save_model(model_path)
    return TrainResult(model_path=model_path, feature_count=feature_frame.shape[1])
