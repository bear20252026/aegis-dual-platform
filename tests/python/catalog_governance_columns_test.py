# catalog_governance_columns_test.py —— R9-B46（第九轮 Q15 / R9-SH-5）的用例。
#
# 单独成文件而不是塞进 codegen_and_catalog_test.py：后者已在行数红线基线里
# （只许减不许增），而这条纪律需要的是「夹具在全规则下干净 + 反向钉住运行时不读治理列」
# 两组可失败判据，本身就该有自己的名字与出处。
from __future__ import annotations

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
