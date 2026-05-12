"""
QMT（迅投极速交易系统）券商适配器。

接入方式：
1. 在有 QMT 终端的 Windows 上运行
2. QMT 需要开启「迅投极速交易 API」插件
3. 使用 xtquant Python 包连接

安装：pip install xtquant

注意事项：
- QMT 只支持 Windows
- 需要有 QMT 账号和量化交易权限
- 实盘前请充分测试
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aistock.broker.base import (
    AccountInfo,
    BrokerAdapter,
    OrderExecution,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
)

logger = logging.getLogger(__name__)

# xtquant 可能未安装，延迟导入以便模拟环境也能运行
_XT_INSTALLED = False
_xt_api = None

try:
    from xtquant import xtdata  # noqa: F401
    from xtquant.xttrade import XtQuantTrader  # noqa: F401

    _XT_INSTALLED = True
except ImportError:
    logger.warning("xtquant not installed. QMTBroker will run in simulation mode.")


# =============================================================================
# 订单类型映射
# =============================================================================

_QMT_ORDER_TYPE = {
    OrderType.MARKET: "4",  # QMT 市价单
    OrderType.LIMIT: "2",  # QMT 限价单
}

_QMT_SIDE_MAP = {
    OrderSide.BUY: "1",
    OrderSide.SELL: "2",
}


# =============================================================================
# QMT 券商
# =============================================================================


class QMTBroker(BrokerAdapter):
    """
    QMT 实盘券商适配器。

    Params:
        account:      资金账号（16 位模拟账号或真实账号）
        password:     交易密码
        session_path: 会话缓存路径（用于断线重连）
        mode:         连接模式，"mini"（MiniQMT默认端口）或 "ext"（迅投极速模式）
    """

    def __init__(
        self,
        account: str,
        password: str,
        session_path: str | None = None,
        mode: str = "mini",
    ) -> None:
        if not _XT_INSTALLED:
            raise RuntimeError("xtquant not installed. Run: pip install xtquant")

        self.account = account
        self._password = password
        self._mode = mode
        self._session_path = session_path or f"./qmt_session_{account}"
        self._trader: Any = None
        self._connect()

    # -------------------------------------------------------------------------
    # 连接管理
    # -------------------------------------------------------------------------

    def _connect(self) -> None:
        """建立 QMT 连接。"""
        if not _XT_INSTALLED:
            return

        from xtquant.xttrade import XtQuantTrader

        if self._mode == "ext":
            self._trader = XtQuantTrader(self._session_path)
        else:
            self._trader = XtQuantTrader()

        # 连接端口（MiniQMT 默认 58610）
        self._trader.connect()
        self._trader.set_check_cache_today(False)

        # 认证
        self._trader.login(self.account, self._password)

        logger.info("QMT connected: account=%s, mode=%s", self.account, self._mode)

    def _ensure_connected(self) -> None:
        if self._trader is None:
            raise ConnectionError("QMT not connected")

    @property
    def broker_type(self) -> str:
        return "qmt"

    # -------------------------------------------------------------------------
    # 行情
    # -------------------------------------------------------------------------

    def get_quote(self, symbol: str) -> Quote | None:
        self._ensure_connected()
        try:
            import xtquant.xtdata as xtdata

            data = xtdata.get_full_tick([symbol])
            if not data or symbol not in data:
                return None
            tick = data[symbol]
            return Quote(
                symbol=symbol,
                last_price=tick.lastPrice or 0.0,
                open=tick.open or 0.0,
                high=tick.high or 0.0,
                low=tick.low or 0.0,
                volume=tick.volume or 0.0,
                amount=tick.amount or 0.0,
                bid1=tick.bid1 or 0.0,
                ask1=tick.ask1 or 0.0,
                timestamp=datetime.now().isoformat(),
            )
        except Exception as exc:
            logger.error("QMT get_quote failed for %s: %s", symbol, exc)
            return None

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        self._ensure_connected()
        result = {}
        for sym in symbols:
            q = self.get_quote(sym)
            if q:
                result[sym] = q
        return result

    # -------------------------------------------------------------------------
    # 账户与持仓
    # -------------------------------------------------------------------------

    def get_account(self) -> AccountInfo:
        self._ensure_connected()
        try:
            from xtquant.xtdata import get_account_info

            info = get_account_info(self.account)
            if info:
                return AccountInfo(
                    account_id=self.account,
                    total_assets=info.get("total_assets", 0.0),
                    cash=info.get("cash", 0.0),
                    market_value=info.get("market_value", 0.0),
                    frozen_cash=info.get("frozen_cash", 0.0),
                    available_cash=info.get("available_cash", 0.0),
                    equity=info.get("total_assets", 0.0),
                )
        except Exception as exc:
            logger.error("QMT get_account failed: %s", exc)

        return AccountInfo(
            account_id=self.account,
            total_assets=0.0,
            cash=0.0,
            market_value=0.0,
            frozen_cash=0.0,
        )

    def get_positions(self) -> list[Position]:
        self._ensure_connected()
        positions = []
        try:
            from xtquant.xtdata import get_stock_pos

            positions_data = get_stock_pos(self.account)
            for pos in positions_data:
                positions.append(
                    Position(
                        symbol=pos.get("stock_code", ""),
                        volume=pos.get("volume", 0),
                        avg_cost=pos.get("avg_cost", 0.0),
                        last_price=pos.get("last_price", 0.0),
                        market_value=pos.get("market_value", 0.0),
                        unrealized_pnl=pos.get("unrealized_pnl", 0.0),
                        realized_pnl=pos.get("realized_pnl", 0.0),
                    )
                )
        except Exception as exc:
            logger.error("QMT get_positions failed: %s", exc)
        return positions

    # -------------------------------------------------------------------------
    # 下单
    # -------------------------------------------------------------------------

    def place_order(self, order: OrderRequest) -> OrderExecution:
        self._ensure_connected()
        order_id = f"qmt-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        submitted_at = datetime.now().isoformat()

        try:
            # QMT 下单参数
            # acc: 证券账号，stock_code: 股票代码，entrust_amount: 委托数量
            # entrust_price: 委托价格（0 表示市价），entrust_type: 委托类型
            # price_type: 价格类型
            price = order.price if order.order_type == OrderType.LIMIT else 0.0

            result = self._trader.order_stock(
                account=self.account,
                stock_code=order.symbol,
                entrust_amount=order.volume,
                entrust_price=price,
                price_type=_QMT_ORDER_TYPE.get(order.order_type, "4"),
                entrust_direction=_QMT_SIDE_MAP.get(order.side, "1"),
                user_data=order.comment or "",
            )

            broker_order_id = str(result.get("entrust_no", ""))
            filled = result.get("filled_volume", 0)
            avg_price = result.get("filled_price", price)

            status = OrderStatus.FILLED if filled >= order.volume else OrderStatus.PARTIAL
            if filled <= 0:
                status = OrderStatus.PENDING

            exec_report = OrderExecution(
                order_id=order_id,
                broker_order_id=broker_order_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                requested_volume=order.volume,
                filled_volume=filled,
                avg_fill_price=avg_price if filled > 0 else None,
                status=status,
                submitted_at=submitted_at,
                filled_at=datetime.now().isoformat() if status == OrderStatus.FILLED else None,
                message=str(result),
            )
            logger.info(
                "QMT order placed: %s %s %d @ %.4f, status=%s",
                order.side.value,
                order.symbol,
                order.volume,
                price,
                status.value,
            )
            return exec_report

        except Exception as exc:
            logger.error("QMT place_order failed for %s: %s", order.symbol, exc)
            return OrderExecution(
                order_id=order_id,
                broker_order_id=None,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                requested_volume=order.volume,
                filled_volume=0,
                avg_fill_price=None,
                status=OrderStatus.REJECTED,
                submitted_at=submitted_at,
                filled_at=None,
                message=str(exc),
            )

    def cancel_order(self, broker_order_id: str) -> bool:
        self._ensure_connected()
        try:
            success = self._trader.cancel_order_stock(broker_order_id)
            logger.info("QMT cancel order: %s -> %s", broker_order_id, success)
            return success
        except Exception as exc:
            logger.error("QMT cancel_order failed: %s", exc)
            return False

    # -------------------------------------------------------------------------
    # 市场状态
    # -------------------------------------------------------------------------

    def is_trading_day(self, date: str | None = None) -> bool:
        try:
            import xtquant.xtdata as xtdata

            if date is None:
                date = datetime.now().strftime("%Y%m%d")
            trading_days = xtdata.get_trading_days("SH", start_time="20000101", end_time="20991231")
            return date in trading_days
        except Exception:
            return False

    def is_market_open(self) -> bool:
        now = datetime.now()
        h, m = now.hour, now.minute
        return (9, 30) <= (h, m) <= (11, 30) or (13, 0) <= (h, m) <= (15, 0)
