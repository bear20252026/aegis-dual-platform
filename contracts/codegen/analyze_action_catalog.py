# 由账号2生成
# 静态分析器（照搬 warden analysis.rs 精神——轻量版适配 Aegis action-catalog.yaml）。
# 检查：①重复 action name ②同 scope 风险冲突 ③audit 缺失 ④redteam_fixtures 缺失
#       ⑤confirmation 显式声明 + 词表 + 与 read_only 一致（R9-B46 / 台账 Q15）。
#       ⑤ 的存在理由：`confirmation` 全仓零运行时消费者（Agent 侧没有确认 UI），
#       「列存在但没人读」不能靠删列掩盖，也不能靠注记声明——它现在被当成
#       **必填的意图声明**判：漏写、乱写、与 read_only 矛盾都判红。
# 用法：python contracts/codegen/analyze_action_catalog.py
# 退出码：0=通过 / 1=发现问题 / 2=解析错误

import pathlib
import sys

import yaml

CATALOG = pathlib.Path(__file__).resolve().parent.parent / "policy" / "action-catalog.yaml"

# R9-B46 / Q15：`confirmation` 的词表。运行时不读它（Agent 无确认 UI），所以这里
# 只允许「显式声明 + 与只读性一致」这一种用法；要新增取值=契约面变更，另批定稿。
CONFIRMATION_VOCAB = frozenset({"none", "required"})

# PY-195（2026-09-26 审计）：取 actions 列表各条目的真实 YAML 行号
#（start_mark.line 为 0 基——报告 +1）。拿不到标记（理论不可达——safe_load
# 已成功即意味着 compose 亦可）时报列表下标并在文案中标注是下标不是行号，
# 不再让"首次出现行 N"撒谎。
def _action_start_lines(src: str, count: int) -> list[tuple[int | None, bool]]:
    """返回 [(1 基行号或 None, 是否真实行号)]——与 actions 列表下标对齐。"""
    try:
        root = yaml.compose(src)
        # compose 返回 Node 树：MappingNode.value 是 (key_node, value_node) 元组列表
        actions_node = None
        if isinstance(root, yaml.MappingNode):
            for key_node, value_node in root.value:
                if isinstance(key_node, yaml.ScalarNode) and key_node.value == "actions":
                    actions_node = value_node
                    break
        if actions_node is None or not isinstance(actions_node, yaml.SequenceNode):
            return [(None, False)] * count
        out: list[tuple[int | None, bool]] = []
        for item in actions_node.value:
            line = item.start_mark.line + 1 if item.start_mark is not None else None
            out.append((line, True))
        return out
    except Exception:  # noqa: BLE001
        # （PY-195：标记提取失败降级为下标——不掩盖后续校验；盲捕与 analyze
        # 主入口同口径——compose 对任意 safe_load 可解析输入不再抛非预期类型）
        return [(None, False)] * count


def analyze(src: str) -> list[str]:
    """返回问题列表（空=通过）。"""
    errors: list[str] = []
    try:
        doc = yaml.safe_load(src)
    except yaml.YAMLError as e:
        return [f"YAML 解析错误: {e}"]

    if not doc or "actions" not in doc:
        return ["action-catalog.yaml 缺少 'actions' 字段"]

    actions = doc["actions"]
    if not isinstance(actions, list):
        return ["'actions' 必须是列表"]

    seen_names: dict[str, str] = {}  # name -> 首次出现的位置描述（行号或下标）
    scope_risk: dict[str, list[str]] = {}

    marks = _action_start_lines(src, len(actions))
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"actions[{i}]: 非字典条目")
            continue

        name = action.get("name", f"<unnamed-{i}>")

        # ① 重复 action name（PY-195：定位信息记录真实 YAML 行号）
        line, from_mark = marks[i] if i < len(marks) else (None, False)
        if from_mark and line is not None:
            where = f"行 {line}"
        else:
            where = f"列表下标 {i}（行号不可得）"
        if name in seen_names:
            # PY-195：报"首次出现"位置（存储的第一次出现处），非当前位置
            errors.append(f"重复 action name '{name}'（首次出现{seen_names[name]}）")
        seen_names.setdefault(name, where)

        # ② 同 scope 不同 risk 冲突
        scope = action.get("scope", "")
        risk = action.get("risk", "unknown")
        key = f"{scope}"
        if key not in scope_risk:
            scope_risk[key] = []
        if risk not in scope_risk[key]:
            scope_risk[key].append(risk)
        if len(scope_risk[key]) > 1:
            errors.append(f"'{name}' scope '{scope}' 存在多种 risk 等级: {scope_risk[key]}")

        # ③ audit 缺失
        if not action.get("audit", False):
            errors.append(f"'{name}' 缺少 audit: true（安全审计必须）")

        # ④ redteam_fixtures 缺失
        if not action.get("redteam_fixtures"):
            errors.append(f"'{name}' 缺少 redteam_fixtures（安全测试必须）")

        # ⑤ confirmation：必填意图声明 + 词表 + 与 read_only 一致（判定面之外，见文件头）
        confirmation = action.get("confirmation")
        read_only = action.get("read_only") is True
        if confirmation is None:
            errors.append(
                f"'{name}' 缺 confirmation（写 none 是「确认过：不需要」，不是漏写）")
        elif confirmation not in CONFIRMATION_VOCAB:
            errors.append(
                f"'{name}' confirmation '{confirmation}' 不在词表 "
                f"{sorted(CONFIRMATION_VOCAB)}（扩词表属契约面变更，另批定稿）")
        elif read_only != (confirmation == "none"):
            errors.append(
                f"'{name}' read_only={read_only} 与 confirmation='{confirmation}' 矛盾"
                "（只读免确认；非只读必须 required）")

    return errors

def main() -> int:
    if not CATALOG.exists():
        print(f"❌ 找不到 {CATALOG}")
        return 2

    src = CATALOG.read_text(encoding="utf-8")
    errors = analyze(src)

    if not errors:
        print("✅ action-catalog 静态分析通过（无重复/冲突/缺失）")
        return 0

    print(f"⚠️ 发现 {len(errors)} 个问题：")
    for err in errors:
        print(f"  - {err}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
