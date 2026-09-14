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

# 邮箱：`(?<!...)` 前瞻保证匹配只能从"局部段之外"开始，局部段与域名段按 RFC 上限截断。
#
# 不这样写会退化成二次复杂度：`[A-Za-z0-9._%+-]+@` 允许字符类吃到文本结尾再逐字
# 回溯去找 `@`，而简历正文可以长到 20 万字符（见 tests/test_api_boundary.py 的
# 200_000 字上限用例）。实测未限长版本：2 万字符 535ms，20 万字符约 100 秒 ——
# 一次合法上传就能把请求线程占满。加上前瞻后，同一段 `aaa...` 里只有"局部段起点"
# 会被尝试，其余位置 O(1) 直接否决。
RE_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}"
)
RE_ID = re.compile(r"\d{17}[\dXx]")
RE_NAME_TITLE = re.compile(r"(?:先生|女士|老师|同学)")

# ------------------------------------------------------------------ #
# 中文姓名脱敏
#
# 三条规则叠加，全部只替换“姓名捕获组”，不破坏句意：
#  1) RE_NAME_FIELD   —— 「姓名：张三」等显式字段（历史行为，保留）
#  2) RE_NAME_SELF    —— 「我叫/我是/本人叫/名字是……」等自述句式
#  3) RE_NAME_LINE    —— 整行只由一个姓名构成（简历抬头「王小明」）
#
# 规则 3 刻意收得很紧：只有“整行就是这个姓名”才脱敏，避免把
# 「华为、腾讯」「周末」等普通岗位/公司词误删（交接文档 7.3 第 3 条）。
# ------------------------------------------------------------------ #

# 常见姓氏（单姓）
SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"

# 常见复姓
COMPOUND_SURNAMES = (
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫", "万俟", "闻人",
    "夏侯", "诸葛", "尉迟", "皇甫", "公孙", "慕容", "宇文", "司徒", "司空", "令狐",
    "轩辕", "拓跋", "百里", "呼延", "轩辕", "第五", "西门", "东郭", "南门", "羊舌",
)

# 称谓/职务词：命中则不视为姓名，避免把「王老师」「李经理」整体删掉
NAME_TITLE_WORDS = (
    "先生", "女士", "老师", "同学", "博士", "教授", "经理", "主任", "医生",
    "护士", "主管", "总监", "总裁", "助理", "专员", "工程师", "顾问",
)

# 整行候选的常见非姓名词（公司/词汇），用于兜底规则的误伤保护
NON_NAME_LINE_TOKENS = frozenset({
    "华为", "华硕", "华夏", "华中", "华南", "华北", "华东", "华润", "华能", "华电",
    "周末", "周报", "周边", "周期", "周年", "王国", "王者", "王子",
    "张扬", "张江", "张贴", "张榜", "李白", "李子", "李宁", "孙子", "孙女",
    "陈述", "陈设", "陈旧", "陈年", "杨树", "杨梅", "黄土", "黄金", "金融",
    "金属", "金色", "韩国", "韩语", "楚国", "秦朝", "许可", "许多", "何时",
    "何处", "和平", "和睦", "孔子", "孔明", "严格", "严肃", "严冬", "水星",
    "水泥", "陶器", "陶瓷", "姜汤", "酱油", "卫生", "卫星", "沈阳", "周易",
})

_CN_CHAR = r"[\u4e00-\u9fa5]"
_COMPOUND_ALT = "(?:" + "|".join(COMPOUND_SURNAMES) + ")"
_NAME_BODY = (
    r"(" + _COMPOUND_ALT + _CN_CHAR + r"{1,2}"
    r"|[" + SURNAMES + r"]" + _CN_CHAR + r"{1,2})"
)

# 显式字段：姓名：X（长度同样受限，避免吞掉后续词）
RE_NAME_FIELD = re.compile(r"(姓\s*名\s*[:：]\s*)" + _NAME_BODY)

# 自述句式：我叫/我是/本人叫/本人是/名字叫/名字是/姓名：
# 用「单姓+1~2字」或「复姓+1~2字」限定长度，避免把紧随其后的词一并吞掉
# （例如「我是王小明负责后端」只能吃掉“王小明”，不能吃掉“负”）。
RE_NAME_SELF = re.compile(
    r"(我叫|我是|本人叫|本人是|名字叫|名字是|姓\s*名\s*[:：])\s*" + _NAME_BODY
)

# 兜底：整行只有一个姓名（允许前后空白）
RE_NAME_LINE = re.compile(
    r"^[ \t\u3000]*(?:" + _COMPOUND_ALT + _CN_CHAR + r"{1,2}"
    r"|[" + SURNAMES + r"]" + _CN_CHAR + r"{1,3})[ \t\u3000]*$",
    re.MULTILINE,
)


def _looks_like_name(candidate):
    """保守判定一个候选串是否像中文姓名。"""
    if not candidate or len(candidate) < 2:
        return False
    if candidate in NAME_TITLE_WORDS:
        return False
    if any(candidate.endswith(word) for word in NAME_TITLE_WORDS):
        return False
    if any(candidate.startswith(pair) for pair in COMPOUND_SURNAMES):
        return True
    return candidate[0] in SURNAMES


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
        if not _looks_like_name(m.group(2)):
            return m.group(0)
        mapping[m.group(2)] = "[REDACTED_NAME]"
        return m.group(1) + "[REDACTED_NAME]"

    text = RE_NAME_FIELD.sub(name_field_repl, text)

    def name_self_repl(m):
        if not _looks_like_name(m.group(2)):
            return m.group(0)
        mapping[m.group(2)] = "[REDACTED_NAME]"
        return m.group(1) + "[REDACTED_NAME]"

    text = RE_NAME_SELF.sub(name_self_repl, text)

    def name_line_repl(m):
        candidate = m.group(0).strip(" \t\u3000")
        if candidate in NON_NAME_LINE_TOKENS:
            return m.group(0)
        if not _looks_like_name(candidate):
            return m.group(0)
        mapping[candidate] = "[REDACTED_NAME]"
        return "[REDACTED_NAME]"

    text = RE_NAME_LINE.sub(name_line_repl, text)

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
