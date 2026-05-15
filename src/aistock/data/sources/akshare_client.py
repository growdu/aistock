# src/aistock/data/sources/akshare_client.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aistock.data.sources.base import DataSourceClient

logger = logging.getLogger(__name__)


def _symbol_to_akshare(symbol: str) -> str:
    """将 ts_code 转换为 akshare 格式。

    Tushare: 000001.SZ -> AkShare: 000001
    688041.SH -> AkShare: 688041
    """
    return symbol.split(".")[0]


def _akshare_to_ts_code(symbol: str, market: str | None = None) -> str:
    """将 akshare 数据转为标准 ts_code 格式。

    AkShare 返回的股票代码通常不带交易所后缀，
    需要根据上交所(.SH)/深交所(.SZ)规则补充。
    """
    if symbol.startswith("688"):
        return f"{symbol}.SH"
    elif symbol.startswith("000") or symbol.startswith("001"):
        return f"{symbol}.SZ"
    elif symbol.startswith("002") or symbol.startswith("003"):
        return f"{symbol}.SZ"
    elif symbol.startswith("300"):
        return f"{symbol}.SZ"
    elif symbol.startswith("400") or symbol.startswith("430"):
        return f"{symbol}.BJ"
    elif symbol.startswith("8") or symbol.startswith("430"):
        return f"{symbol}.BJ"
    else:
        # 默认沪市
        return f"{symbol}.SH"


class AkShareClient:
    """AkShare 数据源客户端。

    实现了 DataSourceClient 接口，封装 akshare 的股票数据获取功能。
    特点：完全免费，但分钟线数据有限。
    """

    def __init__(self) -> None:
        self._ak = None

    def _load(self) -> None:
        if self._ak is not None:
            return
        try:
            import akshare as ak
            self._ak = ak
        except ImportError:
            logger.warning("akshare is not installed, some functions will fail")
            self._ak = None

    def ping(self) -> bool:
        """检查 akshare 是否可用。"""
        try:
            import akshare as ak
            # 尝试获取实时行情作为健康检查
            ak.stock_zh_a_spot_em()
            return True
        except Exception:
            return False

    def get_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        """获取 A 股股票基本信息。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            df = self._ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {}
            if "代码" in df.columns:
                rename_map["代码"] = "ts_code"
            if "名称" in df.columns:
                rename_map["名称"] = "name"
            if "板块" in df.columns:
                rename_map["板块"] = "board"
            if "上市时间" in df.columns:
                rename_map["上市时间"] = "list_date"
            if "行业" in df.columns:
                rename_map["行业"] = "industry"

            if rename_map:
                df = df.rename(columns=rename_map)

            # 转换 ts_code 格式
            if "ts_code" in df.columns:
                df["ts_code"] = df["ts_code"].apply(_akshare_to_ts_code)
                df["symbol"] = df["ts_code"].str.split(".").str[0]

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get stock_basic from akshare")
            return pd.DataFrame()

    def get_trade_calendar(
        self, start_date: str, end_date: str, exchange: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            df = self._ak.tool_trade_date_hist_sina()
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            if "trade_date" in df.columns:
                df = df.rename(columns={"trade_date": "cal_date"})

            # 转换日期格式
            if "cal_date" in df.columns:
                df["cal_date"] = df["cal_date"].astype(str).str.replace("-", "")

            df["exchange"] = "SSE"
            df["is_open"] = 1  # akshare 返回的都是交易日
            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get trade_calendar from akshare")
            return pd.DataFrame()

    def get_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线行情。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            # 转换日期格式
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            df = self._ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq"
            )
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {
                "日期": "trade_date",
                "股票代码": "ts_code",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
                "换手率": "turnrate",
            }

            df = df.rename(columns=rename_map)

            # 确保 ts_code 格式正确
            if "ts_code" in df.columns and not df["ts_code"].str.contains(".").any():
                df["ts_code"] = df["ts_code"].apply(lambda x: _akshare_to_ts_code(str(x)))

            # 转换日期格式为 YYYYMMDD
            if "trade_date" in df.columns:
                df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get daily from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_daily_basic(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线基本指标。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            df = self._ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start,
                end_date=end,
                adjust="qfq"
            )
            if df is None or df.empty:
                return pd.DataFrame()

            # AkShare 日线数据含有多因子，返回的列包含换手率、市值等
            rename_map: dict[str, str] = {
                "日期": "trade_date",
                "股票代码": "ts_code",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }

            df = df.rename(columns=rename_map)

            if "ts_code" in df.columns and not df["ts_code"].str.contains(".").any():
                df["ts_code"] = df["ts_code"].apply(lambda x: _akshare_to_ts_code(str(x)))

            if "trade_date" in df.columns:
                df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get daily_basic from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_index_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取指数日线。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            df = self._ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                return pd.DataFrame()

            # 过滤日期范围
            if "date" in df.columns:
                df["date"] = df["date"].astype(str).str.replace("-", "")
                df = df[(df["date"] >= start) & (df["date"] <= end)]

            # 统一字段名
            rename_map: dict[str, str] = {
                "date": "trade_date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            df = df.rename(columns=rename_map)
            df["ts_code"] = ts_code
            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get index_daily from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_bars(
        self, ts_code: str, start_date: str, end_date: str, freq: str = "5m"
    ) -> pd.DataFrame:
        """获取分钟线行情。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            # AkShare period 映射
            period_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "30m": "30",
                "60m": "60",
            }
            period = period_map.get(freq, "5")

            df = self._ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start,
                end_date=end,
                adjust="qfq"
            )
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {
                "日期": "trade_time",
                "时间": "trade_time",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }
            df = df.rename(columns=rename_map)

            if "trade_time" in df.columns:
                df["trade_time"] = df["trade_time"].astype(str)

            df["ts_code"] = ts_code
            df["freq"] = freq
            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get bars from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_financial_indicator(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取财务指标。

        注意: AkShare 没有直接对应 Tushare fina_indicator 的接口，
        此方法返回空 DataFrame，需要财务数据时需使用 Tushare。
        """
        logger.warning("AkShare does not support financial_indicator, use Tushare instead")
        return pd.DataFrame()

    def get_moneyflow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取资金流向。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            df = self._ak.stock_money_flow_em(symbol=symbol)
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {
                "代码": "ts_code",
                "名称": "name",
                "日期": "trade_date",
                "主力净流入": "net_lg_amount",
                "超大单净流入": "net_xl_amount",
                "大单净流入": "net_l_amount",
                "中单净流入": "net_m_amount",
                "小单净流入": "net_s_amount",
            }
            df = df.rename(columns=rename_map)

            if "ts_code" in df.columns:
                df["ts_code"] = df["ts_code"].apply(lambda x: _akshare_to_ts_code(str(x)))

            if "trade_date" in df.columns:
                df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get moneyflow from akshare for %s", ts_code)
            return pd.DataFrame()