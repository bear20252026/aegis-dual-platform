#!/usr/bin/env python3
"""verify_agent_action_schema.py —— Agent 的 IPC 载荷契约 ⇄ broker 实际必填面双向对账（R9-B87 / Q65）。

为什么要这支门禁：`agent/agent-action.schema.json` 是**新写的一份契约**，
它描述的是 `agent/broker.py` 的 `ProposedAction` 载荷面。而本仓反复栽的那族病是
「把单源的值又抄一遍到散文/另一个文件里」（R9-B41 一批改了五条，R9-B82 又为 README 的下界
专门建了一支门禁）。所以这里的判据**不是**「schema 的 required 等于我数出来的 12 个字段」，
而是「schema 的 required 等于从 broker 现算出来的集合」——字段表改了、schema 不改就红；
schema 多加一个 broker 不要求的字段也红；两边同时改但改得不一样，还是红。

**为什么这份契约在 `agent/` 而不是 `contracts/schemas/`**（本批实测撞出来的，不是审美）：
`contracts/schemas/` 是 codegen 枚举的**冻结跨端契约清单**——
`contracts/codegen/verify_contract_compatibility.py` 会对目录里每个 schema 生成 C#/Kotlin 模型，
而 Agent 的 IPC 载荷面是 Python 独有、不该生成任何跨端模型。把它放进去的实测后果是 6 条用例红
（`generate_csharp.cs_type` 处理不了 `"type": ["string", "null"]` 这种联合形态），
而那红是**位置错的证据**：把一张单端契约塞进跨端清单，等于宣称它参与跨端代码生成。

判的四条（每条都在 tests/python/agent_action_schema_test.py 里以内存注入证伪）：
1. `required` ⇄ broker 必填集合（`dataclasses.MISSING` 字段 ∪ 冻结 schema 的 `CONTRACT_REQUIRED`）
   **双向等值**——多、少都算违规，并点名是哪一侧多的；
2. `properties` ⇄ dataclass 字段名集合双向等值——声明成契约的 object 必须能被
   `proposed_action_from_dict` 真的构造出来（契约里出现一个 broker 没有的属性＝假契约）；
3. `required` 每一项都必须在 `properties` 里（JSON Schema 层的自洽：required 指向不存在的
   属性＝这份 schema 谁都验不过）；
4. 两张面的**分歧本身**由推导得出：Agent 相对冻结 schema 多出来的字段集合必须恰好等于
   「dataclass 无默认 且 不在冻结 required 里」那批——这条判的是「分歧还是那条分歧」，
   而不是「有人悄悄把两张面并成一张」（并成一张的话 Q65 的结论就该改写，不是静默通过）。

退出码：0=一致 / 1=任一条违规 / 2=环境错误（契约文件缺失、broker 导入不了、任一集合为空——
判不出「通过」，因为那种情况下四条判据会全部恒真）。
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
AGENT_SCHEMA = ROOT / "agent" / "agent-action.schema.json"
FROZEN_SCHEMA = ROOT / "contracts" / "schemas" / "action.schema.json"


def broker_surfaces() -> tuple[set[str], set[str], set[str]]:
    """现读 broker：返回（必填字段, 全部字段, 冻结 schema 的 required）。

    三个集合都从代码/契约文件推导，本脚本里没有任何手抄的字段名。"""
    if str(AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_DIR))
    from broker import (
        CONTRACT_REQUIRED,
        ProposedAction,
    )

    fields = {f.name: f for f in dataclasses.fields(ProposedAction)}
    no_default = {
        name
        for name, f in fields.items()
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    return no_default | set(CONTRACT_REQUIRED), set(fields), set(CONTRACT_REQUIRED)


def load_required(doc: dict[str, Any]) -> set[str]:
    required = doc.get("required")
    if not isinstance(required, list) or not all(isinstance(x, str) for x in required):
        raise ValueError("required 必须是非空字符串列表")
    return set(required)


def load_properties(doc: dict[str, Any]) -> set[str]:
    props = doc.get("properties")
    if not isinstance(props, dict):
        raise ValueError("properties 必须是映射")
    return set(props)


def violations(
    agent_required: set[str],
    agent_properties: set[str],
    mandatory: set[str],
    all_fields: set[str],
    frozen_required: set[str],
) -> list[str]:
    """四条判据的纯函数：注入任意一侧的改动都会走到这里，反向锚才落在真逻辑上。"""
    problems: list[str] = []

    if agent_required != mandatory:
        extra = sorted(agent_required - mandatory)
        missing = sorted(mandatory - agent_required)
        problems.append(
            f"契约 required 与 broker 必填面不一致：契约多 {extra}；broker 多 {missing}"
            "（改字段表必须同批改契约，反之也一样）"
        )

    if agent_properties != all_fields:
        ghost = sorted(agent_properties - all_fields)
        undeclared = sorted(all_fields - agent_properties)
        problems.append(
            f"契约 properties 与 ProposedAction 字段集不一致：契约里 broker 没有的 {ghost}；"
            f"broker 有但契约没声明的 {undeclared}（声明成契约却无法构造＝假契约）"
        )

    dangling = sorted(agent_required - agent_properties)
    if dangling:
        problems.append(f"required 指向 properties 里没有的字段：{dangling}（谁都验不过的形状）")

    if agent_required - frozen_required != mandatory - frozen_required:
        problems.append(
            "Agent 相对冻结 schema 多出来的字段必须恰好是「broker 必填而冻结 required 没有」那批："
            f"契约差 {sorted(agent_required - frozen_required)}，"
            f"必填面差 {sorted(mandatory - frozen_required)}。"
            "两张面若真要并成一张，那是行为变更——要改的是 Q65 的结论，不是这里减一行判据"
        )

    return problems


def run() -> int:
    for path in (AGENT_SCHEMA, FROZEN_SCHEMA):
        if not path.is_file():
            print(f"[环境错误] 契约文件缺失：{path}", file=sys.stderr)
            return 2
    try:
        mandatory, all_fields, frozen_required = broker_surfaces()
        agent_doc = json.loads(AGENT_SCHEMA.read_text(encoding="utf-8"))
        frozen_doc = json.loads(FROZEN_SCHEMA.read_text(encoding="utf-8"))
        agent_required = load_required(agent_doc)
        agent_properties = load_properties(agent_doc)
        frozen_doc_required = load_required(frozen_doc)
    except Exception as exc:  # noqa: BLE001 - 环境错误必须与「通过」区分开
        print(f"[环境错误] 无法建立判定面：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if not (mandatory and all_fields and agent_required and agent_properties and frozen_required):
        print("[环境错误] 有集合是空的——四条判据会恒真，不作通过判定", file=sys.stderr)
        return 2
    if frozen_doc_required != frozen_required:
        print(
            f"[环境错误] 冻结 schema 的 required（{sorted(frozen_doc_required)}）与 broker 的 "
            f"CONTRACT_REQUIRED（{sorted(frozen_required)}）已经不同源了——先修 action_contract.py",
            file=sys.stderr,
        )
        return 2

    problems = violations(agent_required, agent_properties, mandatory, all_fields, frozen_required)
    if problems:
        for problem in problems:
            print(f"❌ {problem}", file=sys.stderr)
        print(f"共 {len(problems)} 条（口径见本文件 docstring）", file=sys.stderr)
        return 1

    extras = sorted(agent_required - frozen_required)
    print(
        f"[ok] Agent 契约面与 broker 现算必填面对账通过"
        f"（必填 {len(mandatory)} / 字段 {len(all_fields)} / 冻结 required {len(frozen_required)}；"
        f"Agent 比冻结面多：{extras}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
