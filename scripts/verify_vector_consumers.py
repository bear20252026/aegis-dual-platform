#!/usr/bin/env python3
"""verify_vector_consumers.py —— 契约向量的**逐端消费分布**门禁（外部第三轮审计 AEG-006）。

AEG-006 的原话是「跨语言契约测试覆盖不一致」，并举例「C# 只连部分向量、Kotlin 主要消费
url-origin-*」。本脚本把这句话变成一个可判定的表：每份向量实测被哪几端执行，改动必须是
有意识的动作。两条口径，否则数字会被读成另一种意思：
- 「消费者」＝受管源码面里以「完整文件名」或「词干作为独立词」**在代码里**命中（注释一律
  不算——R9-B39），且落在会被编译/执行的
  路径下。markdown 里的提及是**声明**，不算消费（否则文档写一句就冒充「测试跑过」）。
- `META_LEVEL`（按名遍历整个向量目录的工具面，含本门禁自己）判的是「实例对 Schema 的
   通过/拒绝＝向量自述的 expected」，对
  capability/audit-event 那四位就是全部语义 ⇒ 记为「无端侧执行者」≠「没人判」，只等于
  「没有平台实现跑它」；而「跨端同一裁决」恰好只对后者有意义。

判据（每条都在 tests/python/vector_consumers_test.py 里被注入证伪）：
1. 向量数 < MIN_VECTORS 或扫描面为空 ⇒ 退出 2（面塌缩不是「变安全」）。
2. 实测端集必须等于 CONSUMER_MANIFEST 登记端集——少一面、多一面、新增未登记、过期登记
   四种都判红（同 R9-SH-7 的双向不变量：过期声明与悄悄扩面同等致命）。
   0a. 命中口径**剔注释**（R9-B39）：只在注记里写出向量文件名的文件不是消费者——否则
   「文档提到」会被读成「这端跑过」，而覆盖面正是靠这句话立起来的。
3. 至少 MIN_CROSS_END 份向量同时被 CS 与 AD 执行（今天＝url-origin-* 两份）；这条**不随
   登记表松动**，否则「把跨端两份改成单端登记」就能把 AEG-006 说反。
4. 至少 MIN_EXECUTABLE 份有端侧执行者（今天 11 份）——防止整体退化成纯 schema 对账。
5. META_LEVEL 路径必须仍可解析：漂了会把真实端侧消费者误降成「只在元层判」。

退出码：0=通过 / 1=违规 / 2=环境或扫描面异常。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# R9-B45 / Q59：剔注释口径单源（四种形态的原文说明在 text_anchors 的模块 docstring 里）。
from text_anchors import strip_comments

ROOT = Path(__file__).resolve().parents[1]
VECTORS_DIR = ROOT / "contracts" / "vectors"

# 实测面：21 份向量（2026-10-12，R9-B35 加 release/version/semver-form 六份）。
# 下界只保证「减面必须是有意识的动作」。
MIN_VECTORS = 21
# 判据 3/4 的下界：CS∧AD 同跑的最小份数、有端侧执行者的最小份数。
MIN_CROSS_END, MIN_EXECUTABLE = 1, 10

CODE_EXTENSIONS = (".cs", ".kt", ".kts", ".rs", ".py", ".js", ".mjs", ".yml", ".yaml")
EXCLUDED_PARTS = ("/target/", "/obj/", "/bin/", "/node_modules/", "/build/", "/dist/")

# 元面（META_LEVEL）：按名遍历整个向量目录、只判「形状/expected/协议字段对不对」的工具文件，
# 包括**本门禁自己、它的用例，以及 verify_vectors.py 那条词表门禁的用例**——它们在源码里
# 写出每一份向量的名字，若算消费者就会让全部向量都「被 PY 执行」，把整张表读成假象
# （CI 首跑实测正是这样红的）。集合成员不写进散文计数（R9-B41 那一族：抄一个数就多一处会漂移的陈述）。
# 每一项都要能在实树里解析到（判据 5）。
META_LEVEL = (
    "contracts/codegen/validate_vector_schemas.py",
    "tests/python/vector_schema_input_guard_test.py",
    "tests/python/native_vector_partition_test.py",
    "scripts/verify_vectors.py",
    "scripts/verify_vector_consumers.py",
    "tests/python/vector_consumers_test.py",
)

# 实测登记（2026-10-11，扫描 541 个受管源文件）。空 frozenset＝没有端侧执行者，只有
# schema 级判定。改任何一行的端集都要同批在台账写清为什么。两个易错点已被自己的门禁打回过：
# update-manifest-invalid/valid 的 PY 命中**全部**来自元层文件（不算端侧），
# 而 canonical 的 PY 是 tests/python/release_tools_test.py（真实消费者，保留）。
CONSUMER_MANIFEST: dict[str, frozenset[str]] = {
    # R9-B68（队列 Q53 第③档）：AG 命中来自 `agent/tests/action_vector_consumption_test.py`
    # ——Agent 端把两份向量逐条喂进 `ActionContract.payload_violation`（与
    # `evaluate()` 里同一份从 schema 现算的判定面）。登记的是**契约层**：
    # `PolicyBroker.decide()` 那条面对核心形态载荷一律 deny_payload（Agent 的
    # ProposedAction 还要求 intent/budget_used），断它「非 ALLOW」是零信息量断言。
    "action-invalid.json": frozenset({"AG", "RS"}),
    "action-valid.json": frozenset({"AG", "RS"}),
    "approvals-replay-and-expiry.json": frozenset({"RS"}),
    "audit-event-invalid.json": frozenset(),
    # R9-B35（第九轮 Q11）：实例级四条只由 schema 层判定（validate_vector_schemas.py
    # 在 META_LEVEL 里），没有平台实现跑它们——记空集是事实陈述，不是「没人判」。
    # semver-form 两条不同：tests/python/semver_schema_parity_test.py 真的逐案执行它们
    # （三张 schema × 客户端验证器 × 向量期望的三方对账），故登记 PY。
    "release-invalid.json": frozenset(),
    "release-valid.json": frozenset(),
    "semver-form-invalid.json": frozenset({"PY"}),
    "semver-form-valid.json": frozenset({"PY"}),

    "audit-event-valid.json": frozenset(),
    "version-invalid.json": frozenset(),
    "version-valid.json": frozenset(),
    "capability-invalid.json": frozenset(),
    "capability-valid.json": frozenset(),
    "glob-match.json": frozenset({"RS"}),
    "native-navigation-confirmation.json": frozenset({"RS"}),
    # R9-B39 改回事实：这里的 CS 命中此前全部来自注释（见 strip_comments），
    # 没有任何 C# 代码真的读这份向量 ⇒ 登记成 {"CS","RS"} 就是把「文档说过」当成
    # 「跑过了」。Windows 侧真接一份执行者是 §五 Q53 的第②档。
    # R9-B59（§四 第 11 项 ②）把第②档**定稿成「不接全量」**：这两份向量的每条带
    # platform_decidable，false 的那 13 条（+ 确认面整份 5 条）在宿主自己的托管判定路径上
    # 产不出分支 ⇒ 平台执行者将来只能覆盖 true 子集，登记端集不因「有人加了一份读该文件的
    # C# 用例」就自动变成 {"CS","RS"}——那种用例如果断言了 false 子集就是断不真的陈述。
    "native-navigation-decision.json": frozenset({"RS"}),
    "update-manifest-canonical.json": frozenset({"RS", "PY"}),
    "update-manifest-invalid.json": frozenset({"RS"}),
    # R9-B35 起 PY 也是它的消费者：semver_schema_parity_test.py 取其首条 manifest
    # 当 update-manifest.schema.json 的宿主模板（逐案换 version 做三方对账）。
    "update-manifest-valid.json": frozenset({"CI", "PY", "RS"}),
    "url-origin-invalid.json": frozenset({"AD", "CS", "PY", "RS"}),
    "url-origin-valid.json": frozenset({"AD", "CS", "RS"}),
}


def tracked_files() -> list[str]:
    """git ls-files 收口受管面（与 check_file_sizes 同口径：不爬构建产物）。"""
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", check=False
    )
    if out.returncode != 0:
        raise RuntimeError(f"git ls-files 失败：{out.stderr.strip()}")
    return [f for f in out.stdout.splitlines() if f.strip()]


def scan_surface(files: list[str]) -> dict[str, str]:
    """读入受管源码面（扩展名过滤 + 排除构建目录与向量本体）。返回 path → text。"""
    texts: dict[str, str] = {}
    for rel in files:
        if not rel.endswith(CODE_EXTENSIONS):
            continue
        if any(part in f"/{rel}" for part in EXCLUDED_PARTS):
            continue
        if rel.startswith("contracts/vectors/"):
            continue
        try:
            texts[rel] = strip_comments((ROOT / rel).read_text(encoding="utf-8", errors="ignore"), rel)
        except OSError:
            continue
    return texts


def end_of(rel: str) -> str:
    """消费端归类（与台账 §二 的分区口径一致）。"""
    top = rel.split("/", 1)[0]
    return {"windows": "CS", "android": "AD", "core": "RS", "agent": "AG",
            "shared": "SH", "scripts": "PY", "tests": "PY", "contracts": "PY",
            "release": "PY", ".github": "CI"}.get(top, top or "?")


def _matcher(vectors: list[Path]) -> tuple[re.Pattern[str], dict[str, str]]:
    """合并正则单遍扫描（15 份 × 541 文件逐向量扫实测 12.4s，单遍 ≈1s——判据贵到
    进不了常跑面就会变成台账里写着「已登记」而从没执行，R9-SH-7 的同型事故）。
    命中语义不变：词干作为独立词，或完整文件名。"""
    tokens: dict[str, str] = {}
    for path in vectors:
        tokens[path.stem] = path.name
        tokens[path.name] = path.name
    alts = sorted((re.escape(t) for t in tokens), key=len, reverse=True)
    return re.compile(r"(?<![\w.-])(" + "|".join(alts) + r")(?![\w-])"), tokens


def collect_consumers(
    texts: dict[str, str], vectors: list[Path]
) -> dict[str, list[str]]:
    """向量名 → 端侧消费者路径（元层除外；同一文件命中词干与全名只计一次）。"""
    pattern, tokens = _matcher(vectors)
    meta = set(META_LEVEL)
    found: dict[str, list[str]] = {p.name: [] for p in vectors}
    for rel, text in texts.items():
        if rel in meta:
            continue
        for name in {tokens[t] for t in pattern.findall(text) if t in tokens}:
            found[name].append(rel)
    for hits in found.values():
        hits.sort()
    return found


def vector_files() -> list[Path]:
    if not VECTORS_DIR.is_dir():
        raise FileNotFoundError(f"向量目录缺失：{VECTORS_DIR}")
    return sorted(VECTORS_DIR.glob("*.json"))


def check(texts: dict[str, str], vectors: list[Path]) -> tuple[list[str], list[str]]:
    """返回 (违规列表, 逐向量的端侧分布行)。"""
    violations: list[str] = []
    report: list[str] = []
    consumers = collect_consumers(texts, vectors)
    cross_end = 0
    executable = 0
    for path in vectors:
        name = path.name
        ends = frozenset({end_of(h) for h in consumers.get(name, [])})
        registered = CONSUMER_MANIFEST.get(name)
        if registered is None:
            violations.append(
                f"{name}：不在 CONSUMER_MANIFEST 里——新增向量必须登记实测端集、"
                f"删向量必须同批删条目（实测端集={sorted(ends) or '∅'}）")
        elif ends != registered:
            violations.append(
                f"{name}：消费面漂移 登记={sorted(registered) or '∅'} → "
                f"实测={sorted(ends) or '∅'}——改表要写理由，覆盖面变化不是静默事件")
        if ends:
            executable += 1
        if {"CS", "AD"} <= ends:
            cross_end += 1
        hits = consumers.get(name, [])
        report.append(
            f"{name:42s} " + ("/".join(sorted(ends)) if ends else "仅元层（schema/协议）")
            + ("  " + ", ".join(hits[:2]) if hits else ""))
    for stale in sorted(set(CONSUMER_MANIFEST) - {p.name for p in vectors}):
        violations.append(f"CONSUMER_MANIFEST 里的 {stale} 在实树不存在——过期登记")
    if cross_end < MIN_CROSS_END:
        violations.append(
            f"同时被 CS 与 AD 执行的向量只有 {cross_end} 份（下界 {MIN_CROSS_END}）"
            f"——「跨端同一裁决」这条支点没了")
    if executable < MIN_EXECUTABLE:
        violations.append(
            f"有端侧执行者的向量只有 {executable} 份（下界 {MIN_EXECUTABLE}）"
            f"——覆盖面正在退化成纯 schema 对账")
    return violations, report


def check_meta_paths_exist(files: list[str]) -> list[str]:
    """元面漂了会把真实端侧消费者误降成「只在元层判」（判据 5）。"""
    tracked = set(files)
    return [f"{p} 已不在受管面——META_LEVEL 集合过期" for p in META_LEVEL if p not in tracked]


def run() -> int:
    try:
        files = tracked_files()
        vectors = vector_files()
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"::error:: 扫描面不可用：{exc}", file=sys.stderr)
        return 2
    if len(vectors) < MIN_VECTORS:
        print(f"::error:: 向量面塌缩：{len(vectors)} 份（基线 ≥{MIN_VECTORS}）", file=sys.stderr)
        return 2
    texts = scan_surface(files)
    if not texts:
        print("::error:: 受管源码面为空——本门禁没有判定面", file=sys.stderr)
        return 2
    violations, report = check(texts, vectors)
    violations += check_meta_paths_exist(files)
    if violations:
        for line in violations:
            print(f"::error:: {line}", file=sys.stderr)
        print(f"❌ 向量逐端消费面门禁失败（{len(violations)} 项）", file=sys.stderr)
        return 1
    print(f"契约向量逐端消费面：{len(vectors)} 份（扫描 {len(texts)} 个受管源文件）")
    print("\n".join("  " + line for line in report))
    print("✅ 向量逐端消费面门禁通过")
    return 0


def main() -> int:
    """判据的注入式自证不在这里——见 tests/python/vector_consumers_test.py：
    一个要人主动敲的 flag 就是「跑不动的判据」，放进 pytest 才每次 PR 都执行。"""
    return run()


if __name__ == "__main__":
    sys.exit(main())
