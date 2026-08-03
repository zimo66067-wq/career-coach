# ui/prototype · 公开前端与内部 QA 演示

零依赖、零构建：双击 `index.html` 即可在浏览器打开（file:// 协议可用，无需起服务）。

## 页面

| 页面 | 路径 | 内容 |
|---|---|---|
| 首页 | `index.html` | 主流程与四项功能入口 |
| F1 简历诊断 | `pages/f1-resume.html` | 总分环 + 子分条 + 证据对照（点击理由高亮原文） |
| F2 岗位匹配 | `pages/f2-match.html` | 四态分组列表 + 硬性置顶 + 覆盖率条 + 缺口分级 |
| F3 模拟面试 | `pages/f3-interview.html` | 对话气泡 + 每轮评估卡（引用块/STAR 缺口/追问） |
| F4 能力报告 | `pages/f4-report.html` | C0 大数 + C7 区间带 + 六维雷达 + 七天计划 |

## 公开运行规则

- 所有公开功能页默认 `empty`；未提交材料时不展示分数、建议或匹配结论。
- 普通 `?state=...` 参数会被忽略，公开导航不展示状态墙或状态切换器。
- 内部 QA 才可显式使用 `?demo=1&state=empty|processing|success|error|degraded`；`pages/states.html` 仅保留为未链接的 QA 矩阵。
- degraded 态：F1 简化诊断清单 / F2 BM25 简化匹配 / F3 固定题库 / F4 雷达强制降级为表格。

## 数据来源与一致性

- `js/mock-data.js` 仅用于显式 QA 演示，且全部为合成样本；不得作为公开用户的诊断输入或结果。
- 真实结果必须来自用户提交、服务端处理和证据校验；当前静态页面尚未完成此链路。

## ECharts 三级降级

1. CDN（jsdelivr）→ 2. 本地 `../assets/vendor/echarts.min.js`（已随仓库提交）→ 3. 均失败时 `js/radar.js` 渲染六维表格

## 响应式

- ≥1024px：证据对照双栏；<768px：单栏堆叠、导航横向滚动
