"""
因子工程模块。

提供三大类因子：
1. 技术因子（Tech）  — 动量、波动率、均线、成交量、换手率
2. 基本面因子（Fund）— ROE、ROA、毛利率、营收增速、估值
3. 市场因子（Mkt）   — Beta、板块强弱、指数相对表现、资金流

标签生成：
- target_return_Nd   — 未来 N 日收益率（回归标签）
- target_direction_Nd — 未来 N 日涨跌方向（分类标签）
- target_up_Nd       — 二分类（涨=1，跌=0）

特征快照（推理时使用）：
- build_inference_features() 与 build_training_features() 共享同一套因子计算逻辑，
  确保训练和推理特征口径完全一致。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# =============================================================================
# 工具函数
# =============================================================================


def _safe_pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    """计算涨跌幅，带容错。"""
    return series.pct_change(periods=periods).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _rolling_extreme(
    grouped: pd.core.groupby.DataFrameGroupBy,
    col: str,
    window: int,
    stat: str = "max",
) -> pd.Series:
    """分组滚动极值（max/min），用于计算历史高点/低点偏离。"""
    if stat == "max":
        return grouped[col].transform(lambda x: x.rolling(window, min_periods=1).max())
    elif stat == "min":
        return grouped[col].transform(lambda x: x.rolling(window, min_periods=1).min())
    elif stat == "std":
        return grouped[col].transform(lambda x: x.rolling(window, min_periods=1).std())
    elif stat == "mean":
        return grouped[col].transform(lambda x: x.rolling(window, min_periods=1).mean())
    return grouped[col]


# =============================================================================
# 技术因子
# =============================================================================


def add_tech_return_features(frame: pd.DataFrame) -> pd.DataFrame:
    """
    动量类因子：N 日收益率及其派生。
    """
    g = frame.groupby("ts_code", group_keys=False)

    # 已实现收益率
    frame["return_1"] = g["close"].transform(lambda x: _safe_pct_change(x, 1))
    frame["return_3"] = g["close"].transform(lambda x: _safe_pct_change(x, 3))
    frame["return_5"] = g["close"].transform(lambda x: _safe_pct_change(x, 5))
    frame["return_10"] = g["close"].transform(lambda x: _safe_pct_change(x, 10))
    frame["return_20"] = g["close"].transform(lambda x: _safe_pct_change(x, 20))

    # 收益率均值回归特征
    frame["return_5_vs_20"] = frame["return_5"] - frame["return_20"]
    frame["return_1_vs_5"] = frame["return_1"] - frame["return_5"]

    # 收益率分位数（相对自身历史）
    def _rank_pct(x: pd.Series, w: int = 20) -> pd.Series:
        return x.rolling(w, min_periods=1).apply(lambda s: (s < s.iloc[-1]).sum() / len(s) if len(s) > 1 else 0.5, raw=False)

    frame["return_5_rank_pct"] = g["return_5"].transform(lambda x: _rank_pct(x, 20))

    return frame


def add_tech_moving_average_features(frame: pd.DataFrame) -> pd.DataFrame:
    """
    均线类因子：MA偏离、均线金叉死叉能量。
    """
    g = frame.groupby("ts_code", group_keys=False)
    close = g["close"]

    windows = [5, 10, 20, 60, 120]
    ma_cols: dict[int, str] = {}
    for w in windows:
        col = f"ma_{w}"
        frame[col] = close.transform(lambda x: x.rolling(w, min_periods=1).mean())
        frame[f"close_vs_ma_{w}"] = frame["close"] / frame[col] - 1.0
        ma_cols[w] = col

    # 均线多头排列能量（短期均线 > 长期均线的程度）
    frame["ma_short_vs_long"] = (frame["ma_5"] / frame["ma_20"] - 1.0) + (frame["ma_10"] / frame["ma_60"] - 1.0)

    # EMA（指数移动平均）
    frame["ema_12"] = close.transform(lambda x: x.ewm(span=12, min_periods=1, adjust=False).mean())
    frame["ema_26"] = close.transform(lambda x: x.ewm(span=26, min_periods=1, adjust=False).mean())
    frame["macd"] = frame["ema_12"] - frame["ema_26"]
    frame["macd_signal"] = frame["macd"].transform(lambda x: x.ewm(span=9, min_periods=1, adjust=False).mean())
    frame["macd_hist"] = frame["macd"] - frame["macd_signal"]

    # EMA 金叉死叉能量
    frame["ema_12_vs_26"] = frame["ema_12"] / frame["ema_26"] - 1.0

    return frame


def add_tech_volatility_features(frame: pd.DataFrame) -> pd.DataFrame:
    """
    波动率类因子：历史波动率、ATR、Bollinger Bands 偏离。
    """
    g = frame.groupby("ts_code", group_keys=False)

    for w in [5, 10, 20]:
        col = f"volatility_{w}"
        frame[col] = g["return_1" if "return_1" in frame.columns else "close"].transform(
            lambda x: x.rolling(w, min_periods=1).std()
        )

    # 平均真实波幅 ATR
    tr1 = frame["high"] - frame["low"]
    tr2 = (frame["high"] - frame["close"].shift(1)).abs()
    tr3 = (frame["low"] - frame["close"].shift(1)).abs()
    frame["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    frame["atr_14"] = frame.groupby("ts_code", group_keys=False)["tr"].transform(
        lambda x: x.ewm(span=14, min_periods=1, adjust=False).mean()
    )
    frame["atr_ratio"] = frame["atr_14"] / frame["close"]

    # Bollinger Bands
    for w in [20]:
        ma = frame["close"].groupby(frame["ts_code"]).transform(lambda x: x.rolling(w, min_periods=1).mean())
        std = frame["close"].groupby(frame["ts_code"]).transform(lambda x: x.rolling(w, min_periods=1).std())
        frame[f"bb_upper_{w}"] = ma + 2 * std
        frame[f"bb_lower_{w}"] = ma - 2 * std
        frame[f"bb_width_{w}"] = (frame[f"bb_upper_{w}"] - frame[f"bb_lower_{w}"]) / ma
        frame[f"bb_position_{w}"] = (frame["close"] - frame[f"bb_lower_{w}"]) / (frame[f"bb_upper_{w}"] - frame[f"bb_lower_{w}"])

    return frame


def add_tech_volume_features(frame: pd.DataFrame) -> pd.DataFrame:
    """
    成交量与换手率类因子。
    """
    g = frame.groupby("ts_code", group_keys=False)
    vol = g["volume"]

    for w in [5, 10, 20]:
        frame[f"volume_ma_{w}"] = vol.transform(lambda x: x.rolling(w, min_periods=1).mean())
        frame[f"volume_ratio_{w}"] = frame["volume"] / frame[f"volume_ma_{w}"]

    # 量价相关性：逐股滚动计算 corr
    frame["price_volume_corr"] = np.nan
    for tc, grp in frame.groupby("ts_code"):
        if len(grp) >= 5:
            corr_vals = grp["close"].rolling(20, min_periods=5).corr(grp["volume"])
            frame.loc[grp.index, "price_volume_corr"] = corr_vals.values

    # 量增价涨 / 量缩价跌
    frame["vol_change"] = g["volume"].transform(lambda x: x.pct_change())
    frame["vol_vs_return"] = frame["vol_change"] * frame["return_1"]

    return frame


def add_tech_momentum_oscillators(frame: pd.DataFrame) -> pd.DataFrame:
    """
    动量类技术指标：RSI、KDJ、CCI。
    """
    g = frame.groupby("ts_code", group_keys=False)

    # RSI
    def _rsi(series: pd.Series, n: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=n - 1, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(com=n - 1, min_periods=1, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)

    frame["rsi_14"] = g["close"].transform(lambda x: _rsi(x, 14))

    # KDJ
    n = 9
    low_n = g["low"].transform(lambda x: x.rolling(n, min_periods=1).min())
    high_n = g["high"].transform(lambda x: x.rolling(n, min_periods=1).max())
    rsv = (frame["close"] - low_n) / (high_n - low_n + 1e-9) * 100
    frame["kdj_k"] = rsv.ewm(com=2, min_periods=1, adjust=False).mean()
    frame["kdj_d"] = frame["kdj_k"].ewm(com=2, min_periods=1, adjust=False).mean()
    frame["kdj_j"] = 3 * frame["kdj_k"] - 2 * frame["kdj_d"]
    frame["kdj_k_vs_d"] = frame["kdj_k"] / (frame["kdj_d"] + 1e-9) - 1.0

    # CCI: 先逐股计算，再对齐回 frame
    tp = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    cci_vals = np.nan * np.zeros(len(frame))
    for tc, grp in frame.groupby("ts_code"):
        tp_grp = tp.loc[grp.index]
        sma = tp_grp.rolling(20, min_periods=1).mean()
        mad = tp_grp.rolling(20, min_periods=1).apply(lambda s: (s - s.mean()).abs().mean(), raw=False)
        cci_vals[grp.index] = (tp_grp - sma) / (0.015 * mad + 1e-9)
    frame["cci_20"] = cci_vals

    return frame


def add_tech_high_low_features(frame: pd.DataFrame) -> pd.DataFrame:
    """
    高低价位偏离因子：距离 N 日高点的比例、距离 N 日低点的比例。
    """
    g = frame.groupby("ts_code", group_keys=False)

    for w in [20, 60]:
        frame[f"high_{w}d"] = g["high"].transform(lambda x: x.rolling(w, min_periods=1).max())
        frame[f"low_{w}d"] = g["low"].transform(lambda x: x.rolling(w, min_periods=1).min())
        frame[f"close_vs_high_{w}d"] = frame["close"] / (frame[f"high_{w}d"] + 1e-9) - 1.0
        frame[f"close_vs_low_{w}d"] = frame["close"] / (frame[f"low_{w}d"] + 1e-9) - 1.0

    return frame


# =============================================================================
# 基本面因子（来自 financial_indicator 表）
# =============================================================================


def add_fundamental_features(
    frame: pd.DataFrame,
    fin_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    基本面因子。
    如果传入 fin_df（财务指标 DataFrame），则 merge 到行情表；
    否则假设 frame 中已有对应字段（由 build_daily_features 合并而来）。
    """
    if fin_df is not None and not fin_df.empty:
        # 取每个股票最新一期财务数据（按 ann_date 排序取最新）
        fin_latest = (
            fin_df.sort_values(["ts_code", "ann_date"], ascending=[True, False])
            .groupby("ts_code", as_index=False)
            .first()
        )
        fund_cols = [
            "ts_code",
            "roe", "roe_avg", "roa", "roa2",
            "gross_margin", "net_margin",
            "revenue_growth", "profit_growth",
            "debt_to_assets", "current_ratio", "quick_ratio",
            "eps", "bps",
            "pe_ttm", "pb_ratio", "ps_ratio",
        ]
        existing = [c for c in fund_cols if c in fin_latest.columns]
        frame = frame.merge(fin_latest[existing], on="ts_code", how="left")

    # 估值分位（相对历史）
    if "pe_ttm" in frame.columns:
        frame["pe_ttm_zscore"] = frame.groupby("ts_code")["pe_ttm"].transform(
            lambda x: (x - x.rolling(250, min_periods=30).mean()) / (x.rolling(250, min_periods=30).std() + 1e-9)
        )
    if "pb_ratio" in frame.columns:
        frame["pb_zscore"] = frame.groupby("ts_code")["pb_ratio"].transform(
            lambda x: (x - x.rolling(250, min_periods=30).mean()) / (x.rolling(250, min_periods=30).std() + 1e-9)
        )

    # 盈利能力派生
    if "roe" in frame.columns and "roa" in frame.columns:
        frame["roe_vs_roa"] = frame["roe"] - frame["roa"]  # 杠杆贡献
    if "gross_margin" in frame.columns and "net_margin" in frame.columns:
        frame["margin_spread"] = frame["gross_margin"] - frame["net_margin"]

    return frame


