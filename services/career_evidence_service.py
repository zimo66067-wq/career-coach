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
import json
import logging

from domain.career_profile import new_profile
from domain.errors import DomainError
from domain.evidence import EvidenceType, new_evidence
from repositories import career_evidence as evidence_repo
from repositories import career_profile as profile_repo
from tools import database
from tools.deidentify import deidentify

logger = logging.getLogger(__name__)

SOURCE_RESUME = "resume"

#: 面试来源的候选证据由 ``domain.interview.candidate_evidence`` 打标，
#: 这里只用于文档与测试断言，不参与写入。
SOURCE_INTERVIEW = "interview"

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


#: 面试单轮最多保留的候选条数（模型可能不守 prompt 约束，服务层兜底限流）
MAX_CANDIDATES_PER_TURN = 2


def _interview_turns(turns):
    """筛选**有效轮次**，并把回答**脱敏**后作为事实来源。

    引擎在 ASR 置信度过低时不记录轮次（``subscores`` 为 ``None``、``answer_quote``
    为空）。这类轮次没有可靠原文，不能拿去生成证据。

    ``turn["answer"]`` 是用户**原始**输入 —— 引擎的 ``_deidentify_answer`` 只用于
    外发模型的入参，不写回 session。所以这里必须自己再脱敏一次，与简历路径保持一致：
    证据的唯一事实来源是脱敏后文本。含 PII 的引文脱敏后对不上原文，会被
    ``is_complete_span`` 丢弃 —— 这是期望行为，而不是 bug。
    """
    valid = []
    for index, turn in enumerate(turns or []):
        if not isinstance(turn, dict):
            continue
        raw = str(turn.get("answer") or "")
        if not raw or not turn.get("subscores"):
            continue
        answer = _compact(deidentify(raw)[0])
        if not answer:
            continue
        turn_id = turn.get("turn_id")
        valid.append({
            "turn_id": index + 1 if turn_id is None else turn_id,
            "answer": answer,
            # 引文与事实来源同口径（都过 _compact），否则内部空白差异会让校验失败
            "answer_quote": _compact(turn.get("answer_quote")),
        })
    return valid


def _interview_record(owner_key, session_id, turn, claim, quote, evidence_type):
    """经域层生成候选证据 —— 事实锁（quote 必须是 answer 的逐字子串）在这里生效。"""
    from domain import interview as interview_domain

    return interview_domain.candidate_evidence(
        {"session_id": str(session_id)},
        {"owner_key": owner_key},
        claim=claim,
        quote=quote,
        answer_text=turn["answer"],
        evidence_type=evidence_type,
        turn_id=turn["turn_id"],
    )


def candidates_from_interview(owner_key, session_id, turns, extracted=None):
    """面试有效轮次 → 候选证据记录（**全部 pending**）。

    ``extracted`` 是模型抽取结果 ``[{"claim","quote","evidence_type","turn_id"}]``。

    - 传 ``None``（模型不可用 / 降级 / 解析失败）→ **逐轮用 ``answer_quote`` 兜底**。
      它是引擎按「优先含数字的句子，否则最长句」算出的**完整句子**，属于用户原话，
      因此既不是编造，也能通过完整性校验（与简历规则路径的定长截断窗口不同）。
    - 模型可用 → **以模型的判断为准**：它说某轮没有事实就不补，避免把"我明白了"
      这类礼节性回答也塞进证据档案。引文对不上原文的条目直接丢弃。

    两条路径都由域层 ``candidate_evidence()`` 收口，因此不可能产出 confirmed。
    """
    turns_by_id = {}
    for turn in _interview_turns(turns):
        turns_by_id.setdefault(str(turn["turn_id"]), turn)

    records, dropped = [], 0

    if extracted is None:
        for turn in turns_by_id.values():
            quote = turn["answer_quote"]
            if not quote or not is_substantive_claim(quote):
                dropped += 1
                continue
            if not is_complete_span(turn["answer"], quote):
                dropped += 1
                continue
            try:
                records.append(_interview_record(
                    owner_key, session_id, turn, claim=quote, quote=quote,
                    evidence_type=None,
                ))
            except DomainError:
                dropped += 1
        return records, dropped

    per_turn = {}
    for item in extracted:
        if not isinstance(item, dict):
            dropped += 1
            continue
        turn = turns_by_id.get(str(item.get("turn_id")))
        if turn is None:
            dropped += 1
            continue
        index = str(turn["turn_id"])
        if len(per_turn.get(index, [])) >= MAX_CANDIDATES_PER_TURN:
            dropped += 1
            continue
        quote = _raw_quote(item.get("quote"))
        claim = _compact(item.get("claim")) or quote
        if not quote or not is_substantive_claim(quote):
            dropped += 1
            continue
        if not is_complete_span(turn["answer"], quote):
            # 模型改写了原文（换字、截断、拼接）→ 丢弃，绝不用改写的引文当证据
            dropped += 1
            continue
        try:
            record = _interview_record(
                owner_key, session_id, turn, claim=claim, quote=quote,
                evidence_type=item.get("evidence_type"),
            )
        except DomainError:
            dropped += 1
            continue
        per_turn.setdefault(index, []).append(record)
        records.append(record)

    return records, dropped


def persist_records(owner_key, records):
    """落库已由域层构造好的证据记录，按 ``(source_id, source_quote)`` 去重。

    去重键与 ``persist_candidates`` 一致，因此同一场面试重复结束不会堆记录，
    用户否决过的条目也不会被重新塞回来。
    """
    created, skipped = [], 0
    for record in records:
        if evidence_repo.exists_for_source(
            owner_key, record["source_type"], record["source_id"], record["source_quote"]
        ):
            skipped += 1
            continue
        created.append(evidence_repo.create(record))
    return created, skipped


def extract_candidates(owner_key, session_id, turns, router=None):
    """D9 方案 A：面试结束后一次性抽取候选事实。

    **实现时机的偏离**：挂在结束时一次性抽取，而不是逐轮抽取。成本是轮数 × 模型调用，
    而候选最终要被用户批量确认 —— 逐轮落库只会让确认列表变长，且同一段经历会在多轮
    里重复出现。结束时才有完整对话，抽取质量也更高。

    模型调用失败**不抛错**：降级为 ``answer_quote`` 兜底，面试结果本身不受影响。
    """
    extracted = None
    if router is not None:
        payload = [
            {
                "turn_id": turn["turn_id"],
                "question": _compact(turn.get("question")),
                "answer": turn["answer"],
            }
            for turn in _interview_turns(turns)
        ]
        if payload:
            try:
                result = router.call(
                    "interview_evidence",
                    json.dumps(payload, ensure_ascii=False),
                    context={"turn_count": len(payload)},
                )
                if result.get("status") == "success" and isinstance(result.get("output"), dict):
                    candidates = result["output"].get("candidates")
                    if isinstance(candidates, list):
                        extracted = candidates
            except Exception as exc:  # noqa: BLE001 - 抽取失败不得影响面试结束
                logger.warning("[evidence] interview extraction failed: %s", type(exc).__name__)

    records, dropped = candidates_from_interview(
        owner_key, session_id, turns, extracted=extracted
    )
    created, skipped = persist_records(owner_key, records)
    return {
        "created": created,
        "skipped": skipped,
        "dropped": dropped,
        "degraded": extracted is None,
    }


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
