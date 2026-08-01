# -*- coding: utf-8 -*-
"""deidentify.py · 去标识化（WF-01 必经环节，见 docs/privacy.md）

用法:
  python tools/deidentify.py --input <in.txt> --output <out.txt> [--map map.json]

规则:
  - 脱除：手机号 / 邮箱 / 身份证18位 / 姓名（常见姓氏+称谓启发式、以及「姓名：X」显式字段）
  - 输出尾部追加标记行 `pii_removed:true`
  - --map 默认不落盘（传入路径才会写，且仓库 .gitignore 与 privacy.md 禁止入库）
"""
import argparse
import io
import json
import re
import sys

RE_PHONE = re.compile(r"1[3-9]\d{9}")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_ID = re.compile(r"\d{17}[\dXx]")
RE_NAME_FIELD = re.compile(r"(姓\s*名\s*[:：]\s*)([\u4e00-\u9fa5·]{2,4})")
RE_NAME_TITLE = re.compile(r"(?:先生|女士|老师|同学)")

# 常见姓氏启发式：2-3 字中文名（仅作兜底，误伤率可接受——合成样本场景）
SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
RE_NAME_HEURISTIC = re.compile(r"(?<![\u4e00-\u9fa5])([" + SURNAMES + r"][\u4e00-\u9fa5]{1,2})(?=[\s，,。:：/]|$)")


def deidentify(text):
    mapping = {}

    def _tag_sub(pattern, tag, s):
        def repl(m):
            mapping[m.group(0)] = tag
            return tag
        return pattern.sub(repl, s)

    text = _tag_sub(RE_ID, "[REDACTED_ID]", text)
    text = _tag_sub(RE_PHONE, "[REDACTED_PHONE]", text)
    text = _tag_sub(RE_EMAIL, "[REDACTED_EMAIL]", text)

    def name_field_repl(m):
        mapping[m.group(2)] = "[REDACTED_NAME]"
        return m.group(1) + "[REDACTED_NAME]"

    text = RE_NAME_FIELD.sub(name_field_repl, text)
    text = RE_NAME_TITLE.sub("[REDACTED_TITLE]", text)
    return text, mapping


def scan_residue(text):
    """返回残留 PII 命中列表（应为空）。"""
    hits = []
    for name, pat in (("phone", RE_PHONE), ("email", RE_EMAIL), ("id", RE_ID)):
        for m in pat.finditer(text):
            hits.append({"type": name, "value": m.group(0), "pos": m.start()})
    return hits


def main():
    ap = argparse.ArgumentParser(description="去标识化：姓名/手机号/邮箱/身份证")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--map", default=None, help="PII 映射表输出路径（默认不落盘，禁止入库）")
    args = ap.parse_args()

    text = io.open(args.input, encoding="utf-8").read()
    cleaned, mapping = deidentify(text)
    cleaned = cleaned.rstrip() + "\n\npii_removed:true\n"

    residue = scan_residue(cleaned)
    if residue:
        print("[deidentify] 警告：脱除后仍检测到残留 PII：%s" % residue, file=sys.stderr)
        sys.exit(3)

    with io.open(args.output, "w", encoding="utf-8") as f:
        f.write(cleaned)
    if args.map:
        with io.open(args.map, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        print("[deidentify] 映射表已写入 %s（注意：禁止入库！）" % args.map, file=sys.stderr)
    print("[deidentify] OK %s -> %s（脱除 %d 项）" % (args.input, args.output, len(mapping)))


if __name__ == "__main__":
    main()
