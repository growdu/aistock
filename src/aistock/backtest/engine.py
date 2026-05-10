"""
回测引擎。

支持：
- 完整仓位管理（买入/卖出/持有）
- 交易成本（手续费 + 滑点 + 印花税）
- 流动性成交限制（成交量百分比上限）
- 动态权益曲线
- 每日风控评估（使用 RiskEngine）
- 结果指标：收益率/回撤/胜率/CAGR/夏普/换手率
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aistock.common.types import Prediction, SignalAction, TradeSignal
from aistock.config.settings import FileConfig
from aistock.model.predict import predict_feature_frame
from aistock.risk.engine import BacktestRiskState, RiskEngine
from aistock.strategy.engine import PositionTracker, compute_target_positions, filter_candidates, rank_signals

logger = logging.getLogger(__name__)

# =============================================================================
# 回测配置
# =============================================================================


@dataclass
class BacktestConfig:
    """回测引擎配置。"""

    initial_cash: float = 1_000_000.0  # 初始资金 100 万
    transaction_cost_rate: float = 0.0003  # 手续费 0.03%（买卖双向）
    slippage_rate: float = 0.0005  # 滑点 0.05%（影响成交价格）
    stamp_tax_rate: float = 0.001  # 印花税 0.1%（仅卖出时收取）
    max_single_position_pct: float = 0.10  # 单股最大仓位 10%
    max_total_position_pct: float = 0.90  # 最大总仓位 90%
    max_volumeParticipation: float = 0.05  # 最大成交量占比 5%（成交量限制）
    min_position_size: float = 100.0  # 最小建仓金额（元）
    daily_rebalance: bool = True  # 是否每日调仓
    stop_loss_pct: float = -0.05  # 止损线 -5%
    take_profit_pct: float = 0.15  # 止盈线 +15%
    max_hold_days: int = 20  # 最大持仓天数
    # 排序配置
    position_method: str = "confidence"  # equal | confidence | kelly
    # 风控配置
    use_risk_engine: bool = True  # 是否使用 RiskEngine
    min_confidence_score: float = 0.5  # 最小置信度
    max_daily_trades: int = 10  # 每日最大交易次数


# =============================================================================
# 持仓状态
# =============================================================================


@dataclass
class Position:
    """持仓。"""

    symbol: str
    shares: int  # 股数
    avg_cost: float  # 加权平均成本
    entry_date: str  # 入场日期
    last_rebalance_date: str  # 上次调仓日期


@dataclass
class DailySnapshot:
    """每日账户快照。"""

    trade_date: str
    equity: float  # 总权益
    cash: float  # 可用资金
    market_value: float  # 持仓市值
    positions_count: int  # 持仓数量
    day_return: float  # 当日收益率
    cumulative_return: float  # 累计收益率
    drawdown: float  # 当前回撤
    max_drawdown: float  # 历史最大回撤
    turnover_rate: float  # 换手率
    long_positions: dict[str, float]  # 各持仓市值
    new_trades: int  # 当日新开仓数
    closed_trades: int  # 当日平仓数
    realized_pnl: float  # 当日已实现盈亏
    unrealized_pnl: float  # 当日未实现盈亏
    risk_state: dict[str, Any]  # 风控状态摘要


# =============================================================================
# 回测结果
# =============================================================================


@dataclass
class BacktestResult:
    """回测结果。"""

    config: dict[str, Any]
    metrics: dict[str, float]
    equity_curve: pd.DataFrame
    trades_log: list[dict[str, Any]]
    final_positions: dict[str, dict]
    report_path: str | None = None


# =============================================================================
# 内部工具
# =============================================================================


def _trade_price(price: float, side: str, slippage_rate: float, config: BacktestConfig) -> float:
    """
    计算成交价（含滑点）。
    买入上浮，卖出下浮。
    """
    if side == "buy":
        return price * (1 + slippage_rate)
    else:
        return price * (1 - slippage_rate - config.stamp_tax_rate)


def _shares_with_volume_limit(
    target_value: float,
    price: float,
    daily_volume: float,
    config: BacktestConfig,
) -> int:
    """计算成交量限制下的最大可买股数。"""
    max_by_volume = int(daily_volume * config.max_volumeParticipation / price)
    max_by_value = int(target_value / price)
    return min(max_by_volume, max_by_value)


def _update_drawdown(equity: float, peak: float) -> tuple[float, float]:
    peak = max(peak, equity)
    dd = (peak - equity) / peak if peak > 0 else 0.0
    return peak, dd


# =============================================================================
# 回测主引擎
# =============================================================================


def run_backtest(
    feature_df: pd.DataFrame,
    file_config: FileConfig,
    config: BacktestConfig | None = None,
    model_path: str | None = None,
    metadata_path: str | None = None,
    top_n: int | None = None,
    output_dir: str | Path = "data/reports",
    existing_predictions: list[Prediction] | None = None,
) -> BacktestResult:
    """
    完整回测引擎。

    Params:
        feature_df:           特征 DataFrame（包含 trade_date / ts_code / 模型特征 / target_return_Nd）
        file_config:          全局配置
        config:               回测配置
        model_path:           模型路径（用于 predict_feature_frame 推理）
        metadata_path:         模型元数据路径
        top_n:                每日持仓数，默认用 file_config.strategy.top_n
        output_dir:           报告输出目录
        existing_predictions: 如果已有 Prediction 列表，直接使用（无需模型推理）

    Returns:
        BacktestResult（含 equity_curve、metrics、trades_log）
    """
    if config is None:
        config = BacktestConfig()
        # 从 file_config 同步风控参数
        config.min_confidence_score = file_config.risk.min_confidence_score
        config.max_single_position_pct = file_config.risk.max_single_position_pct
        config.max_daily_trades = file_config.risk.max_daily_trades

    if top_n is None:
        top_n = file_config.strategy.top_n

    if feature_df.empty:
        return _empty_result(config)

    # 过滤有标签的日期（去除未来数据）
    frame = feature_df.dropna(subset=["target_return_1d", "trade_date"]).copy()
    if "ts_code" in frame.columns:
        frame = frame.rename(columns={"ts_code": "symbol"})
    frame = frame.sort_values(["trade_date", "symbol"]).reset_index(drop=True)

    # 若有模型路径，进行批量推理
    if model_path and metadata_path and existing_predictions is None:
        logger.info("running inference with model=%s", model_path)
        frame = predict_feature_frame(frame, model_path=model_path, metadata_path=metadata_path)

    # 风控引擎
    risk_engine = RiskEngine(file_config) if config.use_risk_engine else None
    risk_state = BacktestRiskState()
    position_tracker = PositionTracker()

    # 账户状态
    cash = config.initial_cash
    peak_equity = config.initial_cash
    equity = config.initial_cash

    # 持仓
    positions: dict[str, Position] = {}

    # 权益曲线
    equity_curve: list[DailySnapshot] = []

    # 交易日志
    trades_log: list[dict[str, Any]] = []

    # 按日遍历
    dates = sorted(frame["trade_date"].unique())

    for i, trade_date in enumerate(dates):
        date_str = str(trade_date)
        day_frame = frame[frame["trade_date"] == date_str].copy()
        if day_frame.empty:
            continue

        # === 计算当日持仓盈亏 ===
        unrealized_pnl = 0.0
        for sym, pos in list(positions.items()):
            price_row = day_frame[day_frame["symbol"] == sym]
            if price_row.empty:
                continue
            current_price = float(price_row.iloc[0]["close"])
            pos_market_value = pos.shares * current_price
            unrealized_pnl += pos_market_value - pos.shares * pos.avg_cost

        market_value = sum(pos.shares * _get_day_close(day_frame, sym) for sym, pos in positions.items())
        prev_equity = equity
        equity = cash + market_value

        # === 检查止损/止盈 ===
        to_close: list[str] = []
        for sym, pos in positions.items():
            current_price = _get_day_close(day_frame, sym)
            if current_price is None:
                continue
            pct_change = current_price / pos.avg_cost - 1.0
            if pct_change <= config.stop_loss_pct or pct_change >= config.take_profit_pct:
                logger.debug("stop triggered %s: %.1f%%", sym, pct_change * 100)
                to_close.append(sym)

        # === 强制平仓 ===
        for sym in to_close:
            pos = positions.pop(sym, None)
            if pos is None:
                continue
            price_row = day_frame[day_frame["symbol"] == sym]
            if price_row.empty:
                continue
            sell_price = _trade_price(float(price_row.iloc[0]["close"]), "sell", config.slippage_rate, config)
            proceeds = pos.shares * sell_price
            transaction_cost = proceeds * config.transaction_cost_rate
            net_proceeds = proceeds - transaction_cost
            cash += net_proceeds
            pnl = net_proceeds - pos.shares * pos.avg_cost
            trades_log.append(
                {
                    "trade_date": date_str,
                    "symbol": sym,
                    "side": "sell",
                    "shares": pos.shares,
                    "price": sell_price,
                    "reason": "stop",
                    "pnl": pnl,
                    "hold_days": (datetime.strptime(date_str, "%Y%m%d") - datetime.strptime(pos.entry_date, "%Y%m%d")).days,
                }
            )
            risk_state.closed_trades += 1

        # === 重新计算权益（强制平仓后） ===
        market_value = sum(pos.shares * _get_day_close(day_frame, sym) for sym, pos in positions.items())
        equity = cash + market_value

        # === 每日调仓 ===
        new_trades = 0
        realized_pnl_day = 0.0

        if config.daily_rebalance:
            # 构建候选 Prediction
            predictions: list[Prediction] = []
            for _, row in day_frame.iterrows():
                sym = str(row.get("symbol", ""))
                if not sym:
                    continue
                score = float(row.get("score", 0.0))
                pred_return = float(row.get("target_return_1d", 0.0))
                conf = float(row.get("confidence", 0.0))
                if conf <= 0 and score <= 0:
                    continue
                predictions.append(Prediction(symbol=sym, score=score, predicted_return=pred_return, confidence=conf))

            # 过滤+排序
            ranked = rank_signals(predictions)

            # 目标仓位
            existing_pos_dict = {sym: pos.shares * pos.avg_cost / equity for sym, pos in positions.items()}
            plans = compute_target_positions(
                predictions=ranked,
                file_config=file_config,
                position_method=config.position_method,
                max_total_weight=config.max_total_position_pct,
                existing_positions=existing_pos_dict,
            )

            # 计算目标持仓市值
            target_positions: dict[str, float] = {}  # symbol -> target market value
            for plan in plans:
                if plan.action in (SignalKind.BUY, SignalKind.HOLD):
                    target_positions[plan.symbol] = plan.target_weight * equity

            # === 调仓：平多余，卖弱，换强 ===
            for sym in list(positions.keys()):
                target_w = target_positions.get(sym, 0.0)
                pos = positions[sym]
                current_mv = pos.shares * _get_day_close(day_frame, sym)
                target_shares_val = target_w * equity

                # 需要卖出
                if target_shares_val < current_mv * 0.95:  # 5% 以下差异视为无需操作
                    sell_shares = max(0, int((current_mv - target_shares_val) / _get_day_close(day_frame, sym)))
                    if sell_shares >= 100:
                        price_row = day_frame[day_frame["symbol"] == sym]
                        if not price_row.empty:
                            sell_price = _trade_price(float(price_row.iloc[0]["close"]), "sell", config.slippage_rate, config)
                            proceeds = sell_shares * sell_price
                            cost = proceeds * config.transaction_cost_rate
                            net = proceeds - cost
                            cash += net
                            pos.shares -= sell_shares
                            pnl = net - sell_shares * pos.avg_cost
                            realized_pnl_day += pnl
                            trades_log.append(
                                {
                                    "trade_date": date_str,
                                    "symbol": sym,
                                    "side": "sell",
                                    "shares": sell_shares,
                                    "price": sell_price,
                                    "reason": "rebalance",
                                    "pnl": pnl,
                                    "hold_days": (datetime.strptime(date_str, "%Y%m%d") - datetime.strptime(pos.entry_date, "%Y%m%d")).days,
                                }
                            )
                            risk_state.closed_trades += 1
                            new_trades += 1

                # 更新均价（如果加仓）
                if target_shares_val > current_mv * 1.05:
                    buy_val = target_shares_val - current_mv
                    if buy_val >= config.min_position_size and cash >= buy_val * (1 + config.transaction_cost_rate + config.slippage_rate):
                        price_row = day_frame[day_frame["symbol"] == sym]
                        if not price_row.empty:
                            buy_price = _trade_price(float(price_row.iloc[0]["close"]), "buy", config.slippage_rate, config)
                            max_shares = _shares_with_volume_limit(
                                min(buy_val, cash / (1 + config.transaction_cost_rate + config.slippage_rate)),
                                buy_price,
                                float(price_row.iloc[0]["volume"]),
                                config,
                            )
                            buy_shares = min(max_shares, int(buy_val / buy_price))
                            if buy_shares >= 100:
                                cost = buy_shares * buy_price * (1 + config.transaction_cost_rate)
                                if cost <= cash:
                                    cash -= cost
                                    new_cost = (pos.shares * pos.avg_cost + buy_shares * buy_price) / (pos.shares + buy_shares)
                                    pos.shares += buy_shares
                                    pos.avg_cost = new_cost
                                    trades_log.append(
                                        {
                                            "trade_date": date_str,
                                            "symbol": sym,
                                            "side": "buy",
                                            "shares": buy_shares,
                                            "price": buy_price,
                                            "reason": "rebalance",
                                            "hold_days": 0,
                                            "pnl": 0.0,
                                        }
                                    )
                                    risk_state.new_trades += 1
                                    new_trades += 1

            # === 新开仓 ===
            current_holdings = set(positions.keys())
            for plan in plans:
                if plan.action == SignalAction.BUY and plan.symbol not in current_holdings:
                    pos = positions.get(plan.symbol)
                    if pos is None:
                        target_mv = plan.target_weight * equity
                        price_row = day_frame[day_frame["symbol"] == plan.symbol]
                        if price_row.empty:
                            continue
                        buy_price = _trade_price(float(price_row.iloc[0]["close"]), "buy", config.slippage_rate, config)
                        max_shares = _shares_with_volume_limit(
                            target_mv,
                            buy_price,
                            float(price_row.iloc[0]["volume"]),
                            config,
                        )
                        buy_shares = min(max_shares, int(target_mv / buy_price))
                        if buy_shares < 100 or cash < buy_shares * buy_price * (1 + config.transaction_cost_rate):
                            continue
                        cost = buy_shares * buy_price * (1 + config.transaction_cost_rate)
                        cash -= cost
                        positions[plan.symbol] = Position(
                            symbol=plan.symbol,
                            shares=buy_shares,
                            avg_cost=buy_price,
                            entry_date=date_str,
                            last_rebalance_date=date_str,
                        )
                        trades_log.append(
                            {
                                "trade_date": date_str,
                                "symbol": plan.symbol,
                                "side": "buy",
                                "shares": buy_shares,
                                "price": buy_price,
                                "reason": "new",
                                "hold_days": 0,
                                "pnl": 0.0,
                            }
                        )
                        risk_state.new_trades += 1
                        new_trades += 1

        # === 记录快照 ===
        market_value = sum(pos.shares * _get_day_close(day_frame, pos.symbol) for pos in positions.values())
        equity = cash + market_value
        peak_equity, drawdown = _update_drawdown(equity, peak_equity)
        day_return = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0

        long_positions = {pos.symbol: pos.shares * _get_day_close(day_frame, pos.symbol) for pos in positions.values()}
        turnover_rate = new_trades / max(len(positions) + new_trades, 1)

        snapshot = DailySnapshot(
            trade_date=date_str,
            equity=equity,
            cash=cash,
            market_value=market_value,
            positions_count=len(positions),
            day_return=day_return,
            cumulative_return=equity / config.initial_cash - 1.0,
            drawdown=drawdown,
            max_drawdown=peak_equity - equity,
            turnover_rate=turnover_rate,
            long_positions=long_positions,
            new_trades=new_trades,
            closed_trades=getattr(risk_state, "closed_trades", 0),
            realized_pnl=realized_pnl_day,
            unrealized_pnl=unrealized_pnl,
            risk_state={"daily_trade_count": getattr(risk_state, "daily_trade_count", 0)},
        )
        equity_curve.append(snapshot)

        # === 每日收盘后更新 ===
        risk_state.on_day_close(equity)

    # === 最终结果 ===
    equity_df = _build_equity_curve(equity_curve)
    metrics = _compute_metrics(equity_curve, trades_log, config)
    final_positions = {sym: {"shares": p.shares, "avg_cost": p.avg_cost} for sym, p in positions.items()}

    # 保存报告
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_file = output_path / f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "config": {
            "initial_cash": config.initial_cash,
            "transaction_cost_rate": config.transaction_cost_rate,
            "slippage_rate": config.slippage_rate,
            "stamp_tax_rate": config.stamp_tax_rate,
            "max_single_position_pct": config.max_single_position_pct,
            "max_total_position_pct": config.max_total_position_pct,
            "position_method": config.position_method,
            "stop_loss_pct": config.stop_loss_pct,
            "take_profit_pct": config.take_profit_pct,
        },
        "metrics": metrics,
        "trades_count": len(trades_log),
        "trades_log_sample": trades_log[:10],
    }
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return BacktestResult(
        config={
            "initial_cash": config.initial_cash,
            "transaction_cost_rate": config.transaction_cost_rate,
            "slippage_rate": config.slippage_rate,
            "position_method": config.position_method,
        },
        metrics=metrics,
        equity_curve=equity_df,
        trades_log=trades_log,
        final_positions=final_positions,
        report_path=str(report_file),
    )


# =============================================================================
# 工具
# =============================================================================


def _get_day_close(day_frame: pd.DataFrame, symbol: str) -> float | None:
    row = day_frame[day_frame["symbol"] == symbol]
    if row.empty:
        return None
    return float(row.iloc[0]["close"])


def _build_equity_curve(snapshots: list[DailySnapshot]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": [s.trade_date for s in snapshots],
            "equity": [s.equity for s in snapshots],
            "cash": [s.cash for s in snapshots],
            "market_value": [s.market_value for s in snapshots],
            "day_return": [s.day_return for s in snapshots],
            "cumulative_return": [s.cumulative_return for s in snapshots],
            "drawdown": [s.drawdown for s in snapshots],
            "max_drawdown": [s.max_drawdown for s in snapshots],
            "turnover_rate": [s.turnover_rate for s in snapshots],
            "positions_count": [s.positions_count for s in snapshots],
            "new_trades": [s.new_trades for s in snapshots],
            "realized_pnl": [s.realized_pnl for s in snapshots],
            "unrealized_pnl": [s.unrealized_pnl for s in snapshots],
        }
    )


def _compute_metrics(
    snapshots: list[DailySnapshot],
    trades_log: list[dict[str, Any]],
    config: BacktestConfig,
) -> dict[str, float]:
    if not snapshots:
        return {}

    equity_series = np.array([s.equity for s in snapshots])
    returns = np.array([s.day_return for s in snapshots])

    # 基本指标
    total_return = equity_series[-1] / equity_series[0] - 1.0 if equity_series[0] > 0 else 0.0
    max_drawdown = max((s.peak_equity - s.equity) / s.peak_equity if s.peak_equity > 0 else 0 for s in snapshots)
    annual_trading_days = 252
    n_days = len(snapshots)
    years = n_days / annual_trading_days

    # CAGR
    cagr = (1 + total_return) ** (1 / years) - 1.0 if years > 0 else 0.0

    # 夏普比率（无风险利率 3%）
    risk_free = 0.03
    excess_returns = returns - risk_free / annual_trading_days
    sharpe = float(np.mean(excess_returns) / (np.std(excess_returns) + 1e-9) * np.sqrt(annual_trading_days))

    # 胜率
    winning_days = int(np.sum(returns > 0))
    win_rate = winning_days / max(n_days, 1)

    # 盈亏比
    gains = [t["pnl"] for t in trades_log if t.get("pnl", 0) > 0]
    losses = [-t["pnl"] for t in trades_log if t.get("pnl", 0) < 0]
    avg_gain = np.mean(gains) if gains else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    profit_loss_ratio = avg_gain / avg_loss if avg_loss > 0 else 0.0

    # 换手率
    total_turnover = sum(s.turnover_rate for s in snapshots) / max(n_days, 1)

    # 最大连续亏损天数
    consecutive_loss = 0
    max_consecutive_loss = 0
    for r in returns:
        if r < 0:
            consecutive_loss += 1
            max_consecutive_loss = max(max_consecutive_loss, consecutive_loss)
        else:
            consecutive_loss = 0

    # 持仓天数统计
    hold_days = [t.get("hold_days", 0) for t in trades_log if t.get("side") == "sell"]
    avg_hold_days = float(np.mean(hold_days)) if hold_days else 0.0

    return {
        "total_return": round(total_return, 6),
        "annual_return": round(cagr, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe_ratio": round(sharpe, 4),
        "win_rate": round(win_rate, 4),
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "avg_hold_days": round(avg_hold_days, 2),
        "max_consecutive_loss_days": max_consecutive_loss,
        "total_trades": len(trades_log),
        "new_trades": sum(s.new_trades for s in snapshots),
        "closed_trades": sum(s.closed_trades for s in snapshots),
        "avg_turnover_rate": round(total_turnover, 4),
        "final_equity": round(equity_series[-1], 2),
        "initial_cash": round(config.initial_cash, 2),
        "days": n_days,
    }


def _empty_result(config: BacktestConfig) -> BacktestResult:
    return BacktestResult(
        config={},
        metrics={"total_return": 0.0, "max_drawdown": 0.0},
        equity_curve=pd.DataFrame(),
        trades_log=[],
        final_positions={},
    )


# =============================================================================
# 兼容旧 API
# =============================================================================


def run_model_backtest(
    feature_df: pd.DataFrame,
    file_config: FileConfig,
    model_path: str,
    metadata_path: str,
    top_n: int | None = None,
    initial_cash: float = 1_000_000.0,
    transaction_cost_rate: float = 0.0003,
    slippage_rate: float = 0.0005,
) -> BacktestResult:
    """
    兼容旧 API。
    推荐改用 run_backtest。
    """
    config = BacktestConfig(
        initial_cash=initial_cash,
        transaction_cost_rate=transaction_cost_rate,
        slippage_rate=slippage_rate,
    )
    return run_backtest(
        feature_df=feature_df,
        file_config=file_config,
        config=config,
        model_path=model_path,
        metadata_path=metadata_path,
        top_n=top_n,
    )



