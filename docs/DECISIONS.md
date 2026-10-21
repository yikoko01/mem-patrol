# 已拍板决定（2026-10-21）

用户回复「按默认」，采纳 2026-10-20 交接文档中的 5 条建议默认：

| # | 决定 | 拍板值 |
|---|---|---|
| 1 | 语言/栈 | **纯 Python**（stdlib 优先；MCP 后期薄封装） |
| 2 | 发布粒度 | **先独立 `memorix/`**；`gatekeep` 到时平级加目录（兼容 monorepo/两仓库） |
| 3 | 巡检编排（最关键） | **混合**：确定性状态机 `audit→status→extract→apply→consolidate→finish`；LLM 只在「提炼」格出现；自由 SOP 保留兜底 |
| 4 | 裁判是否绑 IM | **通用 Context**（不绑 QQ/AstrBot），M2 再落地 |
| 5 | 开源协议/社区改判据 | **Apache-2.0**；判据改动须带离线评测（M3 后） |
| 6 | 召回打分器是否一开始做双档（2026-10-21 指南追加） | **先 lexical（零依赖，可选 jieba 锚定），保留 `vector` provider 接口**；两档共用 §10.3 六条用例（M1.5 落地） |

## 对 M1 的直接约束

- 第 3 条落地为：CLI 只做确定性步骤；「提炼」输出/输入走 JSON，CLI 负责校验与落库；
  `consolidate` 只提供 `--show`（给 LLM 的候选窗口）与 `--apply-file`（校验后的计划），不在代码里猜语义。
- 第 1 条：不引第三方运行时依赖（M1 仍只用 stdlib；pytest 仅测试期）。
- 第 4 条：M1 不引入任何 IM 类型；Context 定义留到 M2。
- 第 5 条：先按 Apache-2.0 保留（LICENSE 待 M4 发布前补全）。

## 本次「诊断修复」的口径

用户指示「文件改动是对其进行诊断修复」。执行口径：

1. **诊断**：对生产 `messages.db` 做**只读**诊断（先做一致性快照到 /tmp，再分析）；
   输出 `verify/production-diagnosis-*.md`，列出可验证问题与建议修复。
2. **修复**：在 **memorix（新产物）** 里实现修复路径（`intents --apply` / `decay --apply` /
   `finish --apply` / `audit --apply` / `consolidate --apply-file`），并在**副本**上验证修复可执行、可回滚。
3. **不直接修改生产**：`/root/AstrBot` 的代码与数据都不动（指南 §8-6 明令）；生产修复需另行显式授权。
