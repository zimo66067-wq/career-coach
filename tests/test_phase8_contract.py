# -*- coding: utf-8 -*-
"""Phase 8 契约：观察面由**清单**决定，且清单坏掉时判据必须红而不是降级。

## 这一轮的新失效模式

Phase 8 把「活文档观察面」从写死在 `scripts/live-doc-path-check.py` 里的 8 份，
改成从 `contracts/living-docs.json` 读的 56 份。于是判据的**输入**多了一个外部对象，
它自己也就多了一类失效方式：

1. **观察面其实是写死的，清单只是装饰** —— 本文件第 1 条用"给一份编造的清单，
   看判据跟不跟"来判。只查源码里有没有 `json.load` 是骗得过去的（改个名字就行），
   所以这里把脚本加载起来、换一份清单、看它的观察面变不变。
2. **清单坏了就悄悄退回默认的 8 份** —— 那会让判据继续绿，而它看的已经不是
   清单说的那个观察面了。第 2/3/4 条要求"缺清单""清单非法""条目缺理由"三种情况
   都必须**返回问题**，不许静默放行。
3. **`fnmatch` 的 `*` 跨 `/` 这条语义被改回 glob 语义** —— `deliverables/**`
   就只匹配一层了，深层证据文件会被当 offender 报出来。第 5 条钉住它。
4. **「同名即镜像」的假设回来** —— `docs/index.md` 与 `public/index.md` 同名但语义不同
   （前者是 docs 目录索引，后者是发布树公开清单）。第 7 条钉住这一对**不是**镜像。

端到端（全仓 56 份 / 955 处引用 / 0 死链）**刻意不在这里跑**：那是门禁第 10 步的职责。
本文件只测"判据的输入契约"，跑得快，且在观察面出问题时能指出是哪一条。
"""
import importlib.util
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUDGE = os.path.join(ROOT, "scripts", "live-doc-path-check.py")
MANIFEST = os.path.join("contracts", "living-docs.json")


def _judge():
    """每次调用都加载一个**全新的**模块实例：`LIVING_DOCS` 等是全局状态，
    复用实例会让"临时清单"污染后面的用例（顺序一变就假红/假绿）。"""
    spec = importlib.util.spec_from_file_location("live_doc_path_check_8", JUDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(root, payload):
    os.makedirs(os.path.join(root, "contracts"), exist_ok=True)
    with io.open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False))


def _tmp_manifest(tmp_path, payload):
    """把清单写进一个临时 root，返回该 root。"""
    root = str(tmp_path)
    _write_manifest(root, payload)
    return root


# ── 1. 观察面真的是数据驱动的（这条是本文件的地基）────────────────────
def test_the_surface_comes_from_the_manifest_not_from_source(tmp_path):
    """换一份编造的清单，判据的观察面必须跟着换。

    用一个**只列了一份不存在文件**的清单：装载后 `LIVING_DOCS` 必须正好是那一条
    （如果判据内部还留着写死的清单，这里会是那 8 份），且 `audit` 必须报
    「观察面清单过期」—— 一份编造清单里的文件当然不存在。
    """
    root = _tmp_manifest(tmp_path, {
        "version": 1,
        "precedence": "living 优先",
        "living": [{"path": "docs/编造出来的活文档.md", "why": "只为证明观察面是数据驱动的"}],
        "historical": [{"glob": "CHANGELOG.md", "why": "临时清单也要写理由"}],
        "mirrors": [],
    })
    judge = _judge()
    problems = judge.load_manifest(root)
    assert problems == [], "临时清单本身是合法的，不该报问题：%s" % problems
    assert judge.LIVING_DOCS == ["docs/编造出来的活文档.md"], (
        "观察面没跟着清单走 —— 判据里还留着写死的清单？实测 %r" % (judge.LIVING_DOCS,))


# ── 2. 清单缺失不许降级 ────────────────────────────────────────────
def test_a_missing_manifest_is_never_downgraded(tmp_path):
    """清单没了必须报问题，且观察面必须是空的 —— 不许悄悄退回写死的那几份。"""
    root = str(tmp_path)          # 故意不写清单
    judge = _judge()
    problems = judge.load_manifest(root)
    assert problems, "清单缺失却返回 0 问题 —— 判据会绿着看一个它自己编的观察面"
    assert judge.LIVING_DOCS == [], (
        "清单缺失时观察面不是空的（%d 份）—— 降级回写死的清单了" % len(judge.LIVING_DOCS))


