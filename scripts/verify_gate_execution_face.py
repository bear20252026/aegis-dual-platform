#!/usr/bin/env python3
"""verify_gate_execution_face.py —— 「门禁脚本到底在哪个面上被执行」的可判红登记（R9-B62 / 台账 §3.62）。

族谱（同一个形状踩了三次，每次都靠人现读才发现）：R9-CI-4 是一支门禁的唯一调用点在 tag 触发的发布流里、
PR 面零执行，四条 pytest 用例又全部 monkeypatch ⇒ 常跑面只证明机制、不证明现树；AEG-006 是向量
「有形状校验、零真实消费者」；R9-B60 是一条自 R9-B49 起就从没跑通的诊断步骤（站在错的 cwd 里，且是
dispatch-only 面，PR 全绿没人看）。共同形状是**判定写好了、执行面没人核**。本批收成通则：登记表
`contracts/ci/gate-execution-face.yaml` ＋ 这条判据。

口径三条，每条都有被实测否掉的备选：① 执行点只取 workflow / 本地 composite action 的 `run:` **正文**
（提取单源 `scripts/workflow_run_face.py`，含沿本地 `uses:` 传递的复用面）——理由不是设想，`verify_artifact_set` 在 `release.yml` 里只出现在 191-195 行的注记中（195 行是把命令抄成
注释那一行），按原文正则判它「有 CI 执行点」会当场假绿；② 闭包只走**非测试**文件——`tests/python/`
整目录被一条 pytest 步骤收集，允许穿过测试的话「可达」就膨胀成「凡被 import 过的都算跑过」⇒ 判据恒真，
而 R9-CI-4 正是「用例全绿＋门禁没判过现树」；③ 文件内引用只取 AST 里会进入代码的字符串与 import 名
（注释与 docstring 都不算）——理由写在 `scripts/text_anchors.py` 的实测教训里：docstring 是字符串字面量，
逐字写被观察的文件名就会造出一条假调用点，所以本文件 docstring 里这些文件名不会成为调用点，
是设计而非漏洞。

判红的面（每条都在 tests/python/gate_execution_face_test.py 里以内存态注入证伪）：闭包外的受管脚本必须
**恰好登记一次**（零条＝没有任何判据知道它该不该跑；两条＝两份会在不同批次各自漂移，R9-B61 同族）；
已可达的**不得**留在表里（该撤不撤，表就烂成「其实接了而读的人以为没接」）；`face: ci` 的 workflow 必须
存在、不在 PR 判定面上、且其 `run:` 正文在该步生效 cwd 下真调用到它（R9-B60：调用点存在 ≠ 能执行）；
`face: manual` 的 evidence 必须存在且正文逐字出现该路径（写「见 runbook」而 runbook 里没那条命令，就是
第二条失实陈述）；两种 face 都要 `why` 非空，`face` 只认 ci/manual，该带的字段缺了判红、乱填也判红。

退出码：0=一致 / 1=违规 / 2=环境错误或判定面塌缩（workflows 目录、登记表缺失，解析失败，受管面或 PR 面
入口为空——「什么都没判到」不等于「判过了且没问题」）。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import verify_ci_trigger_surface as categories
import workflow_run_face as run_face
import yaml

ROOT = Path(__file__).resolve().parents[1]
FACE_REGISTRY = ROOT / "contracts" / "ci" / "gate-execution-face.yaml"
MANAGED_DIRS = ("agent", "contracts", "release", "scripts")
MANAGED_PREFIXES = ("check_", "verify_")
FACES = ("ci", "manual")
# 测试面被一条 pytest 步骤整体收集：穿过它建可达性＝把「import 过」当成「当门禁跑过」
TEST_PATH = re.compile(r"(?:^|/)tests?/|_test\.py$|^conftest\.py$")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sources() -> dict[Path, str]:
    """参与闭包的非测试 py 源文件——注释与 docstring 的剔除发生在引用提取里，不在这里。"""
    out: dict[Path, str] = {}
    for path in ROOT.rglob("*.py"):
        if set(path.relative_to(ROOT).parts) & {".git", "__pycache__", "node_modules", "target"}:
            continue
        if TEST_PATH.search(rel(path)):
            continue
        out[path.resolve()] = path.read_text(encoding="utf-8", errors="ignore")
    return out


def code_refs(text: str) -> list[str]:
    """AST 里会进入代码的字符串 ＋ import 名；注释天然不在 AST 里，docstring 单独剔除。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            head = node.body[:1]
            if head and isinstance(head[0], ast.Expr) and isinstance(head[0].value, ast.Constant) \
                    and isinstance(head[0].value.value, str):
                docstrings.add(id(head[0].value))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and id(node) not in docstrings:
                out.append(node.value)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            out += [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                out.append(node.module)
    return out


def referenced(text: str, by_name: dict[str, list[Path]]) -> set[Path]:
    out: set[Path] = set()
    for ref in code_refs(text):
        normalized = ref.replace("\\", "/").strip()
        if normalized.endswith(".py"):
            if "/" in normalized and (ROOT / normalized).resolve().is_file():
                out.add((ROOT / normalized).resolve())
            out.update(by_name.get(normalized.split("/")[-1], ()))
        else:
            out.update(by_name.get(normalized.rsplit(".", 1)[-1] + ".py", ()))
    return out


def closure(entries: set[Path], src: dict[Path, str]) -> set[Path]:
    """从 PR 面入口出发、沿非测试 py 文件的代码引用做传递闭包。"""
    by_name: dict[str, list[Path]] = {}
    for path in src:
        by_name.setdefault(path.name, []).append(path)
    seen, stack = set(entries), list(entries)
    while stack:
        text = src.get(stack.pop())
        if text is None:
            continue
        for target in referenced(text, by_name):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def managed_scripts(src: dict[Path, str]) -> set[Path]:
    return {path for path in src
            if len(path.relative_to(ROOT).parts) > 1
            and path.relative_to(ROOT).parts[0] in MANAGED_DIRS
            and path.name.startswith(MANAGED_PREFIXES)}


def script_of(entry: dict) -> str:
    return str(entry.get("script") or "").replace("\\", "/").strip("/")


def load_face_registry() -> list[dict]:
    document = run_face.load_document(FACE_REGISTRY)
    if not isinstance(document, dict):
        raise ValueError("gate-execution-face.yaml 顶层必须是映射")
    entries = document.get("registered")
    if not isinstance(entries, list):
        raise ValueError("gate-execution-face.yaml 必须有 registered 列表")
    return [entry for entry in entries if isinstance(entry, dict)]


def entry_problems(entry: dict, managed_paths: set[str], pr_face: set[str],
                   ci_calls: dict[str, set[Path]], workflow_names: set[str]) -> list[str]:
    """单条登记的自洽性：字段齐、face 合法、证据真。存在性与受管归属由 violations 统一报。"""
    script = script_of(entry)
    if not script:
        return [f"登记表里有一项没有 script 字段（{entry}）——判不到路径就是空登记"]
    if script not in managed_paths:
        return []
    face = str(entry.get("face") or "")
    if face not in FACES:
        return [f"{script} 的 face={face!r} 不合法（只认 {'/'.join(FACES)}）"]
    problems = [] if str(entry.get("why") or "").strip() else [
        f"{script} 没有 why——理由是本表唯一的可读信息，也是下一轮判断该撤还是要动的依据"]
    if face == "manual":
        if entry.get("workflow"):
            problems.append(f"{script} 是 face: manual 却填了 workflow——人工面没有 CI 执行点")
        evidence = str(entry.get("evidence") or "")
        if not evidence:
            problems.append(f"{script} 是 face: manual 却没填 evidence")
            return problems
        target = (ROOT / evidence.replace("\\", "/")).resolve()
        if not target.is_file():
            problems.append(f"{script} 的 evidence={evidence!r} 文件不存在")
        elif script not in target.read_text(encoding="utf-8", errors="ignore"):
            problems.append(f"{script} 的 evidence={evidence!r} 里没有这条命令路径——「见 runbook」而 "
                            "runbook 里没有，是第二条失实陈述")
        return problems
    if entry.get("evidence"):
        problems.append(f"{script} 是 face: ci 却填了 evidence——两种面的证据形状不同，别混")
    workflow = str(entry.get("workflow") or "")
    if not workflow:
        problems.append(f"{script} 是 face: ci 却没填 workflow")
    elif workflow not in workflow_names:
        problems.append(f"{script} 的 workflow={workflow!r} 不在实树的 workflows 里")
    elif workflow in pr_face:
        problems.append(f"{script} 登记的 workflow={workflow} 就在 PR 判定面上——它已由 PR 面执行，"
                        "留在表里等于宣称它没人跑（该撤登记）")
    elif (ROOT / script).resolve() not in ci_calls.get(workflow, set()):
        problems.append(f"{script} 声称由 {workflow}.yml 执行，但该流（含本地 uses 面）的 `run:` 正文"
                        "在生效 cwd 下没调用到它——注释里的命令不算执行点（R9-B60）")
    return problems


def violations(reachable: set[Path], managed: set[Path], entries: list[dict], pr_face: set[str],
               ci_calls: dict[str, set[Path]], workflow_names: set[str]) -> list[str]:
    """可达性、登记唯一性、逐条自洽性的合判（纯函数，输入全部现读可得）。"""
    managed_paths = {rel(path) for path in managed}
    unreachable = managed_paths - {rel(path) for path in reachable}
    listed = [script_of(entry) for entry in entries]
    problems: list[str] = []
    for script in sorted(set(listed) - managed_paths - {""}):
        if (ROOT / script).is_file():
            problems.append(f"{script} 不在受管门禁面（前缀 {'/'.join(MANAGED_PREFIXES)} 于目录 "
                            "{'/'.join(MANAGED_DIRS)} 之外）——往执行面表里塞非门禁脚本它会变杂物抽屉")
        else:
            problems.append(f"登记表引用了不存在的脚本：{script}（表要跟着实树走）")
    for script in sorted(unreachable):
        count = listed.count(script)
        if count == 0:
            problems.append(f"{script} 在 PR 判定面上不可达，也没登记执行面"
                            "——现在没有任何判据知道它该不该跑")
        elif count > 1:
            problems.append(f"{script} 被登记了 {count} 次——两份会在不同批次各自漂移（R9-B61 同族）")
    for script in sorted(set(listed) & managed_paths - unreachable):
        problems.append(f"{script} 已在 PR 判定面上可达，仍留在登记表里——该撤登记")
    for entry in entries:
        problems += entry_problems(entry, managed_paths, pr_face, ci_calls, workflow_names)
    return problems


def run() -> int:
    if not categories.WORKFLOWS.is_dir():
        print(f"::error:: 缺 workflows 目录：{categories.WORKFLOWS}", file=sys.stderr)
        return 2
    if not FACE_REGISTRY.is_file():
        print(f"::error:: 缺执行面登记表：{FACE_REGISTRY}", file=sys.stderr)
        return 2
    try:
        names = categories.workflow_files()
        triggers = categories.parsed_triggers(names)
        entries = load_face_registry()
        src = sources()
    except (yaml.YAMLError, ValueError, OSError) as exc:
        print(f"::error:: 解析失败：{exc}", file=sys.stderr)
        return 2
    pr_face = {name for name, body in triggers.items() if "pull_request" in body}
    ci_calls = run_face.calls_by_workflow(names)
    # 入口只取 PR 判定面：把 builds/probes 的调用点也算进来，等于用「发布流里有一行」替「有人判它」，
    # 而那正是这条判据要防的形状
    called = {path for name in pr_face for path in ci_calls.get(name, set())}
    managed = managed_scripts(src)
    if not names or not pr_face or not called or not managed:
        print(f"::error:: 判定面塌缩（workflow {len(names)}、PR 面 {len(pr_face)}、"
              f"入口调用点 {len(called)}、受管脚本 {len(managed)}）", file=sys.stderr)
        return 2
    reachable = closure(called, src) & managed
    problems = violations(reachable, managed, entries, pr_face, ci_calls, names)
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条违规（判据见本文件 docstring）", file=sys.stderr)
        return 1
    print(f"[ok] {len(managed)} 个受管门禁脚本：{len(reachable)} 个在 PR 判定面上可达"
          f"（入口来自 {len(pr_face)} 份 workflow 的 run 正文＋本地 uses 面），"
          f"{len(managed) - len(reachable)} 个已登记执行面且证据可回读")
    return 0


if __name__ == "__main__":
    sys.exit(run())
