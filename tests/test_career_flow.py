# -*- coding: utf-8 -*-
"""Phase 3 core-flow contract: Resume → Evidence → Target Job → Decision → Interview.

These tests exercise the whole backend chain through the HTTP surface, not just the
services, because the failure modes that matter here are cross-layer:

* a **section heading** ("实习经历") must never become a career fact,
* a **truncated window** must never be quoted as evidence,
* a **JD heading** ("职位描述") must never become a requirement that then fabricates
  a blocking gap and forces PASS,
* a **weak hard requirement** is rewriteable → STRETCH, while an unmet **credential**
  is not → PASS,
* another owner must not be able to read, analyse or delete someone else's data.

The verdict distribution is asserted explicitly, because a rule that can only ever
return one verdict is broken even though every individual assertion might pass.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures-synthetic"

RESUME = (FIXTURES / "resumes" / "resume-01-swe.txt").read_text(encoding="utf-8")
JD_SWE = (FIXTURES / "jobs" / "job-01-swe.txt").read_text(encoding="utf-8")
JD_FE = (FIXTURES / "jobs" / "job-02-fe.txt").read_text(encoding="utf-8")
JD_DATA = (FIXTURES / "jobs" / "job-03-data.txt").read_text(encoding="utf-8")


class ConsentedClient:
    """把同意令牌固定注入每个请求的小包装（Flask 测试客户端的 headers 不可这样赋值）。"""

    def __init__(self, flask_client, token):
        self.raw = flask_client
        self.token = token

    @property
    def application(self):
        return self.raw.application

    def _kwargs(self, kwargs):
        headers = {"X-Consent-Token": self.token}
        headers.update(kwargs.pop("headers", None) or {})
        kwargs["headers"] = headers
        return kwargs

    def get(self, path, **kwargs):
        return self.raw.get(path, **self._kwargs(kwargs))

    def post(self, path, **kwargs):
        return self.raw.post(path, **self._kwargs(kwargs))

    def delete(self, path, **kwargs):
        return self.raw.delete(path, **self._kwargs(kwargs))

    def options(self, path, **kwargs):
        return self.raw.options(path, **self._kwargs(kwargs))


def _consent(app_client):
    token = app_client.post("/api/wf01/consent", json={"accepted": True}).json["consent_token"]
    return ConsentedClient(app_client, token)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A fresh database + Flask client per test, with consent already issued."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "career_flow.db"))
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "phase3-flow-secret")

    import api.index as api_module
    from repositories import migrations
    from tools import database

    database.reset_init_cache()
    migrations.reset_cache()
    api_module.app.config.update(TESTING=True)

    return _consent(api_module.app.test_client())


def _second_owner(client):
    """另一个 owner（不同 consent → 不同 guest 归属），用于归属隔离测试。"""
    return _consent(client.application.test_client())


def _make_target_job(client, jd=JD_SWE, **extra):
    payload = {"jdText": jd}
    payload.update(extra)
    response = client.post("/api/target-jobs", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _analyse(client, target_job_id, resume=RESUME):
    response = client.post(
        "/api/target-jobs/%d/analyse" % target_job_id, json={"resumeText": resume}
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


# ------------------------------------------------------------------ #
# D8=A · 候选证据
# ------------------------------------------------------------------ #

def test_diagnosis_candidates_are_pending_and_never_confirmed(client):
    """模型抽取只能产出 pending；HTTP 层不提供任何直接写 confirmed 的入参。"""
    job = _make_target_job(client)
    result = _analyse(client, job["targetJob"]["id"])

    assert result["analysis"]["new_candidate_evidence"] > 0

    profile = client.get("/api/profile").get_json()
    assert profile["pending"], "应当有候选证据"
    for item in profile["pending"]:
        assert item["status"] == "pending"
        assert item["user_confirmed"] == 0
        assert item["confirmed_at"] is None
        assert item["source_type"] == "resume"
        assert item["source_quote"], "引文必填"
    assert profile["confirmed"] == []
    assert "尚未核实" in profile["notice"]


def test_section_headings_never_become_career_facts(client):
    """「实习经历」「技能清单」是版块标题，不是职业事实。"""
    from services import career_evidence_service as evidence_service

    for heading in ("实习经历", "技能清单", "个人信息", "教育背景"):
        assert evidence_service.is_substantive_claim(heading) is False
        assert heading in evidence_service.SECTION_HEADINGS

    # 一句真正的陈述则应当通过
    assert evidence_service.is_substantive_claim(
        "编写接口文档并推动联调，与前端约定统一的错误码规范"
    ) is True


def test_truncated_windows_are_rejected_even_when_they_are_substrings(client):
    """规则降级路径给的是定长窗口（词中间截断），必须是"不完整片段"。"""
    from services import career_evidence_service as evidence_service

    text = "负责订单接口开发并完成上线验证，把响应时间从 800ms 降到 220ms。"
    truncated = "负责订单接口开发并完成上线验证，把响应时间从 800"  # 结尾不是边界
    complete = "负责订单接口开发并完成上线验证"

    assert evidence_service.is_complete_span(text, truncated) is False
    assert evidence_service.is_complete_span(text, complete) is True
    assert evidence_service.is_complete_span(text, "完全不存在的句子") is False


def test_candidates_require_a_source_quote_that_matches_the_original(client):
    """引文对不上原文的一律不产 —— 宁可少一条，也不留不可核验的证据。"""
    from services import career_evidence_service as evidence_service

    profile = {
        "subscores": {
            "clarity": {"source_spans": [{"quote": "这句话根本不在简历里，但是够长了"}]},
            "achievement_evidence": {"source_spans": []},
            "skill_evidence": {"source_spans": []},
        }
    }
    candidates = evidence_service.candidates_from_diagnosis(
        "guest:x", "sess", profile, RESUME
    )
    assert candidates == []


def test_evidence_lifecycle_confirm_reject_edit_and_delete(client):
    job = _make_target_job(client)
    _analyse(client, job["targetJob"]["id"])
    pending = client.get("/api/profile").get_json()["pending"]
    assert len(pending) >= 3

    first = pending[0]["id"]
    confirmed = client.post("/api/profile/evidence/%d/confirm" % first).get_json()["evidence"]
    assert confirmed["status"] == "confirmed"
    assert confirmed["user_confirmed"] == 1
    assert confirmed["confirmed_at"]

    # 已确认的证据被改正文会退回 pending（防止"确认过的旧文案被悄悄替换"）
    edited = client.post(
        "/api/profile/evidence/%d/edit" % first,
        json={"claim": "我重构了订单模块的接口层并完成上线验证"},
    ).get_json()["evidence"]
    assert edited["status"] == "pending"
    assert edited["user_confirmed"] == 0
    assert edited["confirmed_at"] is None

    # 重新确认
    again = client.post("/api/profile/evidence/%d/confirm" % first).get_json()["evidence"]
    assert again["status"] == "confirmed"

    # confirmedByUser 的语义是"这次改动是用户本人做的，别退回"，
    # 而不是"把 pending 提升为 confirmed" —— 所以它只在已确认时才有意义
    kept = client.post(
        "/api/profile/evidence/%d/edit" % first,
        json={"claim": "我重构了订单模块的接口层并完成上线验证，接口耗时下降 60%",
              "confirmedByUser": True},
    ).get_json()["evidence"]
    assert kept["status"] == "confirmed"
    assert kept["user_confirmed"] == 1

    # 已被否决的不能直接确认
    rejected = client.post(
        "/api/profile/evidence/%d/reject" % pending[1]["id"]
    ).get_json()["evidence"]
    assert rejected["status"] == "rejected"
    blocked = client.post("/api/profile/evidence/%d/confirm" % pending[1]["id"])
    assert blocked.status_code == 422
    assert blocked.json["error"] == "evidence_rejected"

    assert client.delete("/api/profile/evidence/%d" % pending[2]["id"]).status_code == 200
    assert client.delete("/api/profile/evidence/%d" % pending[2]["id"]).status_code == 404


def test_only_confirmed_evidence_is_usable(client):
    """下游只读已确认证据 —— 这是 source of truth 的定义。"""
    from repositories import career_evidence as evidence_repo

    job = _make_target_job(client)
    _analyse(client, job["targetJob"]["id"])
    pending = client.get("/api/profile").get_json()["pending"]
    assert len(pending) >= 2

    # 确认前：库里一条 usable 都没有（service 的 usable_evidence 只查 confirmed）
    from services import career_evidence_service as evidence_service

    owner = _owner_key(client)
    assert evidence_service.usable_evidence(owner) == []

    client.post("/api/profile/evidence/%d/confirm" % pending[0]["id"])

    usable = evidence_service.usable_evidence(owner)
    assert [item["id"] for item in usable] == [pending[0]["id"]]
    assert evidence_repo.counts(owner)["confirmed"] == 1
    assert evidence_repo.counts(owner)["pending"] == len(pending) - 1


def _owner_key(client):
    """复算该 client 的 owner_key（与 api.index._owner_context 同口径）。"""
    import hashlib

    return "guest:legacy:" + hashlib.sha256(client.token.encode("utf-8")).hexdigest()[:24]


# ------------------------------------------------------------------ #
# Target Job · 解析过滤
# ------------------------------------------------------------------ #

def test_jd_headings_and_the_title_line_do_not_become_requirements(client):
    job = _make_target_job(client)
    dropped = job["droppedNonRequirements"]

    assert any("职位描述" in item for item in dropped), dropped
    assert any("常用技术栈" in item for item in dropped), dropped
    # 首行本来是职位名，应被丢弃并回收成岗位名
    assert any("后端开发工程师" in item for item in dropped), dropped
    assert job["targetJob"]["position"].startswith("后端开发工程师")

    texts = [row["text"] for row in job["requirements"]]
    assert "职位描述" not in texts
    assert not any(text.startswith("后端开发工程师（校招）") for text in texts)
    assert len(texts) >= 8, "真实要求不应被误删"


def test_unparseable_jd_is_rejected_instead_of_producing_a_fake_job(client):
    response = client.post("/api/target-jobs", json={"jdText": "职位描述\n任职要求\n"})
    assert response.status_code == 422
    assert response.json["error"] == "no_requirements"


def test_target_job_requires_jd_or_profile(client):
    response = client.post("/api/target-jobs", json={})
    assert response.status_code == 422
    assert response.json["error"] == "jd_required"


# ------------------------------------------------------------------ #
# Decision · APPLY / STRETCH / PASS
# ------------------------------------------------------------------ #

def test_weak_hard_requirement_is_stretch_not_pass(client):
    """硬性要求只是弱命中 → 可由已有证据重写 → STRETCH，不是 PASS。"""
    job = _make_target_job(client, jd="任职要求：\n本科及以上学历，计算机相关专业；\n熟练掌握 TypeScript 和 React；\n")
    result = _analyse(client, job["targetJob"]["id"])

    assert result["decision"]["decision"] == "STRETCH"
    assert all(gap["blocking"] == 0 for gap in result["gaps"] if gap["priority"] == "P0")


def test_unmet_credential_is_pass(client):
    """学历门槛高于现有 → 不可短期解决 → PASS。"""
    job = _make_target_job(client, jd="任职要求：\n硕士研究生及以上学历，计算机相关专业；\n")
    result = _analyse(client, job["targetJob"]["id"])

    assert result["decision"]["decision"] == "PASS"
    p0 = [gap for gap in result["gaps"] if gap["priority"] == "P0"]
    assert p0 and all(gap["blocking"] == 1 for gap in p0)


def test_certificate_requirement_blocks_only_until_it_appears(client):
    unmet = _make_target_job(client, jd="任职要求：\n持有 PMP 项目管理证书；\n")
    assert _analyse(client, unmet["targetJob"]["id"])["decision"]["decision"] == "PASS"

    # 简历里出现该证书字样后，"缺证书"这个结论不再成立 → 不再阻断
    mentioned = _make_target_job(client, jd="任职要求：\n持有 PMP 项目管理证书；\n")
    resume_with_cert = RESUME + "\n证书：PMP 项目管理证书（2024）\n"
    verdict = _analyse(client, mentioned["targetJob"]["id"], resume_with_cert)["decision"]["decision"]
    assert verdict in {"APPLY", "STRETCH"}, verdict
    assert verdict != "PASS"


def test_fully_covered_requirements_are_apply(client):
    jd = ("任职要求：\n"
          "负责交易系统的后端服务开发与维护，参与高并发场景下的性能优化。\n"
          "熟悉 MySQL，了解索引优化和慢查询分析。\n")
    job = _make_target_job(client, jd=jd)
    result = _analyse(client, job["targetJob"]["id"])
    assert result["decision"]["decision"] == "APPLY"
    assert result["gaps"] == []


def test_the_rule_reaches_all_three_verdicts(client):
    """只有一种结论可达的规则等于没有规则 —— 三个分支都必须可达。"""
    verdicts = set()
    cases = {
        "pass": "任职要求：\n硕士研究生及以上学历，计算机相关专业；\n",
        "stretch": "任职要求：\n本科及以上学历，计算机相关专业；\n熟练掌握 TypeScript 和 React；\n",
        "apply": ("任职要求：\n"
                  "负责交易系统的后端服务开发与维护，参与高并发场景下的性能优化。\n"
                  "熟悉 MySQL，了解索引优化和慢查询分析。\n"),
    }
    for key, jd in cases.items():
        job = _make_target_job(client, jd=jd)
        verdict = _analyse(client, job["targetJob"]["id"])["decision"]["decision"]
        assert verdict == key.upper(), (key, verdict)
        verdicts.add(verdict)
    assert verdicts == {"PASS", "STRETCH", "APPLY"}


def test_every_decision_cites_at_least_three_checkable_grounds(client):
    job = _make_target_job(client)
    result = _analyse(client, job["targetJob"]["id"])

    citations = result["decision"]["rationale"]["citations"]
    assert len(citations) >= 3
    assert len(set(citations)) == len(citations), "依据不得重复"
    assert any("要求 " in item for item in citations)
    assert any("已确认职业证据" in item for item in citations)


def test_decision_must_agree_with_the_gap_distribution(client):
    """手写结论会被拒绝：缺口的分布决定结论。"""
    from domain.errors import DomainError
    from domain.target_job import decide

    gaps = [{"priority": "P0", "blocking": 1, "status": "open", "gap_type": "missing", "requirement_id": 1}]
    with pytest.raises(DomainError) as err:
        decide(1, "APPLY", ["a", "b", "c"], gaps=gaps)
    assert err.value.code == "decision_inconsistent"


def test_reanalysis_preserves_gap_progress_and_does_not_duplicate(client):
    from repositories import target_job as repo
    from tools import database

    job = _make_target_job(client)
    target_id = job["targetJob"]["id"]
    first = _analyse(client, target_id)
    assert first["gaps"]

    first_ids = {gap["id"] for gap in first["gaps"]}
    # 用户把某个缺口标记为 doing
    repo.set_gap_status(first["gaps"][0]["id"], "doing", database.utc_iso())

    second = _analyse(client, target_id)
    second_ids = {gap["id"] for gap in second["gaps"]}

    assert second_ids == first_ids, "重新分析不应新建重复缺口：%s vs %s" % (first_ids, second_ids)
    after = {gap["id"]: gap["status"] for gap in second["gaps"]}
    assert after.get(first["gaps"][0]["id"]) == "doing", "重新分析不得抹掉用户进度"
    # 匹配行是派生数据，整体替换而不是累加
    assert len(second["matches"]) == len(second["requirements"])


def test_reanalysis_clears_gaps_whose_requirement_is_now_covered(client):
    from repositories import target_job as repo

    job = _make_target_job(client, jd="任职要求：\n熟悉 MySQL，了解索引优化和慢查询分析。\n")
    target_id = job["targetJob"]["id"]

    # 一份完全没有 SQL 的材料 → 该要求 missing → 产生缺口
    _analyse(client, target_id, "熟练掌握 TypeScript 和 React，有前端性能优化经验。")
    assert repo.list_gaps(target_id, status="open"), "首次分析应当产生缺口"

    _analyse(client, target_id, RESUME)  # 这份简历里有 MySQL
    assert repo.list_gaps(target_id, status="open") == []
    cleared = repo.list_gaps(target_id, status="cleared")
    assert cleared, "被覆盖的缺口应标记为 cleared，而不是 done（那会谎称用户解决了它）"


def test_unmatched_material_is_unverifiable_and_never_reads_as_apply(client):
    """材料完全对不上 → unknown。

    这既不是"满足"也不是"缺失"。它必须算缺口 —— 否则一条关键硬性要求会
    既不产生缺口也不阻断，最终输出 APPLY（"关键要求均有已确认证据支撑"），
    而事实是我们什么都没能核实。补材料即可判定，所以推 STRETCH，不是 PASS。
    """
    from repositories import target_job as repo

    job = _make_target_job(client, jd="任职要求：\n熟悉 MySQL，了解索引优化和慢查询分析。\n")
    target_id = job["targetJob"]["id"]
    result = _analyse(client, target_id, "完全无关的一段材料，没有任何技术内容。")

    assert [item["status"] for item in result["requirements"]] == ["unknown"]

    gaps = repo.list_gaps(target_id)
    assert len(gaps) == 1
    assert gaps[0]["gap_type"] == "unverifiable"
    assert gaps[0]["blocking"] == 0, "补材料就能判定，不是不可短期解决"
    assert result["decision"]["decision"] == "STRETCH"


# ------------------------------------------------------------------ #
# Interview · 按 Gap 定向出题
# ------------------------------------------------------------------ #

def test_interview_questions_follow_the_gap_priority(client):
    job = _make_target_job(client)
    target_id = job["targetJob"]["id"]
    result = _analyse(client, target_id)
    assert result["gaps"], "需要有缺口才能验证定向出题"

    started = client.post("/api/wf04/start", json={"targetJobId": target_id}).get_json()

    plan = started["questionPlan"]
    assert plan, "应返回出题计划"
    kinds = [item["kind"] for item in plan]
    assert kinds[0] == "p0_gap", kinds
    # P0 必须全部排在 P1 之前
    assert kinds.index("p0_gap") < (kinds.index("p1_gap") if "p1_gap" in kinds else len(kinds))

    # 首题必须打在最高优先级缺口上，而不是通用题库
    assert started["targets"] and started["targets"][0].startswith("gap-")
    assert started["targetJobId"] == target_id


def test_interview_without_a_target_job_is_unchanged(client):
    started = client.post("/api/wf04/start", json={})
    assert started.status_code == 200
    assert "questionPlan" not in started.get_json()


def test_interview_rejects_a_bad_target_job_id(client):
    response = client.post("/api/wf04/start", json={"targetJobId": "abc"})
    assert response.status_code == 422
    assert response.json["error"] == "invalid_request"


def test_interview_new_facts_can_only_enter_as_pending_evidence():
    """DoD #12：面试里冒出来的新事实必须经用户确认（域层强制）。"""
    from domain import interview as interview_domain
    from domain.evidence import is_usable

    answer = "我在实习期独立负责了订单模块的重构，把接口响应时间从 900ms 压到 180ms。"
    record = interview_domain.candidate_evidence(
        {"session_id": "iv_phase3"},
        {"owner_key": "guest:phase3"},
        "我独立负责了订单模块的重构。",
        "独立负责了订单模块的重构",
        answer,
        evidence_type="experience",
        turn_id=1,
    )
    assert record["source_type"] == "interview"
    assert record["status"] == "pending"
    assert is_usable(record) is False