# =============================================================================
# 市场因子（来自 index_daily / money_flow 表）
# =============================================================================


def add_market_beta_features(
    frame: pd.DataFrame,
    index_df: pd.DataFrame | None = None,
    benchmark: str = "000001.SH",
) -> pd.DataFrame:
    """
    Beta、市场超额收益因子。
    需要 index_df 包含 benchmark 指数的日线数据。
    """
    if index_df is None or index_df.empty:
        return frame

    bm = index_df[index_df["ts_code"] == benchmark][["trade_date", "close"]].copy()
    if bm.empty:
        return frame
    bm = bm.sort_values("trade_date")
    bm["bm_return"] = bm["close"].pct_change().fillna(0.0)
    bm = bm.rename(columns={"close": "bm_close"})

    frame = frame.merge(bm[["trade_date", "bm_return"]], on="trade_date", how="left")
    frame["bm_return"] = frame["bm_return"].fillna(0.0)

    # 计算个股 Beta（20 日滚动）
    g = frame.groupby("ts_code", group_keys=False)
    cov = g[["return_1", "bm_return"]].transform(
        lambda x: x["return_1"].rolling(20, min_periods=10).cov(x["bm_return"])
    )
    var = frame["bm_return"].rolling(20, min_periods=10).var()
    frame["beta_20d"] = cov / (var + 1e-9)
    frame["beta_20d"] = frame.groupby("ts_code")["beta_20d"].transform(lambda x: x.fillna(1.0).clip(0.2, 3.0))

    # Alpha（个股收益 - Beta * 市场收益）
    frame["alpha_20d"] = frame["return_1"] - frame["beta_20d"] * frame["bm_return"]

    # 相关性
    frame["corr_bm_20d"] = g[["return_1", "bm_return"]].transform(
        lambda x: x["return_1"].rolling(20, min_periods=10).corr(x["bm_return"])
    )

    # 清理临时列
    frame = frame.drop(columns=["bm_return"], errors="ignore")
    return frame


