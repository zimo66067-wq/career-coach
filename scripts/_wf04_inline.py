
import sys, json
from pathlib import Path
sys.path.insert(0, "tools")
from interview_engine import InterviewEngine

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures-synthetic"

# 加载 fixture 数据
with open(FIXTURES / "jobs" / "job-01-swe.expected.json", encoding="utf-8") as f:
    job_profile = json.load(f)
with open(FIXTURES / "resumes" / "resume-01-swe.expected.json", encoding="utf-8") as f:
    resume_profile = json.load(f)

# 从 WF-03 匹配结果中提取缺口
match_gaps = []
try:
    with open("/tmp/wf03_match.json", encoding="utf-8") as f:
        match = json.load(f)
    for item in match.get("weak", []):
        match_gaps.append({"id": item.get("id",""), "type": "soft", "text": item.get("text",""), "status": "weak"})
    for item in match.get("missing", []):
        match_gaps.append({"id": item.get("id",""), "type": "hard", "text": item.get("text",""), "status": "missing"})
except Exception:
    pass

engine = InterviewEngine()
session = engine.start(job_profile, resume_profile, match_gaps)

# 跑 3 轮问答
answers = [
    "我在实习时负责订单查询接口优化，通过加复合索引和Redis缓存，将响应时间从800ms降到220ms。",
    "团队讨论库存扣减方案时有分歧，我做了压测对比，最终常态用乐观锁、秒杀切分布式锁。",
    "学新技术我会先读官方文档Quickstart，跑通最小示例，再对照项目代码梳理调用链。之前学Go两周能独立写接口。"
]

for i, ans in enumerate(answers):
    q = engine.next_question(session)
    if q is None:
        break
    engine.submit_answer(session, ans)
    # 尝试追问回答
    fu = session["turns"][-1].get("follow_up") if session["turns"] else None
    if fu:
        engine.submit_followup_answer(session, "补充说明：已通过测试验证，指标符合预期。")

report = engine.end_session(session)
print(json.dumps(report, ensure_ascii=False, indent=2))
with open("/tmp/wf04_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
