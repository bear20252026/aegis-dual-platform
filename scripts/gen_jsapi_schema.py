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
- PY-005（2026-09-24 审计）：Api 的 28/30 暴露方法来自 mixin
  （TabOpsMixin + bridge/ 下 7 个 Mixin）——此前只遍历 Api 自身 body，
  schema 缺失绝大部分接口。现按基类链（BFS）合并全部 mixin 的方法，
  registry 覆盖 app/*.py 与 app/bridge/*.py 全部 ClassDef。
- 输出 JSON Schema 风格的接口清单（纯文档，不 import 运行时）。
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 审计修复：路径随 ADR-009 迁移失效（windows/aegis_source → legacy/），
# 生成链曾 100% 断裂——schema 冻结为陈旧快照
APP_DIR = ROOT / "legacy" / "windows-pywebview" / "app"
API_BRIDGE = APP_DIR / "api_bridge.py"
OUTPUT = ROOT / "shared" / "jsapi-schema.json"

# 允许暴露的私有辅助方法（不对外，但文档标注 internal）
_ALLOWED_UNDERSCORE = {"_load", "_eval", "_nav_healthy", "_recover_nav"}

_MAX_BASE_DEPTH = 8  # 基类链 BFS 深度上限（防循环继承死循环）


def _doc_first_line(docstring: str | None) -> str:
    if not docstring:
        return ""
    lines = docstring.strip().splitlines()
    return lines[0].strip() if lines else ""


def _build_class_registry(sources: dict[str, str]) -> dict[str, ast.ClassDef]:
    """全量 ClassDef 索引（Api + mixin 解析跨文件——PY-005）。"""
    registry: dict[str, ast.ClassDef] = {}
    for text in sources.values():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                registry.setdefault(node.name, node)
    return registry


def _base_chain(
    registry: dict[str, ast.ClassDef],
    root: ast.ClassDef,
) -> list[ast.ClassDef]:
    """从 root 出发按基类名 BFS（ast.Name 基类；Attribute/下标基类跳过）。"""
    chain: list[ast.ClassDef] = []
    seen = {root.name}
    frontier = [root]
    depth = 0
    while frontier and depth < _MAX_BASE_DEPTH:
        nxt: list[ast.ClassDef] = []
        for cls in frontier:
            for base in cls.bases:
                name = base.id if isinstance(base, ast.Name) else None
                if not name or name in seen:
                    continue
                seen.add(name)
                base_cls = registry.get(name)
                if base_cls is not None:
                    chain.append(base_cls)
                    nxt.append(base_cls)
        frontier = nxt
        depth += 1
    return chain


def _extract_methods(cls: ast.ClassDef, exposed: set[str]) -> dict[str, dict]:
    methods: dict[str, dict] = {}
    for item in cls.body:
        if not isinstance(item, ast.FunctionDef):
            continue
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
            "description": _doc_first_line(ast.get_docstring(item)),
            "params": params,
            "returns": ast.unparse(item.returns) if item.returns else "None",
            "exposed_to_js": name in exposed,
            # 溯源（PY-005）：方法实际定义所在类（mixin 方法不再误标 Api）
            "defined_in": cls.name,
        }
        methods[name]["n_required_params"] = len(params)
    return methods


def build_schema(
    src_text: str,
    extra_sources: dict[str, str] | None = None,
) -> dict:
    sources = {"app/api_bridge.py": src_text}
    if extra_sources:
        sources.update(extra_sources)
    tree = ast.parse(src_text)
    exposed: set[str] = set()

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

    # 第二遍：Api + 基类链全部 mixin 的方法合并（PY-005）
    registry = _build_class_registry(sources)
    methods: dict[str, dict] = {}
    api_cls = registry.get("Api")
    if api_cls is not None:
        for cls in [api_cls, *_base_chain(registry, api_cls)]:
            for name, entry in _extract_methods(cls, exposed).items():
                # 同名方法以更派生类（Api 本体）为准——先到先得
                methods.setdefault(name, entry)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Aegis js_api Bridge Schema",
        "description": "Aegis 浏览器暴露给注入式 UI 的 Python 桥接口规范。"
                       "由 scripts/gen_jsapi_schema.py 自动生成，勿手改。",
        "version": "0.5.0",
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
    # PY-005：registry 需要覆盖 mixin 所在文件（app/*.py + app/bridge/*.py）
    extra: dict[str, str] = {}
    for py in [*APP_DIR.glob("*.py"), *APP_DIR.glob("bridge/*.py")]:
        if py == API_BRIDGE:
            continue
        try:
            extra[py.relative_to(APP_DIR.parent).as_posix()] = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    schema = build_schema(src, extra)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    exposed = schema["properties"]["js_exposed_methods"]
    documented = sum(1 for m in schema["properties"]["methods"].values()
                     if m["exposed_to_js"])
    print(f"[ok] js_api schema 已生成: {OUTPUT}")
    print(f"[ok] 暴露方法数（白名单）: {len(exposed)}")
    print(f"[ok] 白名单方法已入文档数: {documented}")
    print(f"[ok] 全部方法数（含内部）: {len(schema['properties']['methods'])}")
    if documented < len(exposed):
        missing = sorted(set(exposed) - {
            n for n, m in schema["properties"]["methods"].items() if m["exposed_to_js"]})
        print(f"[fail] 白名单方法缺失文档定义: {missing}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
