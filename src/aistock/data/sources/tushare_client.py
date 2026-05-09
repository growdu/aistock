from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class TushareClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self._ts: Any | None = None
        self._pro: Any | None = None

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

    def get_trade_calendar(self, start_date: str, end_date: str, exchange: str = "SSE") -> pd.DataFrame:
        self._load()
        return self._pro.trade_cal(
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            fields="exchange,cal_date,is_open,pretrade_date",
        )

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self._load()
        return self._pro.daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self._load()
        return self._pro.daily_basic(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date,pe,pb,ps_ttm,dv_ratio,total_mv,circ_mv",
        )
