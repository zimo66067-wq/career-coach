# ui/prototype · 静态高保真原型

零依赖、零构建：双击 `index.html` 即可在浏览器打开（file:// 协议可用，无需起服务）。

## 页面

| 页面 | 路径 | 内容 |
|---|---|---|
| 首页 | `index.html` | 主流程与四项功能入口 |
| F1 简历诊断 | `pages/f1-resume.html` | 总分环 + 子分条 + 证据对照（点击理由高亮原文） |
| F2 岗位匹配 | `pages/f2-match.html` | 四态分组列表 + 硬性置顶 + 覆盖率条 + 缺口分级 |
| F3 模拟面试 | `pages/f3-interview.html` | 对话气泡 + 每轮评估卡（引用块/STAR 缺口/追问） |
| F4 能力报告 | `pages/f4-report.html` | C0 大数 + C7 区间带 + 六维雷达 + 七天计划 |
| 状态墙 | `pages/states.html` | 4 页 × 5 态共 20 个演示入口矩阵 |

## 状态演示

- 每个功能页读 URL 参数 `?state=empty|processing|success|error|degraded`（默认 `success`）
- 页面右下角悬浮「界面状态演示」切换器，点击即切状态
- degraded 态：F1 简化诊断清单 / F2 BM25 简化匹配 / F3 固定题库 / F4 雷达强制降级为表格

## 数据来源与一致性

- 演示数据在 `js/mock-data.js`，**与 tests/fixtures-synthetic/ 同源**，修改 fixtures 必须同步本文件
- 接入真实数据时只需替换 `window.MOCK` 的内容（DuMate 侧见 handoffs/003）

## ECharts 三级降级

1. CDN（jsdelivr）→ 2. 本地 `../assets/vendor/echarts.min.js`（已随仓库提交）→ 3. 均失败时 `js/radar.js` 渲染六维表格

## 响应式

- ≥1024px：证据对照双栏；<768px：单栏堆叠、导航横向滚动
