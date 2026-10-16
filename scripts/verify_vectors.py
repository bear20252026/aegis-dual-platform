#!/usr/bin/env python3
"""verify_vectors.py —— contracts 向量断言字段协议校验（PY-064 自 CI 内联抽出）。

单步协议：顶层 expected ∈ SINGLE_STEP_ACCEPTED；
多步流协议：expected_request/approve/consume/evaluate ∈ MULTI_STEP_ACCEPTED
（*_code 后缀字段是错误码不是决策，不校验）。
R9-B59 起还判**两份原生 C-ABI 向量的信封形状与 platform_decidable 分区**
（见 NATIVE_VECTORS——分区标签必须能由该条期望值推导，不许省略、不许塌成一块）。
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

# R7-TOOL-04（第七轮）：契约面数量下界（实测 schemas 7 份 / vectors 21 份——
# R9-B35 加 release/version/semver-form 六份）。
# 目录缺失或整体清空此前是静默通过——「删掉一个目录名」即可让本门禁零判定。
# 下界不是「越多越好」，它只保证减面必须是**有意识**的动作。
MIN_FILES = {'schemas': 7, 'vectors': 21}

# R8-PY-02（第八轮审计 2026-10-04）：MIN_FILES 只数**文件**，把任一 vectors 数组
# 清空（文件在场）即可让全部循环零次执行、门禁仍绿——「删文件」被堵住了，「改内容
# 清空」这条路还通。现同时钉全树条目总数下界与逐文件非空。
# R9-B66（2026-10-15，IPv6 解冻）：222 → 246，实测增量 url-origin-valid +8、
# url-origin-invalid +6、native-navigation-decision +10（另有 3 条 IPv6 形态从
# invalid 移进 valid，对总数净零）。
# R9-B69（2026-10-15，队列 Q64）：246 → 251，实测增量 native-navigation-decision +3
# （v4-compatible `::169.254.169.254` / `::2` / `::1.2.3.4`）、url-origin-valid +2
# （同两种形态的语法面）。
# R9-B70（2026-10-15）：251 → 298，新增 reserved-address-boundary.json 47 条（26 deny／
# 21 allow）——这张表此前在 C# 与 Kotlin 各抄一份，条数是两份的并集，由合并实测得出。
# R9-B71（2026-10-15，队列 Q66）：298 → 351，同表 +53 条（逐段左右邻 42 条 + authority
# 清洗形态 11 条），现表 100 条（48 deny／52 allow）。
# R9-B72（2026-10-16，队列 Q66 第二半）：351 → 372，同表再 +21 条（IPv6 段左右邻：
# fe80::/10、ff00::/8、fc00::/7 各两侧，内嵌 IPv4 的字节边界，以及 userinfo + IPv6 的
# authority 叠加形态），现表 121 条（57 deny／64 allow）。
# R9-B75（2026-10-16）：372 → 375，同表 +3 条大小写叠加形态（`0XA9FEA9FE` 裸/带路径/带
# userinfo）——本批要量的正是「裸 authority 不转小写会不会漏判」这条推断，现表 124 条
# （60 deny／64 allow）。
MIN_VECTOR_ENTRIES = 375

# R9-B59（§四 第 11 项 ② 与 Q21 是同一次定稿）：两份原生 C-ABI 向量的**信封 + 分区**词表。
#
# 信封此前不一致是实测的：decision 有 version/description 而没有 protocol，confirmation 只有
# protocol 且把修订号焊在字符串尾巴（`...-v3`）⇒ 同一 ABI 的两份向量没有共同的头部形状，
# 任何「按信封识别向量」的工具都得写两套解析。现在判**键集合本身**，不只是值。
#
# `platform_decidable` 的语义要写清，否则它会被读成「产品里没有这个分支」：
# false ＝「**宿主在自己的托管判定路径上产不出这一支**，所以平台执行者断言它是断不真的」——
# Windows 单测/Debug 构建 `NativePolicyCoreBuildMarker.RequiredByThisBuild=false` ⇒
# `RequestNavigationConfirmation` 直接拒 `native_confirmation_core_required`；
# Android 无 native core 时 `requestNavigationConfirmation` 顺延 `evaluateNavigation`。
# shipping Release 构建 RequiredByThisBuild=true，两端确实会走原生确认链——那是发布/装机面，
# 不是 PR 必跑面。核心这一侧三种分支都产得出，所以本文件仍然由 RS 全量执行。
# 关键设计：标签**不是自由声明**，而是由该条的期望值可推导（下面 `decidable_when`），
# 门禁逐条判这个推导式——「自由填写的分区字段」只会变成第二个会漂移的真相。
NATIVE_VECTORS: dict[str, dict] = {
    "native-navigation-decision.json": {
        "protocol": "aegis-native-navigation-decision",
        "version": 1,
        "decidable_when": lambda v: v.get("expected_evaluate") != "require_confirmation",
        # 分区必须**真的分了两块**：全 true 或全 false 都说明这个字段没在描述任何东西
        "both_partitions_required": True,
    },
    "native-navigation-confirmation.json": {
        "protocol": "aegis-native-navigation-confirmation",
        "version": 3,
        "decidable_when": lambda v: False,
        "both_partitions_required": False,
    },
}
NATIVE_ENVELOPE_KEYS = {"protocol", "version", "description", "vectors"}
# R9-B59 同批改名：`MULTI_STEP_PREFIXES` 已经规定了「按协议步骤命名」，错误码字段就该是
# `expected_<step>_code`；decision 那份此前叫 `expected_deny_code`（deny 是**值**不是步骤）。
LEGACY_CODE_FIELDS = {"expected_deny_code": "expected_evaluate_code"}


def check_native_vector(data: dict, path: Path, failures: list[str]) -> None:
    """原生向量：信封形状 + 逐条 platform_decidable 的可推导性（不在表里的文件零判定）。"""
    spec = NATIVE_VECTORS.get(path.name)
    if spec is None:
        return
    keys = set(data)
    if keys != NATIVE_ENVELOPE_KEYS:
        failures.append(
            f"{path.name}: 原生向量信封键集合应为 {sorted(NATIVE_ENVELOPE_KEYS)}，"
            f"实得 {sorted(keys)}——信封是这次定稿的对象，加/删/改名都要同批改本表")
    for field in ("protocol", "version"):
        if data.get(field) != spec[field]:
            failures.append(
                f"{path.name}: {field}={data.get(field)!r} 与登记表 {spec[field]!r} 不一致"
                "——改信封值就是改冻结词表，须写清理由并同批改 NATIVE_VECTORS")
    if not str(data.get("description", "")).strip():
        failures.append(f"{path.name}: description 为空——信封统一的意义就在「读头部就知道这是哪族哪版」")

    entries = data.get("vectors", [])
    decidable_true = 0
    for vector in entries:
        name = vector.get("name", "?")
        for legacy, current in LEGACY_CODE_FIELDS.items():
            if legacy in vector:
                failures.append(
                    f"{path.name}/{name}: 仍用旧字段 {legacy!r}——"
                    f"词表已定稿为 expected_<步骤>_code，此处应为 {current!r}")
        if "platform_decidable" not in vector:
            failures.append(
                f"{path.name}/{name}: 缺 platform_decidable——省略不得被读成「默认可判定」")
            continue
        value = vector["platform_decidable"]
        if not isinstance(value, bool):
            failures.append(
                f"{path.name}/{name}: platform_decidable 必须是布尔，实得 {type(value).__name__}")
            continue
        expected = bool(spec["decidable_when"](vector))
        if value is not expected:
            failures.append(
                f"{path.name}/{name}: platform_decidable={value}，但按该条期望值推导应为 {expected}"
                "——分区标签必须可推导，否则它就是第二个会各自漂移的真相")
        if value:
            decidable_true += 1
    if spec["both_partitions_required"] and (decidable_true == 0 or decidable_true == len(entries)):
        failures.append(
            f"{path.name}: platform_decidable 全部{'为 true' if decidable_true else '为 false'}"
            f"（{len(entries)} 条）——分区塌成一块就说明标签已不再描述任何事实")


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
    vector_entries = 0
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
            entries = data.get('vectors', [])
            if directory.name == 'vectors':
                vector_entries += len(entries)
                if not entries:
                    failures.append(
                        f'{path.name}: vectors 数组为空——文件在场而零判定'
                        '（R8-PY-02：清空内容即可摘掉门禁）')
            for vector in entries:
                # PY-187：显式收集（不再依赖 AssertionError 捕获——-O 下
                # assert 被剥离会导致校验整体失效）
                validate_vector(vector, str(path.relative_to(ROOT)), failures)
            check_native_vector(data, path, failures)
            try:
                anchor_hits += check_oversize_anchor(data, path, failures)
            except OSError as exc:
                failures.append(f'{path.name}: 锚点检查失败（{exc}）')
    # 全树汇总判定：锚点丢失即 vectors.rs / Kotlin / C# 三端的超长 URL 物化分支
    # 失去输入（改名、删除、移动向量文件都不得静默摘掉它）。
    if vector_entries < MIN_VECTOR_ENTRIES:
        failures.append(
            f'契约向量总条目 {vector_entries} 条，低于下界 {MIN_VECTOR_ENTRIES}'
            '——清空或摘除条目须显式核减本下界并说明理由')
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
