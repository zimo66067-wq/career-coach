# 项目交接与复跑文档 · career-coach（职跃AI）

> **这份文档要解决的问题**：换一个账号、换一台机器，从零 `clone` 之后，能独立把本项目
> **装起来、配置好、跑通全部测试**，并且明确知道"哪一步不是敲命令能解决的、需要人工"。
>
> 成文日期：**2026-09-22**。代码基线：远端 `main` = `82b0eee`（本机 HEAD 另有一笔 `b0b6951`，见 §2.3）。
> 本文档自身在仓库内，且**登记在 `contracts/living-docs.json` 的 living 清单**里 —— 它的每条路径引用
> 都要真实存在，改完必须跑门禁第 10 步。

---

## 0. 先读这三条（不知道就会踩）

**① 虚拟环境不入库。** `.venv-audit/` 是开发机上的虚拟环境（**275 MB**），**没有被 git 跟踪**，
`clone` 之后**不存在**。所以必须自建（§3），而且**不要**用系统 Python 直接跑 `pytest` —— 会缺 `flask`、
`jsonschema`、`psycopg` 等依赖，报一堆 `ModuleNotFoundError`。

**② 仓库外还有一层工具，`clone` 拿不到。** 本项目的"全量门禁"脚本 `gate8.sh`、它的日志、
真实密钥文件 `local-secrets.env`、以及几个线上/真模型探针，都放在**仓库的上一层目录**
（本机是 `…/new-chat/work/`，与仓库目录 `career-coach-audit/` **平级**）。**它们不随仓库分发。**
本文 §4.4 给出了这 18 步的**等价命令**，可以在新环境独立复跑 —— 这是本文最重要的一节。

**③ `README.md` 的「跑测试」一节已过期。** 它写的是 `pip install -r tools\requirements.txt`，
而 `tools/` 整层已在 Phase 7 删除（现在由门禁第 15 步保证"零残留"）。真正的依赖文件是仓库根的
`requirements.txt`。同理 `README.md` 的「目录导航」里仍列着 `tools/`。**以本文档为准，不要照抄 README 那条命令。**

---

## 1. 环境要求

### 1.1 依赖矩阵与校验命令

| 项 | 要求 | 本机实测 | 校验命令 |
|---|---|---|---|
| 操作系统 | Windows 10/11、Linux、macOS 均可（无平台专有代码） | Windows 10 | — |
| Python | **3.10 或 3.11**（本机 venv 3.10.11；CI 用 3.11） | 3.10.11 | `python -V` |
| Node.js | **≥ 20**（CI 用 20；本机 22.22.2）。**仅前端契约测试需要** | 22.22.2 | `node -v` |
| pip | 随 Python 提供 | — | `python -m pip -V` |
| git | ≥ 2.30 | 2.55.0 | `git --version` |
| Node 包管理器 | **不需要** —— 仓库没有 `package.json`，也没有 `node_modules` | — | — |
| 系统级依赖 | **无** —— 无编译器、无外部数据库、无 Redis | — | — |

### 1.2 三个「其实不需要」

跑通**全部测试**，不需要：

1. **任何密钥** —— `ZHIPU_API_KEY` 等只用于「真模型复测」这类可选脚本（§4.5）。
2. **任何数据库** —— 本地默认走 SQLite（Python 内置），且 `tests/conftest.py` 会自动把
   `RESUME_DB_PATH` 指向一次性临时目录并 `init_db()`，与你的机器状态隔离。
3. **联网** —— 18 步门禁里没有一步会外呼（唯一外呼的是"生产探针"，它**不在**门禁里）。

### 1.3 可选依赖（只在特定场景需要）

```bash
# 只有跑截图脚本 scripts/capture_mobile_ui.py 才需要（首次约 150 MB）
.venv-audit/Scripts/python.exe -m playwright install chromium
```

---

## 2. 仓库信息

### 2.1 地址、分支、基线

| 项 | 值 |
|---|---|
| 仓库地址 | `https://github.com/zimo66067-wq/career-coach.git` |
| 可见性 | **公开** —— `clone` 不需要任何凭据（推送才需要 collaborator 权限） |
| 默认/工作分支 | `main` |
| 交接时远端 main | `82b0eee` |
| 交接时本机 HEAD | `b0b6951`（比远端多一笔台账更正，**未推送**） |
| 跟踪文件数 | 478（2026-09-22 实测） |

