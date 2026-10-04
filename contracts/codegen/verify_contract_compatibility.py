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
import sys

# PY-042：需要重生成内容做 diff——平铺导入同目录生成器模块
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from generate_csharp import SKIP_SCHEMAS
from generate_csharp import generate as generate_cs_model
from generate_kotlin import generate as generate_kt_model

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
VECTORS = ROOT / "vectors"
# 审计第六轮（2026-10-03）：仓库根——真实手写模型对账的锚定根（不经 ROOT，
# 因单测把 ROOT/SCHEMAS/VECTORS 重定向到合成契约树，真实模型仍在仓库原位）。
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# 审计第六轮（2026-10-03）：schema ↔ 真实手写模型对账映射。
# 此前 check_generated_models 只把 schema 与其自身生成镜像比对——「契约兼容性 =
# 跨语言一致」在 schema 与自己镜像之间自证，从不触及两端实际运行的手写类型
#（AD-244 已坦白）。本表把每条冻结契约对到其消费端手写实现，缺失/可选性漂移即红。
# 值 = (模型文件, 语言, 类型名)。只读这些文件，绝不写。
REAL_MODEL_CONTRACTS: dict[str, tuple[pathlib.Path, str, str]] = {
    "approval.schema.json": (
        REPO_ROOT / "windows" / "src" / "Aegis.Windows.App" / "Broker" / "Decision.cs",
        "cs", "ApprovalRequest"),
    "audit-event.schema.json": (
        REPO_ROOT / "windows" / "src" / "Aegis.Windows.App" / "Broker" / "Audit" / "AuditEvent.cs",
        "cs", "AuditEvent"),
    "capability.schema.json": (
        REPO_ROOT / "core" / "rust-policy-core" / "src" / "capability.rs",
        "rust", "Capability"),
}

# 审计第六轮：已声明为「设计标注镜像」的生成物——AD-244：当前零消费方，保留仅为
# 跨语言契约镜像完整性。列于此显式承认为非承重镜像；此集外的任何镜像若无真实
# 消费方则 check_mirror_consumption 计入 failures（防镜像悄悄沦为无人消费的假保证）。
DESIGN_NOTATION_MIRRORS = {
    "ApprovalContract", "AuditEventContract", "CapabilityContract",
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


def main() -> int:
    failures = check_schemas() + check_vectors() + check_generated_models()
    if failures:
        for f in failures:
            print(f"❌ {f}")
        return 1
    print("✅ 契约兼容性验证通过（schemas/vectors JSON 有效 + C#/Kotlin 模型与 "
          "schema 一致——跨语言一致——阶段 B 完成标准）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
