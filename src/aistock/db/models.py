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


class SignalRecord(Base):
    __tablename__ = "signal_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8))
    target_weight: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
