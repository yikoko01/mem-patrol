# 两种用法：聊天机器人 / 长期项目（可单开，也可同时开）

结论：**可以分成两组用，也可以同时用**。它们不是两套代码，而是同一组内核的两个使用面：

| 面 | 用到的内核 | 需要宿主提供 |
|---|---|---|
| **聊天机器人** | `retrieval`（召回打分器）+ `gatekeep`（该不该开口的闸门/JSON 决策）+ `safety`（untrusted 包装）+ `observability`（指标） | 聊天事件适配器（把消息变成 `Context`）、LLM 判定器（`judge` callable） |
| **长期项目** | `policy`（孤儿/衰减/巩固/意图/收尾闸门）+ `store`/`cli`（诊断/修复）+ `eval`（离线回归）+ `metrics` | 一个符合 `memories/raw_messages/bot_messages` schema 的 SQLite 库（或写 StorageAdapter） |

- 两者都 **零第三方运行时依赖**；MCP server 把两者都暴露成只读工具。
- 两组的开关是 **profile 预设 + 细粒度 config**，不是一刀切。

## 1. Profile 预设（MCP 工具 allow-list + 默认 config）

```bash
python -m memorix.profiles --list
python -m memorix.profiles --name chat
python -m memorix.profiles --name project
python -m memorix.profiles --name both
```

| profile | 开的功能 | MCP 工具 | 默认 config |
|---|---|---|---|
| `chat` | recall / gatekeep / metrics / safety | recall、gate_check、judge_replay | `enable=true`, 日上限 30, judge=true, consult 10s, 说话间隔 1min, 同话题 0 |
| `project` | recall / patrol / eval / metrics / safety | diagnose、orphan、recall、eval | `enable_group_interjection=false`, 日上限 0 |
| `both` | 全部 | 全部 6 个 | `enable=true`, 日上限 30, judge=true, consult 10s, 说话间隔 1min |

- profile **只提供默认值**：`merge_config(profile, explicit)` 里显式 config 永远覆盖 profile。
- MCP 用 `--profile chat|project|both` 过滤可调用工具；默认 `both`。
- 两个内核可同时跑：`both`（默认开启插话判定+轻节流），聊天面走召回/闸门，项目面走巡检诊断/评测，互不阻塞。
- 插话专项策略/排查顺序见 `docs/INTERJECTION.md`。

## 2. 聊天机器人：开关在哪

| 开关 | 默认 | 作用 |
|---|---|---|
| `enable_group_interjection` | false | **总闸**（关=所有群插话闸门直接 dropped） |
| `group_interject_max_daily` | 0（profile chat/both 给 30） | 0=禁止；否则每日上限 |
| `group_interject_min_interval_minutes` | 0 | 0=不限制最小间隔 |
| `group_interject_same_topic_cooldown_minutes` | 0 | 0=同话题不冷却 |
| `group_interject_judge_decides` | true | true=过闸后交给 LLM 判定；false=回退旧骰子 |
| `group_interject_judge_min_consult_seconds` | 40（profile chat/both 给 10） | 0=关闭按秒咨询节流 |
| `group_busy_timing_enabled` | true | 热闹时段只降权、不否决 |
| `--profile`（MCP） | both | chat/project/both 工具集 |

- 定向消息（@/回复/叫名字）走 **directed 快路径**：跳过 ambient 闸门与 consult，直接判定；
  needs_tools 定向→`handoff`（交回主 agent），非定向→`tool_task`。
- 召回侧：`top_k`、`max_chars`、`context`、`as_of_ms` 全可传；`query` 必须是用户原话，
  instruction 不参与匹配。jieba 是可选锚定依赖（缺失自动退化为纯词面）。
- **不建议做成开关的安全不变量**：契约/偏好无锚不入选、无锚覆盖度下限、MCP 只读、
  修复必须 `--apply` 且先备份。这些是防事故的，不给“灵活”留口子。

## 3. 长期项目：开关在哪

```bash
# 只读诊断（默认只读）
memorix diagnose --db <db> [--state <state.json>] [--ledger <ledger>] [--schema <schema.json|auto>] --json
# 计划/修复（修复才加 --apply，自动 DB 快照）
memorix decay --db <db>            # 只看计划
memorix decay --db <db> --apply    # 才写库
memorix intents --db <db> --apply
memorix finish --db <db> --state <state.json> --user-end N --bot-end N --mem-ids ... --ledger-mark ...
# 离线评测
python -m memorix.eval --suite all --baseline eval/baseline.json
```

- 路径全部显式（`--db/--state/--ledger/--audit-snapshot/--config/--schema`）或 `MEMORIX_*`，不写死生产路径。
- 表不是标准三表？`--schema` 映射或 `--schema auto`；只有记忆表也能用诊断/召回/衰减/评测（详见 `docs/SCHEMA.md`）。
- 私聊上下文按 `group_id == sender_id` 过滤（`recent_private_context`），否则群友发言会被当成用户原话。
- `--apply` 是唯一写入口，写前自动 `<db>/../memorix-backups/` 快照；MCP 不暴露写。
- 评测回归：baseline 里由 pass→fail / case 消失 → exit 1 + `REGRESSIONS`；红报告禁止更新 baseline。
- 巩固/衰减/意图：`decay`/`consolidate`/`intents`；巩固的语义键由调用方（LLM）注入，代码不猜。

## 4. 同时用（both）的推荐接法

```python
from memorix.profiles import merge_config
from memorix.gatekeep import Context, decide
from memorix.retrieval.score import recall
from memorix.observability import MetricsCollector

collector = MetricsCollector()
config = merge_config("both", {"enable_group_interjection": True})  # 显式打开
gate = decide(Context(text=msg, config=config), judge=llm_judge, metrics=collector)
if gate.action == "sent":
    block = recall(user_words, rows=mem_rows, context=recent, metrics=collector)
```

```json
{"mcpServers": {
  "memorix-chat":   {"command": "memorix-mcp", "args": ["--profile", "chat", "--db", "/path/db"]},
  "memorix-project":{"command": "memorix-mcp", "args": ["--profile", "project", "--db", "/path/db"]}
}}
```

## 5. 两组各自还缺什么（诚实）

- 聊天面：本包不含具体 IM 适配器（任意 IM 事件 → `Context`）与真实 LLM 调用；需要宿主 adapter。
- 项目面：`SQLiteStore` 目前假定 `memories/raw_messages/bot_messages` 三表（从生产 schema 抽的）；
  别的项目库需要写一个 `StorageAdapter`（这是 post-M4 的第一优先级）。
- 发布：v0.3.6 已发布到 GitHub Release（PyPI 尚未上传）；`dist/*` 可直接 pip 装。
