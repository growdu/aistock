"""
券商适配器抽象层。

BrokerAdapter 是所有券商实现的统一接口：
- place_order()    — 下单
- cancel_order()    — 撤单
- get_positions()  — 持仓查询
- get_account()    — 账户信息
- get_quote()      — 行情查询

提供两个内置实现：
- SimBroker  — 模拟交易（基于内存，支持完整持仓/权益追踪）
- QMTBroker — QMT 实盘（通过 xtquant 接入）
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# 数据类型
# =============================================================================


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MKT"  # 市价单
    LIMIT = "LMT"  # 限价单


class OrderStatus(str, Enum):
    PENDING = "PENDING"  # 待成交
    PARTIAL = "PARTIAL"  # 部分成交
    FILLED = "FILLED"  # 全部成交
    CANCELLED = "CANCELLED"  # 已撤销
    REJECTED = "REJECTED"  # 拒绝


@dataclass(slots=True)
class OrderRequest:
    """下单请求。"""

    symbol: str  # 证券代码，如 "300750.SZ"
    side: OrderSide
    volume: int = 0  # 股数（100 的整数倍）
    price: float = 0.0  # 限价（0 表示市价）
    order_type: OrderType = OrderType.MARKET
    reference_price: float | None = None  # 参考价格（用于市价单滑点计算）
    comment: str = ""  # 备注/原因


@dataclass(slots=True)
class OrderExecution:
    """订单执行报告。"""

    order_id: str
    broker_order_id: str | None  # 券商订单号
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_volume: int
    filled_volume: int
    avg_fill_price: float | None
    status: OrderStatus
    submitted_at: str
    filled_at: str | None = None
    message: str = ""


@dataclass(slots=True)
class Position:
    """持仓信息。"""

    symbol: str
    volume: int  # 持股数
    avg_cost: float  # 加权平均成本
    last_price: float  # 最新价
    market_value: float  # 市值
    unrealized_pnl: float  # 未实现盈亏
    realized_pnl: float = 0.0  # 已实现盈亏
    today_volume: int = 0  # 今日买入量


@dataclass(slots=True)
class AccountInfo:
    """账户信息。"""

    account_id: str
    total_assets: float  # 总资产
    cash: float  # 可用资金
    market_value: float  # 持仓市值
    frozen_cash: float  # 冻结资金
    margin_used: float = 0.0  # 保证金占用
    available_cash: float = 0.0  # 可用资金（冗余字段，兼容）
    equity: float = 0.0  # 实时权益（= total_assets）


@dataclass(slots=True)
class Quote:
    """行情快照。"""

    symbol: str
    last_price: float
    open: float
    high: float
    low: float
    volume: float
    amount: float  # 成交额
    bid1: float = 0.0
    ask1: float = 0.0
    timestamp: str = ""


# =============================================================================
# 券商适配器协议
# =============================================================================


class BrokerAdapter(ABC):
    """
    券商适配器抽象基类。

    所有实盘/模拟券商均实现此接口。
    """

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderExecution:
        """提交订单。"""
        ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        """撤销订单。返回是否成功。"""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """查询当前持仓。"""
        ...

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """查询账户信息。"""
        ...

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote | None:
        """查询单个标的实时行情。"""
        ...

    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """批量查询实时行情。"""
        ...

    @abstractmethod
    def is_trading_day(self, date: str | None = None) -> bool:
        """检查是否为交易日。"""
        ...

    @abstractmethod
    def is_market_open(self) -> bool:
        """检查当前是否在交易时间内。"""
        ...

    @property
    @abstractmethod
    def broker_type(self) -> str:
        """券商类型标识：sim / qmt / gf / os"。"""
        ...
