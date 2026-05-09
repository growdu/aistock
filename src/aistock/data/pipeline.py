from __future__ import annotations

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
    engine = build_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM {table_name}"))
        if not df.empty:
            df.to_sql(table_name, connection, if_exists="append", index=False)


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


def _write_stub_snapshot(file_config: FileConfig) -> None:
    ensure_runtime_dirs(file_config)
    output = Path(file_config.app.data_dir) / "raw" / "market_snapshot.parquet"
    df = pd.DataFrame(
        [{"symbol": "300750", "close": 0.0, "source": file_config.data_source.primary_provider}]
    )
    _write_parquet(df, output)
    logger.info("wrote market snapshot to %s", output)


def sync_market_data(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
) -> None:
    ensure_runtime_dirs(file_config)

    if not runtime.tushare_token:
        logger.warning("tushare token is empty, using stub snapshot")
        _write_stub_snapshot(file_config)
        return

    client = TushareClient(runtime.tushare_token)
    calendar_df = client.get_trade_calendar(start_date=start_date, end_date=end_date, exchange="SSE")
    daily_frames: list[pd.DataFrame] = []
    security_rows: list[dict[str, str]] = []

    for ts_code in symbols:
        daily_df = client.get_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if not daily_df.empty:
            daily_frames.append(daily_df)
        security_rows.append(_infer_security_row(ts_code))

    daily_df = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
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
    _write_parquet(security_df, data_root / "raw" / "security_master.parquet")
    _write_parquet(snapshot_df, data_root / "raw" / "market_snapshot.parquet")

    _refresh_table(runtime.database_url, "trade_calendar", calendar_df)
    _refresh_table(runtime.database_url, "market_bar_1d", daily_df)
    _refresh_table(runtime.database_url, "security_master", security_df)

    logger.info("synced trade calendar and daily bars for %s symbols", len(list(symbols)))
