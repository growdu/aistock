# AIStock 用户手册

本文档面向使用 AIStock 量化交易系统的个人用户，涵盖从安装到日常使用的完整说明。

## 1. 系统概述

### 1.1 定位与能力

AIStock 是面向个人用户的 AI 辅助量化交易系统，聚焦科创板（688xxx）和创业板（300xxx）场景。

**核心链路：**

```
数据同步 → 因子与特征 → 预测与信号 → 风控 → 模拟/实盘执行 → 回测与复盘
```

**当前已完成的功能模块：**

| 模块 | 能力 |
|------|------|
| 数据层 | Tushare / AkShare 双数据源，日线/分钟线/财务/资金流/涨跌停，增量 UPSERT 同步 |
| 特征工程 | 81 个技术/基本面/市场因子 + 9 个预测标签 |
| 模型训练 | LightGBM / XGBoost，时间序列切分，IC + AUC + 夏普指标 |
| 策略引擎 | 多因子排序，equal / confidence / kelly 仓位分配 |
| 风控引擎 | 置信度/次数/仓位/流动性/黑白名单全链路风控 |
| 回测引擎 | 手续费 + 滑点 + 印花税 + 成交量限制 |
| 券商适配 | SimBroker 全内存模拟交易，QMTBroker 实盘（Windows）|
| Web 可视化 | Streamlit 看板，权益曲线/持仓/交易日志/风控指标 |

### 1.2 系统约束

1. 每日交易不超过 **5 次**
2. 每次操作股票不超过 **3 支**
3. 当前为**基线模型**，需充分回测验证后方可实盘

### 1.3 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.10+ |
| 数据库 | SQLite（默认）/ PostgreSQL |
| 主模型 | LightGBM / XGBoost |
| 回测 | Backtrader |
| 可视化 | Streamlit + Plotly |
| 数据源 | Tushare / AkShare（可选）|

### 1.4 数据源说明

系统支持双数据源，可根据需求选择：

| 数据源 | 说明 | 费用 |
|--------|------|------|
| **Tushare** | 全面数据，12+ 接口，含财务/资金流 | 需要积分 |
| **AkShare** | 开源免费，实时行情，日线/分钟线 | 免费 |

切换方式：在 `config/settings.yaml` 中修改 `data_source.type`：

```yaml
data_source:
  type: akshare  # tushare | akshare
```

或通过环境变量：

```bash
DATA_SOURCE_TYPE=akshare
```

## 2. 安装部署

### 2.1 环境要求

- Python 3.10 或更高版本
- Tushare Token（可选，用于真实数据，可先跳过用合成数据）
- AkShare（可选，免费数据源）
- Linux / macOS / Windows

