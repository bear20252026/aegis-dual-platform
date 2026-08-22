# 由账号2生成
# 静态分析器（照搬 warden analysis.rs 精神——轻量版适配 Aegis action-catalog.yaml）。
# 检查：①重复 action name ②同 scope 风险冲突 ③audit 缺失 ④redteam_fixtures 缺失。
# 用法：python contracts/codegen/analyze_action_catalog.py
# 退出码：0=通过 / 1=发现问题 / 2=解析错误

import sys
import pathlib
import yaml

CATALOG = pathlib.Path(__file__).resolve().parent.parent / "policy" / "action-catalog.yaml"

def analyze(src: str) -> list[str]:
    """返回问题列表（空=通过）。"""
    errors: list[str] = []
    try:
        doc = yaml.safe_load(src)
    except Exception as e:
        return [f"YAML 解析错误: {e}"]

    if not doc or "actions" not in doc:
        return ["action-catalog.yaml 缺少 'actions' 字段"]

    actions = doc["actions"]
    if not isinstance(actions, list):
        return ["'actions' 必须是列表"]

    seen_names: dict[str, int] = {}
    scope_risk: dict[str, list[str]] = {}

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"actions[{i}]: 非字典条目")
            continue

        name = action.get("name", f"<unnamed-{i}>")

        # ① 重复 action name
        if name in seen_names:
            errors.append(f"重复 action name '{name}'（首次出现行 {seen_names[name]}）")
        seen_names[name] = i

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
