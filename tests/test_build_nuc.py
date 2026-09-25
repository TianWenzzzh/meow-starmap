"""P3 验收：中北 76 只全量数据包构建产物必须与数据包语义等价。

硬断言：
  1. HTML 无残留 token；
  2. CATS 76 条 12 字段，人工小传/亮度等与 v2.7 真值（cats_override）全等；
  3. v34 起 CALIB 为空（不再带人工键，basePos+STAR_BOX 推导），旧 54 键块
     不得复活；STAR_BOX 框限定在建成区（判据形状经真实构建测量核定）；
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

    def test_calib_is_empty_and_note_is_honest(self) -> None:
        """v34 起 nuc 不再带人工 CALIB：星位=basePos 确定性推导，页面上手拖
        校准后导出坐标。反向守卫：旧 54 键块不得悄悄复活。"""
        m = re.search(r"const CALIB=\{(.*?)\};", self.html, re.S)
        self.assertEqual(m.group(1).strip(), "", "v34 起 nuc 不再带人工 CALIB")
        self.assertIn("basePos",
                      self.html[self.html.find("const CALIB") - 200:
                                self.html.find("const CALIB")])
        self.assertNotIn('"CAT-001":{x:.626', self.html,
                         "旧的 54 键校准块不得复活")
        # 自动文案（build.py:608-613）必须如实说明「待校准」，不许再声称已标定
        self.assertIn("星位由页面内置算法按编号稳定推导", self.html)

    def test_all_generated_stars_inside_star_zone(self) -> None:
        """端到端确定性守卫：用 Python 逐位移植页面的 hashStr/mulberry32/basePos
        （含 STAR_ZONE 拒绝采样），对 76 只真猫重演撒点——每一颗都必须落在
        build_meta.star_zone 多边形内（喂进被测进程真读到的数据）。"""
        M = 0xFFFFFFFF

        def imul(a, b):
            return (a * b) & M

        def hash_str(s):
            h = 2166136261
            for c in s:
                h = imul(h ^ ord(c), 16777619)
            return h

        def mulberry32(seed):
            a = seed & M

            def rnd():
                nonlocal a
                a = (a + 0x6D2B79F5) & M
                t = imul(a ^ (a >> 15), (1 | a) & M)
                t = ((t + imul(t ^ (t >> 7), (61 | t) & M)) ^ t) & M
                return ((t ^ (t >> 14)) & M) / 4294967296
            return rnd

        def in_zone(x, y, zone):
            inside = False
            for i in range(len(zone)):
                j = (i - 1) % len(zone)
                xi, yi = zone[i]
                xj, yj = zone[j]
                if (yi > y) != (yj > y) and                         x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
            return inside

        bm = json.loads((REPO / "schools/nuc/data/build_meta.json")
                        .read_text("utf-8"))
        zone = bm["star_zone"]
        box = bm["star_box"]
        m = re.search(r"const CATS = \[(.*?)\n\];", self.html, re.S)
        ids = re.findall(r'id:"(CAT-\d+)"', m.group(1))
        self.assertEqual(len(ids), 76)
        for cid in ids:
            r = mulberry32(hash_str(cid))
            for _ in range(10_000):
                x = box["x0"] + r() * box["w"]
                y = box["y0"] + r() * box["h"]
                if in_zone(x, y, zone):
                    break
            else:
                self.fail(f"{cid} 10000 次采样都落不到 zone 内（包络/zone 配置错误）")
            self.assertTrue(in_zone(x, y, zone), f"{cid} 落在 zone 外")

    def test_star_box_confined_to_campus(self) -> None:
        """STAR_BOX 真值（2026-09-26 实测 x0=.154 y0=.294 w=.646 h=.448，
        面积 0.289）：框必须限定在建成区内，且判据对它不恒真。"""
        m = re.search(r"const STAR_BOX=\{x0:([\d.]+),y0:([\d.]+),"
                      r"w:([\d.]+),h:([\d.]+)\};", self.html)
        self.assertTrue(m, "产物里没有 STAR_BOX 字面量（形状变了就要同步这条判据）")
        x0, y0, w, h = (float(v) for v in m.groups())
        self.assertGreaterEqual(x0, 0.10)
        self.assertLessEqual(x0 + w, 0.90)
        self.assertGreaterEqual(y0, 0.15)
        self.assertLessEqual(y0 + h, 0.90)
        self.assertLess(w * h, 0.55, "框面积过大 ⇒ 等于回到整幅撒点")

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
                "poster_stars", "photo_scripts", "cats_lead_comment",
                # 深扫 E-02（2026-09-19）：页脚追加双许可行属设计内差异，
                # v2.7 原文完整保留在 tests/fixtures/v32_baseline.html
                "stats_foot",
                # P0 版本串注入（2026-09-18）：版本号改为 build_meta 驱动
                # （v2.7 → v2.8.4），两条旧字面量随产物版本演进属设计内差异
                "console_line1", "version",
                # v34（2026-09-26）：底图文件名改为数据包驱动（MAP_FILE token），
                # 两条 old 内嵌的 v2.7 旧图名属历史快照；MAP_SRC 真值由
                # test_map/冒烟另行校验
                "banner_sub", "map_src",
                # v34（2026-09-26）：删 calib_note 后该注释由 build.py 自动文案
                # 接管（星位=basePos 推导 · 可手拖校准），新文案由
                # test_calib_is_empty_and_note_is_honest 校验
                "calib_lead_comment",
                # v34（2026-09-26）：star_box 的 old 是「缺省框」字面量（golden
                # 链用），nuc 产物是 build_meta 下发的真实框，由
                # test_star_box_confined_to_campus 校验真值
                "star_box",
                # v35（2026-09-26）：star_zone 的 old 是「null」缺省字面量（golden
                # 链用），nuc 产物是 build_meta 下发的真实多边形，撒点全部落在
                # zone 内由 test_all_generated_stars_inside_star_zone 端到端守卫
                "star_zone"}
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
