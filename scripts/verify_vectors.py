#!/usr/bin/env python3
"""verify_vectors.py —— contracts 向量断言字段协议校验（PY-064 自 CI 内联抽出）。

单步协议：顶层 expected ∈ SINGLE_STEP_ACCEPTED；
多步流协议：expected_request/approve/consume/evaluate ∈ MULTI_STEP_ACCEPTED
（*_code 后缀字段是错误码不是决策，不校验）。
退出码：0 = 全部向量断言合法；1 = 存在非法断言。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 单步协议：顶层 expected 字段
SINGLE_STEP_ACCEPTED = {
    'allow', 'valid', 'deny', 'deny_rollback', 'deny_threshold',
    'deny_expired', 'deny_schema', 'deny_replay'
}

# 多步流协议：每步各自的 expected_* 字段（值域：allow / deny / require_confirmation）
MULTI_STEP_ACCEPTED = {'allow', 'deny', 'require_confirmation'}

# 多步流字段前缀（按协议步骤命名）
MULTI_STEP_PREFIXES = ('expected_request', 'expected_approve',
                       'expected_consume', 'expected_evaluate')

# PY-078：超长 URL 占位向量锚点——全树必须恰好含一处，且锚点向量自身必须保持短
#（占位语义）；真实超长样本由消费端 vectors.rs 物化
#（https://example.org/ + 'a'×9000）。锚点丢失会导致 Rust 差分静默跳过该用例。
# R7-TOOL-04（第七轮）：判定不再绑定文件名——改名/移动向量文件不得静默摘掉锚点。
OVERSIZE_ANCHOR = 'oversize-url-limit-test'

# R7-TOOL-04（第七轮）：契约面数量下界（实测 schemas 7 份 / vectors 15 份）。
# 目录缺失或整体清空此前是静默通过——「删掉一个目录名」即可让本门禁零判定。
# 下界不是「越多越好」，它只保证减面必须是**有意识**的动作。
MIN_FILES = {'schemas': 7, 'vectors': 15}


def check_oversize_anchor(data: dict, path: Path, failures: list[str]) -> int:
    """统计本文件内的超长 URL 物化锚点命中数（fail-closed）。

    R7-TOOL-04（第七轮）：本守卫此前按**文件名**（`url-origin-invalid.json`）
    早退——同内容改名/移动到别的向量文件即静默摘掉锚点（实测 exit 0）。
    现改为内容驱动 + 全树汇总：命中数由 main() 累加，跨文件恰好 1 次才算存在。
    """
    hits = [v for v in data.get('vectors', [])
            if OVERSIZE_ANCHOR in str(v.get('url', ''))]
    if len(hits) > 1:
        failures.append(
            f'{path.name}: 超长 URL 物化锚点 {OVERSIZE_ANCHOR!r} 在本文件出现 '
            f'{len(hits)} 次（应全树恰好 1 次）')
    for hit in hits:
        if len(hit.get('url', '')) > 256:
            failures.append(
                f'{path.name}: 锚点向量应为短占位 URL（真实样本由消费端物化），'
                f'当前长度 {len(hit["url"])}')
    return len(hits)


def validate_vector(vector: dict, path: str, failures: list[str]) -> None:
    """根据协议类型验证向量断言（单步 expected / 多步 expected_*）。

    PY-187（2026-09-26 审计）：校验逻辑此前用裸 assert 实现——`python -O`
    运行时断言全部被剥离，脚本对任意非法向量静默返回 0（fail-open，门禁
    可剥离）。现改为显式 failures.append 收集——与优化器无关，-O 下仍 fail。
    """
    if 'expected' in vector:
        if vector['expected'] not in SINGLE_STEP_ACCEPTED:
            failures.append(
                f'单步协议 expected 值非法: {path} → {vector["expected"]!r}')
        return

    multi_step_fields = [
        k for k in vector
        if k.startswith(MULTI_STEP_PREFIXES)
        and not k.endswith('_code')  # _code 字段是错误码，不是决策
    ]
    if not multi_step_fields:
        failures.append(
            f'向量缺少断言字段（既无 expected 也无 expected_*）: {path}')
        return

    for field in multi_step_fields:
        value = vector[field]
        if value not in MULTI_STEP_ACCEPTED:
            failures.append(f'多步流 {field} 值非法: {path} → {value!r}')


def main() -> int:
    failures: list[str] = []
    pattern = [ROOT / 'contracts' / 'schemas', ROOT / 'contracts' / 'vectors']
    anchor_hits = 0
    for directory in pattern:
        if not directory.is_dir():
            failures.append(f'契约目录缺失：{directory.relative_to(ROOT)}（空扫描面不放行）')
            continue
        files = sorted(directory.glob('*.json'))
        floor = MIN_FILES.get(directory.name, 1)
        if len(files) < floor:
            failures.append(
                f'契约目录 {directory.name}/ 仅 {len(files)} 个 JSON，低于下界 {floor}'
                '——契约面被缩减须显式核减本下界并说明理由')
        for path in files:
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError) as exc:
                failures.append(f'{path.name}: JSON 无效（{exc}）')
                continue
            for vector in data.get('vectors', []):
                # PY-187：显式收集（不再依赖 AssertionError 捕获——-O 下
                # assert 被剥离会导致校验整体失效）
                validate_vector(vector, str(path.relative_to(ROOT)), failures)
            try:
                anchor_hits += check_oversize_anchor(data, path, failures)
            except OSError as exc:
                failures.append(f'{path.name}: 锚点检查失败（{exc}）')
    # 全树汇总判定：锚点丢失即 vectors.rs / Kotlin / C# 三端的超长 URL 物化分支
    # 失去输入（改名、删除、移动向量文件都不得静默摘掉它）。
    if anchor_hits != 1:
        failures.append(
            f'超长 URL 物化锚点 {OVERSIZE_ANCHOR!r} 全树命中 {anchor_hits} 次'
            '（应恰好 1 次；0 次 = vectors.rs 物化分支静默失效，'
            '>1 次 = 物化目标不唯一）')
    if failures:
        print('❌ contracts 向量断言无效：')
        for failure in failures:
            print('  -', failure)
        return 1
    print('✅ contracts JSON 与向量期望有效')
    return 0


if __name__ == '__main__':
    sys.exit(main())
