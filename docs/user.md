# AI量化交易系统用户与运维文档

## 1. 文档目的

本文档面向当前个人版 AI 量化交易系统，整合两类内容：

1. 用户文档：说明系统怎么使用
2. 运维文档：说明系统怎么部署、运行、排查和维护

本文档适用于当前项目的单机、低频、个人交易场景。

## 2. 适用对象

1. 个人交易用户
2. 策略开发者
3. 本地部署和维护人员

## 3. 系统概览

当前系统目标是为个人用户提供一个轻量的量化交易工作流，覆盖以下能力：

1. 行情和基础数据同步
2. 特征与信号生成
3. 风控过滤
4. 模拟交易执行
5. 回测验证
6. 结果查看与复盘

当前技术形态：

1. 单机部署
2. Python 工程
3. 本地数据库或 PostgreSQL
4. CLI 为主，后续可扩展轻量 Web 页面

## 4. 用户文档

## 4.1 使用前准备

在开始前，用户需要准备：

1. Python 3.10+
2. 数据源账号，例如 TuShare Token
3. 模拟交易账号
4. 实盘交易账号和 API 权限
5. `.env` 配置文件
6. `config/settings.yaml` 或沿用示例配置

建议先从模拟交易开始，不要直接启用实盘自动下单。

## 4.2 目录说明

用户最常接触的目录和文件如下：

1. [product.md](/Users/growduduan/pythowork/aistock/docs/product.md)：产品需求
2. [resource.md](/Users/growduduan/pythowork/aistock/docs/resource.md)：资源要求
3. [tech.md](/Users/growduduan/pythowork/aistock/docs/tech.md)：技术选型
4. [project_structure.md](/Users/growduduan/pythowork/aistock/docs/project_structure.md)：项目结构
5. [config/settings.example.yaml](/Users/growduduan/pythowork/aistock/config/settings.example.yaml)：配置样例
6. [src/aistock/app/cli.py](/Users/growduduan/pythowork/aistock/src/aistock/app/cli.py)：CLI 入口

## 4.3 初始化步骤

建议按以下顺序完成初始化：

1. 安装依赖
2. 复制环境变量模板
3. 配置数据源和券商参数
4. 初始化数据库
5. 同步测试数据
6. 生成测试信号
7. 执行模拟交易

## 4.4 环境配置

### 4.4.1 环境变量

参考 [.env.example](/Users/growduduan/pythowork/aistock/.env.example) 创建 `.env`：

```env
ENV=dev
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./aistock.db
TUSHARE_TOKEN=你的token
BROKER_API_KEY=
BROKER_API_SECRET=
BROKER_ACCOUNT_ID=
ALERT_WEBHOOK=
```

说明：

1. 如果暂时没有 PostgreSQL，可先使用 SQLite。
2. 如果暂时不接实盘，可先不填写券商真实密钥。

### 4.4.2 配置文件

参考 [config/settings.example.yaml](/Users/growduduan/pythowork/aistock/config/settings.example.yaml)：

1. 策略观察池大小
2. 调仓频率
3. 风控阈值
4. 是否启用小模型
5. 是否启用新闻处理

建议复制为 `config/settings.yaml` 后再修改，并在 `.env` 中将 `CONFIG_PATH` 指向真实文件。

## 4.5 常用命令

当前 CLI 已提供这些基础命令：

### 4.5.1 准备运行目录

```bash
aistock prepare-runtime
```

用途：

1. 创建 `data/` 目录
2. 创建 `logs/` 目录

### 4.5.2 查看配置

```bash
aistock show-config
```

用途：

1. 查看当前环境、数据库和关键配置

### 4.5.3 健康检查

```bash
aistock health-check
```

用途：

1. 检查数据库连接
2. 检查运行目录初始化

### 4.5.4 初始化数据库

```bash
aistock init-db
```

用途：

1. 创建基础表
2. 准备信号落库环境

### 4.5.5 同步数据

```bash
aistock sync-data
```

用途：

1. 生成原始市场数据快照
2. 创建 `data/` 目录结构

说明：

