# -*- coding: utf-8 -*-
"""Phase 4 contract tests: knowledge base (BM25),
SSE interview follow-up stream, and resume rewrite (optimize + apply)."""
import io
import json
import tempfile
import uuid
from pathlib import Path

import api.index as api_module
import repositories.database as database
import domain.knowledge as knowledge
import domain.optimizer as optimizer

RESUME = (
    "项目经历：负责后端接口开发并完成上线验证，持续跟进问题闭环。"
    "熟悉 Python、Flask 与 SQL 查询优化，具备数据库设计与接口文档维护经验。"
)
JD_TEXT = (
    "岗位职责：负责后端 API 开发与接口文档维护。\n"
    "任职要求：熟悉 Python、Flask 与 SQL；有项目交付经验。\n"
    "加分项：熟悉 Redis。\n"
    "技术栈：Python、Flask、SQLite。"
)


def raw_client(monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    monkeypatch.delenv("DUMATE_CONSENT_MAX_AGE_SECONDS", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    if not hasattr(monkeypatch, "_career_test_db"):
        monkeypatch._career_test_db = str(
            Path(tempfile.mkdtemp(prefix="career_coach_test_"))
            / ("test_%s.db" % uuid.uuid4().hex[:8])
        )
    monkeypatch.setenv("RESUME_DB_PATH", monkeypatch._career_test_db)
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


def issue_consent(raw):
    response = raw.post("/api/wf01/consent", json={"accepted": True})
    assert response.status_code == 200
    return response.json["consent_token"]


def authed_post(raw, token, path, json_body):
    return raw.post(path, json=json_body, headers={"X-Consent-Token": token})


def authed_get(raw, token, path):
    return raw.get(path, headers={"X-Consent-Token": token})


def upload_resume(raw, token):
    response = raw.post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(RESUME.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
        headers={"X-Consent-Token": token},
    )
    assert response.status_code == 200
    return response.json


def diagnose(raw, token, sid, resume_text):
    response = authed_post(
        raw, token, "/api/wf02/diagnose",
        {"resumeText": resume_text, "session_id": sid},
    )
    assert response.status_code == 200
    return response.json


# ---------------------------------------------------------------- #
# Knowledge service (unit)
# ---------------------------------------------------------------- #

def test_knowledge_service_lists_categories_and_questions():
    categories = knowledge.list_categories()
    assert len(categories) >= 5
    items = knowledge.list_questions()
    assert len(items) >= 24
    assert sum(c["count"] for c in categories) == len(items)
    zh = knowledge.list_questions("自我介绍")
    assert zh and all(e["category"] == "自我介绍" for e in zh)


def test_knowledge_service_bm25_search_returns_items():
    result = knowledge.search_questions("自我介绍 优势")
    assert result["engine"] == "bm25"
    assert result["items"]
    first = result["items"][0]
    for key in ("id", "category", "question", "answer", "tips", "keywords", "score"):
        assert key in first
    assert "BM25" in result["notice"]  # no EMBEDDING_API_KEY in tests


def test_knowledge_service_empty_query_returns_notice():
    result = knowledge.search_questions("   ")
    assert result["items"] == []
    assert result["total"] == 0
    assert "关键词" in result["notice"]


# ---------------------------------------------------------------- #
# Knowledge API —— 2026-09-13 已下线
# ---------------------------------------------------------------- #
# 「面经知识库」不再是独立产品：导航、页面与 /api/knowledge/* 均已删除。
# 题库数据保留在 domain/knowledge.py，作为 Interview Engine 的内部数据源
# （模块级行为仍由上面的 knowledge 测试覆盖）。这里固化 API 已下线。

def test_knowledge_api_is_retired(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    for path in ("/api/knowledge/questions", "/api/knowledge/search?q=test"):
        assert authed_get(raw, token, path).status_code == 404


# ---------------------------------------------------------------- #
# SSE interview stream
# ---------------------------------------------------------------- #

def test_wf04_stream_returns_sse_fragments_and_done(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    uploaded = upload_resume(raw, token)
    sid = uploaded["session_id"]
    resume_text = uploaded["resumeText"]

    profile = diagnose(raw, token, sid, resume_text)["resumeProfile"]

    parsed = authed_post(
        raw, token, "/api/wf03/jd",
        {"jdText": JD_TEXT, "session_id": sid},
    )
    assert parsed.status_code == 200
    job_profile = parsed.json["jobProfile"]
    job_profile["user_confirmed"] = True

    matched = authed_post(
        raw, token, "/api/wf03/match",
        {"resumeText": resume_text, "jobProfile": job_profile, "session_id": sid},
    )
    assert matched.status_code == 200
    gaps = [
        {"id": g["id"], "type": g["type"], "text": g["text"], "status": g["status"]}
        for g in matched.json["requirements"]
        if g["status"] in ("missing", "weak")
    ]

    started = authed_post(
        raw, token, "/api/wf04/start",
        {
            "jobProfile": job_profile,
            "resumeProfile": profile,
            "matchGaps": gaps,
            "session_id": sid,
        },
    )
    assert started.status_code == 200
    assert started.json["firstQuestion"]

    streamed = authed_post(
        raw, token, "/api/wf04/stream",
        {
            "session_id": sid,
            "answer_text": "我用 Python 开发数据分析平台，日处理 100 万条记录，性能提升 40%。",
        },
    )
    assert streamed.status_code == 200
    assert "text/event-stream" in streamed.content_type
    data = streamed.get_data(as_text=True)
    assert "data:" in data
    assert '"type": "fragment"' in data
    assert '"type": "done"' in data
    assert '"done": true' in data
    # every SSE event must be delimited by blank line
    assert data.endswith("\n\n")


# ---------------------------------------------------------------- #
# Resume rewrite (optimize + apply)
# ---------------------------------------------------------------- #

def test_optimizer_rule_fallback_without_model():
    suggestion = {
        "id": "suggestion-1",
        "severity": "P1",
        "issue": "项目成果描述不够具体。",
        "suggestion": "建议补充可验证的项目成果描述。",
    }
    result = optimizer.rewrite_suggestion(suggestion, resume_profile={}, model_router=None)
    assert result["pending_confirm"] is True
    assert result["basis"] == "rule"
    assert result["candidate"]
    assert result["suggestion_id"] == "suggestion-1"


def test_wf02_optimize_rule_fallback_and_apply(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    uploaded = upload_resume(raw, token)
    sid = uploaded["session_id"]
    diagnose(raw, token, sid, uploaded["resumeText"])

    optimized = authed_post(
        raw, token, "/api/wf02/optimize",
        {"session_id": sid, "suggestion_id": "suggestion-1"},
    )
    assert optimized.status_code == 200
    body = optimized.json
    assert body["pending_confirm"] is True
    assert body["basis"] == "rule"
    assert body["candidate"]
    assert body["suggestion_id"]

    applied = authed_post(
        raw, token, "/api/wf02/apply-rewrite",
        {
            "session_id": sid,
            "suggestion_id": body["suggestion_id"],
            "issue": "项目成果描述不够具体。",
            "candidate_text": body["candidate"],
        },
    )
    assert applied.status_code == 201
    assert applied.json["status"] == "APPLIED"
    assert applied.json["rewrite"]["status"] == "applied"

    rows = database.list_rewrites(sid)
    assert len(rows) == 1
    assert rows[0]["status"] == "applied"
    assert rows[0]["candidate_text"] == body["candidate"]


def test_wf02_optimize_requires_diagnosis(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    uploaded = upload_resume(raw, token)
    sid = uploaded["session_id"]

    optimized = authed_post(
        raw, token, "/api/wf02/optimize",
        {"session_id": sid, "suggestion_id": "suggestion-1"},
    )
    assert optimized.status_code == 422
    assert optimized.json["error"] == "diagnosis_required"


# ---------------------------------------------------------------- #
# Vercel routing coverage
# ---------------------------------------------------------------- #

def test_vercel_routes_cover_phase4_endpoints():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    routes = {item["source"]: item["destination"] for item in config["rewrites"]}
    expected = {
        "/api/wf04/stream": "/api?_route=wf04/stream",
        "/api/wf02/optimize": "/api?_route=wf02/optimize",
        "/api/wf02/apply-rewrite": "/api?_route=wf02/apply-rewrite",
    }
    for source, destination in expected.items():
        assert routes[source] == destination, source


# ---------------------------------------------------------------- #
# 打字对话状态机：追问回答后自动进入下一主问题
# ---------------------------------------------------------------- #

def _parse_sse_done(data):
    done = None
    for block in data.split("\n\n"):
        line = None
        for l in block.splitlines():
            if l.startswith("data: "):
                line = l[len("data: "):]
        if not line:
            continue
        ev = json.loads(line)
        if ev.get("type") == "done":
            done = ev
    assert done is not None, "missing done event"
    return done


def test_wf04_stream_advances_to_next_question_after_followup(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    uploaded = upload_resume(raw, token)
    sid = uploaded["session_id"]
    resume_text = uploaded["resumeText"]
    profile = diagnose(raw, token, sid, resume_text)["resumeProfile"]

    parsed = authed_post(raw, token, "/api/wf03/jd", {"jdText": JD_TEXT, "session_id": sid})
    assert parsed.status_code == 200
    job_profile = parsed.json["jobProfile"]
    job_profile["user_confirmed"] = True
    matched = authed_post(
        raw, token, "/api/wf03/match",
        {"resumeText": resume_text, "jobProfile": job_profile, "session_id": sid},
    )
    assert matched.status_code == 200
    gaps = [
        {"id": g["id"], "type": g["type"], "text": g["text"], "status": g["status"]}
        for g in matched.json["requirements"]
        if g["status"] in ("missing", "weak")
    ]

    started = authed_post(
        raw, token, "/api/wf04/start",
        {"jobProfile": job_profile, "resumeProfile": profile,
         "matchGaps": gaps, "session_id": sid},
    )
    assert started.status_code == 200
    assert started.json["firstQuestion"]

    # 主回答：缺少结果/量化 → 应生成追问，且不进入下一题
    vague = "我负责后端开发，使用 Python 和 Flask 完成接口，遇到问题就修复。"
    streamed = authed_post(
        raw, token, "/api/wf04/stream",
        {"session_id": sid, "answer_text": vague},
    )
    assert streamed.status_code == 200
    done1 = _parse_sse_done(streamed.get_data(as_text=True))
    assert done1["followUp"] is not None, "vague answer should produce a follow-up"
    assert done1["nextQuestion"] is None, "main answer with follow-up must not advance"
    assert done1["evaluation"] is not None
    assert done1["evaluation"]["weaknesses"]

    # 追问回答：补充量化结果 → 记录追问并自动进入下一主问题
    followup_answer = (
        "结果：接口上线后响应时间从 800ms 降到 200ms，性能提升 75%，日处理 100 万条记录。"
    )
    streamed2 = authed_post(
        raw, token, "/api/wf04/stream",
        {"session_id": sid, "answer_text": followup_answer},
    )
    assert streamed2.status_code == 200
    done2 = _parse_sse_done(streamed2.get_data(as_text=True))
    assert done2["followUp"] is None
    assert done2["nextQuestion"] is not None
    assert done2["nextQuestion"].get("question")
    assert done2["nextQuestion"].get("done") is False
    assert done2["nextQuestion"].get("adaptive") is True
    assert done2["nextQuestion"].get("basis")
    assert done2["nextQuestion"]["basis"] in followup_answer
    assert done2["nextQuestion"]["basis"] in done2["nextQuestion"]["question"]
    assert done2["evaluation"] is not None


# ---------------------------------------------------------------- #
# 低 ASR 置信度：不得推进状态机（P0）
# ---------------------------------------------------------------- #

def _start_minimal(raw, token, sid, gaps=None):
    started = authed_post(
        raw, token, "/api/wf04/start",
        {
            "jobProfile": {"title": "后端开发工程师", "requirements": []},
            "resumeProfile": {"score_R": 70.0},
            "matchGaps": gaps if gaps is not None else [
                {"id": "G1", "type": "hard", "text": "接口性能优化", "status": "weak"},
                {"id": "G2", "type": "responsibility", "text": "故障复盘", "status": "weak"},
            ],
            "session_id": sid,
        },
    )
    assert started.status_code == 200
    return started.json


def test_wf04_stream_low_confidence_does_not_advance_state_machine(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    sid = "iv_lowconf_" + uuid.uuid4().hex[:8]
    _start_minimal(raw, token, sid)

    streamed = authed_post(
        raw, token, "/api/wf04/stream",
        {"session_id": sid, "answer_text": "语音转写结果，置信度偏低。", "asr_confidence": 0.4},
    )
    assert streamed.status_code == 200
    done = _parse_sse_done(streamed.get_data(as_text=True))
    assert done["needs_confirmation"] is True
    assert done["nextQuestion"] is None
    assert done["followUp"] is None

    _state, payload = database.load_session(sid)
    assert payload["turns"] == [], "低置信度不得记录轮次"
    assert payload["current_main"] == 1, "低置信度不得推进主问题"


def test_wf04_stream_low_confidence_keeps_pending_followup(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    sid = "iv_lowconf_fu_" + uuid.uuid4().hex[:8]
    _start_minimal(raw, token, sid)

    vague = "我负责后端开发，使用 Python 和 Flask 完成接口，遇到问题就修复。"
    first = authed_post(
        raw, token, "/api/wf04/stream", {"session_id": sid, "answer_text": vague}
    )
    done1 = _parse_sse_done(first.get_data(as_text=True))
    assert done1["followUp"] is not None
    assert done1["nextQuestion"] is None

    _state, before = database.load_session(sid)
    turns_before = len(before["turns"])
    pending_before = before["_current_followup"]
    assert pending_before

    low = authed_post(
        raw, token, "/api/wf04/stream",
        {"session_id": sid, "answer_text": "语音转写结果。", "asr_confidence": 0.3},
    )
    done2 = _parse_sse_done(low.get_data(as_text=True))
    assert done2["needs_confirmation"] is True
    assert done2["nextQuestion"] is None

    _state, after = database.load_session(sid)
    assert len(after["turns"]) == turns_before, "低置信度不得消费追问回答"
    assert after["_current_followup"] == pending_before

    # 低置信度之后，正常回答仍被当作追问回答消费，并推进到下一主问题
    good = (
        "结果：接口上线后响应时间从 800ms 降到 200ms，性能提升 75%，日处理 100 万条记录。"
    )
    resumed = authed_post(
        raw, token, "/api/wf04/stream", {"session_id": sid, "answer_text": good}
    )
    done3 = _parse_sse_done(resumed.get_data(as_text=True))
    assert done3["nextQuestion"] is not None
    assert done3["nextQuestion"]["adaptive"] is True


# ---------------------------------------------------------------- #
# F3 输入边界
# ---------------------------------------------------------------- #

def test_wf04_answer_rejects_oversized_answer(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    sid = "iv_big_" + uuid.uuid4().hex[:8]
    _start_minimal(raw, token, sid)

    response = authed_post(
        raw, token, "/api/wf04/answer",
        {"session_id": sid, "answer_text": "答" * 4001},
    )
    assert response.status_code == 422
    assert response.json["error"] == "answer_too_long"


def test_wf04_answer_rejects_non_numeric_asr_confidence(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)
    sid = "iv_badconf_" + uuid.uuid4().hex[:8]
    _start_minimal(raw, token, sid)

    response = authed_post(
        raw, token, "/api/wf04/answer",
        {"session_id": sid, "answer_text": "正常回答内容。", "asr_confidence": "high"},
    )
    assert response.status_code == 422
    assert response.json["error"] == "invalid_asr_confidence"


def test_wf04_start_rejects_non_object_match_gaps(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)

    response = authed_post(
        raw, token, "/api/wf04/start",
        {
            "jobProfile": {"title": "后端", "requirements": []},
            "matchGaps": ["不是对象"],
            "session_id": "iv_badgap_" + uuid.uuid4().hex[:8],
        },
    )
    assert response.status_code == 422
    assert response.json["error"] == "invalid_match_gaps"


def test_wf04_start_rejects_oversized_match_gaps(monkeypatch):
    raw = raw_client(monkeypatch)
    token = issue_consent(raw)

    response = authed_post(
        raw, token, "/api/wf04/start",
        {
            "jobProfile": {"title": "后端", "requirements": []},
            "matchGaps": [
                {"id": "G%d" % i, "type": "hard", "text": "缺口%d" % i, "status": "weak"}
                for i in range(21)
            ],
            "session_id": "iv_manygap_" + uuid.uuid4().hex[:8],
        },
    )
    assert response.status_code == 422
    assert response.json["error"] == "invalid_match_gaps"
