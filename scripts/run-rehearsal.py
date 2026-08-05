#!/usr/bin/env python3
"""run-rehearsal.py · 10 次自动化彩排（G9 前置证据）

在不依赖真实模型密钥的前提下，用 FakeRouter 走通
consent -> diagnose -> jd -> match -> interview -> ability -> delete
完整闭环 10 轮，输出每轮分步耗时与结果到
deliverables/wf-evidence-<date>/rehearsal-10x.json。

说明：这是"自动化彩排"证据（无阻断、可复现），不等同于 DuMate 平台/真机彩排。

用法:
  python scripts/run-rehearsal.py [--rounds 10]
"""
import argparse
import io
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DUMATE_CONSENT_SECRET", "rehearsal-consent-secret")

import api.index as api_module  # noqa: E402
from tools.database import delete_session_data  # noqa: E402


RESUME = "项目经历：负责接口开发并完成上线验证，持续跟进问题闭环，响应时间从 800ms 降至 220ms。"
JD_TEXT = (
    "岗位职责：负责后端 API 开发与接口文档维护。\n"
    "任职要求：熟悉 Python、Flask 与 SQL；有项目交付经验。\n"
    "加分项：熟悉 Redis。\n"
    "技术栈：Python、Flask、SQLite。"
)


def valid_profile(resume=RESUME):
    span = {"doc": "resume", "quote": resume, "start": 0, "end": len(resume)}
    subscores = {}
    for key, score in {
        "structure": 80, "clarity": 75, "achievement_evidence": 70,
        "skill_evidence": 70, "ats_readability": 85,
    }.items():
        subscores[key] = {"score": score, "rationale": "该项依据简历原文进行判断。", "source_spans": [span]}
    return {
        "version": "1.0", "pii_removed": True, "subscores": subscores,
        "suggestions": [{
            "id": "suggestion-1", "severity": "P1",
            "issue": "项目成果描述不够具体。",
            "suggestion": "建议补充可验证的项目成果描述。",
            "source_spans": [span],
        }],
    }


class FakeRouter:
    def call(self, *_args, **_kwargs):
        return {
            "status": "success",
            "output": valid_profile(),
            "trace_id": "rehearsal_model_trace",
            "degraded": False,
        }


def run_round(client, session_id):
    steps = []

    def step(name, fn):
        t0 = time.time()
        try:
            status, body = fn()
            ok = status == 200
        except Exception as exc:  # noqa: BLE001
            ok = False
            body = {"error": "exception", "message": str(exc)}
        steps.append({
            "step": name,
            "passed": ok,
            "status": body.get("error") if not ok else status,
            "duration_ms": int((time.time() - t0) * 1000),
        })
        return ok

    ok = True
    ok &= step("consent", lambda: (200, {"ok": True}))  # token obtained before round
    ok &= step("diagnose", lambda: (
        client.post("/api/wf02/diagnose",
                    json={"resumeText": RESUME, "session_id": session_id}).status_code,
        {}
    ))
    parsed = client.post("/api/wf03/jd", json={"jdText": JD_TEXT, "session_id": session_id})
    ok &= step("jd_parse", lambda: (parsed.status_code, {}))
    if parsed.status_code == 200:
        job_profile = parsed.json["jobProfile"]
        job_profile["user_confirmed"] = True
        ok &= step("match", lambda: (
            client.post("/api/wf03/match",
                        json={"resumeText": RESUME, "jobProfile": job_profile,
                              "session_id": session_id}).status_code,
            {}
        ))
    ok &= step("interview_start", lambda: (
        client.post("/api/wf04/start",
                    json={"session_id": session_id, "jobProfile": {},
                          "resumeProfile": {}, "matchGaps": []}).status_code,
        {}
    ))
    answer = ("我在实习中负责订单接口开发，背景是接口响应慢。我的任务是优化性能，我加了索引并引入缓存，"
              "最终平均响应从 800ms 降到 220ms，提升了 72%。")
    ok &= step("interview_answer", lambda: (
        client.post("/api/wf04/answer",
                    json={"session_id": session_id, "answer_text": answer,
                          "asr_confidence": None}).status_code,
        {}
    ))
    ok &= step("interview_end", lambda: (
        client.post("/api/wf04/end", json={"session_id": session_id}).status_code,
        {}
    ))
    ok &= step("ability", lambda: (
        client.post("/api/wf05/ability", json={"session_id": session_id}).status_code,
        {}
    ))
    ok &= step("delete", lambda: (
        client.post("/api/wf06/delete", json={"session_id": session_id}).status_code,
        {}
    ))
    delete_session_data(session_id)
    return steps, ok


def main():
    ap = argparse.ArgumentParser(description="10 次自动化彩排")
    ap.add_argument("--rounds", type=int, default=10)
    args = ap.parse_args()

    api_module.build_model_router = lambda: FakeRouter()
    api_module.app.config.update(TESTING=True)
    client = api_module.app.test_client()

    rounds = []
    total_ok = True
    for i in range(1, args.rounds + 1):
        consent = client.post("/api/wf01/consent", json={"accepted": True})
        if consent.status_code != 200:
            rounds.append({"round": i, "passed": False, "steps": [], "error": "consent failed"})
            total_ok = False
            continue
        token = consent.json["consent_token"]
        wrapped = _Consented(client, token)
        session_id = "rehearsal_%02d" % i
        steps, ok = run_round(wrapped, session_id)
        rounds.append({"round": i, "passed": ok, "steps": steps})
        total_ok = total_ok and ok

    report = {
        "event": "automated_rehearsal",
        "date": datetime.now().isoformat(),
        "rounds_total": args.rounds,
        "rounds_passed": sum(1 for r in rounds if r["passed"]),
        "all_passed": total_ok,
        "note": "自动化彩排（FakeRouter，无真实模型密钥）；DuMate 平台与真机彩排仍需另行执行。",
        "rounds": rounds,
    }
    out_dir = ROOT / "deliverables" / ("wf-evidence-%s" % datetime.now().strftime("%Y%m%d"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rehearsal-10x.json"
    with io.open(str(out_path), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("自动化彩排完成: %d/%d 轮通过" % (report["rounds_passed"], args.rounds))
    print("证据: %s" % out_path)
    return 0 if total_ok else 1


class _Consented:
    """Attach X-Consent-Token to every request."""

    def __init__(self, raw, token):
        self._raw = raw
        self._token = token

    def __getattr__(self, name):
        method = getattr(self._raw, name)
        if name not in {"get", "post", "open", "delete", "put", "patch"}:
            return method

        def wrap(*args, **kwargs):
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.setdefault("X-Consent-Token", self._token)
            return method(*args, headers=headers, **kwargs)

        return wrap


if __name__ == "__main__":
    raise SystemExit(main())
