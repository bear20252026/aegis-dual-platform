#!/usr/bin/env python3
"""verify_doc_floors.py —— README 抄的「机器判定的下界」必须逐字等于实树常量（R9-B82）。

形状与本仓反复栽的那族一样，但落点不同：**文档把门禁的数值抄了一遍，而没人对账**。
README 的「测试规模」段自己写着「这里不抄具体用例数」（R9-DOC-15），却紧接着抄了四个**下界**：
`assert_test_counts.py（Core ≥700 / Broker ≥160）` 与 `verify_vectors.py（向量 ≥21 份 / 条目 ≥222）`。
R9-B82 现读实测：条目下界早已是 **375**（第九轮逐批追加上调），份数下界是 **22** 且它的单源
根本不在 `verify_vectors.py`，而在 `scripts/verify_vector_consumers.py:46`——三个数字过期、一处归属写错，
`check_doc_claims.py` 全绿（它的正则 `COUNT_CLAIM` 只认「N 个 workflow」，见
`scripts/check_doc_claims.py:43`）。

判据四条，每条都在 `tests/python/doc_floors_test.py` 里以内存注入证伪：
1. **逐归属脚本双向对账**：README 挂在某个脚本名下的 `≥N` 集合，必须**恰好等于**实树归该脚本的
   下界集合——少了是数字过期，多了是抄了一个还没接线的下界，挂错脚本也是这一条；
2. 反向也判：脚本名下有数字而实树没有任何下界归它 ⇒ 判红（历史事故正是份数被挂在
   `verify_vectors.py` 名下，而它的单源是 `verify_vector_consumers.py`）；
3. dotnet 发现数下界取自 workflow 调用点（只认 `uses: …/dotnet-test-suite` 的 `with:`），同一 label
   在多个 workflow 里给出不同值 ⇒ 判红（R9-B61 同族：两份会在不同批次各自漂移）；
4. 判定面塌缩按环境错误退出，不判「通过」：README 找不到那条 bullet、实树一个下界都没解析到、
   或调用点缺 `label`/`minimum`。

本门禁自己先栽过一次假绿：第一版按「`label:` 之后第一个 `minimum:`」配对，猜出 `Core=160`
这种伪下界，而 160 恰好在 README 抄写的集合里 ⇒ 单向判据全绿。改成结构化取数 + 双向对账
之后，同一条 bullet 才真的被判到。这条按 R9-CI-20 的口径记在这儿，防下一版再把「绿」当结论。

范围只判 README 的这一条 bullet 是有意的：`CLAUDE.md` 与 CHANGELOG 里的数字是**当批口径**
（README 第 170 行自己声明过），把它们算进判定面就是拿判据去判不存在的形状。

退出码：0=一致 / 1=过期、错归属、多抄、调用点漂移 / 2=环境错误或判定面塌缩。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CLAIM_ANCHOR = "机器判定的只有下界"
GREATER = re.compile(r"≥\s*(\d+)")
PATH_MENTION = re.compile(r"`((?:scripts|\.github)/[A-Za-z0-9_.\-/]+)`")


def python_const(rel_path: str, name: str) -> int:
    """从脚本正文里取 `NAME = 数字`——注释行先剔（口径同 `text_anchors.py`），
    否则「MIN_VECTOR_ENTRIES 此前是 222」这种带日期的追记行会被当成现值。"""
    text = (ROOT / rel_path).read_text(encoding="utf-8", errors="ignore")
    body = re.sub(r"(?m)^\s*#.*$", "", text)
    found = re.search(rf"^{name}\s*=\s*(\d+)\b", body, re.M)
    if not found:
        raise ValueError(f"{rel_path} 里找不到常量 {name}")
    return int(found.group(1))


def dotnet_floors() -> dict[str, set[int]]:
    """label → 该 label 在所有 workflow 里出现过的 minimum 值集合（多值＝调用点漂了）。

    **按 YAML 结构取，不按邻行猜**：本文件第一版用「`label:` 之后第一个 `minimum:`」配对，
    实测把同一 job 里相邻的两个调用点交叉配成了 `Core=160`、还凭空多出
    `Core-native` / `Broker-release` 这类标签——而 160/700 恰好都在 README 抄写的集合里，
    于是门禁**空转判绿**。只认 `uses: ./.github/actions/dotnet-test-suite` 那个 composite action
    的 `with:` 里的 label/minimum 一对，别的 `label:` 键（runner 标签等）一律不进判定面。
    """
    out: dict[str, set[int]] = {}
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        try:
            doc = yaml.safe_load(workflow.read_text(encoding="utf-8", errors="ignore"))
        except yaml.YAMLError as exc:
            raise ValueError(f"{workflow.name} 解析失败：{exc}") from exc
        for job in (doc or {}).get("jobs", {}).values():
            for step in (job or {}).get("steps", []) or []:
                uses = str(step.get("uses", ""))
                if "dotnet-test-suite" not in uses:
                    continue
                with_block = step.get("with") or {}
                label, minimum = with_block.get("label"), with_block.get("minimum")
                if label is None or minimum is None:
                    raise ValueError(f"{workflow.name} 里有个 dotnet-test-suite 调用点缺 label/minimum")
                out.setdefault(str(label), set()).add(int(minimum))
    return out


def real_floors() -> list[tuple[str, str, int]]:
    """(名称, 归属脚本, 值)——归属脚本就是 README 必须挂的名字。"""
    floors = [
        ("契约向量份数", "scripts/verify_vector_consumers.py",
         python_const("scripts/verify_vector_consumers.py", "MIN_VECTORS")),
        ("向量条目总数", "scripts/verify_vectors.py",
         python_const("scripts/verify_vectors.py", "MIN_VECTOR_ENTRIES")),
    ]
    for label, values in sorted(dotnet_floors().items()):
        if len(values) > 1:
            floors.append((f"dotnet {label} 发现数（调用点漂了：{sorted(values)}）",
                           "scripts/assert_test_counts.py", -1))
            continue
        floors.append((f"dotnet {label} 发现数", "scripts/assert_test_counts.py",
                       next(iter(values))))
    return floors


def claimed(text: str) -> dict[str, set[int]]:
    """README 那条 bullet → 归属脚本 → 抄写数字集合。"""
    start = text.find(CLAIM_ANCHOR)
    if start < 0:
        return {}
    end_match = re.search(r"\n- ", text[start:])
    bullet = re.sub(r"\s+", " ", text[start: start + end_match.start()] if end_match else text[start:])
    out: dict[str, set[int]] = {}
    mentions = list(PATH_MENTION.finditer(bullet))
    for index, match in enumerate(mentions):
        stop = mentions[index + 1].start() if index + 1 < len(mentions) else len(bullet)
        numbers = {int(n) for n in GREATER.findall(bullet[match.end():stop])}
        out.setdefault(match.group(1), set()).update(numbers)
    return out


def violations(text: str, floors: list[tuple[str, str, int]]) -> list[str]:
    problems: list[str] = []
    claims = claimed(text)
    if not claims:
        return [f"README 里找不到「{CLAIM_ANCHOR}」那条 bullet——本判据的语料面已漂移"]
    for name, owner, value in floors:
        if value < 0:
            problems.append(f"{name}——同一 label 的下界在多个 workflow 里不一致")
    by_owner: dict[str, set[int]] = {}
    for _, owner, value in floors:
        if value > 0:
            by_owner.setdefault(owner, set()).add(value)
    # 逐归属脚本**双向**对账：少了是过期，多了是抄了个实树没有的下界。
    # 只判「实树的值有没有被抄进去」是单向的，本文件第一版就因此空转判绿（见 dotnet_floors）：
    # 猜出来的伪下界 Core=160 恰好也在 README 的集合里，一条都不缺。
    for owner, expected in sorted(by_owner.items()):
        got = claims.get(owner, set())
        if got != expected:
            problems.append(
                f"`{owner}` 名下：实树下界是 {sorted(expected)}，README 抄的是 {sorted(got) or '一个数都没有'}"
                f"（少 {sorted(expected - got)}／多 {sorted(got - expected)}）——"
                "数字过期、归属写错、或多抄一个还没接线的下界，都是这一条")
    unknown = set(claims) - set(by_owner)
    for owner in sorted(unknown):
        if claims[owner]:
            problems.append(
                f"README 把下界 {sorted(claims[owner])} 挂在 `{owner}` 名下，而实树没有任何下界归它——"
                "要么改归属，要么去脚本里把下界接出来")
    return problems


def run() -> int:
    if not README.is_file():
        print(f"[环境错误] 找不到 {README}", file=sys.stderr)
        return 2
    try:
        floors = real_floors()
    except (OSError, ValueError) as exc:
        print(f"[环境错误] 实树下界取不到：{exc}", file=sys.stderr)
        return 2
    if not floors:
        print("[环境错误] 一个下界都没解析到——判定面塌了，不作通过判定", file=sys.stderr)
        return 2
    problems = violations(README.read_text(encoding="utf-8", errors="ignore"), floors)
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条（口径见本文件 docstring）")
        return 1
    detail = "、".join(f"{name}={value}" for name, _, value in floors)
    print(f"[ok] README 的下界与实树常量逐条对账通过（{len(floors)} 条：{detail}）")
    return 0


if __name__ == "__main__":
    sys.exit(run())
