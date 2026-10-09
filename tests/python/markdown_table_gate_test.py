# markdown_table_gate_test.py —— R8-DOC-19（第八轮 2026-10-10）：表格形状门禁的自证。
#
# 这条门禁要防的是「台账写坏了却看不出来」：GFM 的表格解析器不认代码段里的裸竖线，
# `|| true` 出现在单元格里就是两个额外分隔符——整行向右错位、超出表头的列被丢弃，
# 源码里字句俱在、渲染后内容消失。第八轮的台账里实测到 12 处（含两处是本轮自己的
# 脚本把行追加坏：R8-RS 行重复了三次 `| 9 |`、R8-DEPS 行折成了五行）。
#
# 按本仓固定口径（R7-TOOL-04 / R8-PY-02）：除了「现在绿」，必须证「弄坏它会红」，
# 并且要证「不误红」——转义竖线算内容、围栏与无分隔行的管道块不算表。
from __future__ import annotations

import check_markdown_tables as mts

GOOD = """# t

| A | B |
| --- | --- |
| 1 | 2 |
"""

RAGGED = """# t

| A | B |
| --- | --- |
| 1 | 2 |
| 1 | 2 | 3 |
"""

# 代码段里的裸竖线：这正是 12 处失效的形态（GFM 会把它当分隔符）
BARE_PIPE = """# t

| A | B |
| --- | --- |
| 移除 `\\|\\| true` | 已落地 |
"""

BAD_PIPE = BARE_PIPE.replace("\\|\\|", "||")

FENCED_ART = """# t

```
+--------+
| 图 | 框 |
| 文 | 字 |
+--------+
```

| A | B |
| --- | --- |
| 1 | 2 |
"""

NO_DELIMITER = """# t

| A | B |
| 1 | 2 |
"""


def _tree(tmp_path, files):
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


def test_the_real_tree_is_rectangular(capsys):
    # 现网面：受管 *.md 全部表逐行列数与表头一致（本批修掉的 12 处即其成果）
    assert mts.main([]) == 0, capsys.readouterr().out


def test_extra_column_row_is_caught(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": RAGGED}))
    assert mts.main(["--paths", "a.md"]) == 1
    out = capsys.readouterr().out
    assert "a.md" in out and "列 ≠ 表头" in out, out


def test_bare_pipe_inside_code_span_is_caught(tmp_path, monkeypatch, capsys):
    # 反向证：裸 `||` 在单元格里 = 多出两列——正是历史台账的失效形态，必须判红
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": BAD_PIPE}))
    assert mts.main(["--paths", "a.md"]) == 1
    assert "a.md:5" in capsys.readouterr().out


def test_escaped_pipe_is_content_not_separator(tmp_path, monkeypatch):
    # 不误红：`\|` 按内容计——否则修复方案本身会被门禁判坏
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": BARE_PIPE}))
    assert mts.main(["--paths", "a.md"]) == 0


def test_fenced_ascii_art_is_not_a_table(tmp_path, monkeypatch):
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": FENCED_ART}))
    assert mts.main(["--paths", "a.md"]) == 0


def test_pipe_block_without_delimiter_row_is_not_a_table(tmp_path, monkeypatch):
    # 无分隔行的管道对齐不是 GFM 表——不得据此判红（也说明它不受本门禁保护）
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": NO_DELIMITER}))
    assert mts.main(["--paths", "a.md"]) == 2  # 零表 ⇒ 门禁未真正运行


def test_delimiter_row_mismatch_is_caught(tmp_path, monkeypatch, capsys):
    text = "| A | B | C |\n| --- | --- |\n| 1 | 2 | 3 |\n"
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": text}))
    assert mts.main(["--paths", "a.md"]) == 1
    assert "分隔行" in capsys.readouterr().out


def test_missing_explicit_file_is_environment_error(tmp_path, monkeypatch):
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": GOOD}))
    try:
        mts.main(["--paths", "a.md", "gone.md"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("指定文件缺失未 fail-closed")


def test_split_row_like_the_round8_deps_cell_is_caught(tmp_path, monkeypatch, capsys):
    # 第八轮实踩形态：一行被软折成多行（后续行仍以 `|` 开头）⇒ 列数各不相同
    text = "| A | B |\n| --- | --- |\n| 1\n| 2 | 3 |\n"
    monkeypatch.setattr(mts, "ROOT", _tree(tmp_path, {"a.md": text}))
    assert mts.main(["--paths", "a.md"]) == 1
    assert "列 ≠ 表头" in capsys.readouterr().out
