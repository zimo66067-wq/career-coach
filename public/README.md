# 职跃AI · 前端发布树

零依赖、零构建：直接用浏览器打开 `index.html` 即可（`file://` 协议可用，无需起服务）。

## 页面

| 页面 | 路径 | 内容 | 导航 |
|---|---|---|---|
| 首页 | `index.html` | 主流程入口与快速演示 | 品牌区 |
| 简历证据 | `pages/resume-evidence.html` | 总分环 + 子分条 + 证据对照（点击理由高亮原文）+ 改写建议 | 一级工作区 |
| 目标岗位 | `pages/target-job.html` | 粘贴 JD → 拆出可核对要求 → 对照简历 → 给出可解释的投递判断（可以投 / 够一够再投 / 先别投）+ 缺口铺成行动 | 一级工作区 |
| 模拟面试 | `pages/interview-practice.html` | 对话气泡 + 每轮评估卡（引用块 / STAR 缺口 / 追问）+ 流式追问；出题顺序取自当前目标岗位的未解决缺口 | 一级工作区 |
| 行动闭环 | `pages/action-loop.html` | 六维雷达 + C0 证据快照 + 缺口行动清单（消费 `/api/actions`：待办 / 进行中 / 已完成 / 已放弃 + 结果回流） | 一级工作区 |
| 投递与求职信 | `pages/job-apply.html` | 求职信生成（引用目标岗位要求与已确认证据）+ 申请记录；**不提供单位检索** | 目标岗位的子页 |
| 状态墙 | `pages/states.html` | 内部 QA：五状态矩阵 | 不进导航 |

> 一级导航只放 4 个一级工作区（简历证据 / 目标岗位 / 模拟面试 / 行动闭环）；首页由品牌区进入。
> 页面文件名不含 `F1–F5` 代号 —— URL 属于用户可见面（Phase 6b-2b）。

> **已下线**（勿再引用）：
> - `pages/f2-match.html` —— 2026-09-13 随「专业→职业匹配」整块删除而下线。
> - `js/job-upload.js` —— 2026-09-17（Phase 6b-1）随 `f2-match.html` 的界面一并退役。
>   它绑定的 `/api/wf03/{upload,jd,match}` 前端路径**只产出匹配分数，产不出 Decision 与 Gap**，
>   无法支撑目标岗位工作区；替代实现是 `pages/target-job.html` + `js/target-job.js`
>   （走 `/api/target-jobs` 与 `/api/actions`）。
>   **后端 `/api/wf03/*` 三条路由保留（Phase 7b 决议，2026-09-17）**：它们不是死接口 ——
>   `wf03` 是 DuMate 工作流编号 WF-01~WF-07 在 HTTP 上的体现（与 `capability_matrix.md`
>   的 N7/N9 两行、`dumate-workflow-sop.md` 的 WF-03 一一对应），**归零的是浏览器消费方，
>   不是消费者**。判据把它锁住：`tests/test_phase7b_contract.js`。
> - `pages/kb.html` —— 2026-09-13 随「知识库不作为独立产品」下线，题库下沉为面试引擎的内部数据源。
> - 目录索引里原先的 `voice-test-checklist.md` 一项已随语音链路删除一并清除。

## 公开运行规则

- 所有公开功能页默认 `empty`；未提交材料时不展示分数、建议或匹配结论。
- 普通 `?state=...` 参数会被忽略，公开导航不展示状态墙或状态切换器。
- 内部 QA 才可显式使用 `?demo=1&state=empty|processing|success|error|degraded`；
  状态切换器仅在演示模式显示，页面会标识合成样本。
- degraded 态：简历证据简化诊断清单 / 模拟面试固定题库 / 行动闭环雷达强制降级为表格。

## 数据来源与一致性

- 演示数据在 `js/mock-data.js`，与 `tests/fixtures-synthetic/` 同源，只能在 `demo=1` 下读取。
- 生产路径为 API → 当前会话缓存 → 明确错误，绝不以 `window.MOCK` 代替用户上传、诊断、匹配或面试结果。

## 发布结构与同步约定

| 树 | 角色 |
|---|---|
| `public/` | **唯一 canonical**，Vercel 生产树（`vercel.json` 把 `/`、`/index.html` 与 `css`、`js`、`pages`、`assets` 四类路径全部重写到 `public/`） |
| `docs/` | GitHub Pages 发布镜像 |

**不变量**：两棵树下所有 **非 `.md`** 文件必须集合相同且逐字节相同。

- 校验：`tests/test_publish_mirror.js`（进 `node --test tests/*.js` 门禁，含判据自检）
- 修复：`python scripts/sync_mirror.py`（`--check` 只校验，退出码 1 表示有漂移）
- 侧栏/账号弹窗标记改动后：先跑 `python scripts/sync_sidebar.py`（幂等），再跑一次 `sync_mirror.py`

`.md` 不在自动镜像范围内：`docs/` 合法地多出内部文档（各类阶段报告、`product-scope.md`、
`dependency-map.md` 等），它们是文档树而非前端资源。

## ECharts 三级降级

1. CDN（jsdelivr）→ 2. 本地 `../assets/vendor/echarts.min.js`（已随仓库提交）→
3. 均失败时 `js/radar.js` 渲染六维表格

## 响应式

- ≥1024px：证据对照双栏；<768px：单栏堆叠、导航横向滚动
