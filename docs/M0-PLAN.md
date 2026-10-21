# M0 方案 · memorix 纯函数内核（先方案，后动手）

- 依据：`/sdcard/dsh-work/project-guide-patrol-judge-20261020.md` §5 M0
- 输入：`/sdcard/dsh-work/verify/verification-summary-20261020.md`（已独立复核，按修正版执行）
- 状态：**方案先行 → 已实现（见 docs/M0.md，109 passed，独立验收 PASS（v1.0→v1.2））**。本目录是新建的独立产物；**不修改 `/root/AstrBot` 任何文件**。
- 定位：M0 只做 `memorix`（记忆巡检内核）；`gatekeep`（裁判骨架）从 M2 开始。

## 1. 目标与出口

**目标**：把巡检里可确定性验证的规则抽成**纯函数**，脱离 AstrBot、脱离生产库可单测。

**出口（可机器验证）**：
1. `cd /sdcard/dsh-work/memorix && /root/AstrBot/.venv/bin/python -m pytest -q` → 全绿，收集数 **> 0**（现有脚本是 0，不算数）。
2. `src/memorix/policy/` 下 0 处 `import astrbot` / `sqlite3` / `openai` / `requests`，0 处 `/root/`、`/sdcard/` 字面量。
3. 三个隔离维度可跑：不设 `PYTHONPATH=/root/AstrBot`、`python -I` 下可 import（只依赖 stdlib）。
4. 生产树零改动：`/root/AstrBot` 无 mtime/内容变化（`find -newermt` + `git diff` 校验）。
5. `docs/M0.md` 给出「生产位置 → 新模块/函数 → 行为差异」映射表。

## 2. 范围

### 做（M0）
| 生产来源（只读参考） | M0 产物 | 说明 |
|---|---|---|
| `memory_patrol.py:356-370 _parse_ts` | `policy/timeparse.py::parse_ts` | 原样保留 ms/s/ISO 混口径归一 |
| `memory_patrol.py:137-176 build_sender_name_map/display_sender` | `policy/senders.py` | 入参从 sqlite conn 改为 `Iterable[Mapping]`，去掉 DB 依赖 |
| `memory_patrol.py:373-398 _detect_orphans` | `policy/orphan.py::detect_orphans` | 只报告语义保留；ORPHAN_MEMORY_TYPES 作参数 |
| `memory_patrol.py:899-995 _file_md5/_load/_save/cmd_audit` | `policy/audit.py::classify_audit` + `adapters/files.py` | 纯比对核心抽出；md5/glob/落盘留 adapter |
| `PATROL_SOP.md:169-176`（无代码） | `policy/decay.py::plan_decay` | **新写**：>30 天且 importance≤3 减 1；到 0 改 archived；contract 永不 |
| `PATROL_SOP.md:169-176`（无代码） | `policy/consolidation.py::plan_consolidation` | **新写**：最近 5 条 episodic、主题≥2 次、选最完整升格；**语义键/排序做成注入点** |
| `memory_patrol.py:547-599 cmd_intents` | `policy/intents.py` | 过期判定 + 降级算术，纯函数化 |
| `memory_patrol.py:414-449 _verify_writes` | `policy/finish_gate.py::verify_finish` | 收尾闸门判定纯函数化（错误文案保持逐字一致） |
| 3 个脚本式测试 | `tests/test_*.py` | 改写成 pytest 原生；保留原断言语义 |

### 不做（留给后续里程碑）
- `StorageAdapter` + sqlite 实现 + 路径参数化 CLI → **M1**
- `cmd_profile*`（画像回流 90 行过程混了校验/INSERT/索引/备份）→ M1 先拆副作用
- `cmd_hooks/hook_log`、`hook_triggers` DDL、cron 交互 → M1
- 裁判 `gatekeep`、Context/Decision、影子模式 → M2
- 指标、离线评测、MCP、打包发布 → M3/M4

## 3. 目录与契约

```
memorix/
  pyproject.toml          # setuptools；[tool.pytest.ini_options] pythonpath=["src"]
  README.md
  docs/M0-PLAN.md         # 本文件
  docs/M0.md              # 完成后填映射表 + 运行结果
  src/memorix/
    __init__.py
    models.py             # MemoryRecord / OrphanRecord / DecayAction / Promotion / IntentReport / AuditResult / FileState
    policy/
      timeparse.py  senders.py  orphan.py  audit.py
      decay.py  consolidation.py  intents.py  finish_gate.py
    adapters/
      files.py            # 文件指纹/快照读写（唯一允许 IO 的 M0 模块，供 audit 用）
  tests/
    conftest.py
    test_timeparse.py  test_senders.py  test_orphan.py
    test_audit.py  test_decay.py  test_consolidation.py
    test_intents.py  test_finish_gate.py  test_purity_guard.py
```

**设计约束**
- `policy/*` 纯函数：不碰文件/网络/DB/全局可变状态；时间、路径、配置全由参数传入。
- 行为差异必须显式记录（见 §5），不悄悄"顺手修"。
- 语义判断（巩固的"主题/最完整"、画像归并）通过**注入 callable** 或延后到 LLM/adapter，不在纯函数里编造启发式。

## 4. 测试计划

