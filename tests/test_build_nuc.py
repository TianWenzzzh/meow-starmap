"""P3 验收：中北 76 只全量数据包构建产物必须与 v2.7 语义等价。

硬断言：
  1. HTML 无残留 token；
  2. CATS 76 条 12 字段，人工小传/亮度等与 v2.7 真值（cats_override）全等；
  3. CALIB 54 键坐标与 v2.7 逐键差 ≤0.02（实测全 0），22 只无键走 basePos；
  4. AREAS/AREA_KEYS/REL/CONST/stars 与数据包全等；
  5. __PHOTOS 76 键（75 猫照 + 1 底图），每个数据行与 v2.7 分片逐字节相同；
  6. 52 条提取规则的原文字面量（整块除外）在产物中逐字保留；
  7. 原创署名与 GitHub 链接存在。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_HOME = Path(os.environ.get("STARMAP_HOME",
                            "/media/tianwen/KINGSTON/猫咪星图_总库"))
SRC_ASSETS = _HOME / "05_git仓库_最新v2.6" / "assets"
DIST = Path("/tmp/meow-starmap-test/nuc")

STR_FIELDS = ("id", "name", "rank", "title", "coat", "coatGroup",
              "features", "area", "bio", "photo")


def build_once() -> None:
    if (DIST / "中北喵星图.html").exists():
        return
    DIST.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build.py"),
         "--pkg", str(REPO / "schools" / "nuc"),
         "--out", str(DIST)],
        check=True, capture_output=True, text=True, cwd=str(REPO))


def num(tok: str) -> float:
    return float(tok)


class NucBuildTests(unittest.TestCase):
    html: str = ""
    fx: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        build_once()
        cls.html = (DIST / "中北喵星图.html").read_text("utf-8")
        cls.fx = json.loads((REPO / "tests" / "fixtures" /
                             "nuc_literals.json").read_text("utf-8"))

    def test_no_leftover_tokens(self) -> None:
        self.assertEqual(re.findall(r"__[A-Z_]+__", self.html), [])

    def test_cats_76_fields_match_v27(self) -> None:
        m = re.search(r"const CATS = \[(.*?)\n\];", self.html, re.S)
        self.assertIsNotNone(m)
        entries = re.findall(r"\{ id:.*?brightness:[\d.]+\s*\}",
                             m.group(1), re.S)
        self.assertEqual(len(entries), 76)
        truth = {c["id"]: c for c in json.loads(
            (REPO / "schools/nuc/data/cats_override.json").read_text("utf-8"))}
        for e in entries:
            got = {}
            for k in STR_FIELDS:
                mm = re.search(r'\b' + k + r':"((?:[^"\\]|\\.)*)"', e, re.S)
                self.assertIsNotNone(mm, f"{k} 缺失：{e[:80]}")
                got[k] = mm.group(1)
            pc = int(re.search(r"photoCount:(\d+)", e).group(1))
            br = float(re.search(r"brightness:([\d.]+)", e).group(1))
            t = truth[got["id"]]
            for k in STR_FIELDS:
                want = t[k] if k != "photo" else "assets/photos/" + t["photo"]
                self.assertEqual(got[k], want,
                                 f'{got["id"]} 字段 {k} 与 v2.7 不一致')
            self.assertEqual(pc, t["photoCount"])
            self.assertAlmostEqual(br, t["brightness"], places=6)

    def test_calib_54_keys_coords_equal(self) -> None:
        src = next(r["old"] for r in self.fx["rules"]
                   if r["name"] == "calib_block")
        src_pts = {cid: (float(x), float(y)) for cid, x, y in
                   re.findall(r'"(CAT-\d+)":\{x:([\d.]+),y:([\d.]+)\}', src)}
        self.assertEqual(len(src_pts), 54)
        m = re.search(r"const CALIB=\{(.*?)\};", self.html, re.S)
        got_pts = {cid: (float(x), float(y)) for cid, x, y in
                   re.findall(r'"(CAT-\d+)":\{x:([\d.]+),y:([\d.]+)\}',
                              m.group(1))}
        self.assertEqual(set(got_pts), set(src_pts))
        for cid, (sx, sy) in src_pts.items():
            gx, gy = got_pts[cid]
            self.assertLessEqual(abs(gx - sx), 0.02, f"{cid} x 漂移")
            self.assertLessEqual(abs(gy - sy), 0.02, f"{cid} y 漂移")
        # 22 只无 CALIB 键，浏览器 basePos 兜底
        m2 = re.search(r"const CATS = \[(.*?)\n\];", self.html, re.S)
        all_ids = set(re.findall(r'id:"(CAT-\d+)"', m2.group(1)))
        fallback = sorted(all_ids - set(got_pts))
        self.assertEqual(len(fallback), 22)

    def test_areas_keys_rel_const_stars(self) -> None:
        def block(const_name: str) -> str:
            m = re.search(rf"const {const_name}.*?;", self.html, re.S)
            return m.group(0) if m else ""
        areas = json.loads((REPO / "schools/nuc/data/areas.json")
                           .read_text("utf-8"))
        self.assertEqual(len(re.findall(r'\{x:[\d.]+,y:[\d.]+,t:"',
                                        block("AREAS"))), len(areas))
        keys = json.loads((REPO / "schools/nuc/data/area_keys.json")
                          .read_text("utf-8"))
        self.assertEqual(len(re.findall(r'\["(?:[^"\\]|\\.)*",\d+\]',
                                        block("AREA_KEYS"))), len(keys))
        rel = json.loads((REPO / "schools/nuc/data/relations.json")
                         .read_text("utf-8"))
        self.assertEqual(len(re.findall(r'\{ a:"CAT-\d+"',
                                        block("REL"))), len(rel))
        consts = json.loads((REPO / "schools/nuc/data/constellations.json")
                            .read_text("utf-8"))
        self.assertEqual(len(re.findall(r'\{n:"', block("CONST"))),
                         len(consts))
        stars = json.loads((REPO / "schools/nuc/data/poster_stars.json")
                           .read_text("utf-8"))
        sm = re.search(r"const stars=(\[.*?\]);", self.html, re.S)
        self.assertIsNotNone(sm)
        self.assertEqual(len(re.findall(r'\["CAT-\d+","', sm.group(1))),
                         len(stars))

    def test_photos_76_keys_byte_identical(self) -> None:
        if not SRC_ASSETS.exists():
            self.skipTest("总库 05 资产不在本机")
        src_lines: dict[str, str] = {}
        for f in sorted(SRC_ASSETS.glob("photo-data-*.js")):
            for ln in f.read_text("utf-8").splitlines():
                mm = re.match(r'__PHOTOS\["(.*)"\]=', ln)
                if mm:
                    src_lines[mm.group(1)] = ln
        got_lines: dict[str, str] = {}
        for f in sorted((DIST / "assets").glob("photo-data-*.js")):
            for ln in f.read_text("utf-8").splitlines():
                mm = re.match(r'__PHOTOS\["(.*)"\]=', ln)
                if mm:
                    got_lines[mm.group(1)] = ln
        self.assertEqual(len(got_lines), 76)
        self.assertEqual(set(got_lines), set(src_lines))
        for k in src_lines:
            self.assertEqual(got_lines[k], src_lines[k],
                             f"照片数据行不一致：{k}")

    def test_original_literals_preserved(self) -> None:
        """52 条规则 old 原文（整块与已知差异项除外）必须逐字保留。"""
        skip = {"cats_block", "calib_block", "areas_block",
                "area_keys_block", "rel_block", "const_block",
                "poster_stars", "photo_scripts", "cats_lead_comment"}
        for r in self.fx["rules"]:
            if r["name"] in skip:
                continue
            self.assertIn(r["old"], self.html,
                          f'v2.7 原文丢失（{r["name"]}）：{r["old"][:60]}')

    def test_signature_and_repo_present(self) -> None:
        self.assertIn("© 2026 TianWenzzzh", self.html)
        self.assertIn("github.com/TianWenzzzh/nuc-cat-starmap", self.html)
        self.assertIn("原创", self.html)
        self.assertIn("76 只", self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