1. 在未配置 `TUSHARE_TOKEN` 时会回退为占位快照。
2. 配置了 `TUSHARE_TOKEN` 后会执行真实 TuShare 数据同步。
3. 支持通过参数指定股票与时间区间。

示例：

```bash
aistock sync-data --symbols 300750.SZ,688041.SH --start-date 20240101 --end-date 20240131
```

### 4.5.6 生成信号

```bash
aistock generate-signals
```

用途：

1. 执行候选标的打分
2. 生成交易信号
3. 应用基础风控
4. 将结果写入数据库和报表文件

输出位置：

1. `data/reports/signals.csv`

### 4.5.7 查看信号

```bash
aistock show-signals
```

用途：

1. 查看当前数据库中的信号记录

### 4.5.8 执行模拟交易

```bash
aistock paper-trade
```

用途：

1. 使用模拟券商适配器提交订单
2. 用于联调完整闭环

### 4.5.9 运行回测

```bash
aistock run-backtest
```

用途：

1. 基于已有数据运行基础回测

## 4.6 用户推荐操作流程

建议每日按以下顺序使用：

1. 执行 `sync-data`
2. 执行 `generate-signals`
3. 执行 `show-signals`
4. 人工检查信号是否合理
5. 如需联调，执行 `paper-trade`
6. 收盘后执行 `run-backtest` 或复盘脚本

对于实盘用户，当前建议：

1. 先人工确认信号
2. 再决定是否通过实盘接口发单

## 4.7 关键风控约束

当前项目默认遵循以下个人版限制：

1. 每日交易次数不超过 `5 次`
2. 每次操作股票数量不超过 `3 支`
3. 单股仓位不超过配置阈值
4. 低置信度信号不建议直接执行

用户必须理解：

1. 当前系统不是“稳赚系统”
2. 所有策略都必须先经过回测和模拟验证
3. 自动交易启用前必须检查数据和风控配置

## 4.8 结果查看

用户可以重点查看以下输出：

1. 数据快照：`data/raw/`
2. 因子与特征：`data/features/`
3. 模型文件：`data/models/`
4. 信号报表：`data/reports/`
5. 数据库信号表：`signal_record`

## 4.9 常见问题

### 4.9.1 为什么没有生成信号

可能原因：

1. 没有先执行 `sync-data`
2. 风控把信号过滤掉了
3. 配置阈值过严
4. 数据源没有正确配置

### 4.9.2 为什么回测结果为空

可能原因：

1. 原始数据文件不存在
2. 特征列未生成
3. 当前仍是骨架数据，没有接入真实行情

### 4.9.3 为什么不建议直接实盘全自动

原因：

1. 当前项目还处于骨架和逐步实现阶段
2. 数据、信号、风控和券商适配需要逐步验证
3. 个人账户更应该优先保守部署

## 5. 运维文档

## 5.1 运维目标

对于当前个人版项目，运维目标很简单：

1. 能稳定启动
2. 能按计划同步数据
3. 能生成信号
4. 能保留日志和备份
5. 出问题时能快速定位

## 5.2 部署方式

推荐两种部署方式：

### 5.2.1 本地工作站部署

适合：

1. 本人长期在同一台机器上开发和使用
2. 每日手动启动和检查

优点：

1. 成本低
2. 调试方便

缺点：

1. 机器休眠或断网会影响定时任务

### 5.2.2 单台云主机部署

适合：

1. 希望定时任务长期在线
2. 希望盘中自动运行

优点：

1. 稳定在线
2. 适合定时任务

缺点：

1. 需要管理远程环境和安全

## 5.3 安装部署流程

### 5.3.1 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5.3.2 安装项目依赖

```bash
pip install -e .
```

如果需要 PostgreSQL 支持：

```bash
pip install -e .[postgres]
```

如果需要 UI：

```bash
pip install -e .[ui]
```

如果需要 4B 小模型能力：

```bash
pip install -e .[llm]
```

### 5.3.3 配置文件准备

1. 创建 `.env`
2. 准备 `config/settings.yaml`
3. 检查数据库 URL
4. 检查数据源 Token
5. 检查告警 Webhook

### 5.3.4 初始化

```bash
aistock init-db
aistock sync-data
aistock generate-signals
```

