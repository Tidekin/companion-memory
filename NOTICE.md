# 来源与许可

本仓库采用 [MIT](LICENSE)。维护者授权将这里选定的项目自有实现、合成题库、
评测脚本、示例和文档按 MIT 发布。源码来自
[Tidekin/companion-core](https://github.com/Tidekin/companion-core)，
具体提交、Git blob 和 SHA-256 见 [源码清单](provenance/upstream.json)。
主仓库原有许可证由其自身仓库维护。

选定内容经过源码头部、提交归属、导入和题库生成来源检查；未收录其他基准仓库的
实现代码、原始对话或题库。本项目的合成题库借鉴以下方法论，题目与人物另行编写：

| 方法论来源 | 参考版本 | 使用方式 |
| --- | --- | --- |
| [Ornn8/memory-system-benchmark](https://github.com/Ornn8/memory-system-benchmark/tree/4c9d147ec650419cdd3e66d81d15582e4672fe3b) | `4c9d147e` | 分类、延迟、多模态、原生维护与逐题隔离等设计参考 |
| [FuRongJun-1999/hive-memory-bench](https://github.com/FuRongJun-1999/hive-memory-bench/tree/179b29451b7e528798569269560389e3863789d9) | `179b2945` | 盲评、来源边界、闭卷对照、独立性与因果归因参考 |

这两套基准的内容及许可仍由原作者维护；本仓库的分数只对应本项目公开的合成题库。
题库图像是项目文字的程序渲染，语音由通用 Windows System.Speech TTS 合成。
发布包包含输出素材与生成脚本，字体文件、TTS 引擎和模型权重由使用者自行提供。

Python 示例依赖 Pydantic（MIT），开发检查使用 pytest（MIT）、Ruff（MIT）和
PyPA build（MIT）。这些依赖由包管理器获取，没有把其实现复制进本仓库。
历史完整评测需要相应 Core 版本及其依赖；其许可、供应商条款和运行配置分别适用。
MIT 不授予第三方模型、服务、字体或商标的权利。
