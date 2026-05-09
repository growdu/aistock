# AI量化交易系统部署文档

## 1. 文档目的

本文档给出当前个人版 AI 量化交易系统的实际部署方案，覆盖：

1. 本地工作站部署
2. 单台云主机部署
3. 环境初始化
4. 日常运行
5. 定时任务
6. 备份与恢复

本文档以当前项目的`单机部署`方案为准，不涉及多机集群和微服务编排。

## 2. 部署目标

当前部署目标不是高可用集群，而是让系统具备以下能力：

1. 能稳定安装和启动
2. 能同步数据
3. 能生成信号
4. 能执行模拟交易
5. 能运行基础回测
6. 能执行备份

## 3. 部署方式选择

## 3.1 方式 A：本地工作站

适合：

1. 个人开发和个人使用在同一台机器上进行
2. 每日手动运行任务
3. 交易频率低，不依赖全天在线

优点：

1. 成本最低
2. 调试最方便
3. 数据完全本地可控

缺点：

1. 机器休眠会影响定时任务
2. 不适合长期无人值守

## 3.2 方式 B：单台云主机

适合：

1. 希望系统在交易时间持续在线
2. 希望使用 `cron` 执行盘前和盘后任务
3. 本地机器不稳定或不常开机

优点：

1. 稳定在线
2. 适合自动化运行

缺点：

1. 需要额外维护远程主机安全
2. 需要处理云主机备份和 SSH 登录

## 4. 系统要求

推荐环境：

1. Python `3.10+`
2. Linux `Ubuntu 22.04 LTS`
3. 内存 `16 GB` 起步，推荐 `32 GB`
4. 磁盘 `300 GB SSD` 起步，推荐 `1 TB SSD`

当前项目在个人场景下不要求：

1. Kubernetes
2. Kafka
3. Redis 必选
4. ELK
5. GPU 常驻运行

## 5. 部署目录建议

推荐将项目部署在固定路径，例如：

```text
/opt/aistock
```

建议目录布局：

```text
/opt/aistock
├── .env
├── .venv/
├── config/
├── data/
├── docs/
├── logs/
├── scripts/
├── src/
└── pyproject.toml
```

## 6. 安装步骤

## 6.1 获取项目代码

如果使用 Git：

```bash
git clone <your-repo-url> /opt/aistock
cd /opt/aistock
```

如果是本地目录，直接进入项目根目录即可。

## 6.2 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 6.3 安装依赖

基础安装：

```bash
pip install --upgrade pip
pip install -e .
```

如果需要 PostgreSQL：

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

## 6.4 创建运行目录

```bash
mkdir -p logs
mkdir -p data/raw data/clean data/features data/models data/reports data/backups
```

## 6.5 创建环境变量文件

参考 [.env.example](/Users/growduduan/pythowork/aistock/.env.example) 创建 `.env`：

```bash
cp .env.example .env
```

然后至少修改以下项：

1. `DATABASE_URL`
2. `TUSHARE_TOKEN`
3. `BROKER_API_KEY`
4. `BROKER_API_SECRET`
5. `BROKER_ACCOUNT_ID`
6. `ALERT_WEBHOOK`

## 6.6 创建业务配置文件

```bash
cp config/settings.example.yaml config/settings.yaml
```

按需求修改：

1. 观察池大小
2. 风控阈值
3. 是否启用新闻处理
4. 是否启用小模型

建议在 `.env` 中增加：

```env
CONFIG_PATH=config/settings.yaml
```

## 7. 初始化步骤

## 7.1 准备运行目录与环境检查

```bash
aistock prepare-runtime
aistock show-config
aistock health-check
```

用途：

1. 创建运行目录
2. 检查配置是否生效
3. 检查数据库与基本环境

## 7.2 初始化数据库

```bash
aistock init-db
```

用途：

1. 创建基础表
2. 让信号和后续记录可以落库

## 7.3 首次同步测试数据

```bash
aistock sync-data
```

说明：

1. 在未配置 `TUSHARE_TOKEN` 时会回退为占位快照。
2. 配置了 `TUSHARE_TOKEN` 后会执行真实 TuShare 数据同步。
3. 支持通过参数指定股票和时间范围。

示例：

```bash
aistock sync-data --symbols 300750.SZ,688041.SH --start-date 20240101 --end-date 20240131
```

## 7.4 生成测试信号

```bash
aistock generate-signals
```

## 7.5 查看信号

```bash
aistock show-signals
```

## 7.6 执行模拟交易

```bash
aistock paper-trade
```

## 7.7 运行基础回测

```bash
aistock run-backtest
```

## 8. 运行模式

## 8.1 开发模式

适合当前阶段：

1. 手动执行命令
2. 手动检查结果
3. 手动查看数据库和报表

推荐顺序：

```bash
aistock prepare-runtime
aistock show-config
aistock health-check
aistock sync-data
aistock generate-signals
aistock show-signals
aistock paper-trade
```

