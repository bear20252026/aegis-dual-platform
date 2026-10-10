"""mirror_consumers.py —— 「生成镜像有没有真实消费方」这条判据的扫描面与口径。

从 `verify_contract_compatibility.py` 拆出来只有一个原因：那条门禁已在 300 行红线边缘，
而 R9-SH-7 修它要加的口径注释恰好放不下（本仓红线是新文件 ≤300，不靠抬基线绕过）。
拆开后职责也更清楚：本文件只管**怎么扫**，判定与豁免表在对面的门禁里。

「消费」只认同语言、且不在生成物/测试/构建目录里的引用。三条边界各挡一种蒙混：

* **跨语言同名不算**——`agent/action_contract.py` 里有 `class ActionContract`，那是同一
  schema 的另一份实现，不等于 C#/Kotlin 的镜像被端侧用了。旧实现把 .py/.rs/.cs/.kt
  混在一起扫，会把零消费的豁免项读成「有消费方」（实测现树就是这样）。
* **测试与生成物引用不算**（AD-244 原口径）——`android/broker/src/test/.../
  ActionContractConversions.kt` 就是活例：镜像靠测试自我引用不能算承重。
* **构建/依赖目录不算**——这一条是 R9-SH-7 的直接成因：旧实现从仓库根 `rglob("*")`，
  连 `core/rust-policy-core/target`、`obj/`、`bin/`、`node_modules/` 一起爬（本机实测
  20,467 个文件系统条目、641 个候选源文件，单次调用 ≈5.6s 且每个未豁免镜像各调一次
  ⇒ 全表 ≈34s），代价大到那条判据在现树里**从没真正跑过**（豁免集恰等于镜像全集 ⇒
  每条都 `continue`）。判据跑得动，才是判据（收窄后整条门禁 ≈0.5s）。
"""
from __future__ import annotations

import pathlib
import re

# 各语言的端侧源码根（相对仓库根）。只扫自己那一侧，跨语言由对面的门禁另判。
CONSUMER_ROOTS = {"cs": "windows/src", "kt": "android"}
CONSUMER_SUFFIX = {"cs": ".cs", "kt": ".kt"}

# 路径任一段命中即排除：构建产物、依赖目录、生成物自身、测试源集。
NON_CONSUMER_PARTS = {
    "generated", "tests", "test", "obj", "bin", "build", "target", "node_modules",
    "dist", ".git",
}


def consumed_names(repo_root: pathlib.Path, lang: str, names: set[str]) -> set[str]:
    """一次遍历该端同语言源码，返回**被真实引用**的类型名子集。

    `names` 是镜像类型名集合（本仓只有 6 个量级），因此单遍扫完即返回；命中集齐了就提前
    退出。调用方传 `ROOT / ".."`（仓库根）而不是模块常量，便于测试用合成树做故障注入。
    """
    root = repo_root / CONSUMER_ROOTS[lang]
    if not names or not root.is_dir():
        return set()
    patterns = {name: re.compile(rf"\b{re.escape(name)}\b") for name in sorted(names)}
    found: set[str] = set()
    for path in sorted(root.rglob("*" + CONSUMER_SUFFIX[lang])):
        if {part.lower() for part in path.parts} & NON_CONSUMER_PARTS:
            continue
        if "_test" in path.name.lower() or "verify_contract_compatibility" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name, pattern in patterns.items():
            if name not in found and pattern.search(text):
                found.add(name)
        if found == names:
            break
    return found
