# -*- coding: utf-8 -*-
"""model_router.py · 统一模型调用路由层（P0-03）

用法:
  from tools.model_router import ModelRouter
  router = DuMateModelRouter()  # 子类实现 _try_call
  result = router.call("resume_diagnosis", user_input=clean_text)
  # result = {status, output, trace_id, model, latency_ms, error_type, degraded}

任务路由: resume_diagnosis | resume_report | jd_extract | jd_match_explain
         | interview_question | interview_review | seven_day_plan
降级链: 配置的主模型 -> 备用模型 -> 规则/BM25 降级
日志: trace_id + model + latency + status + error_type (不含原始内容，仅记输入摘要哈希)

冻结参数: 各任务的 temperature / max_tokens / timeout 在 MODEL_PARAMS 中冻结，不可运行时修改。
模型名称: 全部从环境变量读取，不硬编码。
"""
import hashlib
import json
import logging
import os
import string
import time
import random
from typing import Optional

# ------------------------------------------------------------------ #
# 任务到提示词的映射（冻结）
# ------------------------------------------------------------------ #
TASK_PROMPTS = {
    "resume_diagnosis": "prompts/resume/diagnose.md",
    "resume_report": "prompts/resume/report-deep.md",
    "jd_extract": "prompts/match/jd-extract.md",
    "jd_match_explain": "prompts/match/explain.md",
    "interview_question": "prompts/interview/interviewer.md",
    "interview_review": "prompts/interview/review.md",
    "seven_day_plan": "prompts/plan/seven-day.md",
}

# ------------------------------------------------------------------ #
# 冻结参数（temperature / max_tokens / timeout）
# ------------------------------------------------------------------ #
MODEL_PARAMS = {
    "resume_diagnosis":     {"temperature": 0.1, "max_tokens": 4096, "timeout": 30},
    "resume_report":        {"temperature": 0.3, "max_tokens": 4096, "timeout": 30},
    "jd_extract":           {"temperature": 0.1, "max_tokens": 2048, "timeout": 20},
    "jd_match_explain":     {"temperature": 0.3, "max_tokens": 2048, "timeout": 20},
    "interview_question":   {"temperature": 0.4, "max_tokens": 1024, "timeout": 15},
    "interview_review":     {"temperature": 0.3, "max_tokens": 4096, "timeout": 30},
    "seven_day_plan":       {"temperature": 0.2, "max_tokens": 2048, "timeout": 20},
}

# ------------------------------------------------------------------ #
# 降级返回的预制规则结果（标注 degraded=true）
# ------------------------------------------------------------------ #
DEGRADED_OUTPUTS = {
    "resume_diagnosis": {
        "note": "model_unavailable_degraded: rule-based skeleton, manual review required",
        "subscores": {
            "structure": None, "clarity": None,
            "achievement_evidence": None, "skill_evidence": None,
            "ats_readability": None,
        },
        "suggestions": [],
        "pii_removed": True,
    },
    "resume_report": {
        "note": "model_unavailable_degraded: report skeleton, manual review required",
        "sections": ["structure", "clarity", "achievement_evidence",
                     "skill_evidence", "ats_readability"],
    },
    "jd_extract": {
        "note": "model_unavailable_degraded: use tools/match_requirements.py text parsing",
        "requirements": [],
    },
    "jd_match_explain": {
        "note": "model_unavailable_degraded: BM25 fallback, UI must label simplified_match",
        "backend": "bm25",
    },
    "interview_question": {
        "note": "model_unavailable_degraded: question bank fallback",
        "question": "describe a project you led, including your role, actions, and quantifiable results",
        "targets": ["generic_behavioral"],
    },
    "interview_review": {
        "note": "model_unavailable_degraded: report skeleton, manual review required",
        "report": "## Interview Review (rule-degraded)\n\nmodel unavailable, skeleton:\n1. overall\n2. per-turn\n3. prep\n4. plan linkage\n",
    },
    "seven_day_plan": {
        "note": "model_unavailable_degraded: plan skeleton, manual review required",
        "plan": [
            {"day": i, "title": "TBD", "minutes": 35, "artifact": "TBD", "actions": []}
            for i in range(1, 8)
        ],
    },
}

logger = logging.getLogger("model_router")


def _gen_trace_id():
    """trace_id = 毫秒时间戳 + 8位随机串"""
    ts = str(int(time.time() * 1000))
    rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return "%s_%s" % (ts, rnd)


