# 上线剩余步骤清单

## 2026-09-30 生产状态与 F3 再验（最新；均以对应 SHA 为准）

- 另一工作流已将核心版 PR #8 合并到 `main`，提交 `3347d35` 并部署生产；其 CI #90/#91 因一条旧用例把“会 MySQL 索引优化”误当成“也会慢查询分析”而失败，不是生产健康检查失败。用户随后仅授权修正测试：PR #9（只改 `tests/test_career_flow.py`）以 squash 提交 `ff70ca0` 合并，`main` CI #93 为 success，Vercel 生产部署 `dpl_EERvZaUT7UMiotjSeS5xq6xaMc8C` 为 READY，生产 `/api/health` 返回 200、PostgreSQL 与模型配置就绪、迁移检查通过。这些信号不证明数据库可恢复，也不等于真人业务验收。
- 已登录旧 Preview `e69cede` 的 F2 浏览器复测：岗位 #17 的“编写单元测试并排查线上问题”已从虚假“覆盖”改判“缺失”。同页又发现复合要求误判——只读文档被当成完整“沟通能力和文档习惯”，只做订单被当成完整“订单、库存”。后续提交 `3347d35` 将仅覆盖部分子要求降为弱命中；该补丁的本地回归通过，但尚未用相同样本在生产逐项复核。
- 已登录旧 Preview `e69cede` 的 F3 完成 5 道主问及追问并生成报告，发现第 2、3 题仍换说法问团队协作，第 4 题把“学历要求”硬接到压测工具问题，一条追问截断脱敏占位符。现于 `codex/f3-adaptive-quality-20260930` 本地修复：按要求文字去重、不循环已用缺口、拦截学历与无关技术题、识别团队协作换问法、清理回答引文截断；新增 4 条回归。本地 Python 565/565 通过。**此 F3 修复尚未合并或部署，须同 SHA CI、Preview 登录态复测后才能宣称线上改善。**
- `work/core-acceptance-20260930-e69cede-preview.json` 的受保护 Preview 自动化验收只完整通过第 1 轮；第 2 轮在面试结束后的下一请求发生 `URLError`，清理成功且无业务断言失败，但不能算三轮通过。需在后续 Preview 补足独立轮次，并保留失败记录。
- 当前仍不能只剩“5 名真人试用”：生产 PostgreSQL 提供方/实例身份和恢复演练、实际数据保留期及人工数据权利处理流程尚未验证。账号原文件留存与管理员后台由用户明确排到上线后独立版本；密码只可安全重置，不提供明文查看。`zimo66067@gmail.com` 已获授权公开作为人工个人信息请求邮箱。

## 2026-09-30 登录态浏览器闭环与规则精度修复（历史快照）

- 当前核对的代码基线：分支 `codex/core-release-20260928`，Preview `dpl_3b9UxkZuUsRBTSXvqyVFDJYrXgs1`（`0251c53`，READY），对应 CI 第 88 次运行通过；生产仍是 `main` 的旧版本。下列新增匹配与面试修复尚未提交/部署，不能算线上已修复。
- 用户登录该 Preview 后，合成样例从 F1 简历诊断、F2 目标岗位建立/分析/行动生成、F3 五道主问及各自追问、F4 三源能力报告与七天计划、F5 求职信生成/人工确认/内部申请记录保存，已在浏览器走通。岗位 #17 拆出 8 条要求、过滤 2 行非要求，F2 决策 STRETCH；F4 得到 C0=70.50。F5 因已确认职业证据为 0，明确降为仅含目标岗位要求的规则模板，不冒充模型或个人经历。全部是合成材料，不能替代真人试用或真实投递。
- 浏览器验收另外发现两个质量缺陷：F2 把“编写接口文档”当作“编写单元测试并排查线上问题”的覆盖证据；F3 第 4/5 题换说法重复追问慢查询量化。现已在本地给 BM25 单句证据增加事实重叠门槛，并给面试题加入跨措辞重复检测、模型提示补充避免重复/资格事实混接；回归用例同步调整为真正有直接证据的 APPLY 场景。修复前的浏览器结果不能证明这两处已经上线修好。
- 本地修复后全量 Python 559/559、前端 Node 94/94、Schema 32/32、发布镜像 30/30、敏感信息扫描通过。下一步仍须推送、等待同 SHA CI/Preview，并在新 Preview 复测误报和重复问题；不能仅凭本地测试合并生产。
- Checkly 控制台 2026-09-30 显示 Team Trial 将于 2026-10-13 自动切为免费 Hobby；Hobby 页面列出 10 个 uptime monitors、邮件告警。原有故障/恢复邮件已实测到达；到期后须核对监控仍运行，未升级付费。
- 生产数据库恢复仍受资源身份阻断：Vercel 项目 Storage 只关联独立 Preview Neon 库；团队另有未关联的 `neon-amber-cave`，不能按日期或名称认定是 Production `DATABASE_URL` 所指。用户当前无法确认提供方/资源 ID；不得读取生产连接串或对未知库执行恢复。生产发布/恢复门禁和 5 名真实用户试用仍未齐。
- 用户决定暂不做账号注销按钮，原始简历留存与管理员后台列为上线后独立版本。当前系统只保留去标识化简历文字与文件元数据，原上传文件在提取后删除；密码仅以哈希保存，不能提供明文查看。用户已授权将 `zimo66067@gmail.com` 公开为人工受理邮箱，首页入口及隐私处理说明已在本地补上；仍须确认并落实实际保存期限、身份核验和完整数据权利处理流程，不能把“暂不开放按钮”解释为取消法定权利。

## 2026-09-30 核心版续验与待发布修复（当前状态）

