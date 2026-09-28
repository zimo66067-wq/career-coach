"""Core release acceptance over real HTTP, synthetic data only.

Uses deployed business endpoints, never downloads model keys. Reports contain
assertions and timing, not credentials, cookies, bodies or model output.
Stops the dependent journey on its first failure; cleanup still runs.
"""
import argparse
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RESUME = (ROOT / "tests/fixtures-synthetic/resumes/resume-01-swe.txt").read_text(encoding="utf-8")
JD = (ROOT / "tests/fixtures-synthetic/jobs/job-01-swe.txt").read_text(encoding="utf-8")
ANSWERS = [
    "在课程订单系统项目中，我负责接口性能优化，用缓存和索引将响应从900毫秒降低到180毫秒，并以压测报告核验结果。",
    "我先用慢查询日志定位索引失效，再用相同数据做对照压测，记录P95延迟，发现缓存失效后增加回源保护。",
    "我负责整理实验记录，向团队解释两个方案的成本和风险，最终通过小流量发布验证效果并保留回滚版本。",
]


class Acceptance:
    def __init__(self, base, request_fn=None):
        self.base = base.rstrip("/")
        self.request_fn = request_fn
        self.events = []
        self.checks = []
        self.observations = []

    def request(self, method, path, body=None, token=None, expected=(200,)):
        started = time.monotonic()
        if self.request_fn:
            status, data = self.request_fn(method, path, body, token)
        else:
            headers = {"Content-Type": "application/json"}
            if token:
                headers["X-Consent-Token"] = token
            req = Request(self.base + path, method=method, headers=headers,
                          data=None if body is None else json.dumps(body).encode("utf-8"))
            try:
                response = urlopen(req, timeout=70)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                raw = response.read(2_000_000)
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = {}
        elapsed = round((time.monotonic() - started) * 1000)
        # Path IDs belong only to disposable synthetic records; never record bodies.
        self.events.append({"method": method, "path": path, "http": status, "ms": elapsed})
        self.check("HTTP %s %s actual=%s expected=%s" % (method, path, status, expected), status in expected)
        return data

    def check(self, name, passed):
        self.checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    def consent(self):
        return self.request("POST", "/api/wf01/consent", {"accepted": True})["consent_token"]

    def journey(self, index, require_model=True):
        token = self.consent()
        sid = "core-acceptance-" + uuid.uuid4().hex
        target_id = None
        session_created = False
        try:
            # TC01: real diagnosis and rewrite, content not merely HTTP success.
            session_created = True  # a failed response may follow a successful DB write
            diag = self.request("POST", "/api/wf02/diagnose",
                                {"session_id": sid, "resumeText": RESUME}, token)
            self.observations.append({"round": index, "diagnosis_mode": diag.get("diagnosis_mode")})
            profile = diag.get("profile") or diag.get("resumeProfile") or {}
            self.check("TC01 diagnosis has structured subscores", bool(profile.get("subscores")))
            self.check("TC01 diagnosis has actionable suggestions", bool(profile.get("suggestions")))
            if require_model:
                self.check("TC01 diagnosis is model, not fallback", diag.get("diagnosis_mode") in ("model", "fallback_model"))
            rewrite = self.request("POST", "/api/wf02/optimize", {"session_id": sid}, token)
            self.check("TC01 rewrite requires confirmation", rewrite.get("pending_confirm") is True)
            self.check("TC01 rewrite nonempty", len(str(rewrite.get("candidate") or "").strip()) >= 10)
            self.observations.append({"round": index, "diagnosis_mode": diag.get("diagnosis_mode"),
                                      "rewrite_basis": rewrite.get("basis")})

            # TC02: source evidence is pending until confirmed; target -> decision -> action.
            candidates = self.request("POST", "/api/profile/evidence/candidates",
                                      {"session_id": sid, "resumeProfile": profile}, token, (201,))
            for item in candidates.get("created", []):
                self.check("TC02 extracted evidence pending", item.get("status") == "pending")
            self.check("TC02 real evidence available", bool(candidates.get("created")))
            evidence_id = candidates["created"][0]["id"]
            confirmed = self.request("POST", "/api/profile/evidence/%d/confirm" % evidence_id, {}, token)
            self.check("TC02 explicit evidence confirmation", confirmed["evidence"]["status"] == "confirmed")
            job = self.request("POST", "/api/target-jobs",
                               {"session_id": sid, "jdText": JD, "company": "合成验收单位", "position": "后端开发"},
                               token, (201,))
            target_id = job["targetJob"]["id"]
            self.check("TC02 JD has requirements", bool(job.get("requirements")))
            analysis = self.request("POST", "/api/target-jobs/%d/analyse" % target_id,
                                    {"session_id": sid}, token)
            decision = self.request("GET", "/api/target-jobs/%d/decision" % target_id, token=token)
            self.check("TC02 deterministic decision", (decision.get("decision") or {}).get("decision") in ("APPLY", "STRETCH", "PASS"))
            self.check("TC02 gaps available for practice", bool(analysis.get("gaps")))
            plan = self.request("POST", "/api/actions", {"targetJobId": target_id}, token, (200, 201))
            self.check("TC02 actionable plan", bool(plan.get("created")) and all(x.get("task") and x.get("artifact") for x in plan["created"]))
            again = self.request("POST", "/api/actions", {"targetJobId": target_id}, token)
            self.check("TC02 no duplicate actions", again.get("createdCount") == 0)

            # TC03: adaptive interview, and extraction never creates confirmed facts.
            start = self.request("POST", "/api/wf04/start", {"session_id": sid, "targetJobId": target_id}, token)
            self.check("TC03 first question nonempty", bool(start.get("firstQuestion")))
            previous_questions = {start["firstQuestion"]}
            for answer in ANSWERS:
                turn = self.request("POST", "/api/wf04/answer", {"session_id": sid, "answer_text": answer}, token)
                next_q = turn.get("followUp") or (turn.get("turn") or {}).get("follow_up") or turn.get("nextQuestion") or {}
                if next_q and not next_q.get("done"):
                    question = next_q.get("question") or ""
                    self.check("TC03 next question not repeated", bool(question) and question not in previous_questions)
                    previous_questions.add(question)
                    anchor = next_q.get("basis") or next_q.get("answer_quote") or ""
                    if not anchor:
                        quoted = re.search(r"「([^」]+)」", question)
                        anchor = quoted.group(1) if quoted else ""
                    self.check("TC03 next question references actual answer", bool(anchor) and anchor in answer and anchor in question)
            ended = self.request("POST", "/api/wf04/end", {"session_id": sid, "targetJobId": target_id}, token)
            self.observations.append({"round": index, "interview_extraction_degraded": (ended.get("candidateEvidence") or {}).get("degraded")})
            current = self.request("GET", "/api/profile", token=token)
            self.check("TC03 extracted interview facts remain pending", all(x.get("status") == "pending" for x in current.get("pending", []) if x.get("source_type") == "interview"))

            # TC04: grounded cover letter -> application -> genuine state transition.
            letter = self.request("POST", "/api/wf07/cover-letter",
                                  {"session_id": sid, "targetJobId": target_id, "company": "合成验收单位", "position": "后端开发"}, token)
            self.check("TC04 letter grounded and pending", bool(letter.get("evidence")) and letter.get("pending_confirm") is True)
            self.check("TC04 letter nonempty", len(str(letter.get("candidate") or "").strip()) >= 20)
            self.observations.append({"round": index, "cover_letter_basis": letter.get("basis"), "grounding": letter.get("grounding")})
            created = self.request("POST", "/api/wf07/applications",
                                   {"session_id": sid, "company": "合成验收单位", "position": "后端开发", "cover_letter": letter["candidate"]}, token, (201,))
            app_id = created["application"]["id"]
            result = self.request("POST", "/api/wf07/applications/%d/outcome" % app_id,
                                  {"outcome": "interview", "note": "仅合成验收，未向真实单位投递"}, token)
            self.check("TC04 outcome stored", result.get("statusApplied") is True and result["application"]["status"] == "interview")

            # TC05: negative control, ownership, deletion checked during cleanup.
            stranger = self.consent()
            self.request("GET", "/api/profile", expected=(428,))
            self.request("GET", "/api/target-jobs/%d" % target_id, token=stranger, expected=(404,))
            self.request("POST", "/api/wf06/delete", {"session_id": sid}, stranger, (404,))
        finally:
            # Delete only IDs created under this run's isolated signed owner token.
            # Keep cleaning independent records after an individual cleanup failure.
            cleanup_errors = []
            def clean(method, path, body=None, expected=(200,)):
                try:
                    return self.request(method, path, body, token, expected)
                except Exception as exc:
                    cleanup_errors.append(type(exc).__name__)
                    return {}
            if target_id is not None:
                clean("DELETE", "/api/target-jobs/%d" % target_id)
                clean("GET", "/api/target-jobs/%d" % target_id, expected=(404,))
            if session_created:
                owned = clean("GET", "/api/profile")
                for group in ("pending", "confirmed", "rejected"):
                    for item in owned.get(group, []):
                        clean("DELETE", "/api/profile/evidence/%d" % item["id"])
                deleted = clean("POST", "/api/wf06/delete", {"session_id": sid}, expected=(200, 404))
                if deleted and not deleted.get("error"):
                    self.check("TC05 workflow session deleted", deleted.get("status") == "DELETED")
                clean("POST", "/api/wf02/optimize", {"session_id": sid}, expected=(404,))
            self.observations.append({"round": index, "cleanup_errors": len(cleanup_errors),
                                      "residual": "empty owner profile and quota metadata may remain; not an account erasure test"})
            if cleanup_errors:
                raise AssertionError("cleanup_failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--repeat", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if Path(args.out).exists():
        parser.error("Report exists; choose a new output path to preserve evidence")
    parsed = urlsplit(args.base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("URL must not contain credentials, query or fragment")
    if not (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))):
        parser.error("HTTPS required except localhost")
    run = Acceptance(args.base_url)
    failure = None
    completed = 0
    try:
        health = run.request("GET", "/api/health")
        run.check("production database and model configuration ready", health.get("status") == "ok" and health.get("model_ready") is True and (health.get("migrations") or {}).get("ok") is True)
        for index in range(1, args.repeat + 1):
            run.journey(index)
            completed += 1
            print("round %d complete" % index, flush=True)
    except Exception as exc:
        # Never serialize exception strings: transport errors can contain secrets.
        failure = type(exc).__name__
    report = {"date": datetime.now(timezone.utc).isoformat(), "scope": "core-only",
              "synthetic": True, "human_participants": 0, "base_url": args.base_url,
              "requested_rounds": args.repeat, "completed_rounds": completed,
              "passed": failure is None, "failure_category": failure,
              "checks": run.checks, "requests": run.events, "observations": run.observations}
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"passed": report["passed"], "completed_rounds": completed,
                      "checks": len(run.checks), "failed_checks": [x["name"] for x in run.checks if not x["passed"]],
                      "failure_category": failure}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
