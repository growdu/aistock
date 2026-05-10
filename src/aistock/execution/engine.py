"""
执行层：信号 → 券商订单。

职责：
- 将 TradeSignal 转换为 OrderRequest
- 批量下单（原子执行）
- 成交回报处理
- 滑点/成本估算
- 执行日志
"""

from __future__ import annotations

import logging
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
from aistock.common.types import SignalAction, TradeSignal
from aistock.config.settings import FileConfig

logger = logging.getLogger(__name__)


@dataclass
class ExecutionReport:
    """执行报告。"""

    trade_date: str
    signals: list[TradeSignal]
    orders: list[OrderExecution]
    fills: list[OrderExecution] = field(default_factory=list)
    rejects: list[OrderExecution] = field(default_factory=list)
    execution_cost: float = 0.0  # 手续费+滑点总额
    total_value_traded: float = 0.0  # 成交总额


class ExecutionEngine:
    """
    执行引擎。

    将策略生成的 TradeSignal 转换为实际订单，
    委托给 BrokerAdapter 执行。
    """

    def __init__(self, broker: BrokerAdapter, file_config: FileConfig) -> None:
        self.broker = broker
        self.cfg = file_config
        self.strategy_cfg = file_config.strategy
        self.risk_cfg = file_config.risk

    def execute_signals(
        self,
        signals: list[TradeSignal],
        trade_date: str | None = None,
        order_type: OrderType = OrderType.MARKET,
    ) -> ExecutionReport:
        """
        执行交易信号。

        Params:
            signals:    策略信号列表
            trade_date: 交易日期（YYYYMMDD）
            order_type: 订单类型（市价单/限价单）
        """
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y%m%d")

        date_str = trade_date

        # 获取账户和持仓
        account = self.broker.get_account()
        positions = {p.symbol: p for p in self.broker.get_positions()}

        # 批量获取行情
        symbols_needed = [s.symbol for s in signals]
        quotes = self.broker.get_quotes(symbols_needed)

        # 构建订单
        orders: list[OrderRequest] = []
        for signal in signals:
            order = self._signal_to_order(signal, account, positions, quotes, order_type)
            if order:
                orders.append(order)

        # 批量执行
        executions: list[OrderExecution] = []
        cost_total = 0.0
        value_total = 0.0

        for order in orders:
            exec_report = self.broker.place_order(order)
            executions.append(exec_report)

            if exec_report.status == OrderStatus.FILLED:
                self._log_fill(exec_report, date_str)
            elif exec_report.status == OrderStatus.REJECTED:
                logger.warning("order rejected: %s %s — %s", exec_report.symbol, exec_report.message, order.comment)

            # 累加成本（使用配置中的费率）
            if exec_report.filled_volume > 0 and exec_report.avg_fill_price:
                vol = exec_report.filled_volume
                price = exec_report.avg_fill_price
                commission = vol * price * self.cfg.portfolio.transaction_cost_rate
                slippage = vol * price * self.cfg.portfolio.slippage_rate
                stamp_tax = (vol * price * 0.001) if exec_report.side == OrderSide.SELL else 0.0
                cost_total += commission + slippage + stamp_tax
                value_total += vol * price

        fills = [e for e in executions if e.status == OrderStatus.FILLED]
        rejects = [e for e in executions if e.status == OrderStatus.REJECTED]

        report = ExecutionReport(
            trade_date=date_str,
            signals=signals,
            orders=executions,
            fills=fills,
            rejects=rejects,
            execution_cost=round(cost_total, 2),
            total_value_traded=round(value_total, 2),
        )

        logger.info(
            "execution report [%s]: signals=%d, orders=%d, fills=%d, rejects=%d, cost=%.2f, value=%.2f",
            date_str, len(signals), len(orders), len(fills), len(rejects), cost_total, value_total,
        )
        return report

    def _signal_to_order(
        self,
        signal: TradeSignal,
        account: AccountInfo,
        positions: dict[str, Position],
        quotes: dict[str, Quote],
        order_type: OrderType,
    ) -> OrderRequest | None:
        """将 TradeSignal 转换为 OrderRequest。"""
        # 获取行情
        quote = quotes.get(signal.symbol)
        if quote is None:
            logger.warning("no quote for %s, skipping", signal.symbol)
            return None

        current_price = quote.last_price
        if current_price <= 0:
            logger.warning("invalid price for %s: %.4f, skipping", signal.symbol, current_price)
            return None

        # 计算股数（100 的整数倍，A股规则）
        target_weight = signal.target_weight
        target_value = account.total_assets * target_weight
        shares = self._calc_shares(target_value, current_price, order_type, quote)

        if shares < 100:
            logger.debug("target shares %d < 100 for %s, skipping", shares, signal.symbol)
            return None

        # 确定方向
        pos = positions.get(signal.symbol)
        current_position_value = pos.volume * pos.last_price if pos else 0.0
        current_weight = current_position_value / account.total_assets if account.total_assets > 0 else 0.0

        if target_weight > current_weight + 0.001:  # 买入
            side = OrderSide.BUY
        elif target_weight < current_weight - 0.001:  # 卖出
            side = OrderSide.SELL
            # 卖出全部
            shares = pos.volume if pos else 0
            if shares <= 0:
                return None
        else:
            logger.debug("weight unchanged for %s (%.4f), skipping", signal.symbol, current_weight)
            return None

        return OrderRequest(
            symbol=signal.symbol,
            side=side,
            volume=shares,
            price=0.0 if order_type == OrderType.MARKET else current_price,
            order_type=order_type,
            reference_price=current_price,
            comment=signal.reason,
        )

    def _calc_shares(
        self,
        target_value: float,
        price: float,
        order_type: OrderType,
        quote: Quote,
    ) -> int:
        """计算下单股数（100 的整数倍，向下取整到整手）。"""
        if price <= 0:
            return 0
        raw_shares = int(target_value / price / 100) * 100
        # 成交量限制：单笔不超过日成交量的 5%（按整手）
        daily_volume = getattr(quote, "volume", 0) or 0
        max_by_volume = int(daily_volume * 0.05 / 100) * 100
        return min(raw_shares, max_by_volume)

    def _log_fill(self, exec_: OrderExecution, trade_date: str) -> None:
        logger.info(
            "[%s] FILLED: %s %s %d @ %.4f (order_id=%s, comment=%s)",
            trade_date, exec_.side.value, exec_.symbol, exec_.filled_volume,
            exec_.avg_fill_price, exec_.order_id, exec_.message,
        )


# =============================================================================
# 便捷函数
# =============================================================================


def create_execution_engine(
    broker: BrokerAdapter,
    file_config: FileConfig,
) -> ExecutionEngine:
    """创建执行引擎。"""
    return ExecutionEngine(broker=broker, file_config=file_config)


def signals_to_order_requests(
    signals: list[TradeSignal],
    broker: BrokerAdapter,
    account: AccountInfo,
    positions: list[Position],
    order_type: OrderType = OrderType.MARKET,
) -> list[OrderRequest]:
    """将信号转换为订单请求（不执行，仅转换）。"""
    pos_dict = {p.symbol: p for p in positions}
    quotes = broker.get_quotes([s.symbol for s in signals])
    engine = ExecutionEngine(broker, FileConfig())
    orders = []
    for sig in signals:
        order = engine._signal_to_order(sig, account, pos_dict, quotes, order_type)
        if order:
            orders.append(order)
    return orders
