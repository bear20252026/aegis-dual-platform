# gate_execution_face_test.py —— R9-B62 执行面登记判据的门禁用例（口径与 ffi_input_bounds_test.py 同）。
#
# 先证现树一致，再把每条判据要拦的形状逐个摆上去看它红不红——不改工作树，全部内存注入。
# 两条「现读锚」不靠注入：`test_a_command_inside_a_comment_is_not_an_execution_point` 直接拿
# release.yml 的 191-195 行注记 vs 188 行真调用做对照（同一份文件里一字之差，一边算执行点一边不算），
# `test_a_docstring_mention_is_not_a_call_site` 拿 docstring vs 代码字符串做对照。没有这两条，
# 判据可以在「其实按原文正则算」的形态下全绿。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_gate_execution_face as g
import workflow_run_face as run_face


@pytest.fixture(scope="module")
def face():
    """现读一遍判定面：workflow 分类、run 正文调用点、非测试闭包、受管脚本、登记表。"""
    names = g.categories.workflow_files()
    triggers = g.categories.parsed_triggers(names)
    pr_face = {n for n, body in triggers.items() if "pull_request" in body}
    ci_calls = run_face.calls_by_workflow(names)
    src = g.sources()
    called = {path for name in pr_face for path in ci_calls.get(name, set())}
    managed = g.managed_scripts(src)
    return {"names": names, "pr_face": pr_face, "ci_calls": ci_calls, "managed": managed,
            "reachable": g.closure(called, src) & managed, "entries": g.load_face_registry()}


def problems(fixture: dict, entries: list[dict]) -> list[str]:
    return g.violations(fixture["reachable"], fixture["managed"], entries,
                        fixture["pr_face"], fixture["ci_calls"], fixture["names"])


def any_with(lines: list[str], needle: str) -> bool:
    return any(needle in line for line in lines)


def test_real_tree_registry_matches_the_unreachable_managed_face(face):
    """现读：登记表面跟实树一致；规模塌了就报环境错而不是「没问题」。"""
    assert len(face["names"]) >= 16, f"workflow 面塌缩：{len(face['names'])}"
    assert len(face["pr_face"]) >= 7, f"PR 判定面塌缩：{len(face['pr_face'])}"
    assert len(face["managed"]) >= 30, f"受管门禁面塌缩：{len(face['managed'])}"
    assert len(face["reachable"]) >= 25, f"可达面塌缩：{len(face['reachable'])}"
    assert len(face["entries"]) >= 5, f"登记表塌缩：{len(face['entries'])}"
    assert problems(face, face["entries"]) == []


def test_unreachable_script_without_registration_goes_red(face):
    """R9-CI-4 的形状：门禁写好了，没有任何面判它该不该跑。"""
    entries = [e for e in face["entries"] if e["script"] != "release/verify_checksum_json.py"]
    lines = problems(face, entries)
    assert any_with(lines, "release/verify_checksum_json.py") and any_with(lines, "没登记执行面"), lines


def test_same_script_registered_twice_goes_red(face):
    """两份会在不同批次各自漂移（R9-B61 同族）。"""
    victim = next(e for e in face["entries"] if e["script"] == "release/verify_checksum_json.py")
    lines = problems(face, face["entries"] + [dict(victim)])
    assert any_with(lines, "被登记了 2 次"), lines


def test_reachable_script_left_in_the_registry_goes_red(face):
    """接进 PR 面之后不撤登记＝表烂成杂物抽屉，读的人以为它没人跑。"""
    reachable = sorted(g.rel(path) for path in face["reachable"])[0]
    lines = problems(face, face["entries"] + [{"script": reachable, "face": "manual",
                                               "evidence": "release/runbooks/security-release.md",
                                               "why": "已接进 PR 面却留着"}])
    assert any_with(lines, "该撤登记"), lines


def test_ci_face_claim_without_a_real_call_site_goes_red(face):
    """声称由某个非 PR 面 workflow 执行，而那条流的 run 正文里没有这个调用点。"""
    called = (ROOT / "release/verify_checksum_json.py").resolve()
    non_pr = sorted(n for n in face["names"] - face["pr_face"] if called not in face["ci_calls"][n])
    assert non_pr, "所有非 PR 面都调用它——本用例的注入面不存在，需重判"
    victim = next(e for e in face["entries"] if e["script"] == "release/verify_checksum_json.py")
    entry = {**victim, "workflow": non_pr[0]}
    lines = problems(face, [e for e in face["entries"] if e is not victim] + [entry])
    assert any_with(lines, "没调用到它"), lines


def test_registering_a_pr_face_workflow_goes_red(face):
    """`face: ci` 指向 PR 判定面上的流——它已在常跑面上跑，登记本身是假陈述。"""
    pr_workflow = sorted(face["pr_face"])[0]
    victim = next(e for e in face["entries"] if e["script"] == "release/verify_checksum_json.py")
    entry = {**victim, "workflow": pr_workflow}
    lines = problems(face, [e for e in face["entries"] if e is not victim] + [entry])
    assert any_with(lines, "就在 PR 判定面上"), lines