**为什么本文不写死自身的 commit**：文档一旦提交，它自己就改变了 HEAD，写进去的 hash 立刻过期。
**复跑时以命令输出为准**：

```bash
git rev-parse HEAD                       # 本地 HEAD
git ls-remote origin refs/heads/main     # 远端 main（判"推没推上去"只认这一条）
```

### 2.2 目录结构概览

括号内为 2026-09-22 的文件计数，**仅作规模参考**（会随开发漂移）。

```text
career-coach/
├── api/              13 项   HTTP 层（单函数分发；handlers/ 下按 WF 分文件）
├── domain/           20 项   领域规则（纯逻辑，不碰 DB 与框架）
│   └── internal/             层内机制件（无仓库内依赖，硬约束见 tests/test_layering.py）
├── providers/         5 项   外部服务适配（模型路由 / OCR / 单位数据）
├── repositories/     10 项   表级读写（**唯一拼 SQL 的地方**）
├── services/         11 项   编排与事务边界
├── contracts/         8 项   4 个 JSON Schema + scoring.md（冻结层）+ living-docs.json
├── scripts/          27 项   判据与工具（每个脚本自身就是一条门禁）
├── tests/            77 项   pytest 用例 + 15 个 Node 契约测试 + fixtures-synthetic/
├── public/           21 项   前端 canonical（**Vercel 生产静态根**）
├── docs/             55 项   设计/技术文档 + GitHub Pages 发布镜像
├── prompts/                  提示词模块（resume / match / interview / plan）
├── workflows/         7 项   WF-01~06 工作流定义（DuMate 侧实现）
├── tasks/                    任务看板规则
├── handoffs/                 跨 Agent 交接文件
├── deliverables/             提交包与证据材料
├── data/                     本地运行态数据
├── app.py                    ← 根目录候选入口（把 api/index.py 的 app 重导出）
├── requirements.txt          ← **唯一**依赖清单
├── vercel.json               部署配置（重写 / maxDuration）
├── .env.example              环境变量模板（**变量清单的唯一来源**）
├── README.md HANDOFF.md CHANGELOG.md SECURITY.md
└── .github/workflows/ci.yml  GitHub Actions CI
```

### 2.3 关键配置文件

| 文件 | 作用 | 改动注意 |
|---|---|---|
| `requirements.txt` | 唯一依赖清单（无 `pyproject.toml`，已删除，**勿再加**） | 加依赖要同步 CI |
| `.env.example` | 环境变量模板。**与代码读取点双向一致**由门禁第 12 步强制 | 代码新读一个变量，必须补进这里，否则门禁红 |
| `vercel.json` | 部署重写规则 + `maxDuration=60`；静态根是 `public/` | 新增 `/api/xxx` 路由必须同步加 `source`（门禁第 5 步） |
| `contracts/living-docs.json` | **活文档观察面清单**（57 living + 17 historical + 15 对镜像） | 新增含路径引用的 md 必须登记，否则门禁第 10 步自检 B 红 |
| `.github/workflows/ci.yml` | CI：Python 3.11 + Node 20，跑 pytest / node / schema / 敏感扫描 / pip-audit | — |
| `.gitignore` | 排除 `.env*`、`*.log`、`*.pdf`、`*.docx`、`__pycache__` 等 | 真实用户数据**绝不入库** |

### 2.4 关键脚本（`scripts/` 下 27 个，挑交接必知的）

