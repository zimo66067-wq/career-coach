# -*- coding: utf-8 -*-
"""DoD #10 · 求职信接地：岗位要求 + 已确认证据（Phase 4b）

Phase 4 之前，求职信只读 F1 诊断里模型抽的 span 引文 —— 那些**不是已确认事实**，
只是"模型觉得相关"的简历片段。DoD #10 要求它同时用上目标岗位与职业证据。

这些测试盯的是这条链路最容易骗人的四件事：

* **未确认的候选证据绝不能进正文。** 求职信是发给雇主的对外材料，不是内部草稿；
  把 pending 事实写进去，等于让"模型觉得像"变成"求职者声称"。
* **没有已确认证据时不许请模型写。** 只给岗位要求、不给事实底座，模型一定会替用户编经历。
* **未覆盖的要求不许声称具备。** 缺口是"禁止声称"名单，不是写作素材；它只能出现在
  接口元数据里让界面提示用户，不能进正文。
* **旧路径不能被顺手改坏。** 不带 `targetJobId` 的调用行为必须与 Phase 4 之前一致。
"""
import hashlib
import io
import uuid
from pathlib import Path

import pytest

from tools.providers import model as model_provider

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures-synthetic"
RESUME = (FIXTURES / "resumes" / "resume-01-swe.txt").read_text(encoding="utf-8")
JD_SWE = (FIXTURES / "jobs" / "job-01-swe.txt").read_text(encoding="utf-8")

COMPANY = "示例科技"
POSITION = "后端开发工程师"


class ConsentedClient:
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
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("DUMATE_MODEL", raising=False)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "letter.db"))
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "phase4b-letter-secret")

    import api.index as api_module
    from repositories import migrations
    from tools import database

    database.reset_init_cache()
    migrations.reset_cache()
    api_module.app.config.update(TESTING=True)

    return _consent(api_module.app.test_client())


def _owner_key(client):
    return "guest:legacy:" + hashlib.sha256(client.token.encode("utf-8")).hexdigest()[:24]


def _session(client):
    session_id = "iv_letter_" + uuid.uuid4().hex[:10]
    started = client.post("/api/wf04/start", json={"session_id": session_id})
    assert started.status_code == 200, started.get_json()
    return session_id


def _legacy_session(client):
    """旧路径要的是 F1 诊断落库（它读诊断里的 span 引文），不是面试会话。"""
    uploaded = client.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()
    session_id = uploaded.get_json()["session_id"]
    diagnosed = client.post("/api/wf02/diagnose", json={
        "resumeText": uploaded.get_json()["resumeText"], "session_id": session_id,
    })
    assert diagnosed.status_code == 200, diagnosed.get_json()
    return session_id


