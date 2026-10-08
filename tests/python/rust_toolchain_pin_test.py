"""「固定 toolchain」的声明与实树必须一致（第八轮 B7，R8-DEPS-2 的执行面）。

成因（本仓自己的两处声明 vs 实树）：`core/rust-policy-core/Cargo.toml` 的依赖注与
`docs/adr/ADR-005` 的决策条都把「固定 toolchain」写成蓝图口径，而仓库根既没有
`rust-toolchain.toml`，workflow 里 9 处又全用 `toolchain: stable` ⇒ 同一 commit 隔月
重跑出来的 `aegis_policy_core.dll` 字节可变，自建哈希基线与 release 台账对账会周期性
失配。`dtolnay/rust-toolchain` 没有 `toolchain: file` 输入（README 只列 rustup 工具链
说明符），也不承诺读本文件 ⇒ 单源只能表达成「文件里的 channel + workflow 里的同值
字面量」，而这两者不得漂移就是本文件的判据。

判据都可失败，并各带正面控制：扫不到任何 `toolchain:` 输入即红（否则「值都对」是空话）、
出现 `stable`/`beta` 即红、`nightly` 例外只允许一个且有 job 级 `RUSTUP_TOOLCHAIN`
（rustup 优先级：`+toolchain` 参数 > `RUSTUP_TOOLCHAIN` > 目录级文件 override > default；
少了那行 env，fuzz job 会被本仓的 rust-toolchain.toml 拉回 stable）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLCHAIN_FILE = ROOT / "rust-toolchain.toml"
CARGO_TOML = ROOT / "core" / "rust-policy-core" / "Cargo.toml"
WORKFLOWS = ROOT / ".github" / "workflows"

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