- 工作分支 `codex/core-release-20260928` 已推送修复提交 `c82966602446f29be856234760021abac9b453e8`；PR #8 仍为草稿，生产仍未合并这些修复。该提交同 SHA 的 CI [第 87 次运行](https://github.com/zimo66067-wq/career-coach/actions/runs/36607836234) 为 success，Preview `dpl_H9wkQarfoE5CuDGofNP9tUKwKYs5` 为 READY；这不是生产部署。
- 前述求职信约束修复在受保护 Preview 完成三轮独立合成流程：`deliverables/core-acceptance-20260929-prompt-r2r3b.json` 两轮、130 项检查通过；`deliverables/core-acceptance-20260930-prompt-r3.json` 一轮、72 项检查通过。三轮求职信均标记 `basis=model`、`grounding=target_job+evidence`。这只证明该 Preview 代码与当前样本的结果，不证明模型普遍稳定；两份失败/中断报告已保存在仓库外的 `work/acceptance-failed-archive/`，未抹除失败历史。
- Checkly 免费外部监控已完成真实告警闭环：生产首页及 `/api/health` 两个 10 分钟探针已配置；隔离演练探针的故障邮件与恢复邮件均实际送达指定邮箱，演练探针随后停用。一次健康探针因 5 秒降级阈值出现 5.74 秒响应，断言未失败，但需持续观察性能。账号当时显示 TEAM TRIAL，将来是否自动落为免费 Hobby 仍应到期核对；未升级、未提供付款信息。
- 已登录浏览器在旧 Preview 完成 F1 合成诊断、F2 建岗/分析、F3 五道主问与追问，暴露真实缺陷：同意过期无续接；岗位理由显示 JSON；演示说明与写入历史不一致；JD 的测试声明被当作要求；F3 报告生成后页面仍空白；F4 行动列表被错误嵌入隐藏视图，且页面从未调用真实 WF-05 聚合接口。旧 Preview 的这次浏览器行程不能计作全流程通过。
- `c829666` 已包含：显式同意续接、不自动代用户同意；过滤 JD 来源声明及标题等非要求文本；F2 当前分析写入 WF-05 可读取的会话级匹配；F3 `report` 视图可见；F4 行动列表可见并提供真实能力报告入口，去除默认演示分数、拒绝空对象/空数组进度、把岗位结论理由格式化；`public/` 与 `docs/` 镜像同步。
- `deliverables/core-acceptance-20260930-wf05-preview.json`：在该提交的受保护 Preview 上以隔离合成会话完成三轮，206 项检查全部通过，含每轮真实 WF-05 聚合结果的数值基线、六维与七天计划。报告不保存临时访问 URL、Cookie、简历正文或模型输出。
- 续查发现浏览器缓存可跨会话回退能力报告，且空报告响应可能错误记入成功历史。现已在本地增加会话级缓存隔离、新简历/新分析/新面试时清理下游缓存、拒绝空响应并补回归测试；本地前端 Node 94/94。**此增补仍需提交、推送并以新 SHA 复验**。登录后的新 Preview 浏览器全程仍待完成，不能以接口三轮替代。
- 发布前剩余独立门禁：至少 5 名真人试用；生产 PostgreSQL 的提供方与备份资源身份仍未确认，不能安全完成隔离恢复演练；当前生产版本未做本轮修复的线上复验。单位库/实时职位检索已按用户决策不纳入核心版范围。任何门禁未齐时保持 PR 草稿，不合并生产。

## 2026-09-29 求职信原因定位与登录态页面修复（最新状态）

- 诊断提交 `90b6b02` 的 Preview `https://career-coach-dw210j3st-zimo66067.vercel.app` 三轮接口验收完成：199 项检查通过、无失败，报告 `deliverables/core-acceptance-20260929-reasons.json`。三轮候选证据 4/1/1 条、清理错误均为 0；诊断均 model，改写 rule/model/model，面试证据提取均未降级；不能把接口通过等同于所有模型任务稳定通过。
- 求职信 model/rule/rule；后两轮明确返回 `target_not_referenced`，即正文未逐字引用目标公司或职位，触发现有拒绝规则。此次修复补充对应生成约束，不放宽事实和目标校验；修复后的真实模型复测仍待完成，不能反推旧版本的唯一根因。
- 登录态浏览器已完成合成样例诊断，发现两个页面问题：后端 rationale 未被显示，以及样例实际进入账号历史却声称不保存。已修正 public/docs 两份脚本与回归测试；未删除用户历史。修复前浏览器只走到诊断页，不声称后续全流程通过。
- 本次本地验证：求职信测试 21/21、Quick Demo 契约 5/5、镜像 30 文件一致、敏感扫描 294 文件通过；前一轮完整前端 86/86。这些测试集合不相加。当前新增修复仍需同 SHA CI、Preview 与浏览器复验。
- 用户选择免费外部监控。Vercel Hobby 告警页面要求升级 Pro，未升级。命令行集成发现意外要求登录，已取消，改查官方 Marketplace：首项相关监控为 Checkly。官方定价确认 Hobby 免费且支持邮件，注册页却先显示 14 天试用，因此必须在账号内核实免费计划及用量上限。已打开注册页交用户完成，未创建监控、未发送告警、未接受协议或付费。
- 生产恢复仍受资源确认阻断：项目存储仅显示独立 Preview 库；团队另有未连接项目的 `neon-amber-cave`，不能仅凭名称/创建日期认定是生产库。尚未恢复或读取生产数据。下一步确认生产数据库资源身份与备份窗口，再在隔离目的地演练，不覆盖生产。
- 发布门禁仍未齐：修复后的模型稳定性、登录浏览器完整闭环、生产恢复、告警触发及恢复通知到达。PR #8 保持草稿，不合并生产；真人试用仍不能由合成测试替代。

## 2026-09-29 引文定位修复与三轮验收完成（最新状态）

