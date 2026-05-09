from __future__ import annotations

import pandas as pd


def build_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if "close" in frame.columns:
        frame["return_1"] = frame["close"].pct_change().fillna(0.0)
        frame["ma_5"] = frame["close"].rolling(5, min_periods=1).mean()
        frame["close_vs_ma_5"] = frame["close"] / frame["ma_5"] - 1.0
    return frame
