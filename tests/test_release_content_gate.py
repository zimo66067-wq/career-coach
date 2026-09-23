# -*- coding: utf-8 -*-
"""五个发布验收回归用例（2026-09-23），全部为离线合成测试。

运行：python -m pytest tests/test_release_content_gate.py -v

TC01：真实结构化 fixture 输入 -> 可解析、符合 Schema、无占位符。
TC02：HTTP success 但内容拒答 -> invalid，成功数为零，进程失败。
TC03：空输出（含空容器）/低于长度边界 -> 拒绝；恰好边界 -> 通过。
TC04：输入缺失 -> 不调用模型，计 skipped，进程失败。
TC05：正常合成输出 -> 成功计数、调用数、JSONL 记录与退出码一致。

这里只验证复测工具能否正确判定；不证明真实模型质量，不替代五名真人验收。
所有报告落 pytest 临时目录，不覆盖历史证据，不读取真实凭据或访问网络。
"""
import importlib.util
import json
from pathlib import Path
import socket

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def gate(monkeypatch, tmp_path):
    # 只为通过脚本的导入期配置检查；绝不会构造真实模型客户端。
    monkeypatch.setenv("ZHIPU_API_KEY", "placeholder-offline-not-a-real-key")
    for name in ("QIANFAN_ACCESS_KEY", "QIANFAN_SECRET_KEY", "QIANFAN_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("offline acceptance tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    spec = importlib.util.spec_from_file_location(
        "release_content_gate_under_test", ROOT / "scripts/p0-03-real-model-test.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return module


def run_case(gate, monkeypatch, outputs, inputs=None, repeat=1):
    calls = []

    class OfflineRouter:
        def __init__(self, **kwargs):
            pass

        def call(self, task, user_input, context):
            calls.append((task, user_input, context))
            return {"status": "success", "model": "offline-test-double",
                    "degraded": False, "latency_ms": 1, "output": outputs[task]}

    monkeypatch.setattr(gate, "ROUTER_CLASS", OfflineRouter)
    monkeypatch.setattr(gate, "TASK_TYPES", list(outputs))
    monkeypatch.setattr(gate, "REPEAT", repeat)
    monkeypatch.setattr(gate, "TEST_INPUTS", inputs if inputs is not None else {
        task: "离线合成输入：仅验证判据，不代表真实模型验收。" for task in outputs})
    exit_code = gate.main()
    folder = Path(gate.OUTPUT_DIR)
    report = json.loads(next(folder.glob("p0-03-report-*.json")).read_text(encoding="utf-8"))
    records = [json.loads(line) for line in
               next(folder.glob("p0-03-run-*.jsonl")).read_text(encoding="utf-8").splitlines()]
    return exit_code, report, records, calls


def test_tc01_structured_inputs_are_schema_valid_and_grounded(gate):
    """前置：仓库样本可读；输入：两种长文任务；期望：真实结构而非占位符。"""
    assert gate.INPUT_BUILD_ERROR is None
    report_input, match_input = gate._build_structured_inputs()
    resume_json, resume_text = report_input.removeprefix("ResumeProfile: ").split("\n简历文本: ", 1)
    job_json, remainder = match_input.removeprefix("JobProfile: ").split("\n四态结果: ", 1)
    match_json, second_resume_json = remainder.split("\nResumeProfile: ", 1)
    for stem, payload in (("resume", resume_json), ("job", job_json)):
        schema = json.loads((ROOT / "contracts" / (stem + "-profile.schema.json")).read_text(encoding="utf-8"))
        jsonschema.validate(json.loads(payload), schema)
    assert json.loads(resume_json) == json.loads(second_resume_json)
    assert resume_text == gate._read_fixture("resumes", "resume-01-swe.txt")
    from services.match_service import match_job_profile
    assert json.loads(match_json) == match_job_profile(resume_text, json.loads(job_json))
    assert "同上简历文本" not in report_input
    assert "简历同上，JD同上" not in match_input


def test_tc02_http_success_with_refusal_is_invalid(gate, monkeypatch):
    """输入：超过长度下限的拒答；期望：不得以 HTTP 成功或篇幅长判绿。"""
    output = "由于您没有提供具体的简历内容，我无法生成针对性报告。" + "补充说明。" * 100
    code, report, records, calls = run_case(gate, monkeypatch, {"resume_report": output}, repeat=3)
    assert code == 1
    assert len(calls) == len(records) == 3
    assert report["summary"]["success_rate"] == "0/3"
    assert report["summary"]["content_invalid_count"] == 3
    assert report["summary"]["failed_count"] == 0  # HTTP 层成功、内容层失败。
    assert all(not row["content_ok"] and row["content_reason"].startswith("refusal:") for row in records)


def test_tc03_empty_outputs_and_length_boundaries(gate):
    """输入：空文本/空容器/边界长度；期望：空结构也不是有效内容。"""
    wrongly_accepted = [repr(value) for value in (None, "", " \n\t", {}, [])
                        if gate.judge_output("resume_diagnosis", value)[0]]
    for task, floor in gate.MIN_TEXT_LEN.items():
        assert gate.judge_output(task, "测" * (floor - 1))[0] is False
        assert gate.judge_output(task, "测" * floor) == (True, None)
        assert gate.judge_output(task, "测" * (floor + 1)) == (True, None)
    assert not wrongly_accepted, "empty outputs accepted as valid: " + ", ".join(wrongly_accepted)


def test_tc04_missing_input_skips_without_false_success(gate, monkeypatch):
    """输入：构造失败；期望：零模型调用、三次跳过、退出码 1。"""
    monkeypatch.setattr(gate, "INPUT_BUILD_ERROR", "synthetic fixture unavailable")
    code, report, records, calls = run_case(
        gate, monkeypatch, {"resume_report": "must never be used"},
        inputs={"resume_report": None}, repeat=3)
    assert code == 1 and calls == [] and records == []
    assert report["summary"]["skipped_count"] == 3
    assert report["summary"]["success_rate"] == "0/3"
    assert report["meta"]["actual_calls"] == 0
    assert report["meta"]["input_build_error"] == "synthetic fixture unavailable"


def test_tc05_valid_synthetic_results_have_consistent_evidence(gate, monkeypatch):
    """正向控制：判据不能一概拒绝；只证实统计正确，不证明生成内容质量。"""
    outputs = {
        "resume_diagnosis": json.loads(gate._read_fixture("resumes", "resume-01-swe.expected.json")),
        "resume_report": "离线合成断言样本：项目经历具备技术栈依据，建议补充本人职责与可验证的交付记录。" * 15,
        "jd_match_explain": "离线合成断言样本：匹配基于已提供证据，未确认的技能保持未知，不虚构经历。" * 8,
    }
    code, report, records, calls = run_case(gate, monkeypatch, outputs)
    assert code == 0
    assert len(calls) == len(records) == report["meta"]["actual_calls"] == 3
    assert report["summary"]["success_rate"] == "3/3"
    assert report["summary"]["content_invalid_count"] == report["summary"]["skipped_count"] == 0
    assert all(row["content_ok"] and row["content_reason"] is None for row in records)
    assert all(item["success"] == 1 for item in report["per_task"].values())
