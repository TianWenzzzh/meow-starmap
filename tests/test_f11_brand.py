#!/usr/bin/env python3
"""F11（v29）主题/校徽注入测试。

默认空值字节回归由 test_template_roundtrip.V29RoundtripTest 强断言；
本文件覆盖有值通道与安全拒绝。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def build_with_meta(meta_extra: dict, out: Path) -> subprocess.CompletedProcess:
    t = out.parent
    shutil.copytree(REPO / "schools" / "示例校" / "data", t / "data",
                    dirs_exist_ok=True)
    shutil.copytree(REPO / "schools" / "示例校" / "photos", t / "photos")
    shutil.copytree(REPO / "schools" / "示例校" / "map", t / "map")
    meta = {
        "school": "品牌测试校", "product": "品牌测试校喵星图",
        "en": "BRAND CAT GALAXY", "ls_prefix": "brandtest",
    }
    meta.update(meta_extra)
    (t / "data" / "build_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / "build.py"),
         "--pkg", str(t), "--out", str(out)],
        capture_output=True, text=True, cwd=str(REPO))


class F11InjectionTests(unittest.TestCase):
    def test_theme_css_injected_and_applied(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            css = ":root{--gold:#ff00aa!important}"
            r = build_with_meta({"theme_css": css}, t / "out")
            self.assertEqual(r.returncode, 0, r.stderr)
            html = (t / "out" / "品牌测试校喵星图.html").read_text("utf-8")
            self.assertIn(css, html)
            self.assertNotIn("__THEME_CSS__", html)
            self.assertNotIn("__LOGO_INTRO__", html)
            self.assertNotIn("__LOGO_TOPBAR__", html)

    def test_logo_tags_injected_at_two_slots(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            intro = '<img class="logo" src="assets/logo.png" alt="校徽">'
            top = '<img class="logo brandLogo" src="assets/logo.png" alt="">'
            r = build_with_meta({"logo_intro": intro, "logo_topbar": top},
                                t / "out")
            self.assertEqual(r.returncode, 0, r.stderr)
            html = (t / "out" / "品牌测试校喵星图.html").read_text("utf-8")
            self.assertIn(intro, html)
            self.assertIn(top, html)
            # 校徽必须落在指定锚点附近
            self.assertIn('<div id="intro">' + intro, html)
            self.assertIn('<div class="brand">' + top, html)

    def test_theme_css_rejects_script_breakout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            r = build_with_meta(
                {"theme_css": "</style><script>alert(1)</script>"}, t / "out")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("theme_css", r.stderr + r.stdout)

    def test_logo_rejects_non_img(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            r = build_with_meta(
                {"logo_topbar": '<script>alert(1)</script>'}, t / "out")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("logo_topbar", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
