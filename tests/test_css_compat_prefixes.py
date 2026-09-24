#!/usr/bin/env python3
"""一方案 CSS 的 Safari 前缀门禁：`backdrop-filter` 必须成对出现。

Safari（iOS/macOS）至今只认 `-webkit-backdrop-filter`，漏前缀的面板在 Safari
上背景不糊、直接透出满亮度底图。v33 代际把模板补齐了，但**展示墙/落地页/404**
这几份一方案 HTML 不由模板 golden 生成，代际脚本管不到它们——所以在这里统一看守，
任何人新增一处裸 `backdrop-filter` 都会立即变红。

生成产物（nuc/、demo/、schools/）不在本门禁范围内：它们的真相在模板，
由 tests/test_template_roundtrip.py 与托管产物漂移门禁负责。

运行：python3 -m unittest tests.test_css_compat_prefixes -v
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 一方案（手维护）HTML → 该文件里标准 backdrop-filter 声明的应有条数。
# 条数也钉住：只删不补、或整段被搬走，同样要红。
FIRST_PARTY: dict[Path, int] = {
    Path("template/starmap.html"): 17,
    Path("gallery/index.html"): 1,
    Path("index.html"): 0,
    Path("404.html"): 0,
}

# 标准声明（不含前缀版）；值允许 blur() 与可选 saturate()
_DECL = re.compile(
    r"(?<!-webkit-)(backdrop-filter:\s*blur\([0-9.]+px\)(?:\s+saturate\([0-9.]+\))?;)")


def missing(text: str) -> list[str]:
    """按位置判定：每条标准声明右侧必须紧跟 ` -webkit-同值`（允许换行缩进）。"""
    out = []
    for m in _DECL.finditer(text):
        tail = text[m.end():]
        if not re.match(r"\s*-webkit-" + re.escape(m.group(1)), tail):
            out.append(m.group(1))
    return out


class BackdropFilterPrefixTests(unittest.TestCase):
    def test_detector_is_not_vacuous(self) -> None:
        """自检：检测器对「裸声明」必须报问题、对「成对声明」必须放行。

        没有这条，本门禁可能在正则失配时空转（永远绿）。
        """
        bad = ".a{backdrop-filter:blur(12px); color:#fff}"
        good = ".a{backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px);}"
        mixed = ".a{backdrop-filter:blur(6px);}\n.b{backdrop-filter:blur(8px); " \
                "-webkit-backdrop-filter:blur(8px);}"
        self.assertEqual(missing(bad), ["backdrop-filter:blur(12px);"],
                         "检测器漏报：裸声明没被抓到，门禁是假绿的")
        self.assertEqual(missing(good), [])
        self.assertEqual(missing(mixed), ["backdrop-filter:blur(6px);"])
        # 前缀版不得被当成待补对象（否则会把已配对的重复补一遍）
        self.assertEqual(len(_DECL.findall(good)), 1)

    def test_every_first_party_declaration_is_paired(self) -> None:
        for rel, expect in FIRST_PARTY.items():
            path = REPO / rel
            with self.subTest(file=str(rel)):
                self.assertTrue(path.exists(), f"一方案文件消失：{rel}")
                text = path.read_text("utf-8")
                decls = _DECL.findall(text)
                self.assertEqual(
                    len(decls), expect,
                    f"{rel} 有 {len(decls)} 处 backdrop-filter，预期 {expect} 处")
                gaps = missing(text)
                self.assertEqual(
                    gaps, [],
                    f"{rel} 缺 -webkit- 兄弟声明：{gaps}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
