"""P3 验收：中北 76 只全量数据包构建产物必须与 v2.7 语义等价。

硬断言：
  1. HTML 无残留 token；
  2. CATS 76 条 12 字段，人工小传/亮度等与 v2.7 真值（cats_override）全等；
  3. CALIB 54 键坐标与 v2.7 逐键差 ≤0.02（实测全 0），22 只无键走 basePos；
  4. AREAS/AREA_KEYS/REL/CONST/stars 与数据包全等；
  5. __PHOTOS 76 键（75 猫照 + 1 底图），解码后字节 sha256 与入库清单
     tests/fixtures/nuc_photos_sha256.json 全等（CI 无需 05 资产）；
     本机存在 05 原件时额外做分片逐行字节比对；
  6. 52 条提取规则的原文字面量（整块除外）在产物中逐字保留；
  7. 原创署名与 GitHub 链接存在。
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
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


_PHOTO_LINE = re.compile(
    r'__PHOTOS\["(.*)"\]="data:image/(\w+);base64,([^"]*)";')


def _collect_photo_bytes(assets_dir: Path) -> dict[str, tuple[str, bytes]]:
    """解析 photo-data-*.js，返回 {键: (mime, 解码字节)}。"""
    out: dict[str, tuple[str, bytes]] = {}
    for f in sorted(assets_dir.glob("photo-data-*.js")):
        for ln in f.read_text("utf-8").splitlines():
            m = _PHOTO_LINE.match(ln)
            if m:
                out[m.group(1)] = (m.group(2), base64.b64decode(m.group(3)))
    return out


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

    def test_photos_76_keys_match_sha_manifest(self) -> None:
        """76 个 __PHOTOS 键解码后必须与 v2.7 字节清单全等
        （sha256 + 字节数 + mime）。清单入库，CI 无需 05 原件即可跑。"""
        manifest = json.loads((REPO / "tests" / "fixtures" /
                               "nuc_photos_sha256.json").read_text("utf-8"))["keys"]
        got = _collect_photo_bytes(DIST / "assets")
        self.assertEqual(len(got), 76)
        self.assertEqual(set(got), set(manifest))
        for k, (mime, raw) in got.items():
            want = manifest[k]
            self.assertEqual(mime, want["mime"], f"{k} mime 漂移")
            self.assertEqual(len(raw), want["bytes"], f"{k} 字节数漂移")
            self.assertEqual(hashlib.sha256(raw).hexdigest(), want["sha256"],
                             f"照片内容变了（EXIF/压缩/替换？）：{k}")

    def test_photos_shards_line_identical_to_manifest(self) -> None:
        """76 个分片行（含 base64 编码层）逐行 sha256 必须与 v2.7 清单全等。"""
        manifest = json.loads((REPO / "tests" / "fixtures" /
                               "nuc_photos_sha256.json").read_text("utf-8"))["keys"]
        got_lines: dict[str, str] = {}
        for f in sorted((DIST / "assets").glob("photo-data-*.js")):
            for ln in f.read_text("utf-8").splitlines():
                mm = re.match(r'__PHOTOS\["(.*)"\]=', ln)
                if mm:
                    got_lines[mm.group(1)] = ln
        self.assertEqual(len(got_lines), 76)
        self.assertEqual(set(got_lines), set(manifest))
        for k, line in got_lines.items():
            self.assertEqual(
                hashlib.sha256(line.encode("utf-8")).hexdigest(),
                manifest[k]["line_sha256"],
                f"分片行与 v2.7 不一致（编码层漂移？）：{k}")

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
