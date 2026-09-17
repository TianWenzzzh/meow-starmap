#!/usr/bin/env python3
"""v2.8 golden 新鲜度门禁：补丁脚本 → baseline/rules/template 必须与入库文件一致。

任何人改了 v28 补丁（CODE_PATCHES）、build.py 引导渲染或 schools/nuc 分片
布局而忘记重跑 tools/make_v28_baseline.py，本测试立即变红。
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class V28GoldenFreshnessTests(unittest.TestCase):
    def test_make_v28_baseline_check_clean(self) -> None:
        r = subprocess.run(
            [sys.executable, str(REPO / "tools" / "make_v28_baseline.py"),
             "--check"],
            capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(
            r.returncode, 0,
            "v28 golden 漂移：\n" + r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
