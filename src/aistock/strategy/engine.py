"""
策略信号生成引擎。

支持：
- 候选池过滤（市值/流动性/停牌/涨跌停）
- 多因子排序（模型分 + 动量 + 波动率 + 流动性）
- 目标仓位计算（等权 / 按 confidence 加权 / Kelly 上限）
- 止损/止盈信号生成
- 持仓期管理
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from aistock.common.types import Prediction, SignalAction, TradeSignal
from aistock.config.settings import FileConfig

logger = logging.getLogger(__name__)


# =============================================================================
# 过滤器
# =============================================================================


@dataclass
class FilterConfig:
    """候选池过滤器配置。"""

    min_market_cap: float = 10e6  # 最小市值（元），低于此过滤
    min_volume: float = 1e6  # 最小日均成交量（股）
    max_single_position_pct: float = 0.1  # 单股最大仓位比例
    max_concentration_pct: float = 0.3  # 最大持仓集中度（top-N 总仓位上限）
    blacklist: set[str] = field(default_factory=set)  # 黑名单（如涨跌停/停牌）


def _is_in_blacklist(symbol: str, blacklist: set[str]) -> bool:
    return symbol in blacklist


def filter_candidates(
    predictions: list[Prediction],
    latest_prices: dict[str, float] | None = None,
    config: FilterConfig | None = None,
) -> list[Prediction]:
    """
    过滤候选池：
    1. 剔除黑名单
    2. 剔除 confidence <= 0 的预测
    3. 剔除价格 <= 0 或无法获取价格的标的
    """
    if config is None:
        config = FilterConfig()

    filtered: list[Prediction] = []
    for p in predictions:
        if p.confidence <= 0:
            continue
        if _is_in_blacklist(p.symbol, config.blacklist):
            logger.debug("filtered %s: blacklisted", p.symbol)
            continue
        if latest_prices is not None:
            price = latest_prices.get(p.symbol)
            if price is None or price <= 0:
                logger.debug("filtered %s: no valid price", p.symbol)
                continue
        filtered.append(p)

    return filtered


# =============================================================================
# 排序
# =============================================================================


@dataclass
class RankConfig:
    """排序权重配置。"""

    score_weight: float = 1.0  # 模型分权重
    momentum_weight: float = 0.0  # 动量因子权重（预留）
    volatility_weight: float = 0.0  # 波动率因子权重（预留）
    # 最终得分 = score_weight * norm(score) + momentum_weight * norm(momentum) + ...


def rank_signals(
    predictions: list[Prediction],
    config: RankConfig | None = None,
) -> list[Prediction]:
    """
    多因子排序：
    默认仅用模型分排序，支持扩展动量/波动率因子。
    返回按 score 降序排列的列表。
    """
    if config is None:
        config = RankConfig()

    ranked = sorted(predictions, key=lambda p: p.score, reverse=True)
    return ranked


# =============================================================================
# 目标仓位计算
# =============================================================================


@dataclass
class PositionPlan:
    """目标仓位计划。"""

    symbol: str
    action: SignalAction
    target_weight: float  # 0.0 ~ 1.0
    confidence: float
    predicted_return: float
    reason: str
    stop_loss_pct: float | None = None  # 止损线（如 -0.05 表示 -5%）
    take_profit_pct: float | None = None  # 止盈线


def _compute_kelly_fraction(
    predicted_return: float, confidence: float, max_fraction: float = 0.25
) -> float:
    """
    Kelly Criterion 简化版：
    f = p * b - q / b
    其中 p=胜率(confidence), b=赔率(predicted_return/基准), q=1-p
    """
    if confidence <= 0 or predicted_return <= 0:
        return 0.0
    b = predicted_return / max(predicted_return, 0.01)  # 简化为赔率
    p = min(confidence, 0.99)
    q = 1.0 - p
    kelly = p - q / max(b, 0.01)
    return min(max(kelly, 0.0), max_fraction)


def compute_target_positions(
    predictions: list[Prediction],
    file_config: FileConfig,
    position_method: str = "equal",  # "equal" | "confidence" | "kelly"
    max_total_weight: float = 1.0,
    existing_positions: dict[str, float] | None = None,
) -> list[PositionPlan]:
    """
    计算目标仓位。

    Params:
        predictions:     排序后的预测列表
        file_config:     全局配置
        position_method: 仓位分配方式
            equal      - 等权分配（top_n 平分 max_total_weight）
            confidence - 按 confidence 加权
            kelly      - Kelly Criterion 上限
        max_total_weight: 最大总仓位上限（如 0.9 = 留 10% 现金）
        existing_positions: 已有持仓 symbol -> weight
    """
    top_n = file_config.strategy.top_n
    max_single = file_config.risk.max_single_position_pct

    selected = predictions[:top_n]
    if not selected:
        return []

    # 计算各标的权重
    if position_method == "equal":
        base_weight = min(max_total_weight, max_single * len(selected)) / len(selected)
        weights = {p.symbol: base_weight for p in selected}

    elif position_method == "confidence":
        total_conf = sum(p.confidence for p in selected)
        if total_conf <= 0:
            weights = {p.symbol: max_single for p in selected}
        else:
            weights = {
                p.symbol: min(max_single, max_total_weight * p.confidence / total_conf)
                for p in selected
            }

    elif position_method == "kelly":
        weights = {}
        for p in selected:
            kelly_f = _compute_kelly_fraction(
                p.predicted_return, p.confidence, max_fraction=max_single
            )
            weights[p.symbol] = kelly_f
        # 归一化使总权重不超过 max_total_weight
        total_w = sum(weights.values())
        if total_w > max_total_weight:
            for sym in weights:
                weights[sym] *= max_total_weight / total_w

    else:
        weights = {p.symbol: max_single for p in selected}

    # 生成 PositionPlan
    plans: list[PositionPlan] = []
    for p in selected:
        w = weights.get(p.symbol, 0.0)
        if w <= 0:
            continue

        # 判断动作：已有持仓 vs 新买入
        existing_w = (existing_positions or {}).get(p.symbol, 0.0)
        if existing_w <= 0 and p.confidence >= file_config.risk.min_confidence_score:
            action = SignalAction.BUY
        elif existing_w > 0 and w < existing_w:
            action = SignalAction.SELL
        elif existing_w > 0 and w == 0:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD

        reason = (
            f"score={p.score:.3f}, conf={p.confidence:.3f}, "
            f"pred_return={p.predicted_return:.4f}, method={position_method}"
        )

        plans.append(
            PositionPlan(
                symbol=p.symbol,
                action=action,
                target_weight=round(w, 6),
                confidence=p.confidence,
                predicted_return=p.predicted_return,
                reason=reason,
                stop_loss_pct=-0.05,  # 默认 -5% 止损
                take_profit_pct=0.15,  # 默认 +15% 止盈
            )
        )

    return plans


# =============================================================================
# 主入口
# =============================================================================


def generate_signals(
    predictions: list[Prediction],
    file_config: FileConfig,
    latest_prices: dict[str, float] | None = None,
    existing_positions: dict[str, float] | None = None,
    position_method: str = "confidence",
    blacklist: set[str] | None = None,
) -> list[TradeSignal]:
    """
    完整策略流水线：
    1. 候选池过滤
    2. 多因子排序
    3. 目标仓位计算
    4. 转换为 TradeSignal
    """
    # 1. 过滤
    filter_cfg = FilterConfig(blacklist=blacklist or set())
    candidates = filter_candidates(predictions, latest_prices=latest_prices, config=filter_cfg)

    # 2. 排序
    ranked = rank_signals(candidates)

    # 3. 仓位计算
    plans = compute_target_positions(
        predictions=ranked,
        file_config=file_config,
        position_method=position_method,
        existing_positions=existing_positions,
    )

    # 4. 转换为 TradeSignal
    signals: list[TradeSignal] = []
    for plan in plans:
        # 风控模块后续还会调整，这里仅记录初始目标仓位
        signals.append(
            TradeSignal(
                symbol=plan.symbol,
                action=plan.action,
                target_weight=plan.target_weight,
                predicted_return=plan.predicted_return,
                confidence=plan.confidence,
                reason=plan.reason,
            )
        )

    logger.info(
        "generated %d signals from %d candidates: %s",
        len(signals),
        len(predictions),
        [(s.symbol, s.action.value, f"{s.target_weight:.3f}") for s in signals],
    )
    return signals


# =============================================================================
# 持仓期管理（辅助函数，供回测和实盘共用）
# =============================================================================


@dataclass
class PositionTracker:
    """
    持仓状态追踪器。
    用于盘中监控持仓是否触发止损/止盈/最大持仓期。
    """

    positions: dict[str, dict] = field(
        default_factory=dict
    )  # symbol -> {entry_price, entry_date, stop_loss, take_profit}

    def open_position(
        self,
        symbol: str,
        entry_price: float,
        entry_date: str,
        stop_loss_pct: float = -0.05,
        take_profit_pct: float = 0.15,
        max_hold_days: int = 20,
    ) -> None:
        self.positions[symbol] = {
            "entry_price": entry_price,
            "entry_date": entry_date,
            "stop_loss": entry_price * (1 + stop_loss_pct),
            "take_profit": entry_price * (1 + take_profit_pct),
            "max_hold_date": self._add_days(entry_date, max_hold_days),
        }

    def close_position(self, symbol: str) -> None:
        self.positions.pop(symbol, None)

    def check_stop_loss(self, symbol: str, current_price: float) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        return current_price <= pos["stop_loss"]

    def check_take_profit(self, symbol: str, current_price: float) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        return current_price >= pos["take_profit"]

    def check_max_hold(self, symbol: str, current_date: str) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        return current_date >= pos["max_hold_date"]

    @staticmethod
    def _add_days(date_str: str, days: int) -> str:
        from datetime import datetime, timedelta

        d = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=days)
        return d.strftime("%Y%m%d")
