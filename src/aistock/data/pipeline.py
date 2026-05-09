from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import text

from aistock.config.settings import FileConfig, RuntimeSettings
from aistock.data.sources.tushare_client import TushareClient
from aistock.db.base import build_engine

logger = logging.getLogger(__name__)


def ensure_data_dirs(file_config: FileConfig) -> list[Path]:
    root = Path(file_config.app.data_dir)
    created_paths: list[Path] = []
    for name in ("raw", "clean", "features", "models", "reports", "backups"):
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        created_paths.append(path)
    return created_paths


def ensure_runtime_dirs(file_config: FileConfig) -> dict[str, list[Path] | Path]:
    data_paths = ensure_data_dirs(file_config)
    logs_path = Path(file_config.app.logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)
    return {"data_paths": data_paths, "logs_path": logs_path}


def _write_parquet(df: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)


def _refresh_table(database_url: str, table_name: str, df: pd.DataFrame) -> None:
    frame = df.copy()
    if not frame.empty and "updated_at" not in frame.columns:
        frame["updated_at"] = datetime.utcnow()

    engine = build_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM {table_name}"))
        if not frame.empty:
            frame.to_sql(table_name, connection, if_exists="append", index=False)


def _infer_security_row(ts_code: str) -> dict[str, str]:
    symbol, exchange = ts_code.split(".")
    if symbol.startswith("688"):
        board = "STAR"
    elif symbol.startswith("300"):
        board = "GEM"
    else:
        board = "UNKNOWN"
    return {
        "ts_code": ts_code,
        "symbol": symbol,
        "exchange": exchange,
        "board": board,
        "name": "",
    }


