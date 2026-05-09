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