| 脚本 | 作用 |
|---|---|
| `api-prod-probe.py` | 线上探针：静态是否 = HEAD + 业务接口通不通。可选 `--origin` / `--skip-freshness`。**需联网** |
| `phase4-http-smoke.py` | **真端口**冒烟（起真进程打 `127.0.0.1:8791`，不走 `test_client`） |
| `sync_mirror.py` | `public/` → `docs/` 镜像同步；`--check` 只校验 |
| `sensitive-scan.py` | 敏感信息扫描（密钥硬编码） |
| `live-doc-path-check.py` | 活文档里的路径引用必须真实存在；`--verbose` |
| `env-example-check.py` | `.env.example` 与代码读取点双向一致 |
| `vercel-dead-routes.py` | 重写源 ⊆ 处理分支（会实证发请求） |
| `frontend-api-literal-check.py` | 前端写死的 API 路径 ⊆ 重写源 |
| `publish-scope-check.py` | `public/` 公开 md 集合与清单一致 |
| `api-import-check.py` | 分层名字解析；`--roots api,domain,providers,repositories,services,scripts` |
| `living-docs-scope-check.py` | 观察面清单的**独立复算**（不 import 判据） |
| `entrypoint-resolution-check.py` | 每个候选入口名都要解析出**带路由**的 app |
| `p0-03-real-model-test.py` | 真模型复测（7 类任务 × 3 次）。**需要密钥** |
| `run-wf-e2e.py` / `run-rehearsal.py` | 端到端 / 彩排。可选 |
| `capture_mobile_ui.py` | 移动端截图。**需要 Playwright 浏览器** |

另有 `domain/validate_schema.py`（fixture 对 Schema 校验）与 `api/constants.py`（CORS 第一方源常量）。

---

## 3. 安装配置

### 3.1 一步式安装（按依赖顺序）

**Git Bash / WSL / Linux / macOS：**

```bash
git clone https://github.com/zimo66067-wq/career-coach.git career-coach
cd career-coach

# 1) 建虚拟环境（名字与开发机保持一致，便于对照）
python -m venv .venv-audit

# 2) 升级 pip 并装齐依赖（唯一依赖清单就在仓库根）
./.venv-audit/bin/python -m pip install --upgrade pip          # Linux/macOS
./.venv-audit/bin/python -m pip install -r requirements.txt
```

**Windows（PowerShell）：**

```powershell
git clone https://github.com/zimo66067-wq/career-coach.git career-coach
cd career-coach

python -m venv .venv-audit
.\.venv-audit\Scripts\python.exe -m pip install --upgrade pip
.\.venv-audit\Scripts\python.exe -m pip install -r requirements.txt
```

**Windows（CMD）：**

```bat
git clone https://github.com/zimo66067-wq/career-coach.git career-coach
cd career-coach
python -m venv .venv-audit
.venv-audit\Scripts\python.exe -m pip install --upgrade pip
.venv-audit\Scripts\python.exe -m pip install -r requirements.txt
```

> 国内网络可加镜像源：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（放在 `-r requirements.txt` 之前）。

### 3.2 验证安装成功

```bash
# Windows
.venv-audit/Scripts/python.exe -c "import flask, jsonschema, pytest, psycopg, jieba, pypdf; print('deps ok')"
# Linux/macOS
./.venv-audit/bin/python -c "import flask, jsonschema, pytest, psycopg, jieba, pypdf; print('deps ok')"
```

打印 `deps ok` 即依赖齐全。再确认 Node：

```bash
node -v     # 需要 >= 20
```

### 3.3 环境变量：跑测试**不需要** `.env`

**这是最容易过度配置的地方。** 18 步门禁**没有任何一步**读取真实密钥，所以：

- **跑通全部测试** → 不用建 `.env`，直接跳到 §4。
- 想**本地起服务**或**调真模型** → 才需要：

```bash
cp .env.example .env      # 然后按注释填值；.env 已在 .gitignore 中，绝不入库
```

`.env` 里只有一项与"跑起来"强相关，且有个**性能陷阱**：

| 变量 | 说明 |
|---|---|
| `DUMATE_MODEL` | 主 Chat 模型名。**它不只是个名字**：路由器对 `resume_diagnosis` 的读超时**冻结在 50 秒**，模型吞吐低于约 20 tokens/s 就会必然超时、每次落规则降级 —— 而接口仍返回 HTTP 200 和一份看起来正常的分数。2026-09-21 实测：`glm-4-flash` 要 58~68s（**必然降级**）、`glm-4-flash-250414` 20.6s ✅、`glm-4-air` 11.4s ✅、`glm-4.7-flash` HTTP 429 ❌ |

