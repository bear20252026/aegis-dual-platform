# verify_agent_catalog.py —— PY-202（2026-09-26 审计）：agent-redteam.yml 的
# heredoc 内联 Python（open 无 close、结构变化时 KeyError 原始栈、断言与
# redteam_test.py 双源）移出为单源脚本——内容只做 action-catalog 读取与断言。
# 断言（PY-254 与 pytest 侧四项同源）：default_deny 开启 + policy_version
# 非空 + 首批全部只读 + int 预算（Agent 门禁 fail-closed）。
# 用法：python contracts/codegen/verify_agent_catalog.py
# 退出码：0=通过 / 1=断言失败 / 2=读取或解析错误
# 风格参照同目录 analyze_action_catalog.py（专项断言不与其重复检查项交叉：
# 重复名/风险冲突/audit/fixtures 由 analyze_action_catalog.py 负责）。

import pathlib
import sys

import yaml

CATALOG = pathlib.Path(__file__).resolve().parent.parent / "policy" / "action-catalog.yaml"


def check(doc) -> list[str]:
    """返回问题列表（空=通过）。结构异常给中文明确报错，不抛原始 KeyError。

    PY-254（2026-10-01 审计）：CI 脚本此前只断言 default_deny/read_only 两项，
    pytest 侧（agent/tests/redteam_test.py）断言四项——门禁弱于测试，catalog
    可在 CI 绿灯下丢失 policy_version/预算登记。现四项同源：default_deny +
    policy_version 非空 + read_only + int 预算（max_actions/max_bytes>0，
    排除 bool——PY-251 口径）。
    """
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["action-catalog.yaml 顶层必须是映射"]
    if doc.get("default_deny") is not True:
        errors.append("default_deny 必须显式为 true（未登记 action 不可用——fail-closed）")
    if not doc.get("policy_version"):
        errors.append("policy_version 必须非空声明（单源）")
    actions = doc.get("actions")
    if not isinstance(actions, list) or not actions:
        return errors + ["actions 必须是非空列表"]
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"actions[{i}]: 非字典条目")
            continue
        name = action.get("name") or f"<unnamed-{i}>"
        if action.get("read_only") is not True:
            errors.append(f"'{name}' read_only 必须为 true（首批只读门禁）")
        budget = action.get("budget") or {}
        for key in ("max_actions", "max_bytes"):
            value = budget.get(key)
            # PY-251 口径：bool 是 int 子类——max_actions: true 不得过门禁
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(f"'{name}' budget.{key} 必须为正整数（当前: {value!r}）")
    return errors


def main() -> int:
    if not CATALOG.exists():
        print(f"❌ 找不到 {CATALOG}")
        return 2

    try:
        doc = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"❌ YAML 解析错误: {e}")
        return 2

    errors = check(doc)

    if not errors:
        print("✅ action-catalog default_deny + policy_version + 首批只读 + int 预算——Agent 门禁闭合")
        return 0

    print(f"⚠️ 发现 {len(errors)} 个问题：")
    for err in errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
