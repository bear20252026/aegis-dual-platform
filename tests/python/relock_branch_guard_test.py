"""`scripts/relock_branch_guard.sh` 的行为判据（第九轮 R9-B58 / 台账 §五 Q60）。

Dependency-Retlock 是**手工触发 + 持 `contents: write`** 的作业，它能造成的唯一越界就是「推到哪」。
原来这条边界内联在三个 job 的两处步骤里（`case "$target" in deps/*)`）；Q60 需要第二类目标
——Dependabot 的 Gradle bump PR 分支名是 `dependabot/…`，不在 `deps/*` 面内，于是新依赖的
sha256 校验和没有自动补录路径，bump PR 只能红着等人手工跑生成命令。
把前缀改成「按 kind 选」如果内联抄六遍，就是六份可以各自漂移的真相 ⇒ 规则收进脚本。

**判法是真调 bash**，不是文本锚：文本锚管不住「少写一个括号」「`[[ ]]` 写成 `[ ]`」
「前缀比较用了 `=` 而不是模式匹配」这类错，而这些恰恰都是本仓在 shell 面上记过的形态
（`cmd | tail; echo $?` 读错退出码就是同一族）。所以：
- 正反案例各跑一遍，断言的是**退出码**（0=允许、2=拒绝）而不是 stdout 措辞；
- 每种拒绝还要**指名是哪条规则**拒的（见下面 `rule` 列）——只断言「exit 2 + stderr 非空」时，
  把主干检查整段删掉依然 22 条全绿（前缀通配顺带把 `master` 拒了），注释里那句「独立检查」
  就成了没人作证的主张。这条是本文件的变异测试跑出来的，不是先想到的；
- 依赖 `bash` 存在；没有 bash 就抛出去而不是跳过——一条会被跳过的判据等于没有判据。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "relock_branch_guard.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-relock.yml"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if bash is None:
        # 不 skip：跳过会让这条判据在「装了但没测」的机器上永远绿。
        raise AssertionError("找不到 bash——本判据无法执行，请修环境而不是让它静默通过")
    return subprocess.run([bash, str(GUARD), *args], capture_output=True, text=True, check=False)


# ---------------------------------------------------------------- 允许面

@pytest.mark.parametrize(("face", "kind", "branch"), [
    ("dotnet", "deps", "deps/relock-round8"),
    ("gradle", "deps", "deps/r9-b50-gradle-verification"),
    # 三条**真实** Dependabot 分支名（`gh pr list --json headRefName` 现读，段数 3/4/5）：
    # 补录面必须对它们全部成立，任何「按段数限形」的写法都会关掉其中一档。
    ("gradle", "dependabot", "dependabot/pip/cryptography-50.0.2"),
    ("gradle", "dependabot", "dependabot/gradle/android/minor-and-patch-0bc2cf4c4f"),
    ("gradle", "dependabot", "dependabot/github_actions/gradle/actions/dependency-submission-6.4.0"),
    # Gradle 面才是本仓真正要补字节的生态（pip/cargo/github_actions 的分支列在这里只判「形状允许」，
    # 具体写回哪条分支由 dispatch 输入与 ecosystem 决定）。
    ("gradle", "dependabot", "dependabot/gradle/android/org.bouncycastle-bcprov-jdk18on-1.86"),
])
def test_allowed_targets_exit_zero(face: str, kind: str, branch: str) -> None:
    r = run(face, kind, branch)
    assert r.returncode == 0, f"{face}/{kind}/{branch} 应当允许，实得 {r.returncode}：{r.stderr.strip()}"


# ---------------------------------------------------------------- 拒绝面

# 每种拒绝都带**期望的 rule 措辞**（最后一列），而不是只断言 exit 2 + stderr 非空：
# 变异测试实测过「只断言退出码」的代价——把主干检查整段删掉，`master` 仍会被前缀通配顺带拒掉，
# 于是 22 条全绿而「独立检查」这句注释已经变假。前缀规则能兜住主干是巧合，不是设计；
# 设计是**每条规则都要能为自己作证**，所以措辞进判据。
@pytest.mark.parametrize(("face", "kind", "branch", "why", "rule"), [
    ("gradle", "deps", "master", "主干", "目标分支是主干"),
    ("gradle", "dependabot", "master", "主干即使在 dependabot 面也拒", "目标分支是主干"),
    ("gradle", "deps", "main", "主干别名", "目标分支是主干"),
    ("gradle", "deps", "refs/heads/deps/x", "完整 ref 形态", "短名而不是完整 ref"),
    # ref 不止 refs/heads 一种形态；只写 `refs/heads/*` 的窄化变异就是被这条抓出来的。
    ("gradle", "deps", "refs/remotes/origin/master", "完整 ref 的其它分支", "短名而不是完整 ref"),
    ("gradle", "deps", "deps/../master", "路径式解释", "含 '..'"),
    ("gradle", "dependabot", "deps/x", "跨类：dependabot 面不许写 deps 分支", "只允许写 dependabot/"),
    ("gradle", "deps", "dependabot/gradle/x", "跨类：deps 面不许写 dependabot 分支", "只允许写 deps/"),
    ("dotnet", "dependabot", "dependabot/nuget/newtonsoft-1.0.0", "dotnet 面没有 dependabot 补录",
     "face=dotnet 没有 dependabot"),
    ("gradle", "deps", "deps/", "只有前缀没有名字", "只允许写 deps/"),
    ("gradle", "dependabot", "dependabot/", "只有前缀没有名字", "只允许写 dependabot/"),
    ("gradle", "deps", "depsx/y", "前缀必须带斜杠", "只允许写 deps/"),
    ("gradle", "DEPS", "deps/x", "kind 大小写不是可选项", "kind 只能是"),
    ("gradle", "both", "deps/x", "kind 是闭集", "kind 只能是"),
    ("weird", "deps", "deps/x", "face 是闭集", "face 只能是"),
    ("gradle", "", "deps/x", "空 kind 不能靠默认值蒙过去", "kind 只能是"),
    ("gradle", "deps", "", "空分支名", "只允许写 deps/"),
])
def test_rejected_targets_exit_two_with_reason(
    face: str, kind: str, branch: str, why: str, rule: str) -> None:
    r = run(face, kind, branch)
    assert r.returncode == 2, f"{why}：应当 exit 2，实得 {r.returncode}（{r.stdout.strip()}）"
    assert rule in r.stderr, (
        f"{why}：exit 2 但不是这条规则拒的（实得 stderr：{r.stderr.strip()}）"
        "——措辞要对得上，否则运维日志里指不到规则，独立检查也就没了证据")


# ---------------------------------------------------------------- 调用点

def test_every_write_capable_job_calls_the_guard_twice() -> None:
    """三个持写权限的 job 各自「job 级 + 写回级」都要调守卫——二次守卫不依赖第一步存在。

    判 yaml 结构而不是数文件里的字符串次数：把调用挪进一个 composite action 也应该被这里
    认可（那是单源方向），但**少一处调用**必须红。
    """
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or {}
    assert jobs, "workflow 里没有 jobs——提取口径坏了"
    writers = [name for name, job in jobs.items()
               if any("写回分支" in str(step.get("name", "")) for step in job.get("steps", []) or [])]
    assert len(writers) == 3, f"持写权限的 job 数量变了（{writers}）——本判据的口径要同步改"
    missing = [name for name in writers
               if sum("relock_branch_guard.sh" in str(step.get("run", ""))
                      for step in jobs[name].get("steps", []) or []) < 2]
    assert not missing, f"这些 job 的守卫调用少于两处：{missing}"


def test_every_guard_call_sits_after_a_checkout() -> None:
    """守卫是**一份仓库脚本**，所以每个调用点前面必须有 checkout——否则 workspace 里根本没有这个文件。

    这条不是理论：把守卫放在「检出目标分支」之前时，dispatch 在 Actions 里红在
    `bash: scripts/relock_branch_guard.sh: No such file or directory`（run 38520687580），
    而当时上面那条判据（数调用点）全绿——「调用点存在」和「调用点能执行」是两件事。
    runner 的 workspace 在第一次 `actions/checkout` 之前是空的，这是 Actions 的事实，不是本仓的约定。
    """
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for name, job in (doc.get("jobs") or {}).items():
        steps = job.get("steps", []) or []
        checkout_at = [i for i, s in enumerate(steps)
                       if "actions/checkout" in str(s.get("uses", ""))]
        guard_at = [i for i, s in enumerate(steps)
                    if "relock_branch_guard.sh" in str(s.get("run", ""))]
        if not guard_at:
            continue
        assert checkout_at, f"job {name} 调了守卫却没有任何 checkout——脚本无从存在"
        for index in guard_at:
            assert index > min(checkout_at), (
                f"job {name} 第 {index} 步调守卫，早于第 {min(checkout_at)} 步的 checkout："
                "workspace 还没有 scripts/relock_branch_guard.sh")


def test_guard_script_is_not_a_dead_file() -> None:
    """脚本本身要能被解析（bash -n），且 workflow 的 header 提到的单源路径就是它。"""
    bash = shutil.which("bash")
    assert bash
    assert subprocess.run([bash, "-n", str(GUARD)], capture_output=True, text=True,
                          check=False).returncode == 0
    header = WORKFLOW.read_text(encoding="utf-8").split("name: Dependency-Retlock")[0]
    assert "scripts/relock_branch_guard.sh" in header, (
        "workflow 头注里那条硬边界的单源路径没提脚本——下一次有人在内联再抄一份规则时，"
        "读者不会知道该改哪儿")
