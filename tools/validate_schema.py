# -*- coding: utf-8 -*-
"""validate_schema.py · 合同校验器（Schema 层 + 业务规则层）

用法:
  python tools/validate_schema.py --schema <schema.json> --instance <data.json>

业务规则（contracts/README.md 冻结）:
  - 所有 score ∈ [0,100]（Schema 已含，双保险）
  - AbilityProfile.plan 恰好 7 条、day 1-7 不重复、minutes ∈ [30,45]、必含 artifact
  - InterviewTurn.answer_quote 必须是 answer 的子串
  - ResumeProfile 每条评分理由与建议 ≥1 个 source_span
  - AbilityProfile.dimensions 六维 key 不重复
退出码: 0=VALID  1=INVALID  2=用法/文件错误
"""
import argparse
import io
import json
import sys


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def business_rules(instance, errors):
    if not isinstance(instance, dict):
        return
    # InterviewTurn 或 InterviewTurn 序列
    turns = []
    if "answer" in instance and "answer_quote" in instance:
        turns = [instance]
    elif isinstance(instance, list):
        turns = [x for x in instance if isinstance(x, dict) and "answer" in x]
    for t in turns:
        q = t.get("answer_quote")
        a = t.get("answer", "")
        if q is not None and q not in a:
            errors.append("turn %s: answer_quote 不是 answer 的子串" % t.get("turn_id", "?"))

    # ResumeProfile 证据约束（InterviewTurn 的 subscores 为数值，跳过）
    if isinstance(instance.get("subscores"), dict):
        for k, v in instance["subscores"].items():
            if isinstance(v, dict) and "source_spans" in v and not v.get("source_spans"):
                errors.append("subscores.%s 缺少 source_span" % k)
        for s in instance.get("suggestions", []):
            if isinstance(s, dict) and not s.get("source_spans"):
                errors.append("suggestion %s 缺少 source_span" % s.get("id", "?"))

    # AbilityProfile 业务规则
    if "plan" in instance:
        plan = instance["plan"]
        days = [p.get("day") for p in plan]
        if len(plan) != 7:
            errors.append("plan 必须恰好 7 条（当前 %d）" % len(plan))
        if len(set(days)) != len(days):
            errors.append("plan 的 day 存在重复：%s" % days)
        for p in plan:
            if not (30 <= p.get("minutes", 0) <= 45):
                errors.append("day %s 的 minutes=%s 不在 [30,45]" % (p.get("day"), p.get("minutes")))
            if not p.get("artifact"):
                errors.append("day %s 缺少 artifact" % p.get("day"))
    if "dimensions" in instance:
        keys = [d.get("key") for d in instance["dimensions"]]
        if len(set(keys)) != len(keys):
            errors.append("dimensions 的 key 存在重复：%s" % keys)
        if len(keys) != 6:
            errors.append("dimensions 必须恰好六维（当前 %d）" % len(keys))


def main():
    ap = argparse.ArgumentParser(description="JSON Schema + 业务规则双重校验")
    ap.add_argument("--schema", required=True)
    ap.add_argument("--instance", required=True)
    args = ap.parse_args()

    try:
        schema = load(args.schema)
        instance = load(args.instance)
    except (OSError, json.JSONDecodeError) as e:
        print("INVALID: 文件读取失败 %s" % e)
        sys.exit(2)

    errors = []
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("INVALID: 缺少 jsonschema 依赖，请先 pip install -r tools/requirements.txt")
        sys.exit(2)

    validator = Draft202012Validator(schema)
    for e in sorted(validator.iter_errors(instance), key=str):
        path = "/".join(str(p) for p in e.absolute_path) or "(root)"
        errors.append("schema: %s: %s" % (path, e.message))

    business_rules(instance, errors)

    if errors:
        print("INVALID")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("VALID")
    sys.exit(0)


if __name__ == "__main__":
    main()
