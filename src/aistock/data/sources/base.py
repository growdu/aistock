# src/aistock/data/sources/base.py
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any

import pandas as pd


@runtime_checkable
class DataSourceClient(Protocol):
    """数据源客户端统一接口。

    所有数据源客户端（Tushare、AkShare 等）必须实现此接口。
    这样 pipeline.py 可以使用统一的接口，不需要关心具体是哪个数据源。
    """

    def ping(self) -> bool:
        """检查数据源连接是否正常。"""

    def get_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        """获取 A 股股票基本信息。

        Returns:
            DataFrame with columns: ts_code, symbol, name, industry, market, list_date...
        """

    def get_trade_calendar(
        self, start_date: str, end_date: str, exchange: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历。

        Returns:
            DataFrame with columns: exchange, cal_date, is_open, pretrade_date
        """

    def get_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线行情（未复权）。

        Returns:
            DataFrame with columns: ts_code, trade_date, open, high, low, close, volume, amount
        """

    def get_daily_basic(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线基本指标（PE/PB/换手率等）。

        Returns:
            DataFrame with columns: ts_code, trade_date, close, pe, pb, turnrate, total_mv, circ_mv...
        """

    def get_index_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取指数日线。

        Returns:
            DataFrame with columns: ts_code, trade_date, open, high, low, close, volume
        """

    def get_bars(
        self, ts_code: str, start_date: str, end_date: str, freq: str = "5m"
    ) -> pd.DataFrame:
        """获取分钟线行情。

        Args:
            freq: 频率，1m/5m/15m/30m/60m

        Returns:
            DataFrame with columns: ts_code, trade_time, open, high, low, close, volume
        """

    def get_financial_indicator(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取财务指标。

        Returns:
            DataFrame with ROE, ROA, gross_margin, net_margin, eps, bps...
        """

    def get_moneyflow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取个股资金流向。

        Returns:
            DataFrame with buy_sm_amount, sell_sm_amount, buy_lg_amount, sell_lg_amount...
        """