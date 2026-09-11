# -*- coding: utf-8 -*-
"""interview_engine.py · 文字自适应面试引擎（P0-04）

主路径: JD+简历缺口 -> 动态问题 -> 回答分析 -> 追问(<=1次) -> 下一题 -> 报告
降级: 动态生成失败 -> 岗位题库 -> 3道通用行为题
敏感阻断: 20条敏感词 -> 立即替换题目

用法:
  from tools.interview_engine import InterviewEngine
  engine = InterviewEngine(model_router=router)
  session = engine.start(job_profile, resume_profile, match_gaps)
  q = engine.next_question(session)
  result = engine.submit_answer(session, answer_text)
  report = engine.end_session(session)
"""
import json
import os
import re
import random
from difflib import SequenceMatcher
from typing import Optional

# ------------------------------------------------------------------ #
# 敏感问题关键词（20条），命中任意一条就替换题目
# ------------------------------------------------------------------ #
SENSITIVE_PATTERNS = [
    r"婚育|怀孕|计划生育|生育|备孕|产假|哺乳期",
    r"年龄|出生年月|生日|多大|几岁|哪年出生|属相|星座",
    r"民族|种族|籍贯|户口|户籍|出生地|老家",
    r"宗教|信仰|政治面貌|党派|党员",
    r"残疾|残疾证|健康状况|疾病|病历|体检",
    r"性取向|性别认同|同性恋",
    r"家庭收入|父母职业|配偶|结婚|单身|离婚|婚姻",
    r"身高|体重|外貌|相貌|长相",
    r"债务|贷款|征信|欠款",
    r"违法犯罪|犯罪记录|案底|前科|拘留",
    r"劳动仲裁|上家离职原因|被辞退|被开除|开除原因",
    r"工资|薪资|上家薪水|当前薪资|期望薪资|月薪|年薪|收入",
    r"社保|公积金断缴|断缴",
    r"住房|租房|自有住房|房贷|买房",
    r"子女|孩子数量|学龄|几个孩子|有无小孩",
    r"方言|母语|口音",
    r"抑郁症|心理健康|心理咨询|精神疾病",
    r"疫区|隔离|传染病|感染",
    r"退伍|服役|军事|兵役|当兵",
    r"工会|工会会员|工会身份",
]

# ------------------------------------------------------------------ #
# 危险模型输出检测（提示注入 / 凭据与隐私索取）
#
# 与 SENSITIVE_PATTERNS 含义不同：后者拦截歧视性 HR 提问；本组拦截
# 被注入或被操纵的模型输出，防止面试链路变成泄露系统提示、密钥或
# 索取候选人身份证/银行卡等个人信息的通道。安全闸门一律 fail closed。
# ------------------------------------------------------------------ #
_ASK_VERBS = (
    r"(提供|上传|粘贴|输入|填写|告知|告诉|说出|报出|发送|提交|索取|要求|"
    r"给我|发我|留下|出示|展示|泄露|补充|交代)"
)

UNSAFE_QUESTION_PATTERNS = (
    # 1) 提示注入：要求忽略/绕过/覆盖规则、系统提示或安全约束
    r"(忽略|忽视|无视|绕过|跳过|覆盖|推翻|取消|忘记|丢弃)[^。！？!?]{0,10}"
    r"(规则|指令|要求|设定|提示|约束|限制|策略|安全|角色|身份)",
    r"(ignore|disregard|forget|bypass|override)[^.!?]{0,24}"
    r"(rule|instruction|prompt|policy|guideline|safety|system)",
    # 2) 直接索取内部配置或凭据
    r"(系统提示词?|开发者消息|内部指令|隐藏指令|system\s*prompt|developer\s*message)",
    r"(api[\s_\-]*key|apikey|私钥|访问令牌|\.env\b|数据库连接串|数据库备份)",
    # 3) 带请求动词的凭据索取（避免误伤「密码学」「token 机制」等技术提问）
    _ASK_VERBS + r"[^。！？!?]{0,12}"
    r"(密码(?!学|算法)|口令|验证码|密钥|令牌|token|凭据|账号|环境变量|连接串)",
    # 4) 带请求动词的 PII 索取
    _ASK_VERBS + r"[^。！？!?]{0,12}"
    r"(身份证|手机号|手机号码|电话号码|邮箱|住址|家庭地址|家庭住址|银行卡|"
    r"微信号|微信|qq|支付宝|护照|社保)",
    # 5) 无动词也需拦截的高危短语
    r"身份证号(码)?|银行卡号|护照号|社保号",
)

# ------------------------------------------------------------------ #
# STAR 缺口检测关键词（启发式）
# ------------------------------------------------------------------ #
STAR_KEYWORDS = {
    "situation":  ["场景", "情况", "当时", "背景", "项目背景", "context", "在.*项目中", "在.*工作中", "实习", "工作经历"],
    "task":       ["任务", "目标", "负责", "职责", "需要完成", "objective", "分工", "承担"],
    "action":     ["采取", "实施", "做了", "使用", "通过", "方法", "工具", "approach", "采用", "实现", "编写", "开发", "设计", "搭建", "重构", "优化", "引入"],
    "result":     ["结果", "效果", "提升", "降低", "减少", "增加", "完成",
                   "实现", "达到", "改善", "优化", "节省", "缩短", "提高", "outcome", "上线", "交付", "部署"],
    "metric":     ["%", "百分比", "数字", "倍", "万", "次", "小时", "天",
                   "ms", "分钟", "秒", r"\d", "百万", "亿", "千"],
    "reflection": ["反思", "总结", "学到", "经验", "教训", "下次", "改进", "回顾", "体会", "收获"],
}

