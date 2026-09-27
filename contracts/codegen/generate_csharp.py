#!/usr/bin/env python3
"""generate_csharp.py —— contracts/codegen（蓝图阶段 B——由契约生成 C# 模型）。

从 contracts/schemas/*.json 生成 C# record（与阶段 C Aegis.Windows.Contracts
对齐——不手工维护平行 Schema——蓝图）。属性由 schema required/properties 驱动。
"""

from __future__ import annotations

import json
import pathlib
import sys

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


def cs_type(prop: dict) -> str:
    t = prop.get("type", "string")
    if t == "array":
        items = prop.get("items", {}).get("type", "string")
        if items not in CS_TYPE_MAP:
            raise ValueError(f"数组 items 类型不支持: {items!r}（fail-closed——禁止静默降级）")
        return f"List<{CS_TYPE_MAP[items]}>"
    if t not in CS_TYPE_MAP:
        raise ValueError(f"schema 类型不支持: {t!r}（fail-closed——禁止静默降级 object）")
    return CS_TYPE_MAP[t]


# 值类型可空标记（引用类型 string?/List<T>? 由统一后缀处理）
CS_VALUE_TYPES = {"long", "decimal", "bool"}


# PY-188（2026-09-26 审计）——enum/const 支持的降级取舍：
# 6 份 schema 含 enum/const，此前类型映射完全忽略（C#/Kotlin 模型全部降级
# 为裸 string）。首选方案是生成 C# enum/Kotlin 常量类，但生成物落盘于
# windows/src/Aegis.Windows.App/Contracts/Generated 与 android/contracts/.../
# generated——PY-N1 批次文件范围不含 windows/src 与 android/，无条件改生成
# 输出会使本仓库生成物与生成器漂移（verify_contract_compatibility 的
# 重生成 diff 门禁必红）。经 grep 确认生成物当前零消费方（C#/Kotlin 应用
# 代码均未引用 Generated 命名空间——见 AD-244），升级 enum 生成不会破坏
# 消费方，但需要同步重生成落盘产物（越范围）。故本批次退化为：
# 「值域注释（本注释 + describe_value_domain 元数据 API）+ 单测锁定」——
# 单测锁定 schema enum/const 值域与生成器降级行为，待后续批次连同落盘
# 产物一并升级为 enum 类型生成。
def describe_value_domain(prop: dict) -> str:
    """提取属性的 enum/const 值域描述（PY-188 降级版——仅元数据不改进模型）。

    enum → "enum: A | B | C"；const → "const: X"；两者皆无 → ""。
    """
    if "enum" in prop:
        values = prop["enum"]
        rendered = " | ".join(str(v) for v in values)
        return f"enum: {rendered}"
    if "const" in prop:
        return f"const: {prop['const']}"
    return ""


def cs_nullable(t: str) -> str:
    if t in CS_VALUE_TYPES:
        return f"{t}?"
    if t == "object":
        return t  # object 本即可空
    return f"{t}?"


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
    # PY-099：required 区分——必选在前（C# record 可选参数必须位于必选参数
    # 之后），组内保持 schema 声明序；非必选生成可空类型 + 默认 null
    ordered = [k for k in props if k in required] + [k for k in props if k not in required]
    lines = [
        "// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）",
        "using System.Collections.Generic;",
        "namespace Aegis.Windows.Contracts.Generated;",
        "",
        f"public sealed record {name}(",
    ]
    for index, pname in enumerate(ordered):
        p = props[pname]
        t = cs_type(p)
        suffix = "," if index < len(ordered) - 1 else ""
        if pname in required:
            lines.append(f"    {t} {pname}{suffix}")
        else:
            lines.append(f"    {cs_nullable(t)} {pname} = null{suffix}")
    lines.append(");")
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
        (out_dir / f"{name}.cs").write_text(generate(schema, name) + "\n", encoding="utf-8")
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
