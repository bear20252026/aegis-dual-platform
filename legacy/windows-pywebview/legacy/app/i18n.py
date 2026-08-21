"""i18n.py —— 轻量国际化基础设施（B3）。

设计：
- 语言选择：环境变量 AEGIS_LANG（zh-CN 默认 / en 预留），避免引入
  设置页联动复杂度，后续可扩展为配置项。
- tr(key)：按 key 查当前语言包；未命中返回 key 原文。
- 简体中文包（_ZH）的 value 即 key 原文——当前界面本身就是中文，
  tr() 接入后行为零变化；未来增加 en 包只需扩展 _PACKS 并翻译。

接入范围（诚实声明）：主窗口全部菜单动作、命令面板动作、
设置页 tab 标题、下载栏标题。其余界面字符串为增量迁移（tr() 兜底
返回原文，不影响现有功能）。
"""

import os

_LANG = (os.environ.get("AEGIS_LANG") or "zh-CN").strip()

# 简体中文语言包（默认语言：原文即翻译，保证接入零行为变化）
_ZH = {
    # ---- 文件菜单 ----
    "新标签页 (Ctrl+T)": "新标签页 (Ctrl+T)",
    "新窗口 (Ctrl+N)": "新窗口 (Ctrl+N)",
    "新建无痕会话": "新建无痕会话",
    "恢复已关闭标签 (Ctrl+Shift+T)": "恢复已关闭标签 (Ctrl+Shift+T)",
    "关闭标签页 (Ctrl+W)": "关闭标签页 (Ctrl+W)",
    "打印为 PDF (Ctrl+P)": "打印为 PDF (Ctrl+P)",
    "退出 (Ctrl+Q)": "退出 (Ctrl+Q)",
    # ---- 编辑菜单 ----
    "复制 (Ctrl+C)": "复制 (Ctrl+C)",
    "粘贴 (Ctrl+V)": "粘贴 (Ctrl+V)",
    "在页面中查找 (Ctrl+F)": "在页面中查找 (Ctrl+F)",
    "密码管理器": "密码管理器",
    # ---- 视图菜单 ----
    "放大 (Ctrl+=)": "放大 (Ctrl+=)",
    "缩小 (Ctrl+-)": "缩小 (Ctrl+-)",
    "重置缩放 (Ctrl+0)": "重置缩放 (Ctrl+0)",
    "标签搜索 (Ctrl+Shift+A)": "标签搜索 (Ctrl+Shift+A)",
    "阅读模式": "阅读模式",
    "保存页面截图 (Ctrl+Shift+S)": "保存页面截图 (Ctrl+Shift+S)",
    "全屏 (F11)": "全屏 (F11)",
    "下载管理": "下载管理",
    # ---- 历史菜单 ----
    "查看历史记录": "查看历史记录",
    "清除浏览数据": "清除浏览数据",
    # ---- 书签菜单 ----
    "收藏/取消收藏当前页": "收藏/取消收藏当前页",
    "阅读清单…": "阅读清单…",
    "书签管理…": "书签管理…",
    # ---- 工具菜单 ----
    "设置": "设置",
    "任务管理器": "任务管理器",
    "安全仪表盘": "安全仪表盘",
    "查看源代码 (Ctrl+U)": "查看源代码 (Ctrl+U)",
    "命令面板 (Ctrl+Shift+P)": "命令面板 (Ctrl+Shift+P)",
    "站点信息": "站点信息",
    "站点权限…": "站点权限…",
    "开发者工具 (Ctrl+Shift+I)": "开发者工具 (Ctrl+Shift+I)",
    "强制深色模式": "强制深色模式",
    "视觉问答（AI）": "视觉问答（AI）",
    "AI 上网代理": "AI 上网代理",
    "AI 助手（本地）": "AI 助手（本地）",
    "保存到 IMA 笔记": "保存到 IMA 笔记",
    "IMA 知识库": "IMA 知识库",
    "网页截图 (PNG)": "网页截图 (PNG)",
    "导入书签…": "导入书签…",
    "导出书签…": "导出书签…",
    "用户脚本管理…": "用户脚本管理…",
    "更新恶意站点情报": "更新恶意站点情报",
    "导出加密同步备份…": "导出加密同步备份…",
    "导入加密同步备份…": "导入加密同步备份…",
    "同步到 WebDAV…": "同步到 WebDAV…",
    "从 WebDAV 拉取…": "从 WebDAV 拉取…",
    # ---- 帮助菜单 ----
    "检查更新": "检查更新",
    "关于 Aegis": "关于 Aegis",
    # ---- 汉堡菜单 ----
    "历史记录": "历史记录",
    "下载": "下载",
    "密码管理": "密码管理",
    "密码工具": "密码工具",
    "关于": "关于",
    # ---- 命令面板 ----
    "输入命令，如 查看源代码 / 深色 / 历史 …": "输入命令，如 查看源代码 / 深色 / 历史 …",
    "查看源代码": "查看源代码",
    "新建标签页": "新建标签页",
    "关闭当前标签": "关闭当前标签",
    "书签栏 显示/隐藏": "书签栏 显示/隐藏",
    "打印为 PDF": "打印为 PDF",
    "后退": "后退",
    "前进": "前进",
    "刷新": "刷新",
    "停止加载": "停止加载",
    "复制当前网址": "复制当前网址",
    "查找": "查找",
    "无痕新窗口": "无痕新窗口",
    # ---- 设置页 tab ----
    "外观": "外观",
    "启动": "启动",
    "隐私与安全": "隐私与安全",
    "性能": "性能",
    "网络": "网络",
    "同步": "同步",
    "AI": "AI",
    # ---- 下载栏 ----
    "暂无历史记录": "暂无历史记录",
    # ---- 汉堡/命令面板的短标签（与带快捷键后缀的菜单项并存）----
    "新标签页": "新标签页",
    "新窗口": "新窗口",
    "全屏": "全屏",
    "历史": "历史",
    "导入书签": "导入书签",
    "导出书签": "导出书签",
}

