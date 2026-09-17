#!/usr/bin/env python3
"""T1：照片分片懒加载的构建产物结构门禁。

eager（旧整包）：全部片立即加载，无 __PM 清单，字节布局与历史一致。
lazy（新默认方向，T1 用 --photo-loading lazy 显式开启）：
  - 00 片=底图单独一片且唯一 eager 标签；猫片 01..N 不出现在 HTML 标签中；
  - 内联 __PM 清单覆盖全部键，底图→0、猫照→≥1 且索引连续；
  - 00 片只含底图键；每张猫照只出现一次；
  - 分片内照片解码字节与源文件一致（分组变化不得改字节）。
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT_SRC = re.compile(r'<script src="(assets/photo-data-\d+\.js)"></script>')
PHOTO_LINE = re.compile(
    r'__PHOTOS\["(.*)"\]="data:image/(\w+);base64,([^"]*)";')
PM_RE = re.compile(r"const __PM=(\{.*?\});</script>", re.S)


def run_build(pkg: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / "build.py"),
         "--pkg", str(pkg), "--out", str(out), *extra],
        capture_output=True, text=True, cwd=str(REPO))


def parse_shards(assets: Path) -> dict[str, dict[str, tuple[str, bytes]]]:
    """{分片文件名: {键: (mime, 解码字节)}}"""
    out: dict[str, dict[str, tuple[str, bytes]]] = {}
    for f in sorted(assets.glob("photo-data-*.js")):
        keys = {}
        for ln in f.read_text("utf-8").splitlines():
            m = PHOTO_LINE.match(ln)
            if m:
                keys[m.group(1)] = (m.group(2), base64.b64decode(m.group(3)))
        out[f.name] = keys
    return out


class DemoLazyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.out = t / "demo-lazy"
        r = run_build(REPO / "schools" / "示例校", cls.out,
                      "--photo-loading", "lazy")
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
        cls.html = (cls.out / "示例校喵星图.html").read_text("utf-8")
        cls.shards = parse_shards(cls.out / "assets")
        cls.map_name = "示例校园星地图.jpg"
        cls.cat_names = ["demo-cat-001.jpg", "demo-cat-002.jpg"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_only_critical_chunk_eager_in_html(self) -> None:
        tags = SCRIPT_SRC.findall(self.html)
        self.assertEqual(tags, ["assets/photo-data-00.js"], tags)
        # 猫片标签绝不出现在初始 HTML
        self.assertNotIn("photo-data-01.js", self.html)

    def test_manifest_covers_all_keys(self) -> None:
        m = PM_RE.search(self.html)
        self.assertIsNotNone(m, "缺少 __PM 清单")
        pm = json.loads(m.group(1))
        manifest = pm["m"]
        self.assertEqual(set(manifest), set(self.cat_names) | {self.map_name})
        self.assertEqual(manifest[self.map_name], 0)
        for c in self.cat_names:
            self.assertEqual(manifest[c], 1)        # 示例校 2 猫同在 01 片
        self.assertEqual(pm["n"], 2)

    def test_chunk00_is_map_only(self) -> None:
        self.assertEqual(set(self.shards["photo-data-00.js"]),
                         {self.map_name})

    def test_cat_bytes_identical_to_sources(self) -> None:
        seen: set[str] = set()
        for fname, keys in self.shards.items():
            if fname == "photo-data-00.js":
                continue
            for k, (_mime, raw) in keys.items():
                seen.add(k)
                src = REPO / "schools" / "示例校" / "photos" / k
                self.assertEqual(raw, src.read_bytes(), f"{k} 字节被改动")
        self.assertEqual(seen, set(self.cat_names))   # 每张恰好出现一次

    def test_ph_function_still_sync_for_critical_map(self) -> None:
        # PH 同步查表签名保留（底图已 eager，启动链路不依赖 Promise）
        self.assertIn("function PH(p)", self.html)
        self.assertIn(f'const MAP_SRC = "{self.map_name}";', self.html)


class DemoEagerLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.out = t / "demo-eager"
        r = run_build(REPO / "schools" / "示例校", cls.out)   # 默认=eager
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
        cls.html = (cls.out / "示例校喵星图.html").read_text("utf-8")
        cls.shards = parse_shards(cls.out / "assets")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_eager_keeps_legacy_layout(self) -> None:
        tags = SCRIPT_SRC.findall(self.html)
        self.assertEqual(tags, ["assets/photo-data-01.js"], tags)  # 旧编号 01 起
        self.assertNotIn("const __PM=", self.html)
        # 旧布局 3 键同片
        self.assertEqual(
            set(self.shards["photo-data-01.js"]),
            {"示例校园星地图.jpg", "demo-cat-001.jpg",
             "demo-cat-002.jpg"})

    def test_eager_flag_overrides_lazy_meta(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            import shutil
            shutil.copytree(REPO / "schools" / "示例校" / "data", t / "data")
            shutil.copytree(REPO / "schools" / "示例校" / "photos",
                            t / "photos")
            shutil.copytree(REPO / "schools" / "示例校" / "map", t / "map")
            (t / "data" / "build_meta.json").write_text(json.dumps({
                "school": "元数据懒校", "product": "元数据懒校喵星图",
                "en": "META CAT GALAXY", "ls_prefix": "metalazy",
                "photo_loading": "lazy"}), encoding="utf-8")
            out = t / "dist"
            r = run_build(t, out, "--eager-photos")
            self.assertEqual(r.returncode, 0, r.stderr)
            html = (out / "元数据懒校喵星图.html").read_text("utf-8")
            self.assertNotIn("const __PM=", html)     # CLI 开关压过 meta


class NucLazyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.out = t / "nuc-lazy"
        r = run_build(REPO / "schools" / "nuc", cls.out,
                      "--photo-loading", "lazy")
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
        cls.html = (cls.out / "中北喵星图.html").read_text("utf-8")
        cls.shards = parse_shards(cls.out / "assets")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_nuc_lazy_partition(self) -> None:
        tags = SCRIPT_SRC.findall(self.html)
        self.assertEqual(tags, ["assets/photo-data-00.js"])
        pm = json.loads(PM_RE.search(self.html).group(1))
        manifest = pm["m"]
        self.assertEqual(len(manifest), 76)
        map_keys = [k for k, i in manifest.items() if i == 0]
        self.assertEqual(len(map_keys), 1)
        cat_indexes = sorted({i for i in manifest.values() if i >= 1})
        self.assertEqual(cat_indexes, list(range(1, pm["n"])))  # 1..N 连续
        # 00 片仅底图；75 猫照在猫片且每键一次
        self.assertEqual(set(self.shards["photo-data-00.js"]), set(map_keys))
        all_cats: set[str] = set()
        for fname, keys in self.shards.items():
            if fname == "photo-data-00.js":
                continue
            all_cats |= set(keys)
        self.assertEqual(len(all_cats), 75)


if __name__ == "__main__":
    unittest.main(verbosity=2)
