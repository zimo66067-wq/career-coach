# -*- coding: utf-8 -*-
"""target_job_service · Target Job Analysis（唯一一套"岗位匹配"实现）

Phase 1 已经删掉了独立的「专业→职业匹配」，主产品只剩这一条血脉：
``services/match_service.py``（JD 四态判定 + BM25）负责"哪条要求被哪句话命中"，
本模块负责把它翻译成**领域记录 + 可解释决策**：

    TargetJob → JobRequirement → EvidenceMatch → Gap → Decision(APPLY/STRETCH/PASS)

## 三条硬规则

1. **决策只能由缺口推出。** 结论 = ``expected_decision(gaps)``，再交给
   ``domain.decide()`` 复核；两者不一致会抛错。也就是说判断无法被手写，
   也不存在"分数够了就给 APPLY"。
2. **每条依据都必须是可核对的事实。** 依据串由真实数据拼出（要求编号 + 判定结果、
   缺口编号 + 优先级、已确认证据条数），凑不满 3 条时**不产出决策**，
   返回 ``insufficient_grounds`` —— 宁可不判，也不编造依据。
3. **缺口保留用户进度。** 重新分析会整体替换匹配行（派生数据），但缺口只刷新文案、
   不动 ``status``，否则用户标记的 ``doing`` / ``done`` 会被抹掉。
"""
import json

from domain.target_job import (
    CLEARED_GAP_STATUS,
    Decision,
    expected_decision,
    gap_from_requirement,
    new_target_job,
    priority_for,
    requirement_from_profile_item,
)
from domain.target_job import decide as domain_decide
from repositories import target_job as repo
from tools import database

MATCH_ENGINE = "rule_bm25"

#: JD 里的版块标题 —— 它们不是"要求"，不能进 JobRequirement，更不能产生缺口。
#: 实测规则解析把「职位描述」原样当成了一条要求并判为 missing，于是一条不存在的
#: P0 缺口把结论推成 PASS —— 这种"可解释"是假的，必须挡在落库之前。
JD_HEADING_WORDS = frozenset({
    "职位描述", "岗位描述", "职位简介", "岗位简介", "工作描述",
    "岗位职责", "工作职责", "职位职责", "主要职责", "职责描述",
    "任职要求", "职位要求", "岗位要求", "任职资格", "资格要求", "岗位条件",
    "我们希望你", "我们希望", "你需要", "加分项", "优先条件", "福利待遇", "职位福利",
    "薪资范围", "薪资待遇", "工作地点", "联系方式", "公司介绍", "关于我们",
    "团队介绍", "招聘流程", "应聘方式", "其他信息", "备注",
    "常用技术栈", "技术栈", "技能要求", "必备技能", "加分条件", "我们提供",
})

#: 要求式动词/名词 —— 用来区分"一句要求"与"一个职位名"。
#: 刻意**不含** 开发/设计/维护 这类会出现在职位名里的词（「后端开发工程师」）。
STRONG_REQUIREMENT_SIGNALS = (
    "熟悉", "掌握", "了解", "具备", "负责", "参与", "能够", "要求", "优先",
    "至少", "及以上", "经验", "能力", "学历", "专业", "证书",
    "熟练", "精通", "倾向于", "加分", "有", "会",
)

MIN_REQUIREMENT_CHARS = 6
TITLE_LINE_MAX_CHARS = 80


def _norm(value):
    return " ".join(str(value or "").split())


def looks_like_title_line(text):
    """JD 首行在解析器没抓到 ``job_title`` 时，通常是「职位名 - 公司名」。

    判据：短、无句末标点、且不含任何"要求式"信号词。
    """
    body = _norm(text)
    if not body or len(body) > TITLE_LINE_MAX_CHARS:
        return False
    if any(punct in body for punct in "；;。！？"):
        return False
    return not any(signal in body for signal in STRONG_REQUIREMENT_SIGNALS)


def looks_like_requirement(text, is_first_line=False, profile_has_title=False):
    """判断一行 JD 文本是否真的是"岗位要求"。

    ``job_profile_json`` 里仍保留解析器的原始输出（可追溯），
    这里只决定**哪些能进 JobRequirement 表并参与决策**。

    策略是**保守**的：只挡掉三类明确不是要求的行（过短、版块标题、首行职位名），
    其余一律保留 —— 漏放一条真要求的代价，比误删一条要小。
    """
    body = _norm(text)
    if len(body) < MIN_REQUIREMENT_CHARS:
        return False
    if body.rstrip("：:。. ") in JD_HEADING_WORDS:
        return False
    if is_first_line and not profile_has_title and looks_like_title_line(body):
        return False
    return True

