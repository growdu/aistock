from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from sqlalchemy import inspect, text

from aistock.config.settings import DataSourceConfig, FileConfig, RuntimeSettings
from aistock.data.sources.tushare_client import TushareClient
from aistock.data.sources.akshare_client import AkShareClient
from aistock.db.base import build_engine


def get_client(file_config: FileConfig, runtime: RuntimeSettings):
    """根据配置类型返回对应的数据源客户端。"""
    if file_config.data_source.type == "akshare":
        return AkShareClient()
    else:
        return TushareClient(runtime.tushare_token)

logger = logging.getLogger(__name__)

# 科创板+创业板股票池（可通过配置覆盖）
DEFAULT_WATCHLIST = ["300750.SZ", "688041.SH", "688111.SH", "688012.SH", "300059.SZ"]
# 核心指数列表（用于市场因子）
CORE_INDICES = ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"]


# =============================================================================
# 目录初始化
# =============================================================================


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


# =============================================================================
# 内部工具
# =============================================================================


def _write_parquet(df: pd.DataFrame, output: Path) -> None:
    if df is None or df.empty:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)


def _ts_to_date(ts: str) -> str:
    """将 YYYY-MM-DD HH:MM:SS 转为 YYYYMMDD"""
    return ts.replace("-", "").replace(":", "").replace(" ", "")[:8]


def _add_updated_at(df: pd.DataFrame) -> pd.DataFrame:
    if not df.empty and "updated_at" not in df.columns:
        df = df.copy()
        df["updated_at"] = datetime.utcnow()
    return df


# =============================================================================
# 数据库 UPSERT（增量同步核心）
# =============================================================================


def _upsert_table(database_url: str, table_name: str, df: pd.DataFrame) -> int:
    """
    增量写入：只插入新记录或更新已有记录。
    主键相同的记录会被 UPDATE，其他字段取最新值。
    返回影响行数。
    """
    if df is None or df.empty:
        return 0

    frame = _add_updated_at(df.copy())
    engine = build_engine(database_url)
    rows_affected = 0

    with engine.begin() as conn:
        # 提取主键列
        inspector = inspect(engine)
        pk_cols: list[str] = [
            c["name"] for c in inspector.get_pk_constraint(table_name)["constrained_columns"]
        ]

        if not pk_cols:
            logger.warning("table %s has no primary key, falling back to replace", table_name)
            frame.to_sql(table_name, conn, if_exists="replace", index=False)
            return len(frame)

        # 构造 ON CONFLICT ... DO UPDATE SET ... WHERE 子句
        cols = [c for c in frame.columns if c != "updated_at"]
        placeholders = ", ".join([f":{c}" for c in cols])
        pk_set = ", ".join([f"{c}=EXCLUDED.{c}" for c in pk_cols])
        update_cols = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols if c not in pk_cols])

        sql = text(
            f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {pk_set}, {update_cols}"
        )
        rows_affected = conn.execute(sql, frame.to_dict(orient="records")).rowcount

    logger.debug("upserted %s rows into %s", rows_affected, table_name)
    return rows_affected


def _delete_and_insert(database_url: str, table_name: str, df: pd.DataFrame) -> None:
    """
    全量替换（用于小表如交易日历）。
    """
    if df is None or df.empty:
        return
    frame = _add_updated_at(df.copy())
    engine = build_engine(database_url)
    with engine.begin() as conn:
        # 交易日历用复合主键，DELETE 时也用复合键
        conn.execute(text(f"DELETE FROM {table_name}"))
        frame.to_sql(table_name, conn, if_exists="append", index=False)


# =============================================================================
# 股票信息同步
# =============================================================================


def _infer_security_row(ts_code: str, name: str = "") -> dict[str, str]:
    symbol, exchange = ts_code.split(".")
    if symbol.startswith("688"):
        board = "STAR"
    elif symbol.startswith("300"):
        board = "GEM"
    else:
        board = "MAIN"
    return {
        "ts_code": ts_code,
        "symbol": symbol,
        "exchange": exchange,
        "board": board,
        "name": name,
    }


def sync_stock_basic(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    list_status: str = "L",
) -> int:
    """
    同步股票基本信息（ts_code, symbol, name, industry, market, list_date...）。
    这是其他所有数据同步的前置条件。
    返回同步的股票数量。
    """
    client = get_client(file_config, runtime)
    df = client.get_stock_basic(list_status=list_status)
    if df is None or df.empty:
        logger.warning("stock_basic returned empty, skipping")
        return 0

    # 统一字段
    rename = {}
    if "symbol" not in df.columns and "ts_code" in df.columns:
        df = df.copy()
        df["symbol"] = df["ts_code"].str.split(".").str[0]
    if "vol" in df.columns:
        rename["vol"] = "volume"
    df = df.rename(columns=rename)

    if "source" not in df.columns:
        df["source"] = "tushare"

    data_root = Path(file_config.app.data_dir)
    _write_parquet(df, data_root / "raw" / "stock_basic.parquet")
    rows = _upsert_table(runtime.database_url, "stock_basic", df)
    logger.info("synced %s stock_basic records", rows)
    return rows