# ------------------------------------------------------------------ #
# 通用行为题降级池（3道）
# ------------------------------------------------------------------ #
GENERIC_QUESTIONS = [
    {
        "question": "请描述一个你主导的项目：你负责什么，采取了什么行动，结果如何？",
        "targets": ["project_leadership"],
    },
    {
        "question": "请举一个你与团队协作中遇到冲突的例子，你是如何解决的？",
        "targets": ["collaboration_conflict"],
    },
    {
        "question": "请讲一个你需要快速学习新技术或新知识来完成任务的场景。",
        "targets": ["learning_adaptation"],
    },
]

# ------------------------------------------------------------------ #
# 岗位题库模板（按 job_profile 的 requirements 生成）
# ------------------------------------------------------------------ #
QUESTION_TEMPLATES = {
    "achievement_evidence": "你在简历中提到了与「{gap}」相关的经历，能具体讲讲你在其中做了什么、取得了什么结果吗？",
    "collaboration_conflict": "在涉及「{gap}」的工作中，你是否遇到过与同事意见不一致的情况？你是怎么处理的？",
    "learning_adaptation": "如果让你快速上手「{gap}」相关的任务，你会怎么规划学习路径？",
    "job_depth": "请深入解释一下你对「{gap}」的理解，包括实际应用中需要注意的细节。",
    "scenario_pressure": "假设项目即将上线，但「{gap}」环节出了问题，你会怎么应对？",
}

QUESTION_TYPES = [
    "achievement_evidence", "collaboration_conflict",
    "learning_adaptation", "job_depth", "scenario_pressure",
]

MAX_MAIN_QUESTIONS = 5
MAX_FOLLOWUPS_PER_QUESTION = 1

# ASR 置信度低于该阈值时先要求用户确认转写，不得推进面试状态机
ASR_MIN_CONFIDENCE = 0.75