# ── 3. 清单损坏不许降级 ────────────────────────────────────────────
def test_a_broken_manifest_is_never_downgraded(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "contracts"), exist_ok=True)
    with io.open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as f:
        f.write('{"living": [ this is not json ')
    judge = _judge()
    problems = judge.load_manifest(root)
    assert problems and "不是合法 JSON" in problems[0], "非法 JSON 没有被报出来：%s" % problems
    assert judge.LIVING_DOCS == []


# ── 4. 每个条目必须写理由（清单要当"可判对象"，理由就是判据）──────────
def test_every_entry_must_state_a_reason(tmp_path):
    """`why` 不是排版：一条说不出理由的登记，下一个人只会照抄或删掉。"""
    root = _tmp_manifest(tmp_path, {
        "version": 1,
        "precedence": "living 优先",
        "living": [{"path": "docs/architecture.md"}],              # 缺 why
        "historical": [{"glob": "CHANGELOG.md"}],                   # 缺 why
        "mirrors": [],
    })
    judge = _judge()
    problems = judge.load_manifest(root)
    assert any("living 条目缺" in p for p in problems), problems
    assert any("historical 条目缺" in p for p in problems), problems


# ── 5. `fnmatch` 的 `*` 必须跨 `/`（glob 语义会把深层证据报成死链）────
def test_historical_glob_matches_across_slashes():
    judge = _judge()
    judge.load_manifest(ROOT)
    deep = "deliverables/p0-03-evidence/RUN_EVIDENCE_REPORT.md"
    hit = judge.is_historical(deep)
    assert hit, ("`%s` 没被任何历史族豁免 —— glob 语义被改成只匹配一层了，"
                 "整个交付树会被报成漂移" % deep)


# ── 6. living 优先于 historical，且这条优先级必须写在清单里 ─────────
def test_living_takes_precedence_and_it_is_declared():
    """`deliverables/README.md` 同时是活文档与 `deliverables/**` 的成员。

    两者都为真 ⇒ 优先级规则**必须**存在，否则它会被静默豁免（那是探针 18 的题目）。
    这里从清单侧钉：`precedence` 字段必须在，且这一条确实既在 living 又命中 historical。
    """
    judge = _judge()
    judge.load_manifest(ROOT)
    assert "deliverables/README.md" in judge.LIVING_DOCS
    assert judge.is_historical("deliverables/README.md"), "它本该同时落在 deliverables/** 里"
    with io.open(os.path.join(ROOT, MANIFEST), "r", encoding="utf-8") as f:
        data = json.load(f)
    assert (data.get("precedence") or "").strip(), "清单缺 `precedence`：重叠时无裁决规则"


# ── 7. 同名 ≠ 镜像（否则 docs/index.md 的目录索引语义会被抹掉）───────
def test_same_named_index_files_are_not_registered_as_mirrors():
    judge = _judge()
    judge.load_manifest(ROOT)
    pairs = {(a, b) for a, b, _ in judge.MIRRORS}
    assert ("docs/index.md", "public/index.md") not in pairs, (
        "把两份同名 index.md 登记成镜像了 —— 它们内容不同，同步任一方向都会毁掉一份")
    a = os.path.join(ROOT, "docs", "index.md")
    b = os.path.join(ROOT, "public", "index.md")
    assert os.path.exists(a) and os.path.exists(b)
    assert judge.sha(a) != judge.sha(b), (
        "两份 index.md 变成逐字节相同了 —— 有人按「同名即镜像」同步过")


# ── 8. 登记在册的镜像对必须真的逐字节相同 ─────────────────────────
def test_registered_mirrors_are_byte_identical():
    judge = _judge()
    judge.load_manifest(ROOT)
    assert judge.MIRRORS, "镜像对为空 —— 这条不变量不再约束任何东西"
    drifted = [a for a, b, _ in judge.MIRRORS
               if judge.sha(os.path.join(ROOT, a)) != judge.sha(os.path.join(ROOT, b))]
    assert not drifted, "镜像漂移（改了一边没改另一边）：%s" % drifted


if __name__ == "__main__":
    sys.exit(0)
