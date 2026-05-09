from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aistock.db.base import Base


class SecurityMaster(Base):
    __tablename__ = "security_master"

    ts_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    board: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TradeCalendar(Base):
    __tablename__ = "trade_calendar"

    exchange: Mapped[str] = mapped_column(String(8), primary_key=True)
    cal_date: Mapped[str] = mapped_column(String(8), primary_key=True)
    is_open: Mapped[str] = mapped_column(String(1))
    pretrade_date: Mapped[str] = mapped_column(String(8), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MarketBar1D(Base):
    __tablename__ = "market_bar_1d"

    ts_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(8), primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyBasic1D(Base):
    __tablename__ = "daily_basic_1d"

    ts_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(8), primary_key=True)
    pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dv_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_mv: Mapped[float | None] = mapped_column(Float, nullable=True)
    circ_mv: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SignalRecord(Base):
    __tablename__ = "signal_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8))
    target_weight: Mapped[float] = mapped_column(Float)
    predicted_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TradeOrder(Base):
    __tablename__ = "trade_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    target_weight: Mapped[float] = mapped_column(Float)
    filled_weight: Mapped[float] = mapped_column(Float, default=0.0)
    requested_notional: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_notional: Mapped[float | None] = mapped_column(Float, nullable=True)
    transaction_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    slippage_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="NEW")
    broker: Mapped[str] = mapped_column(String(32), default="paper")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PortfolioPosition(Base):
    __tablename__ = "portfolio_position"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    position_weight: Mapped[float] = mapped_column(Float, default=0.0)
    allocated_capital: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    source: Mapped[str] = mapped_column(String(32), default="paper")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccountState(Base):
    __tablename__ = "account_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initial_cash: Mapped[float] = mapped_column(Float, default=100000.0)
    available_cash: Mapped[float] = mapped_column(Float, default=100000.0)
    invested_capital: Mapped[float] = mapped_column(Float, default=0.0)
    total_equity: Mapped[float] = mapped_column(Float, default=100000.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    daily_trade_count: Mapped[int] = mapped_column(Integer, default=0)
    last_trade_date: Mapped[str] = mapped_column(String(8), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# 数据层新表
# =============================================================================


class StockBasic(Base):
    """股票基本信息表，每日同步一次即可。"""

    __tablename__ = "stock_basic"

    ts_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    area: Mapped[str] = mapped_column(String(32), default="")
    industry: Mapped[str] = mapped_column(String(64), default="")
    market: Mapped[str] = mapped_column(String(32), default="")
    list_status: Mapped[str] = mapped_column(String(1), default="L")
    list_date: Mapped[str] = mapped_column(String(8), default="")
    delist_date: Mapped[str] = mapped_column(String(8), default="")
    is_hs: Mapped[str] = mapped_column(String(1), default="N")
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FinancialIndicator(Base):
    """财务指标表，按季度更新。"""

    __tablename__ = "financial_indicator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    ann_date: Mapped[str] = mapped_column(String(8))  # 公告日期
    report_date: Mapped[str] = mapped_column(String(8))  # 报告期
    # 盈利能力
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    roe_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    roa: Mapped[float | None] = mapped_column(Float, nullable=True)
    roa2: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 成长能力
    revenue_cagr: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_cagr: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 财务结构
    debt_to_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    quick_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 每股指标
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    bps: Mapped[float | None] = mapped_column(Float, nullable=True)  # 每股净资产
    # 估值
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MarketBar1M(Base):
    """分钟线行情表。"""

    __tablename__ = "market_bar_1m"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_time: Mapped[str] = mapped_column(String(19))  # YYYY-MM-DD HH:MM:SS
    freq: Mapped[str] = mapped_column(String(4))  # 1m/5m/15m/30m/60m
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IndexDaily(Base):
    """指数日线行情（用于市场因子）。"""

    __tablename__ = "index_daily"

    ts_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(8), primary_key=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MoneyFlow(Base):
    """个股资金流向。"""

    __tablename__ = "money_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[str] = mapped_column(String(8))
    buy_sm_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # 小单买入额
    sell_sm_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_md_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # 中单买入额
    sell_md_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_lg_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # 大单买入额
    sell_lg_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_mf_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # 净流入额
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SuspendD(Base):
    """每日停牌记录。"""

    __tablename__ = "suspend_d"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[str] = mapped_column(String(8))
    suspend_type: Mapped[str] = mapped_column(String(16))
    suspend_reason: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LimitListD(Base):
    """涨跌停股票列表。"""

    __tablename__ = "limit_list_d"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[str] = mapped_column(String(8))
    limit_type: Mapped[int] = mapped_column(Integer)  # 1=涨停, 2=跌停
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DisclosureDate(Base):
    """财报披露日期。"""

    __tablename__ = "disclosure_date"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    ann_date: Mapped[str] = mapped_column(String(8))
    report_date: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BlockTrade(Base):
    """大宗交易记录。"""

    __tablename__ = "block_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[str] = mapped_column(String(8))
    price: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    buyer: Mapped[str] = mapped_column(String(128), default="")
    seller: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(32), default="tushare")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
