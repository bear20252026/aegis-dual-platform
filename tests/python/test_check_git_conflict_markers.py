#!/usr/bin/env python3
"""test_check_git_conflict_markers.py —— 门禁注入证红测试（Q74 R9-DOC-27）。

验证 check_git_conflict_markers.py 能正确检测冲突标记：
1. 无冲突标记时返回 0
2. 有冲突标记时返回 1 并列出位置
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_git_conflict_markers.py"


def test_no_markers():
    """无冲突标记时返回 0"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT), capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"Expected 0, got {result.returncode}: {result.stderr}"
    print("✓ test_no_markers passed")


def test_with_markers():
    """有冲突标记时返回 1"""
    # 在主仓库中创建临时文件
    temp_file = ROOT / "docs" / "test-conflict-marker.md"
    try:
        temp_file.write_text(
            "# Test\n\n"
            "<<<<<<< HEAD\n"
            "old content\n"
            "=======\n"
            "new content\n"
            ">>>>>>> branch\n",
            encoding="utf-8"
        )
        
        # 添加到 git
        subprocess.run(
            ["git", "add", str(temp_file)],
            cwd=str(ROOT), capture_output=True, check=True
        )
        
        # 运行检查脚本
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(ROOT), capture_output=True, text=True, check=False
        )
        
        assert result.returncode == 1, f"Expected 1, got {result.returncode}"
        assert "test-conflict-marker.md" in result.stderr, \
            f"Expected 'test-conflict-marker.md' in stderr: {result.stderr}"
        assert "<<<<<<<" in result.stderr or ">>>>>>>" in result.stderr, \
            f"Expected conflict marker in stderr: {result.stderr}"
        print("✓ test_with_markers passed")
    finally:
        # 清理
        try:
            temp_file.unlink()
            subprocess.run(
                ["git", "reset", "HEAD", str(temp_file)],
                cwd=str(ROOT), capture_output=True, check=False
            )
        except Exception:
            pass


if __name__ == "__main__":
    test_no_markers()
    test_with_markers()
    print("\n所有测试通过！")
