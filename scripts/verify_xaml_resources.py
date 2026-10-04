"""XAML 资源键连通性守卫（回归防护）。

崩溃根源 V3：RefreshBookmarkBar() 调用 FindResource("BookmarkBarButton")，
但仓库里从未定义该资源。只要有书签，启动即抛
ResourceReferenceKeyNotFoundException——安装版打不开，而本地因无书签
循环为空侥幸通过。本脚本在发布前断言“所有 FindResource(<key>) 的键
必须在某个 XAML 资源字典存在”，从源头杜绝该类别回归。

用法：python scripts/verify_xaml_resources.py
失败：exit 1 并列出缺失键；扫描面塌缩（根目录缺失/0 资源键/0 源文件）exit 2。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "windows" / "src" / "Aegis.Windows.App"

# PY-036：只匹配 FindResource 字面量——TryFindResource 与 Resources["key"]
# 索引器引用同一批资源键，抛的异常同源（TryFindResource 返回 null 崩溃 /
# 索引器 KeyNotFound），一并纳入扫描
_CS_FIND = re.compile(r'(?:FindResource|TryFindResource)\(\s*"([^"]+)"\s*\)|Resources\s*\[\s*"([^"]+)"\s*\]')
_XAML_KEY = re.compile(r'x:Key="([^"]+)"')


def collect_keys() -> set[str]:
    keys: set[str] = set()
    for xaml in SRC.rglob("*.xaml"):
        # App.xaml 及所有 Window/Control 资源字典均在打包可见范围。
        keys.update(_XAML_KEY.findall(xaml.read_text(encoding="utf-8")))
    return keys


def main() -> int:
    # GitHub Actions Windows 控制台用非 UTF-8 代码页；强制 UTF-8 输出避免
    # UnicodeEncodeError 导致脚本非零退出（误判断言失败）。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    keys = collect_keys()
    # R7-TOOL-04（第七轮）：SRC 不存在 / 采集到 0 个 x:Key / 0 个待扫描 .cs
    # 都是「扫描面塌缩」而非「全部通过」——原实现三者一律 [OK] + exit 0，
    # 删掉一个目录名即可让本门禁零判定。空面按环境错误（2）处理。
    if not SRC.is_dir():
        print(f"[FAIL] 扫描根不存在：{SRC}（环境错误，不作通过判定）", file=sys.stderr)
        return 2
    cs_files = sorted(SRC.rglob("*.cs"))
    if not keys or not cs_files:
        print(f"[FAIL] 扫描面为空（x:Key {len(keys)} 个 / .cs {len(cs_files)} 个）"
              "——资源连通性未判定任何东西（环境错误）", file=sys.stderr)
        return 2
    missing: list[tuple[Path, str, int, str]] = []
    for cs in cs_files:
        txt = cs.read_text(encoding="utf-8")
        for m in _CS_FIND.finditer(txt):
            key = m.group(1) or m.group(2)
            if key not in keys:
                line = txt.count("\n", 0, m.start()) + 1
                # PY-213（2026-09-26 审计）：kind 此前把 TryFindResource 命中
                # 也标成 "FindResource"——排障提示失真（TryFindResource 不抛
                # 异常而是返回 null，崩溃形态不同）。改记录匹配前缀原文。
                kind = "索引器" if m.group(2) else m.group(0).split("(")[0]
                missing.append((cs, key, line, kind))
    if missing:
        print(f"[FAIL] 发现 {len(missing)} 个资源引用指向未定义的 XAML 资源键：")
        for path, key, line, kind in missing:
            # PY-117/118 配套：SRC 可被重定向（单测）——仓库外路径原样输出
            try:
                loc = path.relative_to(ROOT)
            except ValueError:
                loc = path
            print(f"   {loc}:{line}  {kind}(\"{key}\") 无匹配 x:Key")
        print("     -- 这是启动/运行期 ResourceReferenceKeyNotFoundException 的常见根源。")
        return 1
    print(f"[OK] XAML 资源连通性通过：{len(keys)} 个 x:Key 均被合理引用/定义。")
    return 0


if __name__ == "__main__":
    sys.exit(main())