#: 每类要求的补强剧本：Gap → Reason → Missing Evidence → Action → Artifact → Retest
GAP_PLAYBOOK = {
    "hard": {
        "action": "补一条与该硬性要求直接对应的真实经历、资质或证明，并写清时间与角色。",
        "expected_artifact": "1 条可核验的硬性要求对应描述（含时间、角色、可查证事实）",
        "missing_evidence": "缺少能直接证明该硬性要求的经历或资质",
    },
    "responsibility": {
        "action": "把一项与该职责相关的经历改写成「动作 + 方法 + 结果」的陈述句。",
        "expected_artifact": "1 条 STAR 结构的职责描述",
        "missing_evidence": "缺少与该职责对应的具体做法描述",
    },
    "preferred": {
        "action": "在简历中补充与该加分项相关的实操说明（用过什么、做到什么程度）。",
        "expected_artifact": "1 条含加分项关键词的实操描述",
        "missing_evidence": "缺少与加分项相关的实操记录",
    },
    "terminology": {
        "action": "确认是否真的接触过该术语/工具；若接触过，用一句具体场景说明。",
        "expected_artifact": "1 条含该术语/工具的具体场景说明",
        "missing_evidence": "简历中未出现该术语或工具",
    },
    # 材料完全对不上：要补的是材料，不是能力
    "unverifiable": {
        "action": "确认是否真的具备该要求；若有相关经历，用一句具体描述补进材料。",
        "expected_artifact": "1 条与该要求直接相关的真实经历描述",
        "missing_evidence": "材料中找不到与该要求相关的任何内容，无法判定",
    },
}

RETEST_ACTION = "重新运行目标岗位分析，观察该缺口是否被覆盖。"

#: 结构性门槛：**靠改简历补不上**的两类要求。
#: 只有这两类才会把结论推成 PASS；其余缺口（哪怕是 missing）都算"可能只是没写"。
#:
#: 学历必须比**级别**而不是比关键词：「硕士研究生及以上学历」在一个本科简历上会被
#: BM25 判成 weak（因为简历里有"学历"两个字），若只看 gap_type 就会错判成可短期解决。
DEGREE_LEVELS = (
    ("博士", 4), ("硕士", 3), ("研究生", 3), ("本科", 2), ("学士", 2),
    ("专科", 1), ("大专", 1), ("高职", 1),
)

CERTIFICATE_MARKERS = (
    "证书", "资格证", "从业资格", "执业资格", "四六级", "CET", "雅思", "托福", "驾照",
)


def degree_level(text):
    """文本中出现的最高学历级别；0 表示没提到。"""
    body = _norm(text)
    best = 0
    for marker, level in DEGREE_LEVELS:
        if marker in body and level > best:
            best = level
    return best


def is_blocking_gap(gap_type, requirement_text, status, resume_text):
    """该缺口是否**不可短期解决**。

    只有两种情形算"不可短期解决"：

    1. 要求了高于现有学历的门槛（如 JD 要硕士、简历只有本科）；
    2. 要求了证书/资格，而简历里完全没有任何相关字样。

    其余（工具没写进简历、经历强度不够）都可以靠重写或不长的实战补强，
    所以一律不阻断 —— 把"没写"当成"没有"会误伤大量本可以投的岗位。

    服务层才拿得到要求原文与简历原文，所以判定在这里做，结果存进
    ``gaps.blocking``，使 APPLY/STRETCH/PASS 完全可以从库里的数据复现。
    """
    text = _norm(requirement_text)
    asked = degree_level(text)
    if asked and degree_level(resume_text) < asked:
        return True
    for marker in CERTIFICATE_MARKERS:
        if marker in text:
            return marker not in _norm(resume_text)
    return False


class TargetJobError(Exception):
    """带机器可读 code 的服务层错误（路由层翻译成 HTTP）。"""

    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ------------------------------------------------------------------ #
# 创建 / 读取
# ------------------------------------------------------------------ #

