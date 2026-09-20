# -*- coding: utf-8 -*-
"""test_phase7d_contract.py · Phase 7d「`tools/` 归并」的结构契约

7d 把 `tools/` 整层并入 `domain/` + `providers/`（另加 `repositories/` 1 个、
`services/` 1 个），并重写全仓 `tools.*` 的引用。这一轮的风险**不是**行为变化
（那类问题 pytest 会先响），而是**结构悄悄回潮**：

* 有人又建一个 `tools/` 放"临时工具" —— `dependency-map.md` §5 第 4 条的保留期已到期；
* 某个模块被漏搬 —— 它只会在没被覆盖的那条分支上炸；
* 映射表被改了一条而没人发现。

所以这里把「哪个文件搬到哪、`tools/` 必须不在、旧路径不许再出现」变成**可判对象**。
"""
import ast
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 7d 的映射表。**这张表就是"归并没有漏"的判据**，不是文档。
MAPPING = {
    # → domain/：领域规则与领域内容
    "tools/interview_engine.py": "domain/interview_engine.py",
    "tools/match_requirements.py": "domain/match_requirements.py",
    "tools/privacy_lifecycle.py": "domain/privacy_lifecycle.py",
    "tools/upload_security.py": "domain/upload_security.py",
    "tools/validate_schema.py": "domain/validate_schema.py",
    "tools/deidentify.py": "domain/deidentify.py",
    "tools/knowledge.py": "domain/knowledge.py",
    "tools/optimizer.py": "domain/optimizer.py",
    "tools/redflag.py": "domain/redflag.py",
    "tools/rescore.py": "domain/rescore.py",
    # → domain/internal/：领域层的**层内工具**（§5 第 4 条说的"降级为 domain 的内部工具"）
    "tools/api_errors.py": "domain/internal/api_errors.py",
    "tools/contracts.py": "domain/internal/contracts.py",
    "tools/extract_text.py": "domain/internal/extract_text.py",
    "tools/log_sanitize.py": "domain/internal/log_sanitize.py",
    "tools/radar_adapter.py": "domain/internal/radar_adapter.py",
    "tools/trace.py": "domain/internal/trace.py",
    # → providers/：外部服务适配
    "tools/providers/__init__.py": "providers/__init__.py",
    "tools/providers/model.py": "providers/model.py",
    "tools/providers/organization.py": "providers/organization.py",
    "tools/model_router.py": "providers/model_router.py",
    "tools/ocr_provider.py": "providers/ocr_provider.py",
    # → repositories/：数据访问（§5 自己写明 repositories 就是 database.py 拆出来的）
    "tools/database.py": "repositories/database.py",
    # → services/：唯一同时"持业务逻辑 + 落库"的模块（services 是唯一允许两者的层）
    "tools/account.py": "services/account_service.py",
}

#: `tools/requirements.txt` 被删（逐行是根 `requirements.txt` 的子集）。这里是它的原文，
#: 用来证明"删掉不会少依赖"这件事**可复算**。
DELETED_REQUIREMENTS = [
    "pytest==9.0.3",
    "jsonschema==4.26.0",
    "pypdf==6.16.1",
    "python-docx==1.2.0",
    "requests==2.34.2",
    "playwright==1.62.0",
    "jieba==0.42.1",
]