### 3.4 不需要"构建"

本项目**没有构建步骤**：没有打包、没有 `npm install`、没有编译。`public/` 下的静态资源直接就是产物。

唯一需要注意的一致性约定：**`public/` 是唯一 canonical 前端树**，`docs/` 是它的发布镜像
（GitHub Pages 从 `docs/` 发布）。两棵树下的**所有非 `.md` 文件必须逐字节相同**，由
`tests/test_publish_mirror.js` 强制。改完 `public/` 要同步：

```bash
.venv-audit/Scripts/python.exe scripts/sync_mirror.py            # 修复漂移
.venv-audit/Scripts/python.exe scripts/sync_mirror.py --check    # 复核
```

---

## 4. 测试执行

> 下面所有命令都**在仓库根目录**执行。Windows 用 `.venv-audit/Scripts/python.exe`，
> Linux/macOS 用 `./.venv-audit/bin/python`。为避免重复，下文统一写作 `$PY`：
>
> ```bash
> PY="./.venv-audit/Scripts/python.exe"; [ -x "$PY" ] || PY="./.venv-audit/bin/python"
> ```

### 4.1 全量测试

```bash
$PY -m pytest tests/ -q --tb=short
```

**判据**：摘要行里 **`failed` 与 `error` 都为 0**。本机 2026-09-22 实测基线是 **`520 passed`**
（约 136 秒）。**不要把 `520` 当判据** —— 测试数量会随开发变化，`failed/error = 0` 才是判据。

前端契约测试（**必须给 `"tests/*.js"` 加引号**，原因见 §5.4 的坑表）：

```bash
node --test "tests/*.js"
```

**判据**：输出里 `# fail 0`。本机实测基线 **`# tests 85 / # pass 85 / # fail 0`**。

### 4.2 单个测试用例

```bash
# 整个文件
$PY -m pytest tests/test_api.py -q

# 单个用例（文件::类::函数）
$PY -m pytest "tests/test_api.py::test_health" -q

# 按关键字筛
$PY -m pytest tests/ -q -k health

# 出错即停 + 详细回溯（排障时用）
$PY -m pytest tests/ -x --tb=long
```

### 4.3 测试所需的环境变量与外部依赖

**结论：全量测试零配置、零密钥、零外呼。** 明细：

| 项 | 是否必需 | 说明 |
|---|---|---|
| 密钥（`ZHIPU_API_KEY` 等） | **不需要** | 相关用例走 mock / 降级路径 |
| 数据库 | **不需要** | `tests/conftest.py` 自动把 `RESUME_DB_PATH` 指向临时目录并 `init_db()` |
| 网络 | **不需要** | 18 步门禁无外呼 |
| 端口 | 需要 **8791** 空闲 | `scripts/phase4-http-smoke.py` 固定用它起真进程 |
| Node | 需要（跑前端契约时） | ≥ 20 |

### 4.4 全部 18 步门禁（**仓库外 `gate8.sh` 的等价命令**）

开发机的 `gate8.sh` 把路径**硬编码**成了本机的 PortableGit / `.venv-audit` / node，
**换机器不能直接跑**。下表是它每一步的等价命令，可在新环境逐条复跑。
**每条判据的约定是：退出码 0 = 通过。**

