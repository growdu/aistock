# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2025-XX-XX

### Added

- **P2 Feature Engineering**: `feature/factors.py` with 81 tech/fundamental/market features + 9 prediction labels
  - Tech: return_1/3/5/10/20d, MA, EMA, MACD, RSI, KDJ, CCI, Bollinger Bands, ATR
  - Volume: volume ratio, price-volume correlation (per-stock rolling)
  - Fundamental: ROE/ROA, revenue/net profit growth, R&D ratio, PE/PB rank
  - Market: beta, alpha, index correlation, northbound flow
  - Labels: target_return_1d/3d/5d, target_direction/up
- **P3 Model Training**: `model/train.py` complete rewrite
  - LightGBM + XGBoost support
  - Time-series train/val/test split with configurable date boundaries
  - Early stopping (30-round patience), best iteration tracking
  - Metrics: RMSE, MAE, AUC (direction), IC (information coefficient)
  - `train_all_targets()` for 1d/3d/5d multi-target batch training
  - Model artifacts: `.cbm` (joblib) + `.json` (metadata) + `.report.json`
- **P4 Strategy + Risk + Backtest**: Complete pipeline
  - `strategy/engine.py`: FilterConfig, RankConfig, kelly/equal/confidence position sizing, PositionTracker
  - `risk/engine.py`: RiskEngine with confidence/daily-trades/position/liquidity/blacklist checks, BacktestRiskState
  - `backtest/engine.py`: Full backtest with transaction costs, slippage, stamp tax, volume limits, stop-loss/take-profit
- **P5 Broker Adapters**: Full trading infrastructure
  - `broker/base.py`: BrokerAdapter protocol, OrderRequest/Execution/Position/Account/Quote types
  - `broker/paper.py`: SimBroker with full cash/position tracking, commission/slippage/stamp tax, daily settlement
  - `broker/qmt.py`: QMTBroker via xtquant (Windows only, deferred import)
  - `execution/engine.py`: ExecutionEngine (signal → order translation, batch execution, cost accounting)
- **P6 Visualization**: Streamlit dashboard
  - `report/dashboard_app.py`: 4-tab dashboard (equity curve, positions, trade log, risk metrics)
  - Equity curve with cumulative return + drawdown charts
  - Trade log with CSV download
  - Sidebar with data availability status
- **Config**: BrokerConfig in settings + RuntimeSettings.trading_mode (paper/live)
- **CLI**: All commands updated with new parameters
- **Logging**: Per-module log files (app.log / data.log / trade.log)
- **Backup script**: Enhanced with DB path auto-detection, max-backup retention (30)

### Changed

- `data/pipeline.py`: Complete rewrite with 10+ sync functions, UPSERT incremental sync
- `TushareClient`: Enhanced with 12 data interfaces (minute bars, financials, money flow, index data, limit list, block trade, etc.)
- Database models: 9 new tables (financial_indicator, market_bar_1m, index_daily, money_flow, suspend_d, limit_list_d, etc.)
- `strategy/engine.py`: Replaced `generate_signals` with FilterConfig + RankConfig + compute_target_positions
- README.md: P1-P6 completion table, updated limitations and next steps
- implementation_plan.md: All phases marked complete, MVP achieved

## [0.1.0] — 2025-XX-XX

### Added

- Project scaffold (CLI, config, db, data, feature, model, strategy, risk, broker, backtest, report modules)
- Tushare data client (basic daily sync)
- Placeholder factor and signal generation
- Basic paper trading adapter
- Minimal backtest engine
- Documentation: README, product, tech, user, deployment, implementation plan