#: 允许继续出现 `tools` 字样（点号或路径形态）的文件 —— **每条都要写理由**。
#:
#: 扫描面 = **AST 里的字符串常量**（也就是"能被执行到、或被复制去跑"的文字）：
#: 代码里的路径串、mock 目标串、以及 **docstring**。纯 `#` 注释**不在**面内 ——
#: 它既不会被执行，也不会被复制去跑，它只是写给下一个读代码的人看的；把注释也纳进来
#: 会让白名单多出三条"7d 的出处说明"，
#: 于是白名单就变成了"谁改了注释谁来加一行"的东西 —— 那正是白名单腐烂的方式。
#: （这里刻意不写"5 条/8 条"这类会自己漂移的计数，Phase 7c §21.5 已记过这一条教训。）
#:
#: 反过来说，docstring **必须**在面内：本次归并真的扫出过一条
#: `pip install -r tools/requirements.txt`（写在 `validate_schema.py` 的 docstring 里，
#: 会被用户原样复制去跑），它是这次最有价值的一条修复。
ALLOWED_RESIDUE = {
    "tests/test_phase1_deletions.py":
        "Phase 1 退役清单（RETIRED_FILES / RETIRED_PHASE1B_FILES）里的历史路径，"
        "配的是 `assert not (...).exists()` / `assert \"tools.tasks\" not in source`"
        "这类**否定**断言 —— 「`tools/tasks.py` 必须不存在」在 7d 之后仍然为真，"
        "删掉反而丢掉退役证据。这里的 `tools` 是**被判对象**，不是引用。",
    "tests/test_phase7d_contract.py":
        "就是本文件：`MAPPING` 的左列**必须**写 `tools/…`，否则「源路径已消失」这条"
        "断言没法写。它和 test_phase1_deletions 同属**否定**用法。",
    "tests/test_layering.py":
        "模块 docstring 记录 7d 对分层判据做了什么改动（`LAYERS` 里 `tools` → `providers`、"
        "规则 2 删掉冗余的 `tools.database`）。是变更说明，不是路径。",
    "api/trace.py":
        "模块 docstring 说明「原先 `tools/trace.py` 把纯函数与 Flask 半截塞在一起」——"
        "这解释了为什么全仓只有 `api/` 会碰 flask。是出处引用。",
    "domain/internal/__init__.py":
        "该文件**引用** dependency-map §5 第 4 条的原文（「`tools/` 逐步并入 …，"
        "或降级为 domain 的内部工具」），并逐条说明 6 个模块为什么算「内部工具」。"
        "是出处引用与设计依据。",
    "scripts/live-doc-path-check.py":
        "7d 给这条判据补了第三种观察面（仓库内路径），它的 docstring 必须举出"
        "`tools/validate_schema.py` / `tools/redflag.py` 这类**实例** —— 那正是它要抓的"
        "死链形态；`GONE_LAYERS` 里也必须留名 `tools`，否则「指向已消失的层」这个最该抓的"
        "形态会连同假阳性一起被放过。这里的 `tools` 全是**被判对象**，不是引用。",
}

# 左边界必须挡住 `functools.` / `setuptools.`（它们以 tools 结尾，但不是这一层）。
RESIDUE_RE = re.compile(r"(?<![A-Za-z0-9_.])tools[._/][A-Za-z0-9_./]*")
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".venv-audit"}


def _walk():
    """遍历仓库树，剪掉 SKIP_DIRS 与一切点开头的目录/文件。**所有判据共用它。**

    为什么要抽出来：每个判据各写一遍过滤，迟早有一个忘了。7d 就漏过一次 ——
    `ROOT.rglob("tools")` 没剪 `.venv-audit`，把 site-packages 里 5 个**第三方**的
    `tools/` 目录（playwright / pyparsing / zhipuai）报成了"`tools/` 回潮"。
    假阳性比漏判更糟：它训练人去看白名单而不是看代码。
    """
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in parts):
            continue
        yield path


def _py_files():
    return [p for p in _walk() if p.is_file() and p.suffix == ".py"]


def _string_constants(path):
    """该文件里所有**字符串常量**（docstring 本身就是字符串常量，天然在内）。"""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def _residue_hits():
    hits = {}
    for path in _py_files():
        found = set()
        for _lineno, value in _string_constants(path):
            found.update(RESIDUE_RE.findall(value))
        if found:
            hits[_rel(path)] = sorted(found)
    return hits


def _rel(path):
    return path.relative_to(ROOT).as_posix()


# ------------------------------------------------------------------ #
# 1. `tools/` 整层必须不存在
# ------------------------------------------------------------------ #

def test_tools_layer_is_gone():
    """目录没了，而且**不可 import**。

    两条要一起判：只删掉 `.py` 而留下空目录的话，`tools` 会变成一个可 import 的
    **命名空间包**，`import tools` 会静默成功 —— 「tools/ 已不存在」这条判据就成了空判。
    """
    assert not (ROOT / "tools").exists(), "tools/ 目录还在（哪怕是空的也算）"
    assert importlib.util.find_spec("tools") is None, "tools 仍然能被 import"


