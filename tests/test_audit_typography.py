#!/usr/bin/env python3
"""audit_typography 工具的单测。

核心不变式：工具从 <style> 解析出的 font-size 声明数 == 源文本中
`font-size:` 的出现次数（模板书写风格统一为 `font-size:`，SVG 属性用
`font-size=`，canvas 用 `px` 字面量，三者天然不重叠）——防止解析器漏算/多算。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from audit_typography import (  # noqa: E402
    _split_declarations,
    audit_canvas_scripts,
    audit_css,
    audit_file,
    audit_svg_attrs,
    iter_css_blocks,
)

SAMPLE = """<html><head><style>
  :root{ --x:1; }
  html,body{ font-family:"PingFang SC","Microsoft YaHei",sans-serif;
    font-size:14px; }
  .chip .n{ font-size:9.5px; font-family:"a;b",c; }
  @media (max-width:768px){
    .chip{ font-size:11px; }
    @supports (backdrop-filter: blur(1px)){
      .panel{ font-size:12.5px; }
    }
  }
  .logo{ font:700 18px sans-serif; }
  .motto{ font: inherit; }
  @keyframes pop{ from{opacity:0} to{opacity:1} }
  .after{ font-size:13px; }
</style></head>
<body>
<script>
  ctx.font='11px "PingFang SC","Microsoft YaHei"'; doWork();
  g.font='900 '+fs+'px "PingFang SC","Microsoft YaHei",sans-serif';
</script>
<svg><text font-size="34" font-family="PingFang SC,Microsoft YaHei,sans-serif">喵</text></svg>
</body></html>
"""


class CssBlockTests(unittest.TestCase):
    def test_top_level_rule_lines_are_1_based(self) -> None:
        blocks = list(iter_css_blocks("a{ color:red; }"))
        self.assertEqual(blocks, [("a", " color:red; ", 1)])

    def test_media_nesting_prefixes_selector_and_keeps_lines(self) -> None:
        css = "\n".join([
            "@media (max-width:768px){",   # 行1
            "  .chip{ font-size:11px; }",  # 行2
            "}",                           # 行3
        ])
        blocks = list(iter_css_blocks(css))
        self.assertEqual(len(blocks), 1)
        sel, body, line = blocks[0]
        self.assertTrue(sel.startswith("@media (max-width:768px) :: .chip"))
        self.assertIn("font-size:11px", body)
        self.assertEqual(line, 2)

    def test_keyframes_do_not_corrupt_following_rules(self) -> None:
        css = "\n".join([
            "@keyframes pop{ from{opacity:0} to{opacity:1} }",  # 行1
            ".after{ font-size:13px; }",                        # 行2
        ])
        blocks = list(iter_css_blocks(css))
        self.assertEqual(len(blocks), 3)  # from / to / .after
        sel, body, line = blocks[-1]
        self.assertEqual(sel, ".after")
        self.assertIn("font-size:13px", body)
        self.assertEqual(line, 2)
        for s, _, _ in blocks:
            self.assertNotIn("}", s, "选择器不应混入残留花括号")

    def test_keyframes_after_inline_comment_is_still_nested(self) -> None:
        """模板惯例：前一条规则 } 后跟行内注释，紧接着 @keyframes。"""
        css = "\n".join([
            ".prev{ color:red; }   /* 落空：暗红呼吸 */",        # 行1
            "@keyframes missPulse{ 0%,100%{ box-shadow:none; }",  # 行2
            "  50%{ box-shadow:none; } } /* 尾注 */",             # 行3
            ".after{ font-size:12px; }",                          # 行4
        ])
        blocks = list(iter_css_blocks(css))
        sels = [s for s, _, _ in blocks]
        # .after 的 selector 带前一条规则的行内注释前缀（如实呈现源文本）
        self.assertTrue(any(s.endswith(".after") for s in sels), sels)
        self.assertTrue(
            any("missPulse" in s for s in sels), sels)
        for s in sels:
            self.assertNotIn("}", s)
        # keyframes 的内部块（from/50% 等）只能以嵌套前缀形态出现，
        # 不得泄漏为顶层选择器
        for s in (s for s in sels if " :: " not in s):
            self.assertNotIn("50%", s)

    def test_unbalanced_braces_raise(self) -> None:
        with self.assertRaises(ValueError):
            list(iter_css_blocks("@media x{ .a{ color:red; }"))


class DeclarationSplitTests(unittest.TestCase):
    def test_semicolon_inside_quotes_is_not_a_separator(self) -> None:
        decls = list(_split_declarations('font-family:"a;b",c; color:red'))
        self.assertEqual(decls, ['font-family:"a;b",c', "color:red"])

    def test_parenthesised_values_survive(self) -> None:
        decls = list(_split_declarations("width:calc(1px + 2px); x:y"))
        self.assertEqual(decls, ["width:calc(1px + 2px)", "x:y"])


class AuditCssTests(unittest.TestCase):
    def test_font_size_entries_in_file_order(self) -> None:
        result = audit_css(SAMPLE)
        sizes = result["props"]["font-size"]
        self.assertEqual([e["value"] for e in sizes],
                         ["14px", "9.5px", "11px", "12.5px", "13px"])

    def test_shorthand_filter_and_clean_selectors(self) -> None:
        result = audit_css(SAMPLE)
        # font:700 18px 登记；font:inherit 不登记
        self.assertEqual(len(result["font_shorthand"]), 1)
        self.assertEqual(result["font_shorthand"][0]["selector"], ".logo")
        for e in result["props"]["font-size"]:
            self.assertNotIn("}", e["selector"])
            self.assertNotIn("\n", e["selector"])

    def test_tracked_props_present(self) -> None:
        result = audit_css(SAMPLE)
        self.assertEqual(len(result["props"]["font-family"]), 2)


class CanvasAndSvgTests(unittest.TestCase):
    def test_canvas_static_and_dynamic(self) -> None:
        fonts = audit_canvas_scripts(SAMPLE)
        self.assertEqual(len(fonts), 2)
        self.assertFalse(fonts[0]["dynamic"])
        self.assertEqual(fonts[0]["static_px"], [11.0])
        self.assertTrue(fonts[1]["dynamic"])
        self.assertEqual(fonts[1]["static_px"], [])  # px 在拼接串里，非静态字面量

    def test_svg_attrs(self) -> None:
        svg = audit_svg_attrs(SAMPLE)
        self.assertEqual(svg["font_size"], [{"value": "34", "line": 22}])
        self.assertEqual(svg["font_family"],
                         ["PingFang SC,Microsoft YaHei,sans-serif"])


class RealTemplateInvariantTests(unittest.TestCase):
    """真实模板上的自洽不变式：解析声明数 == `font-size:` 出现次数。"""

    def test_font_size_count_matches_source(self) -> None:
        path = REPO_ROOT / "template" / "starmap.html"
        result = audit_file(path)
        parsed = sum(t["count"] for t in result["css_font_size_tiers"])
        self.assertEqual(parsed, path.read_text("utf-8").count("font-size:"))

    def test_lines_are_absolute_and_per_tier_monotonic(self) -> None:
        result = audit_file(REPO_ROOT / "template" / "starmap.html")
        for tier in result["css_font_size_tiers"]:
            lines = [r["line"] for r in tier["rules"]]
            self.assertTrue(all(l >= 1 for l in lines), tier["value"])
            self.assertEqual(lines, sorted(lines), tier["value"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
