/* mock-data.js · 与 tests/fixtures-synthetic/ 同源的演示数据（不可随意修改，须与合同保持一致） */
window.MOCK = {
  resumeText: `个人简历（合成样本，非真实人物）

姓名：[REDACTED_NAME]
电话：[REDACTED_PHONE]
邮箱：[REDACTED_EMAIL]
身份证号：[REDACTED_ID]
求职意向：后端开发工程师

教育经历
2019.09-2023.06 某某大学 计算机科学与技术 本科
主修课程：数据结构、操作系统、计算机网络、数据库原理

实习经历
2022.06-2022.12 某科技公司 后端开发实习生
负责订单中心微服务开发，使用 Go 语言和 Gin 框架实现订单查询接口
将订单列表接口的平均响应时间从 800ms 优化到 220ms，通过给 MySQL 加复合索引和引入 Redis 缓存实现
参与设计库存扣减的分布式锁方案，使用 Redisson 解决了超卖问题，上线后超卖投诉降为 0
编写接口文档并推动联调，与前端约定统一的错误码规范

项目经历
2023.03-2023.06 校园二手交易平台（课程项目）
独立完成后端全部开发，使用 Spring Boot + MyBatis，设计了 12 张数据表
实现基于 JWT 的登录鉴权和基于 RabbitMQ 的异步消息通知
项目在课程答辩中获得 92 分（满分 100）

技能清单
语言：Go（熟练）、Java（熟练）、Python（了解）
框架：Gin、Spring Boot、MyBatis
中间件：MySQL、Redis、RabbitMQ、Kafka（了解）
工具：Git、Docker、Linux 常用命令

自我评价
学习能力强，习惯阅读官方文档和源码，能够在指导下独立完成模块开发。
pii_removed:true`,

  resumeProfile: {
    version: "1.0", pii_removed: true,
    score_R: 73.0,
    subscores: {
      structure: { score: 80, label: "结构完整度", rationale: "教育/实习/项目/技能版块齐全，结构完整",
        source_spans: [{doc:"resume", quote:"实习经历", start:304, end:308}] },
      clarity: { score: 75, label: "表达清晰度", rationale: "表达具体，含协作与规范意识",
        source_spans: [{doc:"resume", quote:"编写接口文档并推动联调，与前端约定统一的错误码规范", start:405, end:434}] },
      achievement_evidence: { score: 60, label: "成果证据", rationale: "有量化成果但数量偏少",
        source_spans: [{doc:"resume", quote:"将订单列表接口的平均响应时间从 800ms 优化到 220ms，通过给 MySQL 加复合索引和引入 Redis 缓存实现", start:332, end:403}] },
      skill_evidence: { score: 70, label: "技能证据", rationale: "技能与岗位匹配但中间件深度待证",
        source_spans: [{doc:"resume", quote:"语言：Go（熟练）、Java（熟练）、Python（了解）", start:508, end:532}] },
      ats_readability: { score: 85, label: "ATS可读性", rationale: "纯文本结构清晰，ATS 可解析",
        source_spans: [{doc:"resume", quote:"技能清单", start:496, end:500}] }
    },
    suggestions: [
      { id: "S1", severity: "P1", issue: "自我评价偏主观，缺少事实支撑",
        suggestion: "将自我评价改写为可验证陈述，补充源码阅读或文档实践的具体例子",
        rewrite_draft: "独立完成订单查询接口开发并推动联调，习惯以官方文档为准排查问题",
        source_spans: [{doc:"resume", quote:"学习能力强，习惯阅读官方文档和源码，能够在指导下独立完成模块开发。", start:534, end:570}] },
      { id: "S2", severity: "P0", issue: "成果证据仅一处量化，其余经历缺少数字",
        suggestion: "为分布式锁项目补充量化结果口径，无法确认的数字用占位格式",
        rewrite_draft: "库存扣减方案支撑秒杀场景，峰值 QPS 待用户核实：约X",
        source_spans: [{doc:"resume", quote:"参与设计库存扣减的分布式锁方案，使用 Redisson 解决了超卖问题，上线后超卖投诉降为 0", start:370, end:404}] },
      { id: "S3", severity: "P2", issue: "课程项目缺少团队规模与本人分工说明",
        suggestion: "标注独立开发或团队角色，避免面试追问时表述含糊",
        rewrite_draft: "独立完成后端全部开发（1 人），设计 12 张数据表",
        source_spans: [{doc:"resume", quote:"独立完成后端全部开发，使用 Spring Boot + MyBatis，设计了 12 张数据表", start:445, end:490}] }
    ]
  },

  matchResult: {
    score_M: 60.0,
    summary: { hard: 50.0, responsibility: 100.0, preferred: 0.0, terminology: 100.0 },
    requirements: [
      { id: "J1", type: "hard", typeLabel: "硬性", status: "covered", text: "本科及以上学历，计算机相关专业",
        evidence: "2019.09-2023.06 某某大学 计算机科学与技术 本科" },
      { id: "J2", type: "hard", typeLabel: "硬性", status: "weak", text: "熟悉 Go 或 Java 至少一门语言，有实际项目经验",
        evidence: "使用 Go 语言和 Gin 框架实现订单查询接口" },
      { id: "J3", type: "hard", typeLabel: "硬性", status: "missing", text: "熟悉 MySQL，了解索引优化和慢查询分析",
        evidence: "仅有加复合索引实践，未见慢查询分析证据" },
      { id: "J4", type: "hard", typeLabel: "硬性", status: "unknown", text: "了解 Redis 等缓存中间件的使用场景",
        evidence: "unknown：材料不足以判断使用场景理解深度" },
      { id: "R1", type: "responsibility", typeLabel: "职责", status: "covered", text: "参与订单、库存等核心链路的接口开发",
        evidence: "负责订单中心微服务开发" },
      { id: "R2", type: "responsibility", typeLabel: "职责", status: "covered", text: "编写单元测试，保证代码质量",
        evidence: "推动联调并约定统一错误码规范" },
      { id: "P1", type: "preferred", typeLabel: "加分", status: "missing", text: "有分布式锁、分布式事务实践经验者优先",
        evidence: "有分布式锁实践，分布式事务未见证据（weak 边界，按缺口提示）", gap: "P0" },
      { id: "T1", type: "terminology", typeLabel: "术语", status: "covered", text: "Go、MySQL、Redis、RabbitMQ",
        evidence: "技能清单与实习经历均覆盖" }
    ],
    gaps: [
      { level: "P0", text: "分布式事务实践经验缺失", action: "第2天整理项目复盘笔记，准备 STAR 回答" },
      { level: "P1", text: "慢查询分析证据不足", action: "补充一次慢查询优化实例，未知数字用「待用户核实：」占位" },
      { level: "P2", text: "Redis 使用场景理解待确认", action: "面试中主动说明缓存一致性方案" }
    ]
  },

  interviews: [
    { turn_id: 1,
      question: "请介绍一个你最有成就感的项目，并说明你本人的贡献。",
      targets: ["成果证据", "结构化表达"],
      answer: "我在实习时负责订单查询接口的优化。当时的背景是接口平均响应 800ms，用户投诉集中在列表加载慢。我的任务是定位瓶颈并提出优化方案。我通过慢查询日志发现是索引缺失，于是加了复合索引，并引入 Redis 缓存热点数据。最终平均响应降到 220ms。",
      answer_quote: "最终平均响应降到 220ms",
      missing_elements: [],
      follow_up: { question: "你提到引入 Redis 缓存热点数据，缓存与数据库的一致性是怎么保证的？",
        reason: "回答中提到了缓存方案但未说明一致性策略，属于 action 深度追问" },
      subscores: { structure: 85, relevance: 88, specificity: 82, followup_adaptation: 70, clarity: 84 } },
    { turn_id: 2,
      question: "讲讲你在团队中和他人发生分歧的一次经历。",
      targets: ["协作沟通", "冲突处理"],
      answer: "有一次讨论库存扣减方案，同学主张直接数据库乐观锁，我认为高并发下应该用分布式锁。我们各自做了压测对比，最后结合两种方案：常态用乐观锁，秒杀场景切分布式锁。",
      answer_quote: "常态用乐观锁，秒杀场景切分布式锁",
      missing_elements: ["metric"],
      follow_up: { question: "你提到做了压测对比，具体的 QPS 数据还记得吗？",
        reason: "回答缺少 metric 维度，追问量化证据" },
      subscores: { structure: 72, relevance: 78, specificity: 60, followup_adaptation: 75, clarity: 70 } },
    { turn_id: 3,
      question: "如果这个岗位需要你在一个月内上手不熟悉的技术栈，你会怎么做？",
      targets: ["学习能力", "岗位适配"],
      answer: "我会先读官方文档的 Quickstart，然后找一个最小可运行示例跑通，再对照项目代码梳理调用链。之前学 Go 时我就是用这个方法，两周内能独立写接口。",
      answer_quote: "两周内能独立写接口",
      missing_elements: ["result"],
      follow_up: null,
      subscores: { structure: 70, relevance: 82, specificity: 65, followup_adaptation: 72, clarity: 74 } }
  ],
  score_I: 72.55,

  ability: {
    version: "1.0",
    resume_score: 73.0, match_score: 60.0, interview_score: 72.55,
    dimensions: [
      { key: "job_fit", name: "岗位契合", score: 60.0 },
      { key: "achievement_evidence", name: "成果证据", score: 60.0 },
      { key: "professional_expression", name: "专业表达", score: 75.0 },
      { key: "structured_answer", name: "结构化回答", score: 70.0 },
      { key: "job_depth", name: "岗位深度", score: 65.0 },
      { key: "followup_adaptation", name: "追问适应", score: 75.0 }
    ],
    baseline: 68.27,
    scenario_day7: { low: 77.79, high: 90.48, assumptions: [
      "0.30 与 0.70 为 MVP 演示假设，非统计学习参数",
      "假设用户按计划完成每天 30-45 分钟训练并产出 artifact",
      "第七天复测结果才是真实变化"
    ] },
    plan: [
      { day: 1, focus: "为三条核心经历补充量化证据，无法确认的数字用「待用户核实：」占位", minutes: 40, artifact: "修订后的三段经历文本" },
      { day: 2, focus: "针对 P0 缺口（分布式实践经验）整理项目复盘笔记", minutes: 35, artifact: "一页复盘笔记" },
      { day: 3, focus: "按 STAR 结构重写两个面试高频回答", minutes: 40, artifact: "两份 STAR 回答稿" },
      { day: 4, focus: "针对岗位术语（gRPC/Kubernetes）做概念速学并自测", minutes: 30, artifact: "术语自测清单" },
      { day: 5, focus: "完成一轮五题文字模拟面试并复盘 missing_elements", minutes: 45, artifact: "面试复盘记录" },
      { day: 6, focus: "根据复盘改写简历自我评价与技能描述", minutes: 35, artifact: "简历修订版 v2" },
      { day: 7, focus: "复测诊断与匹配，对比 C0 变化并记录真实提升", minutes: 40, artifact: "复测对比表" }
    ]
  }
};
