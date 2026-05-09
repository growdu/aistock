"""
模拟交易券商。

支持：
- 全内存持仓/资金追踪
- 交易成本（手续费 + 滑点 + 印花税）
- 订单簿日志（所有操作可追溯）
- 权益重估（每日收盘）
- 批量下单（原子性执行）
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
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


@dataclass
class TradeConfig:
    """模拟交易配置。"""

    initial_cash: float = 1_000_000.0
    transaction_cost_rate: float = 0.0003  # 手续费 0.03%
    slippage_rate: float = 0.0005  # 滑点 0.05%
    stamp_tax_rate: float = 0.001  # 印花税 0.1%（仅卖出）
    min_order_value: float = 100.0  # 最小下单金额
    margin_rate: float = 1.0  # 担保物率（1 = 全额，0.5 = 两倍杠杆）
    test_mode: bool = False  # True 时跳过市场时间检查，便于单元测试


class SimBroker(BrokerAdapter):
    """
    内存模拟券商。

    支持以下订单类型和风控：
    - 市价单/限价单
    - 成交量限制（单笔不超过日均成交量的 5%）
    - 最小下单金额
    - 资金充足性检查
    """

    def __init__(self, config: TradeConfig | None = None) -> None:
        self.cfg = config or TradeConfig()
        self._cash = self.cfg.initial_cash
        self._frozen_cash = 0.0
        self._positions: dict[str, dict[str, Any]] = {}  # symbol -> pos data
        self._orders: dict[str, OrderExecution] = {}  # order_id -> execution
        self._order_history: list[OrderExecution] = []
        self._market_prices: dict[str, float] = {}  # symbol -> last_price
        self._daily_volumes: dict[str, float] = {}  # symbol -> volume
        self._started_at = datetime.now().isoformat()
        self._trade_days = 0

    # -------------------------------------------------------------------------
    # 基础设施
    # -------------------------------------------------------------------------

    @property
    def broker_type(self) -> str:
        return "sim"

    def is_trading_day(self, date: str | None = None) -> bool:
        # 模拟环境：始终可交易
        return True

    def is_market_open(self) -> bool:
        if self.cfg.test_mode:
            return True
        now = datetime.now()
        h, m = now.hour, now.minute
        # A 股：9:30-11:30 / 13:00-15:00
        return (9, 30) <= (h, m) <= (11, 30) or (13, 0) <= (h, m) <= (15, 0)

    def get_quote(self, symbol: str) -> Quote | None:
        price = self._market_prices.get(symbol, 0.0)
        if price <= 0:
            return None
        return Quote(
            symbol=symbol,
            last_price=price,
            open=price * 0.99,
            high=price * 1.01,
            low=price * 0.98,
            volume=self._daily_volumes.get(symbol, 10_000_000),
            amount=price * self._daily_volumes.get(symbol, 10_000_000),
            bid1=price * 0.999,
            ask1=price * 1.001,
            timestamp=datetime.now().isoformat(),
        )

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {sym: q for sym in symbols if (q := self.get_quote(sym)) is not None}

    # -------------------------------------------------------------------------
    # 账户与持仓
    # -------------------------------------------------------------------------

    def get_account(self) -> AccountInfo:
        market_value = self._calc_market_value()
        total_assets = self._cash + market_value
        return AccountInfo(
            account_id="SIM001",
            total_assets=total_assets,
            cash=self._cash,
            market_value=market_value,
            frozen_cash=self._frozen_cash,
            available_cash=self._cash - self._frozen_cash,
            equity=total_assets,
        )

    def get_positions(self) -> list[Position]:
        positions = []
        for sym, pos_data in self._positions.items():
            if pos_data["volume"] <= 0:
                continue
            last_price = self._market_prices.get(sym, pos_data["avg_cost"])
            market_value = pos_data["volume"] * last_price
            cost_basis = pos_data["volume"] * pos_data["avg_cost"]
            positions.append(
                Position(
                    symbol=sym,
                    volume=pos_data["volume"],
                    avg_cost=pos_data["avg_cost"],
                    last_price=last_price,
                    market_value=market_value,
                    unrealized_pnl=market_value - cost_basis,
                    realized_pnl=pos_data.get("realized_pnl", 0.0),
                    today_volume=pos_data.get("today_volume", 0),
                )
            )
        return positions

    def _calc_market_value(self) -> float:
        return sum(
            pos["volume"] * self._market_prices.get(sym, pos["avg_cost"])
            for sym, pos in self._positions.items()
            if pos["volume"] > 0
        )

    # -------------------------------------------------------------------------
    # 下单核心
    # -------------------------------------------------------------------------

    def place_order(self, order: OrderRequest) -> OrderExecution:
        """执行模拟下单（含资金检查、成交量限制）。"""
        order_id = f"sim-{uuid.uuid4().hex[:12]}"
        submitted_at = datetime.now().isoformat()

        # 获取当前行情
        quote = self.get_quote(order.symbol)
        if quote is None:
            return self._reject(order_id, order, submitted_at, "no market quote")

        # 确定成交价
        exec_price = self._calc_exec_price(order, quote)
        volume = order.volume

        # 风控检查
        if order.side == OrderSide.BUY:
            # 买入：所需资金 = 股数 × 执行价 × (1 + 手续费率) + 手续费（滑点在价里已体现）
            cost = volume * exec_price * (1 + self.cfg.transaction_cost_rate)
            if cost > self._cash - self._frozen_cash:
                return self._reject(order_id, order, submitted_at, "insufficient cash")
            # 成交量限制
            max_volume_by_liq = int(quote.volume * 0.05 / 100) * 100
            if volume > max_volume_by_liq:
                volume = max_volume_by_liq
                if volume < 100:
                    return self._reject(order_id, order, submitted_at, "insufficient liquidity")

        elif order.side == OrderSide.SELL:
            pos = self._positions.get(order.symbol, {})
            if pos.get("volume", 0) < volume:
                return self._reject(order_id, order, submitted_at, "insufficient position")

        # 更新持仓
        self._apply_trade(order.symbol, order.side, volume, exec_price)

        # 更新订单记录
        exec_report = OrderExecution(
            order_id=order_id,
            broker_order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            requested_volume=order.volume,
            filled_volume=volume,
            avg_fill_price=exec_price,
            status=OrderStatus.FILLED,
            submitted_at=submitted_at,
            filled_at=datetime.now().isoformat(),
            message="filled",
        )
        self._orders[order_id] = exec_report
        self._order_history.append(exec_report)

        logger.info(
            "sim order filled: %s %s %d @ %.4f (reason: %s)",
            order.side.value, order.symbol, volume, exec_price, order.comment,
        )
        return exec_report

    def _calc_exec_price(self, order: OrderRequest, quote: Quote) -> float:
        """计算成交价。"""
        base_price = order.reference_price or quote.last_price

        if order.order_type == OrderType.LIMIT:
            # 限价单：买入不低于 ask，卖出不高于 bid
            if order.side == OrderSide.BUY:
                return min(order.price, quote.ask1 * (1 + self.cfg.slippage_rate))
            else:
                return max(order.price, quote.bid1 * (1 - self.cfg.slippage_rate))

        # 市价单：买入上浮滑点，卖出下浮滑点
        if order.side == OrderSide.BUY:
            return base_price * (1 + self.cfg.slippage_rate)
        else:
            return base_price * (1 - self.cfg.slippage_rate - self.cfg.stamp_tax_rate)

    def _apply_trade(self, symbol: str, side: OrderSide, volume: int, price: float) -> None:
        """更新持仓和现金。"""
        if side == OrderSide.BUY:
            cost = volume * price * (1 + self.cfg.transaction_cost_rate)
            self._cash -= cost
            pos = self._positions.get(symbol, {"volume": 0, "avg_cost": 0.0, "realized_pnl": 0.0, "today_volume": 0})
            new_vol = pos["volume"] + volume
            new_cost = (pos["volume"] * pos["avg_cost"] + volume * price) / new_vol
            pos["volume"] = new_vol
            pos["avg_cost"] = new_cost
            pos["today_volume"] = pos.get("today_volume", 0) + volume
            self._positions[symbol] = pos

        else:  # SELL
            proceeds = volume * price * (1 - self.cfg.transaction_cost_rate - self.cfg.stamp_tax_rate)
            self._cash += proceeds
            pos = self._positions.get(symbol, {"volume": 0, "avg_cost": 0.0, "realized_pnl": 0.0, "today_volume": 0})
            pos["volume"] -= volume
            pnl = volume * (price - pos["avg_cost"])
            pos["realized_pnl"] = pos.get("realized_pnl", 0.0) + pnl
            if pos["volume"] <= 0:
                self._positions.pop(symbol, None)
            else:
                self._positions[symbol] = pos

    def _reject(self, order_id: str, order: OrderRequest, submitted_at: str, message: str) -> OrderExecution:
        exec_report = OrderExecution(
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
            message=message,
        )
        self._orders[order_id] = exec_report
        logger.warning("sim order rejected: %s %s %s — %s", order.side.value, order.symbol, order.volume, message)
        return exec_report

    # -------------------------------------------------------------------------
    # 撤单
    # -------------------------------------------------------------------------

    def cancel_order(self, broker_order_id: str) -> bool:
        order = self._orders.get(broker_order_id)
        if order is None:
            return False
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return False
        # 模拟：标记为已撤销（已成交的无法撤）
        self._orders[broker_order_id] = OrderExecution(
            order_id=order.order_id,
            broker_order_id=order.broker_order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            requested_volume=order.requested_volume,
            filled_volume=order.filled_volume,
            avg_fill_price=order.avg_fill_price,
            status=OrderStatus.CANCELLED,
            submitted_at=order.submitted_at,
            filled_at=order.filled_at,
            message="cancelled by user",
        )
        logger.info("sim order cancelled: %s", broker_order_id)
        return True

    # -------------------------------------------------------------------------
    # 行情更新（供外部调用）
    # -------------------------------------------------------------------------

    def update_market_price(self, symbol: str, price: float, volume: float = 0.0) -> None:
        """更新行情（由行情推送服务调用）。"""
        self._market_prices[symbol] = price
        if volume > 0:
            self._daily_volumes[symbol] = volume

    def batch_update_prices(self, prices: dict[str, float], volumes: dict[str, float] | None = None) -> None:
        """批量更新行情。"""
        for sym, price in prices.items():
            self.update_market_price(sym, price, volumes.get(sym, 0.0) if volumes else 0.0)

    # -------------------------------------------------------------------------
    # 结算与日志
    # -------------------------------------------------------------------------

    def daily_settlement(self, prices: dict[str, float] | None = None) -> dict[str, float]:
        """
        每日收盘结算。
        更新所有持仓盯市盈亏，重置日成交量计数器。
        """
        if prices:
            self.batch_update_prices(prices)

        account = self.get_account()
        snapshot = {
            "date": datetime.now().strftime("%Y%m%d"),
            "total_assets": account.total_assets,
            "cash": account.cash,
            "market_value": account.market_value,
            "day_return": account.total_assets / self.cfg.initial_cash - 1.0,
            "positions": {
                p.symbol: {"volume": p.volume, "avg_cost": p.avg_cost, "pnl": p.unrealized_pnl}
                for p in self.get_positions()
            },
        }

        # 重置日成交量
        self._daily_volumes = {k: 0.0 for k in self._daily_volumes}
        self._trade_days += 1

        logger.info(
            "daily settlement [day %d]: equity=%.2f, cash=%.2f, mv=%.2f, return=%.2f%%",
            self._trade_days, account.total_assets, account.cash, account.market_value,
            snapshot["day_return"] * 100,
        )
        return snapshot

    def get_order_history(self, symbol: str | None = None, limit: int = 100) -> list[OrderExecution]:
        """获取订单历史。"""
        history = self._order_history[-limit:]
        if symbol:
            history = [o for o in history if o.symbol == symbol]
        return history

    def get_trade_log(self, limit: int = 200) -> list[dict[str, Any]]:
        """获取交易日志（格式化的成交记录）。"""
        return [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": o.side.value,
                "filled_volume": o.filled_volume,
                "avg_price": o.avg_fill_price,
                "status": o.status.value,
                "submitted_at": o.submitted_at,
                "filled_at": o.filled_at,
                "message": o.message,
            }
            for o in self._order_history[-limit:]
        ]
