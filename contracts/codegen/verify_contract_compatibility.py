#!/usr/bin/env python3
"""verify_contract_compatibility.py —— contracts/codegen（蓝图阶段 B——契约兼容性）。

阶段 B 完成标准：Schema/C#/Kotlin/Python fixture 对同一组合法/非法输入得到一致
结果——跨语言一致（Rust/C#/Kotlin reference + Python fixture——同一 contracts
vectors）。校验：schemas/vectors JSON 有效 + 生成的 C#/Kotlin 模型与 schema
properties 一致（不平行 Schema——蓝图）。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

# PY-042：需要重生成内容做 diff——平铺导入同目录生成器模块
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from generate_csharp import SKIP_SCHEMAS
from generate_csharp import generate as generate_cs_model
from generate_kotlin import generate as generate_kt_model
from mirror_consumers import consumed_names

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
VECTORS = ROOT / "vectors"


# 审计第六轮（2026-10-03）：schema ↔ 真实手写模型对账映射。
# 此前 check_generated_models 只把 schema 与其自身生成镜像比对——「契约兼容性 =
# 跨语言一致」在 schema 与自己镜像之间自证，从不触及两端实际运行的手写类型
#（AD-244 已坦白）。本表把每条冻结契约对到其消费端手写实现，缺失/字段漂移即红。
# 值 = (模型文件, 语言, 类型名)。只读这些文件，绝不写。
#
# 审计第七轮（2026-10-04·R7-SH-01 整改）：本表于第六轮建好但**从未被调用**——
# 当时注释宣称的 check_mirror_consumption 也不存在，门禁仍是 schema↔自身镜像自证。
# 现按实测消费面重写：
#   · approval / audit-event 两条经回读确认存在真实手写对应类型（C# record 参数
#     与 schema required 逐项对应），纳入 check_real_models 硬对账；
#   · capability 一条**已删除**——Rust `capability.rs:54` 的 `pub struct Capability`
#     是运行时能力对象（name/scope/allowed_origins/max_uses/uses_count），与
#     `capability.schema.json` 的 required（scope/actions/resources）不是同一事物，
#     全仓亦无任何手写类型含 `requires_confirmation`（仅生成物含）。capability
#     契约的跨语言面由生成镜像 + 向量结构校验承担，如实登记，不假称有手写消费方。
#
# 路径一律写**相对仓库根的 posix 串**并在函数内按 `ROOT.parent` 解析——与
# check_generated_models 的 `ROOT / ".."` 同口径，使单测把 ROOT 重定向到合成契约树
# 时这两个检查也随之指向合成树（不会一半读合成、一半读真实仓库）。
REAL_MODEL_CONTRACTS: dict[str, tuple[str, str, str]] = {
    "approval.schema.json": (
        "windows/src/Aegis.Windows.App/Broker/Decision.cs", "cs", "ApprovalRequest"),
    "audit-event.schema.json": (
        "windows/src/Aegis.Windows.App/Broker/Audit/AuditEvent.cs", "cs", "AuditEvent"),
}

# 审计第六轮：已声明为「设计标注镜像」的生成物——AD-244：当前零消费方，保留仅为
# 跨语言契约镜像完整性。列于此显式承认为非承重镜像；此集外的任何镜像若无真实
# 消费方则 check_mirror_consumption 计入 failures（防镜像悄悄沦为无人消费的假保证）。
# 审计第七轮（R7-SH-01）：补齐此前漏登记的 ActionContract（生成物存在但不在豁免
# 清单内＝清单本身在漂移），并把「豁免项必须有对应生成文件」做成反向断言，
# 使本清单不能靠堆积历史条目蒙混。
# 第九轮 R9-SH-7：本表曾**恰好等于**镜像全集（两目录各 6 份），于是每条都在
# `continue` 处被跳过、消费面检查在现树里从没真正跑过；而旧扫描从仓库根
# `rglob("*")` 连 target/obj/node_modules 一起爬，贵到进不了「每次 PR 都跑」的面
#（实测口径与收窄后的扫描面在 `mirror_consumers.py`）。
# 现在的口径把豁免变成**要自证的声明**：登记项必须①仍在生成面上（R7-SH-01）
# 且②确实无人消费（本轮新增）——被端侧用起来却没删登记，同样判红。
DESIGN_NOTATION_MIRRORS = {
    "ActionContract", "ApprovalContract", "AuditEventContract", "CapabilityContract",
    "UpdateManifestContract", "VersionContract",
}



def contract_name(schema_file: pathlib.Path) -> str:
    """与 C#/Kotlin 生成器一致地生成稳定且合法的契约类型名。"""
    stem = schema_file.stem.removesuffix(".schema")
    return "".join(part[:1].upper() + part[1:] for part in stem.split("-")) + "Contract"


