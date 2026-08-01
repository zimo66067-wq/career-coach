# -*- coding: utf-8 -*-
"""rescore.py · 分数复算器（contracts/scoring.md 的唯一执行口径）

用法:
  python tools/rescore.py --input <score-input.json> [--expect C0=68.27] [--tolerance 0.5]

输入格式（见 tests/fixtures-synthetic/abilities/score-input-01.json）:
  R: 五个子分 0-100
  M: requirements 数组，每项 {type: hard|responsibility|preferred|terminology,
                               status: covered|weak|missing|unknown}
  I: 五个子分 0-100
  expected（可选）: {R,M,I,C0,C7_low,C7_high} 对拍基准

规则（冻结）:
  covered=1 / weak=0.5 / missing=0 / unknown 剔出分母
  类别全 unknown -> 该类 insufficient_evidence，权重在剩余类别归一
  全部类别 unknown -> M=insufficient_evidence，退出码 3
退出码: 0=对拍通过  1=对拍超差  2=输入错误  3=证据不足
"""
import argparse
import io
import json
import sys

R_WEIGHTS = {"structure": 0.15, "clarity": 0.20, "achievement_evidence": 0.25,
             "skill_evidence": 0.20, "ats_readability": 0.20}
M_WEIGHTS = {"hard": 0.50, "responsibility": 0.25, "preferred": 0.15, "terminology": 0.10}
I_WEIGHTS = {"structure": 0.25, "relevance": 0.25, "specificity": 0.20,
             "followup_adaptation": 0.15, "clarity": 0.15}
STATUS_VALUE = {"covered": 1.0, "weak": 0.5, "missing": 0.0}


def round2(x):
    # round half up，避免银行家舍入与手算不一致
    import decimal
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def calc_R(r):
    vals, wsum, acc = {}, 0.0, 0.0
    for k, w in R_WEIGHTS.items():
        v = r.get(k)
        if v is None:  # unknown：剔除并归一
            vals[k] = None
            continue
        if not (0 <= v <= 100):
            raise ValueError("R.%s=%s 越界 [0,100]" % (k, v))
        vals[k] = v
        wsum += w
        acc += v * w
    if wsum == 0:
        raise ValueError("R 全部子分 unknown")
    return acc / wsum


def calc_M(requirements):
    cat_sum = {k: 0.0 for k in M_WEIGHTS}
    cat_cnt = {k: 0 for k in M_WEIGHTS}
    for req in requirements:
        t, s = req.get("type"), req.get("status")
        if t not in M_WEIGHTS:
            raise ValueError("未知 requirement type: %s" % t)
        if s == "unknown":
            continue  # 不进分母
        if s not in STATUS_VALUE:
            raise ValueError("未知 status: %s" % s)
        cat_sum[t] += STATUS_VALUE[s]
        cat_cnt[t] += 1
    cat_score, eff_w = {}, 0.0
    for t, w in M_WEIGHTS.items():
        if cat_cnt[t] == 0:
            cat_score[t] = None  # insufficient_evidence
        else:
            cat_score[t] = cat_sum[t] / cat_cnt[t] * 100.0
            eff_w += w
    if eff_w == 0:
        return None, cat_score  # 整体 insufficient_evidence
    m = sum((cat_score[t] or 0.0) * w for t, w in M_WEIGHTS.items() if cat_score[t] is not None) / eff_w
    return m, cat_score


def calc_I(i):
    wsum, acc = 0.0, 0.0
    for k, w in I_WEIGHTS.items():
        v = i.get(k)
        if v is None:
            continue
        if not (0 <= v <= 100):
            raise ValueError("I.%s=%s 越界 [0,100]" % (k, v))
        wsum += w
        acc += v * w
    if wsum == 0:
        raise ValueError("I 全部子分 unknown")
    return acc / wsum


def compute(data):
    R = calc_R(data["R"])
    M, cat = calc_M(data["M"]["requirements"])
    if M is None:
        return {"insufficient_evidence": True, "M_categories": cat}
    I = calc_I(data["I"])
    C0 = 0.25 * R + 0.35 * M + 0.40 * I
    space = 100.0 - C0
    return {
        "R": round2(R), "M": round2(M), "I": round2(I),
        "M_categories": {k: (round2(v) if v is not None else "insufficient_evidence") for k, v in cat.items()},
        "C0": round2(C0),
        "C7_low": round2(min(100.0, C0 + space * 0.30)),
        "C7_high": round2(min(100.0, C0 + space * 0.70)),
    }


def main():
    ap = argparse.ArgumentParser(description="按 contracts/scoring.md 复算 R/M/I/C0/C7")
    ap.add_argument("--input", required=True)
    ap.add_argument("--expect", nargs="*", default=[], help="如 C0=68.27 R=73.00（可多个）")
    ap.add_argument("--tolerance", type=float, default=0.5)
    args = ap.parse_args()

    try:
        data = json.load(io.open(args.input, encoding="utf-8"))
        result = compute(data)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        print("[rescore] 输入错误：%s" % e, file=sys.stderr)
        sys.exit(2)

    if result.get("insufficient_evidence"):
        print("[rescore] M insufficient_evidence：全部类别均为 unknown，C0 不计算")
        sys.exit(3)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    expects = dict(e.split("=", 1) for e in args.expect)
    expected = dict(data.get("expected", {}))
    expected.update({k: float(v) for k, v in expects.items()})
    bad = []
    for k, v in expected.items():
        if k not in result:
            continue
        diff = abs(result[k] - float(v))
        print("[rescore] 对拍 %s: 复算=%.2f 期望=%.2f diff=%.2f" % (k, result[k], float(v), diff))
        if diff > args.tolerance:
            bad.append(k)
    if bad:
        print("[rescore] FAIL: 超差项 %s（tolerance=%.2f）" % (bad, args.tolerance))
        sys.exit(1)
    print("[rescore] PASS（tolerance=%.2f）" % args.tolerance)


if __name__ == "__main__":
    main()
