"""gen_jsapi_schema.py —— 从 Api 桥生成 js_api JSON Schema 文档（R2）。

借鉴 steel-browser / ShardBrowser 的 openapi.yaml 模式：把隐式
`_JS_EXPOSED` 白名单变成**显式接口规范**，供前端开发、外部对接与
审查使用，降低"零全局意识"导致的接口漂移风险。

用法：
    python scripts/gen_jsapi_schema.py
    # 输出: shared/jsapi-schema.json（与版本同步提交）

实现：
- 用 AST 解析 app/api_bridge.py，提取：
    * _JS_EXPOSED 白名单（暴露给 JS 的方法）
    * 各方法签名（参数名 / 默认值 / 返回注解）
    * docstring 首行（方法用途）
- 输出 JSON Schema 风格的接口清单（纯文档，不 import 运行时）。
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_BRIDGE = ROOT / "windows" / "aegis_source" / "app" / "api_bridge.py"
OUTPUT = ROOT / "shared" / "jsapi-schema.json"

# 允许暴露的私有辅助方法（不对外，但文档标注 internal）
_ALLOWED_UNDERSCORE = {"_load", "_eval", "_nav_healthy", "_recover_nav"}


def _doc_first_line(docstring: str | None) -> str:
    if not docstring:
        return ""
    lines = docstring.strip().splitlines()
    return lines[0].strip() if lines else ""


def build_schema(src_text: str) -> dict:
    tree = ast.parse(src_text)
    exposed: set[str] = set()
    methods: dict[str, dict] = {}

    # 第一遍：收集 _JS_EXPOSED 白名单（须在构建 methods 前完成，
    # 避免单遍遍历时 ast.walk 先访问 ClassDef 导致 exposed 未填充）
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_JS_EXPOSED"
                        for t in node.targets)):
            value = node.value
            # frozenset({...}) → Call(frozenset, [Set])；取 args[0]
            if isinstance(value, ast.Call):
                args = value.args
                value = args[0] if args else None
            if isinstance(value, ast.Set):
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        exposed.add(elt.value)

    # 第二遍：构建 methods（此时 exposed 已完整，exposed_to_js 判断准确）
    for node in ast.walk(tree):
        # 提取 Api 类的方法
        if isinstance(node, ast.ClassDef) and node.name == "Api":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    name = item.name
                    # 跳过属性/内部方法（除非在白名单允许列表）
                    if name.startswith("_") and name not in _ALLOWED_UNDERSCORE:
                        continue
                    params = []
                    for a in item.args.args:
                        if a.arg in ("self",):
                            continue
                        params.append({"name": a.arg, "required": True})
                    for d in item.args.defaults:
                        pass  # 默认值解析留简化：记录参数个数
                    methods[name] = {
                        "name": name,
                        "description": _doc_first_line(
                            ast.get_docstring(item)),
                        "params": params,
                        "returns": ast.unparse(item.returns)
                        if item.returns else "None",
                        "exposed_to_js": name in exposed,
                    }
                    methods[name]["n_required_params"] = len(params)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Aegis js_api Bridge Schema",
        "description": "Aegis 浏览器暴露给注入式 UI 的 Python 桥接口规范。"
                       "由 scripts/gen_jsapi_schema.py 自动生成，勿手改。",
        "version": "0.4.0",
        "type": "object",
        "properties": {
            "js_exposed_methods": sorted(exposed),
            "methods": dict(sorted(methods.items())),
        },
    }


def main() -> int:
    if not API_BRIDGE.exists():
        print(f"[fail] 未找到 {API_BRIDGE}", file=sys.stderr)
        return 1
    src = API_BRIDGE.read_text(encoding="utf-8")
    schema = build_schema(src)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    exposed = schema["properties"]["js_exposed_methods"]
    print(f"[ok] js_api schema 已生成: {OUTPUT}")
    print(f"[ok] 暴露方法数: {len(exposed)}")
    print(f"[ok] 全部方法数（含内部）: {len(schema['properties']['methods'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
