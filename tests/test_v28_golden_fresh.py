#!/usr/bin/env python3
"""v29 golden 新鲜度门禁：make_v29 补丁脚本 → baseline/rules/template 必须入库一致。

任何人改了 v29 补丁（F11 token）、build.py 引导渲染或 schools/nuc 分片布局
而忘记重跑 tools/make_v29_baseline.py，本测试立即变红。
v28 golden 的新鲜度由其生成脚本的历史快照测试覆盖（v28 已冻结）。
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class V29GoldenFreshnessTests(unittest.TestCase):
    def test_make_v29_baseline_check_clean(self) -> None:
        r = subprocess.run(
            [sys.executable, str(REPO / "tools" / "make_v29_baseline.py"),
             "--check"],
            capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(
            r.returncode, 0,
            "v29 golden 漂移：\n" + r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