### 2.2 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
```

### 2.3 安装依赖

```bash
pip install --upgrade pip
pip install -e .
```

可选依赖组：

```bash
pip install -e .[postgres]   # PostgreSQL 支持
pip install -e .[ui]         # Streamlit 可视化
pip install -e .[llm]       # 4B 小模型（需要 torch + transformers）
pip install -e ".[all]"     # 全部依赖
```

### 2.4 准备配置文件

```bash
cp .env.example .env
cp config/settings.example.yaml config/settings.yaml
```

至少填写 `.env` 中的以下字段：

```env
DATABASE_URL=sqlite:///./aistock.db
CONFIG_PATH=config/settings.yaml
DATA_SOURCE_TYPE=akshare    # tushare | akshare（默认 tushare）
TUSHARE_TOKEN=your_token_here    # 仅 Tushare 需要
```

> **提示**：
> - **AkShare（免费）**：配置 `DATA_SOURCE_TYPE=akshare`，无需 Token
> - **Tushare（付费）**：在 [tushare.pro](https://tushare.pro/register) 注册并获取 Token
> - 默认使用 Tushare，如需切换到 AkShare 见下方配置

### 2.5 初始化

```bash
aistock prepare-runtime    # 创建 data/ 和 logs/ 目录
aistock init-db            # 初始化数据库表
aistock health-check       # 验证环境
```

## 3. 配置指南

### 3.1 .env 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENV` | 环境：`dev` / `prod` | `dev` |
| `LOG_LEVEL` | 日志级别：`DEBUG` / `INFO` / `WARNING` | `INFO` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./aistock.db` |
| `CONFIG_PATH` | 配置文件路径 | `config/settings.yaml` |
| `DATA_SOURCE_TYPE` | 数据源类型：`tushare` / `akshare` | `tushare` |
| `TUSHARE_TOKEN` | Tushare API Token | 空 |
| `TRADING_MODE` | 交易模式：`paper` / `live` | `paper` |
| `BROKER_TYPE` | 券商类型：`sim` / `qmt` | `sim` |
| `ALERT_WEBHOOK` | 告警 Webhook（可选）| 空 |

### 3.2 config/settings.yaml

#### app 区

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `app.name` | 应用名称 | `aistock` |
| `app.data_dir` | 数据根目录 | `data` |
| `app.logs_dir` | 日志目录 | `logs` |

#### strategy 区

| 字段 | 说明 | 默认值 | 推荐 |
|------|------|--------|------|
| `strategy.top_n` | 每次持仓标的数量 | `3` | `3` |
| `strategy.symbols` | 默认股票池 | 见示例 | 科创板+创业板各 2-3 只 |

#### risk 区

| 字段 | 说明 | 默认值 | 推荐 |
|------|------|--------|------|
| `risk.max_daily_trades` | 每日最大交易次数 | `5` | 个人用户 3-5 |
| `risk.max_symbols_per_trade` | 每次最多操作股票数 | `3` | `3` |
| `risk.max_single_position_pct` | 单股最大仓位 | `0.10` | 不超过 15% |
| `risk.max_daily_loss_pct` | 当日最大亏损止损 | `0.03` | `0.03` |
| `risk.min_confidence_score` | 最小置信度阈值 | `0.60` | 保守用户可设 0.7 |

#### portfolio 区（模拟交易）

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `portfolio.initial_cash` | 初始资金 | `1_000_000.0` |
| `portfolio.transaction_cost_rate` | 手续费率（买卖双向）| `0.0003`（万三）|
| `portfolio.slippage_rate` | 滑点率 | `0.0005`（万分之五）|
| `portfolio.min_expected_excess_return` | 最小期望超额收益 | `0.001` |
| `portfolio.sim_stamp_tax_rate` | 印花税率（仅卖出）| `0.001`（千分之一）|

#### backtest 区

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `backtest.initial_cash` | 回测初始资金 | `1_000_000.0` |
| `backtest.transaction_cost_rate` | 回测手续费率 | `0.0003` |
| `backtest.slippage_rate` | 回测滑点率 | `0.0005` |

## 4. 快速开始

### 4.1 路径一：使用 AkShare（免费，无需 Token）

适合不想付费的用户，使用开源 AkShare 数据源。

```bash
# 1. 安装后初始化
aistock prepare-runtime
aistock init-db

# 2. 配置 AkShare（修改 .env）
echo "DATA_SOURCE_TYPE=akshare" >> .env

# 3. 安装 akshare（如未安装）
pip install akshare

# 4. 同步数据（AkShare 免费数据）
aistock sync-data

# 5. 构建特征并生成信号
aistock build-features
aistock generate-signals
aistock show-signals

# 6. 执行模拟交易
aistock paper-trade
aistock show-account

# 7. 运行回测
aistock run-backtest

# 8. 启动 Web 可视化
streamlit run src/aistock/report/dashboard_app.py
```

### 4.2 路径二：使用 Tushare（需要 Token）

适合需要更全面数据的用户（Tushare 需要积分）。

```bash
# 1. 在 .env 中填入 TUSHARE_TOKEN 后
aistock sync-data                          # 同步近 2 年日线数据
aistock sync-data --mode all               # 全量同步（含财务/资金流/分钟线）
aistock build-features                     # 构建 81 个因子
aistock train-model                        # 训练 LightGBM 模型
aistock generate-signals                   # 生成交易信号
aistock show-signals                       # 查看信号
aistock paper-trade                        # 执行模拟交易
aistock show-account                       # 查看账户
aistock show-orders                        # 查看订单
aistock show-positions                     # 查看持仓
aistock run-backtest                       # 运行回测
streamlit run src/aistock/report/dashboard_app.py  # Web 可视化
```

### 4.3 路径三：合成数据演示（无需任何配置）

适合先体验完整流程，不拉取任何真实行情数据。

```bash
# 1. 安装后初始化
aistock prepare-runtime
aistock init-db

# 2. 直接构建特征（使用内置合成数据）
aistock build-features

# 3. 生成信号（使用 fallback 排序，无真实模型）
aistock generate-signals
aistock show-signals

# 4. 执行模拟交易
aistock paper-trade
aistock show-account

# 5. 运行回测
aistock run-backtest

