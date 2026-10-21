# 插话策略：判定优先 + 轻节流（不静默）

目标：**读懂上下文后，有自然插入点就接话；节流只防刷屏/排队，不替裁判判死。**

## 1. 流水线（gatekeep.decide）

```
触发消息
 → 硬闸（enabled / 明确在跟别人说 / 别插 / 日上限 / 最小间隔 / 同话题 / 秒级咨询节流）
 → LLM judge（读上下文、记忆、引用；输出 {should_reply,text,reason,needs_tools}）
 → allow 且 needs_tools=false → 发送
   allow 且 needs_tools=true  → directed: handoff 回主 agent；非定向: tool_task 后台查
   deny / invalid → dropped（带 reason）
```

关键语义：

- **裁判是决定者**：只要过了硬闸且 judge 说 `should_reply=true`，就会说；没有第二道“概率/字数/话术”否决。
- **定向消息（@/回复/叫名字/`addressed_to_bot`）**：跳过全部 ambient 闸 + consult，直接给 judge。
- **节流**只限制频率，不判断内容：
  - `group_interject_judge_min_consult_seconds`：同一群最小裁判咨询间隔（防消息链排队）；
  - `group_interject_min_interval_minutes`：两次“已发送”之间的最小间隔（防刷屏）；
  - `group_interject_max_daily`：每日上限；
  - `group_interject_same_topic_cooldown_minutes`：同话题冷却（默认 0=关）；
  - `group_busy_timing_enabled`：热闹时段只降权（只在 legacy 骰子路径参与，judge 路径不否决）。

## 2. 默认值（chat / both）

| 键 | chat | both | 说明 |
|---|---|---|---|
| `enable_group_interjection` | **true** | **true** | 不静默 |
| `group_interject_max_daily` | 30 | 30 | 防刷屏 |
| `group_interject_judge_decides` | true | true | 交给 judge，不掷骰子 |
| `group_interject_judge_min_consult_seconds` | 10 | 10 | 轻咨询节流 |
| `group_interject_min_interval_minutes` | 1 | 1 | 说话间隔 |
| `group_interject_same_topic_cooldown_minutes` | 0 | 0 | 同话题不锁 |
| `group_busy_timing_enabled` | true | true | 只降权 |

`project` profile：`enable=false`、`max_daily=0`（项目面不需要插话）。

## 3. “AI 还是不说话”排查顺序

1. `enable_group_interjection` 是否为 true；
2. `group_interject_max_daily` 是否 0 或已达上限（需要 adapter 维护 `interject_day/interject_today`）；
3. 是否被“明确在跟别人说/别插”硬闸挡（看 trace 的 `reason`）；
4. judge 是否返回 `should_reply=false` 或空 `text`（看原始 JSON/reason）；
5. 是否 `needs_tools=true`（走 handoff/tool_task，不是 judge 直接发）；
6. consult/min-interval 是否太严（把 10/1 调小或 0）。

## 4. 隐藏 bug 修复（本轮）

- **@bot 被当成“在跟别人说”**：新增 `Context.addressed_to_bot`；@/回复 bot 走定向快路径，不再被 `explicit_direction` 误杀。
- **时钟回拨/未来时间戳导致永久静默**：`MinIntervalGate`/`SameTopicGate`/`ConsultThrottleGate` 对 `last > now` 一律 fail-open（并重置 consult 记录）。
- **收尾游标可越界/回退**：`finish` 拒绝 `user_end > 库内最大 id` 或回退游标（宁可重记，不可倒退）。
- 回归测试覆盖：chat/both 默认能说话、@bot 定向、三种未来时间戳、finish 越界/回退。

## 5. 调参建议

- 想更活跃：`daily 50`、`consult 5`、`min_interval 0`，judge prompt 明确“有自然插入点就说”。
- 想更克制：`daily 10`、`consult 30`、`min_interval 3`；不要关 judge 改回骰子。
- 不要把 `enable_group_interjection` 设 false 当“降噪”，那会让 AI 永不接话——用日上限/间隔。