# =============================================================================
# 交易日历同步
# =============================================================================


def sync_trade_calendar(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    start_date: str,
    end_date: str,
    exchange: str = "SSE",
) -> int:
    """同步交易日历（全量替换）。"""
    client = get_client(file_config, runtime)
    df = client.get_trade_calendar(start_date=start_date, end_date=end_date, exchange=exchange)
    if df is None or df.empty:
        logger.warning("trade_calendar returned empty for %s %s-%s", exchange, start_date, end_date)
        return 0

    if "source" not in df.columns:
        df["source"] = "tushare"

    data_root = Path(file_config.app.data_dir)
    _write_parquet(df, data_root / "raw" / "trade_calendar.parquet")
    _delete_and_insert(runtime.database_url, "trade_calendar", df)
    logger.info("synced %s trade_calendar records", len(df))
    return len(df)


# =============================================================================
# 日线行情 + 日线指标同步（增量）
# =============================================================================


def sync_market_daily(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    """
    同步日线行情和日线指标（增量 UPSERT）。
    返回每种数据的行数。
    """
    client = get_client(file_config, runtime)
    symbol_list = list(symbols)
    results: dict[str, int] = {}

    daily_frames: list[pd.DataFrame] = []
    daily_basic_frames: list[pd.DataFrame] = []
    security_rows: list[dict[str, str]] = []

    for ts_code in symbol_list:
        daily_df = client.get_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if daily_df is not None and not daily_df.empty:
            daily_df["source"] = "tushare"
            daily_frames.append(daily_df)

        daily_basic_df = client.get_daily_basic(
            ts_code=ts_code, start_date=start_date, end_date=end_date
        )
        if daily_basic_df is not None and not daily_basic_df.empty:
            daily_basic_df["source"] = "tushare"
            daily_basic_frames.append(daily_basic_df)

        security_rows.append(_infer_security_row(ts_code, ""))

    daily_all = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    daily_basic_all = (
        pd.concat(daily_basic_frames, ignore_index=True) if daily_basic_frames else pd.DataFrame()
    )
    security_df = pd.DataFrame(security_rows)

    data_root = Path(file_config.app.data_dir)

    if not daily_all.empty:
        _write_parquet(daily_all, data_root / "raw" / "market_bar_1d.parquet")
        results["market_bar_1d"] = _upsert_table(runtime.database_url, "market_bar_1d", daily_all)
    else:
        results["market_bar_1d"] = 0

    if not daily_basic_all.empty:
        _write_parquet(daily_basic_all, data_root / "raw" / "daily_basic_1d.parquet")
        results["daily_basic_1d"] = _upsert_table(
            runtime.database_url, "daily_basic_1d", daily_basic_all
        )
    else:
        results["daily_basic_1d"] = 0

    if not security_df.empty:
        _write_parquet(security_df, data_root / "raw" / "security_master.parquet")
        _upsert_table(runtime.database_url, "security_master", security_df)

    # 更新 snapshot
    if not daily_all.empty:
        snapshot_df = (
            daily_all.sort_values(["ts_code", "trade_date"])
            .groupby("ts_code", as_index=False)
            .tail(1)
            .rename(columns={"ts_code": "symbol"})
        )[["symbol", "close", "source"]]
        _write_parquet(snapshot_df, data_root / "raw" / "market_snapshot.parquet")

    logger.info(
        "synced daily data: market_bar_1d=%s, daily_basic_1d=%s for %s symbols",
        results.get("market_bar_1d", 0),
        results.get("daily_basic_1d", 0),
        len(symbol_list),
    )
    return results


# =============================================================================
# 分钟线同步
# =============================================================================


FreqLiteral = Literal["1m", "5m", "15m", "30m", "60m"]


def sync_market_minute(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
    freq: FreqLiteral = "5m",
) -> dict[str, int]:
    """
    同步分钟线行情（增量 UPSERT，按 freq 分表）。
    分钟线数据量大，每次同步限制回溯天数以控制量。
    """
    client = get_client(file_config, runtime)

    symbol_list = list(symbols)
    all_bars: list[pd.DataFrame] = []
    table_name = "market_bar_1m"  # 目前 1m/5m/15m 共用 1m 表，通过 freq 字段区分

    for ts_code in symbol_list:
        df = client.get_bars(ts_code=ts_code, start_date=start_date, end_date=end_date, freq=freq)
        if df is None or df.empty:
            continue
        # trade_time 统一为 YYYY-MM-DD HH:MM:SS
        if "trade_time" not in df.columns and "trade_date" in df.columns:
            df = df.rename(columns={"trade_date": "trade_time"})
        df["freq"] = freq
        df["source"] = "tushare"
        all_bars.append(df)

    if not all_bars:
        return {table_name: 0}

    bars_df = pd.concat(all_bars, ignore_index=True)
    data_root = Path(file_config.app.data_dir)
    minute_path = data_root / "raw" / f"market_bar_{freq}.parquet"
    _write_parquet(bars_df, minute_path)

    rows = _upsert_table(runtime.database_url, table_name, bars_df)
    logger.info("synced %s minute bars (%s freq) for %s symbols", rows, freq, len(symbol_list))
    return {table_name: rows}


# =============================================================================
# 财务指标同步（按季度）
# =============================================================================


# 财报披露的四个季度节点
QUARTER_DATES = ["0331", "0630", "0930", "1231"]


def _generate_fiscal_quarters(start_year: int, end_year: int) -> list[str]:
    """生成 start_year~end_year 所有季度末日期（格式 YYYMMDD）。"""
    dates: list[str] = []
    for year in range(start_year, end_year + 1):
        for qd in QUARTER_DATES:
            dates.append(f"{year}{qd}")
    return dates


def sync_financial_indicator(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str],
    start_year: int | None = None,
    end_year: int | None = None,
) -> int:
    """
    同步财务指标（ROE, ROA, gross_margin 等）。
    建议每年同步一次即可，不需要每日拉取。
    默认同步最近 4 年数据。
    """
    client = get_client(file_config, runtime)
    symbol_list = list(symbols)
    quarters = _generate_fiscal_quarters(start_year, end_year)

    all_indicators: list[pd.DataFrame] = []
    for ts_code in symbol_list:
        for qdate in quarters:
            df = client.get_financial_indicator(ts_code=ts_code, start_date=qdate, end_date=qdate)
            if df is not None and not df.empty:
                df["source"] = "tushare"
                all_indicators.append(df)

    if not all_indicators:
        logger.info("no financial indicators returned for %s symbols", len(symbol_list))
        return 0

    indicator_df = pd.concat(all_indicators, ignore_index=True)
    data_root = Path(file_config.app.data_dir)
    _write_parquet(indicator_df, data_root / "raw" / "financial_indicator.parquet")
    rows = _upsert_table(runtime.database_url, "financial_indicator", indicator_df)
    logger.info("synced %s financial_indicator records for %s symbols", rows, len(symbol_list))
    return rows