| 步 | 判据 | 命令 |
|---|---|---|
| 0 | git 可用 | `git --version` |
| 1 | pytest 全量无 failed/error | `$PY -m pytest tests/ -q --tb=short` |
| 2 | 前端契约 | `node --test "tests/*.js"` |
| 3 | 4 类 fixture 对 Schema | 见下方脚本块（`domain/validate_schema.py`） |
| 4 | 敏感扫描 | `$PY scripts/sensitive-scan.py` |
| 5 | Vercel 死路由 | `$PY scripts/vercel-dead-routes.py` |
| 6 | 行尾空白/冲突标记 | `git diff --check` |
| 7 | 双方言 DDL（迁移） | `$PY -m pytest tests/test_migrations.py -q` |
| 8 | 真端口 HTTP 冒烟 | `$PY scripts/phase4-http-smoke.py` |
| 9 | 发布镜像不变量 | `$PY scripts/sync_mirror.py --check` |
| 10 | 活文档路径存在 | `$PY scripts/live-doc-path-check.py --verbose` |
| 11 | 前端字面量 ⊆ 重写源 | `$PY scripts/frontend-api-literal-check.py` |
| 12 | `.env.example` 双向一致 | `$PY scripts/env-example-check.py` |
| 13 | `public/` 公开 md 集合一致 | `$PY scripts/publish-scope-check.py` |
| 14 | 分层名字解析 | `$PY scripts/api-import-check.py --verbose --roots api,domain,providers,repositories,services,scripts` |
| 15 | `tools/` 零残留 | `$PY -m pytest tests/test_phase7d_contract.py -q`（另加 `$PY -c "import tools"` **应当失败**） |
| 16 | 观察面清单独立复算 | `$PY scripts/living-docs-scope-check.py` |
| 17 | 入口解析出带路由的 app | `$PY scripts/entrypoint-resolution-check.py` |

**第 3 步展开**（CI 里是同一套逻辑，逐类循环）：

```bash
for f in tests/fixtures-synthetic/resumes/*.expected.json; do
  $PY domain/validate_schema.py --schema contracts/resume-profile.schema.json --instance "$f" || echo "FAIL $f"
done
for f in tests/fixtures-synthetic/jobs/*.expected.json; do
  $PY domain/validate_schema.py --schema contracts/job-profile.schema.json --instance "$f" || echo "FAIL $f"
done
for f in tests/fixtures-synthetic/interviews/*.json; do
  $PY domain/validate_schema.py --schema contracts/interview-turn.schema.json --instance "$f" || echo "FAIL $f"
done
for f in tests/fixtures-synthetic/abilities/*.json; do
  case "$f" in *score-input*) continue ;; esac   # score-input 不是 AbilityProfile，跳过
  $PY domain/validate_schema.py --schema contracts/ability-profile.schema.json --instance "$f" || echo "FAIL $f"
done
```

本机实测基线：`OK=32 FAIL=0`（4 类合计 32 个 fixture）。

**一次跑完 18 步的脚本**（可整段复制保存为 `run-gates.sh` 后 `bash run-gates.sh`）：

```bash
#!/usr/bin/env bash
# 与开发机 gate8.sh 等价的跨平台版本：只依赖仓库内文件与 shell，不依赖仓库外工具。
set -uo pipefail
PY="./.venv-audit/Scripts/python.exe"; [ -x "$PY" ] || PY="./.venv-audit/bin/python"
FAILED=""
step() {  # step <编号> <说明> <命令...>
  local n="$1" desc="$2"; shift 2
  if "$@" >/tmp/gate-$n.log 2>&1; then echo "step $n PASS  $desc"
  else echo "step $n FAIL  $desc  （日志 /tmp/gate-$n.log）"; FAILED="$FAILED $n"; fi
}
step 1  "pytest 全量"            $PY -m pytest tests/ -q --tb=short
step 2  "前端契约"               node --test "tests/*.js"
step 4  "敏感扫描"               $PY scripts/sensitive-scan.py
step 5  "vercel 死路由"          $PY scripts/vercel-dead-routes.py
step 6  "行尾空白/冲突标记"      git diff --check
step 7  "双方言 DDL"             $PY -m pytest tests/test_migrations.py -q
step 8  "真端口冒烟"             $PY scripts/phase4-http-smoke.py
step 9  "发布镜像不变量"         $PY scripts/sync_mirror.py --check
step 10 "活文档路径"             $PY scripts/live-doc-path-check.py
step 11 "前端字面量"             $PY scripts/frontend-api-literal-check.py
step 12 "env.example 双向"       $PY scripts/env-example-check.py
step 13 "public md 集合"         $PY scripts/publish-scope-check.py
step 14 "分层名字解析"           $PY scripts/api-import-check.py --roots api,domain,providers,repositories,services,scripts
step 15 "tools 零残留"           $PY -m pytest tests/test_phase7d_contract.py -q
step 16 "观察面独立复算"         $PY scripts/living-docs-scope-check.py
step 17 "入口解析"               $PY scripts/entrypoint-resolution-check.py
if [ -n "$FAILED" ]; then echo "== 失败步骤：$FAILED =="; exit 1; fi
echo "== ALL PASS =="
```

