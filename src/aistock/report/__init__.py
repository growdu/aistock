"""Reporting, dashboards, and backtest result visualization."""

from aistock.report.dashboard import write_backtest_curve, write_signal_report, write_trade_log

# Note: run_dashboard requires streamlit. Import it directly when needed:
#     from aistock.report.dashboard_app import run_dashboard
# Or run via CLI: streamlit run src/aistock/report/dashboard_app.py

__all__ = [
    "write_backtest_curve",
    "write_signal_report",
]
