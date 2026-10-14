"""WebView2 下载面静态探测的接线判据（第九轮 R9-B56 / 台账 §五 Q58 = R9-CS-18 第一步）。

探测本体是 `windows/tools/WebView2SdkSurfaceProbe`（静态反射：SDK 属性/事件/Runtime 版本），
挂在 `compat.yml`（每周 + 手动 dispatch），**不是** PR 门禁。本文件判的是「这套东西
还接得住」的三件事：

1. **同一把 SDK**：不出货的工具没有 `packages.lock.json`（这是有意的偏离——理由写在
   csproj 里，因为 `verify_lock_rids.py` 的 REQUIRED_* 语义是「出货依赖面」）。
   于是「探针测的就是出货那份 SDK」只能靠现读两个 csproj 的 PackageReference 版本对账；
   不对账的话，探针会安静地量成另一版 SDK，而报告看起来一模一样。
2. **调用点与产物名同源**：workflow 里那条 exe 路径里的装配名必须等于 csproj 的
   `AssemblyName`——改名时漏一处，红的是 CI 而不是「本地能跑」。
3. **探测的退出码纪律**：`set -euo pipefail` 要在、不许 `|| true`、报告里必须出现
   `TYPE`/`runtime_version=` 行——空报告配上 exit 0 就是判据在判空气（本仓反复记的那类）；
4. **忽略规则按形状而不是按目录名点名**：本批第一次 build 就把 `windows/tools/.../bin/`
   摆进了 `git status`，因为 .gitignore 写的是 `windows/src/**/bin/`。判法用
   `git check-ignore --no-index` 去问一个**还没存在过的路径**，配一条「源码不能被忽略」
   的正面控制，否则规则一旦被写宽这条用例也会跟着恒真。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "contracts" / "codegen"))

TOOL_DIR = ROOT / "windows" / "tools" / "WebView2SdkSurfaceProbe"
COMPAT = ROOT / ".github" / "workflows" / "compat.yml"
APP_CSPROJ = ROOT / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj"
PACKAGE = "Microsoft.Web.WebView2"
JOB = "webview2-download-surface"


def package_version(text: str) -> str:
    """csproj 里某包的 Version= 值（现读，不假设书写顺序）。"""
    m = re.search(rf'PackageReference Include="{PACKAGE}" Version="([^"]+)"', text)
    if not m:
        raise AssertionError(f"读不到 {PACKAGE} 的版本号——写法变了就同步这里")
    return m.group(1)


def assembly_name() -> str:
    text = (TOOL_DIR / "WebView2SdkSurfaceProbe.csproj").read_text(encoding="utf-8")
    m = re.search(r"<AssemblyName>([^<]+)</AssemblyName>", text)
    assert m, "探针 csproj 没有 AssemblyName——workflow 里的 exe 路径就没有单源了"
    return m.group(1)


def compat_doc() -> dict:
    return yaml.safe_load(COMPAT.read_text(encoding="utf-8"))


def job_steps() -> list[dict]:
    doc = compat_doc()
    steps = ((doc.get("jobs") or {}).get(JOB) or {}).get("steps")
    assert isinstance(steps, list), f"compat.yml 缺 {JOB} job 的 steps——探测掉线了"
    return steps


def wiring_problems(steps: list[dict], name: str) -> list[str]:
    """纯函数：给定 job 的 steps，返回探测接线的问题。注入用例走同一份判定。"""
    problems: list[str] = []
    bodies = [str(s["run"]) for s in steps if isinstance(s.get("run"), str)]
    hit = [b for b in bodies if f"{name}.exe" in b]
    if not hit:
        problems.append(f"没有任何步骤跑 {name}.exe——探测没接上")
    for body in hit:
        if "set -euo pipefail" not in body:
            problems.append("探测步骤没有 set -euo pipefail")
        if "|| true" in body:
            problems.append("探测步骤里有 `|| true`：量不到也绿＝探测变成装饰")
        if not re.search(r"grep\s+-q\s+'\^TYPE", body):
            problems.append("缺「报告里必须有 TYPE 行」这条空报告判据")
    for step in steps:
        if step.get("uses", "").startswith("actions/upload-artifact"):
            if step.get("with", {}).get("if-no-files-found") != "error":
                problems.append("探测报告的 artifact 上传不是 error 档：报告没了也绿")
    return problems


def test_tool_and_job_exist() -> None:
    assert (TOOL_DIR / "Program.cs").is_file(), "探针源码不在树里"
    steps = job_steps()
    assert wiring_problems(steps, assembly_name()) == [], wiring_problems(steps, assembly_name())


def test_probe_uses_the_same_sdk_version_as_the_shipping_app() -> None:
    """两份版本号必须逐字相同——否则报告量的是另一版 SDK，而它读起来一样可信。"""
    tool = (TOOL_DIR / "WebView2SdkSurfaceProbe.csproj").read_text(encoding="utf-8")
    assert package_version(tool) == package_version(APP_CSPROJ.read_text(encoding="utf-8")), (
        f"探针与正典 App 的 {PACKAGE} 版本不一致——探测结论不能外推到出货制品")


def test_probe_is_a_scheduled_probe_not_a_required_check() -> None:
    """这是探测：compat 只有定时 + 手动触发。把它挂进 PR 必需检查会造出
    「Windows runner 排队 = 全仓 PR 卡死」的形状，而它给的是事实表不是判决。"""
    doc = compat_doc()
    triggers = doc.get("on") or doc.get(True) or {}
    assert "pull_request" not in triggers and "push" not in triggers, (
        f"compat.yml 的触发面变成了 {sorted(triggers)}——探测进了合并门，请重读本用例")


def test_dropped_wiring_is_red() -> None:
    """注入必红：把 exe 名字改错 / 加 `|| true` / 换掉 AssemblyName，都得被同一份判定抓住。"""
    good = job_steps()
    assert wiring_problems(good, assembly_name()) == []
    assert wiring_problems(good, "not_the_probe"), "改名之后还判绿＝调用点是假接上的"
    with_true = [dict(s, run=f"{s['run']} || true") if isinstance(s.get("run"), str) else s for s in good]
    assert wiring_problems(with_true, assembly_name()), "`|| true` 加回去了却不被判红"
    no_pipe = [dict(s, run=s["run"].replace("set -euo pipefail", "")) if isinstance(s.get("run"), str) else s
               for s in good]
    assert wiring_problems(no_pipe, assembly_name()), "丢了 pipefail 不被判红（tee 之后的退出码就没人管了）"


def test_report_assertion_survives_only_when_lines_exist() -> None:
    """现读探针自己的输出契约：它打印的确实是 `TYPE`/`runtime_version=` 这些行，
    否则上面那条 grep 是在等一个永远不会出现的模式。"""
    source = (TOOL_DIR / "Program.cs").read_text(encoding="utf-8")
    for needle in ("runtime_version=", "TYPE_ABSENT", "  PROP ", "  EVENT "):
        assert needle in source, f"探针不再打印「{needle}」——workflow 里等它的 grep 就成了死判据"


def test_build_output_is_ignored_by_shape_not_by_directory_name() -> None:
    """`.gitignore` 里那条得匹配**任意** windows 工程形状的 bin/，不是只点 src 的名。

    这条是本批自己撞出来的：第一版规则只有 `windows/src/**/bin/`，`windows/tools/` 一 build
    就把产物摆进 `git status`——下一次谁再加 `windows/benchmarks/` 会再撞一遍。
    用 `--no-index` 问假想路径，所以不需要真的先造出产物。
    """
    for path in ("windows/tools/Whatever/bin/Debug/a.dll",
                 "windows/src/Aegis.Windows.App/bin/Release/a.dll",
                 "windows/tests/Aegis.Windows.Core.Tests/bin/Release/a.dll"):
        r = subprocess.run(["git", "check-ignore", "--no-index", "-q", path],
                           cwd=ROOT, capture_output=True, text=True, check=False)
        assert r.returncode == 0, f"{path} 不被任何忽略规则匹配——构建产物会进 git status"


def test_probe_source_is_not_swept_up_by_that_rule() -> None:
    """上一条的正面控制：忽略规则不能宽到把工具源码本身也吃掉。

    少了这条，「把 windows/** 全忽略」也能让上一条全绿——那正是白名单式规则最常见的
    反向失效（R9-B47/R9-B51 同一条纪律：豁免与规则自己也要被判）。
    """
    r = subprocess.run(["git", "check-ignore", "--no-index", "-q",
                        "windows/tools/WebView2SdkSurfaceProbe/Program.cs"],
                       cwd=ROOT, capture_output=True, text=True, check=False)
    assert r.returncode != 0, "探针源码被忽略规则命中了——上一条的绿就没有意义"
