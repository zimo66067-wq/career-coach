# -*- coding: utf-8 -*-
"""career_evidence_service · 把诊断/匹配产出转成**候选证据**（D8 方案 A）

产品口径见 ``docs/product-scope.md`` §10.7：

    模型抽取 → 候选证据（pending） → 用户确认 → 可信事实（confirmed）

本模块是唯一把"模型产出"翻译成 ``CareerEvidence`` 的地方。它**只能**产出
``pending``：``domain.evidence.new_evidence`` 会对 resume / interview /
application_outcome 三个来源强制拒绝 ``confirmed``，这里是第二道保险 ——
本模块不暴露任何直接确认的入参。

## 实质内容过滤（关键）

不是每一段原文摘录都算职业事实。实测合成样本里，诊断的 ``structure`` 子项引文是
**「实习经历」**、``ats_readability`` 是**「技能清单」** —— 那是版块标题，把它写成
"我的职业事实"会直接污染唯一可信源。因此：

1. ``structure`` / ``ats_readability`` 两个子项**完全不产证据**（它们衡量文档形态）；
2. 其余子项再过一遍 ``is_substantive_claim()``（长度 / 标点 / 数字 / 版块名黑名单）；
3. 最后过 ``is_complete_span()`` —— 引文必须是原文中一个**完整**分句。
   规则降级路径给的是定长窗口（词中间截断、五个子项共用同一段），会被这一关挡掉。

JD 匹配命中的**整句**天然是完整陈述，是质量最高的候选来源。
"""
from domain.career_profile import new_profile
from domain.evidence import EvidenceType, new_evidence
from repositories import career_evidence as evidence_repo
from repositories import career_profile as profile_repo
from tools import database

SOURCE_RESUME = "resume"

#: 诊断子项 → 证据类别。
#: 刻意**不包含** structure / ats_readability：它们衡量的是文档组织与可读性，
#: 不是"我做过什么"，引文也多是版块标题。
SUBPSCORE_EVIDENCE_TYPE = {
    "clarity": EvidenceType.EXPERIENCE.value,
    "achievement_evidence": EvidenceType.ACHIEVEMENT.value,
    "skill_evidence": EvidenceType.SKILL.value,
}

#: 版块标题黑名单（兜底；主要靠上面的子项白名单）。
SECTION_HEADINGS = frozenset({
    "个人信息", "基本信息", "求职意向", "教育背景", "教育经历", "实习经历", "工作经历",
    "项目经历", "项目经验", "校园经历", "实践经历", "技能清单", "专业技能", "技能特长",
    "获奖情况", "荣誉奖项", "自我评价", "个人评价", "证书", "语言能力", "兴趣爱好",
    "作品集", "科研经历", "培训经历",
})

#: 判定"像一句陈述"的标点/字形特征。
CLAUSE_MARKERS = "，,；;：:、。！？"

MIN_SUBSTANTIVE_CHARS = 10
LONG_CLAIM_CHARS = 18

#: 一条"片段"不该长过这个长度。超过它通常意味着上游给的不是 span 而是整段文本。
MAX_QUOTE_CHARS = 300

MAX_CANDIDATES_PER_SOURCE = 40

#: 允许出现在片段末尾的边界字符 —— 片段必须是**完整的**分句。
END_BOUNDARY = "\n\r \t，,。；;：:！？!?、）)】」』\"'“”"


def _compact(value):
    return " ".join(str(value or "").split())


def _raw_quote(value):
    """保留内部空白，只去掉首尾 —— 引文必须能逐字回到原文。"""
    return str(value or "").strip()


def is_complete_span(source_text, quote):
    """判断 ``quote`` 是否是 ``source_text`` 中一个**完整**的片段。

    只做"是不是子串"是不够的。规则降级路径（``build_rule_based_resume_profile``）
    对每个子项都用同一段 **160 字定长窗口** 当引文，而窗口是在词中间被截断的
    （实测结尾是「…引入 Redis 缓存实」，下一个字是「现」）。这种片段：

    * 不是任何一句陈述，拿它当"成果证据"就是编造；
    * 五个子项共用同一段，等于给简历抬头贴上"技能/成果"标签。

    所以额外要求：引文在原文中的**下一个字符必须是边界**（换行、空白或句末标点）。
    """
    text = str(source_text or "")
    if not quote or quote not in text:
        return False
    end = text.find(quote) + len(quote)
    if end >= len(text):
        return True
    return text[end] in END_BOUNDARY


