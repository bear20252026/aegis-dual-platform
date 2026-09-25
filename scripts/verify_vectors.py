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


def validate_vector(vector: dict, path: str) -> None:
    """根据协议类型验证向量断言（单步 expected / 多步 expected_*）。"""
    if 'expected' in vector:
        assert vector['expected'] in SINGLE_STEP_ACCEPTED, \
            f'单步协议 expected 值非法: {path} → {vector["expected"]!r}'
        return

    multi_step_fields = [
        k for k in vector
        if k.startswith(MULTI_STEP_PREFIXES)
        and not k.endswith('_code')  # _code 字段是错误码，不是决策
    ]
    assert multi_step_fields, \
        f'向量缺少断言字段（既无 expected 也无 expected_*）: {path}'

    for field in multi_step_fields:
        value = vector[field]
        assert value in MULTI_STEP_ACCEPTED, \
            f'多步流 {field} 值非法: {path} → {value!r}'


def main() -> int:
    failures: list[str] = []
    pattern = [ROOT / 'contracts' / 'schemas', ROOT / 'contracts' / 'vectors']
    for directory in pattern:
        for path in sorted(directory.glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError) as exc:
                failures.append(f'{path.name}: JSON 无效（{exc}）')
                continue
            for vector in data.get('vectors', []):
                try:
                    validate_vector(vector, str(path.relative_to(ROOT)))
                except AssertionError as exc:
                    failures.append(str(exc))
    if failures:
        print('❌ contracts 向量断言无效：')
        for failure in failures:
            print('  -', failure)
        return 1
    print('✅ contracts JSON 与向量期望有效')
    return 0


if __name__ == '__main__':
    sys.exit(main())
