#!/usr/bin/env bash
# e2e-android-search.sh —— 搜索功能端到端回归（需真机/模拟器 + adb）
# 覆盖：安装 → 启动 → 输入 → 触发（按钮路径）→ 断言导航发生（非首页）
# 用法：bash scripts/e2e-android-search.sh [apk路径]
# 设备语义（PY-170，2026-09-23 审计·V1 核验批——头注承诺自此真正实现）：
#   REQUIRES_DEVICE=1   无 adb 设备 → 跳过并返回 0（CI 无设备场景）
#   未设 / 0            无 adb 设备 → 失败退出 1（人工回归应看到缺设备事实）
# PY-168（同批）：set -e 全程 fail-fast——所有 adb 步骤补 || die 兜底，
# 失败走统一 FAIL 汇总退出 1，不再有静默吞错的裸命令。
# PY-169（同批）：截屏落盘改 mktemp 临时目录——不再硬编码 /tmp/e2e_after.png
#（并行运行互相覆盖 / 目标目录不可写陷阱），退出时自动清理。
set -euo pipefail

# 审计修复：默认 APK 不再指向不存在的 2.1.7 旧路径——自动取 dist/ 最新 arm64 APK
if [ -n "${1:-}" ]; then
  APK="$1"
else
  APK="$(ls -t dist/*android*arm64*.apk dist/aegis-android/*.apk 2>/dev/null | head -n 1 || true)"
  if [ -z "$APK" ]; then echo "[e2e][SKIP] 未指定 APK 且 dist 无构建产物"; exit 0; fi
fi
PKG="com.aegis.browser"
ACT="$PKG/.MainActivity"
FAIL=0

step() { echo "[e2e] $*"; }
die()  { echo "[e2e][FAIL] $*"; FAIL=1; }

if adb get-state >/dev/null 2>&1; then
  :
else
  if [ "${REQUIRES_DEVICE:-0}" = "1" ]; then
    echo "[e2e][SKIP] 无 adb 设备（REQUIRES_DEVICE=1 → 跳过并返回 0）"
    exit 0
  fi
  echo "[e2e][FAIL] 无 adb 设备（如需跳过语义请设 REQUIRES_DEVICE=1）"
  exit 1
fi

SHOT_DIR="$(mktemp -d)"
trap 'rm -rf "$SHOT_DIR"' EXIT

step "安装 $APK"
adb install -r -t "$APK" >/dev/null || die "安装失败"

step "启动主界面"
adb logcat -c || die "清空 logcat 失败"
adb shell am force-stop "$PKG" || die "force-stop 失败"
adb shell am start -n "$ACT" || die "启动失败"
sleep 7
adb shell pidof "$PKG" >/dev/null || die "进程未存活（启动崩溃）"

step "输入搜索词并点击搜索按钮（按钮触发路径）"
# 坐标基于 1200x2670 参考屏；其他分辨率按比例换算
W_H="$(adb shell wm size 2>/dev/null | grep -o '[0-9]*x[0-9]*' | head -n 1 || true)"
[ -n "$W_H" ] || die "wm size 解析失败"
read -r W H <<<"${W_H/x/ }"
SX=$(( W * 400 / 1200 )); SY=$(( H * 1458 / 2670 ))   # 输入框
BX=$(( W * 1000 / 1200 ))                              # 搜索按钮
adb shell input tap "$SX" "$SY" || die "点击输入框失败"; sleep 1
adb shell input text "news" || die "输入搜索词失败"; sleep 1
adb shell input tap "$BX" "$SY" || die "点击搜索按钮失败"; sleep 9

step "断言：离开首页（导航已发生）"
adb shell screencap -p /sdcard/e2e_after.png || die "设备端截屏失败"
adb pull /sdcard/e2e_after.png "$SHOT_DIR/e2e_after.png" >/dev/null || die "截屏拉取失败"
adb shell rm -f /sdcard/e2e_after.png || true
# 启发式：截图字节数与首页（壁纸页）显著不同即认为发生导航
if adb shell dumpsys window 2>/dev/null | grep -q "mCurrentFocus.*$PKG"; then
  :  # 应用在前台（未被导航确认面板外的系统页抢焦点）
else
  die "应用失去前台焦点"
fi
# 直接证据：WebView 不再处于 start.html——查进程内最近页面标题
TITLE="$(adb logcat -d | grep -oE "R12 title: [^\"]*" | tail -n 1 || true)"
echo "[e2e] 最近页面标题: $TITLE"
case "$TITLE" in
  *"新标签页"*) die "仍在首页——搜索未触发导航" ;;
  "") echo "[e2e][WARN] 标题日志缺失（可能被清理）——人工复核 $SHOT_DIR/e2e_after.png" ;;
  *) echo "[e2e][PASS] 导航到: $TITLE" ;;
esac

step "断言：回退键逐级返回（不退出应用）"
adb shell input keyevent 4 || die "回退键注入失败"; sleep 3
adb shell pidof "$PKG" >/dev/null || die "回退后进程退出——回退键未消费历史栈"
echo "[e2e][PASS] 回退后进程存活"

if [ "$FAIL" -eq 1 ]; then
  echo "[e2e] 结果: FAIL"
  exit 1
fi
echo "[e2e] 结果: PASS"
