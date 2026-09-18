"""Generated user-facing text must be bounded and grounded before model labeling."""
import json

from services import apply_service
from repositories import database
from domain import optimizer
from providers import model as model_provider


QUOTE = "负责订单接口开发并将平均响应从八百毫秒降低到两百毫秒"


class Router:
    def __init__(self, output):
        self.output = output

    def call(self, *_args, **_kwargs):
        return {"status": "success", "output": self.output}


def _profile():
    return {
        "subscores": {
            "achievement_evidence": {
                "source_spans": [{"doc": "resume", "quote": QUOTE, "start": 0, "end": len(QUOTE)}]
            }
        },
        "suggestions": [],
    }


def _saved_session(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RESUME_DB_PATH", str(tmp_path / "generation.db"))
    sid = "grounded_generation"
    database.save_resume(sid, "", "", "resume.txt", ".txt", len(QUOTE), QUOTE)
    database.save_diagnosis(sid, 80, "model", "", "trace", json.dumps(_profile(), ensure_ascii=False))
    return sid


def test_cover_letter_accepts_grounded_structured_model_output(tmp_path, monkeypatch):
    sid = _saved_session(tmp_path, monkeypatch)
    output = {
        "candidate": "贵公司后端开发工程师岗位与我的经历匹配：我负责订单接口开发并完成性能优化，希望进一步沟通。"
    }
    monkeypatch.setattr(model_provider, "build_model_router", lambda: Router(output))
    result = apply_service.generate_cover_letter(sid, "示例公司", "后端开发工程师")
    assert result["basis"] == "model"
    assert result["candidate"] == output["candidate"]


def test_cover_letter_relabels_ungrounded_model_text_as_rule(tmp_path, monkeypatch):
    sid = _saved_session(tmp_path, monkeypatch)
    monkeypatch.setattr(
        model_provider,
        "build_model_router",
        lambda: Router("示例公司后端开发工程师岗位非常适合我，我拥有十年团队管理经验和亿元项目成果。"),
    )
    result = apply_service.generate_cover_letter(sid, "示例公司", "后端开发工程师")
    assert result["basis"] == "rule"
    assert QUOTE in result["candidate"]


def test_resume_rewrite_rejects_unbounded_or_ungrounded_model_output():
    suggestion = {"id": "s1", "issue": "成果缺少量化", "suggestion": "补充性能数据"}
    ungrounded = optimizer.rewrite_suggestion(
        suggestion,
        resume_profile=_profile(),
        model_router=Router("我在完全不同的行业创造了未经材料支持的巨大营收增长。"),
    )
    assert ungrounded["basis"] == "rule"

    grounded = optimizer.rewrite_suggestion(
        suggestion,
        resume_profile=_profile(),
        model_router=Router({"candidate": "负责订单接口开发，并将平均响应从八百毫秒降低到两百毫秒。"}),
    )
    assert grounded["basis"] == "model"
