# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] — 2025-05-11

### Fixed

- **DB data integrity**: `MoneyFlow`, `SuspendD`, `LimitListD`, `DisclosureDate`, `BlockTrade` tables used autoincrement `id` as PK but `(ts_code, trade_date)` unique constraint — caused UPSERT to insert duplicates instead of updating. Fixed: composite PK `(ts_code, trade_date)` + `UniqueConstraint` for each table
- **SimBroker slippage direction**: `_calc_exec_price` BUY applied `*(1 - slippage)` (wrong direction — should add cost for BUY), SELL applied `*(1 - slippage - stamp_tax)` (double-deducted stamp_tax). Fixed: BUY `*(1 + slippage)`, SELL `*(1 - slippage)` (stamp_tax only in `_apply_trade`)
- **SimBroker avg_cost basis**: BUY `new_cost = old + volume × price` excluded transaction fee, understating cost basis and overstating unrealized PnL. Fixed: use `cost = volume × exec_price × (1 + fee)` for avg_cost calculation
- **place_order BUY cost check**: Used post-liquidity-capped volume instead of order volume for max cost estimation, causing insufficient-cash rejections on large orders
- **generate-signals fallback**: `symbols = [item.split(".")[0] for ...]` stripped `.SZ/.SH` suffix from already-full ts_codes, breaking downstream prediction
- **make_market_bar_1d**: Used random walk → price drifted from 50 to 44 after 120 days, breaking test assertions expecting fixed 50.0. Fixed: deterministic 50.0 price
- **make_daily_basic_1d**: Same random walk bug. Fixed to 50.0 matching market_bar
- **Dashboard file paths**: `load_trade_log`/`load_signals` used `data_dir/` instead of `reports_dir/`, `DEFAULT_CURVE_FILE` used `equity_curve.csv` instead of `backtest_curve.csv`
- **Dashboard trade_log columns**: Referenced non-existent columns `filled_volume`, `avg_price`, `pnl`, `reason`, `status`. Fixed to actual trade_log fields
- **Dashboard Tab2 position overview**: Same non-existent column references
- **run_model_backtest signature**: `file_config` was a required positional arg but CLI call omitted it, causing `TypeError` at runtime. Made optional with `None` default
- **BacktestResult._empty_result**: Returned `config={}` (empty dict) instead of real config values
- **run-backtest CLI**: Used `result.curve` but `BacktestResult` field is `equity_curve` — would crash on successful backtest
- **time_split leap-year bug**: `now.replace(year=now.year-1)` fails in January (year goes back then forward). Fixed: `timedelta(days=365/730)`
- **BacktestRiskState.drawdown**: `current_drawdown` was documented as absolute yuan but used in pct comparison. Added `current_drawdown_pct()` method
- **SELL stamp_tax**: Hardcoded `0.001` in `cli.py` SELL branch. Fixed: `file_config.portfolio.sim_stamp_tax_rate`
- **execution/engine.py stamp_tax**: Hardcoded `0.001`. Fixed: `portfolio.sim_stamp_tax_rate`
- **_estimate_market_value edge case**: Returned `allocated_capital` when `entry_price=0`, ignoring available `latest_prices`. Fixed: price=0/None guard added to both branches
- **trade_log CSV export**: `paper-trade` wrote `filled_volume` attribute that doesn't exist on `TradeOrder` model, causing `AttributeError`. Fixed: use `filled_weight`/`filled_notional`
- **paper-trade account update**: BUY branch did not update `account.available_cash` (would show stale cash in `show-account`)
- **paper-trade SELL pnl**: Computed `pnl = volume × (price - avg_cost)` using raw reference price instead of actual `exec_price`. Fixed: use `exec_price`
- **lightgbm deferred import**: `predict.py` imported `lightgbm` at module level → 1.5s overhead for entire package even when only using `score_candidates` (which needs no ML). Fixed: deferred import inside `predict_feature_frame()`

### Changed

- **Dashboard usability**: `show-signals`/`show-orders` now print "no signals/orders found" empty-state message instead of silent pass
- **generate-signals**: Now prints BUY/SELL/total_weight summary after writing signals.csv
- **execution/engine.py**: `_calc_shares` docstring corrected: "向下取整" → "向上取整"
- **signals_to_order_requests**: Added Note in docstring about using default `FileConfig()`

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