> 第 3 步（schema）与第 0 步（git 可用性）没进这个脚本 —— 第 3 步见上方循环，
> 第 0 步在能执行 `git diff --check` 时已隐含成立。

### 4.5 需要密钥 / 联网的可选脚本（**不属于门禁**）

| 脚本 | 依赖 | 说明 |
|---|---|---|
| `scripts/api-prod-probe.py` | **联网** + 线上生产域名 | `--origin URL` 可指任意环境；`--skip-freshness` 只探接口。不需要密钥 |
| `scripts/p0-03-real-model-test.py` | `ZHIPU_API_KEY`（Chat+Embedding）与 `QIANFAN_API_KEY` | 真调模型，**会消耗额度**（7 类任务 × 3 次）。产物写进 `deliverables/p0-03-evidence/` |
| 仓库外 `work/prod-ai-path-probe.py` | **联网** + 线上环境 | 打 `POST /api/wf02/diagnose` 读 `diagnosis_mode`：只有 `"model"` 算通。**不在仓库内** |

**密钥占位符与获取方式**（**绝不可写入仓库、前端或任何交付文档**）：

| 变量 | 占位符 | 获取方式 |
|---|---|---|
| `ZHIPU_API_KEY` | `<ZHIPU_API_KEY>` | 智谱开放平台 `https://open.bigmodel.cn` → API Keys，形如 `xxxxxxxx.yyyyyyyy` |
| `DUMATE_CONSENT_SECRET` | `<32_BYTE_RANDOM>` | 自己生成：`python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `DUMATE_GUEST_SECRET` | `<32_BYTE_RANDOM>` | 同上（不设则回退到 `DUMATE_CONSENT_SECRET`） |
| `DATABASE_URL` | `<postgres://...>` | Neon 控制台复制连接串（生产用；本地测试**不需要**） |
| `QIANFAN_API_KEY` | `<QIANFAN_API_KEY>` | 百度智能云千帆控制台 |
| `QIANFAN_EMBEDDING_AK` / `_SK` | `<AK>` / `<SK>` | 千帆 Embedding-V1 的 OAuth 凭据（不配则匹配降级为 BM25） |

> 变量全集以 `.env.example` 为**唯一来源**（门禁第 12 步保证它与代码读取点双向一致）。
> 生产环境变量只配在 Vercel 控制台，**不进仓库**。

---

## 5. 差异排查

### 5.1 账号 / 权限差异

| 项 | 结论 |
|---|---|
| `clone` / `pull` | 仓库**公开**，无需凭据 |
| `push` | 需要被加为 collaborator。**只复跑测试的话完全不影响** |
| CI | CI 在 GitHub 侧跑（`.github/workflows/ci.yml`），本地无需任何凭据 |
| 生产探针 | 读的是公开 HTTPS 接口，也不需要凭据 |

### 5.2 网络与镜像源

| 现象 | 原因 | 解法 |
|---|---|---|
| `pip install` 很慢 / 超时 | 直连 PyPI | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `git clone` 卡住或失败 | `github.com` 在部分网络被 DNS 污染 | 用 `git config http.curloptResolve` 指定 IP，或走可用代理 |
| **本地起服务的脚本挂住不回** | 环境里存在 `http_proxy` / `https_proxy`，被降级路径的外呼继承 | 在命令前清掉：`env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY <命令>` |

### 5.3 端口占用

`scripts/phase4-http-smoke.py` **固定使用 8791**。被占用时的表现是启动失败或连接被拒。

```bash
# Windows
netstat -ano | findstr :8791
# Linux / macOS / Git Bash
lsof -i :8791
```

释放该端口后重跑；**不要**为了绕开而改脚本里的 `PORT` 常量（改了就不是同一条门禁了）。

### 5.4 残留缓存与"命令写法"导致的假失败