def create_target_job(owner_key, session_id, company=None, position=None, jd_text=None,
                      job_profile=None):
    """建一个目标岗位，并把 JD 拆出的要求落库。

    ``job_profile`` 可传入已解析（并经用户确认）的 JobProfile；不传则用
    ``match_service.build_job_profile`` 现场解析。
    """
    if not (jd_text or job_profile):
        raise TargetJobError("jd_required", "请提供岗位描述（JD）或已确认的岗位画像。")

    if job_profile is None:
        from services.match_service import build_job_profile

        job_profile = build_job_profile(jd_text)

    record = new_target_job(
        owner_key,
        session_id=session_id,
        company=company,
        position=position or job_profile.get("job_title"),
        jd_text=jd_text,
    )
    record["job_profile_json"] = json.dumps(job_profile, ensure_ascii=False)
    created = repo.create_target_job(record)

    # 只把"真的是要求"的行落成 JobRequirement；解析器的原始输出已在
    # job_profile_json 里完整保留，可追溯，不丢信息。
    has_title = bool(job_profile.get("job_title"))
    requirements, dropped, recovered_title = [], [], None
    for ordinal, item in enumerate(job_profile.get("requirements") or []):
        text = _norm(item.get("text"))
        if looks_like_requirement(text, is_first_line=(ordinal == 0),
                                  profile_has_title=has_title):
            requirements.append(
                requirement_from_profile_item(created["id"], item, ordinal=len(requirements))
            )
            continue
        dropped.append(text[:80])
        if ordinal == 0 and not has_title and recovered_title is None:
            recovered_title = text  # 首行本来就是职位名，顺手回收当岗位名

    if not requirements:
        repo.delete_target_job(created["id"], owner_key)
        raise TargetJobError(
            "no_requirements",
            "未能从该 JD 中识别出有效的岗位要求，请补充「任职要求 / 岗位职责」后再试。",
        )

    repo.replace_requirements(created["id"], requirements)

    if recovered_title and not position and not created.get("position"):
        repo.set_position(created["id"], owner_key, recovered_title[:120], database.utc_iso())

    result = get_target_job(created["id"], owner_key)
    result["dropped_non_requirements"] = dropped
    return result


def get_target_job(target_job_id, owner_key):
    record = repo.get_target_job_for_owner(target_job_id, owner_key)
    if record is None:
        raise TargetJobError("target_job_not_found", "目标岗位不存在。", 404)
    return record


def list_target_jobs(owner_key):
    return repo.list_target_jobs(owner_key)


def delete_target_job(target_job_id, owner_key):
    """删除目标岗位及其全部子记录（要求 / 匹配 / 缺口 / 决策）。

    用户删除一个目标岗位时，从它派生出来的个人数据必须一并消失，
    不能留下可以反推出岗位与要求的孤儿行。
    """
    get_target_job(target_job_id, owner_key)
    repo.delete_matches_for_target(target_job_id)
    repo.delete_gaps_for_target(target_job_id)
    repo.delete_requirements_for_target(target_job_id)
    repo.delete_decisions_for_target(target_job_id)
    return repo.delete_target_job(target_job_id, owner_key)


def requirements_of(target_job_id):
    return repo.list_requirements(target_job_id)


# ------------------------------------------------------------------ #
# 分析
# ------------------------------------------------------------------ #

