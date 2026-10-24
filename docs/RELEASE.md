# Release（0.2.4，GitHub 已发布；PyPI 未上传）

## 1. 当前发布门（诚实口径）

| 项 | 状态 |
|---|---|
| 单元/回归测试 | **368 passed** |
| eval（recall 6 + judge 9 + policy 9） | **24/24** |
| synthetic §10.3 fixture | **6/6** |
| **production §10.3 replay（current）** | **6 PASS / 0 FAIL**（`verify/prod-replay-post-memory-20261021.md`） |
| **production §10.3 replay（historical point）** | **5 PASS / 1 DATA_GAP**（当时语料确实没有对比记忆，见 `verify/prod-replay-20261021.md`） |
| 生产代码改动 | **0**；仅新增一条记忆 #1256（已备份，见下） |
| 许可证 | **MIT**（0.2.4 起；0.2.0/0.2.1 为 Apache-2.0） |
| 发布动作 | **GitHub Release `v0.2.4` 已发布**；**PyPI `mem-patrol 0.2.4` 已上传**（MIT） |

> 2026-10-22 已按 B 方案补记忆 #1256（manual_remember, importance 9）：
> `【石头门·8-23 与 8-19 难度对比】8-19 有明确根因（scoped storage/InjectActivity）；8-23 是盲改期（无 logcat、不可复现），所以更难。`
> 当前全量回放 **6/6**；历史点时间回放仍是 **5/6 + DATA_GAP**（历史语料不能靠事后补记忆改写）。

**GitHub**：<https://github.com/yikoko01/mem-patrol/releases/tag/v0.2.4>  
**PyPI**：<https://pypi.org/project/mem-patrol/0.2.4/>  
**CI**：3.10/3.11/3.12 全绿（`952ff73`）。

**生产写入备份**：`/sdcard/dsh-work/backups/live-messages-before-version-memory-20261022-0002.db`（integrity_check ok）。
回滚（停 bot 后）：`delete from memories where id=1256;` 或整体恢复该 backup。

## 1.5 已发布的 GitHub Release

- repo: <https://github.com/yikoko01/mem-patrol>
- tag: `v0.2.4`（commit `952ff73`）
- assets: `mem_patrol-0.2.4-py3-none-any.whl`、`mem_patrol-0.2.4.tar.gz`
- repo description / topics 已设置
- v0.2.0/v0.2.1 是历史 release（Apache-2.0；v0.2.0 的 3.10 CI 曾红）；v0.2.4 起 MIT，CI 全绿

## 2. 本地产物（已验证）

```bash
cd /sdcard/dsh-work/memorix
python -m build
# dist/mem_patrol-0.2.4-py3-none-any.whl
# dist/mem_patrol-0.2.4.tar.gz

python -m pip install --no-deps --prefix /tmp/memorix-prefix dist/mem_patrol-0.2.4-py3-none-any.whl
PYTHONPATH=/tmp/memorix-prefix/lib/python3.12/site-packages /tmp/memorix-prefix/bin/memorix --version
# mem-patrol 0.2.4
```

## 3. 发布到 GitHub（需要 remote；/sdcard 上无法 git init）

```bash
cd /sdcard/dsh-work/memorix
git init -b main          # 在普通文件系统/本地 clone 上执行（/sdcard 的 FUSE 不支持写 git 对象）
git add -A && git commit -m "mem-patrol 0.2.4"
git tag -a v0.2.4 -m "mem-patrol 0.2.4"
git remote add origin <your-repo-url>
git push origin main --tags
```

> 本仓库位于 `/sdcard`（FUSE），`git init/add` 会报 `failed to insert into database`；
> 发布前先 `cp -a memorix ~/memorix && cd ~/memorix` 到普通磁盘，或直接在 GitHub 建仓后 clone。

> v0.2.4 修复了 Python 3.10 CI 的 `tomllib` 测试导入；v0.2.0 的 GitHub Release 已存在。

push `v*` tag 后 `.github/workflows/release.yml` 会：测试 → 构建 wheel/sdist → 安装 smoke → GitHub Release 挂 artifacts。

## 4. 发布到 PyPI（需要凭据）

```bash
python -m pip install twine
python -m twine check dist/*
python -m twine upload dist/*        # 需要 PYPI_TOKEN / trusted publishing
```

## 5. 不要做的两件事

1. **不要接具体宿主 adapter 再发布**：保持独立包 + `raw_messages` 回放；接特定宿主会把包重新绑回它的配置/flag 体系。
2. **不要在没有 remote/凭据时声称已发布**：本地 tag/artifacts 是 release-ready，不等于 registry 上可见。

## 6. 已知局限（release notes 应带）

- Lexical only；无 embedding；真实 §10.3 case3 暴露“版本对比记忆缺失”的数据缺口，不是算法 bug。
- 全快照下自指记忆（记录“用户在做召回验证”的 meta 记忆）可能排前；点时间回放可避免，生产实时召回需要用同一套 `as_of`/上下文策略。
- 无 IM adapter、无网络/鉴权；MCP 只读。