| 现象 | 原因 | 解法 |
|---|---|---|
| 改了代码但测试结果不变 | `__pycache__/` / `.pytest_cache/` 残留 | 删掉 `__pycache__`、`tests/__pycache__`、`.pytest_cache` 后重跑 |
| **`node --test tests/` 得到 `1 failed`** | **传目录时 Node 的默认匹配模式（`test/**`、`test-*.js` 等）**命中不了 `tests/test_xxx.js`** —— 它把整个目录当成一个失败的测试项 | **必须写成 `node --test "tests/*.js"`**（带引号让 Node 自己 glob，跨 shell 都成立）。本机 2026-09-22 实测：目录形式 `# tests 1 / # pass 0 / # fail 1`；带引号形式 `# tests 85 / # pass 85 / # fail 0` |
| 上一轮数据库残留影响本轮 | 一般不会：`conftest.py` 每轮指向新的临时库 | 如确实需要，删掉该临时目录或用 `--basetemp` 指定新目录 |

### 5.5 路径差异与"仓库外工具"

| 项 | 说明 |
|---|---|
| 仓库内脚本 | 都用 `os.path.dirname(os.path.abspath(__file__))` 相对定位，**换机器无痛** |
| 仓库外 `gate8.sh` | **硬编码**了开发机的 PortableGit / venv / node 绝对路径，**换机不能直接跑** → 用 §4.4 的等价命令 |
| 隐藏文件 | `.venv-audit/`、`.pytest_cache/`、`.env` 都是 `ls` 不显示的；用 `ls -a` 核对 |

### 5.6 版本差异

| 项 | 说明 |
|---|---|
| Python 3.12/3.13 | 部分依赖可能缺预编译 wheel（`psycopg[binary]`、`jieba`），**建议用 3.10/3.11** |
| Node < 20 | `node --test` 不可用或行为不同，**请升级到 20+** |
| 本机 vs CI | 本机 venv 是 **3.10.11**，CI 是 **3.11** —— 二者都实测通过 |

### 5.7 一个开发机特有、别的机器**不会**遇到的坑

开发机（WorkBuddy 沙箱）装有一个 **safe-delete 垫片**：`pytest` 退出时 `atexit` 的临时目录清理
会被它拦下并抛 `SystemExit`，导致 **`pytest` 自身的退出码不可信**，且摘要行可能被 traceback 淹没。

- **只在开发机成立**，新环境不受影响。
- 因此在开发机上判 pytest 结果时，**只看摘要行**（`520 passed` / `\d+ (failed|error)`），
  并把输出**落文件后再 grep**，不要直接 `| tail`。

### 5.8 常见报错速查

| 报错 / 现象 | 根因 | 解法 |
|---|---|---|
| `ModuleNotFoundError: No module named 'flask'` | 用了系统 Python，不是 venv | 用 `.venv-audit/Scripts/python.exe -m pytest` |
| 大面积 `ERROR` 指向 `psycopg` | 依赖没装齐 | `$PY -m pip install -r requirements.txt` |
| `env-example-check.py` 报变量不一致 | 代码新读了变量但没补进 `.env.example`（或反之） | 双向补齐；例外必须在脚本里逐条写明理由 |
| `live-doc-path-check.py` 报某路径不存在 | 活文档里引用的页面/脚本路径写错，或新增 md 没登记进 `contracts/living-docs.json` | 先修路径；确属新活文档则登记进清单 |
| `sync_mirror.py --check` 报漂移 | 改了 `public/` 没同步 `docs/` | `$PY scripts/sync_mirror.py` 后复核 |
| `vercel-dead-routes.py` 报某路由未覆盖 | `api/index.py` 加了 `/api/xxx` 但 `vercel.json` 没加 `source` | 补 `vercel.json` 重写 |
| `publish-scope-check.py` 报集合不一致 | `public/` 下增删了 `.md` 但清单没跟 | 同步清单 |
| `git diff --check` 报行尾空白 | 编辑器留了尾随空格 | 清理该行 |
| `node --test` 报找不到测试 | 传了目录而非 glob | 用 `node --test "tests/*.js"`（见 §5.4） |
| `phase4-http-smoke.py` 连不上 8791 | 端口被占，或父进程带了 `http_proxy` | §5.3 + §5.2 |

---

## 6. 验收 Checklist（从零到全绿）

按顺序执行，**每一项都有可观测的通过标志**。