def analyse(target_job_id, owner_key, resume_text):
    """跑完整分析并返回 ``{requirements, matches, gaps, decision, citations, ...}``。"""
    target = get_target_job(target_job_id, owner_key)
    requirements = repo.list_requirements(target_job_id)
    if not requirements:
        raise TargetJobError("no_requirements", "该目标岗位没有可分析的要求，请重新解析 JD。")

    profile = json.loads(target["job_profile_json"] or "{}")
    if not profile.get("requirements"):
        raise TargetJobError("no_job_profile", "该目标岗位缺少岗位画像，请重新解析 JD。")

    from services.match_service import match_job_profile

    match = match_job_profile(resume_text, profile)
    match_by_key = {item["id"]: item for item in match.get("requirements") or []}

    # 1) 命中的整句 → 候选证据（pending），拿到 requirement_id ↔ evidence_id 映射
    from services import career_evidence_service as evidence_service

    _created, _skipped, candidates = evidence_service.collect_candidates(
        owner_key,
        target.get("session_id") or "target-job-%s" % target_job_id,
        resume_text,
        requirements=[match_by_key.get(row["req_key"], {}) for row in requirements],
    )
    quote_to_id = {}
    for record in evidence_service.list_evidence(owner_key):
        # 已确认与待确认都可用于"这条要求有对应材料"的定位；
        # 是否算作可信事实由 decision 阶段的 usable evidence 决定。
        quote_to_id.setdefault(record["source_quote"], record["id"])

    # 2) 重建匹配行（派生数据，整体替换）
    repo.delete_matches_for_target(target_job_id)
    matches = []
    for row in requirements:
        item = match_by_key.get(row["req_key"]) or {}
        status = item.get("status") or "unknown"
        quote = " ".join(str(item.get("evidence") or "").split())
        from domain.target_job import new_evidence_match

        record = new_evidence_match(
            row["id"],
            quote_to_id.get(quote),
            status,
            rationale=("命中简历原文：%s" % quote[:120]) if quote else "简历中未找到对应材料",
        )
        matches.append(repo.add_evidence_match(record))

    # 3) 缺口：weak / missing 才生成；已覆盖的要求把旧缺口标记为 cleared
    now = database.utc_iso()
    gaps = []
    for row in requirements:
        item = match_by_key.get(row["req_key"]) or {}
        status = item.get("status") or "unknown"
        if status == "covered":
            # 已覆盖 → 之前因该要求产生的缺口都不再适用
            for gap_type in ("missing", "weak", "unverifiable"):
                existing = repo.find_gap(target_job_id, row["id"], gap_type)
                if existing and existing["status"] != CLEARED_GAP_STATUS:
                    repo.set_gap_status(existing["id"], CLEARED_GAP_STATUS, now)
            continue

        # unknown（材料完全对不上）也建缺口 —— 否则会输出"满足要求"的假象
        if status == "unknown":
            playbook = GAP_PLAYBOOK["unverifiable"]
        else:
            playbook = GAP_PLAYBOOK.get(row["req_type"], GAP_PLAYBOOK["terminology"])
        draft = gap_from_requirement(
            target_job_id,
            {"id": row["id"], "req_type": row["req_type"], "evidence": item.get("evidence")},
            status,
            missing_evidence=playbook["missing_evidence"],
            action=playbook["action"],
            expected_artifact=playbook["expected_artifact"],
            retest=RETEST_ACTION,
            blocking=is_blocking_gap(
                "missing" if status == "missing" else "weak", row["text"], status, resume_text
            ),
        )
        draft["updated_at"] = now
        gap_type = draft["gap_type"]
        existing = repo.find_gap(target_job_id, row["id"], gap_type)
        if existing:
            # 保留 status（用户进度），只刷新推导文案
            repo.update_gap_content(existing["id"], draft)
            gaps.append(repo.find_gap(target_job_id, row["id"], gap_type))
        else:
            gaps.append(repo.create_gap(draft))

    # 4) 决策：先把旧缺口一并纳入判定（cleared 不参与）
    all_gaps = repo.list_gaps(target_job_id)
    verdict = expected_decision(all_gaps)
    citations = _build_citations(requirements, match_by_key, all_gaps, owner_key)
    if len(citations) < 3:
        raise TargetJobError(
            "insufficient_grounds",
            "当前材料与岗位要求可核对的事实不足 3 条，无法给出可解释的判断。"
            "请补充更完整的 JD 或简历后再试。",
        )

    decision_record = repo.create_decision(
        domain_decide(target_job_id, verdict, citations, rationale=_rationale(verdict), gaps=all_gaps)
    )

    return {
        "target_job": get_target_job(target_job_id, owner_key),
        "requirements": _decorate_requirements(requirements, match_by_key),
        "matches": matches,
        "gaps": all_gaps,
        "decision": {
            **decision_record,
            "rationale": json.loads(decision_record["rationale_json"] or "{}"),
        },
        "citations": citations,
        "analysis": {
            "score_M": match.get("score_M"),
            "match_mode": match.get("match_mode", MATCH_ENGINE),
            "match_notice": match.get("match_notice"),
            "insufficient_evidence": match.get("insufficient_evidence", False),
            "new_candidate_evidence": len(_created),
            "skipped_existing_evidence": _skipped,
            "candidate_count": len(candidates),
        },
    }


def _decorate_requirements(requirements, match_by_key):
    decorated = []
    for row in requirements:
        item = match_by_key.get(row["req_key"]) or {}
        merged = dict(row)
        merged["status"] = item.get("status") or "unknown"
        merged["type_label"] = item.get("typeLabel")
        merged["evidence"] = item.get("evidence") or ""
        decorated.append(merged)
    return decorated


