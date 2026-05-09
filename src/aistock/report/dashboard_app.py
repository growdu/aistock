"""
Streamlit 量化交易看板。

运行方式：
    streamlit run src/aistock/report/dashboard_app.py

功能：
    - 权益曲线（累计收益/回撤）
    - 持仓概览
    - 交易日志
    - 风控指标
    - 信号追踪
    - 模拟账户实时状态
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

# =============================================================================
# 路径配置
# =============================================================================

DEFAULT_DATA_DIR = Path("data")
DEFAULT_REPORTS_DIR = DEFAULT_DATA_DIR / "reports"
DEFAULT_MODELS_DIR = DEFAULT_DATA_DIR / "models"
DEFAULT_CURVE_FILE = DEFAULT_REPORTS_DIR / "equity_curve.csv"


# =============================================================================
# 数据加载
# =============================================================================


@st.cache_data
def load_equity_curve(path: Path | None = None) -> pd.DataFrame | None:
    if path is None:
        path = DEFAULT_CURVE_FILE
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    return df


@st.cache_data
def load_backtest_report(reports_dir: Path | None = None) -> dict | None:
    if reports_dir is None:
        reports_dir = DEFAULT_REPORTS_DIR
    if not reports_dir.exists():
        return None
    files = sorted(reports_dir.glob("backtest_*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


@st.cache_data
def load_trade_log(path: Path | None = None) -> pd.DataFrame | None:
    if path is None:
        path = DEFAULT_DATA_DIR / "trade_log.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return df


@st.cache_data
def load_signals(path: Path | None = None) -> pd.DataFrame | None:
    if path is None:
        path = DEFAULT_DATA_DIR / "signals.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def load_latest_snapshot(data_dir: Path | None = None) -> dict | None:
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
    snap_path = data_dir / "raw" / "market_snapshot.parquet"
    if not snap_path.exists():
        return None
    df = pd.read_parquet(snap_path)
    if df.empty:
        return None
    latest = df.sort_values("trade_date").iloc[-1].to_dict()
    return latest


# =============================================================================
# 指标计算
# =============================================================================


def compute_summary_metrics(curve: pd.DataFrame | None) -> dict:
    if curve is None or curve.empty:
        return {}
    equity_col = "equity" if "equity" in curve.columns else None
    if equity_col is None:
        return {}
    equity = curve[equity_col]
    initial = equity.iloc[0]
    final = equity.iloc[-1]
    total_return = final / initial - 1.0 if initial > 0 else 0.0
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_drawdown = drawdown.min()
    n_days = len(curve)
    years = n_days / 252
    cagr = (1 + total_return) ** (1 / years) - 1.0 if years > 0 else 0.0
    returns = equity.pct_change().dropna()
    sharpe = returns.mean() / returns.std() * (252 ** 0.5) if returns.std() > 0 else 0.0
    return {
        "初始资金": f"{initial:,.0f}",
        "最终权益": f"{final:,.0f}",
        "总收益率": f"{total_return:.2%}",
        "年化收益率": f"{cagr:.2%}",
        "最大回撤": f"{max_drawdown:.2%}",
        "夏普比率": f"{sharpe:.2f}",
        "交易日数": n_days,
    }


# =============================================================================
# 页面配置
# =============================================================================


st.set_page_config(
    page_title="AIStock 量化看板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# 侧边栏
# =============================================================================

st.sidebar.header("⚙️ 配置")
data_dir = st.sidebar.text_input("数据目录", value="data")
reports_dir = Path(data_dir) / "reports"
models_dir = Path(data_dir) / "models"

st.sidebar.markdown("---")
st.sidebar.header("📂 数据状态")
snap = load_latest_snapshot(Path(data_dir))
if snap:
    st.sidebar.success(f"行情数据: {snap.get('trade_date', 'N/A')}")
else:
    st.sidebar.warning("未找到行情数据，请先运行 sync-data")

curve = load_equity_curve(Path(data_dir) / "equity_curve.csv")
if curve is not None and not curve.empty:
    st.sidebar.success(f"权益曲线: {len(curve)} 条记录")
else:
    st.sidebar.warning("未找到权益曲线")

st.sidebar.markdown("---")
st.sidebar.caption(f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# =============================================================================
# 概览指标
# =============================================================================

st.title("📈 AIStock 量化交易看板")

metrics = compute_summary_metrics(curve)
if metrics:
    cols = st.columns(len(metrics))
    for i, (k, v) in enumerate(metrics.items()):
        cols[i].metric(label=k, value=v)
else:
    st.info("运行回测或模拟交易后，这里将显示策略表现指标。")


# =============================================================================
# Tab 1: 权益曲线
# =============================================================================

tab1, tab2, tab3, tab4 = st.tabs(["权益曲线", "持仓概览", "交易日志", "风控指标"])

with tab1:
    st.subheader("权益曲线")

    if curve is not None and not curve.empty:
        col_map = {c: c for c in curve.columns}
        equity_col = "equity" if "equity" in curve.columns else None

        if equity_col:
            # 累计收益
            curve_disp = curve.copy()
            curve_disp["累计收益"] = (curve_disp[equity_col] / curve_disp[equity_col].iloc[0] - 1) * 100

            tab1.line_chart(
                curve_disp.set_index("trade_date")[["累计收益"]],
                use_container_width=True,
            )

            # 权益
            tab1.line_chart(
                curve_disp.set_index("trade_date")[[equity_col]],
                use_container_width=True,
            )

            # 回撤
            if "drawdown" in curve.columns:
                tab1.area_chart(
                    curve.set_index("trade_date")[["drawdown"]],
                    use_container_width=True,
                )
    else:
        tab1.info("暂无数据。请运行 `aistock run-backtest` 或 `aistock paper-trade` 生成权益曲线。")


# =============================================================================
# Tab 2: 持仓概览
# =============================================================================

with tab2:
    st.subheader("当前持仓")

    # 从最新权益曲线快照读取持仓
    positions_data: list[dict] = []
    if curve is not None and not curve.empty and "positions_count" in curve.columns:
        last_row = curve.iloc[-1]
        n_pos = int(last_row.get("positions_count", 0))
        tab2.metric("持仓数量", n_pos)

    # 也尝试从 trade_log 中汇总
    trade_log = load_trade_log(Path(data_dir) / "trade_log.csv")
    if trade_log is not None and not trade_log.empty:
        # 显示最新持仓（根据交易日志推算）
        if "symbol" in trade_log.columns and "side" in trade_log.columns:
            latest_positions: dict[str, dict] = {}
            for _, row in trade_log.sort_values("submitted_at", ascending=False).iterrows():
                sym = str(row.get("symbol", ""))
                side = str(row.get("side", ""))
                if side == "BUY":
                    latest_positions[sym] = {
                        "symbol": sym,
                        "shares": int(row.get("filled_volume", 0)),
                        "avg_price": float(row.get("avg_price", 0)),
                    }
                elif side == "SELL" and sym in latest_positions:
                    latest_positions.pop(sym, None)

            if latest_positions:
                pos_df = pd.DataFrame(latest_positions.values())
                tab2.dataframe(pos_df, use_container_width=True)
            else:
                tab2.info("暂无持仓")
    else:
        tab2.info("暂无交易日志，请先运行模拟交易或实盘")


# =============================================================================
# Tab 3: 交易日志
# =============================================================================

with tab3:
    st.subheader("交易日志")

    log = load_trade_log(Path(data_dir) / "trade_log.csv")
    if log is not None and not log.empty:
        if "submitted_at" in log.columns:
            log = log.sort_values("submitted_at", ascending=False)
        tab3.dataframe(log[[
            c for c in ["submitted_at", "symbol", "side", "filled_volume", "avg_price", "pnl", "reason", "status"]
            if c in log.columns
        ]], use_container_width=True, hide_index=True)

        # 下载按钮
        csv = log.to_csv(index=False)
        tab3.download_button(
            "下载交易日志 CSV",
            data=csv,
            file_name="trade_log.csv",
            mime="text/csv",
        )
    else:
        tab3.info("暂无交易日志。")


# =============================================================================
# Tab 4: 风控指标
# =============================================================================

with tab4:
    st.subheader("风控指标")

    report = load_backtest_report(reports_dir)

    if report:
        m = report.get("metrics", {})
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("总收益率", f"{m.get('total_return', 0):.2%}")
            st.metric("年化收益率", f"{m.get('annual_return', 0):.2%}")
            st.metric("夏普比率", f"{m.get('sharpe_ratio', 0):.2f}")

        with col2:
            st.metric("最大回撤", f"{m.get('max_drawdown', 0):.2%}")
            st.metric("胜率", f"{m.get('win_rate', 0):.2%}")
            st.metric("盈亏比", f"{m.get('profit_loss_ratio', 0):.2f}")

        with col3:
            st.metric("总交易次数", m.get("total_trades", 0))
            st.metric("平均持仓天数", f"{m.get('avg_hold_days', 0):.1f}")
            st.metric("平均换手率", f"{m.get('avg_turnover_rate', 0):.2%}")

        st.markdown("---")
        st.json(report.get("config", {}))
    else:
        # 尝试从 equity_curve 计算风控指标
        if curve is not None and not curve.empty:
            returns = curve["day_return"] if "day_return" in curve.columns else curve["equity"].pct_change()
            winning = (returns > 0).sum()
            total = len(returns)
            st.metric("胜率", f"{winning/total:.2%}" if total > 0 else "N/A")
            st.metric("交易日数", total)
        else:
            st.info("运行回测后显示风控指标。")


# =============================================================================
# 主区域底部：信号追踪
# =============================================================================

st.markdown("---")
st.subheader("📡 最近信号")

signals = load_signals(Path(data_dir) / "signals.csv")
if signals is not None and not signals.empty:
    if "trade_date" in signals.columns:
        signals = signals.sort_values("trade_date", ascending=False)
    st.dataframe(
        signals[[c for c in ["trade_date", "symbol", "action", "target_weight", "predicted_return", "reason"] if c in signals.columns]].head(20),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("运行 `generate-signals` 或 `paper-trade` 后显示信号列表。")


# =============================================================================
# 页脚
# =============================================================================

st.markdown(
    "---"
    "\n📊 AIStock 量化交易系统  |  "
    "数据驱动  |  模型预测  |  风控护航"
)
