"""selftest_session_store.py —— session_store 模块自检（独立 UTF-8 脚本）。

验证点（全部离线，不依赖 pywebview）：
1. save/load round-trip（快照还原一致）
2. 原子写：无 .tmp 残留
3. URL 白名单清洗：file://（非 START_URL）/ javascript: / data: 丢弃
4. title/group 截断（80/32 上限）
5. MAX_TABS=20 截断；current 钳制
6. 损坏文件 / 空目录 / 版本不匹配 → load 返回 None（fail-closed）
"""
from _selftest_support import check, failures  # M-6 共享支撑


import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.session_store import MAX_TABS, START_URL, SessionStore


tmp = tempfile.mkdtemp(prefix="aegis_selftest_")
store = SessionStore(tmp)

# 1) round-trip
tabs = [
    {"title": "站点A", "url": "https://a.cn/", "pinned": False, "group": "默认"},
    {"title": "文档", "url": "https://docs.cn/x?q=1", "pinned": True, "group": "工作"},
]
check("save 成功", store.save(tabs, 1))
back = store.load()
check("load 返回非空", back is not None)
check("round-trip 标签一致", back["tabs"] == tabs, f"{back}")
check("round-trip current 一致", back["current"] == 1)

# 2) 原子写：无 .tmp 残留
check("无 .tmp 残留", not Path(store.path + ".tmp").exists())

# 3) URL 白名单清洗
bad = [
    {"title": "本地页", "url": "file:///C:/Windows/system32/config", "pinned": False},
    {"title": "js", "url": "javascript:alert(1)", "pinned": False},
    {"title": "data", "url": "data:text/html,<h1>", "pinned": False},
    {"title": "壳页", "url": START_URL, "pinned": False},  # 唯一放行的 file://
    {"title": "ok", "url": "http://plain.cn", "pinned": False},
]
check("save 混合快照成功", store.save(bad, 0))
back = store.load()
check("白名单清洗后仅剩 2 条", back is not None and len(back["tabs"]) == 2,
      f"{back and back['tabs']}")
check("清洗保留 START_URL", back["tabs"][0]["url"] == START_URL)
check("清洗保留 http", back["tabs"][1]["url"] == "http://plain.cn")

# 4) 截断
long_tab = {"title": "标" * 200, "url": "https://t.cn", "group": "组" * 100}
check("save 长字段成功", store.save([long_tab], 0))
back = store.load()
check("title 截断到 80", len(back["tabs"][0]["title"]) == 80)
check("group 截断到 32", len(back["tabs"][0]["group"]) == 32)

# 5) MAX_TABS + current 钳制
many = [{"title": f"t{i}", "url": f"https://x{i}.cn", "pinned": False}
        for i in range(MAX_TABS + 10)]
check("save 超量成功", store.save(many, MAX_TABS + 50))
back = store.load()
check("标签数截断到 MAX_TABS", back is not None and len(back["tabs"]) == MAX_TABS)
check("current 钳制到末尾", back["current"] == MAX_TABS - 1)

# 6) 损坏 / 缺失 / 版本不匹配
check("空目录 load → None", SessionStore(tempfile.mkdtemp(
    prefix="aegis_empty_")).load() is None)
Path(store.path).write_text("{broken json", encoding="utf-8")
check("损坏 JSON load → None", store.load() is None)
Path(store.path).write_text(json.dumps({"version": 999, "tabs": [], "current": 0}),
                            encoding="utf-8")
check("版本不匹配 load → None", store.load() is None)

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("OK — session_store 全部自检通过")