def _build_citations(requirements, match_by_key, gaps, owner_key):
    """依据串：只由真实数据拼出，每条都可以回查。

    刻意保持**至少 4 类**可核对事实（要求判定 / 匹配概览 / 缺口 / 证据盘点），
    否则一个只有 1 条要求的 JD 在"没有缺口"（= APPLY）时凑不满 3 条依据，
    就会被迫拒绝给出结论 —— 那其实是把"少要求的 JD"误判成"证据不足"。
    """
    from domain.target_job import open_gaps as domain_open_gaps

    citations = []
    for row in requirements:
        item = match_by_key.get(row["req_key"]) or {}
        status = item.get("status") or "unknown"
        citations.append("要求 %s「%s」判定为 %s" % (row["req_key"], row["text"][:40], status))

    tally = {"covered": 0, "weak": 0, "missing": 0, "unknown": 0}
    for row in requirements:
        item = match_by_key.get(row["req_key"]) or {}
        tally[item.get("status") or "unknown"] = tally.get(item.get("status") or "unknown", 0) + 1
    citations.append(
        "岗位共 %d 条要求：已覆盖 %d、弱命中 %d、缺失 %d、无法判定 %d"
        % (len(requirements), tally["covered"], tally["weak"], tally["missing"], tally["unknown"])
    )

    for gap in domain_open_gaps(gaps):
        citations.append(
            "缺口 %s（要求 #%s）优先级 %s，%s" % (
                gap["gap_type"], gap.get("requirement_id"), gap["priority"],
                "不可短期解决" if gap.get("blocking") else "可由已有材料重写或短期补强",
            )
        )

    from repositories import career_evidence as evidence_repo

    counts = evidence_repo.counts(owner_key)
    citations.append("已确认职业证据 %d 条，待确认 %d 条" % (counts["confirmed"], counts["pending"]))
    # 去重但保持顺序（domain.decide 要求依据互不重复）
    seen, unique = set(), []
    for item in citations:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _rationale(verdict):
    if verdict == Decision.PASS.value:
        return "存在不可短期解决的 P0 缺口（学历 / 专业 / 证书这类结构性门槛），建议先补齐再投。"
    if verdict == Decision.STRETCH.value:
        return ("关键要求已有材料但强度不足，或仍有 P1 缺口；"
                "可由已有经历重写、补量化或不长的时间内实战补强后再投。")
    return "关键要求均有已确认证据支撑，可以投递。"


def decision_of(target_job_id, owner_key):
    get_target_job(target_job_id, owner_key)
    record = repo.latest_decision(target_job_id)
    if record is None:
        return None
    payload = dict(record)
    payload["rationale"] = json.loads(record["rationale_json"] or "{}")
    return payload


# ------------------------------------------------------------------ #
# 面试出题（DoD #11：P0 Gap > P1 Gap > 关键证据验证 > 行为问题 > 通用题库）
# ------------------------------------------------------------------ #

#: 出题优先级排序键。P0 必须排在最前 —— 这是"按缺口定向出题"的全部含义。
GAP_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def interview_gaps(target_job_id, owner_key):
    """目标岗位的**未解决**缺口 → 给面试引擎的出题清单（已按 P0 → P1 → P2 排序）。

    引擎按传入顺序取题（``interview_engine._pick_gap``），所以排序就是优先级本身。
    已关闭 / 已清除的缺口不出题。

    **键名注意**：这里的 ``status`` 是 ``gap_type``（``missing`` / ``weak``），
    因为那是 ``interview_engine.start()`` 的既有契约；它与缺口生命周期状态同名不同义。
    """
    from domain.target_job import OPEN_GAP_STATUSES

    get_target_job(target_job_id, owner_key)
    requirements = {row["id"]: row for row in repo.list_requirements(target_job_id)}
    ordered = []
    for gap in repo.list_gaps(target_job_id):
        if gap.get("status") not in OPEN_GAP_STATUSES:
            continue
        requirement = requirements.get(gap.get("requirement_id")) or {}
        ordered.append({
            "id": "gap-%s" % gap["id"],
            "gapId": gap["id"],
            "type": requirement.get("req_type") or "hard",
            "text": requirement.get("text") or gap.get("reason") or "",
            "status": gap["gap_type"],
            "priority": gap["priority"],
        })
    ordered.sort(key=lambda item: (GAP_PRIORITY_ORDER.get(item["priority"], 9), item["gapId"]))
    return ordered


def question_plan(target_job_id, owner_key):
    """出题计划（含题型），用来证明优先级确实生效。

    **注意键名冲突**：``interview_gaps()`` 返回给引擎的 ``status`` 是
    ``gap_type``（``missing`` / ``weak``）—— 那是引擎的既有契约；而
    ``domain.interview.plan_question_order()`` 里的 ``status`` 指缺口生命周期
    （``open`` / ``doing``）。两者同名不同义，所以这里**从库里的原始缺口行**构造计划，
    绝不能把引擎形态的列表喂给它（否则会被当成"已关闭"全部过滤掉）。
    """
    from domain.interview import plan_question_order
    from domain.target_job import OPEN_GAP_STATUSES

    get_target_job(target_job_id, owner_key)
    open_rows = [
        gap for gap in repo.list_gaps(target_job_id)
        if gap.get("status") in OPEN_GAP_STATUSES
    ]
    return plan_question_order(open_rows)
