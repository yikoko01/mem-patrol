# M2 方案 · gatekeep 裁判骨架（先方案后实现）

- 依据：指南 §5 M2 + 复核修正版（Decision **无 confidence**、Context 不绑 IM）
- 出口：无 LLM 也能跑桩测试；闸门可组合；影子模式 + 精度升格判据；**有回放集**（judge_cases.jsonl + runner）
- 不碰生产；全部在 `src/memorix/gatekeep/`

## 1. 范围

| 做 | 不做（留 adapter/M3） |
|---|---|
| `parse_decision()`：5 组键名别名 + needs_tools → `Decision{allow,text,reason,needs_tools}` | 326KB 插件里的完整判据 prompt / 人设话术 |
| 闸门组合：enabled / daily cap / min interval / same topic / explicit direction / do-not-interrupt / consult throttle / legacy dice | AstrBot `self.data` / `AstrMessageEvent` / 群快照原地写 |
| `decide(ctx, judge=stub)` → `Outcome{action,decision,reason}`；needs_tools 定向→handoff、非定向→tool_task | 真正发消息、quote、媒体、asyncio 后台任务 |
| `ShadowBook`：calls/hits/samples/precision/升格阈值（≥0.8，至少 10 样本） | 落盘 jsonl/指标聚合（M3） |
| `reviewers/`：空炮检测 `barren_phrase`、检索举证 `absence_claim`（纯函数） | 挂到宿主回复复核链 |
| `prompts/`：判据模板独立成文件 + loader | 热改/AB（M3） |
| 单测：桩 judge、闸门逐道、预算公式、影子、reviewers | 真实 LLM 调用 |

## 2. 与生产对应

| 生产（只读参考） | 本包 |
|---|---|
| `_parse_group_interjection_decision`(4483) | `decide.parse_decision` |
| `_judge_needs_tools`(5425) | `decide.parse_needs_tools` |
| `_group_interject_relative_budget`(4520) | `gates.relative_budget` |
| `_group_interject_judge_consult_allowed`(4567) | `gates.ConsultThrottle` |
| `_group_interjection_allowed`(4595) 的硬闸 | `gates` 里各独立 Gate |
| 骰子路径（judge_decides=False） | `gates.stable_roll` + `LegacyDiceGate` |
| `premature_promise_gate.barren_phrase` | `reviewers/premature_promise.py` |
| `retrieval_witness.absence_claim` | `reviewers/retrieval_witness.py` |
| `ShadowBook`（生产是 jsonl+计数器） | 纯内存 dataclass，落盘留 adapter |

## 3. 已知差异（写进 M2.md）

- 预算函数接收**已过滤**的 `recent_messages`（生产 `_filtered_group_recent_messages` 由 adapter 负责）；
- 闸门不原地改 group dict，只返回结果；状态（consult_at/interject_today）由调用方或 adapter 传入/落盘；
- `link_payload`、atmosphere/pace/rhythm 权重、方向权重等宿主耦合项留 adapter，M2 只保留**确定性硬闸** + 一个可注入的 `weight`；
- `needs_tools` 定向判定用 Context 的 `directed`/`scene_trigger` 字段，不读 IM 事件。

## 4. 验收

```bash
cd /sdcard/dsh-work/memorix
PYTHONDONTWRITEBYTECODE=1 /root/AstrBot/.venv/bin/python -m pytest -p no:cacheprovider
# 目标：≥ M1.5 的 210 + gatekeep 用例全绿
```

- 桩 judge 三态（allow/deny/needs_tools）都可跑；
- 影子 8/10 升格、7/10 不升格；
- 不 import astrbot/sqlite3/网络；生产零改动。