def is_substantive_claim(quote):
    """判断一段原文摘录是否像"职业事实陈述"而不是版块标题。

    - 太长 → 否（不是片段）
    - 太短 → 否
    - 命中版块名黑名单 → 否
    - 含分句标点（，；：、。）→ 是（例如「编写接口文档并推动联调，与前端约定统一的错误码规范」）
    - 含数字 → 是（量化成果）
    - 否则要求足够长
    """
    text = _compact(quote)
    if len(text) > MAX_QUOTE_CHARS:
        return False
    if len(text) < MIN_SUBSTANTIVE_CHARS:
        return False
    if text in SECTION_HEADINGS:
        return False
    if any(marker in text for marker in CLAUSE_MARKERS):
        return True
    if any(char.isdigit() for char in text):
        return True
    return len(text) >= LONG_CLAIM_CHARS


def candidates_from_diagnosis(owner_key, session_id, resume_profile, resume_text):
    """诊断画像 → 候选证据列表（全部 pending，不含未落库记录）。

    ``resume_text`` 必须是**脱敏后**的简历正文（与诊断输入同源），引文对它做逐字校验。

    注意：规则降级路径（无模型时）的引文是定长窗口、在词中间截断，会被
    ``is_complete_span`` 全部挡掉 —— 因此降级模式下**不会**产生候选证据。
    这是刻意的：与其把简历抬头包装成"成果证据"，不如让用户看到"没有可核验片段"。
    """
    candidates = []
    subscores = (resume_profile or {}).get("subscores") or {}
    for key, evidence_type in SUBPSCORE_EVIDENCE_TYPE.items():
        block = subscores.get(key) or {}
        for span in (block.get("source_spans") or [])[:MAX_CANDIDATES_PER_SOURCE]:
            quote = _raw_quote((span or {}).get("quote"))
            if not is_substantive_claim(quote):
                continue
            if not is_complete_span(resume_text, quote):
                # 引文对不上原文、或是被截断的窗口 → 不生成。
                # 宁可少一条，也不留不可核验的证据。
                continue
            candidates.append({
                "evidence_type": evidence_type,
                "claim": quote,
                "source_type": SOURCE_RESUME,
                "source_id": str(session_id),
                "source_quote": quote,
                "confidence": 0.6,
                "origin": key,
            })
    return candidates


def candidates_from_requirements(owner_key, session_id, requirements, resume_text):
    """JD 匹配命中（covered / weak）的整句 → 候选证据。

    这些是完整陈述句，是质量最高的候选来源，所以 confidence 也略高。
    """
    candidates = []
    for requirement in (requirements or [])[:MAX_CANDIDATES_PER_SOURCE]:
        status = (requirement or {}).get("status")
        if status not in ("covered", "weak"):
            continue
        quote = _raw_quote(requirement.get("evidence"))
        if not is_substantive_claim(quote):
            continue
        if not is_complete_span(resume_text, quote):
            continue
        candidates.append({
            "evidence_type": EvidenceType.EXPERIENCE.value,
            "claim": quote,
            "source_type": SOURCE_RESUME,
            "source_id": str(session_id),
            "source_quote": quote,
            "confidence": 0.7 if status == "covered" else 0.5,
            "origin": "requirement:%s" % requirement.get("id"),
        })
    return candidates


def ensure_profile(owner_key):
    """幂等建 CareerProfile；返回档案记录。"""
    return profile_repo.ensure_for_owner(new_profile(owner_key))