- 修复提交 `747a23638825715a20c99461e51430eb48384d69` 已推送至 `codex/core-release-20260928`，PR #8 未合并。Preview `dpl_7T5AVePAkN4ufJjSbFnHeDj7We8Q` READY，地址 `https://career-coach-pjk2tkj21-zimo66067.vercel.app`；[对应 CI](https://github.com/zimo66067-wq/career-coach/actions/runs/36511568589) 通过。
- 本地复现并修复：引文逐字存在于原文，但模型提供的 start/end 不准确时，旧归一化逻辑丢弃引文并换成固定截断窗口。现在只对逐字匹配的引文重新定位；不存在于原文的引用仍拒绝，完整片段及用户确认门槛不变。旧线上失败未保留原始模型输出，因此此为已复现缺陷及修复后的成功证据，不声称取到了旧请求的唯一根因。
- `deliverables/core-acceptance-20260929-quotes.json`：三轮真实 Preview API 流程完成，200 项断言全部通过；候选证据分别创建 1、5、1 条，去重跳过均为 0；每轮清理错误为 0。覆盖诊断/改写、证据确认、岗位与行动、面试证据、求职信与投递结果、越权/无同意边界和合成会话清理。
- 模型来源：三轮诊断均 `model`，改写均 `model`，面试证据提取均未降级；求职信分别为 `rule/model/rule`，均基于目标岗位和已确认证据。求职信实际耗时约 3.6/4.2/4.1 秒，不能据此认定超时。现有接口未返回具体降级原因，不能确定为模型不可用还是输出被事实校验拒绝；完整模型质量验收仍有缺口。
- 后续测试：相关 Python/API/安全 50/50；最终核心/安全子集 25/25；本地真实 HTTP 冒烟 70/70；前端契约 85/85；敏感信息扫描通过。不同集合互有重叠，不相加为独立用例数。
- 剩余：登录后的真实浏览器全程验收、求职信降级原因的安全可观测性与稳定性、生产 PostgreSQL 恢复演练及告警到达验证、完整账号数据权利；真人试用人数仍为 0。以上三轮是同一组合成场景的重复验收，不代替五名真人或大规模性能验证。核心修复尚未发布至生产。

## 2026-09-29 Preview 签名配置修复后复测

- 新部署 `dpl_5ubNiT3poMdRbAuBMjfpFtmAQq7u` 为 Preview、READY，代码 `998c91318c841d11df3b7ed4ffa7a0be73123196`，地址 `https://career-coach-nw4jw50w8-zimo66067.vercel.app`。对应 PR CI 与部署检查均通过。
- `deliverables/core-acceptance-20260929-preview.json` 保存严格验收结果：健康/持久化门禁通过；同意接口 HTTP 200，原 503 阻断已解除；诊断 HTTP 200、`diagnosis_mode=model`，耗时 33.906 秒。
- 改写接口 HTTP 200，待确认及非空断言通过，但 `rewrite_basis=rule`，不能称为真实模型改写成功。
- 候选证据接口 HTTP 201，但 `created` 为空，`TC02 real evidence available` 失败。0/3 完整轮次，后续岗位/面试/行动环节未执行；合成会话清理成功，cleanup_errors=0。
- 代码检查表明候选证据要求诊断的指定子项含 `source_spans`，且引文须为原文中的完整、实质性片段。当前报告没有保存原始模型响应，因此尚不能确定本次是引文缺失、被过滤，还是去重；不得降低证据校验或把空结果算通过。下一步应增加不含正文的拒绝原因/计数诊断并复现，再修复实际原因。
- 尚未合并或发布核心修复。用户此前重新部署过旧生产代码 `295a8e9`，部署 ID 为 `dpl_FmLgoPHkZG5yiDDREhM5k234Tj1p`；本轮仅验证 Preview。

## 2026-09-28 核心版发布门禁（优先于下方历史阶段记录）

用户已确认仅发布核心版，并授权在验证通过后提交、推送及部署修复。全国单位库、实时职位检索、竞赛提交包不属于本次发布门槛；仓库保持当前公开状态，不变更权限。

发布前生产回滚基线：`295a8e9d27397f03b8bce31af9413668642aebca`；部署 `dpl_5pY61D9ni9FfY8BKjtHxwAS3saVE`。本节的本地修复在新部署被核实之前，不得称为已上线。

| 门禁 | 当前证据 | 状态 |
|---|---|---|
| 真实核心业务链路 | 新测试复现两个 422：候选证据、岗位按会话分析都把数据库嵌套 `resume.resume_text` 错读成顶层；本地已修复 | 本地通过，线上待复测 |
| 模型质量与来源 | `deliverables/core-acceptance-20260928-initial.json`：诊断 51.922 秒后降级，严格门禁失败；依赖链停止并清理合成会话 | **未通过，不能沿用旧 21/21** |
| 五类正式自动化用例 | `tests/test_core_release.py`：完整链路、降级反向控制、并发限流、日志秘密保护、SQLite 隔离恢复；5/5 | 通过，仅合成测试 |
| 回归 | 本轮全量 Python 538/538；前端 Node 85/85；Python 首次异常耗时运行被中止，重新完整运行 929.22 秒通过 | 本地通过，远端 CI 待核实 |
| 安全加固 | 空模型输出不再标真实模型；异常/迁移日志及健康响应不输出异常正文；会话删除明确保留长期档案；旧导出工具禁止默认写仓库及覆盖既有文件 | 本地测试通过，待部署 |
| 浏览器端 | 生产首页与简历页可见，主流程需要登录；未使用用户账号或创建真实账号绕过门禁 | 已验入口，登录后全程未验证 |
| 真人试用 | 已生成并执行合成用例，实际真人参与数 0 | 仍未完成，不用自动化冒充 |
| 生产恢复与告警 | 本地 SQLite 合成库完整性与逐表恢复通过；没有生产 PostgreSQL 管理凭据或恢复证明、告警接收验证 | **生产部分未验证** |

### 本轮提交与远端验证

