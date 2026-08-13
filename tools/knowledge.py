# -*- coding: utf-8 -*-
"""knowledge.py · 面经知识库 + BM25 检索（阶段4）

面经按 F3 面试场景分类；无 embedding key 时使用 BM25 全量可用，
配置 EMBEDDING_API_KEY 后可升级为向量召回（当前提供接口占位）。

用法:
  from tools.knowledge import search_questions, list_categories, list_questions
  search_questions("项目难点", category=None, limit=5)
"""
import math
import os

try:
    import jieba
except Exception:  # pragma: no cover - jieba 缺失时退化为字符分词
    jieba = None

CATEGORIES = [
    "自我介绍",
    "项目深挖",
    "行为面试",
    "技术能力",
    "压力与应变",
    "岗位理解",
    "反问环节",
]

# 种子面经（24 条）：id / category / question / keywords / answer / tips
KB_ENTRIES = [
    {
        "id": "kb-001",
        "category": "自我介绍",
        "question": "请用一分钟介绍自己。",
        "keywords": ["自我介绍", "一分钟", "开场"],
        "answer": "结构化三段式：我是谁（学历/专业+当前角色）、我做过什么（1-2 个与岗位最相关的成果，用数字量化）、我为什么适合（能力与岗位要求对齐，收尾表态）。",
        "tips": "控制在 60-90 秒，先讲结论再讲证据，不要复述简历全文。",
    },
    {
        "id": "kb-002",
        "category": "自我介绍",
        "question": "你的优势是什么？",
        "keywords": ["优势", "亮点", "核心竞争力"],
        "answer": "选 2-3 个与目标岗位强相关的能力，每个配一个 STAR 案例：情境-任务-行动-结果，结果必须有可量化产出。",
        "tips": "避免空泛形容词（认真、负责），用数据替代形容词。",
    },
    {
        "id": "kb-003",
        "category": "自我介绍",
        "question": "你的劣势或短板是什么？",
        "keywords": ["劣势", "短板", "不足"],
        "answer": "坦诚但选择可改进的短板，并说明正在采取的行动与已取得的进展，避免说自己无法改变的硬伤。",
        "tips": "回答结构：短板是什么 + 影响 + 改进动作 + 进展证据。",
    },
    {
        "id": "kb-004",
        "category": "项目深挖",
        "question": "挑一个你最满意的项目详细讲讲。",
        "keywords": ["项目", "复盘", "难点"],
        "answer": "按 STAR 展开：项目背景与目标、你的职责边界、关键技术或业务难点、你的具体动作、结果与复盘（可改进点）。",
        "tips": "提前准备 2 个可深挖的项目，一个技术向一个业务向。",
    },
    {
        "id": "kb-005",
        "category": "项目深挖",
        "question": "项目里遇到的最大困难是什么？怎么解决的？",
        "keywords": ["困难", "问题", "解决", "踩坑"],
        "answer": "讲清楚困难的全貌：现象、影响范围、排查过程、最终方案、验证结果；重点展示分析思路而不是只讲结果。",
        "tips": "不要甩锅给外部，也不要只说'查了资料'，要有自己的判断依据。",
    },
    {
        "id": "kb-006",
        "category": "项目深挖",
        "question": "这个项目你贡献了什么？",
        "keywords": ["贡献", "职责", "个人产出"],
        "answer": "区分团队成果与个人贡献：明确指出哪些模块/指标是你独立负责的，用提交记录、上线数据、评审反馈佐证。",
        "tips": "避免用'我们'掩盖个人角色，面试官想听你的个人价值。",
    },
    {
        "id": "kb-007",
        "category": "项目深挖",
        "question": "如果重做这个项目，你会改进什么？",
        "keywords": ["复盘", "改进", "重做"],
        "answer": "从技术选型、架构设计、协作流程三个层面各提一个具体改进，并说明预期收益，展示持续迭代意识。",
        "tips": "这是加分题，重点在'思考深度'而非'承认错误'。",
    },
    {
        "id": "kb-008",
        "category": "行为面试",
        "question": "讲一次你与同事意见冲突的经历。",
        "keywords": ["冲突", "协作", "沟通"],
        "answer": "用 STAR 呈现：冲突背景、双方立场、你采取的沟通动作（倾听-对齐目标-找证据）、最终共识与结果；强调对事不对人。",
        "tips": "结尾补充一句复盘：下次会如何更早介入，体现成长。",
    },
    {
        "id": "kb-009",
        "category": "行为面试",
        "question": "你如何安排多任务并行时的优先级？",
        "keywords": ["优先级", "多任务", "时间管理"],
        "answer": "给出明确排序方法：影响范围/紧急度/依赖关系打分，关键任务先排，保留缓冲；举一个实际并行案例说明取舍。",
        "tips": "不要说'我都做完'，要展示你如何做取舍。",
    },
    {
        "id": "kb-010",
        "category": "行为面试",
        "question": "你最近一次主动学习新技能是什么？",
        "keywords": ["学习", "成长", "自驱"],
        "answer": "说清楚学习动机、学习路径（文档/课程/实践）、产出物（项目/文章/开源贡献）与对工作的反哺。",
        "tips": "学习成果要落地：有产出比有课程证书更有说服力。",
    },
    {
        "id": "kb-011",
        "category": "技术能力",
        "question": "介绍一个你熟悉的技术栈及其适用场景。",
        "keywords": ["技术栈", "架构", "选型"],
        "answer": "从语言/框架/数据库/中间件四个维度介绍，说明各组件为什么被选、解决了什么问题、边界在哪。",
        "tips": "不要背八股，讲'为什么选'比'是什么'更显功底。",
    },
    {
        "id": "kb-012",
        "category": "技术能力",
        "question": "你怎么保证代码质量？",
        "keywords": ["代码质量", "测试", "重构", "规范"],
        "answer": "覆盖四层：规范与 Code Review、单测/集成测试覆盖率、CI 流水线卡点、重构与文档同步；举实际项目中的落地案例。",
        "tips": "每层都要有'我实际做过'的证据，而不是背诵流程。",
    },
    {
        "id": "kb-013",
        "category": "技术能力",
        "question": "线上出了问题你怎么排查？",
        "keywords": ["排障", "线上", "监控", "日志"],
        "answer": "按'止血-定位-根因-修复-复盘'五步回答：先评估影响面，再通过日志/监控/链路追踪定位，修复后补充监控与回归用例。",
        "tips": "强调止血优先与事后复盘，展示工程素养。",
    },
    {
        "id": "kb-014",
        "category": "技术能力",
        "question": "你怎么理解性能优化？",
        "keywords": ["性能", "优化", "瓶颈"],
        "answer": "先量化再优化：压测建立基线，用 profile 定位瓶颈，按性价比排序（缓存/索引/异步/算法），每次优化后复测验证。",
        "tips": "回答里带上你实际优化过的指标变化（如接口 P95 从 800ms 降到 200ms）。",
    },
    {
        "id": "kb-015",
        "category": "压力与应变",
        "question": "如果上线前发现严重 bug 你会怎么做？",
        "keywords": ["上线", "紧急", "bug", "应急"],
        "answer": "按紧急度分级：阻断性 bug 立即止损（回滚/熔断），同步干系人，并行定位根因，验证后灰度放量，最后补自动化用例。",
        "tips": "展示冷静与流程意识，别只说'马上修'。",
    },
    {
        "id": "kb-016",
        "category": "压力与应变",
        "question": "需求频繁变更你怎么应对？",
        "keywords": ["需求变更", "范围", "沟通"],
        "answer": "区分变更来源与影响：小变更走快速通道，大变更重新评估成本排期并同步干系人；用需求池管理优先级，避免无限返工。",
        "tips": "体现'管理期望'能力：不是被动接受，而是主动对齐。",
    },
    {
        "id": "kb-017",
        "category": "压力与应变",
        "question": "你如何应对 deadline 很紧的情况？",
        "keywords": ["deadline", "工期", "加班", "交付"],
        "answer": "先拆解最小可交付范围，聚焦核心功能；主动同步风险并争取资源或裁剪范围；加班是短期手段，长期靠流程与缓冲。",
        "tips": "展示你'先保主路径'的判断力。",
    },
    {
        "id": "kb-018",
        "category": "岗位理解",
        "question": "你为什么选择这个岗位？",
        "keywords": ["岗位", "动机", "职业规划"],
        "answer": "结合专业背景、过往项目与岗位 JD 的匹配点说明动机，展示你对岗位日常职责与成长路径的理解，避免只说'感兴趣'。",
        "tips": "至少引用 JD 里的 2 个关键词做锚点。",
    },
    {
        "id": "kb-019",
        "category": "岗位理解",
        "question": "你对公司/团队了解多少？",
        "keywords": ["公司", "业务", "调研"],
        "answer": "从产品/业务、技术、近况三个维度展示调研：公司核心产品与客户、团队技术栈、最近的产品动态或新闻。",
        "tips": "体现'做功课'，但不要背诵官网原文。",
    },
    {
        "id": "kb-020",
        "category": "岗位理解",
        "question": "未来 3-5 年的职业规划是什么？",
        "keywords": ["规划", "发展", "目标"],
        "answer": "给出与岗位成长路径一致的规划：1 年内胜任岗位核心职责，2-3 年独立负责关键模块，3-5 年成为领域专家或带团队；说明为达目标正在做的事。",
        "tips": "规划要落地：联系具体技能与岗位要求，避免空谈。",
    },
    {
        "id": "kb-021",
        "category": "反问环节",
        "question": "你有什么想问我们的？",
        "keywords": ["反问", "提问", "问题"],
        "answer": "问三类高质量问题：岗位实际工作内容与考核、团队协作与成长支持、业务方向与挑战；避免直接问薪酬和加班。",
        "tips": "提前准备 2-3 个问题，展示你的思考深度。",
    },
    {
        "id": "kb-022",
        "category": "反问环节",
        "question": "团队目前最大的挑战是什么？",
        "keywords": ["挑战", "团队", "业务"],
        "answer": "这是一个展示你'解决问题导向'的好问题：根据回答补充你的相关经验，形成对话而非问答。",
        "tips": "追问细节（如何度量、卡在哪），体现真实兴趣。",
    },
    {
        "id": "kb-023",
        "category": "行为面试",
        "question": "你如何给团队或他人提供帮助？",
        "keywords": ["帮助", "团队", "分享", "mentor"],
        "answer": "举例说明你的分享/指导行为：技术分享、Code Review 帮助、文档沉淀、新人带教；说明对象与可验证的反馈。",
        "tips": "体现协作与利他，同时不显得邀功。",
    },
    {
        "id": "kb-024",
        "category": "压力与应变",
        "question": "如果被否定或被质疑，你会怎么处理？",
        "keywords": ["质疑", "否定", "反馈"],
        "answer": "先区分事实与情绪：对事理性核对证据，对己反思改进点；用一次'被否后改进并被认可'的真实经历佐证。",
        "tips": "展示抗压与成长型思维，不要表现得委屈或过度辩解。",
    },
]

