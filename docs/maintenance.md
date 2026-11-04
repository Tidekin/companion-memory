# 维护与发布

日常记忆开发在 Companion Core 完成。附属仓库选择一个已经验证的提交，
更新源码快照、例子和文档，再发布自己的版本。

```sh
python scripts/sync_upstream.py --source /path/to/companion-core --ref <reviewed-commit>
python scripts/sync_upstream.py --verify
```

生成器只读取 Git 中已提交的文件，记录提交、树、blob 和内容哈希。
更新前校验上一版快照和生成文件，发现人工改动则停下。
源码结构改变、可提取函数出现新宿主依赖时，需要先调整并审查生成器。

发布评测时，从原始目录导出指定轮次，保留原件：

```sh
python scripts/export_evaluations.py --source /path/to/companion-core --ref <commit> \
  --round v1=/path/to/first-round --round v2=/path/to/second-round
```

本仓库已经附有 v1～v6。生成脚本所需字体路径和在线脚本中的 `LOCAL_PATH`
必须配置为自己的环境；历史脚本用于审查方法和重现实验，所需完整 Core 版本
由各轮 `PUBLICATION.json` 指定。重新执行在线实验会形成新的评测身份。

导出结束后核对许可、媒体和脱敏记录，运行针对性的检查。公开文件确定后：

```sh
python scripts/verify_release.py --freeze
python scripts/verify_release.py
```

`--freeze` 生成本次公开文件清单，不改写各轮原始证据身份。
提交之后由本仓库 CI 在 Windows 和 Linux 上检查同一候选，成功后发布 tag/release。
主仓库不需要依赖、同步任务或部署操作。
