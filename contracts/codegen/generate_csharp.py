#!/usr/bin/env python3
"""generate_csharp.py —— contracts/codegen（蓝图阶段 B——由契约生成 C# 模型）。

从 contracts/schemas/*.json 生成 C# record（与阶段 C Aegis.Windows.Contracts
对齐——不手工维护平行 Schema——蓝图）。属性由 schema required/properties 驱动。
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# PY-243（2026-10-01 审计）：嵌套子模型命名规则单源（与 generate_kotlin 共享）
from ident import pascal as _pascal
from ident import singular_pascal as _singular_pascal

# PY-242（2026-10-01 审计）：describe_value_domain 两份逐字重复抽单源
from value_domain import describe_value_domain

SCHEMAS = pathlib.Path(__file__).resolve().parents[1] / "schemas"
# PY-102：发布事实声明（release.schema.json 校验 shared/release.json 用）
# 不是跨语言消息契约——不参与模型生成
SKIP_SCHEMAS = {"release.schema.json"}
OUT = (pathlib.Path(__file__).resolve().parents[1] / ".." / "windows" / "src"
       / "Aegis.Windows.App" / "Contracts" / "Generated")


# PY-099：C# 类型映射——number 不再降级 object；未知类型 fail-closed
CS_TYPE_MAP = {
    "string": "string",
    "integer": "long",
    "number": "decimal",
    "boolean": "bool",
    "object": "object",
}


def cs_type(prop: dict, nested_item: str | None = None) -> str:
    t = prop.get("type", "string")
    if t == "array":
        items = prop.get("items", {})
        it = items.get("type", "string")
        # PY-243（2026-10-01 审计）：数组 items 为 object 且带 properties 时
        # 生成嵌套子模型（调用方传嵌套类型名）——内部 platform/format/url/
        # sha256/size 五字段获得编译期锚点，不再降级 List<object>。无
        # properties 的自由 object 保持 List<object>（nothing to anchor）。
        if it == "object":
            if "properties" in items:
                if not nested_item:
                    raise ValueError(
                        "数组 items 为 object 且带 properties——必须生成嵌套子模型"
                        "（fail-closed——禁止降级 List<object>）")
                return f"List<{nested_item}>"
            return "List<object>"
        if it not in CS_TYPE_MAP:
            raise ValueError(f"数组 items 类型不支持: {it!r}（fail-closed——禁止静默降级）")
        return f"List<{CS_TYPE_MAP[it]}>"
    if t not in CS_TYPE_MAP:
        raise ValueError(f"schema 类型不支持: {t!r}（fail-closed——禁止静默降级 object）")
    return CS_TYPE_MAP[t]


# 值类型可空标记——PY-242：cs_nullable 化简后该集合无剩余消费者，删除
#（此前 CS_VALUE_TYPES 分支与默认分支行为相同，属死结构）。


# PY-188（2026-09-26 审计，收尾批完整化）：enum/const 生成「string 属性 +
# 常量类」——属性保持 string 类型（不破坏镜像消费方），另生成
# {Name}Values 静态常量类提供编译期拼写锚点（值域以 schema 为单源）。
# PY-242（2026-10-01 审计）：describe_value_domain 移至 value_domain.py 单源
#（与 generate_kotlin 共享），此处保留导入供测试与文档锁定值域。


def _cs_literal_type(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "long"
    if isinstance(value, float):
        return "decimal"
    return "string"


def _cs_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(value)


def enum_constant_lines(schema: dict, name: str) -> list[str]:
    """生成 {Name}Values 常量类（PY-188）——无 enum/const 属性时返回空。"""
    props = schema.get("properties", {})
    entries: list[tuple[str, object, str]] = []  # (常量名, 字面值, 属性值域描述)
    for pname, p in props.items():
        if "enum" in p:
            domain = describe_value_domain(p)
            entries.extend((f"{_pascal(pname)}{_pascal(str(v))}", v, domain) for v in p["enum"])
        elif "const" in p:
            entries.append((f"{_pascal(pname)}", p["const"], describe_value_domain(p)))
    if not entries:
        return []
    lines = [
        "",
        (f"/// <summary>PY-188（2026-09-26 审计）：{name} 值域常量——schema enum/const 单源，"
         "属性保持基础类型以兼容既有消费方。</summary>"),
        f"public static class {name}Values",
        "{",
    ]
    for const_name, value, domain in entries:
        suffix = f"  // {domain}" if domain else ""
        lines.append(
            f"    public const {_cs_literal_type(value)} {const_name} = {_cs_literal(value)};{suffix}")
    lines.append("}")
    return lines


def cs_nullable(t: str) -> str:
    """PY-242（2026-10-01 审计）：化简死结构——值类型与引用类型此前分两
    分支返回同一 f"{t}?"；实际唯一差异是 object 不加 ?（本即可空）。
    输出字节不变（verify_contract_compatibility 对账锁定）。"""
    if t == "object":
        return t  # object 本即可空
    return f"{t}?"


def _nested_record_lines(items_schema: dict, nested_name: str) -> list[str]:
    """PY-243：数组 items(object+properties) 的嵌套子模型——record + 值域常量
    类（复用 enum_constant_lines，platform/format 的 enum 亦获编译期锚点）。
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
        (f"/// <summary>PY-243（2026-10-01 审计）：{nested_name} 嵌套子模型——"
         "schema 数组 items 单源（字段获得编译期锚点，不再降级 object）。</summary>"),
        f"public sealed record {nested_name}(",
    ]
    for index, pname in enumerate(nordered):
        p = nprops[pname]
        if p.get("type") == "array":
            raise ValueError("嵌套 items 内不支持数组属性（fail-closed——契约面过深）")
        t = cs_type(p)
        suffix = "," if index < len(nordered) - 1 else ""
        if pname in nrequired:
            lines.append(f"    {t} {pname}{suffix}")
        else:
            lines.append(f"    {cs_nullable(t)} {pname} = null{suffix}")
    lines.append(");")
    # enum_constant_lines 自带 Values 后缀——传嵌套类型名本身
    lines.extend(enum_constant_lines(items_schema, nested_name))
    return lines