def check_schemas() -> list[str]:
    failures = []
    for f in sorted(SCHEMAS.glob("*.json")):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            failures.append(f"schema JSON 无效: {f.name}（{e}）")
    return failures


def check_vectors() -> list[str]:
    failures = []
    for f in sorted(VECTORS.glob("*.json")):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            failures.append(f"vector JSON 无效: {f.name}（{e}）")
    return failures


def check_generated_models() -> list[str]:
    """生成的 C#/Kotlin 模型与 schema 一致（不平行 Schema——蓝图）。

    PY-042：此前只查文件存在——手改生成文件/schema 变更后不重跑生成器
    均静默通过。现按 schema 重生成内容与磁盘 diff（行为等价 `--check`）。

    AD-244（2026-09-26 审计）：Approval/AuditEvent/Capability/UpdateManifest/
    Version 五份 Kotlin 生成物（及 C# 同名生成物）在应用代码中当前零消费
    ——仍全部生成并参与本对账。保留原因：跨语言契约镜像完整性——
    contracts/schemas 是冻结契约事实来源，C#/Kotlin 生成物是其跨语言
    镜像，逐字节对账使 schema 漂移/手改生成物立即门禁红；收窄生成范围
    会让镜像失去对账意义。取舍已同步至两生成器 main() 注释。
    """
    failures = []
    generated_cs = (ROOT / ".." / "windows" / "src" / "Aegis.Windows.App"
                    / "Contracts" / "Generated")
    generated_kt = (ROOT / ".." / "android" / "contracts" / "src" / "main" / "kotlin"
                    / "com" / "aegis" / "contracts" / "generated")
    for f in sorted(SCHEMAS.glob("*.json")):
        if f.name in SKIP_SCHEMAS:
            continue  # PY-102：发布事实声明不生成模型（与生成器跳过集单源）
        name = contract_name(f)
        # PY-196（2026-09-26 审计）：check_generated_models 里 json.loads 无
        # 守卫——坏 schema JSON 时未捕获异常炸出，已收集的失败信息被吞掉。
        # 复用 check_schemas 的 try/except 口径：计 failure 后 continue。
        try:
            schema = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            failures.append(f"schema JSON 无效: {f.name}（{e}）")
            continue
        expected_cs = generate_cs_model(schema, name) + "\n"
        expected_kt = generate_kt_model(schema, name) + "\n"
        cs_path = generated_cs / f"{name}.cs"
        kt_path = generated_kt / f"{name}.kt"
        if not cs_path.is_file():
            failures.append(f"C# 模型缺失: {name}.cs（运行 generate_csharp.py）")
        else:
            actual = cs_path.read_text(encoding="utf-8").replace("\r\n", "\n")
            if actual != expected_cs:
                failures.append(f"C# 模型与 schema 漂移: {name}.cs（重新运行 generate_csharp.py）")
        if not kt_path.is_file():
            failures.append(f"Kotlin 模型缺失: {name}.kt（运行 generate_kotlin.py）")
        else:
            actual = kt_path.read_text(encoding="utf-8").replace("\r\n", "\n")
            if actual != expected_kt:
                failures.append(f"Kotlin 模型与 schema 漂移: {name}.kt（重新运行 generate_kotlin.py）")
    return failures


def _decl_body(text: str, type_name: str) -> str | None:
    """取 `record|class|struct NAME` 声明后的首个配对括号/花括号体。

    C# 位置式 record 的参数表在圆括号内、class/struct 体在花括号内——两者都取，
    取不到配对即返回 None（调用方计 failure，不静默放行）。
    """
    decl = re.search(rf"\b(?:record|class|struct)\s+{re.escape(type_name)}\b", text)
    if decl is None:
        return None
    opens = [(text.find("(", decl.end()), "(", ")"), (text.find("{", decl.end()), "{", "}")]
    valid = [(i, o, c) for i, o, c in opens if i >= 0]
    if not valid:
        return None
    start, open_c, close_c = min(valid)
    depth = 0
    for k in range(start, len(text)):
        if text[k] == open_c:
            depth += 1
        elif text[k] == close_c:
            depth -= 1
            if depth == 0:
                return text[start + 1:k]
    return None


