# optimization-report.md · career-coach 全仓升级优化报告

> 日期：2026-08-03 ｜ 分支：`eng-hardening-2026-08-03`（基于 main `01d42e2`）｜ 提交：`e7bd08d`
> 原则：保守、可验证、可回滚。未执行 push / merge / 部署 / 历史改写。

---

## 1. 范围、环境与基线

- **产品目标**：职跃AI —— AI 求职面试教练（iCAN 比赛 MVP），四条主流程 F1 简历诊断 / F2 JD 匹配 / F3 模拟面试 / F4 能力报告。
- **技术栈**：静态 HTML/CSS/JS 前端（ui/prototype + docs  Pages 副本）；Python 工具链（tools/×13）与 pytest 测试（tests/，200 用例）；GitHub Actions CI。
- **运行环境**：本地开发机（Windows，Python 3.13 venv）+ GitHub Pages（docs/）+ DuMate 工作流平台（外部）。
- **验证命令**（真实存在，来自 ci.yml 与 tests/）：
  - `python -m pytest tests/ -q`（单测）
  - `node --check ui/prototype/js/*.js`（JS 语法）
  - `python tools/validate_schema.py --schema contracts/*.schema.json --instance <fixture>`（Schema 校验）
  - 未发现 lint / type-check 配置（无 ruff/mypy/tsconfig）。
- **基线 Git 状态**：main `01d42e2`，工作树干净；远程 origin/main `3cbe3b4`（本地领先 1 个 v3 合规提交，未推送）。

### 基线表

| 命令 | 基线结果 | 可复现 |
|---|---|---|
| `pytest tests/ -q` | ❌ 收集期 INTERNALERROR（test_qianfan_embedding sys.exit(2)；3 个智谱文件 ImportError: zhipuai）；`--ignore` 排除后 200 passed | 是 |
| `node --check` ×6 | ✅ 全部通过 | 是 |
| 静态资源可达（http.server + curl ×15） | ✅ 15/15 200 | 是 |
| 密钥扫描（grep 模式） | ❌ 3 处硬编码智谱 API Key | 是 |

## 2. 架构 / 模块摘要

| 模块 | 职责 | 风险 | 验证 |
|---|---|---|---|
| ui/prototype + docs | 前端原型与 Pages 副本 | 低（本轮 v3 已回归） | node --check、curl |
| contracts/ | 四份 JSON Schema + scoring | 低 | validate_schema |
| tools/ | 抽取/匹配/面试/评分/脱敏等 13 个 CLI 工具 | 中 | pytest |
| tests/ | 200 用例 + 凭证依赖在线测试 | 高（本轮修复） | pytest |
| .github/workflows/ci.yml | CI 流水线 | 中（本轮修复） | 人工审查 |
| workflows/、prompts/、deliverables/ | 工作流定义、提示词、比赛交付物 | 冻结不动 | — |

## 3. 已实施改动（批次 1：凭证安全 + 测试可执行性）

| 问题 | 根因 | 文件 | 行为影响 | 验证证据 | 回滚 |
|---|---|---|---|---|---|
| **P0** 硬编码智谱 API Key ×3 并进入 git 历史与远程 | 在线测试脚本直接字面量写入 Key | tests/test_zhipu_quick.py、test_zhipu_threshold.py、test_embedding_models.py | Key 改为 `os.environ.get("ZHIPUAI_API_KEY")`；缺省时整模块 skip | `grep -rn "<key前缀>" tests/` → 0 匹配；pytest 200 passed/4 skipped | `git revert e7bd08d`；Key 需轮换（见 §4） |
| **P1** pytest 收集期崩溃 | test_qianfan_embedding.py 缺凭证时 `sys.exit(2)`；3 个智谱文件顶层硬 import zhipuai | 上述 3 文件 + tests/test_qianfan_embedding.py | 缺包/缺凭证 → `pytest.skip(allow_module_level=True)`；凭证存在时行为不变 | 修复前：INTERNALERROR / collection errors；修复后：`200 passed, 4 skipped`，exit 0 | 同上 |
| **P1** CI 吞掉测试失败 | ci.yml pytest 行尾 `\|\| true` | .github/workflows/ci.yml | 移除 `\|\| true` 与冗余收集回显；测试失败将使 CI 变红（skip 守卫保证无凭证环境可通过） | 本地模拟 CI 无凭证环境：exit 0 | 同上 |