class InterviewEngine:
    """文字自适应面试引擎。

    面试流程:
        start() -> next_question() -> submit_answer() ->
        [submit_followup_answer() if follow_up] -> next_question() -> ... ->
        end_session()
    """

    def __init__(self, model_router=None):
        """初始化面试引擎。

        Args:
            model_router: ModelRouter 实例，用于动态生成问题和评估回答。
                          为 None 时所有生成走降级路径。
        """
        self.router = model_router
        # 预编译敏感词正则
        self._sensitive_re = [re.compile(p) for p in SENSITIVE_PATTERNS]
        # 预编译危险模型输出正则（大小写不敏感以覆盖 API key / token 等英文写法）
        self._unsafe_re = [
            re.compile(p, re.IGNORECASE) for p in UNSAFE_QUESTION_PATTERNS
        ]

    # ================================================================ #
    # 公开接口
    # ================================================================ #

    def start(self, job_profile, resume_profile, match_gaps):
        """初始化面试会话。

        Args:
            job_profile: JobProfile JSON dict
            resume_profile: ResumeProfile JSON dict
            match_gaps: F2 缺口列表，每项形如
                        {"id": "L1", "type": "hard", "text": "...", "status": "missing"|"weak"}

        Returns:
            session dict:
                {state, job_profile, resume_profile, match_gaps,
                 turns, current_main, current_followup_count, question_type_index}
        """
        # 从 match_gaps 中提取 weakness/missing 项作为问题来源
        gaps = []
        for g in (match_gaps or []):
            status = g.get("status", "")
            if status in ("missing", "weak"):
                gaps.append({
                    "id": g.get("id", ""),
                    "type": g.get("type", ""),
                    "text": g.get("text", ""),
                    "status": status,
                })

        # 如果缺口不足 5 个，从 job_profile requirements 补充
        if len(gaps) < MAX_MAIN_QUESTIONS:
            reqs = (job_profile or {}).get("requirements", [])
            existing_ids = {g["id"] for g in gaps}
            for req in reqs:
                if len(gaps) >= MAX_MAIN_QUESTIONS:
                    break
                rid = req.get("id", "")
                if rid and rid not in existing_ids:
                    gaps.append({
                        "id": rid,
                        "type": req.get("type", ""),
                        "text": req.get("text", ""),
                        "status": "weak",
                    })

        session = {
            "state": "SETUP",
            "job_profile": job_profile or {},
            "resume_profile": resume_profile or {},
            "match_gaps": gaps,
            "turns": [],
            "current_main": 0,
            "current_followup_count": 0,
            "question_type_index": 0,
            "used_gaps": [],
            "degraded": False,
            "unsafe_blocked": False,
            "router_error": None,
        }
        session["state"] = "ASK"
        return session

    def next_question(self, session):
        """生成下一个问题。

        Returns:
            dict: {question, targets, turn_id}
            如果动态生成失败，降级到岗位题库再降级到通用行为题。
        """
        # 检查是否已完成所有主问题
        if session["current_main"] >= MAX_MAIN_QUESTIONS:
            return {"question": None, "targets": [], "turn_id": -1,
                    "done": True}

        turn_id = len(session["turns"]) + 1
        gap = self._pick_gap(session)
        recent_turns = self._recent_turn_context(session)
        answer_anchor = self._latest_answer_anchor(session)
        is_adaptive = bool(recent_turns)

        # 尝试动态生成
        question_text = None
        targets = []

        if self.router and gap:
            try:
                result = self.router.call(
                    "interview_question",
                    self._build_question_input(session, gap),
                    # context 只保留有界标量。结构化、已截断且已脱敏的内容
                    # 全部位于 user_input JSON 中；这里绝不回传原始 gap 或
                    # 原始 recent_turns，避免未脱敏 PII 与超长输入外发。
                    context={
                        "turn_id": turn_id,
                        "adaptive": is_adaptive,
                        "must_reference_previous_answer": is_adaptive,
                    },
                )
                if result["status"] == "success" and result.get("output"):
                    output = result["output"]
                    if isinstance(output, dict):
                        raw_question = output.get("question", "")
                        if isinstance(raw_question, str):
                            question_text = self._compact_text(raw_question, 220)
                        raw_targets = output.get("targets", [])
                        if isinstance(raw_targets, list):
                            targets = [
                                self._compact_text(item, 80) for item in raw_targets
                                if isinstance(item, str) and item.strip()
                            ][:8]
            except Exception as exc:
                # Keep the safe question-bank fallback, but retain a non-sensitive
                # diagnostic marker instead of silently swallowing provider errors.
                session["router_error"] = type(exc).__name__

        # 安全闸门 A：模型输出必须通过危险内容检查（在拼接回答 anchor 之前）
        if question_text and self._check_unsafe_generated_question(question_text):
            question_text = None
            targets = []
            session["degraded"] = True
            session["unsafe_blocked"] = True

        if question_text and self._is_repeated_question(session, question_text):
            question_text = None
            targets = []

        if question_text and is_adaptive:
            question_text = self._ensure_adaptive_question(
                question_text, answer_anchor, gap
            )
            # 安全闸门 B：拼接 anchor 之后再次检查，防止 anchor 回显注入语句
            if question_text and self._check_unsafe_generated_question(question_text):
                question_text = None
                targets = []
                session["degraded"] = True
                session["unsafe_blocked"] = True

        # 降级: 首题使用岗位题库；后续题必须从上一轮回答继续深挖。
        if not question_text:
            if is_adaptive:
                question_text, targets = self._adaptive_fallback_question(
                    session, gap
                )
            else:
                question_text, targets = self._fallback_question_bank(session, gap)
            session["degraded"] = True

        # 敏感词检测 -> 替换
        if self._check_sensitive(question_text):
            if is_adaptive:
                question_text, targets = self._adaptive_fallback_question(
                    session, gap, omit_anchor=True
                )
            else:
                question_text, targets = self._fallback_generic_by_index(
                    session["current_main"]
                )
            session["degraded"] = True

        # 安全闸门 C：降级/替换后的题目也必须干净；否则使用硬编码安全题。
        if self._check_unsafe_generated_question(question_text):
            question_text, targets = self._hardcoded_safe_question(session)
            session["degraded"] = True
            session["unsafe_blocked"] = True

        if not targets:
            targets = [gap["id"]] if gap else ["generic"]

        # basis 必须是“已脱敏回答的逐字子串”，且必须真的出现在最终题目里。
        # 如果安全闸门把题目换成了不引用回答的兜底题，就不能再声称有 basis。
        basis = answer_anchor if is_adaptive else ""
        if basis and basis not in question_text:
            basis = ""

        # Persist the emitted question for turn recording and follow-up review.
        session["_current_question"] = question_text
        session["_current_targets"] = targets
        session["_current_question_basis"] = basis

        # 记录已用 gap
        if gap:
            session["used_gaps"].append(gap["id"])

        # 主问题计数与本轮上下文必须持久化：否则状态机永远不会到达
        # MAX_MAIN_QUESTIONS 上限，且后续回合无法回填 question/targets
        # （InterviewTurn 合同要求 question 非空）。
        session["current_main"] += 1
        session["_current_question"] = question_text
        session["_current_targets"] = targets
        session["current_followup_count"] = 0
        return {
            "question": question_text,
            "targets": targets,
            "turn_id": turn_id,
            "done": False,
            "adaptive": is_adaptive,
            "basis": basis or None,
        }

    def submit_answer(self, session, answer_text, asr_confidence=None):
        """提交回答，分析 STAR 缺口。

        Args:
            session: 面试会话 dict
            answer_text: 用户回答全文（去标识化后）
            asr_confidence: 语音模式 ASR 置信度，文字模式为 None

        Returns:
            dict: {turn_id, answer, answer_quote, missing_elements,
                   follow_up, subscores}
        """
        turn_id = len(session["turns"]) + 1
        answer = self._deidentify_answer(answer_text or "")

        # ASR 置信度检查
        if asr_confidence is not None and asr_confidence < ASR_MIN_CONFIDENCE:
            return {
                "turn_id": turn_id,
                "answer": answer,
                "answer_quote": "",
                "missing_elements": [],
                "follow_up": None,
                "subscores": None,
                "needs_confirmation": True,
                "asr_confidence": asr_confidence,
            }

        # STAR 缺口检测
        missing_elements = self._detect_star_gaps(answer)

        # 提取 answer_quote
        answer_quote = self._extract_quote(answer)

        # 评估子分数
        subscores = self._assess_subscores(answer, missing_elements)

        # 追问决策
        follow_up = None
        if (missing_elements
                and session["current_followup_count"] < MAX_FOLLOWUPS_PER_QUESTION):
            follow_up = self._generate_followup(answer, missing_elements)
        session["_current_followup"] = follow_up["question"] if follow_up else ""

        turn = {
            "turn_id": turn_id,
            "question": session.get("_current_question", ""),
            "targets": session.get("_current_targets", []),
            "answer": answer,
            "answer_quote": answer_quote,
            "missing_elements": missing_elements,
            "follow_up": follow_up,
            "asr_confidence": asr_confidence,
            "subscores": subscores,
        }
        session["turns"].append(turn)

        return {
            "turn_id": turn_id,
            "answer": answer,
            "answer_quote": answer_quote,
            "missing_elements": missing_elements,
            "follow_up": follow_up,
            "subscores": subscores,
        }

    def submit_followup_answer(self, session, answer_text, asr_confidence=None):
        """提交追问回答。

        追问回答也纳入 turn 序列，但不生成新的追问（每题最多 1 次追问）。
        低 ASR 置信度时与主回答一致：不消费追问、不记录 turn。
        """
        answer = self._deidentify_answer(answer_text or "")

        if asr_confidence is not None and asr_confidence < ASR_MIN_CONFIDENCE:
            return {
                "turn_id": len(session["turns"]) + 1,
                "answer": answer,
                "answer_quote": "",
                "missing_elements": [],
                "follow_up": None,
                "subscores": None,
                "needs_confirmation": True,
                "asr_confidence": asr_confidence,
            }

        turn_id = len(session["turns"]) + 1
        answer_quote = self._extract_quote(answer)
        missing_elements = self._detect_star_gaps(answer)

        # 追问回答的子分数: followup_adaptation 提升权重
        subscores = self._assess_subscores(answer, missing_elements, is_followup=True)

        turn = {
            "turn_id": turn_id,
            "question": session.get("_current_followup", ""),
            "targets": session.get("_current_targets", []),
            "answer": answer,
            "answer_quote": answer_quote,
            "missing_elements": missing_elements,
            "follow_up": None,
            "asr_confidence": None,
            "subscores": subscores,
        }
        session["turns"].append(turn)
        session["current_followup_count"] += 1
        # 追问已回答，清除待回答标记，下一轮输入视为新的主问题回答
        session["_current_followup"] = ""

        return {
            "turn_id": turn_id,
            "answer": answer,
            "answer_quote": answer_quote,
            "missing_elements": missing_elements,
            "follow_up": None,
            "subscores": subscores,
        }

    def end_session(self, session):
        """结束面试，生成报告。

        Returns:
            dict: {report, score_I, turns}
            report: Markdown 格式复盘报告
            score_I: 规则复算的面试分（调用 rescore.calc_I）
        """
        session["state"] = "COMPLETE"

        # 计算子分均值
        subscore_keys = [
            "structure", "relevance", "specificity",
            "followup_adaptation", "clarity",
        ]
        sums = {k: 0.0 for k in subscore_keys}
        counts = {k: 0 for k in subscore_keys}

        for turn in session["turns"]:
            sc = turn.get("subscores")
            if not sc:
                continue
            # answer_quote 必须是 answer 的子串，否则该轮作废
            aq = turn.get("answer_quote", "")
            ans = turn.get("answer", "")
            if not aq or aq not in ans:
                continue
            for k in subscore_keys:
                v = sc.get(k)
                if v is not None:
                    sums[k] += v
                    counts[k] += 1

        i_input = {}
        for k in subscore_keys:
            if counts[k] > 0:
                i_input[k] = round(sums[k] / counts[k], 2)
            else:
                i_input[k] = None

        # 调用 rescore.calc_I 规则复算
        score_I = self._calc_score_I(i_input)

        # 生成报告
        report = self._generate_report(session, score_I, i_input)

        session["state"] = "REPORT"
        return {
            "report": report,
            "score_I": score_I,
            "turns": session["turns"],
            "i_subscores": i_input,
        }

    # ================================================================ #
    # 内部方法
    # ================================================================ #

    def _pick_gap(self, session):
        """从 match_gaps 中选取尚未使用过的缺口。"""
        for gap in session["match_gaps"]:
            if gap["id"] not in session["used_gaps"]:
                return gap
        # 全部用完则循环复用
        if session["match_gaps"]:
            idx = session["current_main"] % len(session["match_gaps"])
            return session["match_gaps"][idx]
        return None

    @staticmethod
    def _compact_text(value, limit=240):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip("，,。；;：: ") + "…"

    @staticmethod
    def _limited(value, limit):
        """Hard character bound without the display ellipsis of _compact_text."""
        return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]

    def _safe_job_title(self, session, limit=120):
        """De-identify and bound the job title before it reaches the model."""
        job = session.get("job_profile") or {}
        raw = job.get("title", "") if isinstance(job, dict) else ""
        cleaned = self._deidentify_answer(str(raw or ""))
        return self._limited(cleaned, limit)

    def _safe_gap_payload(self, gap):
        """Bounded, de-identified projection of a single match gap."""
        gap = gap or {}
        return {
            "id": self._limited(gap.get("id", ""), 64),
            "type": self._limited(gap.get("type", ""), 32),
            "text": self._limited(
                self._deidentify_answer(str(gap.get("text", ""))), 160
            ),
            "status": self._limited(gap.get("status", ""), 16),
        }

    @staticmethod
    def _deidentify_answer(value):
        text = str(value or "")
        try:
            from tools.deidentify import deidentify
        except ImportError:
            from deidentify import deidentify
        cleaned, _mapping = deidentify(text)
        return cleaned

    @staticmethod
    def _question_core(value):
        text = re.sub(r"\s+", "", str(value or ""))
        text = re.sub(r"^你刚才提到「.*?」。", "", text)
        text = re.sub(r"^结合你上一轮的回答，", "", text)
        text = re.sub(r"^围绕岗位要求「.*?」，", "", text)
        text = re.sub(r"^沿着这一经历，", "", text)
        return re.sub(r"[，。！？；：,.!?;:]", "", text)

    def _is_repeated_question(self, session, candidate):
        core = self._question_core(candidate)
        if not core:
            return True
        previous = {
            self._question_core(turn.get("question", ""))
            for turn in session.get("turns", [])
        }
        for prior in previous:
            if not prior:
                continue
            if core == prior:
                return True
            # Exact comparison misses cosmetic rewrites such as adding
            # "具体" or changing punctuation.  Treat highly similar long
            # questions as repeats so the fallback can choose another angle.
            if min(len(core), len(prior)) >= 12:
                if SequenceMatcher(None, core, prior).ratio() >= 0.88:
                    return True
        return False

    def _safe_answer_anchor(self, answer, preferred_quote=""):
        """Return a short verbatim, non-sensitive anchor from one answer."""
        raw = str(answer or "")
        answer = self._compact_text(raw, 500)
        if not answer:
            return ""
        quote = self._compact_text(preferred_quote, 80)
        if not quote or quote not in answer:
            quote = self._compact_text(self._extract_quote(answer), 80)
        quote = quote.strip("“”\"'「」《》 ")
        # 危险 anchor（用户回答里自带注入语句）同样不得回显为题目
        if self._check_sensitive(quote) or self._check_unsafe_generated_question(quote):
            return ""
        if len(quote) > 42:
            # Keep the anchor a literal substring of the stored answer.  An
            # appended ellipsis would turn a display abbreviation into fake
            # verbatim evidence and break the answer-quote invariant.
            quote = quote[:42].rstrip("，,。；;：: ")
        # 最终不变量：anchor 必须是原始回答的逐字子串
        if not quote or quote not in raw:
            return ""
        return quote

    def _latest_answer_anchor(self, session):
        for turn in reversed(session.get("turns", [])):
            anchor = self._safe_answer_anchor(
                turn.get("answer", ""), turn.get("answer_quote", "")
            )
            if anchor:
                return anchor
        return ""

    def _recent_turn_context(self, session, limit=4):
        """Build bounded, structured history for adaptive question generation."""
        history = []
        for turn in session.get("turns", [])[-limit:]:
            # Re-sanitize persisted history as well.  This covers sessions
            # created before answer-time de-identification was introduced.
            answer = self._compact_text(
                self._deidentify_answer(turn.get("answer", "")), 220
            )
            if not answer:
                continue
            history.append({
                "question": self._compact_text(turn.get("question", ""), 160),
                "answer": answer,
                "answer_quote": self._safe_answer_anchor(
                    answer, turn.get("answer_quote", "")
                ),
                "missing_elements": list(turn.get("missing_elements") or [])[:6],
                "targets": list(turn.get("targets") or [])[:6],
            })
        return history

    def _ensure_adaptive_question(self, question, anchor, gap=None):
        """Make the dependency on the previous answer explicit and testable."""
        question = self._compact_text(question, 220)
        if anchor and anchor in question:
            return question
        if anchor:
            prefix = "你刚才提到「%s」。" % anchor
        else:
            prefix = "结合你上一轮的回答，"
        if gap and gap.get("text"):
            gap_text = self._deidentify_answer(str(gap["text"]))
            if (
                self._check_unsafe_generated_question(gap_text)
                or self._check_sensitive(gap_text)
            ):
                bridge = "沿着这一经历，"
            else:
                bridge = "围绕岗位要求「%s」，" % self._limited(gap_text, 48)
        else:
            bridge = "沿着这一经历，"
        return self._compact_text(prefix + bridge + question, 280)

    def _adaptive_fallback_question(self, session, gap=None, omit_anchor=False):
        """Generate a deterministic next question from the latest answer."""
        latest = next(
            (turn for turn in reversed(session.get("turns", [])) if turn.get("answer")),
            {},
        )
        anchor = "" if omit_anchor else self._safe_answer_anchor(
            latest.get("answer", ""), latest.get("answer_quote", "")
        )
        prefix = (
            "你刚才提到「%s」。" % anchor
            if anchor else "结合你上一轮的回答，"
        )
        missing = list(latest.get("missing_elements") or [])
        safe_gap = gap
        if gap and (
            self._check_sensitive(str(gap.get("text", "")))
            or self._check_unsafe_generated_question(str(gap.get("text", "")))
        ):
            safe_gap = None
        focus_templates = {
            "action": "其中由你亲自完成的关键动作是什么，为什么选择这种做法？",
            "result": "这项工作的最终结果是什么，它怎样影响了项目或团队？",
            "metric": "这个结果用什么基准和数据验证，数据由谁、以什么方式统计？",
            "situation": "当时最关键的业务背景和约束条件是什么？",
            "task": "你本人承担的目标、边界和决策责任分别是什么？",
            "reflection": "如果重新做一次，你会调整哪个决策，为什么？",
        }
        for key in ("action", "result", "metric", "situation", "task", "reflection"):
            if key in missing:
                candidate = prefix + focus_templates[key]
                if not self._is_repeated_question(session, candidate):
                    return candidate, list(
                        latest.get("targets") or ["previous_answer"]
                    )

        if safe_gap and safe_gap.get("text"):
            question = (
                "目标岗位还要求「%s」。请说明这段经历与该要求的联系，"
                "以及你会如何迁移或深化原有做法？"
            ) % self._compact_text(safe_gap["text"], 48)
            candidate = prefix + question
            if not self._is_repeated_question(session, candidate):
                targets = [
                    safe_gap.get("id")
                    or safe_gap.get("type")
                    or "previous_answer"
                ]
                return candidate, targets

        targets = list(latest.get("targets") or ["previous_answer"])
        depth_questions = [
            "当时最关键的取舍是什么，还有哪些替代方案，为什么没有选择它们？",
            "如果将当时的业务规模扩大十倍，原方案会先在哪里失效，你会如何验证和调整？",
            "这段经历中哪一项证据最能证明你的个人贡献，如果被质疑，你会怎样交叉验证？",
        ]
        for question in depth_questions:
            candidate = prefix + question
            if not self._is_repeated_question(session, candidate):
                return candidate, targets
        # The five-question cap makes exhausting all strategies unlikely.  If
        # it happens, rotate deterministically while retaining the answer
        # anchor instead of falling back to an unrelated generic question.
        question = depth_questions[session.get("current_main", 0) % len(depth_questions)]
        return prefix + question, targets

    def _build_question_input(self, session, gap):
        """构建传给模型的问题生成输入。

        所有自由文本都经过脱敏与长度硬截断后再序列化，且包含重复的
        recent_turns 只以受限结构化形式出现一次。
        """
        qtype = QUESTION_TYPES[
            session["question_type_index"] % len(QUESTION_TYPES)
        ]
        session["question_type_index"] += 1
        payload = {
            "task": "generate_next_interview_question",
            "job_title": self._safe_job_title(session),
            "target_gap": self._safe_gap_payload(gap),
            "question_type": qtype,
            "main_question_number": session.get("current_main", 0) + 1,
            "recent_turns": self._recent_turn_context(session),
            "must_reference_previous_answer": bool(session.get("turns")),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _detect_star_gaps(self, answer_text):
        """检测 STAR 缺口（关键词启发式）。

        Returns:
            list[str]: 缺失的维度名，取值自
            ["situation", "task", "action", "result", "metric", "reflection"]
        """
        if not answer_text or len(answer_text.strip()) < 10:
            return ["situation", "task", "action", "result", "metric", "reflection"]

        text = answer_text
        missing = []
        for element, keywords in STAR_KEYWORDS.items():
            found = False
            for kw in keywords:
                if "." in kw or "\\" in kw:
                    # 含正则元字符的模式
                    if re.search(kw, text):
                        found = True
                        break
                else:
                    if kw in text:
                        found = True
                        break
            if not found:
                missing.append(element)
        return missing

    def _check_sensitive(self, question_text):
        """敏感词检测：命中任意一条返回 True。"""
        if not question_text:
            return False
        for pat in self._sensitive_re:
            if pat.search(question_text):
                return True
        return False

    def _check_unsafe_generated_question(self, text):
        """危险内容检测：提示注入 / 凭据索取 / PII 索取。

        与 :meth:`_check_sensitive` 是两个不同含义的闸门。凡是进入面试
        链路的文本（模型输出、岗位标题、gap、回答 anchor）都必须先过这里，
        命中即拒绝，fail closed。
        """
        if not text:
            return False
        text = str(text)
        for pat in self._unsafe_re:
            if pat.search(text):
                return True
        return False

    def _hardcoded_safe_question(self, session):
        """最终兜底：不依赖任何外部输入的安全题。"""
        title = self._safe_job_title(session, limit=40)
        if (
            title
            and not self._check_unsafe_generated_question(title)
            and not self._check_sensitive(title)
        ):
            question = (
                "围绕「%s」这一岗位，请挑一段你最有代表性的相关经历，"
                "说明当时的背景、你本人采取的行动，以及可以验证的结果。"
            ) % title
            return question, ["job_fit_evidence"]
        entry = GENERIC_QUESTIONS[0]
        return entry["question"], list(entry["targets"])

    def _extract_quote(self, answer_text):
        """从回答中提取最相关的句子作为 answer_quote。

        优先取含数字的句子（metric 证据），否则取最长句子。
        """
        if not answer_text:
            return ""
        # 按中文句号/分号/换行切分
        sentences = re.split(r"[。；;！？!?\n]", answer_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) >= 4]
        if not sentences:
            return answer_text.strip()[:50]

        # 优先: 含数字的句子
        with_numbers = [s for s in sentences if re.search(r"\d", s)]
        if with_numbers:
            return max(with_numbers, key=len)

        # 其次: 最长句子
        return max(sentences, key=len)

    def _assess_subscores(self, answer, missing_elements, is_followup=False):
        """启发式评估五维子分数（0-100）。

        当 model_router 可用时应由模型评估；此处为降级规则评估。
        """
        length = len(answer)
        has_numbers = bool(re.search(r"\d", answer))
        missing_count = len(missing_elements)

        # structure: STAR 覆盖越多越高
        structure = max(10, 100 - missing_count * 15)

        # relevance: 长度 + 是否含数字
        relevance = min(80, length // 3) + (10 if has_numbers else 0)
        relevance = min(100, relevance)

        # specificity: 含数字且长度够
        specificity = min(60, length // 5) + (25 if has_numbers else 5)
        specificity = min(100, specificity)

        # followup_adaptation: 追问回答给基础分
        followup_adaptation = 60 if is_followup else 50

        # clarity: 长度适中（不过短不过长）
        if length < 20:
            clarity = 30
        elif length > 500:
            clarity = 65
        else:
            clarity = 75

        return {
            "structure": structure,
            "relevance": relevance,
            "specificity": specificity,
            "followup_adaptation": followup_adaptation,
            "clarity": clarity,
        }

    def _generate_followup(self, answer_text, missing_elements):
        """基于回答缺失维度生成追问。

        Returns:
            dict: {"question": str, "reason": str} 或 None
        """
        if not missing_elements:
            return None

        # 按优先级生成追问
        followup_map = {
            "action": "你本人在这个过程中具体做了什么？用了什么工具或方法？",
            "result": "结果如何？有没有可量化的指标或数据？",
            "metric": "能否给出具体的数据或数字来说明效果？",
            "situation": "能描述一下当时的具体场景和背景吗？",
            "task": "你当时的具体任务或目标是什么？",
            "reflection": "回过头看，你从这次经历中学到了什么？",
        }

        for elem in missing_elements:
            if elem in followup_map:
                anchor = self._safe_answer_anchor(answer_text)
                prefix = (
                    "你刚才提到「%s」。" % anchor
                    if anchor else "结合你刚才的回答，"
                )
                return {
                    "question": prefix + followup_map[elem],
                    "reason": (
                        "missing_%s: anchored_to_previous_answer; answer lacks %s element"
                        % (elem, elem)
                    ),
                }

        return None

    def _fallback_question_bank(self, session, gap=None):
        """降级: 基于 gap 类型/状态生成规则化面试问题。

        当无 model_router 时，根据 gap 的 status（missing/covered/weak）
        和 type（hard/responsibility/preferred/terminology）选择追问策略，
        使问题比单一模板更精准。
        """
        if not gap:
            return self._fallback_generic_by_index(session["current_main"])

        status = gap.get("status", "missing")
        gtype = gap.get("type", "generic")
        gtext = gap.get("text", "该要求")
        gid = gap.get("id", "unknown")

        # status × type 二维模板表
        templates = {
            "missing": {
                "hard": "你在简历中未提及「{gap}」，能否分享你在该领域的实际经验或学习经历？",
                "responsibility": "简历中没有看到「{gap}」相关的职责描述，能否举一个你承担过类似工作的例子？",
                "preferred": "这是一个加分项——「{gap}」。如果你有相关经验，请举一个具体例子；如果没有，请说明你的学习计划。",
                "terminology": "能否解释一下你对「{gap}」的理解，以及在实际项目中如何应用？",
                "generic": "能否补充说明一下你在「{gap}」方面的经验和能力？",
            },
            "weak": {
                "hard": "你在简历中提到了「{gap}」，但证据不够充分。能否补充更多细节或量化结果？",
                "responsibility": "关于「{gap}」的职责描述比较简单，能否展开说明你具体做了什么、用了什么方法？",
                "preferred": "「{gap}」在简历中有提及但不够深入。能否举一个更能体现深度的例子？",
                "terminology": "能否用更具体的场景说明你对「{gap}」的理解和应用？",
                "generic": "能否更详细地说明你在「{gap}」方面的具体做法和成果？",
            },
            "covered": {
                "hard": "你在简历中展示了「{gap}」的能力。能否举一个最具代表性的例子，说明你在其中的关键贡献？",
                "responsibility": "关于「{gap}」的职责，能否深入讲一个最能体现你解决问题能力的具体事例？",
                "preferred": "「{gap}」是你简历中的亮点。能否分享一个更复杂的应用场景？",
                "terminology": "能否深入解释一下「{gap}」在大型项目中的最佳实践和踩坑经验？",
                "generic": "能否深入讲讲你在「{gap}」方面最自豪的一个成果？",
            },
            "unknown": {
                "hard": "简历中关于「{gap}」的信息不够明确。能否确认一下你是否有相关经验？",
                "responsibility": "「{gap}」相关的职责在简历中不够清晰，能否补充说明？",
                "preferred": "简历中未明确「{gap}」相关经验。如有，请举一个例子。",
                "terminology": "能否简单说明你对「{gap}」的熟悉程度？",
                "generic": "能否补充关于「{gap}」的更多信息？",
            },
        }

        type_map = templates.get(status, templates["missing"])
        template = type_map.get(gtype, type_map["generic"])
        question = template.format(gap=gtext)
        targets = [gid] if gid != "unknown" else [gtype or "generic"]
        return question, targets

    def _fallback_generic_by_index(self, index):
        """降级: 从通用行为题池中取第 index 题（循环）。"""
        idx = index % len(GENERIC_QUESTIONS)
        q = GENERIC_QUESTIONS[idx]
        return q["question"], q["targets"]

    def _fallback_generic(self):
        """降级: 3道通用行为题（返回第一道）。"""
        q = GENERIC_QUESTIONS[0]
        return q["question"], q["targets"]

    def _calc_score_I(self, i_input):
        """调用 rescore.calc_I 规则复算面试分。

        Args:
            i_input: dict with keys structure/relevance/specificity/
                     followup_adaptation/clarity, values 0-100 or None

        Returns:
            float: I 分（0-100），或 None（证据不足）
        """
        try:
            from tools.rescore import calc_I
        except ImportError:
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from rescore import calc_I
            except ImportError:
                # 最终降级: 本地加权计算
                return self._calc_I_local(i_input)

        try:
            return round(calc_I(i_input), 2)
        except (ValueError, KeyError):
            return None

    def _calc_I_local(self, i_input):
        """本地 I 分计算（rescore 不可用时的降级）。"""
        weights = {
            "structure": 0.25, "relevance": 0.25,
            "specificity": 0.20, "followup_adaptation": 0.15,
            "clarity": 0.15,
        }
        wsum, acc = 0.0, 0.0
        for k, w in weights.items():
            v = i_input.get(k)
            if v is None:
                continue
            wsum += w
            acc += v * w
        if wsum == 0:
            return None
        return round(acc / wsum, 2)

    def _generate_report(self, session, score_I, i_subscores):
        """生成 Markdown 复盘报告。"""
        turns = session["turns"]
        lines = ["# Interview Review Report", ""]

        # 总体表现
        lines.append("## 1. Overall Performance")
        if score_I is not None:
            lines.append("- **I score**: %.2f" % score_I)
        else:
            lines.append("- **I score**: insufficient evidence")
        for k, v in i_subscores.items():
            val = "%.2f" % v if v is not None else "N/A"
            lines.append("  - %s: %s" % (k, val))
        if session.get("degraded"):
            lines.append("\n> Note: interview ran in degraded mode (question bank fallback).")
        if session.get("router_error"):
            lines.append("> Model-router error category: %s" % session["router_error"])
        lines.append("")

        # 逐轮复盘
        lines.append("## 2. Per-Turn Review")
        for t in turns:
            lines.append("### Turn %d" % t["turn_id"])
            lines.append("- **Question**: %s" % t.get("question", "N/A"))
            lines.append("- **Targets**: %s" % ", ".join(t.get("targets", [])))
            aq = t.get("answer_quote", "")
            if aq:
                lines.append('- **Answer quote**: "%s"' % aq)
            me = t.get("missing_elements", [])
            if me:
                lines.append("- **Missing elements**: %s" % ", ".join(me))
            fu = t.get("follow_up")
            if fu:
                lines.append("- **Follow-up**: %s (reason: %s)" % (fu["question"], fu["reason"]))
            sc = t.get("subscores")
            if sc:
                sc_str = ", ".join("%s=%d" % (k, v) for k, v in sc.items())
                lines.append("- **Subscores**: %s" % sc_str)
            lines.append("")

        # 高频问题预备
        lines.append("## 3. High-Frequency Question Prep")
        all_missing = []
        for t in turns:
            all_missing.extend(t.get("missing_elements", []))
        from collections import Counter
        freq = Counter(all_missing).most_common(3)
        for elem, cnt in freq:
            lines.append("- Strengthen **%s** (missing in %d turns)" % (elem, cnt))
        lines.append("")

        # 与七天计划衔接
        lines.append("## 4. Seven-Day Plan Linkage")
        lines.append("- Review gaps above and incorporate into seven-day improvement plan.")
        lines.append("- Focus on areas with highest missing frequency.")
        lines.append("")

        # 中文结论：优点 / 不足 / 下一步安排
        star_labels = {
            "situation": "情境交代", "task": "任务职责", "action": "行动过程",
            "result": "结果呈现", "metric": "量化数据", "reflection": "复盘反思",
        }
        dim_labels = {
            "structure": "结构完整度", "relevance": "内容相关性",
            "specificity": "具体程度", "followup_adaptation": "追问适应度",
            "clarity": "表达清晰度",
        }
        covered_counter = Counter()
        missing_counter = Counter()
        for t in turns:
            me = set(t.get("missing_elements") or [])
            covered_counter.update(set(star_labels) - me)
            missing_counter.update(me)
        n_turns = max(1, len([t for t in turns if t.get("answer")]))
        strengths = [star_labels[e] for e, c in covered_counter.items() if c / n_turns >= 0.5]
        weaknesses = [star_labels[e] for e, c in missing_counter.items() if c / n_turns >= 0.3]
        strong_dims = [k for k, v in i_subscores.items() if v is not None and v >= 65]
        weak_dims = [k for k, v in i_subscores.items() if v is not None and v < 60]

        step_templates = {
            "action": "用 STAR 重写 2 个代表项目，突出你本人的具体行动与分工。",
            "result": "为每段经历补充结果句（完成/上线/交付 + 影响）。",
            "metric": "为关键经历补充量化数据（百分比、耗时、规模等）。",
            "situation": "回答前先用 1-2 句交代项目背景与当时处境。",
            "task": "明确说出你的任务目标与职责边界。",
            "reflection": "为一次项目写复盘笔记，提炼经验与改进点。",
        }
        next_steps = []
        for e in weaknesses:
            if e in step_templates:
                next_steps.append(step_templates[e])
        next_steps.extend([
            "基于本报告的高频缺失项，用文字完成一轮 5 题模拟面试复测。",
            "将报告结论同步到 F4 七天提升计划并设置每日任务。",
        ])
        next_steps = next_steps[:5]

        lines.append("## 5. 优点总结（Strengths）")
        if strengths or strong_dims:
            for s in strengths:
                lines.append("- " + s)
            for d in strong_dims:
                lines.append("- 维度表现良好：" + dim_labels.get(d, d))
        else:
            lines.append("- 暂无显著优势项，建议按不足项逐项补齐。")
        lines.append("")
        lines.append("## 6. 不足总结（Weaknesses）")
        if weaknesses or weak_dims:
            for w in weaknesses:
                lines.append("- " + w)
            for d in weak_dims:
                lines.append("- 维度待提升：" + dim_labels.get(d, d))
        else:
            lines.append("- 无明显短板。")
        lines.append("")
        lines.append("## 7. 下一步安排（Next Steps）")
        for i, step in enumerate(next_steps, 1):
            lines.append("%d. %s" % (i, step))
        lines.append("")

        return "\n".join(lines)
