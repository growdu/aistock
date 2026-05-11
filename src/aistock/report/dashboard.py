from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_signal_report(signals: list[dict], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(signals).to_csv(path, index=False)


def write_backtest_curve(curve: pd.DataFrame, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    curve.to_csv(path, index=False)


def write_trade_log(orders: list[dict], output_path: str) -> None:
    """将交易记录写入 CSV，供 dashboard 读取。"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if orders:
        pd.DataFrame(orders).to_csv(path, index=False)
    else:
        # Write empty file with headers so downstream consumers don't crash
        pd.DataFrame(columns=["order_id", "symbol", "side", "filled_price",
                              "filled_weight", "filled_notional",
                              "transaction_cost", "total_cost",
                              "submitted_at"]).to_csv(path, index=False)
