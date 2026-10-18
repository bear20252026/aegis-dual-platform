"""「固定 toolchain」的声明与实树必须一致（第八轮 B7，R8-DEPS-2 的执行面）。

成因（本仓自己的两处声明 vs 实树）：`core/rust-policy-core/Cargo.toml` 的依赖注与
`docs/adr/ADR-005` 的决策条都把「固定 toolchain」写成蓝图口径，而仓库根既没有
`rust-toolchain.toml`，workflow 里 9 处又全用 `toolchain: stable` ⇒ 同一 commit 隔月
重跑出来的 `aegis_policy_core.dll` 字节可变，自建哈希基线与 release 台账对账会周期性
失配。`dtolnay/rust-toolchain` 没有 `toolchain: file` 输入（README 只列 rustup 工具链
说明符），也不承诺读本文件 ⇒ 单源只能表达成「文件里的 channel + workflow 里的同值
字面量」，而这两者不得漂移就是本文件的判据。

R9-B94 加的第二面：runner 镜像里那份**预装残缺**的工具链（`missing manifest in toolchain`，
实测 run 39081120142 与 39082352047，同一 commit 的另一条触发面是绿的）会点亮一盏与代码
无关的红灯。自愈步本身由下面的真调 bash 用例判，「谁调用 dtolnay 就必须先自愈」由配对判据判。

判据都可失败，并各带正面控制：扫不到任何 `toolchain:` 输入即红（否则「值都对」是空话）、
出现 `stable`/`beta` 即红、`nightly` 例外只允许一个且有 job 级 `RUSTUP_TOOLCHAIN`
（rustup 优先级：`+toolchain` 参数 > `RUSTUP_TOOLCHAIN` > 目录级文件 override > default；
少了那行 env，fuzz job 会被本仓的 rust-toolchain.toml 拉回 stable）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

TOOLCHAIN_FILE = ROOT / "rust-toolchain.toml"
CARGO_TOML = ROOT / "core" / "rust-policy-core" / "Cargo.toml"
WORKFLOWS = ROOT / ".github" / "workflows"
HEAL_ACTION = ROOT / ".github" / "actions" / "rust-toolchain-heal" / "action.yml"
HEAL_USES = "./.github/actions/rust-toolchain-heal"
DTOLNEY = "dtolnay/rust-toolchain@"

# 唯一的 nightly 例外所在 workflow（cargo-fuzz 的 sanitizer 插桩要 nightly）
NIGHTLY_OWNER = "core-rust.yml"


def pinned_channel() -> str:
    text = TOOLCHAIN_FILE.read_text(encoding="utf-8")
    match = re.search(r'^channel\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "rust-toolchain.toml 里没有 channel 声明"
    return match.group(1)


def toolchain_values() -> list[tuple[str, str]]:
    """(workflow 文件名, toolchain 输入值)——含正面控制用的总数判据。"""
    found: list[tuple[str, str]] = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        for line in wf.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*toolchain:\s*(\S+)\s*$", line)
            if match:
                found.append((wf.name, match.group(1)))
    return found


def test_rust_toolchain_file_pins_an_exact_stable_release():
    channel = pinned_channel()
    assert re.fullmatch(r"\d+\.\d+\.\d+", channel), (
        f"channel 必须是精确三段版本号，实得 {channel!r}——stable/beta/nightly 都算浮动")
    assert not re.search(r'^channel\s*=\s*"(stable|beta|nightly)"',
                         TOOLCHAIN_FILE.read_text(encoding="utf-8"), re.MULTILINE)


def test_pinned_channel_is_not_below_the_declared_msrv():
    msrv = re.search(r'^rust-version\s*=\s*"([^"]+)"',
                     CARGO_TOML.read_text(encoding="utf-8"), re.MULTILINE)
    assert msrv, "Cargo.toml 的 rust-version（MSRV）声明不见了"
    channel = pinned_channel()
    left = tuple(int(x) for x in channel.split("."))
    right = tuple(int(x) for x in msrv.group(1).split("."))
    assert left >= right, f"钉的 toolchain {channel} 低于 MSRV {msrv.group(1)}"


def test_workflows_contain_no_floating_toolchain_and_agree_with_the_file():
    pairs = toolchain_values()
    # 正面控制：语料确实存在（0 条时下面所有断言都会空过）
    assert len(pairs) >= 9, f"workflow 里只找到 {len(pairs)} 处 toolchain 输入——扫描面塌了"
    channel = pinned_channel()
    offenders = [(name, value) for name, value in pairs if value not in {channel, "nightly"}]
    assert not offenders, f"浮动/漂移的 toolchain 值：{offenders}"


def test_nightly_exception_is_exactly_one_and_forced_by_env():
    channel = pinned_channel()
    nightly = [name for name, value in toolchain_values() if value == "nightly"]
    assert nightly == [NIGHTLY_OWNER], (
        f"nightly 例外必须只在 {NIGHTLY_OWNER} 的 fuzz job，实得 {nightly}")
    doc = yaml.safe_load((WORKFLOWS / NIGHTLY_OWNER).read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or {}
    owners = [
        (name, (job.get("env") or {}).get("RUSTUP_TOOLCHAIN"))
        for name, job in jobs.items()
        if any(
            str(step.get("with", {}).get("toolchain", "")) == "nightly"
            for step in job.get("steps", []) or []
        )
    ]
    assert len(owners) == 1, f"nightly job 定位失败：{owners}"
    name, env_value = owners[0]
    assert env_value == "nightly", (
        f"{name} 必须 job 级钉 RUSTUP_TOOLCHAIN=nightly：仓库根的 rust-toolchain.toml 是"
        f"目录级 override，优先级高于 action 设的 default（实得 {env_value!r}）")
    assert channel != "nightly"


# ------------------------------------------------------------------ R9-B94：自愈步与它的配对判据
def heal_run() -> str:
    doc = yaml.safe_load(HEAL_ACTION.read_text(encoding="utf-8"))
    steps = doc["runs"]["steps"]
    assert len(steps) == 1, f"自愈动作应有单一步骤，实得 {len(steps)}"
    assert steps[0].get("shell") == "bash", "composite 的 bash 步骤必须显式写 shell（否则 windows runner 默认 pwsh）"
    return steps[0]["run"]


def test_heal_action_exists_and_is_self_describing() -> None:
    text = HEAL_ACTION.read_text(encoding="utf-8")
    assert "rust-toolchain.toml" in heal_run(), "自愈步没现读单源 channel，它自己就是第二个漂移点"
    assert "::error::" in heal_run(), "读不到 channel 时必须 fail-closed 而不是静默跳过"
    # 解释「它在等什么」可以提 dtolnay 的名字，但动作文件里不许真的出现第二个调用点
    assert "uses: dtolnay" not in text, "自愈动作里出现了 dtolnay 调用——它就成了第二个安装面"


def test_every_dtolnay_call_is_preceded_by_the_heal_step() -> None:
    """配对判据：谁调用 dtolnay/rust-toolchain，前一步必须是自愈步，且自愈的 channel 与之一致。

    只判「workflow 里有自愈步」是不够的——漏掉一个 job，那个 job 照样会被 runner 的坏预装点亮。
    """
    pairs = 0
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for job_id, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            for index, step in enumerate(steps):
                if not str(step.get("uses", "")).startswith(DTOLNEY):
                    continue
                pairs += 1
                want = str((step.get("with") or {}).get("toolchain", ""))
                previous = steps[index - 1] if index else {}
                assert str(previous.get("uses", "")) == HEAL_USES, (
                    f"{wf.name}:{job_id} 的 dtolnay 调用前一步不是自愈步（实得 {previous.get('uses')!r}）")
                passed = str((previous.get("with") or {}).get("channel", "")).strip()
                effective = passed or pinned_channel()
                assert effective == want, (
                    f"{wf.name}:{job_id} 自愈的是 {effective}，下一步装的却是 {want}")
                prior_uses = " ".join(str(s.get("uses", "")) for s in steps[:index])
                assert "actions/checkout" in prior_uses, (
                    f"{wf.name}:{job_id} 的自愈步在 checkout 之前——那它读不到 rust-toolchain.toml")
    assert pairs >= 9, f"只找到 {pairs} 处 dtolnay 调用——扫描面塌了，配对判据等于没判"


def _bash() -> str:
    path = shutil.which("bash")
    if path is None:
        raise AssertionError("找不到 bash——自愈步的判据无法执行，请修环境而不是让它静默通过")
    return path


def _run_heal(tmp_path: Path, *, rustc_broken: bool, toml_channel: str = "1.99.0",
              input_channel: str = "") -> subprocess.CompletedProcess:
    """真调 bash 跑动作文件里那段脚本体（GitHub 对 composite 的 bash 步骤用的就是这组旗标）。"""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    rustup_home = tmp_path / "rustup"
    (rustup_home / "toolchains" / f"{toml_channel}-x86_64-unknown-linux-gnu").mkdir(parents=True)
    calls = tmp_path / "calls.log"
    (fake_bin / "rustc").write_text(
        "#!/usr/bin/env bash\n"
        'echo "rustc $*" >> "$CALLS"\n'
        'if [ -f "$MARKER" ]; then exit 0; fi\n'
        '[ "$BROKEN" = "1" ] && exit 1\n'
        "exit 0\n",
        encoding="utf-8")
    (fake_bin / "rustup").write_text(
        "#!/usr/bin/env bash\n"
        'echo "rustup $*" >> "$CALLS"\n'
        'if [ "$1" = "show" ]; then echo "$RUSTUP_HOME"; exit 0; fi\n'
        'if [ "$1" = "toolchain" ] && [ "$2" = "install" ]; then touch "$MARKER"; exit 0; fi\n'
        "exit 0\n",
        encoding="utf-8")
    for stub in (fake_bin / "rustc", fake_bin / "rustup"):
        stub.chmod(0o755)
    (tmp_path / "rust-toolchain.toml").write_text(
        f'[toolchain]\nchannel = "{toml_channel}"\n' if toml_channel else "", encoding="utf-8")
    script = tmp_path / "heal.sh"
    script.write_text(heal_run(), encoding="utf-8", newline="\n")
    env = {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RUSTUP_HOME": str(rustup_home),
        "CALLS": str(calls),
        "MARKER": str(tmp_path / "reinstalled"),
        "BROKEN": "1" if rustc_broken else "0",
        "HEAL_CHANNEL": input_channel,
    }
    return subprocess.run(
        [_bash(), "--noprofile", "--norc", "-e", "-o", "pipefail", str(script)],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, check=False)


def test_healthy_toolchain_is_left_alone(tmp_path: Path) -> None:
    result = _run_heal(tmp_path, rustc_broken=False)
    assert result.returncode == 0, result.stderr
    assert "无需重装" in result.stdout, result.stdout
    assert not (tmp_path / "calls.log").read_text(encoding="utf-8").startswith("rustup toolchain install")
    assert (tmp_path / "rustup" / "toolchains" / "1.99.0-x86_64-unknown-linux-gnu").is_dir(), "健康时不许删东西"


def test_broken_manifest_is_reinstalled_from_the_single_source(tmp_path: Path) -> None:
    result = _run_heal(tmp_path, rustc_broken=True)
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "rustup toolchain install 1.99.0" in calls, calls
    assert not (tmp_path / "rustup" / "toolchains" / "1.99.0-x86_64-unknown-linux-gnu").exists(), (
        "坏预装目录没被移除——下一步仍会拿到同一份残缺安装")
    assert (tmp_path / "reinstalled").exists(), "重装没发生"


def test_channel_override_lands_on_the_floating_exception(tmp_path: Path) -> None:
    """nightly 那个 job 显式传 channel；不传的话它会去重装 1.99.0，与下一步装的东西不是同一个。"""
    result = _run_heal(tmp_path, rustc_broken=True, input_channel="nightly")
    assert result.returncode == 0, result.stderr
    assert "rustup toolchain install nightly" in (tmp_path / "calls.log").read_text(encoding="utf-8")


def test_unreadable_channel_fails_closed(tmp_path: Path) -> None:
    result = _run_heal(tmp_path, rustc_broken=False, toml_channel="")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "::error::" in result.stdout, result.stdout