def persist_candidates(owner_key, candidates):
    """把候选证据落库，跳过已存在的同源同引文项。

    返回 ``(created_records, skipped_count)``。去重键是
    ``(owner_key, source_type, source_id, source_quote)``，因此重复上传同一份简历
    不会反复堆记录，也不会把用户已经否决过的条目重新塞回来。
    """
    created, skipped = [], 0
    for candidate in candidates:
        source_id = str(candidate["source_id"])
        if evidence_repo.exists_for_source(
            owner_key, candidate["source_type"], source_id, candidate["source_quote"]
        ):
            skipped += 1
            continue
        record = new_evidence(
            owner_key=owner_key,
            evidence_type=candidate["evidence_type"],
            claim=candidate["claim"],
            source_type=candidate["source_type"],
            source_id=source_id,
            source_quote=candidate["source_quote"],
            confidence=candidate.get("confidence", 0.5),
        )
        created.append(evidence_repo.create(record))
    return created, skipped


def collect_candidates(owner_key, session_id, resume_text,
                       resume_profile=None, requirements=None):
    """统一入口：可同时吃诊断画像与匹配结果，返回落库后的新记录。"""
    candidates = []
    if resume_profile:
        candidates += candidates_from_diagnosis(owner_key, session_id, resume_profile, resume_text)
    if requirements:
        candidates += candidates_from_requirements(owner_key, session_id, requirements, resume_text)
    # 同一次调用内按引文去重，避免同一句既是诊断片段又是匹配命中而写两条
    seen, unique = set(), []
    for item in candidates:
        key = (item["source_type"], str(item["source_id"]), item["source_quote"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    created, skipped = persist_candidates(owner_key, unique)
    return created, skipped, unique


# ------------------------------------------------------------------ #
# 读取 / 用户确认
# ------------------------------------------------------------------ #

def list_evidence(owner_key, status=None, evidence_type=None):
    return evidence_repo.list_for_owner(owner_key, status=status, evidence_type=evidence_type)


def usable_evidence(owner_key):
    """下游（改写 / 匹配 / 面试 / 求职信）唯一允许读取的入口：只返回已确认证据。"""
    return evidence_repo.list_for_owner(owner_key, status="confirmed")


def profile_payload(owner_key):
    """Career Profile 的展示载荷：分支统计 + 待确认清单 + 已确认清单。"""
    from domain.career_profile import summary

    records = list_evidence(owner_key)
    return {
        "profile": profile_repo.get_for_owner(owner_key),
        "summary": summary(records),
        "pending": [item for item in records if item.get("status") == "pending"],
        "confirmed": [item for item in records if item.get("status") == "confirmed"],
        "rejected": [item for item in records if item.get("status") == "rejected"],
        "notice": (
            "候选证据由模型从你的材料中抽取，尚未核实；请逐条确认或否决，"
            "只有你确认过的内容才会被用于改写、匹配与面试。"
        ),
    }


def _load_owned(owner_key, evidence_id):
    record = evidence_repo.get_for_owner(evidence_id, owner_key)
    if record is None:
        raise LookupError("evidence_not_found")
    return record


def confirm(owner_key, evidence_id):
    from domain.evidence import confirm as domain_confirm

    evidence_repo.save(domain_confirm(_load_owned(owner_key, evidence_id)))
    return evidence_repo.get_for_owner(evidence_id, owner_key)


def reject(owner_key, evidence_id):
    from domain.evidence import reject as domain_reject

    evidence_repo.save(domain_reject(_load_owned(owner_key, evidence_id)))
    return evidence_repo.get_for_owner(evidence_id, owner_key)


def edit(owner_key, evidence_id, claim=None, source_quote=None, confirmed_by_user=False):
    from domain.evidence import edit_claim

    record = _load_owned(owner_key, evidence_id)
    updated = edit_claim(
        record,
        claim if claim is not None else record["claim"],
        source_quote=source_quote,
        confirmed_by_user=confirmed_by_user,
    )
    evidence_repo.save(updated)
    return evidence_repo.get_for_owner(evidence_id, owner_key)


def delete(owner_key, evidence_id):
    _load_owned(owner_key, evidence_id)
    evidence_repo.delete(evidence_id, owner_key)
    return True


def counts(owner_key):
    return evidence_repo.counts(owner_key)