# =============================================================================
# 指数日线同步（市场因子用）
# =============================================================================


def sync_index_daily(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    indices: Iterable[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int:
    """
    同步指数日线（用于计算 beta/板块强弱等市场因子）。
    默认追踪沪深指数最近 2 年数据。
    """
    client = get_client(file_config, runtime)

    if indices is None:
        indices = CORE_INDICES
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")

    index_list = list(indices)
    frames: list[pd.DataFrame] = []

    for ts_code in index_list:
        df = client.get_index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            continue
        df["source"] = "tushare"
        frames.append(df)

    if not frames:
        return 0

    all_index = pd.concat(frames, ignore_index=True)
    data_root = Path(file_config.app.data_dir)
    _write_parquet(all_index, data_root / "raw" / "index_daily.parquet")
    rows = _upsert_table(runtime.database_url, "index_daily", all_index)
    logger.info("synced %s index_daily records for %s indices", rows, len(index_list))
    return rows


# =============================================================================
# 资金流向同步
# =============================================================================


def sync_moneyflow(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
) -> int:
    """同步个股资金流向（增量 UPSERT）。"""
    client = get_client(file_config, runtime)
    symbol_list = list(symbols)
    frames: list[pd.DataFrame] = []

    for ts_code in symbol_list:
        df = client.get_moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            continue
        df["source"] = "tushare"
        frames.append(df)

    if not frames:
        return 0

    all_mf = pd.concat(frames, ignore_index=True)
    data_root = Path(file_config.app.data_dir)
    _write_parquet(all_mf, data_root / "raw" / "money_flow.parquet")
    rows = _upsert_table(runtime.database_url, "money_flow", all_mf)
    logger.info("synced %s moneyflow records for %s symbols", rows, len(symbol_list))
    return rows


# =============================================================================
# 停牌/涨跌停同步（风控用）
# =============================================================================


def sync_limit_list(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    trade_date: str,
) -> dict[str, int]:
    """同步指定日期涨跌停股票列表。"""
    client = get_client(file_config, runtime)
    df = client.get_limit_list_d(trade_date=trade_date)
    if df is None or df.empty:
        return {}

    df["source"] = "tushare"
    data_root = Path(file_config.app.data_dir)
    _write_parquet(df, data_root / "raw" / f"limit_list_{trade_date}.parquet")
    rows = _upsert_table(runtime.database_url, "limit_list_d", df)
    logger.info("synced %s limit_list records for %s", rows, trade_date)
    return {"limit_list_d": rows}


# =============================================================================
# 财报披露日期同步
# =============================================================================


def sync_disclosure_date(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    start_year: int | None = None,
    end_year: int | None = None,
) -> int:
    """同步财报披露日期（用于风控/事件驱动）。"""
    client = get_client(file_config, runtime)

    now = datetime.now()
    if start_year is None:
        start_year = now.year - 2
    if end_year is None:
        end_year = now.year

    quarters = _generate_fiscal_quarters(start_year, end_year)
    frames: list[pd.DataFrame] = []

    for qdate in quarters:
        df = client.get_disclosure_date(start_date=qdate, end_date=qdate)
        if df is None or df.empty:
            continue
        df["source"] = "tushare"
        frames.append(df)

    if not frames:
        return 0

    all_dd = pd.concat(frames, ignore_index=True)
    data_root = Path(file_config.app.data_dir)
    _write_parquet(all_dd, data_root / "raw" / "disclosure_date.parquet")
    rows = _upsert_table(runtime.database_url, "disclosure_date", all_dd)
    logger.info("synced %s disclosure_date records", rows)
    return rows


# =============================================================================
# 统一入口：全量同步
# =============================================================================


def sync_all(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    include_minute: bool = False,
    minute_freq: FreqLiteral = "5m",
    sync_financial: bool = True,
) -> dict[str, Any]:
    """
    统一同步入口，按顺序执行所有数据同步。

    Params:
        symbols: 股票列表，默认使用配置文件中的 watchlist
        start_date: 日线开始日期，默认 2 年前
        end_date: 日线结束日期，默认今天
        include_minute: 是否同步分钟线（数据量大，默认 False）
        minute_freq: 分钟线频率
        sync_financial: 是否同步财务数据（默认 True，首次同步后不必每次运行）
    """
    ensure_runtime_dirs(file_config)

    # 确定日期范围
    now = datetime.now()
    if end_date is None:
        end_date = now.strftime("%Y%m%d")
    if start_date is None:
        start_date = (now - timedelta(days=730)).strftime("%Y%m%d")

    # 确定股票池
    if symbols is None:
        symbols = file_config.strategy.symbols or DEFAULT_WATCHLIST
    symbol_list = list(symbols)

    results: dict[str, Any] = {}

    # 1. 股票基本信息（前置依赖）
    results["stock_basic"] = sync_stock_basic(runtime, file_config)

    # 2. 交易日历
    results["trade_calendar"] = sync_trade_calendar(
        runtime,
        file_config,
        start_date=start_date,
        end_date=end_date,
    )

    # 3. 日线行情 + 日线指标
    results["market_daily"] = sync_market_daily(
        runtime,
        file_config,
        symbols=symbol_list,
        start_date=start_date,
        end_date=end_date,
    )

    # 4. 分钟线（可选）
    if include_minute:
        results["market_minute"] = sync_market_minute(
            runtime,
            file_config,
            symbols=symbol_list,
            start_date=start_date,
            end_date=end_date,
            freq=minute_freq,
        )

    # 5. 指数日线（市场因子）
    results["index_daily"] = sync_index_daily(
        runtime,
        file_config,
        start_date=start_date,
        end_date=end_date,
    )

    # 6. 资金流向
    results["moneyflow"] = sync_moneyflow(
        runtime,
        file_config,
        symbols=symbol_list,
        start_date=start_date,
        end_date=end_date,
    )

    # 7. 涨跌停（当日）
    results["limit_list"] = sync_limit_list(
        runtime,
        file_config,
        trade_date=now.strftime("%Y%m%d"),
    )

    # 8. 财务指标（按年度，不需要每次跑）
    if sync_financial:
        results["financial_indicator"] = sync_financial_indicator(
            runtime,
            file_config,
            symbols=symbol_list,
        )
        results["disclosure_date"] = sync_disclosure_date(
            runtime,
            file_config,
        )

    logger.info("sync_all completed: %s", results)
    return results


# =============================================================================
# 兼容旧 API：sync_market_data（仍然是全量替换，但改为调用新的 UPSERT 逻辑）
# =============================================================================


def sync_market_data(
    runtime: RuntimeSettings,
    file_config: FileConfig,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
) -> None:
    """
    兼容旧 API，推荐改用 sync_all。
    本函数仅同步日线数据。
    """
    sync_market_daily(
        runtime=runtime,
        file_config=file_config,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )
