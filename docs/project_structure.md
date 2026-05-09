# AI量化交易系统项目结构设计

## 1. 文档目的

本文档给出当前个人版 AI 量化交易系统的推荐项目结构，用于统一目录组织、模块职责和后续开发边界。

## 2. 结构原则

1. 采用单体式模块化结构。
2. 目录按业务边界划分，而不是按技术层任意堆叠。
3. 区分“源码”“配置”“数据”“脚本”“报告”。
4. 保证未来可以从单机平滑演进，但当前不过度设计。

## 3. 推荐目录结构

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
│   ├── high_level_design.md
│   └── detailed_design.md
├── config/
│   └── settings.example.yaml
├── data/
│   ├── raw/
│   ├── clean/
│   ├── features/
│   ├── models/
│   ├── reports/
│   └── backups/
├── scripts/
├── src/
│   └── aistock/
│       ├── __init__.py
│       ├── common/
│       ├── app/
│       ├── config/
│       ├── db/
│       ├── data/
│       ├── feature/
│       ├── model/
│       ├── strategy/
│       ├── risk/
│       ├── broker/
│       ├── backtest/
│       └── report/
├── .env.example
├── .gitignore
└── pyproject.toml
```

## 4. 目录职责

### 4.1 根目录文档

1. `docs/product.md`：产品需求
2. `docs/resource.md`：资源规划
3. `docs/tech.md`：技术选型
4. `docs/project_structure.md`：项目结构说明

### 4.2 `docs/`

放概要设计和详细设计，不放实现细节脚本。

### 4.3 `config/`

放可版本化的配置模板：

1. 数据源配置
2. 风控阈值
3. 策略参数
4. 调度配置

真实密钥不进入 Git，由 `.env` 管理。

### 4.4 `data/`

用于本地单机存储各类数据文件：

1. `raw/`：原始抓取数据
2. `clean/`：清洗后标准数据
3. `features/`：因子和特征快照
4. `models/`：模型文件
5. `reports/`：回测报告、复盘报告
6. `backups/`：数据库和配置备份

### 4.5 `scripts/`

放运维和调度脚本，例如：

1. 每日同步
2. 每周训练
3. 备份脚本
4. 一键启动本地服务

### 4.6 `src/aistock/`

放主业务代码，按模块拆分。

## 5. 核心模块说明

### 5.1 `common/`

公共类型、常量、通用工具函数。

### 5.2 `app/`

CLI 入口、日志初始化、任务启动入口。

### 5.3 `config/`

配置加载、配置对象、环境变量装载。

### 5.4 `db/`

数据库连接、ORM 模型、仓储基础设施。

### 5.5 `data/`

外部数据接入与清洗逻辑：

1. 行情采集
2. 财务采集
3. 公告/新闻采集
4. 数据标准化

### 5.6 `feature/`

因子与特征工程：

1. 技术因子
2. 基本面因子
3. 市场因子
4. 文本因子

### 5.7 `model/`

模型训练和推理：

1. LightGBM/XGBoost 主模型
2. 小模型文本增强接口
3. 模型版本和加载逻辑

### 5.8 `strategy/`

信号生成、评分、排序和目标仓位计算。

### 5.9 `risk/`

规则型风控，包括：

1. 单股仓位限制
2. 单日交易次数限制
3. 日亏损阈值
4. 流动性和公告风险拦截

### 5.10 `broker/`

券商适配与订单执行：

1. 实盘券商适配器
2. 模拟交易适配器
3. 订单状态管理

### 5.11 `backtest/`

历史回测、策略验证、参数试验。

### 5.12 `report/`

日报、回测报告、可视化面板。

## 6. 当前阶段建议优先实现顺序

1. `config + app + db`
2. `data + feature`
3. `model + strategy + risk`
4. `broker + backtest`
5. `report`

这个顺序适合当前个人版目标，因为先跑通数据和研究闭环，再接交易执行，风险更低。
