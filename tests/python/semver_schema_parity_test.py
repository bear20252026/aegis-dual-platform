# semver_schema_parity_test.py —— R9-B35（第九轮 Q11 / R9-SH-1，P2）。
#
# 判的三件事，缺一不可：
# 1. **三张 schema 的 `version.pattern` 是同一串**——此前 release/version 用旧宽松式
#    （`(?:-[0-9A-Za-z.-]+)?`，接受 `2.2.0-01`、`2.2.0-beta.`、`2.2.0-..`），
#    update-manifest 用 PY-279 收紧式（仍接受 `2.2.0-01`），而
#    `release/update_verifier.py` 对这些抛 UpdateRejected ⇒ 同一个版本串
#    「发布声明说合法、客户端验证器判非法」。三份式子各自演化就是三个真相源。
# 2. **与客户端验证器逐案等价**——判据不是「看起来一样」，而是拿
#    `contracts/vectors/semver-form-{valid,invalid}.json` 的 31 个形态，
#    分别过三张 schema（真 `jsonschema` 校验器，含 release 的完整实例）与
#    `update_verifier._version_tuple`，要求四方对每条给出同一个裁决。
# 3. **电池真有判别力**——把两条旧式喂进同一判据，它们必须在被点名的形态上
#    与验证器分歧（否则第 2 条可能只是「两边都松」的巧合）。
#
# `version.schema.json` 在本批之前全树**零消费者**、release/version 两张 schema
# **零向量**（PY-013 的向量面只覆盖 4/7）——这两件事也在这里被钉住：
# 扫描面按目录现取，新增 schema 不登记就红。
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import update_verifier

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"
VECTORS = ROOT / "contracts" / "vectors"

# 现役发布声明（release.schema.json 要求完整对象，单独一个版本串无法成实例）
RELEASE_BASE = json.loads((ROOT / "shared" / "release.json").read_text(encoding="utf-8"))

# update-manifest.schema.json 同理——它的宿主另有必填字段，取实树合法向量的第一条
# manifest 当基座（`version` 由测试逐案替换）
MANIFEST_BASE = json.loads(
    (VECTORS / "update-manifest-valid.json").read_text(encoding="utf-8")
)["vectors"][0]["manifest"]

# 本判据管的三张带 version.pattern 的 schema
PATTERNS = {
    "release.schema.json": ("release", RELEASE_BASE),
    "version.schema.json": ("version", {"version": "1.0.0"}),
    "update-manifest.schema.json": ("version", MANIFEST_BASE),
}

# 两条历史式（登记在此只为反向锚使用；注记里逐字抄着被禁形态是本仓口径）
OLD_LOOSE = (r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
             r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
OLD_PY279 = (r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
             r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
             r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")


def schema_of(name: str):
    doc = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(doc, format_checker=jsonschema.FormatChecker())


def instance_for(base: dict, key: str, value: str) -> dict:
    """把「一个版本串」放进它所在 schema 的宿主实例里（只换 version 一处）。"""
    return {**base, "version": value}


def client_accepts(value: str) -> bool:
    """客户端验证器的裁决：_version_tuple 抛 UpdateRejected 即拒绝。"""
    try:
        update_verifier._version_tuple(value)
        return True
    except update_verifier.UpdateRejected:
        return False


def pattern_of(name: str) -> str:
    doc = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return doc["properties"]["version"]["pattern"]


def parity_problems(patterns: dict[str, str]) -> list[str]:
    """纯函数：给定「schema 名 → pattern」，返回不同源的问题清单。"""
    distinct = sorted(set(patterns.values()))
    if len(distinct) <= 1:
        return []
    return [f"{name} 的 version.pattern 与其余 {len(distinct) - 1} 份不同源"
            for name, pattern in sorted(patterns.items())
            if pattern != distinct[0]]


def battery() -> list[tuple[str, bool]]:
    """两份形态向量合并成 (版本串, 期望接受) 清单——期望来自向量的 expected 字段。"""
    cases: list[tuple[str, bool]] = []
    for fname, accepted in (("semver-form-valid.json", True), ("semver-form-invalid.json", False)):
        doc = json.loads((VECTORS / fname).read_text(encoding="utf-8"))
        for vector in doc["vectors"]:
            assert vector["expected"] == ("valid" if accepted else "deny"), fname
            cases.append((vector["version"], accepted))
    return cases


def test_the_three_schemas_share_one_semver_pattern() -> None:
    assert not parity_problems({name: pattern_of(name) for name in PATTERNS})


def test_parity_check_itself_can_fail() -> None:
    """反向锚（内存态注入）：只改一张 schema 的 pattern，判据必须点名那一张。"""
    shared = pattern_of("version.schema.json")
    injected = {**{name: shared for name in PATTERNS},
                "update-manifest.schema.json": OLD_PY279}
    problems = parity_problems(injected)
    assert any("update-manifest" in p for p in problems), problems
    assert sum("update-manifest" in p for p in problems) == 1, (
        f"归因跑偏（应当只点名被改的那一张）：{problems}")
    assert parity_problems({name: shared for name in PATTERNS}) == []


def test_pattern_agrees_with_the_client_verifier_case_by_case() -> None:
    offenders: list[str] = []
    for value, expected in battery():
        verdicts = {"client": client_accepts(value)}
        for name, (key, base) in PATTERNS.items():
            verdicts[name] = schema_of(name).is_valid(instance_for(base, key, value))
        bad = [who for who, got in verdicts.items() if got != expected]
        if bad:
            offenders.append(f"{value!r} 期望 accept={expected}，与客户端不一致的一方：{bad}")
    assert not offenders, "；".join(offenders)


def test_battery_discriminates_the_two_historical_patterns() -> None:
    """电池不是摆设：两条旧式各自在**具名形态**上与客户端分歧（这正是 Q11 的现象）。"""
    cases = dict(battery())
    for label, old, witness in (
        ("旧宽松式", OLD_LOOSE, "2.2.0-01"),
        ("PY-279 式", OLD_PY279, "2.2.0-01"),
    ):
        rx = re.compile(old)
        wrongly_accepted = [v for v, want in cases.items()
                            if not want and bool(rx.match(v))]
        assert witness in wrongly_accepted, f"{label} 应放过 {witness!r}：{wrongly_accepted}"
        # 且分歧必须是**可指认的**：客户端对同一条判拒
        assert not client_accepts(witness), f"{witness!r} 客户端应判拒（否则本条没有证明任何东西）"


def test_current_release_declaration_still_validates() -> None:
    """收紧不能伤到现役形态——shared/release.json 的 version 必须三处都过。"""
    live = RELEASE_BASE["version"]
    assert client_accepts(live), f"现役版本 {live!r} 被客户端验证器拒了"
    for name, (key, base) in PATTERNS.items():
        assert schema_of(name).is_valid(instance_for(base, key, live)), (name, live)


def test_every_schema_with_a_version_pattern_is_on_the_scan_surface() -> None:
    """扫描面对账：`contracts/schemas` 里凡是带 `properties.version.pattern` 的 schema
       都必须在 PATTERNS 登记——新增一张而忘记登记，本条判红（否则「三份同源」会悄悄
       变成「登记的这三份同源」）。"""
    found: list[str] = []
    for path in SCHEMAS.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        version = doc.get("properties", {}).get("version")
        if isinstance(version, dict) and version.get("pattern"):
            found.append(path.name)
    assert sorted(found) == sorted(PATTERNS), (
        f"扫描面与登记表不再同一集合：{found} vs {sorted(PATTERNS)}")
