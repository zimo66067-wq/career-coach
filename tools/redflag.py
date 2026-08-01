# -*- coding: utf-8 -*-
"""redflag.py · 事实锁机器校验（事实锁第1/2条，见 docs/PRD.md 第3节）

用法:
  python tools/redflag.py --output <model_output.json> --against <source1.txt> [source2.txt ...]

规则:
  1. 抽取模型输出 JSON 中的所有数字与「疑似专有名词」（连续大写/驼峰/含版本号词、
     连续 2-6 个中文字符的引号外新词暂以数字与英文词为主）
  2. 凡未在任一 --against 输入文本中出现的数字 -> 标红；
     带「待用户核实：」前缀的占位数字除外
  3. 任一标红 -> block_release:true，退出码 1；全部通过 -> 退出码 0
说明: 英文技术词（如 Go/MySQL）采用词表外新增告警（warning，不阻断），
     数字类幻觉是主要阻断对象（与说明书一致：一条虚构即 0 分）。
"""
import argparse
import io
import json
import re
import sys

RE_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
RE_PLACEHOLDER = re.compile(r"待用户核实[：:][^，。,；;\n\"]*?(\d+(?:\.\d+)?|X)", re.I)
RE_EN_WORD = re.compile(r"\b[A-Za-z][A-Za-z0-9+#.\-]{1,}\b")

# 跳过字段：assumptions 为演示假设的元陈述（0.30/0.70 等参数本身即合法输出）；
# 数值型 JSON 字段（score/day/minutes/baseline 等）天然不进入字符串检查。
SKIP_KEYS = {"assumptions"}

# 输出 JSON 自身的结构性字段/常量（白名单，不视为事实）
JSON_NOISE = {"version", "1.0", "true", "false", "null", "hard", "responsibility", "preferred",
              "terminology", "covered", "weak", "missing", "unknown", "structure", "clarity",
              "relevance", "specificity", "artifact", "day", "minutes", "low", "high", "score",
              "P0", "P1", "P2", "S", "R", "M", "I", "C0", "C7"}


def flatten_strings(obj, out, skip_key=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            flatten_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            flatten_strings(v, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out


def main():
    ap = argparse.ArgumentParser(description="事实锁机器校验：输出中的新数字/新名词必须能回指输入")
    ap.add_argument("--output", required=True, help="模型输出 JSON")
    ap.add_argument("--against", nargs="+", required=True, help="输入对象文本（可多份）")
    args = ap.parse_args()

    try:
        model_out = json.load(io.open(args.output, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print("[redflag] 输出文件读取失败：%s" % e, file=sys.stderr)
        sys.exit(2)

    corpus = ""
    for p in args.against:
        corpus += io.open(p, encoding="utf-8", errors="replace").read() + "\n"

    strings = flatten_strings(model_out, [])
    joined = "\n".join(strings)

    # 占位数字白名单（「待用户核实：」前缀）
    placeholder_nums = set(RE_PLACEHOLDER.findall(joined))

    red, warn = [], []
    for m in RE_NUMBER.finditer(joined):
        num = m.group(1)
        if num in placeholder_nums or num in JSON_NOISE:
            continue
        # 结构字段值（day 1-7、minutes、score 0-100 等）若在语料中没有，仍可能是
        # 模型自行计算或计划参数 —— 数字类一律要求在语料中出现，否则标红（严格口径）
        variants = {num, num.rstrip("0").rstrip(".") if "." in num else num, num + "%"}
        if not any(v in corpus for v in variants):
            red.append({"type": "number", "value": num, "pos": m.start()})

    for m in RE_EN_WORD.finditer(joined):
        w = m.group(0)
        if w in JSON_NOISE or len(w) <= 2:
            continue
        if w.lower() not in corpus.lower() and w not in corpus:
            warn.append({"type": "en_word", "value": w})

    # 去重
    seen_r, red_u = set(), []
    for r in red:
        if r["value"] not in seen_r:
            seen_r.add(r["value"])
            red_u.append(r)
    seen_w, warn_u = set(), []
    for w in warn:
        if w["value"] not in seen_w:
            seen_w.add(w["value"])
            warn_u.append(w)

    report = {
        "block_release": bool(red_u),
        "red": red_u,
        "warn": warn_u,
        "note": "red=输出中出现输入语料之外的数字（阻断发布）；warn=语料之外的英文词（人工复核）",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(1 if red_u else 0)


if __name__ == "__main__":
    main()
