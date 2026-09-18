# -*- coding: utf-8 -*-
"""Phase 4 · Action Loop contract: Gap → Action → Artifact → Outcome, and back.

Phase 3 让系统能算出"我差什么"（Gap）和"能不能投"（Decision），但用户拿到结论之后
无事可做。Phase 4 补的是**闭环的那一半**：把缺口翻成今天就能做的一件事，让做完之后
发生的事回流成新证据。

这些测试盯的是闭环里最容易骗人的四件事：

* **开单不等于解决。** 缺口开了行动仍是"未解决"，行动做完了缺口也不会自动消失 ——
  只有当重新分析发现它被覆盖，才允许变 ``cleared``。否则"打了个勾"就成了"能力补齐"。
* **模型说不出的就不写。** D9=A 让模型抽取面试新事实，但抽取结果只能是 ``pending``，
  而且模型说"这轮没有事实"时不能拿 ``answer_quote`` 兜底补一条 —— 那是把编造洗白。
* **结果和状态分开算账。** 记录"被拒"是事实，推进状态机是另一件事；非法推进要如实报
  ``statusApplied=False``，而不是丢掉结果或静默改写历史。
* **派生数据必须跟着源头一起消失。** 删除目标岗位时，由它缺口派生的行动如果留下，
  就是一条能反推出原 JD 要求的孤儿行。
"""
import hashlib
import json
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures-synthetic"
RESUME = (FIXTURES / "resumes" / "resume-01-swe.txt").read_text(encoding="utf-8")
JD_SWE = (FIXTURES / "jobs" / "job-01-swe.txt").read_text(encoding="utf-8")

#: 两句都含量化数字 → 引擎会挑一句当 ``answer_quote``，且必然通过"像职业事实"的判定。
ANSWER_ONE = (
    "我在实习期间独立负责了订单模块的接口重构，把平均响应时间从 900ms 压到 180ms。"
    "同时我推动前后端统一了错误码规范，上线之后线上报错率下降了 40%。"
)
ANSWER_TWO = (
    "我还补齐了订单模块的单元测试，覆盖率从 35% 提到 78%，并把它接进了发布流程。"
)


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
    """独立数据库 + Flask 客户端，同意令牌已签发；模型不可用（走降级路径）。"""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("DUMATE_MODEL", raising=False)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "action_loop.db"))
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "phase4-action-secret")

    import api.index as api_module
    from repositories import migrations
    from repositories import database

    database.reset_init_cache()
    migrations.reset_cache()
    api_module.app.config.update(TESTING=True)

    return _consent(api_module.app.test_client())


def _second_owner(client):
    """另一个 owner（不同 consent → 不同 guest 归属），用于归属隔离测试。"""
    return _consent(client.application.test_client())


def _owner_key(client):
    """复算该 client 的 owner_key（与 api.index._owner_context 同口径）。"""
    return "guest:legacy:" + hashlib.sha256(client.token.encode("utf-8")).hexdigest()[:24]


def _make_target_job(client, jd=JD_SWE):
    response = client.post("/api/target-jobs", json={"jdText": jd})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["targetJob"]["id"]