不变式（本批绝不破坏）：环境变量名（QIANFAN_AK/SK、ZHIPUAI_API_KEY 语义）、测试断言、fixtures、Schema、前端 DOM/数据契约 —— 全部未变。

## 4. 未实施项与需授权事项

| 事项 | 风险 | 为何未改 | 建议动作 |
|---|---|---|---|
| **智谱 Key 轮换 + git 历史清洗** | P0 | 轮换需在智谱平台操作；历史清洗需 force-push，契约禁止 | 立即在智谱控制台作废该 Key 并重新生成；如需清史，授权后用 `git filter-repo` + force-push（需协调协作者） |
| 远程 main 落后于本地（v3 合规提交 `01d42e2` 未推送） | P2 | 本任务契约禁止 push | 人工确认后推送 main 与本分支 |
| 凭证依赖测试在 CI 中恒为 skip | P2 | CI 未配置 ZHIPUAI_API_KEY Secret | 如需在线测试进 CI，配置 GitHub Secret 并加专门 job（需授权） |
| pytest 版本漂移（requirements 锁 `<9.0`，本地 venv 为 9.1.1） | P2 | 非缺陷；升级需另行验证 | 下次依赖窗口统一 |
| test_voice_browser.py 返回非 None（11 条 PytestReturnNotNoneWarning） | P2 | 有警告无失败，证据不足以改语义 | 待验证假设：改为 assert 或保留约定 |
| Playwright 四视口渲染回归 | — | Chromium 下载失败（`__dirlock` trash 错误，3 次重试） | 人工复跑：`python -m playwright install chromium`，再跑 `python tools/regression_check.py`（需先起 http.server） |

## 5. 安全复核结果

- 密钥扫描（api_key/secret/token/password/Bearer 模式，全仓 *.py/*.js/*.json/*.md/*.yml/*.html）：除已修复 3 处外，未发现新泄露；ci.yml 自带扫描步骤仅命中其自身规则文本。
- .env.example 存在且为模板；未发现 .env 被跟踪（.gitignore 含 .env）。
- 前端：无内联 eval/innerHTML 注入面新增；mock 数据为合成样本（fixtures-synthetic）。
- 注入面：tools/ 为本地 CLI，未接收网络输入；JD 注入防护已在产品设计内（F2 文案与测试覆盖）。
- 不确定项：远程仓库历史中仍含明文 Key（§4）；DuMate 平台侧配置不在本仓可视范围。

## 6. 性能结果

本批无性能改动（无基线证据支持的热点，按契约不引入）。

## 7. 完整验证矩阵

| 命令 | 退出状态 | 结果 | 说明 |
|---|---:|---|---|
| `pytest tests/ -q`（修复前） | 2 | 收集期 INTERNALERROR / 3 collection errors | 基线失败，可复现 |
| `pytest tests/ -q`（修复后） | 0 | **200 passed, 4 skipped**, 37.33s | 4 skipped = 凭证依赖在线测试，符合预期 |
| `node --check ui/prototype/js/*.js` ×6 | 0 | 全部通过 | 本批未改 JS，复跑确认 |
| 密钥复扫 `grep -rn "<key前缀>" tests/` | 1（无匹配） | 0 处残留 | 工作树已清除 |
| `git diff main` 审计 | — | 5 文件，+36/-12，无格式化噪声、无密钥新增、无锁文件漂移 | 人工审查 |
| Playwright 渲染回归 | BLOCKED | Chromium 安装失败 ×3 | 复跑命令见 §4 |

## 8. 合并前人工检查清单

- [ ] 智谱 Key 已在平台轮换（作废旧 Key）。
- [ ] 审查 `git show e7bd08d`：仅 5 文件，skip 守卫逻辑符合预期。
- [ ] CI 首次运行确认：无凭证环境下 200 passed + 4 skipped 变绿。
- [ ] 决定是否为 CI 配置 ZHIPUAI_API_KEY Secret 以启用在线测试。
- [ ] 决定 v3 UI 提交 `01d42e2` 与本分支的推送/合并顺序。