def check_real_models() -> list[str]:
    """冻结 schema ↔ 端侧**手写**模型对账（R7-SH-01 收口第六轮建而未用的表）。

    口径与限制如实声明：比对 schema `required` 的属性名是否作为标识符出现在该类型
    的参数表/体内——即**名实对账**，不比对类型与可空性（那需要真正的 C#/Rust 解析器，
    本仓无此依赖，宁可如实弱一档也不写假的强断言）。字段被改名/删除即红。
    """
    failures: list[str] = []
    repo = ROOT.parent
    for schema_name, (rel_model, lang, type_name) in sorted(REAL_MODEL_CONTRACTS.items()):
        try:
            schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"真实模型对账无法进行：schema 不可读 {schema_name}（{exc}）")
            continue
        model = repo / rel_model
        try:
            text = model.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"真实模型缺失：{schema_name} → {rel_model}::{type_name}（{exc}）")
            continue
        body = _decl_body(text, type_name)
        if body is None:
            failures.append(f"真实模型类型未找到：{rel_model} 内无 {type_name} 声明")
            continue
        for prop in schema.get("required", []) or []:
            want = ("".join(p.capitalize() for p in prop.split("_"))
                    if lang == "cs" else prop)
            flags = re.IGNORECASE if lang == "cs" else 0
            if re.search(rf"\b{re.escape(want)}\b", body, flags) is None:
                failures.append(
                    f"字段漂移：{schema_name} required '{prop}' 未在 "
                    f"{type_name}（{rel_model}）出现")
    return failures


def _mirror_dirs() -> list[tuple[str, pathlib.Path]]:
    """生成镜像目录（随 ROOT 重定向，与 check_generated_models 同一表达式口径）。"""
    return [
        ("cs", ROOT / ".." / "windows" / "src" / "Aegis.Windows.App" / "Contracts" / "Generated"),
        ("kt", ROOT / ".." / "android" / "contracts" / "src" / "main" / "kotlin"
              / "com" / "aegis" / "contracts" / "generated"),
    ]


# 「消费」的扫描面与三条边界（跨语言同名不算 / 测试引用不算 / 构建产物不算）写在
# `mirror_consumers.py`——本文件已在 300 行红线上，那套口径放不下，见 R9-SH-7。
def _consumed_names(lang: str, names: set[str]) -> set[str]:
    return consumed_names(ROOT / "..", lang, names)


def check_mirror_consumption() -> list[str]:
    """每个生成镜像必须「有同语言真实消费方」或「在 DESIGN_NOTATION_MIRRORS 里显式承认」。

    四条判据（R9-SH-7 之后，豁免不再是免检）：
    ①未登记且无消费方的镜像 → 红（防镜像沦为无人消费的假保证）；
    ②登记了但**已经有人消费** → 红（豁免的前提是「零消费方的设计标注」，前提没了就必须
      从表里删掉；否则字段漂移与兼容性检查被一句过期的声明悄悄跳过）；
    ③登记了但生成目录里已无该镜像 → 红（防清单堆积死条目）；
    ④镜像目录缺失 → 红（空扫描面不得恒绿）。
    ②③仅在已有镜像面时判定——整棵树不存在时 ④ 已给出更准确的根因，再叠一堆只是把同一个
    缺陷伪装成多个。
    """
    failures: list[str] = []
    seen: set[str] = set()
    for lang, directory in _mirror_dirs():
        if not directory.is_dir():
            failures.append(f"生成镜像目录缺失：{directory}（扫描面为空不放行）")
            continue
        pattern = "*.cs" if lang == "cs" else "*.kt"
        stems = {path.stem for path in sorted(directory.glob(pattern))}
        seen |= stems
        consumed = _consumed_names(lang, stems)
        for path in sorted(directory.glob(pattern)):
            if path.stem in DESIGN_NOTATION_MIRRORS:
                if path.stem in consumed:
                    failures.append(
                        f"豁免已不成立：{path.stem}（{lang}）已被端侧真实消费——必须从 "
                        "DESIGN_NOTATION_MIRRORS 删掉（该表的口径是「零消费方的设计标注镜像」）")
                continue
            if path.stem not in consumed:
                failures.append(
                    f"生成镜像无真实消费方：{path.stem}（{path.name}）——要么接进端侧消费方，"
                    "要么显式登记进 DESIGN_NOTATION_MIRRORS 并说明保留理由（AD-244 口径）")
    for declared in sorted(DESIGN_NOTATION_MIRRORS):
        if seen and declared not in seen:
            failures.append(
                f"豁免清单死条目：DESIGN_NOTATION_MIRRORS 含 {declared}，"
                "但生成目录中已无该镜像（清单须与生成面同步收窄）")
    return failures


def main() -> int:
    failures = (check_schemas() + check_vectors() + check_generated_models()
                + check_real_models() + check_mirror_consumption())
    if failures:
        for f in failures:
            print(f"❌ {f}")
        return 1
    print("✅ 契约兼容性验证通过（schemas/vectors JSON 有效 + C#/Kotlin 生成模型与 "
          "schema 一致 + 手写模型名实对账 + 生成镜像消费面已登记——阶段 B 完成标准）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
