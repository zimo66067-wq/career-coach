# career-coach · AI求职面试教练

> **项目状态：WorkBuddy 工具阶段通过（42/42 测试绿），六工作流自动化已验证（16/16 PASS），提交包已冻结。**
>
> - ✅ 数据合同冻结（4 Schema + scoring.md）
> - ✅ 工具链 8/8 已实现并测试通过
> - ✅ 提示词 7/7 已完成
> - ✅ 公开静态入口默认空态，未提交材料不展示合成诊断结果
> - ✅ 静态原型 6 页面完整
> - ✅ 六工作流自动化证据已生成（含降级路径）
> - ✅ 语音链路验证通过（18/18 PASS）
> - ✅ 官方链接核验完成（6/9 可达）
> - ⬜ P0-01 真实模型复测（待 API key）
> - ⬜ P0-03 端到端真实数据闭环（依赖 P0-01）
> - ⬜ G8 用户验证（模板就绪，待执行）
> - ✅ G9 提交包已冻结（tag: v1.0.0-g9-freeze）

iCAN 无代码开发挑战赛（DuMate 方向）参赛项目。
本仓库是**唯一事实源**：DuMate（百度搭子）做主产品，WorkBuddy 做分工开发，双方通过 git commit + HANDOFF 异步接力。

## MVP 四项（严格冻结）

| 编号 | 功能 | 产出合同 |
|---|---|---|
| F1 | 简历 AI 诊断打分 + 逐条修改建议 | ResumeProfile |
| F2 | 简历-JD 匹配度 + 关键词缺口 | JobProfile + 四态匹配 |
| F3 | 文字 AI 模拟面试（会追问，结束出表现报告） | InterviewTurn 序列 |
| F4 | 能力雷达图 + 七天竞争力情景推演 | AbilityProfile |

> 产品基线：**模型做语义，规则做分数，验证器做事实。** 所有关键节点均有降级路径。
> 口径注意：F4 的七天结果统一称「七天竞争力情景推演」，不得称「预测」。

## 目录导航

```
career-coach/
├── docs/            # PRD / 架构 / 隐私 / 演示脚本 / 审查报告
├── contracts/       # 4 个 JSON Schema + scoring.md 评分公式（冻结层，禁止擅改）
├── workflows/       # WF-01~06 工作流定义（DuMate 负责实现）
├── prompts/         # resume / match / interview / plan 提示词模块
├── ui/              # prototype/ 静态高保真原型 + assets/
├── tools/           # WorkBuddy 交付的 8 个 Python 工具
├── tests/           # fixtures-synthetic 合成样本 + pytest 契约/故障注入测试
├── tasks/           # 任务看板规则
├── handoffs/        # HANDOFF-001~003 交接文件
└── deliverables/    # 最终提交包（DuMate 阶段产出）
```

## 快速开始

**看公开入口**：GitHub Pages 从 `docs/` 发布；本地可双击打开 `ui/prototype/index.html`。功能页默认均为等待用户材料的空态，普通 `?state=...` 参数不会展示诊断结果。

**内部 QA 演示**：仅限显式使用 `?demo=1&state=empty|processing|success|error|degraded`；该入口不在公开导航中，合成数据不得作为用户诊断结果使用。

> 上线边界：当前仓库仍处于真实上传、AI 调用及 DuMate 工作流集成阶段。公开静态页只提供前端入口；没有经过用户提交、服务端处理和证据校验的材料，页面不得展示评分、建议或匹配结论。

要让公开页完成真实上传与诊断，部署方必须在加载 `data-bridge.js` 前配置 `window.DUMATE_API_BASE`，并提供可从 Pages 域名访问的 `POST /api/wf01/upload` 与 `POST /api/wf02/diagnose` 服务。未接入时页面会明确显示失败状态，不会使用旧缓存或合成诊断代替用户结果。

**跑测试**（Windows）：

```bat
cd /d <本仓库目录>
set PY=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe
%PY% -m pip install -r tools\requirements.txt
%PY% -m pytest tests\ -v
```

## 双 Agent 分工与文件所有权

| 角色 | 拥有目录 | 说明 |
|---|---|---|
| Product Agent | docs/ + contracts/ | 已冻结，改动须走变更流程 |
| Frontend Agent (WorkBuddy) | ui/ + prompts/ | 静态原型与提示词 |
| QA/Tool Agent (WorkBuddy) | tools/ + tests/ | 校验器、复算器、契约测试 |
| Workflow Agent (DuMate) | workflows/ + deliverables/ | 六个工作流与提交包 |
| Integration Agent | 合并 + 版本冻结 | 单一负责人 |

规则：两个 Agent 不得同时修改同一文件；交接必须先 commit 再写 HANDOFF；审查 Agent 只输出 review 报告。