def _target_job(client, session_id, company=COMPANY, position=POSITION):
    response = client.post("/api/target-jobs", json={
        "jdText": JD_SWE, "session_id": session_id, "company": company, "position": position,
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["targetJob"]["id"]


def _analyse(client, target_id, resume=RESUME):
    response = client.post(
        "/api/target-jobs/%d/analyse" % target_id, json={"resumeText": resume}
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _ready(client, confirmed=1):
    """一个建好、分析完、并已确认 N 条证据的岗位。"""
    session_id = _session(client)
    target_id = _target_job(client, session_id)
    _analyse(client, target_id)

    pending = client.get("/api/profile").get_json()["pending"]
    assert len(pending) >= max(confirmed, 1), "分析应当产出候选证据"
    confirmed_records = []
    for item in pending[:confirmed]:
        body = client.post("/api/profile/evidence/%d/confirm" % item["id"]).get_json()
        confirmed_records.append(body["evidence"])
    return session_id, target_id, confirmed_records, pending


def _letter(client, session_id, target_id=None, **extra):
    payload = {"session_id": session_id, "company": COMPANY, "position": POSITION}
    if target_id is not None:
        payload["targetJobId"] = target_id
    payload.update(extra)
    response = client.post("/api/wf07/cover-letter", json=payload)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


class StubRouter:
    """替身模型路由：记录调用并返回指定 output。"""

    def __init__(self, output):
        self.output = output
        self.calls = []

    def call(self, task, prompt, **kwargs):
        self.calls.append({"task": task, "prompt": prompt})
        return {"status": "success", "output": self.output}


# ------------------------------------------------------------------ #
# 接地路径：只引用已确认证据
# ------------------------------------------------------------------ #

def test_letter_quotes_only_the_confirmed_evidence(client):
    session_id, target_id, confirmed, pending = _ready(client, confirmed=1)
    body = _letter(client, session_id, target_id)

    assert body["grounding"] == "target_job+evidence"
    assert body["pending_confirm"] is True, "求职信始终是候选，人工确认后才落库"
    assert [item["id"] for item in body["evidence"]] == [confirmed[0]["id"]]
    # 正文必须真的用上那条已确认证据（四字片段级校验）
    assert confirmed[0]["claim"][:8] in body["candidate"], body["candidate"]

    # 未确认的候选证据一个字都不能进正文
    for item in pending:
        if item["id"] == confirmed[0]["id"]:
            continue
        assert item["claim"] not in body["candidate"]
        assert item["source_quote"] not in body["candidate"]


def test_unconfirmed_evidence_cannot_reach_the_letter(client):
    """只有 pending、没有任何 confirmed：正文不得包含候选证据的原文。"""
    session_id = _session(client)
    target_id = _target_job(client, session_id)
    _analyse(client, target_id)

    pending = client.get("/api/profile").get_json()["pending"]
    assert pending
    body = _letter(client, session_id, target_id)

    assert body["grounding"] == "target_job_no_evidence"
    assert body["evidence"] == []
    for item in pending:
        assert item["claim"] not in body["candidate"]
        assert item["source_quote"] not in body["candidate"]


def test_without_confirmed_evidence_the_letter_is_a_frame_not_a_fabrication(client):
    """没有事实底座就不许写经历 —— 只给框架，并明确告诉用户差什么。"""
    session_id = _session(client)
    target_id = _target_job(client, session_id)
    _analyse(client, target_id)

    body = _letter(client, session_id, target_id)
    assert "（请在正文中补充" in body["candidate"]
    assert "还没有确认任何职业证据" in body["notice"]
    assert body["basis"] == "rule"


def test_a_job_without_any_evidence_rows_still_produces_a_frame(client):
    """最朴素的新用户：只建了岗位、一条证据都没有（连档案行都没建）—— 不许 500，只给框架。"""
    session_id = _session(client)
    target_id = _target_job(client, session_id)

    body = _letter(client, session_id, target_id)
    assert body["grounding"] == "target_job_no_evidence"
    assert body["evidence"] == []
    assert body["requirements"], "岗位要求与证据无关，仍然要报出来"
    assert "还没有确认任何职业证据" in body["notice"]


def test_company_and_position_default_from_the_target_job(client):
    """只给 targetJobId 也能出信：公司与职位从岗位记录取。"""
    session_id, target_id, _, _ = _ready(client)
    response = client.post("/api/wf07/cover-letter", json={
        "session_id": session_id, "targetJobId": target_id,
    })
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["company"] == COMPANY
    assert body["position"] == POSITION
    assert COMPANY in body["candidate"] or POSITION in body["candidate"]


def test_position_falls_back_when_the_job_has_none(client):
    """岗位没解析出职位名时，才轮到调用方传入的职位兜底；都没有则 422。"""
    session_id = _session(client)
    response = client.post("/api/target-jobs", json={
        "jdText": "任职要求：\n熟悉 Python 与 SQL；\n", "session_id": session_id,
    })
    target_id = response.get_json()["targetJob"]["id"]

    body = _letter(client, session_id, target_id, position="后端开发工程师")
    assert body["position"] == "后端开发工程师"

    missing = client.post("/api/wf07/cover-letter", json={
        "session_id": session_id, "targetJobId": target_id,
    })
    assert missing.status_code == 422
    assert missing.json["error"] == "apply_info_required"


# ------------------------------------------------------------------ #
# 要求与缺口：写什么、不写什么
# ------------------------------------------------------------------ #

def test_letter_lists_the_requirements_it_answers_in_priority_order(client):
    session_id, target_id, _, _ = _ready(client)
    body = _letter(client, session_id, target_id)

    requirements = body["requirements"]
    assert requirements, "接地路径必须报出正文回应的要求"
    assert len(requirements) <= 5, "200 字的正文塞不下十几条要求"
    ranks = [{"P0": 0, "P1": 1, "P2": 2}[item["priority"]] for item in requirements]
    assert ranks == sorted(ranks), "要求必须按 P0 → P1 → P2 排序"
    assert all(item["text"].strip() for item in requirements)


def test_uncovered_requirements_are_reported_but_never_claimed(client):
    """缺口是「禁止声称」名单 —— 进元数据，不进正文。"""
    session_id, target_id, _, _ = _ready(client)
    body = _letter(client, session_id, target_id)
    assert body["gaps"], "这份 JD 与简历应当留下未覆盖的要求"

    assert "未声称具备" in body["notice"]
    from repositories import target_job as target_repo

    for gap in body["gaps"]:
        row = target_repo.get_gap(gap["id"])
        reason = (row.get("missing_evidence") or row.get("reason") or "").strip()
        if reason:
            assert reason not in body["candidate"], "缺口说明不得出现在正文里"


# ------------------------------------------------------------------ #
# 模型路径的三道门
# ------------------------------------------------------------------ #

def test_model_prose_is_used_when_it_stays_grounded(client, monkeypatch):
    session_id, target_id, confirmed, _ = _ready(client, confirmed=1)
    claim = confirmed[0]["claim"]
    stub = StubRouter({"candidate": "我应聘%s的%s岗位。%s。期待进一步沟通。" % (COMPANY, POSITION, claim)})
    monkeypatch.setattr(model_provider, "build_model_router", lambda: stub)

    body = _letter(client, session_id, target_id)
    assert body["basis"] == "model"
    assert body["grounding"] == "target_job+evidence"
    assert stub.calls and stub.calls[0]["task"] == "cover_letter"
    # 提示词里必须同时出现要求清单与证据清单
    prompt = stub.calls[0]["prompt"]
    assert claim in prompt
    assert body["requirements"][0]["text"] in prompt


def test_model_prose_that_invents_experience_is_rejected(client, monkeypatch):
    """模型写了一段没有任何证据支撑的漂亮话 → 退回规则模板，而不是放行。"""

    session_id, target_id, _, _ = _ready(client, confirmed=1)
    invented = "我在字节跳动负责过千万级并发系统，把 QPS 提升了 300%%。"
    stub = StubRouter({"candidate": "尊敬%s：我应聘%s。%s" % (COMPANY, POSITION, invented)})
    monkeypatch.setattr(model_provider, "build_model_router", lambda: stub)

    body = _letter(client, session_id, target_id)
    assert body["basis"] == "rule", "无证据支撑的模型输出必须被拒"
    assert "字节跳动" not in body["candidate"]


def test_the_model_is_not_even_asked_when_there_is_no_confirmed_evidence(client, monkeypatch):
    """规则 1 的正面证明：没有事实底座时模型调用次数为 0。"""

    session_id = _session(client)
    target_id = _target_job(client, session_id)
    _analyse(client, target_id)

    stub = StubRouter({"candidate": "我应聘%s的%s岗位，我很有信心。" % (COMPANY, POSITION)})
    monkeypatch.setattr(model_provider, "build_model_router", lambda: stub)

    body = _letter(client, session_id, target_id)
    assert body["grounding"] == "target_job_no_evidence"
    assert stub.calls == [], "没有已确认证据时不该请模型写（它会替用户编经历）"


# ------------------------------------------------------------------ #
# 归属隔离、参数校验与旧路径兼容
# ------------------------------------------------------------------ #

def test_another_owner_cannot_ground_on_someone_elses_target_job(client):
    """借用别人的 targetJobId 必须 404 —— 与 /api/target-jobs/* 同一错误码，前端可复用分支。

    另一方的请求里刻意填了**别的**公司与职位：这样一来，只要响应里出现岗位记录里的
    公司/职位名，就说明归属校验失败后仍在回显他人数据。
    """
    session_id, target_id, _, _ = _ready(client)
    other = _consent(client.application.test_client())
    other_session = _session(other)

    response = other.post("/api/wf07/cover-letter", json={
        "session_id": other_session, "targetJobId": target_id,
        "company": "别家公司", "position": "别的职位",
    })
    assert response.status_code == 404
    assert response.json["error"] == "target_job_not_found"
    body = response.get_data(as_text=True)
    assert COMPANY not in body and POSITION not in body, "报错不得回显他人岗位内容"


def test_a_bad_target_job_id_is_rejected(client):
    session_id = _session(client)
    response = client.post("/api/wf07/cover-letter", json={
        "session_id": session_id, "targetJobId": "abc", "company": COMPANY, "position": POSITION,
    })
    assert response.status_code == 422
    assert response.json["error"] == "invalid_request"


def test_legacy_call_without_a_target_job_is_unchanged(client):
    """不带 targetJobId 时行为不变：仍走 F1 诊断路径，并如实标记 grounding=diagnosis。"""
    session_id = _legacy_session(client)
    body = _letter(client, session_id)
    assert body["grounding"] == "diagnosis"
    assert body["company"] == COMPANY and body["position"] == POSITION
    assert body["candidate"].strip()
    assert "evidence" not in body, "旧路径不报证据清单，避免前端把两条路混在一起"


def test_legacy_call_still_requires_company_and_position(client):
    session_id = _session(client)
    response = client.post("/api/wf07/cover-letter", json={"session_id": session_id})
    assert response.status_code == 422
    assert response.json["error"] == "apply_info_required"


def test_letter_route_still_requires_consent_and_answers_preflight(client):
    bare = client.application.test_client()
    response = bare.post("/api/wf07/cover-letter", json={"session_id": "x"})
    assert response.status_code == 428
    assert response.json["error"] == "consent_required"
    assert client.options("/api/wf07/cover-letter").status_code == 204