## 5.4 运行方式

## 5.4.1 手动运行

适合开发期：

```bash
aistock sync-data
aistock generate-signals
aistock show-signals
aistock paper-trade
```

## 5.4.2 定时任务运行

生产或准生产环境建议使用 `cron`。

示例：

```cron
0 9 * * 1-5 cd /path/to/aistock && . .venv/bin/activate && aistock sync-data
15 9 * * 1-5 cd /path/to/aistock && . .venv/bin/activate && aistock generate-signals
30 15 * * 1-5 cd /path/to/aistock && . .venv/bin/activate && aistock run-backtest
0 16 * * 1-5 cd /path/to/aistock && . .venv/bin/activate && python scripts/backup.py
```

说明：

1. 具体时间要按你的交易习惯和数据源更新时间调整。

## 5.5 日志管理

当前项目使用 Python logging。

建议日志分类：

1. 应用日志
2. 数据同步日志
3. 信号生成日志
4. 交易执行日志
5. 异常日志

建议目录：

1. `logs/app.log`
2. `logs/data.log`
3. `logs/trade.log`

建议：

1. 使用按天切分或按大小轮转
2. 至少保留最近 `30 天`

## 5.6 数据与备份

必须备份的内容：

1. `.env`
2. `config/settings.yaml`
3. 数据库文件或数据库备份
4. `data/models/`
5. `data/reports/`
6. 交易日志

推荐备份频率：

1. 配置文件：每次修改后
2. 数据库：每日一次
3. 模型文件：每次训练后
4. 报表和交易日志：每日归档

推荐备份目标：

1. 外置硬盘
2. NAS
3. 对象存储

## 5.7 安全要求

运维时必须遵守：

1. 不要把 `.env` 提交到 Git
2. 不要在代码里写死券商密钥
3. 不要在公网开放不必要端口
4. 不要在未经验证前启用真实自动下单
5. 保留所有真实下单日志

如果部署在云主机：

1. 仅开放 SSH 和必要端口
2. 使用强密码或 SSH Key
3. 定期更新系统安全补丁

## 5.8 故障排查

### 5.8.1 命令无法执行

检查：

1. 虚拟环境是否激活
2. 是否执行了 `pip install -e .`
3. Python 版本是否符合要求

### 5.8.2 数据同步失败

检查：

1. `TUSHARE_TOKEN` 是否正确
2. 网络是否正常
3. 数据源是否限流
4. 输出目录是否可写

### 5.8.3 数据库初始化失败

检查：

1. `DATABASE_URL` 是否正确
2. SQLite 文件目录是否可写
3. PostgreSQL 是否启动

### 5.8.4 没有信号输出

检查：

1. 数据文件是否存在
2. 配置阈值是否过严
3. 风控是否全部拒绝

### 5.8.5 模拟交易没有订单

检查：

1. 是否先执行了 `generate-signals`
2. 是否存在 `BUY` 信号
3. 数据库中是否有信号记录

## 5.9 运维检查清单

每日检查：

1. 数据同步是否成功
2. 当日信号是否生成
3. 模拟或实盘订单是否符合预期
4. 日志中是否有异常
5. 备份任务是否成功

每周检查：

1. 回测结果是否偏移
2. 风控阈值是否仍合理
3. 磁盘空间是否足够
4. 历史日志是否需要归档

每月检查：

1. 数据库文件大小
2. 模型文件清理情况
3. 配置与密钥是否需要轮换
4. 系统依赖是否需要升级

## 5.10 当前阶段限制说明

当前项目仍处于骨架实现阶段，因此运维上必须明确：

1. 数据同步目前还是占位实现，不是完整生产逻辑
2. 模型预测目前还是基础骨架，不是最终策略收益模型
3. 模拟交易适配器目前只用于联调
4. 实盘券商适配器尚未落地，不应直接视为可生产使用

## 6. 建议的下一步文档

在本文件基础上，后续建议补充：

1. `docs/deployment.md`
   详细写部署命令、系统服务和定时任务
2. `runbook.md`
   详细写异常处理和应急步骤
3. `api.md`
   详细写 CLI 和后续 API 接口说明
