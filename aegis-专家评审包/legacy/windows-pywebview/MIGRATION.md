# QtWebEngine 6.x 迁移方案（PySide6）

> 本文件由 `tools/migration_audit.py` 基于 AST 静态扫描自动生成。

## 为什么迁移

- PyQtWebEngine 5.15.7 的内核固定在 **Chromium 87**（2021），
  其后数百个公开 CVE 无法在本二进制内修复。
- QtWebEngine 6.x 随 Qt 6.5+ 提供 Chromium 100/110+，且持续跟进上游。
- PySide6 为 Qt 官方绑定，长期维护确定性高于 PyQt5 的第三方授权模式。

## 扫描结果

| 指标 | 数量 |
|------|------|
| 扫描源文件 | 69 |
| PyQt5 import 语句 | 0 |
| Signal/pyqtSlot/exec_ 等调用 | 49 |
| 疑似需复核枚举访问 | 248 处 / 90 种 |

### PyQt5 专属 API 明细

- `QRegExp` × 0 —— Qt6 移除，改用 QRegularExpression
- `Signal` × 49 —— PySide6 对应 Signal
- `exec_` × 0 —— PySide6 改名为 exec()（Python 关键字冲突已在 Py3 解除）
- `pyqtSlot` × 0 —— PySide6 对应 Slot

### 枚举复核清单（Top 40）

PySide6 要求作用域枚举（如 `Qt.AlignmentFlag.AlignCenter`）。
以下访问点需逐一确认（部分新版 PySide6 兼容旧写法，以运行测试为准）：

- `Qt.UserRole` × 24
- `QMessageBox.information` × 20
- `Qt.NoPen` × 14
- `QMessageBox.Yes` × 8
- `QLineEdit.Password` × 7
- `Qt.AlignCenter` × 7
- `QMessageBox.question` × 6
- `Qt.NoBrush` × 6
- `QFont.AbsoluteSpacing` × 6
- `QApplication.clipboard` × 5
- `Qt.WA_StyledBackground` × 4
- `QFrame.NoFrame` × 4
- `QEasingCurve.OutCubic` × 4
- `QAbstractAnimation.DeleteWhenStopped` × 4
- `QPainter.Antialiasing` × 4
- `QMessageBox.AcceptRole` × 4
- `QMessageBox.RejectRole` × 4
- `QMessageBox.warning` × 4
- `Qt.ElideRight` × 4
- `Qt.Key_Escape` × 3
- `Qt.Key_Return` × 3
- `Qt.AlignRight` × 3
- `Qt.SmoothTransformation` × 3
- `QWebEnginePage.PermissionGrantedByUser` × 3
- `Qt.AlignVCenter` × 3
- `Qt.AlignLeft` × 3
- `Qt.TextSelectableByMouse` × 3
- `Qt.Key_Down` × 2
- `Qt.Key_Up` × 2
- `Qt.NoItemFlags` × 2
- `Qt.PointingHandCursor` × 2
- `Qt.MiddleButton` × 2
- `QWebEnginePage.LifecycleState` × 2
- `QMessageBox.Warning` × 2
- `QMessageBox.No` × 2
- `QDialogButtonBox.Ok` × 2
- `QDialogButtonBox.Cancel` × 2
- `Qt.Key_Enter` × 2
- `QListWidget.ExtendedSelection` × 2
- `Qt.transparent` × 2

## 迁移阶段计划

| 阶段 | 内容 | 风险 |
|------|------|------|
| 0 | 建立 qt_compat.py 导入垫片（PyQt5/PySide6 二选一），全量测试锚定基线 | 低 |
| 1 | 替换 import 与 Signal/Slot 命名；`exec_()→exec()`（机械改动，约 40 处） | 低 |
| 2 | 枚举作用域批量修正（按上方清单，逐项跑回归） | 中 |
| 3 | QtWebEngine API 差异收口（LifecycleState/Permission 等在 Qt6 的签名变化） | 中 |
| 4 | 打包验证（PyInstaller + collect-data PySide6）与 Win11 实机回归 | 中 |

## 验收标准

- 现有 5 套自动化测试（44 项）在 PySide6 下全绿
- `qWebEngineChromiumVersion()` ≥ 100
- 性能压测（tools/perf_harness.py）冷启动不劣化超过 20%