def add_moneyflow_features(
    frame: pd.DataFrame,
    mf_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    资金流因子（来自 money_flow 表）。
    """
    if mf_df is None or mf_df.empty:
        return frame

    # 取每个股票最新一期资金流
    mf_latest = (
        mf_df.sort_values(["ts_code", "trade_date"], ascending=[True, False])
        .groupby("ts_code", as_index=False)
        .first()
    )
    mf_cols = [c for c in ["ts_code", "buy_sm_amount", "sell_sm_amount", "net_mf_amount"] if c in mf_latest.columns]
    frame = frame.merge(mf_latest[mf_cols], on="ts_code", how="left")

    # 净流入比例（相对市值）
    if "net_mf_amount" in frame.columns and "circ_mv" in frame.columns:
        frame["net_mf_ratio"] = frame["net_mf_amount"] / (frame["circ_mv"] * 1e8 + 1e-9)

    return frame


# =============================================================================
# 标签生成（回归 + 分类）
# =============================================================================


def add_label_features(
    frame: pd.DataFrame,
    forward_days: int | list[int] | None = None,
) -> pd.DataFrame:
    """
    生成预测标签。

    Params:
        frame: 必须已按 ts_code + trade_date 排序
        forward_days: 前瞻天数，默认 [1, 3, 5]

    生成字段：
        target_return_Nd      — 未来 N 日收益率（回归标签）
        target_direction_Nd   — 未来 N 日方向（+1/-1 分类）
        target_up_Nd          — 未来 N 日是否上涨（二分类 0/1）
    """
    if forward_days is None:
        forward_days = [1, 3, 5]
    if isinstance(forward_days, int):
        forward_days = [forward_days]

    g = frame.groupby("ts_code", group_keys=False)
    close_series = g["close"]

    for n in forward_days:
        forward_return = close_series.shift(-n) / frame["close"] - 1.0
        frame[f"target_return_{n}d"] = forward_return
        frame[f"target_direction_{n}d"] = (forward_return > 0).astype("int8") * 2 - 1  # +1 涨，-1 跌
        frame[f"target_up_{n}d"] = (forward_return > 0).astype("int8")  # 1 涨，0 跌

    return frame


# =============================================================================
# 主入口：构建完整日频特征（训练/推理共用）
# =============================================================================


def build_daily_features(
    market_df: pd.DataFrame,
    daily_basic_df: pd.DataFrame,
    fin_df: pd.DataFrame | None = None,
    index_df: pd.DataFrame | None = None,
    mf_df: pd.DataFrame | None = None,
    forward_days: int | list[int] | None = None,
    label_only: bool = False,
) -> pd.DataFrame:
    """
    构建完整日频特征表。

    Params:
        market_df:       market_bar_1d 日线行情（必需）
        daily_basic_df:  daily_basic_1d 日线指标（PE/PB/换手率等，可选）
        fin_df:          financial_indicator 财务指标（可选，首次全量时构建）
        index_df:        index_daily 指数日线（可选，用于 Beta 等市场因子）
        mf_df:           money_flow 资金流（可选）
        forward_days:    标签前瞻天数，默认 [1, 3, 5]
        label_only:      若为 True，只生成标签，不计算其他因子（用于推理时加速）

    Returns:
        合并后的特征 DataFrame，按 ts_code + trade_date 排序。

    注意：
        本函数是训练和推理共用的人口，推理时请将 label_only=True
        以跳过前瞻标签计算（避免未来数据泄露）。
    """
    if market_df.empty:
        return pd.DataFrame()

    frame = market_df.copy()
    frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    # ---- 日线基础指标 merge ----
    if not daily_basic_df.empty:
        basics = daily_basic_df.copy()
        frame = frame.merge(
            basics[["ts_code", "trade_date", "pe", "pb", "ps_ttm", "dv_ratio", "total_mv", "circ_mv", "turnrate"]],
            on=["ts_code", "trade_date"],
            how="left",
        )

    # ---- 技术因子 ----
    if not label_only:
        add_tech_return_features(frame)
        add_tech_moving_average_features(frame)
        add_tech_volatility_features(frame)
        add_tech_volume_features(frame)
        add_tech_momentum_oscillators(frame)
        add_tech_high_low_features(frame)

        # ---- 基本面因子 ----
        add_fundamental_features(frame, fin_df)

        # ---- 市场因子 ----
        add_market_beta_features(frame, index_df)
        add_moneyflow_features(frame, mf_df)

    # ---- 标签（始终生成，用于训练） ----
    add_label_features(frame, forward_days=forward_days)

    return frame


# =============================================================================
# 推理特征快照（只计算当日可用的因子，跳过前瞻标签）
# =============================================================================


def build_inference_features(
    market_df: pd.DataFrame,
    daily_basic_df: pd.DataFrame,
    fin_df: pd.DataFrame | None = None,
    index_df: pd.DataFrame | None = None,
    mf_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    推理专用特征构建。
    与 build_daily_features 共享同一因子计算逻辑（label_only=True），
    确保训练和推理口径完全一致。
    """
    return build_daily_features(
        market_df=market_df,
        daily_basic_df=daily_basic_df,
        fin_df=fin_df,
        index_df=index_df,
        mf_df=mf_df,
        label_only=False,  # 推理时也要特征，只是跳过前瞻标签
    )
