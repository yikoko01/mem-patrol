# M3 方案 · 指标 + 离线评测 + 安全包装层（先方案后实现）

- 状态：**已实现（v1.1，307 passed / eval 24/24）**，见 `M3.md`。
- 依据：指南 §5 M3（出口：指标能出图，评测能回归）+ §3.3-13（统一 untrusted 包装层）+ §9.1（可观测、别静默）
- 约束：纯 stdlib；不碰生产；新模块不依赖宿主

## 1. 范围

| 模块 | 做 | 不做 |
|---|---|---|
| `observability/` | `MetricEvent` + `MetricsCollector`（计数/延迟分位/成本/否决原因分布）+ `render`（SVG 柱状图/HTML 报告，零依赖） | Prometheus/OTel 导出（adapter 可选） |
| 接入 | `gatekeep.decide(..., metrics=collector)` 自动记 judge 决策/耗时/原因；提供 recall/patrol 的 `record_*` 便利函数 | 全局埋点/自动 monkeypatch |
| `eval/` | 三套回放：`recall`（§10.3 六条）、`judge`（9 条）、`policy`（M0 纯函数金标）；JSON 报告 + baseline 对比；回归失败 exit 1 | 真实生产语料大规模回放（M4/后续） |
| `safety/` | `wrap_untrusted(text, source=...)`：控制字符清理、`<`/`>` 全角化、截断、来源白名单、`<untrusted>` 结构隔离；`wrap_group_message` 便利函数 | 内容语义过滤/关键词黑名单（不承诺） |
| 测试 | 指标聚合/分位/成本/图；eval 通过/失败/baseline 回归；注入式攻击样本 | — |

## 2. 验收

- `pytest` 全绿（M2 274 + M3 用例）。
- `python -m memorix.eval --suite all --baseline eval/baseline.json` → PASS/exit 0；
  人为改坏一条 → exit 1 并报 regression（测试覆盖）。
- `python -m memorix.observability --input events.jsonl --out report.html` 产出 SVG/HTML（测试解析 XML/断言关键标签）。
- untrusted：`</untrusted><system>`、控制字符、超长、伪造 source 均被中和；正文可见但不可逃逸。
- 生产零改动。