# 6. 启动 Web 可视化
streamlit run src/aistock/report/dashboard_app.py
```

## 5. CLI 命令参考

| 命令 | 作用 | 关键输出 |
|------|------|---------|
| `aistock prepare-runtime` | 创建 data/ 和 logs/ 目录结构 | 各目录就绪状态 |
| `aistock show-config` | 显示当前配置 | 所有配置项当前值 |
| `aistock health-check` | 检查数据库和目录 | `health check passed` |
| `aistock init-db` | 初始化数据库表 | `database initialized` |
| `aistock sync-data` | 同步日线行情（增量）| 同步行数 |
| `aistock sync-data --mode all` | 全量同步（含财务/分钟线）| 各项同步行数 |
| `aistock build-features` | 从原始数据构建特征 | `daily_features.parquet` |
| `aistock train-model` | 训练 LightGBM/XGBoost | 训练指标（RMSE/IC/AUC）|
| `aistock train-model --train-all` | 训练 1d/3d/5d 多目标 | 各目标模型路径 |
| `aistock generate-signals` | 生成交易信号并写入 DB | BUY/SELL 信号数量 + 总权重 |
| `aistock show-signals` | 查看当前信号 | 每条信号的权重/置信度/预测收益 |
| `aistock paper-trade` | 执行模拟交易调仓 | 每笔成交的股数/价格/成本 |
| `aistock show-account` | 查看账户状态 | 可用现金/已实现盈亏/总权益 |
| `aistock show-orders` | 查看历史订单 | 每笔订单的成交价/成本/状态 |
| `aistock show-positions` | 查看当前持仓 | 每只股票的市值/盈亏/权重 |
| `aistock run-backtest` | 运行回测 | 收益率/回撤/夏普/胜率 |

### 常用参数

```bash
# 指定股票池和时间范围
aistock sync-data --symbols 300750.SZ,688041.SH --start-date 20240101 --end-date 20241231

# 全量数据同步
aistock sync-data --mode all --include-minute

# 训练特定目标
aistock train-model --target target_return_3d --model-type xgboost

# 使用 XGBoost 模型
aistock train-model --model-type xgboost --train-all
```

## 6. Web 可视化

### 6.1 启动看板

```bash
# 在项目根目录执行
streamlit run src/aistock/report/dashboard_app.py
```

### 6.2 远程访问配置

默认仅本地访问。如需非本机访问，需绑定到所有网络接口：

```bash
streamlit run src/aistock/report/dashboard_app.py --server.address 0.0.0.0 --server.port 8501
```

然后通过 `http://<服务器IP>:8501` 访问。

> **注意**：公网访问需在云服务器安全组中放行 8501 端口。

### 6.3 看板功能说明

| Tab | 内容 |
|-----|------|
| **权益曲线** | 累计收益曲线 + 回撤曲线 |
| **持仓概览** | 当前持仓列表，含成本/市值/浮动盈亏 |
| **交易日志** | 所有成交记录，含手续费/滑点，支持 CSV 下载 |
| **风控指标** | 夏普比率/胜率/盈亏比/换手率 |

## 7. 每日工作流

### 7.1 盘前（9:00 前）

```bash
# 1. 同步最新数据
aistock sync-data

# 2. 构建特征
aistock build-features

# 3. 生成信号
aistock generate-signals
aistock show-signals
```

### 7.2 盘中（9:30-15:00）

```bash
# 人工确认信号后，执行模拟调仓
aistock paper-trade
aistock show-account
aistock show-positions
```

### 7.3 盘后（15:30 后）

```bash
# 运行回测并复盘
aistock run-backtest

# 启动看板查看结果
streamlit run src/aistock/report/dashboard_app.py

# 备份今日数据
python scripts/backup.py
```

### 7.4 定时任务（cron）示例

```cron
# 盘前 8:30 同步数据 + 生成信号
30 8 * * 1-5 cd /path/to/aistock && .venv/bin/activate && aistock sync-data && aistock generate-signals >> logs/daily.log 2>&1

# 盘后 16:00 运行回测
0 16 * * 1-5 cd /path/to/aistock && .venv/bin/activate && aistock run-backtest >> logs/backtest.log 2>&1

# 每日 17:00 备份
0 17 * * 1-5 cd /path/to/aistock && .venv/bin/activate && python scripts/backup.py >> logs/backup.log 2>&1
```

## 8. 风控说明

### 8.1 风控规则

| 规则 | 说明 |
|------|------|
| 置信度过滤 | `confidence < min_confidence_score` 时拒绝或降低仓位 |
| 每日次数限制 | `daily_trade_count >= max_daily_trades` 时拒绝新单 |
| 单股仓位上限 | 超过 `max_single_position_pct` 的信号被调整 |
| 最小期望收益 | 预测收益 < 手续费 + 滑点 + 最小超额时跳过 |
| 流动性限制 | 市值/成交量低于阈值时警告或拒绝 |
| 黑白名单 | ST 股、退市股、高风险股在黑名单中自动拦截 |