def generate(schema: dict, name: str) -> str:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    # PY-197（2026-09-26 审计）：required 引用不存在的属性时此前被静默丢弃
    #（ordered 推导只看 props 键）——必填约束无声丢失（fail-open）。先算
    # unknown 集合，非空即抛 ValueError（fail-closed——schema 自身损坏必须显式暴露）。
    unknown = required - set(props)
    if unknown:
        raise ValueError(
            f"required 引用未定义属性: {sorted(unknown)}（schema={name}——fail-closed）")
    # PY-243：array-of-object+properties 属性预扫描——登记嵌套子模型类型名
    nested_models: list[tuple[str, dict]] = []  # (类型名, items schema)
    nested_by_pname: dict[str, str] = {}
    for pname, p in props.items():
        items = p.get("items", {}) if p.get("type") == "array" else {}
        if items.get("type") == "object" and "properties" in items:
            nested_name = f"{name}{_singular_pascal(pname)}"
            nested_models.append((nested_name, items))
            nested_by_pname[pname] = nested_name
    # PY-248（2026-10-01 审计）：using 仅在存在数组属性时输出——6 份生成
    # 文件中 4 份零 List<> 使用，无条件注入产生未用 using 噪声。
    has_array = any(p.get("type") == "array" for p in props.values())
    # PY-099：required 区分——必选在前（C# record 可选参数必须位于必选参数
    # 之后），组内保持 schema 声明序；非必选生成可空类型 + 默认 null
    ordered = [k for k in props if k in required] + [k for k in props if k not in required]
    lines = [
        "// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）",
    ]
    if has_array:
        lines.append("using System.Collections.Generic;")
    lines.extend([
        "namespace Aegis.Windows.Contracts.Generated;",
        "",
        f"public sealed record {name}(",
    ])
    for index, pname in enumerate(ordered):
        p = props[pname]
        t = cs_type(p, nested_item=nested_by_pname.get(pname))
        suffix = "," if index < len(ordered) - 1 else ""
        if pname in required:
            lines.append(f"    {t} {pname}{suffix}")
        else:
            lines.append(f"    {cs_nullable(t)} {pname} = null{suffix}")
    lines.append(");")
    for nested_name, items_schema in nested_models:
        lines.extend(_nested_record_lines(items_schema, nested_name))
    lines.extend(enum_constant_lines(schema, name))
    return "\n".join(lines)


def contract_name(schema_file: pathlib.Path) -> str:
    """将 action.schema.json 转为稳定且合法的 ActionContract 类型名。"""
    stem = schema_file.stem.removesuffix(".schema")
    return "".join(part[:1].upper() + part[1:] for part in stem.split("-")) + "Contract"


def main() -> int:
    # AD-244（2026-09-26 审计）：生成的模型（含 Approval/AuditEvent/Capability/
    # UpdateManifest/Version 等）在 C# 应用代码中当前零消费方——保留生成的
    # 原因是「跨语言契约镜像完整性」：contracts/schemas 是冻结契约的事实
    # 来源，C#/Kotlin 生成物作为镜像由 verify_contract_compatibility 逐字节
    # 对账（schema 漂移/手改生成物即门禁红）。不得因暂时无消费方而收窄
    # 生成范围——那会让镜像失去对账意义。
    out_dir = OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: set[str] = set()
    for f in sorted(SCHEMAS.glob("*.json")):
        if f.name in SKIP_SCHEMAS:
            continue
        schema = json.loads(f.read_text(encoding="utf-8"))
        name = contract_name(f)
        # PY-232（2026-10-01 审计）：write_text 显式 newline="\n"——Windows
        # 默认会把 \n 翻译为 CRLF，core.autocrlf 关闭的环境重生成即 CRLF
        # 漂移、git diff 门禁假红。锁定 LF（与 git 归一存储一致）。
        (out_dir / f"{name}.cs").write_text(
            generate(schema, name) + "\n", encoding="utf-8", newline="\n")
        generated.add(f"{name}.cs")
        print(f"  ✅ 生成 C# 模型: {name}.cs")
    # 陈旧清理（差集删除）：此前 glob("*.schema.cs") 与生成名 {Name}Contract.cs
    # 永不匹配——清理是 no-op，被删除 schema 的旧生成文件永久残留
    for stale in out_dir.glob("*Contract.cs"):
        if stale.name not in generated:
            stale.unlink()
            print(f"  🗑 移除陈旧生成文件: {stale.name}")
    print(f"C# 模型生成完成（{len(generated)} 个——contracts 事实来源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
