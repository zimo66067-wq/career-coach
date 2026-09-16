# -*- coding: utf-8 -*-
"""phase4-http-smoke.py · Phase 4 的真实 HTTP 冒烟（起真进程 + 打真端口，不用 test_client）

存在的意义：`test_client()` 绕过 Werkzeug 的 WSGI 栈，验不出"路由注册/方法分派/错误
处理器/CORS 预检"这一层。所以门禁里必须有一次**真端口**的验证。

覆盖：Phase 4 新增三块（D9=A 面试抽取 / Gap Action Plan / 投递结果回流）+ 级联删除
+ 归属隔离 + 已下线路由仍 404 + 预检 + 同意门。

用法（仓库根目录）：
    .venv-audit/Scripts/python.exe scripts/phase4-http-smoke.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8791
BASE = "http://127.0.0.1:%d" % PORT

RESUME = open(os.path.join(ROOT, "tests", "fixtures-synthetic", "resumes",
                           "resume-01-swe.txt"), encoding="utf-8").read()
JD = open(os.path.join(ROOT, "tests", "fixtures-synthetic", "jobs",
                       "job-01-swe.txt"), encoding="utf-8").read()
ANSWER = (
    "我在实习期间独立负责了订单模块的接口重构，把平均响应时间从 900ms 压到 180ms。"
    "同时我推动前后端统一了错误码规范，上线之后线上报错率下降了 40%。"
)

PASSED, FAILED = [], []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
    else:
        FAILED.append("%s %s" % (label, detail))


def request(method, path, body=None, token=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Consent-Token"] = token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, {}


def wait_ready(proc):
    deadline = time.time() + 40
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            status, _ = request("GET", "/api/health")
            if status == 200:
                return True
        except Exception:  # noqa: BLE001 - 未就绪就继续等
            pass
        time.sleep(0.4)
    return False


def main():
    workdir = tempfile.mkdtemp(prefix="phase4-smoke-")
    env = dict(os.environ)
    env["RESUME_DB_PATH"] = os.path.join(workdir, "smoke.db")
    env["DUMATE_CONSENT_SECRET"] = "phase4-smoke-secret"
    env.pop("ZHIPU_API_KEY", None)
    env.pop("MODEL_PROVIDER", None)
    env.pop("DATABASE_URL", None)

    boot = (
        "import sys; sys.path.insert(0, %r);"
        "from api.index import app;"
        "app.run(host='127.0.0.1', port=%d, threaded=True, use_reloader=False)"
        % (ROOT, PORT)
    )
    log_path = os.path.join(workdir, "server.log")
    # 注意：不要把子进程 stdout 接到 PIPE 又不去读 —— 管道缓冲区写满后服务进程会
    # 直接阻塞在 write 上，表现为请求无故超时（第一版就踩了这个坑）。落文件最稳。
    log = open(log_path, "wb")
    proc = subprocess.Popen([sys.executable, "-c", boot], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        if not wait_ready(proc):
            print("server failed to start")
            log.flush()
            print(open(log_path, "rb").read().decode("utf-8", "replace")[-2000:])
            return 1

        # ---- 健康与迁移 -------------------------------------------------
        status, health = request("GET", "/api/health")
        check("health 200", status == 200, status)
        check("health.status ok", health.get("status") == "ok", health.get("status"))
        check("health.migrations 已报告", isinstance(health.get("migrations"), (dict, list)),
              health.get("migrations"))
        check("health 列出 actions", (health.get("workflows") or {}).get("actions") == "available")

        # ---- 已下线路由仍 404 ------------------------------------------
        for dead in ("/api/tasks", "/api/f2/match", "/api/assets/logo.svg"):
            status, _ = request("GET", dead)
            check("已下线路由 404 %s" % dead, status == 404, status)

        # ---- 同意门 -----------------------------------------------------
        status, _ = request("GET", "/api/profile")
        check("无同意令牌 428", status == 428, status)
        status, consent = request("POST", "/api/wf01/consent", {"accepted": True})
        check("consent 200", status == 200, status)
        token = consent["consent_token"]

        # ---- 预检 -------------------------------------------------------
        for path in ("/api/actions", "/api/actions/1", "/api/actions/1/start",
                     "/api/actions/1/complete", "/api/actions/1/outcome",
                     "/api/actions/1/drop", "/api/wf07/applications/1/outcome",
                     "/api/wf07/applications/1/outcomes"):
            status, _ = request("OPTIONS", path, token=token)
            check("预检 204 %s" % path, status == 204, status)

        # ---- 目标岗位 + 分析 -------------------------------------------
        status, job = request("POST", "/api/target-jobs", {"jdText": JD}, token)
        check("建岗位 201", status == 201, status)
        target_id = job["targetJob"]["id"]
        status, analysis = request("POST", "/api/target-jobs/%d/analyse" % target_id,
                                   {"resumeText": RESUME}, token)
        check("分析 200", status == 200, status)
        check("分析产出缺口", len(analysis.get("gaps") or []) > 0)
        status, decision = request("GET", "/api/target-jobs/%d/decision" % target_id, token=token)
        verdict = (decision.get("decision") or {}).get("decision")
        check("结论在三值内", verdict in ("APPLY", "STRETCH", "PASS"), verdict)

        # ---- Gap Action Plan -------------------------------------------
        status, plan = request("POST", "/api/actions", {"targetJobId": target_id}, token)
        check("铺开行动 201", status in (200, 201), status)
        check("铺开产出行动", plan["createdCount"] > 0, plan["createdCount"])
        check("行动带任务", all(item["task"].strip() for item in plan["created"]))
        check("行动带成果物", all(item["artifact"].strip() for item in plan["created"]))

        status, again = request("POST", "/api/actions", {"targetJobId": target_id}, token)
        check("重复铺开 200 且不新增", status == 200 and again["createdCount"] == 0,
              (status, again["createdCount"]))

        action_ids = [item["id"] for item in plan["created"]]
        gap_id = plan["created"][0]["gap_id"]
        status, listing = request("GET", "/api/actions", token=token)
        check("清单数量一致", listing["total"] == plan["createdCount"],
              (listing["total"], plan["createdCount"]))
        status, detail = request("GET", "/api/actions/%d" % action_ids[0], token=token)
        check("单条行动 200", status == 200 and detail["action"]["gap_priority"],
              detail.get("action", {}).get("gap_priority"))

        status, blocked = request("POST", "/api/actions/%d/outcome" % action_ids[1],
                                  {"outcome": "还没做就有结果了"}, token)
        check("未完成不给结果 422", status == 422 and blocked.get("error") == "action_not_done",
              (status, blocked.get("error")))

        status, started = request("POST", "/api/actions/%d/start" % action_ids[0], token=token)
        check("开始行动 doing", started["action"]["status"] == "doing",
              started.get("action", {}).get("status"))
        status, completed = request("POST", "/api/actions/%d/complete" % action_ids[0],
                                    {"artifact": "一页含 3 个量化数字的项目说明"}, token)
        check("完成行动 done", completed["action"]["status"] == "done",
              completed.get("action", {}).get("status"))
        status, recorded = request("POST", "/api/actions/%d/outcome" % action_ids[0],
                                   {"outcome": "改完之后能讲出两个数字了。"}, token)
        check("记录行动结果", recorded["action"]["outcome"] == "改完之后能讲出两个数字了。",
              recorded.get("action", {}).get("outcome"))

        status, dropped = request("POST", "/api/actions/%d/drop" % action_ids[1], token=token)
        check("放弃行动 dropped", dropped["action"]["status"] == "dropped",
              dropped.get("action", {}).get("status"))
        status, _ = request("DELETE", "/api/actions/%d" % action_ids[2], token=token)
        check("删除行动 200", status == 200, status)
        status, _ = request("GET", "/api/actions/%d" % action_ids[2], token=token)
        check("删后 404", status == 404, status)

        status, bad = request("POST", "/api/actions", {}, token)
        check("缺 targetJobId/gapId 422", status == 422 and bad.get("error") == "invalid_request",
              (status, bad.get("error")))

        # ---- 归属隔离 ---------------------------------------------------
        status, other_consent = request("POST", "/api/wf01/consent", {"accepted": True})
        other_token = other_consent["consent_token"]
        status, other_list = request("GET", "/api/actions", token=other_token)
        check("他人清单为空", status == 200 and other_list["total"] == 0, other_list.get("total"))
        status, _ = request("GET", "/api/actions/%d" % action_ids[0], token=other_token)
        check("他人读行动 404", status == 404, status)
        status, _ = request("POST", "/api/actions/%d/start" % action_ids[0], token=other_token)
        check("他人动行动 404", status == 404, status)
        status, _ = request("POST", "/api/actions", {"gapId": gap_id}, other_token)
        check("他人借 gapId 开单 404", status == 404, status)

        # ---- D9=A 面试抽取 ---------------------------------------------
        session_id = "iv_smoke_phase4"
        status, _ = request("POST", "/api/wf04/start", {"session_id": session_id}, token)
        check("面试开始 200", status == 200, status)
        status, _ = request("POST", "/api/wf04/answer",
                            {"session_id": session_id, "answer_text": ANSWER,
                             "asr_confidence": None}, token)
        check("面试答题 200", status == 200, status)
        status, ended = request("POST", "/api/wf04/end",
                                {"session_id": session_id, "targetJobId": target_id}, token)
        check("面试结束 200", status == 200, status)
        extracted = ended.get("candidateEvidence") or {}
        check("结束后抽取候选", extracted.get("created", 0) >= 1, extracted)
        check("无模型时如实降级", extracted.get("degraded") is True, extracted.get("degraded"))

        status, profile = request("GET", "/api/profile", token=token)
        interview_pending = [item for item in profile["pending"]
                             if item["source_type"] == "interview"]
        check("面试候选全为 pending", len(interview_pending) >= 1
              and all(item["status"] == "pending" and item["user_confirmed"] == 0
                      for item in interview_pending), len(interview_pending))

        # ---- 投递结果回流 ----------------------------------------------
        status, created = request("POST", "/api/wf07/applications",
                                  {"session_id": session_id, "company": "示例科技",
                                   "position": "后端开发工程师",
                                   "cover_letter": "尊敬的招聘负责人：\n\n希望加入贵司。"}, token)
        check("建申请 201", status == 201, status)
        app_id = created["application"]["id"]

        status, first = request("POST", "/api/wf07/applications/%d/outcome" % app_id,
                                {"outcome": "interview", "note": "约了下周三一面。"}, token)
        check("结果推进状态", first["statusApplied"] is True
              and first["application"]["status"] == "interview", first.get("statusApplied"))
        check("结果写反向证据 pending",
              first["evidenceCreated"] and first["evidence"]["status"] == "pending",
              first.get("evidence"))
        check("反向证据来源正确",
              first["evidence"]["source_type"] == "application_outcome",
              first["evidence"].get("source_type"))

        status, second = request("POST", "/api/wf07/applications/%d/outcome" % app_id,
                                 {"outcome": "offer"}, token)
        check("非法推进如实回报", second["statusApplied"] is True
              and second["application"]["status"] == "offer", second.get("statusApplied"))
        status, back = request("POST", "/api/wf07/applications/%d/outcome" % app_id,
                               {"outcome": "interview"}, token)
        check("倒流被拒但结果留档",
              back["statusApplied"] is False and back["application"]["status"] == "offer"
              and back["outcome"]["outcome"] == "interview", back.get("statusApplied"))

        status, outcomes = request("GET", "/api/wf07/applications/%d/outcomes" % app_id, token=token)
        check("结果列表三条", len(outcomes["outcomes"]) == 3, len(outcomes.get("outcomes") or []))
        status, _ = request("GET", "/api/wf07/applications/%d/outcomes" % app_id, token=other_token)
        check("他人读结果 404", status == 404, status)
        status, _ = request("POST", "/api/wf07/applications/%d/outcome" % app_id,
                            {"outcome": "offer"}, other_token)
        check("他人写结果 404", status == 404, status)

        # ---- 级联删除 ---------------------------------------------------
        status, _ = request("DELETE", "/api/target-jobs/%d" % target_id, token=token)
        check("删岗位 200", status == 200, status)
        status, after = request("GET", "/api/actions", token=token)
        check("删岗位后行动一并消失", after["total"] == 0, after.get("total"))

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        if FAILED:
            print("--- server.log (tail) ---")
            print(open(log_path, "rb").read().decode("utf-8", "replace")[-1500:])
        shutil.rmtree(workdir, ignore_errors=True)

    print("passed %d / failed %d" % (len(PASSED), len(FAILED)))
    for item in FAILED:
        print("  FAIL %s" % item)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