def _analyse(client, target_id, resume=RESUME):
    response = client.post(
        "/api/target-jobs/%d/analyse" % target_id, json={"resumeText": resume}
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _gap_ready(client):
    """一个分析完毕、带缺口的岗位。"""
    target_id = _make_target_job(client)
    _analyse(client, target_id)
    return target_id


def _plan(client, target_id):
    response = client.post("/api/actions", json={"targetJobId": target_id})
    assert response.status_code in (200, 201), response.get_json()
    return response.get_json()


def _session(client):
    session_id = "iv_phase4_" + uuid.uuid4().hex[:10]
    started = client.post("/api/wf04/start", json={"session_id": session_id})
    assert started.status_code == 200, started.get_json()
    return session_id


def _new_application(client, session_id, company="示例科技", position="后端开发工程师"):
    response = client.post("/api/wf07/applications", json={
        "session_id": session_id,
        "company": company,
        "position": position,
        "cover_letter": "尊敬的招聘负责人：\n\n我希望加入贵司的后端团队。",
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["application"]


# ------------------------------------------------------------------ #
# D9=A · 面试新事实只在结束时抽、且只能是 pending
# ------------------------------------------------------------------ #

def test_interview_end_extracts_new_facts_as_pending_evidence(client):
    """面试里冒出来的新事实必须进"待确认"，不能直接当事实用（DoD #12）。"""
    target_id = _gap_ready(client)
    session_id = _session(client)

    first = client.post("/api/wf04/answer", json={
        "session_id": session_id, "answer_text": ANSWER_ONE, "asr_confidence": None,
    })
    assert first.status_code == 200, first.get_json()
    second = client.post("/api/wf04/answer", json={
        "session_id": session_id, "answer_text": ANSWER_TWO, "asr_confidence": None,
    })
    assert second.status_code == 200, second.get_json()

    ended = client.post("/api/wf04/end", json={
        "session_id": session_id, "targetJobId": target_id,
    })
    assert ended.status_code == 200, ended.get_json()
    body = ended.get_json()

    assert body["targetJobId"] == target_id
    assert body["candidateEvidence"]["created"] >= 1, body["candidateEvidence"]
    # 无模型密钥 → 走 answer_quote 兜底，如实报 degraded
    assert body["candidateEvidence"]["degraded"] is True

    created_ids = set(body["candidateEvidence"]["ids"])
    assert created_ids, "应当返回新建证据的 id"

    profile = client.get("/api/profile").get_json()
    by_id = {item["id"]: item for item in profile["pending"]}
    assert created_ids <= set(by_id), "抽取出来的证据必须落在 pending 列表里"
    for evidence_id in created_ids:
        item = by_id[evidence_id]
        assert item["status"] == "pending"
        assert item["source_type"] == "interview"
        assert item["user_confirmed"] == 0
        assert item["confirmed_at"] is None
        assert item["source_quote"], "引文必填"
    assert profile["confirmed"] == [], "抽取路径绝不允许直接产出已确认证据"


def test_interview_without_a_target_job_extracts_nothing(client):
    """没有目标岗位就没有归属，宁可不抽，也不生成无主证据。"""
    session_id = _session(client)
    client.post("/api/wf04/answer", json={
        "session_id": session_id, "answer_text": ANSWER_ONE, "asr_confidence": None,
    })

    ended = client.post("/api/wf04/end", json={"session_id": session_id})
    assert ended.status_code == 200, ended.get_json()
    assert "candidateEvidence" not in ended.get_json()
    assert client.get("/api/profile").get_json()["pending"] == []


def test_repeated_interview_end_does_not_duplicate_evidence(client):
    """同一场面试重复结束（网络重试）不得堆记录。"""
    target_id = _gap_ready(client)
    session_id = _session(client)
    client.post("/api/wf04/answer", json={
        "session_id": session_id, "answer_text": ANSWER_ONE, "asr_confidence": None,
    })

    first = client.post("/api/wf04/end", json={
        "session_id": session_id, "targetJobId": target_id,
    }).get_json()
    assert first["candidateEvidence"]["created"] >= 1

    second = client.post("/api/wf04/end", json={
        "session_id": session_id, "targetJobId": target_id,
    }).get_json()
    assert second["candidateEvidence"]["created"] == 0
    assert second["candidateEvidence"]["skipped"] == first["candidateEvidence"]["created"]

    # 分析岗位时也会从简历里抽候选（D8=A），所以只数面试来源的这一批
    pending = client.get("/api/profile").get_json()["pending"]
    interview = [item for item in pending if item["source_type"] == "interview"]
    assert len(interview) == first["candidateEvidence"]["created"]


def _turn(turn_id, answer, quote):
    return {
        "turn_id": turn_id,
        "answer": answer,
        "answer_quote": quote,
        "subscores": {"clarity": 60, "achievement_evidence": 55},
    }


def test_model_rewritten_quote_is_dropped_not_stored(client):
    """模型改写原文（换字/截断/拼接）→ 整条丢弃，绝不拿改写的引文当证据。"""
    from services import career_evidence_service as evidence_service

    answer = "我负责了订单模块的接口重构，把响应时间从 900ms 降到 180ms。"
    turns = [_turn(1, answer, "我负责了订单模块的接口重构")]

    records, dropped = evidence_service.candidates_from_interview(
        _owner_key(client), "iv_model", turns,
        extracted=[
            {"turn_id": 1, "claim": "负责订单模块接口重构",
             "quote": "我主导了订单模块的接口重构", "evidence_type": "experience"},
        ],
    )
    assert records == []
    assert dropped == 1


def test_a_model_that_declines_a_turn_is_not_second_guessed(client):
    """模型说"这轮没有事实" → 就真的没有，不允许 answer_quote 兜底补一条。

    这是 D9=A 与降级路径的**本质区别**：降级是"没有判断者"，所以保守地逐轮留档
    （全部 pending，由用户筛）；有判断者时以判断为准，否则"我明白了"这类礼节性回答
    也会进档案，把确认列表变成垃圾场。
    """
    from services import career_evidence_service as evidence_service

    turns = [_turn(1, ANSWER_ONE, "我在实习期间独立负责了订单模块的接口重构")]
    records, dropped = evidence_service.candidates_from_interview(
        _owner_key(client), "iv_decline", turns, extracted=[]
    )
    assert records == []
    assert dropped == 0

    # 同一个 turn 在不传 extracted（降级）时是会被留档的 —— 差异就在"有没有判断者"
    fallback, _ = evidence_service.candidates_from_interview(
        _owner_key(client), "iv_decline", turns, extracted=None
    )
    assert len(fallback) == 1


def test_model_extraction_produces_pending_evidence_locked_to_the_quote(client):
    """模型给的事实经域层收口：状态 pending，引文必须是回答的逐字子串。"""
    from services import career_evidence_service as evidence_service

    quote = "我在实习期间独立负责了订单模块的接口重构，把平均响应时间从 900ms 压到 180ms"
    turns = [_turn(1, ANSWER_ONE, quote)]
    records, dropped = evidence_service.candidates_from_interview(
        _owner_key(client), "iv_good", turns,
        extracted=[{"turn_id": 1, "claim": "独立负责订单模块接口重构，响应时间从 900ms 降到 180ms",
                    "quote": quote, "evidence_type": "experience"}],
    )
    assert dropped == 0
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "pending"
    assert record["source_type"] == "interview"
    assert record["source_quote"] == quote
    # source_id 精确到轮次：同一场面试的第 1 轮与第 2 轮各自去重，不会互相顶掉，
    # 也让前端能说清"这条事实来自第几轮问答"
    assert record["source_id"] == "iv_good:1"


def test_degraded_fallback_skips_answers_without_a_substantive_sentence(client):
    """降级路径也不是照单全收：没有像样的一句事实就丢弃。"""
    from services import career_evidence_service as evidence_service

    turns = [
        _turn(1, "好的，我明白了。", "好的，我明白了"),
        _turn(2, "嗯嗯，谢谢老师。", "嗯嗯，谢谢老师"),
    ]
    records, dropped = evidence_service.candidates_from_interview(
        _owner_key(client), "iv_empty", turns, extracted=None
    )
    assert records == []
    assert dropped == 2


def test_a_failing_model_call_never_breaks_the_interview_end(client):
    """抽取失败不得影响面试结束本身 —— 降级兜底并如实标记。"""
    from services import career_evidence_service as evidence_service

    class ExplodingRouter:
        def call(self, *args, **kwargs):
            raise RuntimeError("provider down")

    turns = [_turn(1, ANSWER_ONE, "我在实习期间独立负责了订单模块的接口重构")]
    result = evidence_service.extract_candidates(
        _owner_key(client), "iv_boom", turns, router=ExplodingRouter()
    )
    assert result["degraded"] is True
    assert len(result["created"]) == 1, "抽取失败仍应走 answer_quote 兜底留档（pending）"


def test_low_confidence_turns_are_not_evidence_sources(client):
    """ASR 置信度过低的轮次没有可靠原文（subscores 为空）→ 不能当证据来源。"""
    from services import career_evidence_service as evidence_service

    turns = [{"turn_id": 1, "answer": ANSWER_ONE, "answer_quote": "被跳过的句子", "subscores": None}]
    records, _ = evidence_service.candidates_from_interview(
        _owner_key(client), "iv_asr", turns, extracted=None
    )
    assert records == []


# ------------------------------------------------------------------ #
# Gap Action Plan · 缺口 → 可执行行动
# ------------------------------------------------------------------ #

def test_plan_opens_one_action_per_open_gap(client):
    target_id = _gap_ready(client)
    result = _plan(client, target_id)

    from repositories import target_job as target_repo

    open_gaps = [gap for gap in target_repo.list_gaps(target_id) if gap["status"] in ("open", "doing")]
    assert result["createdCount"] >= 1
    assert result["createdCount"] + len(result["skipped"]) == len(open_gaps)

    gap_ids = [action["gap_id"] for action in result["created"]]
    assert len(set(gap_ids)) == len(gap_ids), "一条缺口不得开出两条行动"
    for action in result["created"]:
        assert action["status"] == "todo"
        assert action["task"].strip(), "行动必须能直接照做"
        assert action["artifact"].strip(), "没有可验证成果物的行动不算闭环"


def test_planning_twice_does_not_fan_out_actions(client):
    """反复铺开（刷新页面 / 重试）不得让清单膨胀。"""
    target_id = _gap_ready(client)
    first = _plan(client, target_id)
    second = _plan(client, target_id)

    assert second["createdCount"] == 0
    assert second["existingCount"] == first["createdCount"]

    listed = client.get("/api/actions").get_json()
    assert listed["total"] == first["createdCount"]


def _verdict(client, target_id):
    body = client.get("/api/target-jobs/%d/decision" % target_id).get_json()
    return body["decision"]["decision"]


def test_opening_an_action_marks_the_gap_doing_but_keeps_it_unresolved(client):
    """开单只是"开始做了"，不是"做到了" —— Decision 不能因此变乐观。"""
    from repositories import target_job as target_repo
    from domain.target_job import OPEN_GAP_STATUSES

    target_id = _gap_ready(client)
    before = _verdict(client, target_id)
    result = _plan(client, target_id)

    for action in result["created"]:
        gap = target_repo.get_gap(action["gap_id"])
        assert gap["status"] == "doing"
        assert gap["status"] in OPEN_GAP_STATUSES, "doing 仍属未解决集合"

    assert _verdict(client, target_id) == before, "开单不得改变结论"


def test_action_lifecycle_start_complete_then_record_outcome(client):
    target_id = _gap_ready(client)
    action_id = _plan(client, target_id)["created"][0]["id"]

    started = client.post("/api/actions/%d/start" % action_id).get_json()["action"]
    assert started["status"] == "doing"

    completed = client.post("/api/actions/%d/complete" % action_id, json={
        "artifact": "一页含 3 个量化数字的项目说明",
    }).get_json()["action"]
    assert completed["status"] == "done"
    assert completed["artifact"] == "一页含 3 个量化数字的项目说明"

    recorded = client.post("/api/actions/%d/outcome" % action_id, json={
        "outcome": "改完之后同一段经历能讲出两个数字了。",
    }).get_json()["action"]
    assert recorded["outcome"] == "改完之后同一段经历能讲出两个数字了。"
    assert recorded["status"] == "done"

    detail = client.get("/api/actions/%d" % action_id).get_json()["action"]
    assert detail["outcome"] == recorded["outcome"]
    assert detail["gap_priority"], "单条行动要能带出缺口上下文"
    assert detail["target_job_id"] == target_id


def test_outcome_requires_a_completed_action(client):
    """没做任何东西就不该有结果。"""
    target_id = _gap_ready(client)
    action_id = _plan(client, target_id)["created"][0]["id"]

    blocked = client.post("/api/actions/%d/outcome" % action_id, json={"outcome": "我变强了。"})
    assert blocked.status_code == 422
    assert blocked.json["error"] == "action_not_done"

    empty = client.post("/api/actions/%d/outcome" % action_id, json={"outcome": "   "})
    assert empty.status_code == 422
    assert empty.json["error"] == "invalid_request"


def test_dropping_an_action_does_not_close_the_gap(client):
    """放弃行动 ≠ 补齐能力：缺口仍然没被解决，只是允许重新开单。"""
    from repositories import target_job as target_repo

    target_id = _gap_ready(client)
    first = _plan(client, target_id)["created"][0]
    gap_id = first["gap_id"]
    before = _verdict(client, target_id)

    dropped = client.post("/api/actions/%d/drop" % first["id"]).get_json()["action"]
    assert dropped["status"] == "dropped"

    gap = target_repo.get_gap(gap_id)
    assert gap["status"] not in ("done", "dropped", "cleared"), "放弃行动不得关闭缺口"
    assert _verdict(client, target_id) == before

    # 关闭过的行动不算数 → 允许为同一缺口重新开单
    reopened = client.post("/api/actions", json={"gapId": gap_id})
    assert reopened.status_code == 201
    assert reopened.get_json()["opened"] is True
    assert reopened.get_json()["action"]["id"] != first["id"]


def test_reopening_a_gap_only_returns_the_existing_action(client):
    target_id = _gap_ready(client)
    first = _plan(client, target_id)["created"][0]

    again = client.post("/api/actions", json={"gapId": first["gap_id"]})
    assert again.status_code == 200
    payload = again.get_json()
    assert payload["opened"] is False
    assert payload["action"]["id"] == first["id"]


def test_actions_are_listed_by_gap_priority(client):
    target_id = _gap_ready(client)
    _plan(client, target_id)

    listed = client.get("/api/actions").get_json()["actions"]
    assert listed
    ranks = [int(str(item["gap_priority"] or "P9").lstrip("P")) for item in listed]
    assert ranks == sorted(ranks), "P0 必须排在 P1 / P2 之前：%s" % ranks

    filtered = client.get("/api/actions?status=todo").get_json()
    assert all(item["status"] == "todo" for item in filtered["actions"])
    assert filtered["total"] == len(filtered["actions"])


def test_a_gap_without_a_verifiable_artifact_is_reported_not_silently_skipped(client):
    """开不出闭环的缺口要如实报出来，不能让用户以为"都开好单了"。"""
    from repositories import target_job as target_repo
    from repositories import database

    target_id = _gap_ready(client)
    stamp = database.utc_iso()
    bare = target_repo.create_gap({
        "target_job_id": target_id,
        "requirement_id": None,
        "gap_type": "missing",
        "priority": "P2",
        "reason": "手工造的缺口，没有成果物说明",
        "action": "补一段经历",
        "expected_artifact": None,
        "blocking": 0,
        "created_at": stamp,
        "updated_at": stamp,
    })

    result = _plan(client, target_id)
    skipped_ids = {item["gap_id"] for item in result["skipped"]}
    assert bare["id"] in skipped_ids
    assert all(item["reason"].strip() for item in result["skipped"])
    assert bare["id"] not in {action["gap_id"] for action in result["created"]}
    assert bare["id"] not in {action["gap_id"] for action in result["existing"]}

    # 单条开单同样被域层拒绝，且原因透出到 HTTP
    refused = client.post("/api/actions", json={"gapId": bare["id"]})
    assert refused.status_code == 422
    assert refused.json["error"] == "artifact_required"


def test_reanalysis_does_not_fan_out_actions(client):
    """重新分析会刷新缺口文案，但行动清单不该跟着重开。"""
    target_id = _gap_ready(client)
    first = _plan(client, target_id)

    _analyse(client, target_id)
    second = _plan(client, target_id)

    assert second["createdCount"] == 0
    assert second["existingCount"] == first["createdCount"]


def test_another_owner_cannot_see_or_touch_actions(client):
    target_id = _gap_ready(client)
    action = _plan(client, target_id)["created"][0]
    other = _second_owner(client)

    assert other.get("/api/actions").get_json()["total"] == 0
    assert other.get("/api/actions/%d" % action["id"]).status_code == 404
    assert other.post("/api/actions/%d/start" % action["id"]).status_code == 404
    assert other.post("/api/actions/%d/complete" % action["id"]).status_code == 404
    assert other.post("/api/actions/%d/drop" % action["id"]).status_code == 404
    assert other.post("/api/actions/%d/outcome" % action["id"],
                      json={"outcome": "偷看别人的进展"}).status_code == 404
    assert other.delete("/api/actions/%d" % action["id"]).status_code == 404

    # 通过 gapId 也不能越权开单（缺口挂在别人的岗位上）
    assert other.post("/api/actions", json={"gapId": action["gap_id"]}).status_code == 404
    assert other.post("/api/actions", json={"targetJobId": target_id}).status_code == 404

    # 我们的数据仍然完整
    assert client.get("/api/actions/%d" % action["id"]).status_code == 200


def test_deleting_an_action_is_repeatable_and_scoped(client):
    target_id = _gap_ready(client)
    action_id = _plan(client, target_id)["created"][0]["id"]

    assert client.delete("/api/actions/%d" % action_id).status_code == 200
    assert client.get("/api/actions/%d" % action_id).status_code == 404
    assert client.delete("/api/actions/%d" % action_id).status_code == 404

    # 删掉之后允许重新开单
    assert client.post("/api/actions", json={"targetJobId": target_id}).status_code == 201


def test_deleting_a_target_job_also_removes_its_actions(client):
    """派生数据必须跟着源头消失 —— 行动文案就是改写过的 JD 要求。"""
    from repositories import action as action_repo
    from repositories import target_job as target_repo

    target_id = _gap_ready(client)
    created = _plan(client, target_id)["created"]
    assert created

    assert client.delete("/api/target-jobs/%d" % target_id).status_code == 200

    assert target_repo.list_gaps(target_id) == []
    assert action_repo.list_for_owner(_owner_key(client)) == [], (
        "岗位删了，由它缺口派生的行动不能留下孤儿行"
    )
    assert client.get("/api/actions").get_json()["total"] == 0


def test_action_plan_request_must_name_a_target_job_or_a_gap(client):
    empty = client.post("/api/actions", json={})
    assert empty.status_code == 422
    assert empty.json["error"] == "invalid_request"

    bad_target = client.post("/api/actions", json={"targetJobId": "abc"})
    assert bad_target.status_code == 422

    bad_gap = client.post("/api/actions", json={"gapId": "abc"})
    assert bad_gap.status_code == 422


# ------------------------------------------------------------------ #
# 投递结果回流 · Outcome → 状态 + 反向证据
# ------------------------------------------------------------------ #

def test_outcome_advances_the_status_and_writes_pending_evidence(client):
    session_id = _session(client)
    application = _new_application(client, session_id)
    assert application["status"] == "applied"

    response = client.post("/api/wf07/applications/%d/outcome" % application["id"],
                           json={"outcome": "interview", "note": "约了下周三一面。"})
    assert response.status_code == 200, response.get_json()
    body = response.get_json()

    assert body["statusApplied"] is True
    assert body["requestedStatus"] == "interview"
    assert body["application"]["status"] == "interview"
    assert body["outcome"]["outcome"] == "interview"
    assert body["outcome"]["note"] == "约了下周三一面。"
    assert body["evidenceCreated"] is True
    assert body["evidence"]["status"] == "pending"
    assert body["evidence"]["source_type"] == "application_outcome"

    profile = client.get("/api/profile").get_json()
    assert profile["confirmed"] == []
    assert any(item["id"] == body["evidence"]["id"] for item in profile["pending"])
    matched = [item for item in profile["pending"] if item["id"] == body["evidence"]["id"]][0]
    assert matched["user_confirmed"] == 0
    assert matched["source_quote"] == "约了下周三一面。", "结果备注就是引文"


def test_illegal_status_advance_still_records_the_outcome(client):
    """历史结果补记时状态机可能拒绝 —— 结果必须留下，状态如实不变。"""
    session_id = _session(client)
    application = _new_application(client, session_id)
    app_id = application["id"]

    assert client.post("/api/wf07/applications/%d/outcome" % app_id,
                       json={"outcome": "interview"}).get_json()["application"]["status"] == "interview"
    assert client.post("/api/wf07/applications/%d/outcome" % app_id,
                       json={"outcome": "offer"}).get_json()["application"]["status"] == "offer"

    # offer 之后再补记"进入面试"是倒流 → 非法
    replayed = client.post("/api/wf07/applications/%d/outcome" % app_id,
                           json={"outcome": "interview"}).get_json()
    assert replayed["statusApplied"] is False
    assert replayed["requestedStatus"] == "interview"
    assert replayed["application"]["status"] == "offer", "非法推进不得改写历史状态"
    assert replayed["outcome"]["outcome"] == "interview", "结果本身仍然落库"

    outcomes = client.get("/api/wf07/applications/%d/outcomes" % app_id).get_json()["outcomes"]
    assert [item["outcome"] for item in outcomes] == ["interview", "offer", "interview"]


def test_rejection_is_terminal_but_the_result_is_still_recorded(client):
    session_id = _session(client)
    app_id = _new_application(client, session_id)["id"]

    rejected = client.post("/api/wf07/applications/%d/outcome" % app_id,
                           json={"outcome": "rejected"}).get_json()
    assert rejected["statusApplied"] is True
    assert rejected["application"]["status"] == "rejected"

    # 终态之后再补记任何推进都不生效，但结果照样留档
    later = client.post("/api/wf07/applications/%d/outcome" % app_id,
                        json={"outcome": "offer"}).get_json()
    assert later["statusApplied"] is False
    assert later["application"]["status"] == "rejected"
    assert later["evidenceCreated"] is True, "反向证据与状态推进是两本账"


def test_no_response_records_without_moving_the_status(client):
    session_id = _session(client)
    app_id = _new_application(client, session_id)["id"]

    body = client.post("/api/wf07/applications/%d/outcome" % app_id,
                       json={"outcome": "no_response"}).get_json()
    assert body["requestedStatus"] is None
    assert body["statusApplied"] is False
    assert body["application"]["status"] == "applied"
    assert body["outcome"]["outcome"] == "no_response"


def test_repeated_identical_outcome_is_not_duplicated_as_evidence(client):
    session_id = _session(client)
    app_id = _new_application(client, session_id)["id"]

    first = client.post("/api/wf07/applications/%d/outcome" % app_id,
                        json={"outcome": "rejected"}).get_json()
    assert first["evidenceCreated"] is True

    # 同一个结果配同一段备注 → 同一份引文 → 不再重复写证据
    second = client.post("/api/wf07/applications/%d/outcome" % app_id,
                         json={"outcome": "rejected"}).get_json()
    assert second["evidenceCreated"] is False
    assert second["evidenceSkipped"] == 1

    outcomes = client.get("/api/wf07/applications/%d/outcomes" % app_id).get_json()["outcomes"]
    assert len(outcomes) == 2, "结果记录本身是历史，允许重复"


def test_unknown_outcome_is_rejected(client):
    session_id = _session(client)
    app_id = _new_application(client, session_id)["id"]

    response = client.post("/api/wf07/applications/%d/outcome" % app_id,
                           json={"outcome": "hired_maybe"})
    assert response.status_code == 422
    assert response.json["error"] == "invalid_outcome"

    empty = client.post("/api/wf07/applications/%d/outcome" % app_id, json={})
    assert empty.status_code == 422
    assert empty.json["error"] == "invalid_request"


def test_another_owner_cannot_read_or_write_outcomes(client):
    session_id = _session(client)
    app_id = _new_application(client, session_id)["id"]
    client.post("/api/wf07/applications/%d/outcome" % app_id, json={"outcome": "interview"})

    other = _second_owner(client)
    assert other.get("/api/wf07/applications/%d/outcomes" % app_id).status_code == 404
    assert other.post("/api/wf07/applications/%d/outcome" % app_id,
                      json={"outcome": "offer"}).status_code == 404

    outcomes = client.get("/api/wf07/applications/%d/outcomes" % app_id).get_json()["outcomes"]
    assert [item["outcome"] for item in outcomes] == ["interview"]


# ------------------------------------------------------------------ #
# 契约 · 同意 / 预检 / 生产可达性
# ------------------------------------------------------------------ #

PHASE4_PATHS = (
    "/api/actions",
    "/api/actions/1",
    "/api/actions/1/start",
    "/api/actions/1/complete",
    "/api/actions/1/outcome",
    "/api/actions/1/drop",
    "/api/wf07/applications/1/outcome",
    "/api/wf07/applications/1/outcomes",
)


def test_phase4_endpoints_require_consent(client):
    bare = client.application.test_client()
    for path in ("/api/actions",):
        response = bare.get(path)
        assert response.status_code == 428, path
        assert response.json["error"] == "consent_required"


def test_phase4_endpoints_answer_preflight(client):
    for path in PHASE4_PATHS:
        assert client.options(path).status_code == 204, path


def test_phase4_routes_are_reachable_in_production(client):
    """只在本地注册、vercel.json 里没有重写的接口，线上就是 404。

    反向检查（重写目标必须有处理器）已有测试覆盖；这里补正向：新增的接口必须
    在生产入口有条路能走进来。
    """
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    rules = config["rewrites"]

    def covered(path):
        for rule in rules:
            source = rule["source"]
            if source == path:
                return True
            if source.endswith("/(.*)"):
                prefix = source[: -len("/(.*)")]
                if path.startswith(prefix + "/"):
                    return True
        return False

    for path in PHASE4_PATHS:
        assert covered(path), "生产入口缺少重写规则：%s" % path


def test_health_lists_the_action_plan(client):
    workflows = client.get("/api/health").get_json()["workflows"]
    assert workflows["actions"] == "available"