| 测试 | 来源 | 覆盖 |
|---|---|---|
| `test_timeparse.py` | 新 | None / 秒 / 毫秒 / ISO / 数字字符串 / 非法串 / 边界 1e11 |
| `test_senders.py` | 移植 `test_sender_labels.py` 11 项 | 空名回填、同名去重、私聊兜底、`用户{id[:6]}` |
| `test_orphan.py` | 移植 `test_orphan_gate.py` 判定核心 | 无 finish 记录→空、created_at 混口径、类型过滤、排序 |
| `test_audit.py` | 新（按 cmd_audit 语义） | 内容未变+mtime 刷新→benign；内容变+台账点名→刷新；内容变+未点名→suspicious 且不刷新；首次运行；容差边界 |
| `test_decay.py` | 新（按 SOP） | 30 天边界、importance 3/4/7、contract 豁免、到 0 归档、archived 幂等 |
| `test_consolidation.py` | 新（按 SOP + 注入） | 最近 5 条窗口、同主题≥2、rank 选择、上限 9、非 episodic 拒绝、主题键注入 |
| `test_intents.py` | 新（按 cmd_intents） | 格式解析、到期/未到期/坏格式、降级 importance、0-1 小数口径、内容前缀 |
| `test_finish_gate.py` | 新（按 _verify_writes） | 缺 mem-ids/ledger、none 特例、记忆不存在、早于上轮、台账搜不到、全通过 |
| `test_purity_guard.py` | 新 | policy 无宿主/DB/网络/绝对路径导入；`python -I` 可导入 |

预计 **55–70 个 pytest 用例**（含参数化）。

## 5. 行为差异（必须写进 M0.md，不隐藏）

| 项 | 生产行为 | M0 行为 | 理由 |
|---|---|---|---|
| `build_sender_name_map` | SQL `GROUP BY sender_id` 取任意一行名 | 按输入顺序取**首个非空名** | 纯函数确定性；生产 SQL 本身未定义顺序，语义等价 |
| `save_state` | 非原子写、无锁 | adapter 层用 tmp+`os.replace` 原子写 | 纯改进，M0 只提供 adapter，不改变调用语义 |
| 衰减 | 无代码，SOP 散文 | 按 SOP 字面实现；额外跳过 `archived`（防负数/重复） | 幂等保护；与 SOP 不冲突，需在 M0.md 标明 |
| 巩固 | 无代码，LLM 判断"最凝练" | 纯函数只做窗口/分组/选择/升格算术；`theme_key`/`rank_key` 必须注入 | 不在代码里伪造语义；生产由 LLM/adapter 提供 |
| 审计首次运行 | 快照为空 → 未点名文件全报 suspicious | 同生产（保留首次全报） | 不改变安全语义 |
| `intents` 0-1 importance | `imp<=1 → *10` 兜 ORM 口径 | 原样保留 | 生产数据混口径 |

## 6. 风险与对策

1. **created_at/importance 脏数据**：纯函数不清理，只归一；测试用生产真实形态（ms/s/ISO、文本 importance）做样例。
2. **巩固语义无法凭空抽**：用注入点 + 文档标记，M0 不承诺"语义质量"；语义评测留 M3。
3. **测试改写可能丢断言**：逐项对照原脚本 `check()` 名称，M0.md 列出 13/11/31 的映射；未移植的（profile 31 项）显式标 M1。
4. **误碰生产**：所有命令只读 `/root/AstrBot`；写只落 `/sdcard/dsh-work/memorix`；收尾用 `find -newermt` 证明零改动。
5. **写工具在 /sdcard 的 EPERM**：统一用 bash heredoc 落盘（已实测 write 工具失败）。

## 7. 待拍板的 5 个决定（§6）与 M0 的关系

| # | 决定 | M0 是否依赖 | 本次默认（可推翻，推翻只废脚手架） |
|---|---|---|---|
| 1 | 纯 Python vs TS | **是（语言）** | **纯 Python**（复用现有代码/测试最省事；MCP 侧后续可薄封装） |
| 2 | 两仓库 vs monorepo | 否 | 先建独立 `memorix/`；gatekeep 到时若选 monorepo，平级加目录即可 |
| 3 | 保留「LLM 按 SOP 自己执行」vs 编译成确定性 CLI | **否（M1/M2 才分叉）** | 倾向**混合**：确定性状态机 + 只在"提炼"格调 LLM，SOP 散文保留为兜底 |
| 4 | 裁判是否绑具体 IM | 否（M2） | 通用 `Context`（不绑 QQ/AstrBot） |
| 5 | 开源协议 / 社区改判据 | 否 | 暂定 Apache-2.0（附贡献者改判据需评测的 policy） |

**结论：M0 只在 #1 上押了「Python」；#3/#4/#5 不阻塞 M0。** 若 #1 改 TS，M0 的**语义与测试用例仍可复用**，仅 Python 实现作废。

## 8. 执行顺序（本方案批准后）

1. 建骨架 + pyproject + models + purity guard。
2. 先抽 3 个「代码里已存在」的：`parse_ts` → `senders` → `orphan`（移植原断言）。
3. 再抽 2 个「有代码但需拆 IO」的：`audit` 比对核心、`finish_gate` 判定。
4. 最后写 3 个「只有 SOP」的：`decay` / `consolidation`（注入点）/ `intents`。
5. 跑隔离 pytest → 修到全绿；填 `docs/M0.md`；做生产零改动证明。
6. 交给独立 verifier 复核（新开 teammate，不改 M0 文件，只写 `verify/m0-verification.md`）。
