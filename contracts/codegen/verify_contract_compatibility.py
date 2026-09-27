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

from generate_csharp import SKIP_SCHEMAS, generate as generate_cs_model
from generate_kotlin import generate as generate_kt_model

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
VECTORS = ROOT / "vectors"


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
