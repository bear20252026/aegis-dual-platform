"""Gradle 校验和文档**本体**的判据（第九轮 R9-B50 / 台账 Q55 的另一半）。

配置面（属性档位、命令行不得放宽、文档口径）判在 `gradle_verification_test.py`，
重算面（两条生成命令、两条平台的腿、写回守卫）判在 `gradle_relock_surface_test.py`；
这里只判 `android/gradle/verification-metadata.xml` 这份文档自己：它是「字节已验」这句话
的唯一证据，而它有四种会被悄悄做坏的形状——

- `<verify-metadata>` 改成 false：文档还在、还在被重算，但**不比字节**了；
- `<verify-signatures>` 改成 true：仓里没有受信 PGP 密钥，打开它只会把解析失败
  伪装成供应链事件（本批的如实口径是 sha256，不是签名信任）；
- 摘要被截断或换成别的算法名：登记的字节与实际比对的字节不是同一件事；
- 组件/artifact 被摘空：等于把那个坐标放进豁免——文档里没有它，strict 也不会判它。

四条都用**内存态注入**证伪（不改工作树），且注入与原形态走同一个 `document_problems`
判据——否则「注入会红」这句话本身就没有被验过（R9-SH-7 的双向不变量）。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
METADATA = ROOT / "android" / "gradle" / "verification-metadata.xml"

NS = "{https://schema.gradle.org/dependency-verification}"
SHA256 = f"{NS}sha256"
# 下限抓的是「整份文档被清空/整体重写只剩几行」，不是覆盖面——覆盖面由 strict 每次解析判，
# 所以这里宁可比实树小一截（现值见本批台账），也不把它做成「每次加依赖都要改的数」。
MIN_COMPONENTS = 400


def document_problems(text: str) -> list[str]:
    """校验和文档 → 问题清单（空＝通过）。原形态与注入形态共用这一个判据。"""
    try:
        # 信任边界：解析的是**本仓入库的那份** Gradle 生成文档，不是外来上传物；stdlib expat
        # 不解析外部实体，畸形输入走 ParseError ⇒ 这里返回问题而不是静默放行。
        # bandit.yaml 的 PY-270 / R9-CI-9 注记定了口径：行级 # nosec，不把 B314 加回全局 skips。
        root = ET.fromstring(text)  # nosec B314
    except ET.ParseError as exc:
        return [f"文档不可解析：{exc}"]
    if root.tag != f"{NS}verification-metadata":
        return [f"根元素不是 dependency-verification 命名空间下的文档：{root.tag}"]
    configuration = root.find(f"{NS}configuration")
    if configuration is None:
        return ["缺 <configuration>——verify-metadata/verify-signatures 没地方声明"]
    problems: list[str] = []
    for name, expected in (("verify-metadata", True), ("verify-signatures", False)):
        element = configuration.find(f"{NS}{name}")
        actual = (element.text or "").strip() if element is not None else None
        if actual != str(expected).lower():
            problems.append(f"<{name}> 实为 {actual!r}，应为 {str(expected).lower()!r}")
    components = root.findall(f"{NS}components/{NS}component")
    if len(components) < MIN_COMPONENTS:
        problems.append(f"组件只剩 {len(components)} 个（下限 {MIN_COMPONENTS}）——多半被整体重写或清空")
    for component in components:
        label = f"{component.get('group')}:{component.get('name')}:{component.get('version')}"
        artifacts = list(component)
        if not artifacts:
            problems.append(f"组件 {label} 一个 artifact 都没有——等于把它放进豁免")
        for artifact in artifacts:
            digests = list(artifact)
            if not digests:
                problems.append(f"artifact {artifact.get('name')}（{label}）没有任何摘要")
            for digest in digests:
                value = digest.attrib.get("value", "")
                if digest.tag != SHA256:
                    problems.append(f"artifact {artifact.get('name')} 的摘要是 {digest.tag}，文档口径写的是 sha256")
                elif not re.fullmatch(r"[0-9a-f]{64}", value):
                    problems.append(f"sha256 不是 64 位小写十六进制：{value!r}（{artifact.get('name')}）")
    return problems


def _mutate(original: str, pattern: str, replacement: str) -> str:
    mutated = re.sub(pattern, replacement, original, count=1)
    assert mutated != original, f"注入没落到文本上（{pattern}）——用例判的是空气"
    return mutated


def test_current_document_has_no_problems() -> None:
    assert document_problems(METADATA.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("pattern", "replacement"),
    [
        (r"<verify-metadata>true</verify-metadata>", "<verify-metadata>false</verify-metadata>"),
        (r"<verify-signatures>false</verify-signatures>", "<verify-signatures>true</verify-signatures>"),
        # 截断两位：写成 `{60}{2}` 的注入只能命中 62 位的值，等于什么都没注入（实测踩过）
        (r'value="([0-9a-f]{62})[0-9a-f]{2}"', r'value="\1"'),
        (r'value="[0-9a-f]{64}"', 'value="' + "Z" * 64 + '"'),
        (r'<sha256 value="([0-9a-f]{64})" ', '<unknown value="\\1" '),
        # 空组件＝把那个坐标放进豁免
        (r"<components>", '<components><component group="x" name="y" version="1"/></components>'),
        (r'(<artifact name="[^"]+">)\s*<sha256[^>]*/>\s*</artifact>', r"\1</artifact>"),
        # 整块 `<configuration>` 没了＝两个开关都没地方声明。这不是臆想的分支：Gradle 实测
        # **拒绝读**结构不合法的文档（把 `<trust>` 放错层级即报 "Unable to read dependency
        # verification metadata / `<trust>` must be found under the `<trusted-artifacts>` tag"，
        # 2026-10-14），所以「文件还在但声明块被删/改坏」正是人手改坏后的真实形状之一。
        (r"(?s)<configuration>.*?</configuration>", ""),
    ],
)
def test_every_injected_document_defect_is_reported(pattern: str, replacement: str) -> None:
    original = METADATA.read_text(encoding="utf-8")
    assert document_problems(_mutate(original, pattern, replacement)) != []


def test_a_foreign_document_or_truncated_tag_is_reported() -> None:
    """两份都不是校验和文档的东西也必须红：命名空间错了的「同名文档」，和被截断的文本。"""
    assert document_problems('<verification-metadata xmlns="urn:example"><configuration/></verification-metadata>') != []
    assert document_problems("<verification-metadata") != []