_STOPWORDS = {"的", "了", "吗", "呢", "是", "在", "我", "你", "他", "这", "那", "什么", "怎么", "一个", "什么"}


def tokenize_text(text):
    """jieba 分词（缺失时按字符 2-gram 退化）。"""
    text = str(text or "").lower()
    if jieba is not None:
        words = [w for w in jieba.cut(text) if len(w) > 1 and w not in _STOPWORDS]
        return words
    return [text[i:i + 2] for i in range(len(text) - 1)]


class BM25:
    """轻量 BM25：语料为 question + keywords + answer 前 80 字。"""

    def __init__(self, docs):
        self.docs = docs
        self.doc_tokens = [tokenize_text(doc) for doc in docs]
        self.avgdl = sum(len(t) for t in self.doc_tokens) / max(1, len(self.doc_tokens))
        self.k1 = 1.5
        self.b = 0.75
        self.df = {}
        self.idf = {}
        self._build()

    def _build(self):
        n = len(self.doc_tokens)
        for tokens in self.doc_tokens:
            for token in set(tokens):
                self.df[token] = self.df.get(token, 0) + 1
        for token, df in self.df.items():
            self.idf[token] = math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens, idx):
        tokens = self.doc_tokens[idx]
        dl = len(tokens)
        score = 0.0
        for token in query_tokens:
            if token not in self.idf:
                continue
            tf = tokens.count(token)
            score += self.idf[token] * (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            )
        return score

    def search(self, query_tokens, limit=5):
        scored = [(self.score(query_tokens, i), i) for i in range(len(self.docs))]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(round(s, 4), i) for s, i in scored[:limit] if s > 0]


