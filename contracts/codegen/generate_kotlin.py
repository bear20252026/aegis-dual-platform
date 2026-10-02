#!/usr/bin/env python3
"""generate_kotlin.py —— contracts/codegen（蓝图阶段 B——由契约生成 Kotlin 模型）。

从 contracts/schemas/*.json 生成 Kotlin data class（与阶段 D android/contracts
对齐——不手工维护平行 Schema——蓝图）。属性由 schema required/properties 驱动。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# PY-243（2026-10-01 审计）：嵌套子模型命名规则单源（与 generate_csharp 共享）
from ident import singular_pascal as _singular_pascal

# PY-242（2026-10-01 审计）：describe_value_domain 两份逐字重复抽单源
from value_domain import describe_value_domain

SCHEMAS = pathlib.Path(__file__).resolve().parents[1] / "schemas"
# PY-102：发布事实声明（release.schema.json 校验 shared/release.json 用）
# 不是跨语言消息契约——不参与模型生成
SKIP_SCHEMAS = {"release.schema.json"}
OUT = (pathlib.Path(__file__).resolve().parents[1] / ".." / "android" / "contracts"
       / "src" / "main" / "kotlin" / "com" / "aegis" / "contracts" / "generated")


# PY-100：Kotlin 类型映射（与 generate_csharp.cs_type 对偶）——number 不再
# 降级 Any；未知类型 fail-closed
KT_TYPE_MAP = {
    "string": "String",
    "integer": "Long",
    "number": "Double",
    "boolean": "Boolean",
    "object": "Any",
}


def kt_type(prop: dict, nested_item: str | None = None) -> str:
    t = prop.get("type", "string")
    if t == "array":
        items = prop.get("items", {})
        it = items.get("type", "string")
        # PY-243（2026-10-01 审计）：与 generate_csharp.cs_type 对偶——items
        # 为 object 且带 properties 时生成嵌套子模型；自由 object 保持 List<Any>。
        if it == "object":
            if "properties" in items:
                if not nested_item:
                    raise ValueError(
                        "数组 items 为 object 且带 properties——必须生成嵌套子模型"
                        "（fail-closed——禁止降级 List<Any>）")
                return f"List<{nested_item}>"
            return "List<Any>"
        if it not in KT_TYPE_MAP:
            raise ValueError(f"数组 items 类型不支持: {it!r}（fail-closed——禁止静默降级）")
        return f"List<{KT_TYPE_MAP[it]}>"
    if t not in KT_TYPE_MAP:
        raise ValueError(f"schema 类型不支持: {t!r}（fail-closed——禁止静默降级 Any）")
    return KT_TYPE_MAP[t]


# PY-188（2026-09-26 审计，收尾批完整化）：enum/const 生成「基础类型属性 +
# 常量 object」——与 generate_csharp.enum_constant_lines 对偶：属性保持
# String/基础类型（不破坏镜像消费方），另生成 {Name}Values object 提供编译期
# 拼写锚点（值域以 schema 为单源）。
# PY-242（2026-10-01 审计）：describe_value_domain 移至 value_domain.py 单源
#（与 generate_csharp 共享），此处保留导入供测试与文档锁定值域。


def _upper_snake(value: str) -> str:
    """schema 值 → UPPER_SNAKE 标识符段：require_confirmation→REQUIRE_CONFIRMATION。"""
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", value) if t]
    out = "_".join(t.upper() for t in tokens)
    return out or "VALUE"


def _kt_literal_type(value) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Long"
    if isinstance(value, float):
        return "Double"
    return "String"


def _kt_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, float):
        return repr(value)
    return str(value)


def enum_constant_lines(schema: dict, name: str) -> list[str]:
    """生成 {Name}Values 常量 object（PY-188）——无 enum/const 属性时返回空。"""
    props = schema.get("properties", {})
    entries: list[tuple[str, object, str]] = []  # (常量名, 字面值, 属性值域描述)
    for pname, p in props.items():
        if "enum" in p:
            domain = describe_value_domain(p)
            entries.extend((f"{_upper_snake(pname)}_{_upper_snake(str(v))}", v, domain)
                           for v in p["enum"])
        elif "const" in p:
            entries.append((f"{_upper_snake(pname)}", p["const"], describe_value_domain(p)))
    # PY-289（2026-10-02 审计）：常量名派生（值归一 upper_snake）无去重——
    # 不同 enum 值（如 "a-b" 与 "a_b"）归一后撞名产生重复常量（Kotlin 编译
    # 错 redeclaration）。生成前查重，撞名 fail-closed 抛 ValueError（与
    # generate_csharp 同口径——提示改 enum 值或属性名）。
    seen_constants: set[str] = set()
    for const_name, _value, _domain in entries:
        if const_name in seen_constants:
            raise ValueError(
                f"enum 常量名撞名: {const_name}（{name} 的属性/值经 upper_snake "
                "归一后同名——改 enum 值或属性名后重新生成——fail-closed）")
        seen_constants.add(const_name)
    if not entries:
        return []
    lines = [
        "",
        (f"/** PY-188（2026-09-26 审计）：{name} 值域常量——schema enum/const 单源，"
         "属性保持基础类型以兼容既有消费方。 */"),
        f"object {name}Values {{",
    ]
    for const_name, value, domain in entries:
        suffix = f" // {domain}" if domain else ""
        lines.append(
            f"    const val {const_name}: {_kt_literal_type(value)} = {_kt_literal(value)}{suffix}")
    lines.append("}")
    return lines


def _nested_class_lines(items_schema: dict, nested_name: str) -> list[str]:
    """PY-243：数组 items(object+properties) 的嵌套子模型——data class +
    值域常量 object（与 generate_csharp._nested_record_lines 对偶）。
    嵌套层内再出现 array-of-object 属契约面过深，fail-closed。"""
    nprops = items_schema.get("properties", {})
    nrequired = set(items_schema.get("required", []))
    nunknown = nrequired - set(nprops)
    if nunknown:
        raise ValueError(
            f"嵌套 items required 引用未定义属性: {sorted(nunknown)}（fail-closed）")
    nordered = [k for k in nprops if k in nrequired] + [k for k in nprops if k not in nrequired]
    lines = [
        "",
        (f"/** PY-243（2026-10-01 审计）：{nested_name} 嵌套子模型——"
         "schema 数组 items 单源（字段获得编译期锚点，不再降级 Any）。 */"),
        f"data class {nested_name}(",
    ]
    for pname in nordered:
        p = nprops[pname]
        if p.get("type") == "array":
            raise ValueError("嵌套 items 内不支持数组属性（fail-closed——契约面过深）")
        t = kt_type(p)
        # 尾逗恒定输出（ktlint trailing-comma-on-declaration-site——A-2 门禁扩面）
        if pname in nrequired:
            lines.append(f"    val {pname}: {t},")
        else:
            lines.append(f"    val {pname}: {t}? = null,")
    lines.append(")")
    # enum_constant_lines 自带 Values 后缀——传嵌套类型名本身
    lines.extend(enum_constant_lines(items_schema, nested_name))
    return lines


def generate(schema: dict, name: str) -> str:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    # PY-197（2026-09-26 审计）：required 引用未定义属性此前被静默丢弃——
    # 必填约束无声丢失（fail-open）。先算 unknown 集合，非空抛 ValueError
    #（fail-closed——与 generate_csharp 同口径）。
    unknown = required - set(props)
    if unknown:
        raise ValueError(
            f"required 引用未定义属性: {sorted(unknown)}（schema={name}——fail-closed）")
    # PY-243：array-of-object+properties 预扫描（与 generate_csharp 同规则同命名）
    nested_models: list[tuple[str, dict]] = []
    nested_by_pname: dict[str, str] = {}
    for pname, p in props.items():
        items = p.get("items", {}) if p.get("type") == "array" else {}
        if items.get("type") == "object" and "properties" in items:
            nested_name = f"{name}{_singular_pascal(pname)}"
            nested_models.append((nested_name, items))
            nested_by_pname[pname] = nested_name
    # PY-100：required 区分——必选在前（与 C# 对偶，构造可读性），组内保持
    # schema 声明序；非必选生成可空类型 + 默认 null
    ordered = [k for k in props if k in required] + [k for k in props if k not in required]
    lines = [
        "// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）",
        "package com.aegis.contracts.generated",
        "",
        f"data class {name}(",
    ]
    for pname in ordered:
        p = props[pname]
        t = kt_type(p, nested_item=nested_by_pname.get(pname))
        # 尾逗恒定输出（ktlint trailing-comma-on-declaration-site——A-2 门禁扩面）
        if pname in required:
            lines.append(f"    val {pname}: {t},")
        else:
            lines.append(f"    val {pname}: {t}? = null,")
    lines.append(")")
    for nested_name, items_schema in nested_models:
        lines.extend(_nested_class_lines(items_schema, nested_name))
    lines.extend(enum_constant_lines(schema, name))
    return "\n".join(lines)


def contract_name(schema_file: pathlib.Path) -> str:
    """将 action.schema.json 转为稳定且合法的 ActionContract 类型名。"""
    stem = schema_file.stem.removesuffix(".schema")
    return "".join(part[:1].upper() + part[1:] for part in stem.split("-")) + "Contract"


def main() -> int:
    # AD-244（2026-09-26 审计）：Approval/AuditEvent/Capability/UpdateManifest/
    # Version 五份 Kotlin 生成物在 Android 代码中当前零消费——保留生成的原因
    # 是「跨语言契约镜像完整性」（与 C# 镜像同构对账，schema 漂移即门禁红）；
    # 收窄生成范围会让镜像失去对账意义，故保留（取舍说明同步
    # verify_contract_compatibility.check_generated_models）。
    out_dir = OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: set[str] = set()
    for f in sorted(SCHEMAS.glob("*.json")):
        if f.name in SKIP_SCHEMAS:
            continue
        # PY-288（2026-10-02 审计）：schema 文件坏 JSON/不可读此前裸栈——
        # 干净报告 + return 1（与 generate_csharp 同口径）
        try:
            schema = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ❌ schema 读取/解析失败: {f.name}: {exc}")
            return 1
        name = contract_name(f)
        # PY-232（2026-10-01 审计）：write_text 显式 newline="\n"（同
        # generate_csharp——防 Windows 重生成 CRLF 漂移、git diff 假红）
        (out_dir / f"{name}.kt").write_text(
            generate(schema, name) + "\n", encoding="utf-8", newline="\n")
        generated.add(f"{name}.kt")
        print(f"  ✅ 生成 Kotlin 模型: {name}.kt")
    # 陈旧清理（差集删除）：此前 glob("*.schema.kt") 与生成名 {Name}Contract.kt
    # 永不匹配——清理是 no-op，被删除 schema 的旧生成文件永久残留
    for stale in out_dir.glob("*Contract.kt"):
        if stale.name not in generated:
            stale.unlink()
            print(f"  🗑 移除陈旧生成文件: {stale.name}")
    print(f"Kotlin 模型生成完成（{len(generated)} 个——contracts 事实来源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
