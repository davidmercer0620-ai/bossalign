# BossAlign（蛔虫引擎）

> **AI Agent 的反馈对齐层。**
> 把人类反馈变成有范围、可追溯的规则，减少 AI 重复犯同类错误。

[![CI](https://github.com/davidmercer0620-ai/bossalign/actions/workflows/ci.yml/badge.svg?branch=dev%2Fv0.2)](https://github.com/davidmercer0620-ai/bossalign/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

BossAlign 是一个独立于 Agent 框架的轻量层：保存反馈来源，把反馈解析成**待确认规则**，记录适用范围与反例边界，并在新任务中解释规则为什么启用、排除、冲突或无法判断。

普通聊天记忆倾向于保存对话或总结；BossAlign 只希望保留值得重复执行的纠正规则，并明确“适用于哪里”和“不能泛化到哪里”。系统检查结果不等于真实用户批准。

## 快速开始

需要 Python 3.9+。核心包没有运行时第三方依赖。克隆后安装：

```bash
git clone https://github.com/davidmercer0620-ai/bossalign.git
cd bossalign
python -m pip install -e .
bossalign demo
```

`demo` 使用真实 SDK 与临时 SQLite 数据库，数据是虚构的，不调用模型，也不伪造用户审批。

### Python SDK

```python
from bossalign import BossAlign, TaskContext

with BossAlign("bossalign.sqlite3") as align:
    proposal = align.ingest(
        "面向消费者的引导文案不要出现 'guaranteed zero downtime'。"
        "技术事故报告不适用这条规则。",
        reviewer="reviewer-1",
        context={
            "applicable_scope": {
                "project": "sample-app",
                "task_type": "consumer_copy",
                "audience": "consumer",
            },
            "negative_boundaries": [{"task_type": "technical_incident_report"}],
            "deterministic_checks": ["guaranteed zero downtime"],
            "conflict_key": "downtime_claim",
            "effect": "avoid",
        },
    )
    print(proposal.status)  # draft：已保存，尚未生效

    rule = align.confirm_rule(proposal.rule_id)  # 人工明确确认
    task = TaskContext(
        project="sample-app",
        task_type="consumer_copy",
        audience="consumer",
    )
    selection = align.retrieve(task, reviewer="reviewer-1")
    report = align.check(task, "This copy promises guaranteed zero downtime.", reviewer="reviewer-1")

    print([item.rule_id for item in selection.active_rules])
    print(report.status)  # violations_found
    print(report.violations[0].evidence)  # 命中的原文片段
    print(report.user_approved)  # False
```

反馈事件、规则和规则版本保存在 SQLite。重新创建 `BossAlign("bossalign.sqlite3")` 后仍可检索。`update_rule()` 会生成新版本；`deactivate_rule()` 停用规则但保留历史。

## 适用范围与反例

历史反馈：“消费者引导文案不要出现‘guaranteed zero downtime’。技术事故报告不适用。”

| 新任务 | 普通宽泛记忆的风险 | BossAlign 行为 |
| --- | --- | --- |
| 消费者引导文案 | 可能忘记纠正，或只记成模糊偏好 | 启用已确认规则；仅对明确配置的短语做确定性检查 |
| 技术事故报告 | 可能误删事故文档中的必要信息 | 命中结构化反例边界，排除该规则 |
| 缺少受众或项目上下文 | 可能按相似度强行套用 | 返回不确定，不强行应用 |

离线 Provider 不是通用语义模型。它只识别有限的中英文指令/偏好线索；确定性审核只检查显式配置的精确短语。更复杂的自然语言解析可以接入 OpenAI-compatible Provider，其结果仍标记为模型推断，需要人工判断。

## CLI

数据库用法：命令前写 `--db`，或设置环境变量 `BOSSALIGN_DB`。

```bash
# 保存待确认反馈；JSON 中提供结构化范围与精确检查项
bossalign --db ./memory.sqlite3 ingest \
  --reviewer reviewer-1 \
  --raw "Avoid 'guaranteed zero downtime' in consumer copy." \
  --context-json '{"applicable_scope":{"project":"sample-app","audience":"consumer"},"negative_boundaries":[{"task_type":"technical_incident_report"}],"deterministic_checks":["guaranteed zero downtime"]}'

# 查看后人工确认已有规则
bossalign --db ./memory.sqlite3 rules confirm --rule-id RULE_ID
bossalign --db ./memory.sqlite3 rules --reviewer reviewer-1
bossalign --db ./memory.sqlite3 rules update --rule-id RULE_ID --directive "Keep the measurement context"
bossalign --db ./memory.sqlite3 rules deactivate --rule-id RULE_ID
bossalign --db ./memory.sqlite3 check --file draft.md \
  --task-context '{"project":"sample-app","task_type":"consumer_copy","audience":"consumer"}' \
  --reviewer reviewer-1
bossalign --db ./memory.sqlite3 sanitize --file draft.md --out clean.md
```

命令包括 `ingest`、`rules`、`check`、`demo`、`sanitize`。V0.2 没有 `generate` 命令。审核退出码：`0` 表示没有报告问题或没有适用规则，`1` 表示发现规则问题或模型建议人工复核，`2` 表示上下文不足或检查无法完成。

## OpenAI-compatible Provider

SDK 接受 Provider 对象。内置适配器使用 OpenAI Chat Completions 兼容请求格式和 Python 标准库，不依赖厂商 SDK：

```python
import os
from bossalign import BossAlign
from bossalign.providers import OpenAICompatibleProvider

provider = OpenAICompatibleProvider(
    base_url=os.environ.get("BOSSALIGN_BASE_URL", "https://api.openai.com/v1"),
    model=os.environ["BOSSALIGN_MODEL"],
    api_key=os.environ["BOSSALIGN_API_KEY"],
)
align = BossAlign("memory.sqlite3", provider=provider)
```

模型解析结果始终先保存为 `draft`，不会自行确认。模型审核结果标记为 `llm_inference`，需要人工判断。只有应用主动配置并调用 Provider 时才会发生真实模型请求。

CLI 做解析或审核时可设置 `BOSSALIGN_PROVIDER=openai`、`BOSSALIGN_API_KEY`、`BOSSALIGN_MODEL`；兼容服务可通过 `BOSSALIGN_BASE_URL` 指定地址。查看规则、清洗文本和运行虚构 Demo 不需要模型凭据。

## Benchmark

本地运行虚构回归集：

```bash
python benchmarks/run.py
```

包含 4 个虚构案例：软件开发、内容写作、产品设计、数据分析。共 4 条反馈、8 次范围判断、12 次输出检查。脚本报告规则提取准确率、范围准确率、错误泛化率、违反检测 precision/recall 和真实样本数；不调用模型。样本很小，只验证功能路径，不代表通用语言表现或模型排名。

## 架构与限制

CLI、SDK、Demo 共用同一套 parser、SQLite store、boundary engine 和 checker。SQLite 是唯一运行时存储。净室工具只移除 BossAlign 标签，不是通用隐私扫描器或导出管线。

- 离线解析依赖有限的中英文线索，不具备完整语义解析能力。
- 范围采用归一化后的精确值匹配，不使用向量或模糊匹配。
- 非结构化反例会产生不确定结果；建议用 `{"audience":"technical"}` 这类条件对象。
- 确定性审核只检查配置过的精确短语，不能证明语义合规。
- OpenAI-compatible 请求形状有本地 stub 测试，但未对第三方客户端做真实集成验证。
- MCP 暂缓到后续版本；当前不宣称兼容任何 MCP 客户端。
- 虚构 Benchmark 是小型回归集，不代表生产级可靠性或广泛准确率。

## 常见问题

**默认会调用模型吗？** 不会。默认使用离线确定性 Provider；只有你显式配置并调用外部 Provider 才会请求模型。

**`no_deterministic_violations_found` 是否代表稿件通过？** 不代表。它只说明已配置的精确短语检查没有命中，`user_approved` 始终为 `false`。

**V0.2 能否生成或改写内容？** 不能。请用现有 Agent 生成内容，再把任务上下文和输出传给 `check()`。

**记忆存在哪里？** 存在传给 `BossAlign` 的 SQLite 文件；默认是 `~/.bossalign/memory.sqlite3`。本地存储不会自动上传。若显式配置并调用外部 Provider，则该次请求的输入会发送给相应服务。

**任务上下文缺失怎么办？** 返回不确定，不强行应用范围规则。

**是否支持 MCP？** 当前没有实现 MCP，也不宣称兼容任何 MCP 客户端。

开发和贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)、[架构说明](docs/architecture.md) 和 [英文 README](README.md)。许可证为 MIT，见 [LICENSE](LICENSE)。