def _doc_text(entry):
    answer_head = str(entry.get("answer") or "")[:80]
    return " ".join(
        [entry.get("question", ""), " ".join(entry.get("keywords", [])), answer_head]
    )


def list_categories():
    counts = {c: 0 for c in CATEGORIES}
    for entry in KB_ENTRIES:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    return [{"category": c, "count": counts.get(c, 0)} for c in CATEGORIES]


def list_questions(category=None):
    if category:
        return [e for e in KB_ENTRIES if e["category"] == category]
    return list(KB_ENTRIES)


def embedding_available():
    """是否配置了 embedding key；未配置时以 BM25 提供可用检索。"""
    return bool(os.environ.get("EMBEDDING_API_KEY"))


def search_questions(query, category=None, limit=5):
    """BM25 检索；embedding key 存在时返回 notice 提示可升级。"""
    query = str(query or "").strip()
    limit = max(1, min(int(limit or 5), 20))
    if not query:
        return {"items": [], "total": 0, "engine": "bm25", "notice": "请输入关键词进行检索。"}
    pool = list_questions(category) if category else list(KB_ENTRIES)
    docs = [_doc_text(e) for e in pool]
    bm25 = BM25(docs)
    query_tokens = tokenize_text(query)
    hits = bm25.search(query_tokens, limit)
    items = []
    for score, idx in hits:
        entry = pool[idx]
        items.append({
            "id": entry["id"],
            "category": entry["category"],
            "question": entry["question"],
            "answer": entry["answer"],
            "tips": entry.get("tips", ""),
            "keywords": entry.get("keywords", []),
            "score": score,
        })
    notice = ""
    if not embedding_available():
        notice = "当前使用 BM25 关键词检索；配置 EMBEDDING_API_KEY 后可升级向量召回。"
    return {"items": items, "total": len(items), "engine": "bm25", "notice": notice}


def search(query, category=None, limit=5):
    """兼容别名：search_questions 的简写。"""
    return search_questions(query, category=category, limit=limit)