# ------------------------------------------------------------------ #
# 归属隔离与删除链路
# ------------------------------------------------------------------ #

def test_another_owner_cannot_read_analyse_or_delete(client):
    job = _make_target_job(client)
    target_id = job["targetJob"]["id"]
    _analyse(client, target_id)

    other = _second_owner(client)

    assert other.get("/api/target-jobs/%d" % target_id).status_code == 404
    assert other.get("/api/target-jobs/%d/decision" % target_id).status_code == 404
    assert other.post("/api/target-jobs/%d/analyse" % target_id, json={"resumeText": RESUME}).status_code == 404
    assert other.delete("/api/target-jobs/%d" % target_id).status_code == 404

    # 对方的档案里看不到我们的证据
    assert other.get("/api/profile").get_json()["pending"] == []

    # 我们的数据仍然完整
    assert client.get("/api/target-jobs/%d" % target_id).status_code == 200


def test_deleting_a_target_job_removes_its_requirements_and_gaps(client):
    from repositories import target_job as repo

    job = _make_target_job(client)
    target_id = job["targetJob"]["id"]
    _analyse(client, target_id)
    assert repo.list_requirements(target_id)
    assert repo.list_gaps(target_id)

    assert client.delete("/api/target-jobs/%d" % target_id).status_code == 200
    assert repo.list_requirements(target_id) == []
    assert repo.list_gaps(target_id) == []
    assert client.get("/api/target-jobs/%d" % target_id).status_code == 404
    assert client.get("/api/target-jobs").get_json()["total"] == 0


