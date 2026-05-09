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
