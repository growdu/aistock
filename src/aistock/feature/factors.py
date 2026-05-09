from __future__ import annotations

import pandas as pd


def build_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if "close" in frame.columns:
        frame["return_1"] = frame["close"].pct_change().fillna(0.0)
        frame["ma_5"] = frame["close"].rolling(5, min_periods=1).mean()
        frame["close_vs_ma_5"] = frame["close"] / frame["ma_5"] - 1.0
    return frame


def build_daily_features(market_df: pd.DataFrame, daily_basic_df: pd.DataFrame) -> pd.DataFrame:
    if market_df.empty:
        return pd.DataFrame()

    frame = market_df.copy()
    frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    grouped = frame.groupby("ts_code", group_keys=False)
    frame["return_1"] = grouped["close"].pct_change().fillna(0.0)
    frame["ma_5"] = grouped["close"].transform(lambda col: col.rolling(5, min_periods=1).mean())
    frame["ma_10"] = grouped["close"].transform(lambda col: col.rolling(10, min_periods=1).mean())
    frame["close_vs_ma_5"] = frame["close"] / frame["ma_5"] - 1.0
    frame["close_vs_ma_10"] = frame["close"] / frame["ma_10"] - 1.0
    frame["volume_ratio_5"] = frame["volume"] / grouped["volume"].transform(lambda col: col.rolling(5, min_periods=1).mean())
    frame["volatility_5"] = grouped["return_1"].transform(lambda col: col.rolling(5, min_periods=1).std()).fillna(0.0)
    frame["target_return_1d"] = grouped["close"].shift(-1) / frame["close"] - 1.0
    frame["target_up_1d"] = (frame["target_return_1d"] > 0).astype("int64")

    if not daily_basic_df.empty:
        basics = daily_basic_df.copy()
        frame = frame.merge(
            basics[["ts_code", "trade_date", "pe", "pb", "ps_ttm", "dv_ratio", "total_mv", "circ_mv"]],
            on=["ts_code", "trade_date"],
            how="left",
        )

    return frame