# 英文语言包（R11）：覆盖主界面高频键；未覆盖键回退原文。
_EN = {
    "新标签页 (Ctrl+T)": "New Tab (Ctrl+T)",
    "新窗口 (Ctrl+N)": "New Window (Ctrl+N)",
    "新建无痕会话": "New Incognito Window",
    "恢复已关闭标签 (Ctrl+Shift+T)": "Reopen Closed Tab (Ctrl+Shift+T)",
    "关闭标签页 (Ctrl+W)": "Close Tab (Ctrl+W)",
    "打印为 PDF (Ctrl+P)": "Print to PDF (Ctrl+P)",
    "退出 (Ctrl+Q)": "Quit (Ctrl+Q)",
    "复制 (Ctrl+C)": "Copy (Ctrl+C)",
    "粘贴 (Ctrl+V)": "Paste (Ctrl+V)",
    "在页面中查找 (Ctrl+F)": "Find in Page (Ctrl+F)",
    "密码管理器": "Password Manager",
    "放大 (Ctrl+=)": "Zoom In (Ctrl+=)",
    "缩小 (Ctrl+-)": "Zoom Out (Ctrl+-)",
    "重置缩放 (Ctrl+0)": "Reset Zoom (Ctrl+0)",
    "阅读模式": "Reader Mode",
    "全屏 (F11)": "Full Screen (F11)",
    "下载管理": "Downloads",
    "查看历史记录": "History",
    "清除浏览数据": "Clear Browsing Data",
    "收藏/取消收藏当前页": "Bookmark / Unbookmark Page",
    "阅读清单…": "Reading List…",
    "书签管理…": "Bookmark Manager…",
    "设置": "Settings",
    "任务管理器": "Task Manager",
    "安全仪表盘": "Security Dashboard",
    "查看源代码 (Ctrl+U)": "View Source (Ctrl+U)",
    "命令面板 (Ctrl+Shift+P)": "Command Palette (Ctrl+Shift+P)",
    "站点信息": "Site Info",
    "站点权限…": "Site Permissions…",
    "开发者工具 (Ctrl+Shift+I)": "Developer Tools (Ctrl+Shift+I)",
    "强制深色模式": "Force Dark Mode",
    "视觉问答（AI）": "Vision Q&A (AI)",
    "AI 上网代理": "AI Browser Agent",
    "AI 助手（本地）": "AI Assistant (Local)",
    "保存到 IMA 笔记": "Save to IMA Note",
    "IMA 知识库": "IMA Knowledge Base",
    "网页截图 (PNG)": "Screenshot (PNG)",
    "导入书签…": "Import Bookmarks…",
    "导出书签…": "Export Bookmarks…",
    "检查更新": "Check for Updates",
    "关于 Aegis": "About Aegis",
    "历史记录": "History",
    "下载": "Downloads",
    "密码管理": "Passwords",
    "密码工具": "Password Tools",
    "关于": "About",
    "暂无历史记录": "No history yet",
    "外观": "Appearance",
    "启动": "Startup",
    "隐私与安全": "Privacy & Security",
    "性能": "Performance",
    "网络": "Network",
    "同步": "Sync",
    "AI": "AI",
    "标签搜索 (Ctrl+Shift+A)": "Tab Search (Ctrl+Shift+A)",
    "用户脚本管理…": "User Scripts…",
    "输入命令，如 查看源代码 / 深色 / 历史 …": "Type a command, e.g. View Source / Dark / History …",
    "查找": "Find",
    "查看源代码": "View Source",
    "无痕新窗口": "New Incognito Window",
    "更新恶意站点情报": "Update Threat Feed",
    "新标签页": "New Tab",
    "新窗口": "New Window",
    "新建标签页": "New Tab",
    "关闭当前标签": "Close Current Tab",
    "书签栏 显示/隐藏": "Toggle Bookmark Bar",
    "后退": "Back",
    "前进": "Forward",
    "刷新": "Reload",
    "停止加载": "Stop Loading",
    "全屏": "Full Screen",
    "打印为 PDF": "Print to PDF",
    "复制当前网址": "Copy URL",
    "历史": "History",
    "保存页面截图 (Ctrl+Shift+S)": "Save Screenshot (Ctrl+Shift+S)",
    "导入书签": "Import Bookmarks",
    "导出书签": "Export Bookmarks",
    "导入加密同步备份…": "Import Encrypted Backup…",
    "导出加密同步备份…": "Export Encrypted Backup…",
    "同步到 WebDAV…": "Sync to WebDAV…",
    "从 WebDAV 拉取…": "Pull from WebDAV…",
}

_PACKS = {"zh-CN": _ZH, "en": _EN}


def set_lang(lang: str):
    """运行时切换语言（zh-CN / en；未知值回退 zh-CN）。"""
    global _LANG
    _LANG = lang if lang in _PACKS else "zh-CN"


def tr(key: str) -> str:
    """翻译 key；未命中或语言包缺失时返回原文（中文即默认）。"""
    pack = _PACKS.get(_LANG)
    if pack is None:
        return key
    return pack.get(key, key)
