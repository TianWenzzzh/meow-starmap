#!/usr/bin/env python3
"""模板硬门禁：token 模板 ↔ golden 基线的字节级往返（v2.7 历史 / v2.8-lazy 现役）。

- V27RoundtripTest：05 仓库 v2.7 正式版基线的历史回归（v27_template + v27 规则），
  保证模板演进到 v2.8 后，v2.7 提取真相仍可随时复核；
- V28RoundtripTest：当前 template/starmap.html 与 v28-lazy 基线逐字节往返，
  golden 由 tools/make_v28_baseline.py 确定性生成（另有金新鲜度测试兜底）。

运行：python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIX = REPO_ROOT / "tests" / "fixtures"


class _RoundtripBase:
    template_path: Path
    rules_path: Path
    baseline_path: Path
    photo_script_count: int          # 引导串中 <script> 数（v27=8 eager 片）
    expect_source_sha: bool

    @classmethod
    def setUpClass(cls) -> None:
        cls.template = cls.template_path.read_text(encoding="utf-8")
        cls.fixtures = json.loads(cls.rules_path.read_text("utf-8"))
        cls.rules = cls.fixtures["rules"]
        cls.source = cls.baseline_path.read_text(encoding="utf-8")

    def test_source_sha_matches_fixture(self) -> None:
        """fixtures 必须确实来自声称的 v2.7 基准（v28 的 golden 自身即真相，跳过）。"""
        if not self.expect_source_sha:
            self.skipTest("v28 golden 由 make_v28_baseline 自生成，无外部 sha")
        sha = hashlib.sha256(self.source.encode("utf-8")).hexdigest()
        self.assertEqual(sha, self.fixtures["source_sha256"])

    def test_forward_chain_counts_and_output(self) -> None:
        """顺序模拟提取：每条规则 old 次数与记录一致，最终产物 == 模板。"""
        text = self.source
        for r in self.rules:
            self.assertEqual(text.count(r["old"]), r["count"],
                             f"规则 {r['name']} 次数不符")
            text = text.replace(r["old"], r["new"])
        self.assertEqual(text, self.template)

    def test_source_has_no_token_literals(self) -> None:
        self.assertFalse(re.findall(r"__[A-Z_]{3,}__", self.source))

    def test_roundtrip_byte_for_byte(self) -> None:
        """模板按规则正序灌回后与基线逐字节相同（必须正序，复合规则内嵌叶子）。"""
        text = self.template
        for r in self.rules:
            self.assertIn(r["new"], text, f"模板缺少 token：{r['new']}")
            text = text.replace(r["new"], r["old"])
        self.assertEqual(text, self.source)

    def test_template_has_no_unknown_tokens(self) -> None:
        known = set()
        for r in self.rules:
            known.update(re.findall(r"__[A-Z_]+__", r["new"]))
        in_template = set(re.findall(r"__[A-Z_]+__", self.template))
        self.assertEqual(in_template - known, set())
        for must in ("__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__",
                     "__AREAS_BLOCK__", "__AREA_KEYS_BLOCK__", "__REL_BLOCK__",
                     "__CONST_BLOCK__", "__PRODUCT__",
                     "__MILESTONES__", "__PASS_TITLES_JS__"):
            self.assertIn(must, known)

    def test_template_line_count(self) -> None:
        lines = self.template.count("\n") + 1
        self.assertGreaterEqual(lines, 3300)
        self.assertLessEqual(lines, 3700)

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
                self.assertIn(needle, self.template)

    def test_blocks_hold_full_nuc_data(self) -> None:
        by_name = {r["name"]: r["old"] for r in self.rules}
        self.assertEqual(by_name["cats_block"].count('id:"CAT-'), 76)
        calib_keys = re.findall(r'"CAT-\d+":\{x:', by_name["calib_block"])
        self.assertEqual(len(calib_keys), 54)
        self.assertEqual(by_name["areas_block"].count("{x:"), 12)
        self.assertEqual(by_name["const_block"].count('{n:"'), 12)
        self.assertEqual(by_name["rel_block"].count('label:"'), 2)
        self.assertEqual(
            by_name["photo_scripts"].count("<script"), self.photo_script_count)

    def test_author_attribution_kept(self) -> None:
        self.assertIn("© 2026 TianWenzzzh", self.template)
        joined_old = "".join(r["old"] for r in self.rules)
        self.assertIn("© 2026 TianWenzzzh", joined_old)


class V27RoundtripTest(_RoundtripBase, unittest.TestCase):
    template_path = FIX / "v27_template.html"
    rules_path = FIX / "nuc_literals.v27.json"
    baseline_path = FIX / "v27_baseline.html"
    photo_script_count = 8           # 8 个 eager 照片分片标签
    expect_source_sha = True


class V28RoundtripTest(_RoundtripBase, unittest.TestCase):
    template_path = REPO_ROOT / "template" / "starmap.html"
    rules_path = FIX / "nuc_literals.json"
    baseline_path = FIX / "v28_baseline_lazy.html"
    photo_script_count = 2           # 00 关键片标签 + __PM 清单脚本
    expect_source_sha = False

    def test_lazy_loader_runtime_present(self) -> None:
        """v2.8 加载器永久代码必须在模板内（eager 产物靠 typeof 守卫 no-op）。"""
        for needle in ("const __PHOTO_BOOT=", "function __ensureChunk(",
                       "function __ensurePhoto(", "function __whenPhoto("):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.template)

    def test_eager_bootstrap_absent_from_template(self) -> None:
        """模板不得内联具体分片 <script src> 标签或 __PM 数据（只能经 build 注入）。
        加载器运行时用字符串拼接动态生成 src（s.src="assets/..."+i），不在此列。"""
        self.assertNotIn('<script src="assets/photo-data-', self.template)
        self.assertNotIn("const __PM=", self.template)


if __name__ == "__main__":
    unittest.main(verbosity=2)