def test_no_temporary_tools_directory_resurrected():
    """整个仓库树里不许再出现 `tools/` 目录（不只是仓库根）。

    **只看仓库自己的树**：`.venv-audit` 的 site-packages 里有 5 个第三方的 `tools/`
    目录（playwright / pyparsing / zhipuai），它们是 `.venv` 的私事，不是本仓的结构。
    走 `_walk()` 而不是 `rglob` 就是为了这件事只过滤一次。
    """
    found = sorted(str(p.relative_to(ROOT)) for p in _walk() if p.is_dir() and p.name == "tools")
    assert found == [], "仓库树里又出现了 tools/ 目录（哪怕是空的也算）：%s" % found


# ------------------------------------------------------------------ #
# 2. 映射表逐条命中
# ------------------------------------------------------------------ #

def test_every_migrated_module_landed_at_the_mapped_path():
    missing, survivors = [], []
    for src, dst in sorted(MAPPING.items()):
        if not (ROOT / dst).is_file():
            missing.append(dst)
        if (ROOT / src).exists():
            survivors.append(src)
    assert missing == [], "目标路径缺失：%s" % missing
    assert survivors == [], "源路径还在：%s" % survivors
    assert len(MAPPING) == 23, "映射表条目数变了：%d" % len(MAPPING)


def test_migrated_modules_are_importable():
    """逐条真的 import 一次 —— 只判"文件在"会漏掉包 __init__ / 相对路径的问题。"""
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for dst in sorted(MAPPING.values()):
        dotted = dst[:-3].replace("/", ".")
        importlib.import_module(dotted)


# ------------------------------------------------------------------ #
# 3. 旧路径不许再出现
# ------------------------------------------------------------------ #

