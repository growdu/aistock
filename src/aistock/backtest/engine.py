from __future__ import annotations

import pandas as pd


def run_backtest(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"total_return": 0.0, "max_drawdown": 0.0}

    total_return = float(df["return_1"].fillna(0.0).sum()) if "return_1" in df.columns else 0.0
    return {"total_return": total_return, "max_drawdown": 0.0}
