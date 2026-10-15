# catalog_governance_columns_test.py —— R9-B46（第九轮 Q15 / R9-SH-5）的用例。
#
# 单独成文件而不是塞进 codegen_and_catalog_test.py：后者已在行数红线基线里
# （只许减不许增），而这条纪律需要的是「夹具在全规则下干净 + 反向钉住运行时不读治理列」
# 两组可失败判据，本身就该有自己的名字与出处。
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "contracts" / "codegen"))

import analyze_action_catalog as aac

# action-catalog 的列分两种身份：判定面（broker 运行时读）与治理元数据（没人读，
# 但必须自证一致）。本节把「哪种列被谁读」变成可失败判据——包括反向钉住
# 「broker 不读治理列」，这样将来真要把它接进裁决链时会先撞红，而不是悄悄改一行。
CATALOG_PATH = Path(__file__).resolve().parents[2] / "contracts" / "policy" / "action-catalog.yaml"
BROKER_PATH = Path(__file__).resolve().parents[2] / "agent" / "broker.py"
GOVERNANCE_COLUMNS = ("risk", "confirmation", "audit", "read_only")
JUDGMENT_COLUMNS = ("scope", "budget", "policy_version", "default_deny")

# R9-B66：catalog 头注第 8-22 行写的是「哪一列由谁判」。这类指针此前只是散文——
# 实测它已经指错过一次（反向锚写在 catalog_governance_columns_test.py，头注却说
# 是 codegen_and_catalog_test.py），而指错的文档比没有文档更贵：读的人会去那份文件里找判据。
# 所以把「列 → 判它的文件」登记成表，让头注与表**互为对照**：表里的路径必须实存、
# 必须真的在那份文件里查得到该列名；头注必须逐字写出表里的每一条路径。
COLUMN_JUDGES: dict[str, tuple[str, ...]] = {
    "risk": ("contracts/codegen/analyze_action_catalog.py",),
    "audit": ("contracts/codegen/analyze_action_catalog.py",),
    "redteam_fixtures": ("contracts/codegen/analyze_action_catalog.py",
                         "agent/tests/redteam_test.py"),
    "confirmation": ("contracts/codegen/analyze_action_catalog.py",),
    "read_only": ("contracts/codegen/verify_agent_catalog.py",
                  "agent/tests/redteam_test.py"),
}
# 「运行时不读治理列」这条纪律的锚点文件本身（含正反两条用例）
NO_READ_ANCHOR_FILE = "tests/python/catalog_governance_columns_test.py"


def catalog_header() -> str:
    """action-catalog 的前导注释块，折行归一成一条空白。"""
    lines = [
        line.lstrip("#").strip()
        for line in CATALOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#")
    ]
    return " ".join(" ".join(lines).split())


def code_of(rel: str) -> str:
    from text_anchors import strip_comments
    return strip_comments((ROOT / rel).read_text(encoding="utf-8"), rel)


def check_pointer_agreement(header: str, registry: dict[str, tuple[str, ...]],
                            anchor: str) -> list[str]:
    """纯函数：注册表 ⇄ 头注 ⇄ 判据文件三者对账（注入用例直接喂假数据给它）。"""
    problems: list[str] = []
    for column, judges in sorted(registry.items()):
        for rel in judges:
            target = ROOT / rel
            if not target.is_file():
                problems.append(f"{column}：登记的判据文件不存在——{rel}")
                continue
            if column not in code_of(rel):
                problems.append(
                    f"{column}：{rel} 的代码面（剔注释后）里查不到这个列名——"
                    "要么登记表错了，要么那份判据把它摘掉了")
            if rel not in header:
                problems.append(
                    f"{column}：头注没有写出 {rel}——文档与注册表开始各说各话")
    if anchor not in header:
        problems.append(f"头注没有写出反向锚文件 {anchor}")
    anchor_code = code_of(anchor)
    for token in ("GOVERNANCE_COLUMNS", "BROKER_PATH", "JUDGMENT_COLUMNS"):
        if token not in anchor_code:
            problems.append(f"锚点文件 {anchor} 的代码面里没有 {token}——那条指针是空的")
    # 指针一律写全路径：`analyze_action_catalog.py` 这种裸名在本仓有两个同名文件
    #（contracts/codegen/ 下与 scripts/ 下的历史同名物），读到的人无法确定指哪一个。
    for bare in sorted({t for t in re.findall(r"(?<![\w./-])([\w-]+\.(?:py|yaml|json))", header)
                        if "/" not in t}):
        problems.append(f"头注里的指针要写全路径（裸名：{bare}）")
    return problems



