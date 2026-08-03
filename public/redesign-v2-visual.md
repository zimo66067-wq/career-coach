# redesign-v2-visual.md · 职跃AI 前端视觉改版（v2）交付记录

日期：2026-08-03 ｜ 范围：`ui/prototype/` + `docs/`（GitHub Pages 部署副本）｜ 原则：渐进式改版，DOM / 数据 / 业务契约零破坏

> 重要前提：本次改版基于远程 main 最新状态（含 DuMate 侧 voice.js 语音链路、data-bridge.js 数据桥、
> mock-data source_spans 合同升级）重放，全部新增能力完整保留，未回退任何远程工作。

## 1. 设计系统摘要

| 维度 | 规范 |
|---|---|
| 基底 | 温润近白 `#f7f6f4` + 冷灰层次 `#f4f6f9` + 深石墨正文 `#1b1e26` |
| AI 强调 | 电光蓝 `#2f5fe8` → 靛青 `#4f46e5` 渐变（仅用于品牌、主按钮、分数、AI 状态） |
| 语义色 | covered `#15803d` / weak `#b45309` / missing `#d32424` / unknown `#5b6472`（白底均 ≥4.5:1） |
| 材质 | 发丝线 `rgba(22,30,52,.10)`、柔和漫反射阴影三级、导航/悬浮器半透明 + backdrop blur |
| 圆角 | 8 / 12 / 16 / 22 / pill，克制曲线 |
| 动效 | `cubic-bezier(.22,.61,.36,1)`，160/260/480ms；入场淡入上浮、数据渐进绘制、AI 低频呼吸光、流动细线；全面支持 `prefers-reduced-motion` |

## 2. 修改文件清单

### ui/prototype/（源）
| 文件 | 变更类型 | 内容 |
|---|---|---|
| `css/tokens.css` | 新增 | 全局 Design Tokens（色彩/字体/间距/圆角/阴影/动效曲线） |
| `css/main.css` | 重写 | 公共组件全面升级；旧 CSS 变量全部映射到新 token，class 契约不变 |
| `css/states.css` | 重写 | 五状态视觉升级；状态切换选择器原样保留 |
| `index.html` | 改版 | Hero 视觉焦点；引入 tokens.css；skip-link；保留 data-bridge.js |
| `pages/f1-resume.html` | 改版 | 处理中新增「AI 阶段步进器+呼吸光+流动线」；保留 DataBridge 主链路与 fetchSync |
| `pages/f2-match.html` | 改版 | 语义流动轨迹；覆盖条配色同步新语义色；保留 DataBridge |
| `pages/f3-interview.html` | 改版 | 面试官在线区（呼吸光+语音波形）；语音组件配色对齐设计系统；voice.js 逻辑零改动 |
| `pages/f4-report.html` | 改版 | C0 数字递增动画（终值=真实基线）；保留 DataBridge |
| `pages/states.html` | 改版 | tokens.css + skip-link |
| `js/radar.js` | 修改 | 雷达配色对齐设计系统；平滑路径动画；reduced-motion 关闭动画 |
| `js/app.js` | 修改 | 生产默认空态；状态悬浮器与合成数据仅在 `?demo=1&state=` 下启用 |

### docs/（GitHub Pages 部署副本）
全量同步上述前端文件（css×3 / js×6 含 data-bridge.js、voice.js / index.html / pages×5），
消除此前部署副本缺少 voice.js、data-bridge.js 的滞后问题。

未改动：`js/mock-data.js`、`js/evidence.js`、`js/voice.js`、`contracts/`、`workflows/`、`deliverables/`。

## 3. 契约保留核验

- DOM ID 全量保留（含 DuMate 新增：`micBtn / ttsToggle / voice-state-indicator / voice-fallback-area / voiceTextFallback / voiceTextSubmit / voiceTextRetryVoice / draftHint`）
- `data-state-view` ×5 态 ×4 页完整；`data-page`、`data-no-fab`、`data-quote` 契约保留；状态演示改为显式 `?demo=1&state=`
- `window.APP / MOCK / EVIDENCE / RADAR / DataBridge / VoiceHandler` 接口签名不变
- 四条业务流程、五类状态、语音增强链路、文字回退链路完整
- 评分、证据引用、source_spans、追问逻辑、推演区间的合成样本仅用于显式演示；生产态不伪造用户结果

## 4. 验收记录

| # | 检查项 | 方法 | 结果 |
|---|---|---|---|
| 1 | 全量自动化测试无回归 | `pytest tests/ -q` | ✅ 42 passed |
| 2 | JS 语法 | `node --check` ×6 | ✅ 通过 |
| 3 | 静态资源可达 | 本地 HTTP 服务 curl | ✅ 全 200 |
| 4 | DOM 契约 | grep 全量 ID / data-* 比对 | ✅ 零缺失 |
| 5 | 五状态 ×四页 = 20 入口 | 状态墙矩阵结构核验 | ✅ 保留 |
| 6 | 雷达三级降级 / 语音回退链路 | 逻辑未动 | ✅ 保留 |
| 7 | 与 DuMate 远程工作合并 | data-bridge / voice / source_spans 适配器保留 | ✅ 无回退 |

## 5. 无障碍与性能检查

**无障碍（WCAG AA）**
- 对比度：正文 ≈15.8:1；次级 ≈7.0:1；说明 ≈4.8:1；主按钮白字 ≈6.2:1；四态徽章 ≥4.5:1 ✅
- 键盘：skip-link、全交互元素 `:focus-visible` 焦点环（含麦克风按钮）✅
- 动效：`prefers-reduced-motion` 下全部动画关闭（含录音脉冲 mic-pulse）✅
- 语义：nav aria-label、score-ring role/aria、FAB role="group"+aria-current、装饰动效 aria-hidden ✅

**性能**
- 零新增外部依赖；动画全部 transform/opacity（合成层）；低频小元素动画
- 背景柔光为 radial-gradient（无图片请求）；backdrop blur 仅导航与悬浮器

## 6. 已知边界

- `deliverables/zhiyue-ai-core.html`（比赛单文件版）不在本次范围，保持冻结
- 语音波形/呼吸光为链路状态视觉指示；真实 ASR/TTS 由 voice.js 驱动，未改动
- docs/ 副本 favicon 引用 `../assets/`（Pages 下 404，与远程既有行为一致，不影响功能）