class ModelRouter:
    """抽象基类：统一模型调用入口。

    子类（如 DuMateModelRouter / QianfanModelRouter）必须实现 ``_try_call``。
    """

    def __init__(self, primary_model=None, fallback_model=None, enable_log=True):
        """初始化模型路由器。

        模型名称优先级: 参数传入 > 环境变量 PRIMARY_MODEL / FALLBACK_MODEL > None。
        """
        self.primary_model = (
            primary_model
            or os.environ.get("PRIMARY_MODEL")
            or os.environ.get("DUMATE_MODEL")
        )
        self.fallback_model = (
            fallback_model
            or os.environ.get("FALLBACK_MODEL")
            or os.environ.get("QIANFAN_MODEL")
        )
        self.enable_log = enable_log

    # ---- 公开接口 ---- #

    def call(self, task_type, user_input, context=None):
        """统一调用入口。

        Args:
            task_type: TASK_PROMPTS 中的键之一
            user_input: 用户输入文本（去标识化后）
            context: 可选上下文字典（如 resume_profile_json、previous_turns_json）

        Returns:
            dict: {status, output, trace_id, model, latency_ms, error_type, degraded}
            status: "success" | "degraded" | "failed"
        """
        trace_id = _gen_trace_id()
        input_hash = self._hash_input(user_input)

        if task_type not in TASK_PROMPTS:
            result = {
                "status": "failed", "output": None, "trace_id": trace_id,
                "model": None, "latency_ms": 0,
                "error_type": "unknown_task_type", "degraded": False,
            }
            self._log_call(trace_id, task_type, None, 0, "failed",
                           "unknown_task_type", input_hash)
            return result

        prompt = self._load_prompt(task_type)
        params = MODEL_PARAMS[task_type]
        input_summary = (user_input or "")[:200]

        # ---- 主模型 ---- #
        if self.primary_model:
            t0 = time.time()
            try:
                output = self._try_call(
                    self.primary_model, prompt, user_input, params, context
                )
                latency_ms = int((time.time() - t0) * 1000)
                self._log_call(trace_id, task_type, self.primary_model,
                               latency_ms, "success", None, input_hash)
                return {
                    "status": "success", "output": output, "trace_id": trace_id,
                    "model": self.primary_model, "latency_ms": latency_ms,
                    "error_type": None, "degraded": False,
                }
            except Exception as e:
                latency_ms = int((time.time() - t0) * 1000)
                err_type = type(e).__name__
                self._log_call(trace_id, task_type, self.primary_model,
                               latency_ms, "failed", err_type, input_hash)
                logger.warning("[router] primary_model failed: %s: %s", err_type, e)

        # ---- 备用模型 ---- #
        if self.fallback_model:
            t0 = time.time()
            try:
                output = self._try_call(
                    self.fallback_model, prompt, user_input, params, context
                )
                latency_ms = int((time.time() - t0) * 1000)
                self._log_call(trace_id, task_type, self.fallback_model,
                               latency_ms, "success", None, input_hash)
                return {
                    "status": "success", "output": output, "trace_id": trace_id,
                    "model": self.fallback_model, "latency_ms": latency_ms,
                    "error_type": None, "degraded": True,
                }
            except Exception as e:
                latency_ms = int((time.time() - t0) * 1000)
                err_type = type(e).__name__
                self._log_call(trace_id, task_type, self.fallback_model,
                               latency_ms, "failed", err_type, input_hash)
                logger.warning("[router] fallback_model failed: %s: %s", err_type, e)

        # ---- 规则降级 ---- #
        degraded_output = self._degrade(task_type, context)
        self._log_call(trace_id, task_type, "rule_degraded",
                       0, "degraded", "all_models_failed", input_hash)
        return {
            "status": "degraded", "output": degraded_output, "trace_id": trace_id,
            "model": "rule_degraded", "latency_ms": 0,
            "error_type": "all_models_failed", "degraded": True,
        }

    # ---- 内部方法 ---- #

    def _load_prompt(self, task_type):
        """加载冻结提示词（从 prompts/ 目录读取 .md 文件内容）。"""
        rel_path = TASK_PROMPTS.get(task_type, "")
        if not rel_path:
            return ""
        # 以本文件所在目录为基准，向上找仓库根
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full = os.path.join(base, rel_path)
        try:
            with open(full, encoding="utf-8") as f:
                return f.read()
        except (OSError, IOError):
            logger.warning("[router] prompt file not found: %s", full)
            return ""

    def _hash_input(self, text):
        """SHA256 摘要，不存原文。"""
        if not text:
            return "sha256:" + hashlib.sha256(b"").hexdigest()
        encoded = text.encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()[:16]

    def _log_call(self, trace_id, task_type, model, latency_ms,
                  status, error_type, input_hash):
        """记录调用日志到 stderr，JSON 行格式，不含原始内容。"""
        if not self.enable_log:
            return
        entry = {
            "ts": int(time.time()),
            "trace_id": trace_id,
            "task_type": task_type,
            "model": model,
            "latency_ms": latency_ms,
            "status": status,
            "error_type": error_type,
            "input_hash": input_hash,
        }
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    def _try_call(self, model, prompt, user_input, params, context):
        """实际模型调用，子类必须覆盖。

        Raises:
            NotImplementedError: 基类未实现具体调用逻辑。
        """
        raise NotImplementedError(
            "ModelRouter is abstract; subclass must implement _try_call "
            "(e.g. DuMateModelRouter / QianfanModelRouter)"
        )

    def _degrade(self, task_type, context):
        """规则降级返回预制结果。"""
        base = DEGRADED_OUTPUTS.get(task_type, {})
        result = dict(base)
        result["degraded"] = True
        return result


# ------------------------------------------------------------------ #
# 子类示例（DuMate 侧实现后替换 _try_call 内部逻辑）
# ------------------------------------------------------------------ #
class DuMateModelRouter(ModelRouter):
    """DuMate 模型路由器。

    _try_call 通过 DuMate 平台 SDK 调用模型；
    当前阶段 SDK 未接入，调用时 raise NotImplementedError。
    """

    def _try_call(self, model, prompt, user_input, params, context):
        raise NotImplementedError(
            "DuMateModelRouter._try_call: SDK not connected yet. "
            "Wire up DuMate platform SDK here."
        )


class QianfanModelRouter(ModelRouter):
    """千帆模型路由器。

    _try_call 通过千帆 API 调用模型；
    需配置 QIANFAN_API_KEY 环境变量，未配置时 raise NotImplementedError。
    """

    def __init__(self, primary_model=None, fallback_model=None, enable_log=True):
        super().__init__(primary_model, fallback_model, enable_log)
        self.api_key = os.environ.get("QIANFAN_API_KEY")
        if not self.api_key:
            raise NotImplementedError(
                "QianfanModelRouter: QIANFAN_API_KEY not set; "
                "configure it to enable Qianfan model calls"
            )

    def _try_call(self, model, prompt, user_input, params, context):
        raise NotImplementedError(
            "QianfanModelRouter._try_call: API call not implemented yet. "
            "Wire up Qianfan SDK here."
        )
