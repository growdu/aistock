# AIStock

面向个人用户的 AI 辅助量化交易系统，聚焦`科创板 + 创业板`场景，目标是在`低频、轻量、可控`前提下跑通完整闭环：

`数据同步 -> 因子与特征 -> 预测与信号 -> 风控 -> 模拟/实盘执行 -> 回测与复盘`

当前项目定位不是团队级交易平台，而是`个人版单机系统`：

1. 每日交易次数不超过 `5 次`
2. 每次操作股票不超过 `3 支`
3. 主模型以 `LightGBM/XGBoost` 为主
4. `4B 小模型` 仅用于公告/新闻摘要、情绪和解释增强

## 当前状态

项目目前已经完成：

1. 需求、设计、资源、技术选型和部署文档
2. Python 单体式模块化工程骨架
3. CLI 基础入口
4. 基础数据库模型
5. 占位版数据同步、信号生成、风控、模拟交易和回测链路
6. 备份脚本

项目目前还没有完成：

1. 真实 TuShare 数据接入
2. 真实券商实盘适配器
3. 完整特征工程和正式收益模型
4. 可直接无人值守的生产级实盘能力

这意味着当前仓库适合作为`研发起点和迭代骨架`，不应直接视为可生产实盘系统。

## 技术路线

当前选型基于个人版低成本约束，核心决策如下：

1. 架构：`Python 单体式模块化`
2. 部署：`单机部署 + cron`
3. 数据库：`SQLite 起步，可升级 PostgreSQL`
4. 文件存储：`Parquet + 本地目录`
5. 主模型：`LightGBM`
6. 备选模型：`XGBoost`
7. 文本增强：`4B 量化小模型`
8. 回测：`Backtrader`
9. 展示：后续可扩展 `Streamlit + Plotly`

## 项目结构

```text
aistock/
├── README.md
├── docs/
│   ├── README.md
│   ├── product.md
│   ├── resource.md
│   ├── tech.md
│   ├── user.md
│   ├── deployment.md
│   ├── project_structure.md
│   ├── implementation_plan.md
│   ├── depend.md
│   ├── high_level_design.md
│   └── detailed_design.md
├── config/
├── scripts/
├── src/
└── pyproject.toml
```

核心源码目录在 [src/aistock](/Users/growduduan/pythowork/aistock/src/aistock)：

1. `app`：CLI 和应用入口
2. `config`：配置加载
3. `db`：数据库连接和模型
4. `data`：数据采集与清洗
5. `feature`：因子与特征
6. `model`：训练与推理
7. `strategy`：信号生成
8. `risk`：规则风控
9. `broker`：券商适配器
10. `backtest`：回测
11. `report`：报表与结果输出

## 快速开始

## 1. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. 安装依赖

```bash
pip install --upgrade pip
pip install -e .
```

可选依赖：

```bash
pip install -e .[postgres]
pip install -e .[ui]
pip install -e .[llm]
```

## 3. 准备配置

```bash
cp .env.example .env
cp config/settings.example.yaml config/settings.yaml
```

至少配置：

1. `DATABASE_URL`
2. `CONFIG_PATH=config/settings.yaml`
3. `TUSHARE_TOKEN`
4. 券商相关字段
5. `portfolio.initial_cash`

## 4. 准备运行目录

```bash
aistock prepare-runtime
```

## 5. 检查配置与环境

```bash
aistock show-config
aistock health-check
```

## 6. 初始化数据库

```bash
aistock init-db
```

## 7. 同步测试数据

默认在未配置 `TUSHARE_TOKEN` 时，会回退为占位快照：

```bash
aistock sync-data
```

配置了 `TUSHARE_TOKEN` 后，可显式指定股票和时间区间：

```bash
aistock sync-data --symbols 300750.SZ,688041.SH --start-date 20240101 --end-date 20240131
```

## 8. 生成信号

```bash
aistock build-features
```

用途：

1. 从日线和基础面数据构建日频特征
2. 生成训练标签 `target_return_1d` 和 `target_up_1d`
3. 输出 `data/features/daily_features.parquet`

## 9. 训练基线模型

```bash
aistock train-model
```

## 10. 生成信号

```bash
aistock generate-signals
```

## 11. 查看信号

```bash
aistock show-signals
```

## 12. 执行模拟交易

```bash
aistock paper-trade
```

这一步会按目标权重对当前组合做模拟调仓，支持买入、减仓和卖出，并把账户、订单和持仓写入数据库。

## 13. 查看账户、订单和持仓

```bash
aistock show-account
aistock show-orders
aistock show-positions
```

其中：

1. `show-account` 会显示 `available_cash`、`realized_pnl`、`unrealized_pnl`、`total_equity`
2. `show-orders` 会显示每笔模拟成交的成本
3. `show-positions` 会显示持仓成本、市值和浮动盈亏

## 14. 运行基础回测

```bash
aistock run-backtest
```

回测结果会写入 `data/reports/backtest_curve.csv`，其中包含 `available_cash`、`invested_capital`、`market_value`、`unrealized_pnl`、`equity`、`drawdown`。
默认还会计入 `backtest.transaction_cost_rate` 和 `backtest.slippage_rate`。
模拟交易默认也会计入 `portfolio.transaction_cost_rate` 和 `portfolio.slippage_rate`。

## 常用命令

```bash
aistock prepare-runtime
aistock show-config
aistock health-check
aistock init-db
aistock sync-data
aistock build-features
aistock train-model
aistock generate-signals
aistock show-signals
aistock paper-trade
aistock show-account
aistock show-orders
aistock show-positions
aistock run-backtest
python scripts/backup.py
```

## 文档导航

建议按下面顺序阅读：

1. [README.md](/Users/growduduan/pythowork/aistock/README.md)
   先了解项目定位、状态和快速开始
2. [product.md](/Users/growduduan/pythowork/aistock/docs/product.md)
   查看产品目标和需求范围
3. [tech.md](/Users/growduduan/pythowork/aistock/docs/tech.md)
   查看技术架构选型
4. [project_structure.md](/Users/growduduan/pythowork/aistock/docs/project_structure.md)
   查看目录结构和模块边界
5. [implementation_plan.md](/Users/growduduan/pythowork/aistock/docs/implementation_plan.md)
   查看实施阶段、任务拆分和验收标准
6. [depend.md](/Users/growduduan/pythowork/aistock/docs/depend.md)
   查看依赖说明和安装指引
7. [user.md](/Users/growduduan/pythowork/aistock/docs/user.md)
   查看使用说明和运维说明
8. [deployment.md](/Users/growduduan/pythowork/aistock/docs/deployment.md)
   查看部署步骤和定时任务
9. [docs/README.md](/Users/growduduan/pythowork/aistock/docs/README.md)
   查看设计文档索引

## 重要限制

当前版本必须明确以下限制：

1. `sync-data` 仍是骨架实现，不是完整生产数据同步
2. `paper-trade` 仅为模拟适配器，但已支持订单和持仓落库
3. 实盘券商接口尚未接入
4. 当前模型链路可运行，但仍属于基线实现
5. 不应直接对接无人值守实盘

## 下一步开发建议

推荐按以下顺序继续开发：

1. 接入真实 TuShare 数据同步
2. 完善 SQLite/PostgreSQL 表结构
3. 落实真实因子和训练样本
4. 用真实数据替换占位版信号生成
5. 接入实盘券商适配器
6. 增加 Streamlit 可视化页面

## 文档索引

完整文档目录见 [docs/README.md](/Users/growduduan/pythowork/aistock/docs/README.md)。