class TestCatalogGovernanceColumns:
    def test_real_catalog_is_clean(self):
        assert aac.analyze(CATALOG_PATH.read_text(encoding="utf-8")) == []

    def test_missing_confirmation_is_red(self):
        src = CATALOG_PATH.read_text(encoding="utf-8").replace(
            "    confirmation: none" + chr(10), "", 1)
        assert any("confirmation" in e for e in aac.analyze(src)), src

    def test_confirmation_outside_vocabulary_is_red(self):
        src = CATALOG_PATH.read_text(encoding="utf-8").replace(
            "confirmation: none", "confirmation: ask-me", 1)
        assert any("不在词表" in e for e in aac.analyze(src))

    def test_write_action_without_confirmation_is_red(self):
        # read_only 改成 false 而 confirmation 留 none ⇒ 矛盾（这才是「列不是装饰」的实质判据）
        src = CATALOG_PATH.read_text(encoding="utf-8").replace(
            "    read_only: true", "    read_only: false", 1)
        assert any("矛盾" in e for e in aac.analyze(src))

    def test_write_action_requiring_confirmation_is_accepted(self):
        # 正面控制：非只读 + required 必须**不**报错——否则上面三条是恒真断言。
        src = (CATALOG_PATH.read_text(encoding="utf-8")
               .replace("    read_only: true", "    read_only: false", 1)
               .replace("    confirmation: none", "    confirmation: required", 1))
        assert not any("confirmation" in e for e in aac.analyze(src)), src

    def test_broker_never_reads_the_governance_columns(self):
        from text_anchors import strip_comments
        code = strip_comments(BROKER_PATH.read_text(encoding="utf-8"), "agent/broker.py")
        for column in GOVERNANCE_COLUMNS:
            assert column not in code, (
                f"broker 开始读治理列 {column}——那是裁决语义变更，要另批带契约向量")

    def test_broker_really_reads_the_judgment_columns(self):
        # 上一条的正面控制：判定面四列必须确实在 broker 代码里出现，否则反向锚在判空气。
        from text_anchors import strip_comments
        code = strip_comments(BROKER_PATH.read_text(encoding="utf-8"), "agent/broker.py")
        for column in JUDGMENT_COLUMNS:
            assert column in code, f"判定面列 {column} 在 broker 里消失——读取口径要重登记"


class TestWhoJudgesWhichColumn:
    """「列 → 判它的文件 → 写这件事的文档」三者必须互相指得回来（R9-B66）。"""

    def test_real_tree_agrees(self):
        problems = check_pointer_agreement(catalog_header(), COLUMN_JUDGES, NO_READ_ANCHOR_FILE)
        assert not problems, "；".join(problems)

    def test_the_pointer_that_was_actually_wrong_is_now_red(self):
        """这条用的是**历史上真写过的那个错值**，不是我编的形状。

        R9-B66 现读：头注原本说反向锚在 `codegen_and_catalog_test.py`，而它在隔壁文件里。
        当时没有任何判据会发现这件事——文档指向单源，可没人验证那根指针。
        """
        header = catalog_header().replace(
            NO_READ_ANCHOR_FILE, "tests/python/codegen_and_catalog_test.py")
        problems = check_pointer_agreement(header, COLUMN_JUDGES, NO_READ_ANCHOR_FILE)
        assert any("反向锚" in p for p in problems), problems

    def test_registry_entry_pointing_at_a_file_that_does_not_judge_the_column_is_red(self):
        problems = check_pointer_agreement(
            catalog_header(), {"confirmation": ("contracts/codegen/verify_agent_catalog.py",)},
            NO_READ_ANCHOR_FILE)
        assert any("查不到这个列名" in p for p in problems), problems

    def test_registry_entry_pointing_at_a_missing_file_is_red(self):
        problems = check_pointer_agreement(
            catalog_header(), {"risk": ("contracts/codegen/no_longer_here.py",)},
            NO_READ_ANCHOR_FILE)
        assert any("不存在" in p for p in problems), problems

    def test_positive_control_a_consistent_pair_still_passes(self):
        """正面控制：一致的（列、文件、头注）三元组必须**不**红——否则上面三条只是恒真。"""
        header = f"{COLUMN_JUDGES['risk'][0]} {NO_READ_ANCHOR_FILE}"
        assert check_pointer_agreement(
            header, {"risk": COLUMN_JUDGES["risk"]}, NO_READ_ANCHOR_FILE) == []

    def test_bare_filename_pointer_is_red(self):
        """指针写成裸名（不带目录）必须红——本仓有过同名文件，读者无法确定指哪一个。"""
        problems = check_pointer_agreement(
            "confirmation 由 analyze_action_catalog.py 判",
            {}, NO_READ_ANCHOR_FILE)
        assert any("裸名" in x for x in problems), problems

    def test_registry_covers_every_governance_column_named_in_the_header(self):
        """注册表不能悄悄漏列：GOVERNANCE_COLUMNS 四条都在表里（redteam_fixtures 是第五条）。"""
        assert set(GOVERNANCE_COLUMNS) <= set(COLUMN_JUDGES), (
            "有条治理列没登记由谁判——它下一步就会变成「没人读也没人判」的装饰字段")

