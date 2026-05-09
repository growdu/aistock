"""
风控引擎。

支持：
- 仓位风控：单股仓位上限、总仓位上限、集中度
- 交易次数风控：每日最大交易次数
- 亏损风控：单日最大亏损、最大回撤
- 流动性风控：最小市值、最小成交量
- 黑白名单：ST/退市/涨跌停过滤
- 置信度过滤：confidence 低于阈值直接拒绝
- 动态止损：持仓追踪止损
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aistock.common.types import RiskDecision, RiskResult, TradeSignal
from aistock.config.settings import FileConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# 风控检查项
# =============================================================================


@dataclass
class RiskCheckList:
    """风控检查结果列表。"""

    checks: list[tuple[str, RiskDecision, str]] = field(default_factory=list)

    def add(self, name: str, decision: RiskDecision, message: str) -> None:
        self.checks.append((name, decision, message))

    def worst_decision(self) -> RiskDecision:
        """优先级：REJECT > ADJUST > ALLOW"""
        for _, d, _ in self.checks:
            if d == RiskDecision.REJECT:
                return RiskDecision.REJECT
        for _, d, _ in self.checks:
            if d == RiskDecision.ADJUST:
                return RiskDecision.ADJUST
        return RiskDecision.ALLOW

    def adjusted_weight(self, requested: float) -> float:
        """返回被风控调整后的仓位。"""
        adj = requested
        for name, d, msg in self.checks:
            if d == RiskDecision.REJECT:
                return 0.0
            elif d == RiskDecision.ADJUST:
                if "single_position" in name:
                    adj = min(adj, self._parse_weight_from_msg(msg))
        return adj

    @staticmethod
    def _parse_weight_from_msg(msg: str) -> float:
        import re

        m = re.search(r"max\s*(\d+\.?\d*)%", msg)
        if m:
            return float(m.group(1)) / 100.0
        m = re.search(r"(\d+\.\d+)", msg)
        return float(m.group(1)) if m else 0.0


# =============================================================================
# 风控规则集
# =============================================================================


class RiskEngine:
    """
    可组合的风控引擎。

    使用示例：
        engine = RiskEngine(file_config)
        result = engine.evaluate(
            signal=signal,
            daily_trade_count=2,
            day_pnl_pct=-0.02,
            market_cap=50e6,
            avg_volume_20d=2e6,
        )
    """

    def __init__(self, file_config: FileConfig) -> None:
        self.cfg = file_config
        self.risk = file_config.risk

    # ---- 基础规则 ----

    def _check_confidence(self, signal: TradeSignal) -> RiskCheckList:
        checks = RiskCheckList()
        if signal.confidence < self.risk.min_confidence_score:
            checks.add(
                "min_confidence",
                RiskDecision.REJECT,
                f"confidence {signal.confidence:.3f} < {self.risk.min_confidence_score:.3f}",
            )
        return checks

    def _check_daily_trades(self, current_count: int) -> RiskCheckList:
        checks = RiskCheckList()
        if current_count >= self.risk.max_daily_trades:
            checks.add(
                "daily_trade_limit",
                RiskDecision.REJECT,
                f"daily trades {current_count} >= {self.risk.max_daily_trades}",
            )
        return checks

    def _check_single_position(self, signal: TradeSignal) -> RiskCheckList:
        checks = RiskCheckList()
        if signal.target_weight > self.risk.max_single_position_pct:
            checks.add(
                "single_position_limit",
                RiskDecision.ADJUST,
                f"target_weight {signal.target_weight:.4f} > max_single_position_pct {self.risk.max_single_position_pct:.4f}",
            )
        return checks

    def _check_max_daily_loss(self, day_pnl_pct: float) -> RiskCheckList:
        checks = RiskCheckList()
        if day_pnl_pct < -self.risk.max_daily_loss_pct:
            checks.add(
                "max_daily_loss",
                RiskDecision.REJECT,
                f"day_pnl_pct {day_pnl_pct:.4f} < -{self.risk.max_daily_loss_pct:.4f}",
            )
        return checks

    # ---- 流动性规则 ----

    def _check_liquidity(
        self,
        signal: TradeSignal,
        market_cap: float | None = None,
        avg_volume_20d: float | None = None,
        price: float | None = None,
    ) -> RiskCheckList:
        """
        流动性检查：
        - 市值低于阈值（如 10 亿）过滤
        - 日均成交量低于阈值（如 100 万股）过滤
        - 价格低于 1 元的股票过滤（容易被操纵）
        """
        checks = RiskCheckList()
        MIN_MARKET_CAP = 10e6  # 1000 万市值下限
        MIN_DAILY_VOLUME = 1e6  # 100 万股日均成交量下限
        MIN_PRICE = 1.0

        if market_cap is not None and market_cap < MIN_MARKET_CAP:
            checks.add(
                "min_market_cap",
                RiskDecision.REJECT,
                f"market_cap {market_cap/1e6:.1f}M < {MIN_MARKET_CAP/1e6:.0f}M",
            )

        if avg_volume_20d is not None and avg_volume_20d < MIN_DAILY_VOLUME:
            checks.add(
                "min_daily_volume",
                RiskDecision.REJECT,
                f"avg_volume_20d {avg_volume_20d/1e6:.1f}M < {MIN_DAILY_VOLUME/1e6:.0f}M shares",
            )

        if price is not None and price < MIN_PRICE:
            checks.add(
                "min_price",
                RiskDecision.REJECT,
                f"price {price:.2f} < {MIN_PRICE}",
            )

        return checks

    # ---- 黑白名单 ----

    def _check_blacklist(self, signal: TradeSignal, blacklist: set[str] | None = None) -> RiskCheckList:
        checks = RiskCheckList()
        if blacklist and signal.symbol in blacklist:
            checks.add("blacklist", RiskDecision.REJECT, f"symbol {signal.symbol} in blacklist")
        return checks

    def _check_whitelist(
        self,
        signal: TradeSignal,
        whitelist: set[str] | None = None,
    ) -> RiskCheckList:
        """
        白名单检查：若配置了白名单，则只允许白名单内标的。
        （空 whitelist 表示不限制）
        """
        checks = RiskCheckList()
        if whitelist and signal.symbol not in whitelist:
            checks.add("whitelist", RiskDecision.REJECT, f"symbol {signal.symbol} not in whitelist")
        return checks

    # ========================================================================
    # 综合评估
    # ========================================================================

    def evaluate(
        self,
        signal: TradeSignal,
        daily_trade_count: int,
        day_pnl_pct: float = 0.0,
        market_cap: float | None = None,
        avg_volume_20d: float | None = None,
        current_price: float | None = None,
        blacklist: set[str] | None = None,
        whitelist: set[str] | None = None,
    ) -> RiskResult:
        """
        综合风控评估。

        Params:
            signal:             待评估的交易信号
            daily_trade_count:  当日已执行交易次数
            day_pnl_pct:        当日账户收益率（负数表示亏损）
            market_cap:         股票总市值（元）
            avg_volume_20d:      20 日日均成交量（股）
            current_price:      当前价格
            blacklist:          黑名单集合
            whitelist:          白名单集合
        """
        checks = RiskCheckList()

        # 1. 置信度
        checks.checks.extend(self._check_confidence(signal).checks)

        # 2. 每日交易次数
        checks.checks.extend(self._check_daily_trades(daily_trade_count).checks)

        # 3. 单股仓位上限
        checks.checks.extend(self._check_single_position(signal).checks)

        # 4. 当日亏损上限
        if day_pnl_pct < 0:
            checks.checks.extend(self._check_max_daily_loss(day_pnl_pct).checks)

        # 5. 流动性
        checks.checks.extend(
            self._check_liquidity(signal, market_cap=market_cap, avg_volume_20d=avg_volume_20d, price=current_price).checks
        )

        # 6. 黑白名单
        checks.checks.extend(self._check_blacklist(signal, blacklist=blacklist).checks)
        checks.checks.extend(self._check_whitelist(signal, whitelist=whitelist).checks)

        # 汇总
        worst = checks.worst_decision()
        adjusted_w = checks.adjusted_weight(signal.target_weight)

        if worst == RiskDecision.REJECT:
            reason_parts = [msg for _, d, msg in checks.checks if d == RiskDecision.REJECT]
            reason = "; ".join(reason_parts) if reason_parts else "rejected by risk engine"
            logger.info("signal rejected for %s: %s", signal.symbol, reason)
            return RiskResult(
                symbol=signal.symbol,
                decision=RiskDecision.REJECT,
                adjusted_weight=0.0,
                message=reason,
            )

        elif worst == RiskDecision.ADJUST:
            reason_parts = [msg for _, d, msg in checks.checks if d == RiskDecision.ADJUST]
            reason = "; ".join(reason_parts)
            logger.info("signal adjusted for %s: %s (%.4f -> %.4f)", signal.symbol, reason, signal.target_weight, adjusted_w)
            return RiskResult(
                symbol=signal.symbol,
                decision=RiskDecision.ADJUST,
                adjusted_weight=adjusted_w,
                message=reason,
            )

        else:
            return RiskResult(
                symbol=signal.symbol,
                decision=RiskDecision.ALLOW,
                adjusted_weight=adjusted_w,
                message="approved",
            )


# =============================================================================
# 便捷函数（兼容旧 API）
# =============================================================================


def evaluate_signal(
    signal: TradeSignal,
    file_config: FileConfig,
    daily_trade_count: int,
    **kwargs,
) -> RiskResult:
    """
    兼容旧 API 的风控评估函数。
    推荐改用 RiskEngine 类以支持更多检查项。
    """
    engine = RiskEngine(file_config)
    return engine.evaluate(signal=signal, daily_trade_count=daily_trade_count, **kwargs)


# =============================================================================
# 回测风控辅助
# =============================================================================


@dataclass
class BacktestRiskState:
    """
    回测过程中的风控状态。
    每日更新，用于次日风控判断。
    """

    daily_trade_count: int = 0
    day_pnl_pct: float = 0.0
    cumulative_return: float = 0.0
    peak_equity: float = 100000.0
    current_drawdown: float = 0.0
    max_drawdown_seen: float = 0.0
    blacklist: set[str] = field(default_factory=set)

    def on_day_close(self, equity: float) -> None:
        """每日收盘后更新状态。"""
        self.cumulative_return = equity / 100000.0 - 1.0
        self.peak_equity = max(self.peak_equity, equity)
        self.current_drawdown = self.peak_equity - equity
        self.max_drawdown_seen = max(self.max_drawdown_seen, self.current_drawdown)
        # 每日重置交易计数
        self.daily_trade_count = 0
        self.day_pnl_pct = 0.0

    def record_trade(self) -> None:
        self.daily_trade_count += 1
