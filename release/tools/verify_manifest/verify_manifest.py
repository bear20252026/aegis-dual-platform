#!/usr/bin/env python3
"""verify_manifest.py —— 阶段 E（蓝图 release/tools/verify_manifest）：
更新清单验证——复用 release/update_verifier.py（P0-04 已统一：SemVer 字符串/
signatures[]/重复 key_id 只计一次/异常封装 UpdateRejected——TUF 阈值签名对齐）。

发布链独立验证（蓝图阶段 E）：manifest 必须通过签名/回滚/过期/阈值验证——
任何失败返回非零（终止发布——fail-closed——不允许跳过或截断验证）。
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# 复用 P0-04 更新验证器（契约统一——contracts/schemas/update-manifest.schema.json）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from release.update_verifier import UpdateRejected, verify_manifest


def _load_threshold(policy_path: Path | None = None) -> int:
    """签名阈值单源：release/manifests/signing-policy.yaml（SP-006 整改）。

    此前脚本硬编码 threshold=2，策略 yaml 可漂移而不被发现。现强制读
    策略文件——文件缺失/解析失败/threshold 非法一律 exit 2（fail-closed，
    不回退到任何默认值）。

    PY-214/SP-175（2026-09-26 审计）：阈值此前以 MULTILINE+DOTALL 手写正则
    抽取——``.*?`` 可跨块误绑（如 rollback 段或后续新增块中先出现的
    threshold 键会被错误采信）。CI 已锁 pyyaml 依赖，改 yaml.safe_load
    结构化读取 policy.threshold（保留 fail-closed 退出码语义）。
    policy_path 参数仅供单测注入合成策略文件。
    """
    import yaml

    if policy_path is None:
        policy_path = (Path(__file__).resolve().parents[2]
                       / "manifests" / "signing-policy.yaml")
    if not policy_path.is_file():
        print(f"❌ 签名策略缺失: {policy_path}（终止发布——fail-closed）")
        raise SystemExit(2)
    # 结构化读取：policy 块下的 threshold 标量——非整数/缺失/越界一律拒绝
    try:
        doc = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"❌ 签名策略 YAML 解析失败: {policy_path.name}（{exc}）"
              "（终止发布——fail-closed）")
        raise SystemExit(2) from exc
    policy = doc.get("policy") if isinstance(doc, dict) else None
    threshold = policy.get("threshold") if isinstance(policy, dict) else None
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        print("❌ 签名策略 threshold 缺失或非法（终止发布——fail-closed）")
        raise SystemExit(2)
    return threshold


def main() -> int:
    if len(sys.argv) < 4:
        print("用法: verify_manifest.py <manifest.json> <trusted_keys.json> <min_version>")
        return 2
    # SP-024（审计 2026-09-23 清单·SP1 批）：manifest/trusted_keys 坏 JSON 直接
    # traceback 替代干净报告——包 try/except：exit 2 + 文件名上下文（与
    # SP-155 verify_artifact_set/generate_sbom 同一退出码语义——环境错误一律
    # exit 2，验证结论失败才是 exit 1）。
    try:
        manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        trusted = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        src = getattr(exc, "filename", None) or Path(sys.argv[1]).name
        print(f"❌ 输入文件读取/解析失败: {src}（{exc}）（终止发布——fail-closed）")
        return 2
    try:
        verify_manifest(manifest, trusted, sys.argv[3], datetime.now(UTC),
                        threshold=_load_threshold())
    except UpdateRejected as exc:
        print(f"❌ 更新清单验证失败: {exc}（终止发布——fail-closed）")
        return 1
    print("✅ 更新清单验证通过（签名阈值/防回滚/过期——P0-04 契约统一）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
