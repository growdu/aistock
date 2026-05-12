# 依赖说明

## 1. 文档目的

本文档记录当前项目运行所需的关键依赖，以及本地验证过程中曾暴露出的缺失项，便于后续环境初始化和问题排查。

## 2. 关键依赖与曾暴露的缺失项

在执行测试时，以下依赖曾缺失，现已在本地 `.venv` 中安装：

| 模块导入名 | 对应包名 | 用途 | 缺失表现 |
| --- | --- | --- | --- |
| `typer` | `typer` | CLI 入口与命令执行 | `ModuleNotFoundError: No module named 'typer'` |
| `yaml` | `PyYAML` | YAML 配置文件读取 | `ModuleNotFoundError: No module named 'yaml'` |

## 3. 依赖来源

这些依赖已经在项目配置中有对应关系：

1. `typer` 已在 [pyproject.toml](../pyproject.toml) 的主依赖中声明。
2. `PyYAML` 已在 [pyproject.toml](../pyproject.toml) 的主依赖中声明。

这意味着问题不是项目漏声明，而是当时本地运行环境尚未执行依赖安装。

## 4. 安装方式

推荐直接安装项目依赖，而不是单独逐个装包：

```bash
pip install -e .
```

如果需要开发测试依赖：

```bash
pip install -e .[dev]
```

如果需要 PostgreSQL 支持：

```bash
pip install -e .[postgres]
```

如果需要 UI：

```bash
pip install -e .[ui]
```

如果需要 4B 小模型支持：

```bash
pip install -e .[llm]
```

## 5. 当前建议

在继续执行 `P1` 前，建议先完成以下步骤：

1. 创建并激活虚拟环境
2. 执行 `pip install -e .`
3. 如需测试，再执行 `pip install -e .[dev]`
4. 重新运行测试与 CLI 冒烟检查

## 6. 验证命令

安装完成后，建议执行：

```bash
python3 -m unittest discover -s tests -v
```

以及：

```bash
aistock health-check
```

如果这两个命令可以正常运行，说明基础运行依赖已就绪。
