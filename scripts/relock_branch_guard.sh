#!/usr/bin/env bash
# relock_branch_guard.sh —— Dependency-Retlock 的**写回目标**守卫（单源，R9-B58 / 台账 Q60）。
#
# 为什么要有这个脚本：这个 job 持 `contents: write`，它能造成的唯一越界就是「推到哪」。
# 原来这条边界是内联在三个 job 的两处步骤里的（`case "$target" in deps/*)`），
# 而 Q60 需要第二种目标——Dependabot 的 Gradle bump PR 分支名是 `dependabot/…`，
# 不在 `deps/*` 面内 ⇒ 新依赖的校验和没有自动补录路径，bump PR 只能红着等人手工补字节。
# 把前缀改成「按 kind 选」如果内联抄六遍，就是六份可以各自漂移的真相；
# 所以规则收在这里，调用点只传参。判定是**封闭**的：kind 只认 deps / dependabot，
# 分支必须匹配该 kind 的前缀，其它一律 exit 2 ——包括 master、main、`deps`（无斜杠）、
# 以及 `refs/heads/deps/x` 这种「完整 ref 形态」的伪装。
#
# 用法：relock_branch_guard.sh <face> <kind> <branch>
#   face = 谁在写回：dotnet | gradle
#   kind = 调用方声明的补录面：deps（人工/常规重锁）| dependabot（给 bump PR 补依赖证据）
#   exit 0 = 允许写回；exit 2 = 拒绝（并说明是哪一条规则拒的）
#
# 三条规则都在这一份文件里：①kind 的闭集与前缀映射；②face=dotnet 不接受 dependabot
# （补录面目前只实现了 Gradle——NuGet/pip 的锁由 Dependabot 自己改，缺的只有 sha256 那一面，
# 所以宁可拒掉也不假装支持）；③master/main、完整 ref、含 `..` 是**独立检查**，不依赖①那张表
# ——把 `deps/`（只有前缀）拒掉则是①的通配顺带保证的，所以不再单写一条。
#
# 判它的用例：tests/python/relock_branch_guard_test.py（真调 bash 跑正反案例，
# 不是文本锚——文本锚管不住「shell 里少写一个括号」这类错）。
set -euo pipefail

face="${1-}"
kind="${2-}"
target="${3-}"

case "$face" in
  dotnet | gradle) ;;
  *)
    echo "❌ face 只能是 dotnet 或 gradle（收到：'${face}'）——拒绝写回" >&2
    exit 2
    ;;
esac

if [[ "$face" == "dotnet" && "$kind" == "dependabot" ]]; then
  echo "❌ face=dotnet 没有 dependabot 补录面（只有 Gradle 的校验和需要 CI 生成）——拒绝写回" >&2
  exit 2
fi

# 允许清单：kind → 前缀。两边**互斥**（deps 面不许写 dependabot 分支，反之亦然），
# 这样「选错 kind」不会悄悄写到另一类分支上。
case "$kind" in
  deps) prefix="deps/" ;;
  dependabot) prefix="dependabot/" ;;
  *)
    echo "❌ kind 只能是 deps 或 dependabot（收到：'${kind}'）——拒绝写回" >&2
    exit 2
    ;;
esac

# 主干永远不可达：即使有人把前缀改成 `master`（或建了一条叫 `deps/` 前缀的分支再合并），
# 这一道是独立检查，不依赖上面那张表。
case "$target" in
  master | main)
    echo "❌ 目标分支是主干（${target}）——Dependency-Retlock 永不写 master" >&2
    exit 2
    ;;
esac

# 完整 ref 与 `..` 都显式拒：`refs/heads/deps/x` 与 `deps/../master` 都能被 `git push`
# 解释成别的东西，靠「不以 deps/ 开头」顺带挡不住。
# **层数不设限**是实测出来的，不是宽容：本仓已关/已并的 Dependabot PR 的分支名段数就不止一档
# （`gh pr list --json headRefName` 现读）——`dependabot/pip/cryptography-50.0.2` 三段、
# `dependabot/gradle/android/minor-and-patch-0bc2cf4c4f` 四段（group 更新）、
# `dependabot/github_actions/gradle/actions/dependency-submission-6.4.0` 五段。
# 任何「按段数限形」的规则都会把补录面对其中一部分真实分支关掉，所以这里只认前缀 + 至少一个字符。
case "$target" in
  refs/*)
    echo "❌ 目标分支要写短名而不是完整 ref（${target}）" >&2
    exit 2
    ;;
  *..*)
    echo "❌ 目标分支含 '..'（${target}）——拒绝，不做路径式解释" >&2
    exit 2
    ;;
esac

if [[ "$target" != "${prefix}"?* ]]; then
  # `?*` 已经要求前缀之后至少还有一个字符，所以 `deps/`（只有前缀）在这一条就被拒——
  # 曾经在这里另写了一段「只有前缀没有名字」的独立检查，变异测试证明它永远到不了。
  echo "❌ target_kind=${kind} 只允许写 ${prefix}<名字>（收到：'${target}'）" >&2
  exit 2
fi

echo "✅ 写回目标允许：kind=${kind} branch=${target}"