def _build_stub_data(symbols: Iterable[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    trade_dates = pd.date_range(start=pd.to_datetime(start_date), end=pd.to_datetime(end_date), freq="B")
    date_labels = [item.strftime("%Y%m%d") for item in trade_dates]

    calendar_df = pd.DataFrame(
        [
            {"exchange": "SSE", "cal_date": label, "is_open": "1", "pretrade_date": ""}
            for label in date_labels
        ]
    )

    security_rows = [_infer_security_row(ts_code) for ts_code in symbols]
    security_df = pd.DataFrame(security_rows)

    daily_rows: list[dict[str, float | str]] = []
    daily_basic_rows: list[dict[str, float | str]] = []
    for symbol_index, ts_code in enumerate(symbols, start=1):
        base_price = 100.0 + symbol_index * 10
        for idx, trade_date in enumerate(date_labels, start=1):
            close = base_price + idx * 0.8
            daily_rows.append(
                {
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "open": close - 0.5,
                    "high": close + 0.8,
                    "low": close - 1.0,
                    "close": close,
                    "volume": float(100000 + idx * 1000),
                    "amount": float((100000 + idx * 1000) * close / 100),
                    "source": "stub",
                }
            )
            daily_basic_rows.append(
                {
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "pe": 20.0 + symbol_index,
                    "pb": 3.0 + symbol_index * 0.1,
                    "ps_ttm": 5.0 + idx * 0.01,
                    "dv_ratio": 0.5,
                    "total_mv": 1000000.0 + symbol_index * 10000,
                    "circ_mv": 800000.0 + symbol_index * 8000,
                    "source": "stub",
                }
            )

    daily_df = pd.DataFrame(daily_rows)
    daily_basic_df = pd.DataFrame(daily_basic_rows)
    snapshot_df = (
        daily_df.sort_values(["ts_code", "trade_date"])
        .groupby("ts_code", as_index=False)
        .tail(1)
        .rename(columns={"ts_code": "symbol"})
    )[["symbol", "close", "source"]]

    return {
        "trade_calendar": calendar_df,
        "market_bar_1d": daily_df,
        "daily_basic_1d": daily_basic_df,
        "security_master": security_df,
        "market_snapshot": snapshot_df,
    }


def _write_stub_snapshot(runtime: RuntimeSettings, file_config: FileConfig, symbols: Iterable[str], start_date: str, end_date: str) -> None:
    ensure_runtime_dirs(file_config)
    datasets = _build_stub_data(symbols=symbols, start_date=start_date, end_date=end_date)
    data_root = Path(file_config.app.data_dir)

    _write_parquet(datasets["trade_calendar"], data_root / "raw" / "trade_calendar.parquet")
    _write_parquet(datasets["market_bar_1d"], data_root / "raw" / "market_bar_1d.parquet")
    _write_parquet(datasets["daily_basic_1d"], data_root / "raw" / "daily_basic_1d.parquet")
    _write_parquet(datasets["security_master"], data_root / "raw" / "security_master.parquet")
    _write_parquet(datasets["market_snapshot"], data_root / "raw" / "market_snapshot.parquet")

    _refresh_table(runtime.database_url, "trade_calendar", datasets["trade_calendar"])
    _refresh_table(runtime.database_url, "market_bar_1d", datasets["market_bar_1d"])
    _refresh_table(runtime.database_url, "daily_basic_1d", datasets["daily_basic_1d"])
    _refresh_table(runtime.database_url, "security_master", datasets["security_master"])
    logger.info("wrote stub market datasets for %s symbols", len(list(symbols)))


def sync_market_data(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
) -> None:
    ensure_runtime_dirs(file_config)
    symbol_list = list(symbols)

    if not runtime.tushare_token:
        logger.warning("tushare token is empty, using stub snapshot")
        _write_stub_snapshot(runtime, file_config, symbol_list, start_date, end_date)
        return

    client = TushareClient(runtime.tushare_token)
    calendar_df = client.get_trade_calendar(start_date=start_date, end_date=end_date, exchange="SSE")
    daily_frames: list[pd.DataFrame] = []
    daily_basic_frames: list[pd.DataFrame] = []
    security_rows: list[dict[str, str]] = []

    for ts_code in symbol_list:
        daily_df = client.get_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if not daily_df.empty:
            daily_frames.append(daily_df)
        daily_basic_df = client.get_daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if not daily_basic_df.empty:
            daily_basic_frames.append(daily_basic_df)
        security_rows.append(_infer_security_row(ts_code))

    daily_df = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    daily_basic_df = pd.concat(daily_basic_frames, ignore_index=True) if daily_basic_frames else pd.DataFrame()
    security_df = pd.DataFrame(security_rows)

    if not daily_df.empty:
        daily_df = daily_df.rename(columns={"vol": "volume"})
        daily_df["source"] = "tushare"
        snapshot_df = (
            daily_df.sort_values(["ts_code", "trade_date"])
            .groupby("ts_code", as_index=False)
            .tail(1)
            .rename(columns={"ts_code": "symbol"})
        )[["symbol", "close", "source"]]
    else:
        snapshot_df = pd.DataFrame(columns=["symbol", "close", "source"])

    data_root = Path(file_config.app.data_dir)
    _write_parquet(calendar_df, data_root / "raw" / "trade_calendar.parquet")
    _write_parquet(daily_df, data_root / "raw" / "market_bar_1d.parquet")
    if not daily_basic_df.empty:
        daily_basic_df["source"] = "tushare"
    _write_parquet(daily_basic_df, data_root / "raw" / "daily_basic_1d.parquet")
    _write_parquet(security_df, data_root / "raw" / "security_master.parquet")
    _write_parquet(snapshot_df, data_root / "raw" / "market_snapshot.parquet")

    _refresh_table(runtime.database_url, "trade_calendar", calendar_df)
    _refresh_table(runtime.database_url, "market_bar_1d", daily_df)
    _refresh_table(runtime.database_url, "daily_basic_1d", daily_basic_df)
    _refresh_table(runtime.database_url, "security_master", security_df)

    logger.info("synced trade calendar, daily bars and daily basic data for %s symbols", len(symbol_list))
