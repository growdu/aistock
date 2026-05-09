from __future__ import annotations

import logging
import time
from typing import Any, Literal

import pandas as pd

logger = logging.getLogger(__name__)

# 频率与 Tushare freq 参数映射
FreqLiteral = Literal["1m", "5m", "15m", "30m", "60m", "1h", "1d"]
FREQ_MAP: dict[FreqLiteral, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
    "1h": "60min",
    "1d": "D",
}


class TushareClient:
    """Tushare API 封装，支持日线、分钟线、财务、公告、板块等数据拉取。"""

    def __init__(self, token: str, max_retry: int = 3, retry_delay: float = 2.0) -> None:
        self.token = token
        self.max_retry = max_retry
        self.retry_delay = retry_delay
        self._ts: Any | None = None
        self._pro: Any | None = None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._pro is not None:
            return
        try:
            import tushare as ts
        except ModuleNotFoundError as exc:
            raise RuntimeError("tushare package is not installed") from exc

        self._ts = ts
        self._ts.set_token(self.token)
        self._pro = self._ts.pro_api(self.token)

    def _call(self, method: str, **kwargs) -> pd.DataFrame:
        """带重试的 Tushare API 调用，自动处理限流。"""
        self._load()
        for attempt in range(1, self.max_retry + 1):
            try:
                api = getattr(self._pro, method)
                return api(**kwargs)
            except Exception as exc:
                logger.warning(
                    "tushare %s attempt %s/%s failed: %s",
                    method,
                    attempt,
                    self.max_retry,
                    exc,
                )
                if attempt < self.max_retry:
                    time.sleep(self.retry_delay * attempt)
        # 最后一次仍然失败，返回空 DataFrame
        logger.error("tushare %s failed after %s retries", method, self.max_retry)
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # 连接检查
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        if not self.token:
            logger.warning("tushare token is empty")
            return False
        self._load()
        try:
            self._pro.trade_cal(exchange="SSE", start_date="20240101", end_date="20240110", limit=1)
        except Exception:
            logger.exception("failed to call tushare trade_cal")
            return False
        return True

    # ------------------------------------------------------------------
    # 交易日历
    # ------------------------------------------------------------------

    def get_trade_calendar(
        self,
        start_date: str,
        end_date: str,
        exchange: str = "SSE",
    ) -> pd.DataFrame:
        """返回交易日历 DataFrame，包含 exchange, cal_date, is_open, pretrade_date。"""
        return self._call(
            "trade_cal",
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            fields="exchange,cal_date,is_open,pretrade_date",
        )

    # ------------------------------------------------------------------
    # 股票基本信息
    # ------------------------------------------------------------------

    def get_stock_basic(
        self,
        list_status: str = "L",
        exchange: str = "",
        ts_code: str = "",
    ) -> pd.DataFrame:
        """
        获取 A 股股票基本信息。

        Params:
            list_status: L=上市, D=退市, P=暂停上市
            exchange: SSE/SZSE/BSE(北交所)
            ts_code: 可指定单只股票，如 300750.SZ

        Returns:
            DataFrame with ts_code, symbol, name, area, industry, market, list_date, ...
        """
        kwargs: dict[str, Any] = {"list_status": list_status}
        if exchange:
            kwargs["exchange"] = exchange
        if ts_code:
            kwargs["ts_code"] = ts_code
        return self._call("stock_basic", **kwargs)

    # ------------------------------------------------------------------
    # 日线行情
    # ------------------------------------------------------------------

    def get_daily(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        返回日线行情（未复权），包含 ts_code, trade_date, open, high, low, close, volume, amount。
        注意 Tushare 返回字段名为 vol，本模块统一暴露为 volume。
        """
        df = self._call(
            "daily",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        if not df.empty and "vol" in df.columns:
            df = df.rename(columns={"vol": "volume"})
        return df

    # ------------------------------------------------------------------
    # 日线指标（PE/PB/换手率等）
    # ------------------------------------------------------------------

    def get_daily_basic(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        返回日线基本指标，包含 ts_code, trade_date, close, pe, pb, ps_ttm,
        dv_ratio, total_mv, circ_mv, turnrate, ...
        """
        return self._call(
            "daily_basic",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date,close,pe,pb,ps_ttm,dv_ratio,total_mv,circ_mv,turnrate",
        )

    # ------------------------------------------------------------------
    # 停牌/涨跌停状态（用于风控过滤）
    # ------------------------------------------------------------------

    def get_suspend_d(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        返回每日停牌数据，包含 ts_code, trade_date, suspend_type, suspend_reason。
        """
        return self._call(
            "suspend_d",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    def get_limit_list_d(
        self,
        trade_date: str,
    ) -> pd.DataFrame:
        """
        返回指定日期的涨跌停股票列表，包含 ts_code, trade_date, limit_type, open_price, close_price。
        limit_type: 1=涨停, 2=跌停
        """
        return self._call(
            "limit_list_d",
            trade_date=trade_date,
            fields="ts_code,trade_date,limit_type,open_price,close_price",
        )

    # ------------------------------------------------------------------
    # 分钟线行情
    # ------------------------------------------------------------------

    def get_bars(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        freq: FreqLiteral = "5m",
    ) -> pd.DataFrame:
        """
        获取分钟线行情（支持 1min/5min/15min/30min/60min/日线）。

        Params:
            ts_code: 股票代码，如 300750.SZ
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            freq: 频率，1m/5m/15m/30m/60m/1d

        Returns:
            DataFrame with ts_code, trade_time, open, high, low, close, volume, amount
        """
        tushare_freq = FREQ_MAP.get(freq, "5min")
        df = self._call(
            "bars",
            api=self._pro,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            freq=tushare_freq,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        # 统一字段名
        rename = {}
        if "vol" in df.columns:
            rename["vol"] = "volume"
        if rename:
            df = df.rename(columns=rename)
        return df

    # ------------------------------------------------------------------
    # 财务指标
    # ------------------------------------------------------------------

    def get_financial_indicator(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取财务指标，包含 ROE, ROA, gross_margin, net_margin, revenue_cagr,
        profit_cagr, debt_to_assets, current_ratio, quick_ratio, eps, bps,
        pe_ttm, pb_ratio, ps_ratio 等。

        财报通常在公布后 T+1 日更新，建议用季度末日期拉取。
        """
        return self._call(
            "fina_indicator",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    # ------------------------------------------------------------------
    # 业绩快报 / 公告
    # ------------------------------------------------------------------

    def get_announcement(
        self,
        ts_code: str = "",
        start_date: str = "",
        end_date: str = "",
        ann_type: str = "",
    ) -> pd.DataFrame:
        """
        获取公告列表，包含 ts_code, ann_date, title, category。
        ann_type: 财报类型，如 财报, 业绩预告, 重大事项
        """
        kwargs: dict[str, Any] = {}
        if ts_code:
            kwargs["ts_code"] = ts_code
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if ann_type:
            kwargs["ann_type"] = ann_type
        return self._call("disclosure_date", **kwargs)

    def get_disclosure_date(
        self,
        ts_code: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame:
        """获取财报披露日期。"""
        kwargs: dict[str, Any] = {}
        if ts_code:
            kwargs["ts_code"] = ts_code
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        return self._call("disclosure_date", **kwargs)

    # ------------------------------------------------------------------
    # 行业/板块分类
    # ------------------------------------------------------------------

    def get_industry_classified(
        self,
        level: str = "L1",
        src: str = "SW2021",
    ) -> pd.DataFrame:
        """
        获取行业分类。

        Params:
            level: L1(一级行业)/L2(二级行业)/L3(三级行业)
            src: 分类来源，如 SW2021(申万2021), SW(申万2014), ZJ(中金), TMT, HW(华泰)
        """
        return self._call(
            "industry_cn",
            level=level,
            src=src,
        )

    def get_block_trade(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取大宗交易数据，包含 ts_code, trade_date, price, volume, amount, buyer, seller。
        """
        return self._call(
            "block_trade",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    # ------------------------------------------------------------------
    # 资金流向（个股）
    # ------------------------------------------------------------------

    def get_moneyflow(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取个股资金流向，包含 buy_sm_amount, sell_sm_amount, buy_md_amount,
        sell_md_amount, buy_lg_amount, sell_lg_amount, buy_md_amount 等。
        """
        return self._call(
            "moneyflow",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date,buy_sm_amount,sell_sm_amount,buy_md_amount,sell_md_amount,buy_lg_amount,sell_lg_amount,net_mf_amount",
        )

    # ------------------------------------------------------------------
    # 融资融券
    # ------------------------------------------------------------------

    def get_margin_detail(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """获取融资融券明细。"""
        return self._call(
            "margin_detail",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    # ------------------------------------------------------------------
    # 指数日线（用于市场因子/beta 计算）
    # ------------------------------------------------------------------

    def get_index_daily(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取指数日线，用于计算指数收益率、行业强弱等市场因子。
        ts_code 格式：000001.SH(上证指数), 399001.SZ(深证成指),
                      399006.SZ(创业板指), 000688.SH(科创50)
        """
        df = self._call(
            "index_daily",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        if "vol" in df.columns:
            df = df.rename(columns={"vol": "volume"})
        return df