## 8.2 准生产模式

适合未来个人长期运行：

1. 定时同步数据
2. 定时生成信号
3. 定时备份
4. 告警通知失败任务

## 9. 定时任务部署

推荐使用 `cron`。

编辑当前用户的定时任务：

```bash
crontab -e
```

示例：

```cron
0 9 * * 1-5 cd /opt/aistock && . .venv/bin/activate && aistock sync-data >> logs/data.log 2>&1
15 9 * * 1-5 cd /opt/aistock && . .venv/bin/activate && aistock generate-signals >> logs/app.log 2>&1
20 9 * * 1-5 cd /opt/aistock && . .venv/bin/activate && aistock show-signals >> logs/app.log 2>&1
35 15 * * 1-5 cd /opt/aistock && . .venv/bin/activate && aistock run-backtest >> logs/app.log 2>&1
0 16 * * 1-5 cd /opt/aistock && . .venv/bin/activate && python scripts/backup.py >> logs/backup.log 2>&1
```

说明：

1. 这里的时间只是示例。
2. 要结合你的数据更新时间和交易习惯调整。
3. 当前阶段不建议未经人工确认就自动发实盘单。

## 10. 数据库部署建议

## 10.1 SQLite 方案

适合：

1. 原型阶段
2. 单机个人使用
3. 数据量不大时

默认示例：

```env
DATABASE_URL=sqlite:///./aistock.db
```

优点：

1. 零运维
2. 上手最快

缺点：

1. 不适合后续复杂并发和长期扩展

## 10.2 PostgreSQL 方案

适合：

1. 准备长期运行
2. 需要更稳定的数据管理
3. 准备接入真实交易后做长期记录

建议：

1. 本机安装 PostgreSQL
2. 建立独立数据库用户和数据库
3. 把连接串写入 `.env`

示例：

```env
DATABASE_URL=postgresql+psycopg://aistock:password@127.0.0.1:5432/aistock
```

## 11. 日志部署建议

当前项目使用本地文件日志即可。

建议准备：

1. `logs/app.log`
2. `logs/data.log`
3. `logs/backup.log`
4. `logs/trade.log`

建议方式：

1. 使用 shell 重定向输出命令日志
2. 后续如需要，可补 Python 文件轮转日志

## 12. 备份部署

当前项目已补充 [scripts/backup.py](/Users/growduduan/pythowork/aistock/scripts/backup.py)。

备份内容：

1. `.env`
2. `config/settings.yaml`
3. `aistock.db`
4. `data/models/`
5. `data/reports/`

手动执行：

```bash
python scripts/backup.py
```

输出位置：

1. `data/backups/`

## 13. 恢复流程

## 13.1 配置恢复

恢复以下文件：

1. `.env`
2. `config/settings.yaml`

## 13.2 数据恢复

如果使用 SQLite：

1. 停止所有任务
2. 用备份的 `aistock.db` 覆盖当前文件
3. 重新执行 `aistock show-signals` 验证

如果使用 PostgreSQL：

1. 使用 PostgreSQL 自身的备份恢复方式
2. 恢复完成后验证连接

## 13.3 模型与报表恢复

恢复：

1. `data/models/`
2. `data/reports/`

## 14. 安全加固建议

本地部署时：

1. `.env` 权限只给当前用户
2. 定期备份到外部介质
3. 不要把券商账号和 Token 提交到 Git

云主机部署时：

1. 使用 SSH Key
2. 禁止 root 直接远程登录
3. 仅开放必要端口
4. 定期更新安全补丁
5. 启用防火墙

## 15. 故障处理流程

## 15.1 命令不可用

检查：

1. 是否激活 `.venv`
2. 是否执行 `pip install -e .`
3. 是否在项目根目录下执行

## 15.2 数据同步失败

检查：

1. `TUSHARE_TOKEN` 是否有效
2. 网络是否可达
3. 数据目录是否存在

## 15.3 无法生成信号

检查：

1. 是否先执行 `sync-data`
2. 数据文件是否存在
3. 数据库是否初始化

## 15.4 备份失败

检查：

1. `data/backups/` 是否可写
2. 磁盘空间是否充足
3. 备份源文件是否存在

## 16. 当前阶段注意事项

当前项目还处于骨架阶段，因此部署时必须明确：

1. `sync-data` 当前是占位实现
2. `paper-trade` 当前是模拟适配器
3. 实盘券商适配器还未接入
4. 不应将当前版本直接视为可无人值守实盘系统

## 17. 推荐下一步

在本部署文档基础上，接下来建议补以下内容：

1. `runbook.md`
   细化异常场景和恢复步骤
2. `scripts/`
   补更多自动化脚本，例如每日任务脚本、环境检查脚本
3. `systemd` 服务文件
   如果后续部署在 Linux 云主机上，可将关键任务变为系统服务
