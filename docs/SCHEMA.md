# 通用数据库：自定义表 / 缺表也能用（schema 映射）

你的表是「插件自带 + 另设」的没关系。memorix 不要求表名/列名固定；默认用 AstrBot 原生三表，
其他项目用 **显式映射** 或 **自动探测**，缺消息表时只降级对应功能，不崩。

## 1. 三档用法

| 档 | 用法 | 适用 |
|---|---|---|
| 原生 | 不传（默认） | AstrBot `memories/raw_messages/bot_messages` |
| 显式映射 | `--schema schema.json`（或 inline JSON / `Schema` 对象） | 你的插件表、别的项目表 |
| 自动探测 | `--schema auto` | 表名/列名接近常见命名时；SQLAlchemy 变体/业务列名建议显式映射 |

CLI：所有 `--db` 命令都支持 `--schema`；也可用环境变量 `MEMORIX_SCHEMA`。
MCP：`memorix_diagnose` / `memorix_orphan` / `memorix_recall` 接受 `schema` 参数（路径/auto/inline JSON）。

## 1.5 AstrBot self-learning 交接实测（2026-10-21）

生产库：`/root/AstrBot/data/plugin_data/astrbot_plugin_self_learning/messages.db`（DJango? 不，SQLAlchemy 生成，40+ 表）。
用只读快照实测（schema = `examples/astrbot-self-learning.schema.json`）：

- memories **1254**（其中 archived **16**，召回排除后 **1238**）；
- raw_messages **4079**、bot_messages **6173**；
- 显式 DDL：`/sdcard/dsh-work/memories_schema.sql`；交接说明：`/sdcard/dsh-work/memories-schema-note.md`。

**三个坑（写进 schema 才不翻车）：**

1. **时间单位不统一**：`memories.created_at` 是**毫秒**（如 `1792512135055`），
   `raw_messages.timestamp` / `bot_messages.timestamp` 是**秒**（如 `1792512471`）。
   本包 `parse_ts` 会自动按量级归一，但 schema 元数据里应写 `unit: "ms"/"s"` 以免下游误解。
2. **私聊判定**：`raw_messages` 里私聊是 `group_id == sender_id`，群聊才是真实群号。
   `recent_private_context()` 已按这条过滤；不过滤会把群友发言当成用户原话（“认不出人”的根因之一）。
3. **排除 `archived`**：`memory_type='archived'` 是归档态，召回必须排除（默认 `exclude: ["archived"]`）；
   诊断/分布仍统计它，方便看总量。

> 这个库 `auto` 可能识别不出（SQLAlchemy 的 `VARCHAR(255)`、`id INTEGER NOT NULL` 无自增、列名偏业务语义）。
> **建议直接用交接 DDL/显式 `schema.json`**，比自动探测可靠。

## 2. 显式映射示例（只有记忆表）

```json
{
  "name": "my-project",
  "memories": {
    "table": "my_memories",
    "id": "id",
    "content": "body",
    "type": "kind",
    "importance": "weight",
    "created_at": "created_at",
    "group_id": "group_id",
    "user_id": "user_id"
  }
}
```

```bash
memorix diagnose --db my.db --schema schema.json
python -m memorix.retrieval.bench          # bench 不需要你的库
```

只有记忆表时：**diagnose / 衰减 / 意图 / 巩固计划 / recall / eval** 可用；
`status`/`finish` 需要消息表，会返回明确错误（exit 4），不会读错表。

## 3. 显式映射示例（记忆 + 消息）

```json
{
  "memories": {
    "table": "my_memories", "id": "id", "content": "body",
    "type": "kind", "importance": "weight", "created_at": "created_at"
  },
  "raw_messages": {
    "table": "chat_log", "id": "id", "timestamp": "ts",
    "message": "text", "sender_id": "role_id",
    "sender_name": "role_name", "group_id": "group_id"
  },
  "bot_messages": {
    "table": "reply_log", "id": "id", "timestamp": "ts", "message": "text"
  }
}
```

字段可省略：**显式映射里省略的可选列读作 `NULL`/空串**（不会回落到原生列名）；但 `memories` 必须有 `id` + `content`，消息表必须有 `id` + `message`。
写入类命令还要求 `memories.type/importance`（intents 还需 `content`）；缺列时直接 `SchemaError`，**不会写坏库、不会猜**。

## 4. 自动探测

`--schema auto` 会扫 `sqlite_master`：

- 记忆表候选：`memories / memory / long_term_memory / memory_records / knowledge / notes`（也匹配包含这些词的子串）；
- 记忆列别名：`content/text/body/memory/summary/value`、`importance/weight/score/priority/rank`、
  `created_at/created/time/timestamp/ts`、`type/kind/category/label` 等；
- 消息表候选：`raw_messages/messages/chat_messages`、`bot_messages/assistant_messages`；
- 找不到记忆表 → 报错并列出库里有哪些表，提示你写显式映射。

## 4.5 交接 schema 形态（tables/columns）

除上面的扁平映射外，也兼容交接文件里的嵌套形态：

```json
{
  "dialect": "sqlite",
  "path": "/path/to/messages.db",
  "read_only": true,
  "tables": {
    "memories": {"columns": {
      "id": {"type": "integer", "pk": true},
      "content": {"type": "text"},
      "memory_type": {"type": "text", "exclude": ["archived"]},
      "created_at": {"type": "integer", "unit": "ms"}
    }},
    "raw_messages": {"columns": {
      "id": {"type": "integer"}, "message": {"type": "text"},
      "sender_id": {"type": "text"}, "group_id": {"type": "text", "note": "private when group_id == sender_id"},
      "timestamp": {"type": "integer", "unit": "s"}
    }}
  }
}
```

`unit`、`exclude`、`group_id==sender_id` 私聊规则都会被解析并生效；`path` 仍由 `--db` 指定（便于只读快照/测试库）。

## 5. 能力矩阵（缺表时）

| 功能 | 需要 |
|---|---|
| `diagnose` / `orphan` / `decay` / `intents` / `consolidate` / `eval` | memories |
| `recall` / MCP recall | memories；可自动读最近私聊上下文（`user_id`） |
| `status` / `finish` | memories + raw_messages + bot_messages |
| 写库（`--apply`） | memories + type/importance（intents 还需 content）列；缺列即 SchemaError（且先备份） |
| 审计快照 | 只需要配置文件 glob + 台账，与本库无关 |

## 6. 安全

- 表名/列名只允许 `[A-Za-z_][A-Za-z0-9_]*`，防 SQL 注入；值全部参数化。
- 所有 MCP/CLI 默认只读；`--apply` 是唯一写入口，写前自动 DB 快照。
- 自动探测只读 `sqlite_master`，不改库。

## 7. 限制

- 一个逻辑表对应一个物理表；不支持 JOIN/视图/多表合并（需要更复杂时写自定义 `StorageAdapter`）。
- `created_at` 仍按 ms/s/ISO 三种历史口径自动归一（`parse_ts`）。
- 时区/日上限的“日”仍按本地时区（生产同样），需要固定时区时在 adapter 层处理。