def test_no_module_imports_the_removed_layer():
    """AST 判据：全仓没有任何 `tools.*` / `from tools import …`。

    这一条**零容忍、无白名单**：`import` 只有一种意义，出现就是活的引用。
    （字符串形态的 `tools` 归下一条管，那条因为"出处引用"必须有白名单。）
    """
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tools" or alias.name.startswith("tools."):
                        offenders.append("%s:%d import %s" % (_rel(path), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                base = ("." * node.level) + (node.module or "")
                if base == "tools" or base.startswith("tools."):
                    offenders.append("%s:%d from %s import …" % (_rel(path), node.lineno, base))
    assert offenders == [], "仍有对已删除层的 import：\n  " + "\n  ".join(offenders)


def test_path_form_residue_is_confined_to_the_allowlist():
    """字符串常量里的 `tools` 路径/点号残留必须全部在 ALLOWED_RESIDUE 里，且每条都有理由。

    扫描面是**字符串常量**（含 docstring、mock 目标串、路径串），纯注释不在内 ——
    边界与理由见 ALLOWED_RESIDUE 上方的注释。
    """
    hits = _residue_hits()
    assert sorted(hits) == sorted(ALLOWED_RESIDUE), \
        "残留集合与白名单不一致：\n  实际=%s\n  白名单=%s" % (sorted(hits), sorted(ALLOWED_RESIDUE))
    for name, why in ALLOWED_RESIDUE.items():
        assert why.strip(), "%s 在白名单里但没写理由" % name
    # 判据自检：白名单里的文件必须**真的**还有残留，否则名单在腐烂
    for name in ALLOWED_RESIDUE:
        assert name in hits, "白名单里的 %s 已经没有残留了，应把它删掉" % name


# ------------------------------------------------------------------ #
# 4. 删掉的那份 requirements 确实是冗余的
# ------------------------------------------------------------------ #

def test_deleted_requirements_were_a_subset_of_the_root_ones():
    root_reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    root_lines = {ln.strip() for ln in root_reqs.splitlines()
                  if ln.strip() and not ln.strip().startswith("#")}
    assert not (ROOT / "tools" / "requirements.txt").exists()
    absent = [ln for ln in DELETED_REQUIREMENTS if ln not in root_lines]
    assert absent == [], "删掉 tools/requirements.txt 会丢依赖（根清单里没有）：%s" % absent


# ------------------------------------------------------------------ #
# 5. 规则 6 的承重墙：domain/internal 全是叶子
# ------------------------------------------------------------------ #

def _layering():
    """按路径加载 `tests/test_layering.py`，复用它的图与判据（不复制一份规则）。"""
    spec = importlib.util.spec_from_file_location("_layering_for_7d", ROOT / "tests" / "test_layering.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: `domain/internal/` 的成员**冻结**在这里（不含 `__init__`）。
#: 写死在表里而不是只判个数：`len == 6` 挡不住"换掉一个"（数量没变，规则 6 的承重墙
#: 却塌了一角）。
EXPECTED_DOMAIN_INTERNAL = {
    "domain.internal.api_errors",
    "domain.internal.contracts",
    "domain.internal.extract_text",
    "domain.internal.log_sanitize",
    "domain.internal.radar_adapter",
    "domain.internal.trace",
}


def test_domain_internal_is_the_leaf_package_rule6_relies_on():
    """`providers → domain` 那条反向边之所以合法，全靠这 6 个模块是叶子。"""
    layering = _layering()
    known, edges = layering._graph()
    internal = {n for n in known if n.startswith("domain.internal.") and not n.endswith(".__init__")}
    assert internal == EXPECTED_DOMAIN_INTERNAL, \
        "domain/internal 的模块集合变了：多=%s 少=%s" % (
            sorted(internal - EXPECTED_DOMAIN_INTERNAL),
            sorted(EXPECTED_DOMAIN_INTERNAL - internal))
    non_leaves = sorted(internal - layering.leaf_modules(edges))
    assert non_leaves == [], "这些 domain/internal 模块不再是叶子，规则 6 不再成立：%s" % non_leaves


def test_repo_root_derivations_match_the_real_depth():
    """从 `__file__` 推仓库根时，`parents[N]` 的 N 必须等于文件在仓库里的深度。

    **7d 撞到的真缺陷**：`domain/internal/contracts.py` 原来是 `tools/contracts.py`，
    用 `parents[1]` 拿仓库根。搬到 `domain/internal/` 后深了一层，`parents[1]` 变成
    `domain/` —— 它于是去 `domain/contracts/resume-profile.schema.json` 找 schema，
    **13 个测试模块在收集期就 FileNotFoundError**。

    这一类失效的可怕之处：改路径/改 import 的任何自动化都看不见它（它既不是 import，
    也不是字符串形态的 `tools`），而且**不报"我搬过家"，只报下游找不到文件**。
    所以把它写成静态判据：深度对不上就红，不用等下游炸。
    """
    pattern = re.compile(r"__file__\)\.resolve\(\)\.parents\[(\d+)\]")
    offenders = []
    for path in _py_files():
        depth = len(path.relative_to(ROOT).parts) - 1
        for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            for match in pattern.finditer(line):
                if int(match.group(1)) != depth:
                    offenders.append("%s:%d parents[%s] 但实际深度是 %d"
                                     % (_rel(path), line_no, match.group(1), depth))
    assert offenders == [], "从 __file__ 推仓库根的深度写错了：\n  " + "\n  ".join(offenders)
    # 正面证据：判据确实扫到了东西（否则正则是死的，永远绿）
    assert any(pattern.search(p.read_text(encoding="utf-8-sig")) for p in _py_files()), \
        "没有扫到任何 `parents[N]` —— 正则已失效"


def test_contracts_validator_points_at_the_real_contracts_directory():
    """行为侧复核：常量算出来的路径必须真的落在 `<repo>/contracts/`。"""
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from domain.internal import contracts

    assert contracts.REPOSITORY_ROOT == ROOT, contracts.REPOSITORY_ROOT
    assert (contracts.REPOSITORY_ROOT / "contracts" / "resume-profile.schema.json").is_file()


def test_the_mapping_checker_can_fail():
    """判据自检：改坏一条映射，检查器必须报出来（而不是恒绿）。"""
    broken = dict(MAPPING)
    broken["tools/database.py"] = "domain/database.py"          # 故意指向不存在的目标
    missing = [d for _s, d in sorted(broken.items()) if not (ROOT / d).is_file()]
    assert missing == ["domain/database.py"], missing


# ------------------------------------------------------------------ #
# 6. mock 目标串必须可解析（7d 的第二类隐蔽残留）
# ------------------------------------------------------------------ #

#: `unittest.mock.patch` / pytest `monkeypatch.setattr` 这些**收字符串目标**的调用。
MOCK_CALLS = {
    "patch", "patch.dict", "patch.multiple",
    "mock.patch", "mock.patch.dict",
    "setattr", "monkeypatch.setattr",
}


def _callee_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _callee_name(node.value)
        return "%s.%s" % (base, node.attr) if base else None
    return None


def _mock_targets():
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if _callee_name(node.func) not in MOCK_CALLS:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                yield _rel(path), node.lineno, first.value


def test_mock_targets_resolve_to_real_modules():
    """`patch("X.y")` / `monkeypatch.setattr("X.y", …)` 的首段 `X` 必须真的能 import。

    **7d 撞到的第二类隐蔽残留**：`tests/test_model_router_providers.py` 里 8 处
    `patch("model_router.urlopen")`。`model_router` 原来是仓库根的**裸模块**（靠
    `sys.path` 挂着），搬到 `providers/` 之后裸名不再可解析。

    它为什么特别危险 —— 它同时躲过了这次归并的三道判据：

    * 不是 `import` → `test_no_module_imports_the_removed_layer` 的 AST 看不见；
    * 不含 `tools` 字样 → 残留扫描看不见；
    * 只在 `patch(...)` **执行到那一行**才炸 → 收集期看不见，
      而且报错是 `ModuleNotFoundError: No module named 'model_router'`，
      读起来像环境问题，不像搬家问题。

    判据本身不需要维护任何"已迁移模块名"清单：直接把每个 mock 目标的首段拿去
    `find_spec`，解析不了就红。**这里不存在假阳性** —— 运行时也是拿这个名字去 import，
    判据与运行时用的是同一个判定标准。
    """
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    offenders, checked = [], []
    for rel, lineno, target in _mock_targets():
        head = target.split(".", 1)[0]
        if not head.isidentifier():
            continue
        checked.append(target)
        if importlib.util.find_spec(head) is None:
            offenders.append("%s:%d  mock 目标 %r —— 首段 %r 无法 import"
                             % (rel, lineno, target, head))
    assert offenders == [], "mock 目标指向不存在的模块：\n  " + "\n  ".join(offenders)
    # 正面证据：判据确实扫到了东西（否则永远绿）
    assert checked, "没有扫到任何 mock 目标 —— 判据已失效"
    assert any(t.startswith("providers.") for t in checked), \
        "没有扫到 `providers.` 开头的目标 —— 判据可能只扫到了无关的调用"


# ------------------------------------------------------------------ #
# 7. 活文档路径判据的观察面：第三种形态（`path`）必须真的被判
# ------------------------------------------------------------------ #

def _load_live_doc_judge():
    """把 `scripts/live-doc-path-check.py` 当模块加载**并完成清单装载**（这个脚本没有副作用）。

    Phase 8 起 `LIVING_DOCS` / `HISTORICAL` / `MIRRORS` 不再是模块级字面量，
    而是 `load_manifest()` 的产物 —— 只 `exec_module` 而不装载，它们全是空列表，
    下面那条"观察面必须含 HANDOFF.md"的断言会因为**三个空集合**而失败，
    读起来像"7d 的缺口回来了"，其实只是装配少了一步。
    这是 7c 那类"读源码的静态断言"失效的同一族：判据的接口变了，调用方要跟着变。

    装载报错时**直接失败**，不降级：清单坏了却让测试继续跑，等于在测一个空的观察面。
    """
    path = ROOT / "scripts" / "live-doc-path-check.py"
    assert path.exists(), "活文档路径判据不见了"
    spec = importlib.util.spec_from_file_location("live_doc_path_check", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    problems = module.load_manifest(str(ROOT))
    assert not problems, "观察面清单装载失败：%s" % problems
    return module


def test_live_doc_judge_covers_the_path_form():
    """7d 补的第三种形态必须真的在观察面里 —— 这是本轮**唯一没有判据**的那处缺口。

    `contracts/README.md` / `contracts/scoring.md` 里那两处 `tools/validate_schema.py`
    是 Phase 7d 人工扫出来的：`PAGE_RE` 只认 `pages/*.html`、`JS_DIR_RE` 只认 `js/*.js`，
    仓库内路径这种写法**根本抽不出来**。见 `docs/phase7d-report.md` §7。

    这条判据不查"脚本里有没有那行正则"（那是源码 grep，改个名字就骗过去了），
    而是**把脚本加载起来跑**：给它一段编造的行，看它判成什么。
    """
    judge = _load_live_doc_judge()

    # (a) 观察面必须含 `path` 形态，且这些文件必须被真的读进来
    for doc in ("HANDOFF.md", "contracts/README.md", "contracts/scoring.md"):
        assert doc in judge.LIVING_DOCS, "%s 不在活文档清单里 —— 7d 的缺口回来了" % doc

    have = judge.declared(str(ROOT))
    assert len(have["layer"]) >= 8, "只认到 %d 个顶层目录，path 类近乎空判" % len(have["layer"])

    # (b) **已消失的层**必须继续被抓 —— 扩面不能连真漂移一起放过。
    #     `tools/` 已经不在 `os.listdir` 里了，所以它只能靠 GONE_LAYERS 显式留名。
    assert "tools" in judge.GONE_LAYERS, "`tools` 不在已消失层清单里 —— 指向旧层的引用会被放过"
    assert judge.GONE_LAYERS["tools"].strip(), "已消失层必须写理由（否则清单会变成护身符）"
    dead = ["## 9. 处置", "", "`tools/redact.py` 负责脱敏。"]
    assert judge.classify(dead, 2, have)[2] == "offender", \
        "指向已消失的层没有被判为 offender —— 扩面只是换了个地方漏"

    # (c) 假阳性必须被挡在观察面之外（7d 一次实测 68 处里 7 处是这么来的）：
    #     `work/` 在**仓库外**（门禁脚本住的那层），`blind-test-results/` 是**部署 URL**。
    for line in ("- 脚本 `work/verify7d-moves.py` 在仓库外",
                 "- 实测 16 份：`blind-test-results/blind-test-report.md`"):
        leaked = [k for k, _ in judge.refs_in(line) if k == "path"]
        assert leaked == [], "仓库外/部署 URL 路径被当成仓库内路径：%s" % leaked

    # (d) 豁免机制本身要可证伪：历史结论认、范围说明不认。
    baseline = ["## 9. 处置（Phase 0 基线）", "", "### 9.1 明细", "", "`tools/redact.py` 负责脱敏。"]
    assert judge.classify(baseline, 4, have)[2] == "excused", \
        "父标题里的『基线』没有遗传到子标题 —— 审计文档要被迫在 5 个子标题上抄 5 遍"
    snapshot = ["## 2. 用户页面（快照：8 个 HTML）", "", "`tools/redact.py` 负责脱敏。"]
    assert judge.classify(snapshot, 2, have)[2] == "offender", \
        "『快照』被当成历史语境 —— 6b-2b 那条教训回退了（快照是范围，基线是时间点）"
    h1 = ["# 只读审计报告", "", "## 1. 现状", "", "`tools/redact.py` 负责脱敏。"]
    assert judge.classify(h1, 4, have)[2] == "offender", \
        "H1 标题里的词把整份文档豁免了 —— H1 是文档标题，不是章节"

    # 刻意**不**在这里跑 `judge.audit(ROOT)` 做端到端：那件事属于门禁第 10 步。
    # 两处都跑，一次文档漂移会在 pytest 与门禁各报一遍，故障归因反而变模糊。
    # 这里只钉住"判据能判、判得动、且能被证伪"。
