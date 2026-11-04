# Companion Memory

Companion Core 记忆能力的附属参考仓库：源码快照、结构说明、可运行的 Python/SQLite
示例，以及六轮合成评测的题库、答案、判分和测试脚本。

[Companion Core](https://github.com/Tidekin/companion-core) 是日常开发和修复的主线。
这里从其指定提交单向整理发布，Core 自身的开发、构建和运行保持独立。
当前实现快照为 `30628cff61d6642d6ababf833d6432cd83695c0f`。

## 从哪里开始

| 目的 | 入口 |
| --- | --- |
| 理解整体结构与边界 | [架构与源码阅读地图](docs/architecture.md) |
| 在其他 AI 项目里参考实现 | [实现提示词](prompts/implementation.md)、[原生运行提示词](prompts/) |
| 运行小型示例 | [SQLite 示例](examples/sqlite_demo.py) |
| 查看历次题库与结果 | [评测索引与限制](evaluations/README.md) |
| 阅读完整原生实现及回归用例 | [源码快照](reference/upstream/)、[生成来源](provenance/upstream.json) |
| 更新快照、复核公开材料 | [维护与发布](docs/maintenance.md) |
| 了解脱敏和许可范围 | [公开材料说明](docs/publication.md)、[NOTICE](NOTICE.md)、[MIT](LICENSE) |

## 运行 Python 示例

需要 Python 3.11+，在本仓库根目录执行：

```sh
python -m pip install .
python examples/sqlite_demo.py
```

示例使用内存 SQLite 和固定模型输出，演示提取解析、来源绑定、关系复核、检索和
删除来源后事实失效，供应商调用数为零。可用 `--database .local/example.sqlite`
写入一个新的 SQLite 文件。

安装包名为 `companion-memory-reference`，导入名为 `companion_memory`。
包内的解析、关系一致性检查和排序函数从原生源码自动生成并校验。
这个小包及示例展示其中的纯函数边界；完整生产记忆流程还需要 Core 的来源权限、
检查点、事务、记账和删除回放。对应源码和测试一并收录，详见架构文档。

## 检查公开材料

```sh
python -m pip install . pytest ruff build
python scripts/verify_release.py
python -m pytest --basetemp=.local/test-temp
python -m ruff check .
python -m build
```

PowerShell 可以运行 `./scripts/check.ps1`。检查全部离线执行，验证公开文件哈希、
六轮题目和得分统计、生成源码及示例行为。历史在线评测脚本收录在
`benchmarks/memory_campaign/` 和各轮目录；运行前需要自行配置 Core、模型和费用限额，
详见评测索引。

## 版本与成绩

| 轮次 | 语义题数 | 当轮新实现通过数 | RAG 参考通过数 |
| --- | ---: | ---: | ---: |
| v1 | 696，另有 18 项生命周期检查 | 150 | 599 |
| v2 | 576 | 422 | 527 |
| v3 | 480 | 437 | 444 |
| v4 | 480 | 433 | 463 |
| v5 | 744 | 714 | 727 |
| v6 | 792 | 738 | 748 |

各轮题库、代码和评审条件不同，表格用于查阅历史，不能据此计算跨轮提升。
v6 的 738/792 对应 `7074838d`；当前源码快照包含此后修复，尚无该快照的新全量分数。
自动判分和项目内复核也不等于独立人工盲测。完整局限、敏感性分析和原始票据见各轮材料。

问题和修复优先提交到 Companion Core；这里按版本更新参考材料。
