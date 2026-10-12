"""项 10 / AEG-011（第九轮，2026-10-11 用户定稿「全部完成」）：Android 依赖锁定**声明侧**门禁。

启用 `dependencyLocking` 之后，「谁被锁了」这件事需要机器判：

- 锁块单源写在 root `android/build.gradle.kts` 的 `subprojects` 作用域里（声明一次即覆盖
  全部现有与后续子模块；逐模块各写一份的话，「新增第五个模块忘记加锁」是静默的
  fail-open）。所以两道都判：root 必须有那份锁块且**只有一份**，模块脚本必须**没有**
  自己的副本（两份真相必然漂移）。模块清单从 `settings.gradle.kts` 的 `include(...)`
  现取——在测试里再抄一份名单的话，新增模块就永远落在判据之外。
- 同一处还注册了两个任务（PR 面的覆盖判据 + 重锁面的全量解析入口）。本文件判「它们存在」；
  CI 是否真在 PR 面跑那条判据由 `relock_sop_test.py` 判，锁文件自身的形态与覆盖面在
  `gradle_lockfile_shape_test.py`（本仓 300 行新文件红线也正好把两侧切开）。
- 文本锚的口径（本仓反复踩过的三件套）：判代码不判注释（注记里逐字抄着被禁形态）、
  切片有边界、每条锚都配注入式反向锚（把锁块拆开必须判红）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
SETTINGS = ANDROID / "settings.gradle.kts"
ROOT_SCRIPT = ANDROID / "build.gradle.kts"

# root 脚本里那份锁块（注释不参与比对——注记会各自措辞，代码形态漂移才是真问题：
# 少了 lockMode 就退化成「靠缺省值」）。比对按**去缩进**形态做：块在 `subprojects {}`
# 里必然带缩进，写死四空格就是比排版而不是比内容。注入用同一正则（容忍任意缩进），
# 否则「删掉某行」会删不掉⇒锚恒真。
LOCKING_BLOCK = """dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}"""
_BLOCK_RE = re.compile(
    r"^[ \t]*dependencyLocking \{\n"
    r"[ \t]*lockAllConfigurations\(\)\n"
    r"[ \t]*lockMode = LockMode\.STRICT\n"
    r"[ \t]*\}[ \t]*\n",
    re.MULTILINE)
_MODE_RE = re.compile(r"\n[ \t]*lockMode = LockMode\.STRICT(?=\n)")
LOCKING_BLOCK_FLAT = "\n".join(line.strip() for line in LOCKING_BLOCK.splitlines())

# R9-B32（2026-10-12）：锁的覆盖面判据（PR 面跑）与全量解析入口（重锁面跑）
COVERAGE_TASK = "verifyDependencyLockCoverage"
RESOLVE_TASK = "resolveAllConfigurations"


def kotlin_code(text: str) -> str:
    """剔掉 `//` 行注释（口径见模块 docstring：注记里抄着被禁形态）。"""
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("//"))


def dedent_code(text: str) -> str:
    """`kotlin_code` 之后再逐行去掉行首缩进（只用于块形态比对）。"""
    return "\n".join(line.strip() for line in kotlin_code(text).splitlines())


def module_names() -> list[str]:
    """模块清单从 settings 现取——抄一份名单进测试，判据就永远停在旧名单上。"""
    text = SETTINGS.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'include\(":([A-Za-z0-9_\-]+)"\)', text)))


def locking_problems(root_text: str) -> list[str]:
    """纯函数：给定 root 构建脚本，返回「锁没到位」的问题列表（便于内存态注入）。"""
    code = kotlin_code(root_text)
    flat = dedent_code(root_text)
    problems: list[str] = []
    if "subprojects {" not in code:
        problems.append("锁块没写在 subprojects 作用域里（新增模块会静默不锁＝fail-open）")
    if LOCKING_BLOCK_FLAT not in flat:
        problems.append("缺 lockAllConfigurations() + LockMode.STRICT 的锁块")
    if code.count("dependencyLocking") > 1:
        problems.append("root 里有两份锁块——单源就是单源")
    if "lockMode" in code and "LockMode.STRICT" not in code:
        problems.append("写了 lockMode 但不是 STRICT（靠缺省值＝缺省一变即静默放松）")
    return problems


def module_script_problems() -> list[str]:
    """模块脚本面：脚本必须存在，且**不得**自带 `dependencyLocking` 副本。"""
    offenders: list[str] = []
    for name in module_names():
        script = ANDROID / name / "build.gradle.kts"
        if not script.exists():
            offenders.append(f":{name} 的构建脚本不存在")
        elif "dependencyLocking" in kotlin_code(script.read_text(encoding="utf-8")):
            offenders.append(f":{name} 自带锁副本")
    return offenders


def test_module_list_comes_from_settings_not_a_hardcoded_copy() -> None:
    names = module_names()
    assert names, "settings.gradle.kts 里一条 include 都没解析到——扫描面塌了"
    assert {"app", "broker", "webview-adapter", "contracts"} <= set(names), (
        f"四个已知模块必须在 settings 的清单里（实得 {names}）——本门禁的覆盖面定义"
    )


def test_root_declares_locking_once_and_modules_carry_no_copies() -> None:
    assert not locking_problems(ROOT_SCRIPT.read_text(encoding="utf-8")), (
        "root 构建脚本里的锁块不合格（须在 subprojects 作用域内、"
        "含 lockAllConfigurations() 与 LockMode.STRICT、且只有一份）"
    )
    dupes = module_script_problems()
    assert not dupes, f"模块脚本面不干净（单源被破坏）：{dupes}"


def test_deleting_the_locking_block_turns_the_gate_red() -> None:
    """反向锚（内存态注入，不改工作树）：把锁块拆开必须判红。

    只判「脚本里有没有那段文本」的用例，最常见的失效形态是判据本身恒真——
    这里用真脚本的副本做注入，证明判定真的落在代码上。"""
    real = ROOT_SCRIPT.read_text(encoding="utf-8")
    assert locking_problems(real) == [], "真脚本本身就该通过（否则上一条用例在判空气）"
    match = _BLOCK_RE.search(real)
    assert match, "root 脚本里正则匹配不到那段锁块——注入会因「删不掉」而假装通过"
    injections = {
        "拆掉 subprojects 包裹": real.replace("subprojects {", "{", 1),
        "删掉 lockMode 行": _MODE_RE.sub("", real),
        "删掉整块": _BLOCK_RE.sub("", real),
        "复制成两份": real.replace(match.group(0), match.group(0) * 2, 1),
    }
    for name, injected in injections.items():
        assert locking_problems(injected), f"注入「{name}」后必须判红——否则这条锚恒真"


def test_root_script_registers_both_lock_tasks() -> None:
    """覆盖判据与全量解析入口都必须真实存在——CI 那几步敲的就是这两个任务名。"""
    code = kotlin_code(ROOT_SCRIPT.read_text(encoding="utf-8"))
    for task in (COVERAGE_TASK, RESOLVE_TASK):
        assert f'tasks.register("{task}")' in code, (
            f"root 脚本里没有 {task}——判据/重锁入口没了，CI 那一步会报「任务不存在」"
        )
    # 定义判据的地方不能顺手写锁：那等于「自己写自己判」，恒绿
    assert "--write-locks" not in code, "构建脚本定义判据，不调用重锁开关"


def test_settings_records_the_relock_sop_and_the_uncovered_surface() -> None:
    """决策记录必须写明三件容易被读错的事：锁不覆盖脚本类路径、不含校验和、SOP 指向哪儿。"""
    text = SETTINGS.read_text(encoding="utf-8")
    assert "buildscript" in text, "settings 没登记 buildscript/plugins 类路径不在锁内"
    assert "校验和" in text, "settings 没登记锁不含校验和（哈希验证是另一刀）"
    assert "dependency-relock.yml" in text, "settings 没指回重锁执行面"
    assert "gradle.lockfile" in text, "settings 没说锁文件落在哪儿（重锁后要有人找它）"
    assert RESOLVE_TASK in text, "settings 的重锁 SOP 必须指向全量解析入口，不是任务清单"


def test_security_doc_matches_the_tree() -> None:
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Gradle 依赖无 lock 文件" not in text, "SECURITY.md 仍声称 Android 无锁文件"
    assert "gradle.lockfile" in text, "SECURITY.md 没登记四把 gradle 锁"
    assert "不含校验和" in text, "SECURITY.md 必须如实写「版本锁定不含 hash」"