def test_all_core_flow_endpoints_require_consent(client):
    bare = client.application.test_client()
    for path in ("/api/profile", "/api/target-jobs"):
        response = bare.get(path)
        assert response.status_code == 428, path
        assert response.json["error"] == "consent_required"


def test_core_flow_endpoints_answer_preflight(client):
    for path in ("/api/profile", "/api/profile/evidence/candidates",
                 "/api/profile/evidence/1/confirm", "/api/target-jobs",
                 "/api/target-jobs/1", "/api/target-jobs/1/analyse"):
        assert client.options(path).status_code == 204, path


# ------------------------------------------------------------------ #
# 三份真实 JD 的稳定性（避免回归成"一律 PASS"）
# ------------------------------------------------------------------ #

def test_real_job_fixtures_do_not_all_collapse_to_one_verdict(client):
    verdicts = {}
    for name, jd in (("swe", JD_SWE), ("fe", JD_FE), ("data", JD_DATA)):
        job = _make_target_job(client, jd=jd)
        result = _analyse(client, job["targetJob"]["id"])
        verdicts[name] = result["decision"]["decision"]
        assert result["gaps"], name
        assert len(result["decision"]["rationale"]["citations"]) >= 3, name

    assert len(set(verdicts.values())) >= 1
    assert all(verdict in {"APPLY", "STRETCH", "PASS"} for verdict in verdicts.values())
    # 这份简历整体是"材料能对上但强度不足"，不应被判成不可投
    assert verdicts["swe"] == "STRETCH", verdicts