- 工作分支：`codex/core-release-20260928`；首个修复提交 `9629b4c`，已推送；[PR #8](https://github.com/zimo66067-wq/career-coach/pull/8) 保持草稿，未合并 main。
- 该提交 [CI](https://github.com/zimo66067-wq/career-coach/actions/runs/36391505509) 成功。Vercel Preview `dpl_Htw8E61AYSmvfjvYfTqEACJfvZx1` 构建 READY，指向同一 SHA；这不是生产部署。
- 通过 Vercel 认证读取 Preview 健康接口：`database=sqlite`、`model_ready=false`、`model_reason=model_name_missing`。普通未认证抓取会重定向为登录 HTML，不能把 HTTP 200 当 API 成功。
- **后续已修模型名范围**：通过平台 UI 将现有非敏感 `DUMATE_MODEL=glm-4-flash-250414` 从 Production 扩为 Production + Preview，没有读取或变更任何密钥、没有改动生产模型值。对 `6d6a0c8` 重新部署生成 `dpl_7rEzB17mEaLNfU66BaoCrWW22Sc7`；认证健康检查确认 `model_ready=true`、迁移正常，但仍为 `database=sqlite`。
- **2026-09-28 独立测试库已完成**：用户授权创建免费隔离库后，通过 Vercel 已有 Neon 集成新建 `career-coach-preview-20260928`，资源 ID `restless-cherry-16010088`。平台显示 Free，无需信用卡，0.5 GB / 100 CU-hours 每项目；关闭额外 Neon Auth。项目连接页确认仅 Preview，Production 未连接；平台自动注入敏感环境变量，没有读取或导出连接串，没有复制生产数据。
- 基于 `8e1ceb6e6f10c22fe1611c9e4a7de9648546b7f8` 重新部署 Preview：`dpl_AxvDZ6WYhMDwmM6M1zs2ajJRYXqh`，地址 `https://career-coach-gebl4xyrz-zimo66067.vercel.app`。认证健康检查返回 HTTP 200、`database=postgres`、`migrations.ok=true`、`model_ready=true`。这证明配置及迁移就绪，不证明真实模型推理或完整业务通过。该 SHA 的 [CI](https://github.com/zimo66067-wq/career-coach/actions/runs/36392337959) 成功。
- 用户已授权仅本次测试使用的 23 小时临时访问凭据，已创建并通过隐藏输入交给验收进程。访问 URL 和 Cookie 仅在内存处理，未写入报告或仓库，未关闭预览保护。脚本新增 `--protected-access-prompt`，校验凭据 URL 与目标同源；相关核心/安全测试 23/23 通过，敏感扫描通过。
- **正式 Preview 复测失败证据**：`deliverables/core-acceptance-20260928-preview.json`，健康检查与 PostgreSQL/模型配置门禁通过，但 `POST /api/wf01/consent` 返回 503；0/3 完整轮次，未提交简历或调用后续模型流程。平台环境变量页面确认 `DUMATE_CONSENT_SECRET` 仅 Production，Preview 缺失；代码在此配置缺失时返回 503，与实测一致。尚未采集该响应的具体错误码，不把推断写作完整错误响应证据。
- 当前需用户在平台新增同名、仅 Preview 的独立随机签名 Secret（不改原 Production 项，不复用生产值，不发聊天），再重新部署 Preview 并重跑。浏览器创建认证凭据需用户完成输入和保存，不能以开发环境默认签名或关闭保护绕过。生产恢复/告警与完整业务验收仍未完成。
- 本地真实 HTTP 冒烟 70/70；依赖安全扫描无已知漏洞；前端镜像、活文档路径、公开范围、敏感信息扫描通过。
- 生产探针的 HTTP 与 CORS 检查通过，但使用了 `--skip-freshness`，因此没有确认线上静态与当前分支相同。本轮发现它在跳过版本检查后仍输出“线上静态 = HEAD”，已修正文案并添加正反回归测试。
- 补充提交 `6d6a0c8` 已推送且 [CI](https://github.com/zimo66067-wq/career-coach/actions/runs/36391932975) 成功。后续仅文档/验收门禁变更须继续核对对应 SHA 的 CI，不能用早先绿灯替代。
- Preview 持久化环境门禁现已通过，完整业务验收仍未通过。当前生产仍为前述回滚基线，**本轮业务/安全修复尚未上线**。应先补齐 Preview 独立签名密钥及三轮业务复测，再决定是否转为可合并并发布；不默认开通付费资源。

### 当前真实模型调用范围

核心调用点为 `resume_diagnosis`、`resume_rewrite`、`interview_question`、`interview_evidence`、`cover_letter`。JD 解析、匹配决策、面试评分/复盘与行动计划主要走当前规则实现。旧脚本中的 `resume_report`、`jd_match_explain`、`jd_extract`、`interview_review`、`seven_day_plan` 不能直接当作当前页面实际模型调用；外部 DuMate 工作流另行验收。面试追问既有模型路径，也有引用回答的规则路径，不能仅凭题目非空宣称模型成功。

线上重跑使用 `scripts/core-release-acceptance.py`，通过业务接口复用服务端秘密，不导出密钥。报告只保存断言、耗时和来源标志，失败保留、不覆盖。真实主模型和备用模型与规则降级分开记录。三轮小样本只能支持冒烟结论，不足以证明 P95 或大规模并发性能。

### 生产运行保障验收（不得用本地模拟代替）

1. 监控：现有 `scripts/api-prod-probe.py --skip-freshness` 检查 HTTP/跨源边界；健康检查 `model_ready` 仅表示配置就绪。还需平台故障告警明确接收人，触发一次合成告警并核对到达、恢复通知，不向日志平台发送真实简历或完整响应。
2. 恢复：在数据库提供方确认备份保留期与恢复能力，恢复到独立非生产数据库，核对迁移版本、各核心表数量/关系，再用合成账号完成一轮读写。不得覆盖生产库。RPO/RTO 需按实测与业务目标确认，不能先写保证值。
3. 密钥：先前在会话中出现过的密钥应在提供方撤销/轮换；当前生产密钥是否为新密钥不能从健康接口判定。本次不回显、不导出任何生产密钥。
4. 数据权利：当前会话删除不是账号注销。完整账号数据导出/删除与保留期限仍需单独交付，不应向用户承诺“全部资料已删除”。
5. 发布：特性分支 → PR → CI → Preview 验证 → 确认无阻断 → main/生产 → 同一版本线上复测。任一关键门禁失败，只保留工作分支与证据，不强行合并。

---

这份文档回答一个问题：**离"真实用户能走通一个完整流程"还差什么。**
它是这件事的唯一台账 —— 状态只在**实测过**之后才改；没实测就老实写「未验证」。

标注：**【你】** = 只有账号持有人能做的（控制台、凭据、真人、业务决策）；**【我】** = 仓库内可代做的。
完成一条就把它的状态改成 ✅（附实测证据），不要凭印象勾。

> **当前状态（2026-09-21 晚，Redeploy 后）**：**路由渠道通了，AI 渠道也通了。**
> 两份判据在同一时刻各自退出 0：
> · `scripts/api-prod-probe.py` —— 静态 = HEAD、`/api/health` = 200、其余接口都由应用应答；
> · `work/prod-ai-path-probe.py` —— `POST /api/wf02/diagnose` 返回 `diagnosis_mode = 'model'`。
>
> §一、§一之二记的是**同一天发现的两个阻断项，均已解除**，根因都留着 ——
> 因为下一次同类症状会以同样的样子出现（一个是“平台挑错了 WSGI 入口”，
> 一个是“环境变量按部署绑定，改完不重新部署就不生效”）。
> **两个坑的教训都不是“某个值填错了”，而是“原有判据根本看不见这一层”。**
>
> GitHub Pages 那条跨源渠道同日已在代码侧修掉（放行名单改并集），探针第 3 节三行全 `OK` —— **已收口**。
> **仍待完成**：§二的 P0-03 修正后真模型复跑、G8 真人验证、G9 交付与仓库可见性口径；§三的 F5 数据接入前置条件。2026-09-23 已选定大陆优先、北京官方开放数据试点，但未取得实际数据或完成职位实时性验证。

---

## 一、原阻断项（2026-09-21 已解除）与根因记录

判据不是"首页能不能打开"，而是 **`/api/*` 有没有被应用接住**。
一条命令给出现状（它自己按前端字面量找探测源，不写死域名）：

```bash
.venv-audit/Scripts/python.exe scripts/api-prod-probe.py
```

2026-09-20 实测：线上静态资源 = HEAD（3 个新鲜度探针全 OK），
但 `/api/*` 的**每一个**路径都返回同一个 404，且不带应用无条件设置的 `Cache-Control: no-store`。

### 根因（2026-09-21 由**本地复现**定案，不是推断）

线上返回的是 **Werkzeug 默认 404**（207 B、md5 `e46c4e5e1fbc`）。
在本地，**只 import `api/app_instance.py`**（当时叫 `api/app.py`）时，
`/api/health` 返回的正是 **404 / 207 B / md5 `e46c4e5e1fbc` / 无 `no-store`** —— 与线上逐字节相同；
而 **import `api/index.py`** 时同一路径返回 **200 / 591 B / 带 `no-store`**。

⇒ **Vercel 的 Flask 预设按文件名挑入口**（文档给的候选名：`app.py` / `index.py` / `server.py` /
`main.py` / `wsgi.py` / `asgi.py`，位置是仓库根，以及 `src/`、`app/`；实测 `api/` 也会被搜到），
而 `app.py` 排第一顺位。仓库里当时恰好有一个 `api/app.py`（现已改名）—— 那是 Phase 7c 为消除循环 import 把
app 对象下沉成的**叶子模块**（只 `Flask(__name__)`，不注册任何路由）。预设 import 的就是它。

一个**看起来像反证、其实不是**的点：`api.app_instance.app is api.index.app` 为真。
平台只 import 入口那一个模块，**是不是同一个对象无所谓**，"import 它的时候有没有顺带把路由注册上去"才决定线上行为。

### 修法（都在仓库里，不需要改预设）

1. **把原来是 `api/app.py` 的叶子模块改名 `api/app_instance.py`**（旧路径已修，勿再引用）—— 把错的候选名从名单里拿掉。改名后 `api/` 下
   与入口有关的候选只剩 `index.py`（正确的那个），**解析顺序不再是变量**。
2. **根目录 `app.py`** —— 把**同一个** app 对象绑定在根目录的候选名上。文档说根目录优先，
   所以这是"第一顺位"的那条路径；即使顺序与文档不符，第 1 条也已经兜住了。
3. **新增 `scripts/entrypoint-resolution-check.py`** —— 逐个候选名在**全新子进程**里 import，
   要求每个都解析出"规则数 > 1 且 `/api/health` = 200"。**这是唯一能在本地抓住这类 bug 的判据**：
   `tests/` 全都显式 `from api.index import app`，走的直连路径，从来看不见"按文件名会解析到谁"。

### 一次失败的尝试（别再走一遍）

先试的是 `pyproject.toml` + `[tool.vercel] entrypoint = "api.index:app"`（这是官方文档给的
另一个显式声明方式）。**结果构建直接失败**（部署 `dpl_5C4T1VTqfAibMjrHDXetHndVJcnd`）：
**`pyproject.toml` 一存在，平台就改用它作为依赖来源**，以本仓库为 Python 项目去安装；
而本仓库是 flat layout、有多个顶层包（`api`/`domain`/`providers`/`repositories`/`services` …），
setuptools 自动发现报 `Multiple top-level packages discovered`。本地可复现：

```bash
.venv-audit/Scripts/python.exe -m pip install --dry-run --no-deps .
```

所以 `pyproject.toml` **已被删除**，依赖仍走 `requirements.txt`；入口用"文件名"这条路径声明。

| # | 事项 | 谁 | 怎么做 / 判据 |
|---|---|---|---|
| 1 | 核对 Vercel 项目构建设置 | **【你】** | Settings → Build and Deployment：**Root Directory 留空**（= 仓库根 ✅ 已确认）、**Framework Preset 保持 `Flask`**、**Output Directory 留 `N/A`**（Flask 预设自己管静态根 —— 线上 `/capability_matrix.md` 正是从 `public/` 取的，说明它对）。**⚠️ 不要改成 `Other`**：那会切回"`api/` 下每个 `.py` 各自是函数"的约定，而本目录有 25 个 `.py`，其中 23 个不导出任何 handler。 |
| 2 | 补齐生产环境变量 | **【你】** | Settings → Environment Variables（Production）：`ZHIPU_API_KEY`、`DUMATE_MODEL`、`DUMATE_CONSENT_SECRET`、`DATABASE_URL`、`APP_ENV=production`。缺 `DUMATE_CONSENT_SECRET` 会让同意令牌直接失败。`DUMATE_ALLOWED_ORIGINS` 属**追加**项（2026-09-21 起语义是并集，见 §一末）：**不设也照样能用 GitHub Pages 渠道**，只有要额外放行别的跨源前端时才需要填。✅ **2026-09-21 已核对**：`DUMATE_MODEL` 原为「秘密」类型（值不可读、无法改类型），已删掉重建为「配置」，值 `glm-4-flash-250414`、只勾 Production；`ZHIPU_API_KEY` 保持秘密。 |
| 3 | ~~入口修复进主干后点 Redeploy~~ | — | ✅ **已完成**（2026-09-21）：修复（`ec1ce27`）推上主干后 Vercel 自己建了生产部署，**状态 success**，不用手点。 |
| 4 | ~~复跑探针确认阻断解除~~ | **【我】** | ✅ **已完成**：`scripts/api-prod-probe.py` **退出码 0** —— 静态 = HEAD、`/api/health` = **200**、其余接口都是应用在应答（415 / 428 / 404 带 `no-store`）。 |
| 5 | ~~取 Functions 列表与 Build Logs~~ | — | ✅ **不需要了**（定案靠本地隔离 import 对照，没用到平台日志）。保留此行的理由：万一以后又出现同类症状，这是最后一条后备取证手段。 |
| 6 | 端到端冒烟（F1→F5 真流程） | **【我】** | ✅ **2026-09-23 生产合成用户流程通过**：同意 → 简历真模型诊断（`diagnosis_mode=model`）→ JD 解析（16 项要求）→ 匹配（M=80）→ 面试 3 答并结束（I=39.33）→ 七天计划 → 待确认求职信 → 申请创建并可查询 → 会话删除 `DELETED`。仅验证这组合成输入的完整路径，不替代 G8 真人测试。仓库里的 `scripts/phase4-http-smoke.py` 则只验本地端口与状态机。 |

### 另一条渠道：GitHub Pages 前端调不到 API（已修复，代码侧，2026-09-21）

生产域名**既是页面也是 API**，从它打开是**同源**、CORS 不参与 —— 所以主渠道一直可用。
但仓库里还有一个**跨源**前端（GitHub Pages）：`https://zimo66067-wq.github.io/career-coach/`
**实测在线**（200，`js/pages-api-config.js` 就在那儿），而那个文件存在的唯一理由
就是给非 Vercel 宿主的页面找 API 地址。2026-09-21 实测它是坏的：

```
预检 OPTIONS /api/wf01/consent  Origin=https://zimo66067-wq.github.io  code=204  ACAO=(无)
POST   /api/wf03/jd             Origin=https://zimo66067-wq.github.io  code=403  「请求来源未获授权」
```

⇒ 从 GitHub Pages 打开页面时，**浏览器会拦掉所有接口调用**，写操作还会被应用直接 403。

**原因（是一个语义错，不是漏配）**：`api/http_layer.py` 的 `configured_origins()` 原来写的是
"平台变量覆盖默认值"。默认值本身是对的（不设置时就是那个 Pages 源），但只要**设置了**这个变量
（哪怕是为了别的源），默认值就被整体换掉 —— 于是"**忘了把第一方源也列进去**"成了比
"根本没设置"更坏的配置。三处都看不见：仓库里（默认值是对的）、本地/CI（同源不经过 CORS）、
门禁（没有判据探线上配置）。

**修法（已在仓库里改掉，不用你动控制台）**：放行名单改成 **并集** ——
`builtin_origins()`（= `PUBLIC_PAGES_ORIGIN`，**永远放行**）∪ `env_origins()`
（平台变量 `DUMATE_ALLOWED_ORIGINS` 里**追加**的源）。于是"平台侧的省略"不再能关掉第一方渠道；
真要禁掉它只能改代码，那会是一次 review 里看得见的 diff（**这是决定，不是遗漏**）。
`DUMATE_ALLOWED_ORIGINS` 仍然有用，但语义变成"追加"，**不设也照样能用 Pages 渠道**。

**验收判据（已升级为硬门）**：`scripts/api-prod-probe.py` 第 3 节现在探三件事 ——
第一方源预检必须拿到 ACAO、写操作不得是 403、**敌对源（保留 TLD `*.invalid`）必须拿不到 ACAO**。
第三条是反向控制：没有它，"把名单写成全放行"也会是绿的。

**已做的本地验证**（不必等部署）：`work/verify-cors-fix.py` 起两个本地 app 用同一个探针探 ——
真实现退出 0；把 `origin_allowed` 换成无条件放行后退出 1，且失败项正是反向控制那条。
单元层面 `tests/test_api_boundary.py::test_cors_builtin_pages_origin_survives_env_override`
即是那个语义的反向控制（改回"替换"语义立刻变红）。

**部署后确认（已做完，2026-09-21 12:0x）**：这两笔改动推上主干（`404e656..0242a89`）后，
GitHub Deployments API 显示 **`0242a89` 的 Production 部署 = success**（`github-pages` 同 SHA 也 success），
随后 `python scripts/api-prod-probe.py` **退出码 0**，第 3 节三行全是 `OK`：

```
预检 OPTIONS /api/wf01/consent  Origin=https://zimo66067-wq.github.io  code=204  ACAO=它自己
写操作 POST /api/wf03/jd        Origin=https://zimo66067-wq.github.io  code=428（不是 403）
反向控制 同一路径                Origin=https://probe-hostile-origin.invalid  code=204  ACAO=(无)
```

⇒ **GitHub Pages 那条渠道现在真的能调 API 了**，而且没有变成"全放行"。日志留档：
`work/probe-after-cors-fix.log`。**这一步不需要你做什么**（原来挂着的"要不要支持这个渠道"
已由你在 2026-09-21 决定为"支持"，修法落到了代码里，不用动控制台）。

**一个已知的非阻断现象**：`career-coach-<hash>-zimo66067.vercel.app` 这类**部署 URL** 会 302 到 Vercel 登录
（Deployment Protection），但**生产别名**是公开可达的。所以"部署 URL 打不开"不等于线上不可用；
反过来也别把"别名能打开"当成"部署没问题"。

**另一个已经踩过的坑**：本机 `git status` 会假报 `[ahead N]`。
原因是 `.git/refs/remotes/origin/` 这个目录不存在，git 写松散 ref 失败但静默返回 0。
**判定"推没推上去"只认远端**：`git ls-remote origin refs/heads/main`。
不要因为它假报 ahead 就重推或 force。

---

## 一之二、原阻断项（**2026-09-21 晚 Redeploy 后已解除**）：生产真模型链路是坏的

**症状**：生产上用户提交简历后能拿到一份诊断，`score_R` 有值、五个子分数齐全、
**HTTP 200** —— 但里面**没有一个字来自模型**，全是规则打分。

**判据**（`scripts/` 里没有这一条，这是它被抓出来的原因）：

```bash
# 仓库外脚本；探测源从前端字面量推导，不抄第二份域名
python work/prod-ai-path-probe.py
```

它打 `POST /api/wf02/diagnose` 并读 `diagnosis_mode`：`"model"` 才是硬门，
`"fallback_model"` 警告，规则降级是红。

**实测（2026-09-21）**：

```
health: model_configured=True database=postgres
diagnose: HTTP 200，耗时 51573 ms
  diagnosis_mode   = 'rule_fallback'
  model_trace_id   = 1789983186920_sz31f8rv     ← 不等于注入的 X-Trace-Id
  diagnosis_notice = 诊断模型暂时不可用，本次展示基于简历原文的基础规则诊断；……
```

**根因**：**上游调用超时，不是配置缺失**。两件事各自可判：

1. `rule_fallback_diagnosis()` 对**任何**原因都返回同一句文案，真实原因码只打到 stdout
   （Vercel 函数日志，外部读不到）。但 `diagnose_resume` 的两条降级路径用的 trace **不同**：
   配置缺失走**调用方传入**的 trace，调用失败走 **router 自己生成**的 trace。
   于是往请求里塞一个合法 `X-Trace-Id`、看它有没有被回显，就能把两者分开 ——
   实测**没有被回显** ⇒ 路由被构造了、真的发了上游请求。
2. 耗时 **51.6s** 几乎正好是 `MODEL_PARAMS["resume_diagnosis"].timeout` 的 **50s**。
   "模型名不存在"这个替代假设已**证伪**：用一个不存在的模型名打上游，
   **210 ms** 就返回 `HTTP 400 code 1211「模型不存在」` —— 不可能产生 51s 的挂起。
   另外 `vercel.json` 里 `maxDuration=60`，而路由器自己的 50s 先触发，
   所以是"优雅降级成 200"而不是 504 —— 这也是它一直没被发现的原因。

⇒ **配置的模型吞吐低于约 20 tokens/s，出不完 2048 tokens。**

**同一个病已在本地复现（同一份代码，只改环境变量；`work/verify-ai-path-probe.py`）**：

| 配置 | 探针 | `diagnosis_mode` | 耗时 |
|---|---|---|---|
| 有 key、无模型名 | 红 | `rule_fallback` | 0.9s |
| `MODEL_PROVIDER=mock` | 红 | `fallback_model` | 0.8s |
| **`glm-4-flash`** | 红 | `rule_fallback` | **51.1s** ← 与线上逐项吻合 |
| **`glm-4-flash-250414`** | **绿** | **`model`** | **21.2s** |

**修法（【你】控制台，一步）**：Vercel → Settings → Environment Variables → Production，
把 `DUMATE_MODEL` 改成 **`glm-4-flash-250414`**（或任何能在 50s 内出完的模型）。

**为什么不能靠调超时解决**：`MODEL_PARAMS` 是**冻结参数**（`providers/model_router.py`
文件头声明"不可运行时修改"）。为了让测试变绿去放宽冻结超时，就是把判据改成迎合现状 ——
要改就得当成一次产品决策来改，而不是当成修 bug。

**验收**：改完、重新部署后，`python work/prod-ai-path-probe.py` 必须**退出 0**
且打印 `diagnosis_mode = 'model'`。
⚠️ 注意 `python scripts/api-prod-probe.py` **看不出这件事** —— 它判的是静态与路由。
两份判据都过，才算两条路都通。

**实测结果（2026-09-21 晚，控制台改值 + Redeploy 之后，连测两次）**：

```
health: model_configured=True database=postgres
diagnose: HTTP 200，耗时 22983 / 23129 ms（两次）
  diagnosis_mode   = 'model'          ← 硬门通过
  score_R          = 83.5
  model_trace_id   = 1789991162579_1s285iki
  diagnosis_notice = (空)              ← 没有任何降级提示
  subscores        = {"achievement_evidence": 80, "ats_readability": 90,
                      "clarity": 85, "skill_evidence": 75, "structure": 90}
```

**这一段里踩到的第二个坑，比模型名本身更值钱**：**环境变量改完不等于生效。**
在控制台把 `DUMATE_MODEL` 改成正确值并保存之后，复测**仍然是红的**
（`rule_fallback`，51,858 ms，与此前 51,573 / 51,930 几无差别）——
因为 **Vercel 的环境变量是“按部署绑定”的**：值改了，**正在跑的那个部署里的快照不会变**，
必须**重新部署**（Redeploy，或推一个新提交）才生效。

判“线上跑的到底是哪个构建”可以用**本次新增的响应字段**当版本探针
（这轮用的是 `/api/health` 的 `model_ready`）：它比逐个比对静态文件快，也不受 CDN 缓存影响。
另一条经验：**手动 Redeploy 不会在 GitHub Deployments API 里留记录** ——
我当时正是在等部署列表刷新，却什么也没等到，于是差点把“没生效”归因错。
**真值是直接打线上接口，不是看平台的部署列表。**

顺带一条事实：那个变量原来被建成了 **「秘密」类型**，而秘密类型**值是只写的**
（界面恒显空值，且**不允许**把类型改回「配置」）。要换值只能**删掉重建**。
模型名本来就不是密钥 —— 设成秘密除了让下次改不动、让自己查不到现值之外没有任何好处。
这轮已删掉重建为「配置」类型，`ZHIPU_API_KEY` 保持秘密。

**本轮顺手补的观察面空洞**：`/api/health` 的 `model_configured` 只报"有没有
`ZHIPU_API_KEY`"，而 `build_model_router()` 要求**key 与模型名都在**。
于是"key 配了、模型名忘了填"的部署会被 health 判成"已就绪"，每次诊断却在降级。
已新增 `model_ready` / `model_reason`（与工厂同口径，见 `providers/model.py::model_config_status`）
并配了反向控制断言（`tests/test_api.py::test_health_reports_zhipu_configuration`）。

---

## 二、上线前必须完成的验证与交付

| # | 事项 | 谁 | 说明 |
|---|---|---|---|
| 7 | P0-01 真实模型复测 | **【你】** 给凭据 / **【我】** 跑 | ✅ **2026-09-21 已跑**（用临时 key）：`glm-4-flash-250414` 下 21 次调用全部返回。⚠️ 但"21/21 成功"这个说法**含水**：其中 6 条是模型**拒答**（`resume_report` 3/3、`jd_match_explain` 3/3），根因见第 8 项。 |
| 8 | P0-03 端到端真实数据闭环 | **【我】** | ⚠️ **脚本内容判据和输入已修，但仍缺带凭据的 7 类 × 3 次本地复跑。** `resume_report` / `jd_match_explain` 已改为真实结构化样本；空输出（含 `{}`、`[]`）、拒答、过短长文都不得计为成功。2026-09-23 新增的 5 个离线回归用例全部通过；同日生产合成用户路径已实测 `diagnosis_mode=model` 且全流程可走通、会话可删除。两项实测的范围不同：生产探针不调用 `resume_report` / `jd_match_explain` 等全部 7 类任务，旧的“21/21 成功”仍不能作为内容有效证据。当前环境无本地模型密钥；这两个无仓库调用方的任务是否纳入上线门槛，须按 DuMate 侧实际调用链核对。 |
| 9 | G8 真实用户验证（≥5 名真实参与者） | **【你】** | 模板已就绪；这件事**没有人能替你**，且必须真人才算数。 |
| 10 | G9 提交包冻结 | **【我】** 起草 / **【你】** 定稿 | 走 `scripts/p0-07-freeze.py`：方案 PDF（≤20 页 / ≤50MB）、演示 MP4（≤4 分 30 秒 / ≤500MB）、200 字简介、分享 URL、skill 导出、freeze-checklist、commit 记录。 |
| 11 | 仓库可见性口径 | **【你】** 决策 | 提交清单里写的是"私有仓库"，而当前仓库是公开的。要么改口径，要么改设置 —— 需要你定。 |

---

## 三、业务决策（只有你能定，且定了才能对外说）

| # | 事项 | 谁 | 说明 |
|---|---|---|---|
| 12 | F5 五项业务决策 | **【你】** | 数据授权 / 预算 / 责任人等，逐项见 `docs/product-scope.md` 与 F5 计划文档。 |
| 13 | D3（单位 / 职位检索） | **【你】+【我】** | ✅ **方向已定（2026-09-23）**：中国大陆优先、首批北京、先试官方开放数据；首选候选为北京市公共数据开放平台“单位招聘岗位信息”。⚠️ **接入尚未完成**：平台账号/调用标识码、实际数据字段、应用备案/审核、真实更新频率、成本及纠错责任待核实。当前目录最后更新 2026-07-02，不能宣称“实时职位”或全国单位库。原 2026-10-13 复核期限保留；详细来源与口径见 `docs/product-scope.md` §10.5。 |

---

## 四、这一轮已经在仓库内落地的（可复跑，不是声明）

| 产物 | 它填的观察面空洞 |
|---|---|
| `scripts/api-prod-probe.py` | 只有它同时看「线上静态是否 = HEAD」与「接口是否真的被应用接住」。原有的 `scripts/vercel-dead-routes.py` 只看配置、`scripts/p0-05-link-check.py` 只判链接可达、`scripts/phase4-http-smoke.py` 打的是本地端口 —— 三者可以全绿而线上一个流程都走不通。探测源从 `public/js/pages-api-config.js` 的字面量推导，避免此处再抄一份会漂移的域名。 |
| `scripts/vercel-dead-routes.py`（新增方向 B） | 原来只判「重写 → 处理分支」。新增「本地路由 → 重写覆盖」：`api/index.py` 里新增一条 `/api/xxx` 却忘了在 `vercel.json` 加 `source` 时，本地全绿、线上静态 404。判据自带反向控制探针（抽掉一条重写必须变红），防止它"绿着失效"。 |
| `docs/release-checklist.md`（本文） | 把"还差什么"从散落的对话与报告里收成一份带责任人的台账，并登记进 `contracts/living-docs.json` 的观察面。 |
| `scripts/entrypoint-resolution-check.py` | **唯一能看见"平台会解析到哪个入口"的判据**。它对每个候选入口名在**全新子进程**里 import，要求都能得到"带路由的 app"。缺了它，`tests/`（全都显式 import `api.index`）与 CI 可以全绿，而线上跑的是另一个模块。自带反向控制：同一段测量代码必须能把裸 app 判成无路由、把带路由 app 判成有路由，否则报红。 |
| `api/app_instance.py`（原来的 `api/app.py` 已修，此为其新名） | 把"错的候选名"从 Vercel 的入口名单里彻底拿掉。名字从此是**部署契约的一部分**，模块注释里写明了原因与实测指纹。 |
| 根目录 `app.py` | 把**同一个** app 对象绑定在根目录的候选名上（文档说根目录优先）。它与 `api/index.py` 两个候选指向同一个带路由的 app —— 于是**解析顺序无论怎么变，结果都一样**。 |
| `pyproject.toml`（**已删除，勿再加**） | 曾用它声明 `[tool.vercel] entrypoint`，会让平台改以本仓库为 Python 项目安装依赖 ⇒ flat layout 下 setuptools 报错 ⇒ **构建失败**。见上文"一次失败的尝试"。 |
| `providers/model.py::model_config_status` + `/api/health` 的 `model_ready` / `model_reason` | 补的是"**能不能调模型**"这个观察面空洞。原 `model_configured` 只回答"有没有 key"，而工厂要求 key **和** 模型名都在 —— 于是"忘了填模型名"的部署会被判成已就绪，而每次诊断都在降级、响应却仍是 200。反向控制断言在 `tests/test_api.py::test_health_reports_zhipu_configuration`（只给 key 时 `model_ready` 必须为假）。 |
| 仓库外的真模型链路探针（打 `POST /api/wf02/diagnose` 读 `diagnosis_mode`） | 补的是"AI 路径通不通"这个观察面空洞。`scripts/api-prod-probe.py` 判静态与路由、`scripts/phase4-http-smoke.py` 清掉 key 只验降级路径、`/api/health` 只看 key —— **三者可以同时全绿而线上一次模型都没调起来**。它另用一个外部可判的判别量：`diagnose_resume` 的两条降级路径用的 trace 不同，塞一个合法 `X-Trace-Id` 看是否被回显，即可把"配置缺失"与"调用失败"分开（两者都返回同一句用户可见文案）。 |
