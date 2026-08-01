# HANDOFF-002 · 前端原型 → 工具链

- **input_commit**: `91f4fe3`（feat(baseline)）＋ `7be2204`（handoff 001）
- **output_commit**: 本阶段提交后回填（见下方 git log）
- **handoff_commit**: 本文件提交于 output_commit 之后

## 任务目标

按 contracts 与 fixtures 交付 ui/prototype 五页面×五状态静态原型、prompts/ 七份提示词、docs/demo-script.md。

## 已完成

- ui/prototype/：index + F1/F2/F3/F4 + states 状态墙（6 页）；css/main.css（设计系统+响应式）+ css/states.css（五状态）；js/app.js（?state= 参数 + 悬浮切换器）+ js/evidence.js（证据对照）+ js/radar.js（三级降级）+ js/mock-data.js（与 fixtures 同源）
- ui/assets/：logo.svg、favicon.svg、vendor/echarts.min.js（5.5.0 本地化，1.0MB）
- prompts/：resume/diagnose、resume/report-deep、match/jd-extract（注入防御）、match/explain、interview/interviewer、interview/review、plan/seven-day
- docs/demo-script.md：8 分钟走查分镜 + 四句切换口令 + 口径红线

## 变更文件

ui/（13）、prompts/（7）、docs/demo-script.md（1）、handoffs/002（1）

## 验收命令与结果

| 验收项 | 结果 |
|---|---|
| 六个页面 file:// 直接打开无构建 | ✅ |
| 四功能页 × 五状态（?state=）切换正常 | ✅（states.html 矩阵 20 入口） |
| ECharts CDN 失败 → vendor → 表格三级降级 | ✅（radar.js 内建，degraded 态强制表格演示） |
| mock-data 与 fixtures 数值一致（R=73/M=60/I=72.55/C0=68.27/C7=77.79~90.48） | ✅ |
| 响应式（≥1024 双栏 / <768 单栏） | ✅（CSS 断点） |

（浏览器截图验收：见 G8 彩排；本阶段以代码审查与手动走查为准。）

## 未解决问题

- 雷达「推演 low/high」系列目前按 C7/C0 比例缩放演示，正式口径（是否逐维推演）待 DuMate 在 WF-05 确认。
- 移动端真机截图未做（G8 用户测试阶段补）。

## 已知风险

- file:// 协议下个别浏览器对本地 vendor 脚本加载策略不同 → 若双击打开雷达不渲染，用任意静态服务器（或 VSCode LiveServer）打开即可；表格降级仍可演示。

## 回滚点

- 回滚到 `7be2204` = 基线 + handoff-001（无 UI/prompts）。

## 下一位Agent唯一任务

**工具链 Agent（WorkBuddy/Kimi-K2.7-Code）**：实现 tools/ 八个工具 + tests/ pytest 契约与故障注入测试（范围见 tests/acceptance/acceptance-checklist.md 的 WorkBuddy 段）。只拥有 tools/ 与 tests/（新增测试文件），不得改 contracts/、fixtures、ui/、prompts/。

## 禁止改动

contracts/、tests/fixtures-synthetic/、ui/、prompts/ 在本 HANDOFF 之后冻结；如必须改，新开 HANDOFF 并同步 CHANGELOG。
