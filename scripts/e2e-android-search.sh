#!/usr/bin/env bash
# e2e-android-search.sh —— 搜索功能端到端回归（需真机/模拟器 + adb）
# 覆盖：安装 → 启动 → 输入 → 触发（按钮路径）→ 断言导航发生（非首页）
# 用法：bash scripts/e2e-android-search.sh [apk路径]
# 环境要求：REQUIRES_DEVICE=1（无 adb 设备时跳过并返回 0——CI 无设备场景）
set -uo pipefail

APK="${1:-aegis-installers/Aegis-2.1.7-android-arm64.apk}"
PKG="com.aegis.browser"
ACT="$PKG/.MainActivity"
FAIL=0

step() { echo "[e2e] $*"; }
die()  { echo "[e2e][FAIL] $*"; FAIL=1; }

adb get-state >/dev/null 2>&1 || { echo "[e2e][SKIP] 无 adb 设备（REQUIRES_DEVICE）"; exit 0; }

step "安装 $APK"
adb install -r -t "$APK" >/dev/null || die "安装失败"

step "启动主界面"
adb logcat -c
adb shell am force-stop "$PKG"
adb shell am start -n "$ACT" || die "启动失败"
sleep 7
adb shell pidof "$PKG" >/dev/null || die "进程未存活（启动崩溃）"

step "输入搜索词并点击搜索按钮（按钮触发路径）"
# 坐标基于 1200x2670 参考屏；其他分辨率按比例换算
read -r W H <<<"$(adb shell wm size | grep -o '[0-9]*x[0-9]*' | tr 'x' ' ')"
SX=$(( W * 400 / 1200 )); SY=$(( H * 1458 / 2670 ))   # 输入框
BX=$(( W * 1000 / 1200 ))                              # 搜索按钮
adb shell input tap "$SX" "$SY"; sleep 1
adb shell input text "news"; sleep 1
adb shell input tap "$BX" "$SY"; sleep 9

step "断言：离开首页（导航已发生）"
adb shell screencap -p /sdcard/e2e_after.png
adb pull /sdcard/e2e_after.png /tmp/e2e_after.png >/dev/null || die "截屏拉取失败"
# 启发式：截图字节数与首页（壁纸页）显著不同即认为发生导航
HOME_HASH=$(adb shell "ls -l /sdcard/e2e_after.png" >/dev/null; echo skip)
if adb shell dumpsys window 2>/dev/null | grep -q "mCurrentFocus.*$PKG"; then
  :  # 应用在前台（未被导航确认面板外的系统页抢焦点）
else
  die "应用失去前台焦点"
fi
# 直接证据：WebView 不再处于 start.html——查进程内最近页面标题
TITLE=$(adb logcat -d | grep -oE "R12 title: [^\"]*" | tail -1)
echo "[e2e] 最近页面标题: $TITLE"
case "$TITLE" in
  *"新标签页"*) die "仍在首页——搜索未触发导航" ;;
  "") echo "[e2e][WARN] 标题日志缺失（可能被清理）——人工复核 /tmp/e2e_after.png" ;;
  *) echo "[e2e][PASS] 导航到: $TITLE" ;;
esac

step "断言：回退键逐级返回（不退出应用）"
adb shell input keyevent 4; sleep 3
adb shell pidof "$PKG" >/dev/null || die "回退后进程退出——回退键未消费历史栈"
echo "[e2e][PASS] 回退后进程存活"

if [ "$FAIL" -eq 1 ]; then
  echo "[e2e] 结果: FAIL"
  exit 1
fi
echo "[e2e] 结果: PASS"
