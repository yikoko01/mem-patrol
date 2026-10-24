# MemPatrol · 聊天机器人 + 长期记忆/项目内核（README 样稿）

> 一个零第三方依赖的「长期记忆 + 决策闸门」内核：既能做聊天机器人的“该不该说/该记什么”，
> 也能做长期项目的“记忆卫生/巡检/离线回归”。两种用法可单开、可同时开。

## ✨ 两种用法

| 模式 | 做什么 | 入口 |
|---|---|---|
| **聊天机器人** `chat` | 记忆召回注入、该不该开口的闸门、影子模式/审查者、指标 | `memorix.retrieval` / `memorix.gatekeep` |
| **长期项目** `project` | 孤儿批次、衰减/巩固、意图过期、配置漂移审计、离线评测+baseline | `memorix.policy` / `memorix.cli` / `memorix.eval` |
| **同时用** `both` | 两个面同一进程/同一 MCP server | `--profile both` |

```bash
python -m memorix.profiles --list      # chat / project / both
python -m memorix.profiles --name chat
```

## 🚀 快速开始

```bash
pip install dist/mem_patrol-0.2.4-py3-none-any.whl  # 或 pip install .
memorix --version                                  # 导入/CLI 名仍是 memorix

# 聊天面（MCP，只读工具 3 个）
memorix-mcp --profile chat --db /path/to/memories.db   # 别名 mem-patrol-mcp

# 项目面（MCP，只读工具 4 个）
memorix-mcp --profile project --db /path/to/memories.db

# CLI（项目面；默认只读，修复加 --apply）
memorix diagnose --db /path/to/memories.db --json
python -m memorix.eval --suite all --baseline eval/baseline.json
```

## 🎛️ 开关（两层，profile 只给默认值）

**第一层：profile**
- `chat`：召回 + 闸门；**开启判定+轻节流**（日上限 30 / consult 10s / 说话间隔 1min）。
- `project`：巡检诊断/记忆卫生/评测；不启用群插话裁判。
- `both`：全部；**默认也开启判定+轻节流**，项目面照常诊断。

**第二层：config（显式覆盖 profile）**

| 键 | 默认 | 说明 |
|---|---|---|
| `enable_group_interjection` | false（profile chat/both 为 true） | 群插话总闸 |
| `group_interject_max_daily` | 0（chat/both 30） | 0=禁止，>0=每日上限 |
| `group_interject_min_interval_minutes` | 0 | 0=不限间隔 |
| `group_interject_same_topic_cooldown_minutes` | 0 | 0=不冷却同话题 |
| `group_interject_judge_decides` | true | false=回退旧骰子 |
| `group_interject_judge_min_consult_seconds` | 40（chat/both 10） | 0=关闭按秒节流 |
| `group_busy_timing_enabled` | true | 热闹时段只降权 |

召回参数：`top_k`、`max_chars`、`context`、`as_of_ms`；`jieba` 为可选锚定依赖。
**安全不变量不可关**：MCP 只读、修复需 `--apply`+备份、instruction 不参与匹配、契约无锚不入选。

> 插话策略：**裁判读懂后有插入点就接话**，节流只防刷屏/排队；排查“AI 不说话”见 `docs/INTERJECTION.md`。

## 🔌 MCP 配置

```json
{
  "mcpServers": {
    "memorix-chat":    {"command": "memorix-mcp", "args": ["--profile", "chat", "--db", "<db>"]},
    "memorix-project": {"command": "memorix-mcp", "args": ["--profile", "project", "--db", "<db>"]}
  }
}
```

只读工具：`memorix_recall` / `memorix_gate_check` / `memorix_judge_replay`（chat）+ `memorix_diagnose` / `memorix_orphan` / `memorix_eval`（project），`both` 全部 6 个。

## 🗄️ 我的表不是标准三表？

```bash
# 显式映射（只有记忆表也能用 diagnose/recall/decay/eval）
memorix diagnose --db my.db --schema schema.json
# 或自动探测
memorix diagnose --db my.db --schema auto
```

缺 `raw_messages/bot_messages` 时，`status/finish` 会明确报错，其余功能照常。详见 `docs/SCHEMA.md`。

## 🧱 目录

```
src/memorix/policy/         纯函数：孤儿/署名/审计/衰减/巩固/意图/收尾闸门
src/memorix/retrieval/      召回打分器 + §10.3 六条回放
src/memorix/gatekeep/       决策闸门 + JSON 契约 + 9 条裁判回放
src/memorix/observability/  指标 + SVG/HTML 报告
src/memorix/eval/           离线评测 + baseline 回归
src/memorix/safety/         untrusted 包装层
src/memorix/mcp/            MCP stdio server（只读）
src/memorix/profiles.py     chat / project / both 预设
```

## 🧪 测试与评测

```bash
pip install '.[test]'
python -m pytest -p no:cacheprovider          # 363 passed；无 jieba 时锚定用例自动 skip
python -m memorix.eval --suite all --baseline eval/baseline.json   # 24/24
python -m memorix.retrieval.bench              # 6/6
python -m memorix.gatekeep.bench               # 9/9
```

## 🔒 安全边界

- 包内所有工具/命令对数据库默认**只读**；写只走 CLI `--apply`，写前自动快照。
- MCP 只读、无网络监听；宿主负责信任边界。
- 群成员文本用 `memorix.safety.wrap_untrusted` 包裹（结构隔离，不是语义过滤）。

## 📄 License

Apache-2.0。生产代码零改动：本包是从运行中的巡检/裁判系统只读抽出的独立产物。