### 阶段 A：拿到代码

- [ ] **A1** `git clone https://github.com/zimo66067-wq/career-coach.git career-coach` → 成功
- [ ] **A2** `cd career-coach && git rev-parse HEAD` → 打印一个 40 位 hash（记下来）
- [ ] **A3** `git ls-remote origin refs/heads/main` → 与 A2 一致（或知道差在哪里）

### 阶段 B：装环境

- [ ] **B1** `python -V` → **3.10 或 3.11**
- [ ] **B2** `python -m venv .venv-audit` → 生成目录
- [ ] **B3** `.venv-audit/Scripts/python.exe -m pip install -r requirements.txt`（Linux/macOS 用 `./.venv-audit/bin/python`）→ 无 error 退出
- [ ] **B4** 导入自检：`... -c "import flask, jsonschema, pytest, psycopg, jieba, pypdf; print('deps ok')"` → 打印 `deps ok`
- [ ] **B5** `node -v` → **≥ 20**
- [ ] **B6**（无需动作）确认**没有**创建 `.env` —— 跑测试不需要它

### 阶段 C：跑通测试（核心）

- [ ] **C1** `$PY -m pytest tests/ -q --tb=short` → 摘要行 **`failed` 与 `error` 均为 0**
      （2026-09-22 基线：`520 passed`，约 136 秒）
- [ ] **C2** `node --test "tests/*.js"` → **`# fail 0`**（2026-09-22 基线：`# tests 85 / # pass 85`）
- [ ] **C3** `$PY -m pytest tests/test_api.py -q` → 单文件用例全过（验"单用例命令"可用）

### 阶段 D：跑通其余 16 步判据

- [ ] **D1** 把 §4.4 的 `run-gates.sh` 存下来，`bash run-gates.sh` → 末行 **`== ALL PASS ==`**
- [ ] **D2** 若 D1 有 FAIL：按 §5.8 速查表定位；**每修一项都要重跑该步**，不要跳到下一步

### 阶段 E：可选（需要额外条件时）

- [ ] **E1**（联网）`$PY scripts/api-prod-probe.py` → 退出 0（判线上静态与接口）
- [ ] **E2**（需密钥）`$PY scripts/p0-03-real-model-test.py` → 需要 `ZHIPU_API_KEY`、`QIANFAN_API_KEY`
- [ ] **E3**（需浏览器）`$PY -m playwright install chromium` 后跑 `scripts/capture_mobile_ui.py`
- [ ] **E4**（改过前端时）`$PY scripts/sync_mirror.py` → 再 `--check` 通过

### 交付判定

> **C1 + C2 + D1（`ALL PASS`）三项同时成立 = 环境复跑完成。**
> 数字（520 / 85）只是当时的快照，**判据永远是 `failed = 0` 与 `ALL PASS`**。

---

## 附录 A：本机实测基线（2026-09-22）

供对照。**换环境后数字可能不同，缺项原因见 §5。**

| 判据 | 本机结果 |
|---|---|
| pytest 全量（步 1） | `520 passed in 135.97s` |
| 前端契约（步 2） | `# tests 85 / # pass 85 / # fail 0` |
| schema 校验（步 3） | `OK=32 FAIL=0` |
| 敏感扫描（步 4） | `Sensitive information scan passed.` |
| 死路由（步 5） | `0` |
| 双冒烟（步 7） | `15 passed` |
| 真端口冒烟（步 8） | `passed 70 / failed 0` |
| `tools/` 零残留（步 15） | `13 passed` |
| 汇总 | **ALL 18 步通过（0~17）** |

## 附录 B：这份文档的维护

- 它是**活文档**：登记在 `contracts/living-docs.json` 的 `living` 清单里，理由是"复跑步骤必须与
  实际脚本同步；脚本改名/加步而本文未改，下一个人就会照着一份过期步骤操作"。
- 改完必须跑：`$PY scripts/live-doc-path-check.py --verbose`（第 10 步）与
  `$PY scripts/living-docs-scope-check.py`（第 16 步）。
- 新增/删除门禁步骤时，**同步更新 §4.4 的两张表与 `run-gates.sh`**。