### 8.2 建议阈值

- **保守用户**：`min_confidence_score = 0.70`，`max_single_position_pct = 0.10`
- **积极用户**：`min_confidence_score = 0.55`，`max_single_position_pct = 0.15`

### 8.3 重要提醒

> **AIStock 不是稳赚系统**。所有策略必须先经过回测验证。实盘自动交易前请充分在模拟环境测试。

## 9. 数据与备份

### 9.1 关键数据文件

| 文件/目录 | 说明 | 备份频率 |
|-----------|------|---------|
| `.env` | 密钥和数据库配置 | 每次修改 |
| `config/settings.yaml` | 策略和风控参数 | 每次修改 |
| `aistock.db` | SQLite 数据库（交易记录）| 每日 |
| `data/models/` | 训练好的模型文件 | 每次训练后 |
| `data/reports/` | 信号和回测报表 | 每日 |
| `logs/` | 应用日志 | 每周归档 |

### 9.2 备份脚本

```bash
# 手动备份
python scripts/backup.py

# 备份内容：数据库 + 模型 + 报表 + 配置
```

## 10. 常见问题

### Q1: sync-data 提示 "tushare token not configured"

**原因**：`.env` 中 `TUSHARE_TOKEN` 为空。

**解决**：
1. 在 [tushare.pro](https://tushare.pro/register) 注册并获取 Token
2. 填入 `.env`：`TUSHARE_TOKEN=your_token`
3. 重新执行 `aistock sync-data`

---

### Q2: generate-signals 提示 "trained model artifacts missing, using fallback ranking"

**原因**：没有训练好的模型文件（`lightgbm_daily.txt` / `.json`）。

**解决**：
```bash
aistock build-features      # 先生成特征
aistock train-model         # 训练模型
aistock generate-signals    # 再生成信号
```

---

### Q3: paper-trade 没有生成任何订单

**检查步骤**：
```bash
aistock show-signals        # 1. 确认有 BUY/SELL 信号
aistock show-account        # 2. 确认账户有可用现金
```

可能原因：
- 没有 BUY 信号（信号被风控过滤）
- 可用现金不足（需卖出部分持仓释放资金）
- 最小期望收益门槛过高（预测收益被 `min_expected_excess_return` 拦截）

---

### Q4: run-backtest 报错 "market_snapshot.parquet not found"

**原因**：`run-backtest` 的 fallback 路径需要 `data/raw/market_snapshot.parquet`，但该文件不存在。

**解决**：先执行完整数据流程：
```bash
aistock sync-data
aistock build-features
aistock run-backtest
```

---

### Q5: Streamlit 看板无法启动

**检查**：
```bash
# 1. 确认安装了 UI 依赖
pip install -e .[ui]

# 2. 在项目根目录执行
cd /path/to/aistock
streamlit run src/aistock/report/dashboard_app.py
```

---

### Q6: 模拟交易和回测结果差异大

**正常原因**：
- 回测使用历史数据，模拟交易使用实时价格
- 滑点和成交价的估算方式不同
- 回测不考虑流动性冲击，模拟交易更保守

**排查方向**：
1. 确认两者使用相同的 `transaction_cost_rate` 和 `slippage_rate`
2. 检查回测是否开启了风控引擎
3. 对比同一时间段的回测和模拟账户权益曲线

---

## 11. 安全建议

1. **不要将 `.env` 提交到 Git** — 已在 `.gitignore` 中忽略
2. **不要在代码中硬编码密钥** — 所有密钥通过环境变量或配置文件管理
3. **实盘前必须关闭 `TRADING_MODE=papre`** — 默认为 `paper`，切换到 `live` 前需二次确认
4. **保留完整交易日志** — 所有订单记录保存在数据库和 `logs/trade.log` 中
5. **云服务器安全组** — 仅开放 SSH 和必要端口，不将 Streamlit 端口暴露到公网

## 12. 文档索引

| 文档 | 内容 |
|------|------|
| `README.md` | 项目总览、快速开始 |
| `docs/product.md` | 产品需求 |
| `docs/tech.md` | 技术选型说明 |
| `docs/implementation_plan.md` | 实施计划和各阶段状态 |
| `docs/deployment.md` | 部署详细步骤 |
| `docs/DEVELOP.md` | 开发者指南 |
| `CHANGELOG.md` | 版本变更记录 |
