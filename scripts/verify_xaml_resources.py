"""XAML 资源键连通性守卫（回归防护）。

崩溃根源 V3：RefreshBookmarkBar() 调用 FindResource("BookmarkBarButton")，
但仓库里从未定义该资源。只要有书签，启动即抛
ResourceReferenceKeyNotFoundException——安装版打不开，而本地因无书签
循环为空侥幸通过。本脚本在发布前断言“所有 FindResource(<key>) 的键
必须在某个 XAML 资源字典存在”，从源头杜绝该类别回归。

用法：python scripts/verify_xaml_resources.py
失败：exit 1 并列出缺失键。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "windows" / "src" / "Aegis.Windows.App"

_CS_FIND = re.compile(r'FindResource\(\s*"([^"]+)"\s*\)')
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
    missing: list[tuple[Path, str, int]] = []
    for cs in SRC.rglob("*.cs"):
        txt = cs.read_text(encoding="utf-8")
        for m in _CS_FIND.finditer(txt):
            key = m.group(1)
            if key not in keys:
                line = txt.count("\n", 0, m.start()) + 1
                missing.append((cs, key, line))
    if missing:
        print(f"[FAIL] 发现 {len(missing)} 个 FindResource 引用了未定义的 XAML 资源键：")
        for path, key, line in missing:
            print(f"   {path.relative_to(ROOT)}:{line}  FindResource(\"{key}\") 无匹配 x:Key")
        print("     -- 这是启动/运行期 ResourceReferenceKeyNotFoundException 的常见根源。")
        return 1
    print(f"[OK] XAML 资源连通性通过：{len(keys)} 个 x:Key 均被合理引用/定义。")
    return 0


if __name__ == "__main__":
    sys.exit(main())