def test_manual_face_without_the_command_in_its_evidence_goes_red(face):
    """写「见 runbook」而那份文件里没有这条命令，就是第二条失实陈述。"""
    victim = next(e for e in face["entries"] if e["script"] == "release/verify_checksum_json.py")
    entry = {**victim, "face": "manual", "evidence": "contracts/ci/workflow-categories.yaml"}
    lines = problems(face, [e for e in face["entries"] if e is not victim] + [entry])
    assert any_with(lines, "里没有这条命令路径"), lines


def test_evidence_file_that_does_not_exist_goes_red(face):
    victim = next(e for e in face["entries"] if e.get("face") == "manual")
    entry = {**victim, "evidence": "release/runbooks/no-such-runbook.md"}
    lines = problems(face, [e for e in face["entries"] if e is not victim] + [entry])
    assert any_with(lines, "文件不存在"), lines


def test_registration_of_a_nonexistent_script_goes_red(face):
    lines = problems(face, face["entries"] + [{"script": "scripts/verify_no_such_gate.py",
                                               "face": "manual", "evidence": "README.md", "why": "x"}])
    assert any_with(lines, "不存在的脚本"), lines


def test_registration_of_a_non_gate_script_goes_red(face):
    """表里塞辅助模块（存在、但不在 verify_/check_ 受管面）会让它变成杂物抽屉。"""
    assert (ROOT / "scripts/text_anchors.py").is_file()
    lines = problems(face, face["entries"] + [{"script": "scripts/text_anchors.py",
                                               "face": "manual", "evidence": "README.md", "why": "x"}])
    assert any_with(lines, "不在受管门禁面"), lines


@pytest.mark.parametrize("mutation,needle", [
    ({"why": ""}, "没有 why"),
    ({"face": "maybe"}, "不合法"),
    ({"face": "ci", "workflow": None}, "没填 workflow"),
    ({"face": "manual", "evidence": None}, "没填 evidence"),
    ({"face": "ci", "evidence": "README.md"}, "却填了 evidence"),
    ({"face": "manual", "workflow": "release"}, "却填了 workflow"),
])
def test_field_shape_problems_go_red(face, mutation, needle):
    """字段形状：该带的缺了判红、不该带的乱填也判红（同一支脚本，逐个改一个字段）。"""
    victim = next(e for e in face["entries"] if e["script"] == "release/verify_checksum_json.py")
    entry = {**victim, **mutation}
    entry = {k: v for k, v in entry.items() if v is not None}
    lines = problems(face, [e for e in face["entries"] if e is not victim] + [entry])
    assert any_with(lines, needle), lines


def test_a_command_inside_a_comment_is_not_an_execution_point(face):
    """现读对照：同一份 release.yml 里 188 行的真调用算执行点，195 行抄成注释的命令不算。"""
    release_calls = face["ci_calls"]["release"]
    assert (ROOT / "release/verify_release.py").resolve() in release_calls
    assert (ROOT / "release/tools/verify_artifact_set/verify_artifact_set.py").resolve() \
        not in release_calls, "注释里的命令被执行面收进来了——判据会假绿"


def test_a_docstring_mention_is_not_a_call_site():
    """口径③的对照：docstring 与注记里的文件名都不进入代码引用，只有会执行的字符串算。"""
    text = (
        '"""本说明里写了 scripts/verify_docstring_only.py，那不是调用点。"""\n'
        "import scripts.verify_ci_trigger_surface\n"
        'RUN = "python scripts/verify_real_call_site.py"\n'
    )
    refs = g.code_refs(text)
    assert any("verify_real_call_site.py" in ref for ref in refs), refs
    assert not any("verify_docstring_only.py" in ref for ref in refs), refs


def test_closure_does_not_pass_through_the_test_face(face):
    """口径②：pytest 一条步骤收集整个 tests 目录，穿过它建可达性＝判据恒真。"""
    on_disk = sorted((ROOT / "tests" / "python").glob("*_test.py"))
    assert len(on_disk) >= 20, f"测试面本身塌缩：{len(on_disk)}"
    src = g.sources()
    assert not any(path.resolve() in src for path in on_disk), "闭包面里混进了测试文件"
    assert len(src) >= 100, f"闭包面塌缩：{len(src)}"


def test_missing_registry_is_an_environment_error(tmp_path, monkeypatch):
    """判定面塌缩必须是 exit 2，不是「读不到东西＝通过」。"""
    monkeypatch.setattr(g, "FACE_REGISTRY", tmp_path / "absent.yaml")
    assert g.run() == 2


def test_missing_workflow_dir_is_an_environment_error(tmp_path, monkeypatch):
    monkeypatch.setattr(g.categories, "WORKFLOWS", tmp_path / "no-workflows")
    assert g.run() == 2
