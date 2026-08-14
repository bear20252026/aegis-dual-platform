"""selftest_shell_toolbar.py —— shell_toolbar 模块自检（独立 UTF-8 脚本，避免 shell 编码污染）。

验证点：
1. TOOLBAR_JS 含全部必需占位符（__AEGIS_URL__ / __TABS_JSON__）
2. build_toolbar_js 输出已替换全部占位符
3. URL 原样保留（/ 与查询串不转义）
4. 中文被 ensure_ascii 转义为 \\uXXXX（JS 注入安全）
5. 引号/反斜杠被 JSON 转义
6. 注入后的标签 JSON 可被 json.loads 还原（round-trip）
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.shell_toolbar import TOOLBAR_JS, build_toolbar_js

failures = []


def check(name: str, cond: bool, detail: str = ""):
    if not cond:
        failures.append(f"{name}: {detail}")


# 1) TOOLBAR_JS 含两个占位符
check("TOOLBAR_JS 含 __AEGIS_URL__", "__AEGIS_URL__" in TOOLBAR_JS)
check("TOOLBAR_JS 含 __TABS_JSON__", "__TABS_JSON__" in TOOLBAR_JS)

# 2) build 输出替换全部占位符
url = "https://example.com/a?b=1&c=2"
tabs = {"tabs": [{"title": "测试\"引号\"", "url": "https://x.cn"}], "current": 0}
out = build_toolbar_js(url, tabs)
check("占位符 __AEGIS_URL__ 已替换", "__AEGIS_URL__" not in out)
check("占位符 __TABS_JSON__ 已替换", "__TABS_JSON__" not in out)

# 3) URL 原样保留
check("URL 原样保留", "example.com/a?b=1&c=2" in out)

# 4) 中文被 JSON 转义（ensure_ascii）——用 \u 转义写法，ASCII 安全
check("中文按 \\uXXXX 转义", r"\u6d4b\u8bd5" in out)

# 5) 引号被 JSON 转义（\"）
check("引号按 \\\" 转义", r'\"' in out)

# 6) round-trip：提取注入的 TABS_JSON 完整对象并还原
#    定位顶层对象的起点（json.dumps 默认格式为 {"tabs": [...]}）
start = out.find('{"tabs":')
check("可定位注入的标签 JSON", start != -1)
if start != -1:
    # 从 start 起用括号配对找出完整对象
    depth = 0
    end = -1
    for i in range(start, len(out)):
        if out[i] == "{":
            depth += 1
        elif out[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    check("标签 JSON 对象闭合", end != -1)
    if end != -1:
        try:
            restored = json.loads(out[start:end])
            check("标签 JSON round-trip", restored == tabs,
                  f"restored={restored!r}")
        except Exception as exc:
            failures.append(f"标签 JSON 解析失败: {exc!r}")

# 汇总
if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"OK — {len([1])} 项全部通过（占位符/URL/中文转义/引号转义/round-trip）")
print(f"TOOLBAR_JS 长度: {len(TOOLBAR_JS)} 字符")
print(f"shell_toolbar.py 行数: {len(Path('app/shell_toolbar.py').read_text(encoding='utf-8').splitlines())}")
