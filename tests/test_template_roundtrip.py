#!/usr/bin/env python3
"""P2 硬门禁：v2.7 HTML ↔ token 模板的字节级往返。

把 tests/fixtures/nuc_literals.json 里保存的原始字面量全部灌回
template/starmap.html，必须与 05 仓库的「中北喵星图.html」逐字节相同
（sha256 相等）。差一个空格都算提取器破坏了源文件。

运行：python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (REPO_ROOT / "template" / "starmap.html").read_text(encoding="utf-8")
FIXTURES = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "nuc_literals.json").read_text("utf-8"))
RULES = FIXTURES["rules"]


def _starmap_home() -> Path:
    home = os.environ.get("STARMAP_HOME", "/media/tianwen/KINGSTON/猫咪星图_总库")
    return Path(home) / "05_git仓库_最新v2.6" / "中北喵星图.html"


SOURCE_PATH = _starmap_home()


@unittest.skipUnless(SOURCE_PATH.exists(), f"基准文件不存在：{SOURCE_PATH}")
class RoundtripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")

    def test_source_sha_matches_fixture(self) -> None:
        """fixtures 必须确实来自当前这份 v2.7 基准。"""
        sha = hashlib.sha256(self.source.encode("utf-8")).hexdigest()
        self.assertEqual(sha, FIXTURES["source_sha256"])

    def test_forward_chain_counts_and_output(self) -> None:
        """顺序模拟提取器：每条规则应用前 old 次数必须与记录一致，
        最终产物 == 仓库中的模板。count 是「中间文本」视角而非源文件视角。"""
        text = self.source
        for r in RULES:
            self.assertEqual(text.count(r["old"]), r["count"],
                             f"规则 {r['name']} 次数不符")
            text = text.replace(r["old"], r["new"])
        self.assertEqual(text, TEMPLATE)

    def test_source_has_no_token_literals(self) -> None:
        """前提：源 HTML 不得自带 __TOKEN__ 形态，否则正向/逆向替换会碰撞。"""
        self.assertFalse(re.findall(r"__[A-Z_]{3,}__", self.source))

    def test_roundtrip_byte_for_byte(self) -> None:
        """模板按规则**正序**灌回原始字面量后，与源 HTML 逐字节相同。

        必须正序：复合规则（如 console_line2）的 new 内嵌叶子 token
        （__REPO_URL__），逆序会先把叶子还原导致复合 new 失配。
        """
        text = TEMPLATE
        for r in RULES:
            self.assertIn(r["new"], text, f"模板缺少 token：{r['new']}")
            text = text.replace(r["new"], r["old"])
        self.assertEqual(text, self.source)
        self.assertEqual(
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            FIXTURES["source_sha256"])

    def test_template_has_no_unknown_tokens(self) -> None:
        """模板中每个 __TOKEN__ 都必须由某条规则的 new 产生（无拼写野 token）。"""
        known = set()
        for r in RULES:
            known.update(re.findall(r"__[A-Z_]+__", r["new"]))
        in_template = set(re.findall(r"__[A-Z_]+__", TEMPLATE))
        self.assertEqual(in_template - known, set())
        # 关键 token 一个都不能少
        for must in ("__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__",
                     "__AREAS_BLOCK__", "__AREA_KEYS_BLOCK__", "__REL_BLOCK__",
                     "__CONST_BLOCK__", "__PRODUCT__",
                     "__MILESTONES__", "__PASS_TITLES_JS__"):
            self.assertIn(must, known)

    def test_template_line_count(self) -> None:
        """模板 3605 行级基准：块替换后约 3300+ 行（防止误吞大段代码）。"""
        self.assertGreaterEqual(TEMPLATE.count("\n") + 1, 3300)
        self.assertLessEqual(TEMPLATE.count("\n") + 1, 3605)

    # ---- v2.7 特性代码原样存在（token 化不得阉割功能） ----
    def test_features_preserved(self) -> None:
        markers = {
            "影廊": 'id="btnGallery"',
            "星系独立画布": "galCv",
            "喵星护照": 'id="passP"',
            "本命猫测试": 'id="soulP"',
            "冬季初雪": "drawSnow",
            "秋季金叶": "开学季星尘里飘金叶",
            "寻猫海报": "makeFieldPoster",
            "分享卡": "drawShareCard",
            "十二星宿渲染": "drawConstellations",
            "星域关系网渲染": "drawRelations",
            "分区标注渲染": "drawAreas",
            "PH 取图函数": "function PH(p)",
        }
        for label, needle in markers.items():
            with self.subTest(feature=label):
                self.assertIn(needle if needle.startswith(("const", "function"))
                              else needle, TEMPLATE)

    def test_blocks_hold_full_nuc_data(self) -> None:
        """fixtures 保存的块字面量必须含 76 猫 / 54 人工校准 / 8 分片。

        事实（2026-09-16 盘点核实）：v2.7 的 CALIB 只固化 54 个建成区锚点，
        其余 22 只运行时由 basePos()（mulberry32 种子坐标）兜底。build.py
        对 nuc 注入这 54 键；无 calib 的学校 CALIB 为空，浏览器自动 basePos。
        """
        by_name = {r["name"]: r["old"] for r in RULES}
        self.assertEqual(by_name["cats_block"].count('id:"CAT-'), 76)
        calib_keys = re.findall(r'"CAT-\d+":\{x:', by_name["calib_block"])
        self.assertEqual(len(calib_keys), 54)
        self.assertEqual(by_name["photo_scripts"].count("<script"), 8)
        self.assertEqual(by_name["areas_block"].count("{x:"), 12)
        self.assertEqual(by_name["const_block"].count('{n:"'), 12)
        self.assertEqual(by_name["rel_block"].count('label:"'), 2)

    def test_author_attribution_kept(self) -> None:
        """原作者署名只许追加不许抹除：模板与 fixtures 均须保留 © 2026。"""
        self.assertIn("© 2026 TianWenzzzh", TEMPLATE)
        joined_old = "".join(r["old"] for r in RULES)
        self.assertIn("© 2026 TianWenzzzh", joined_old)


if __name__ == "__main__":
    unittest.main(verbosity=2)
