"""示例校构建 / 零素材兜底 / 注入安全回归。

  1. 示例校数据包：2 只、无残留 token、CALIB 空、3 个照片键（2 猫+1 底图），
     内嵌照片与源文件字节相同；
  2. 无底图数据包：自动生成星野底图并完成构建（零门槛承诺）；
  3. 注入安全：恶意校名 / 危险底图文件名必须被拒绝（SystemExit），
     js 字符串转义对 </script> 等攻击串不裸奔。
"""
from __future__ import annotations

import base64
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = Path("/tmp/meow-starmap-test/demo")


def run_build(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / "build.py"), *args],
        capture_output=True, text=True, cwd=str(REPO))


def build_demo_once() -> None:
    if (DIST / "示例校喵星图.html").exists():
        return
    DIST.mkdir(parents=True, exist_ok=True)
    r = run_build("--pkg", str(REPO / "schools" / "示例校"), "--out", str(DIST))
    if r.returncode != 0:
        raise RuntimeError(r.stderr)


def photo_lines(directory: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in sorted((directory / "assets").glob("photo-data-*.js")):
        for ln in f.read_text("utf-8").splitlines():
            m = re.match(r'__PHOTOS\["(.*)"\]="data:image/jpeg;base64,(.*)";', ln)
            if m:
                out[m.group(1)] = m.group(2)
    return out


class DemoBuildTests(unittest.TestCase):
    html: str = ""
    photos: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        build_demo_once()
        cls.html = (DIST / "示例校喵星图.html").read_text("utf-8")
        cls.photos = photo_lines(DIST)

    def test_no_leftover_tokens(self) -> None:
        self.assertEqual(re.findall(r"__[A-Z_]+__", self.html), [])

    def test_two_cats_and_empty_calib(self) -> None:
        m = re.search(r"const CATS = \[(.*?)\n\];", self.html, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(len(re.findall(r'\{\s*id:"CAT-', m.group(1))), 2)
        self.assertIn("const CALIB={};", self.html)

    def test_three_photo_keys_byte_identical(self) -> None:
        # 2 张占位猫照 + 1 张底图，键 = 文件名，base64 解码后与源文件逐字节相同
        self.assertEqual(len(self.photos), 3)
        pdir = REPO / "schools" / "示例校" / "photos"
        for jpg in pdir.glob("*.jpg"):
            self.assertEqual(base64.b64decode(self.photos[jpg.name]),
                             jpg.read_bytes())
        map_dir = REPO / "schools" / "示例校" / "map"
        map_jpg = next(map_dir.glob("*.jpg"))
        self.assertEqual(base64.b64decode(self.photos[map_jpg.name]),
                         map_jpg.read_bytes())

    def test_demo_branding_present(self) -> None:
        self.assertIn("示例校喵星图", self.html)
        self.assertIn("DEMO CAT GALAXY", self.html)
        self.assertIn("github.com/TianWenzzzh/meow-starmap", self.html)


class AutoMapTests(unittest.TestCase):
    def test_package_without_map_builds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            shutil.copytree(REPO / "schools" / "示例校" / "data", t / "data")
            shutil.copytree(REPO / "schools" / "示例校" / "photos",
                            t / "photos")
            # 不带 map/ 目录
            (t / "data" / "build_meta.json").write_text(json.dumps({
                "school": "临时测试校", "product": "临时测试校喵星图",
                "en": "TMP CAT GALAXY", "ls_prefix": "tmptest",
            }), encoding="utf-8")
            out = t / "dist"
            r = run_build("--pkg", str(t), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            auto = t / "map" / "自动生成星野底图.jpg"
            self.assertTrue(auto.exists() and auto.stat().st_size > 10000)
            html = (out / "临时测试校喵星图.html").read_text("utf-8")
            self.assertEqual(re.findall(r"__[A-Z_]+__", html), [])
            self.assertIn('const MAP_SRC = "自动生成星野底图.jpg";', html)
            # 幂等：第二次直接复用，不报错
            r2 = run_build("--pkg", str(t), "--out", str(out))
            self.assertEqual(r2.returncode, 0, r2.stderr)


class InjectionSafetyTests(unittest.TestCase):
    def test_malicious_school_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "p").mkdir()
            roster = (REPO / "schools" / "示例校" / "data" / "猫咪名册.csv").read_text(
                "utf-8")
            (t / "roster.csv").write_text(roster, encoding="utf-8")
            shutil.copytree(REPO / "schools" / "示例校" / "photos", t / "photos")
            shutil.copy(REPO / "schools" / "示例校" / "map" /
                        "示例校园星地图.jpg", t / "safe-map.jpg")
            r = run_build("--school", "<script>alert(1)</script>",
                          "--data", str(t / "roster.csv"),
                          "--photos", str(t / "photos"),
                          "--map", str(t / "safe-map.jpg"),
                          "--out", str(t / "out"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("白名单", r.stderr + r.stdout)

    def test_dangerous_map_filename_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            roster = (REPO / "schools" / "示例校" / "data" / "猫咪名册.csv").read_text(
                "utf-8")
            (t / "roster.csv").write_text(roster, encoding="utf-8")
            shutil.copytree(REPO / "schools" / "示例校" / "photos", t / "photos")
            bad = t / "evil;rm.jpg"
            shutil.copy(REPO / "schools" / "示例校" / "map" /
                        "示例校园星地图.jpg", bad)
            r = run_build("--school", "安全校名",
                          "--data", str(t / "roster.csv"),
                          "--photos", str(t / "photos"),
                          "--map", str(bad),
                          "--out", str(t / "out"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("底图文件名不安全", r.stderr + r.stdout)

    def test_js_escaping_neutralizes_html_breakout(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "starmap_build", REPO / "tools" / "build.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["starmap_build"] = mod   # dataclass 注解解析需要模块已注册
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        evil = '"</script><script>alert(1)</script>'
        s = mod.js_str(evil)
        self.assertNotIn("</script", s)        # HTML 脚本闭合序列被拆
        self.assertIn("<\\/script", s)
        self.assertIn('\\"', s)                # 双引号被转义


class RosterValidationTests(unittest.TestCase):
    """新手最常踩的数据坑必须在构建前被明确拒绝（而不是产出坏星图）。"""

    HEADER = ("编号,昵称,军衔,工位,毛色,特征描述,代表照片文件,照片数量,"
              "出没区域,关联照片编号,置信度,备注\n")

    def _pkg(self, td: Path, roster_rows: str,
             override: list | None = None) -> Path:
        t = td / "pkg"
        (t / "data").mkdir(parents=True)
        (t / "data" / "猫咪名册.csv").write_text(self.HEADER + roster_rows,
                                                 encoding="utf-8")
        shutil.copytree(REPO / "schools" / "示例校" / "photos", t / "photos")
        (t / "data" / "build_meta.json").write_text(json.dumps({
            "school": "校验测试校", "product": "校验测试校喵星图",
            "en": "CHECK CAT GALAXY", "ls_prefix": "check"}), encoding="utf-8")
        if override is not None:
            (t / "data" / "cats_override.json").write_text(
                json.dumps(override, ensure_ascii=False), encoding="utf-8")
        return t

    def _row(self, cid: str, name: str, photo: str = "demo-cat-001.jpg") -> str:
        # 两猫共用同一占位照（构建允许），只关心名册校验
        return (f'{cid},{name},列兵,站岗,橘白,贪吃,{photo},1,'
                f'东区,,高,\n')

    def test_duplicate_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = self._pkg(Path(td),
                          self._row("CAT-001", "阿橘") + self._row("CAT-001", "小黑"))
            r = run_build("--pkg", str(t), "--out", str(Path(td) / "out"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("重复", r.stderr + r.stdout)

    def test_empty_id_rejected_with_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = self._pkg(Path(td),
                          self._row("CAT-001", "阿橘") +
                          self._row("", "没有编号的猫"))
            r = run_build("--pkg", str(t), "--out", str(Path(td) / "out"))
            self.assertNotEqual(r.returncode, 0)
            msg = r.stderr + r.stdout
            self.assertIn("编号", msg)
            self.assertIn("3", msg)          # CSV 第 3 行（含表头）

    def test_empty_name_rejected_with_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = self._pkg(Path(td),
                          self._row("CAT-001", "阿橘") +
                          self._row("CAT-002", " "))
            r = run_build("--pkg", str(t), "--out", str(Path(td) / "out"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("昵称", r.stderr + r.stdout)

    def test_override_duplicate_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = self._pkg(Path(td),
                          self._row("CAT-001", "阿橘") +
                          self._row("CAT-002", "小黑"),
                          override=[
                              {"id": "CAT-009", "name": "阿橘", "rank": "",
                               "title": "", "coat": "", "coatGroup": "",
                               "features": "", "area": "东区", "bio": "",
                               "photo": "demo-cat-001.jpg", "photoCount": 1,
                               "brightness": .5},
                              {"id": "CAT-009", "name": "小黑", "rank": "",
                               "title": "", "coat": "", "coatGroup": "",
                               "features": "", "area": "东区", "bio": "",
                               "photo": "demo-cat-002.jpg", "photoCount": 1,
                               "brightness": .5},
                          ])
            r = run_build("--pkg", str(t), "--out", str(Path(td) / "out"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("重复", r.stderr + r.stdout)

    def test_photos_dir_missing_rejected_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = self._pkg(Path(td), self._row("CAT-001", "阿橘"))
            shutil.rmtree(t / "photos")
            r = run_build("--pkg", str(t), "--out", str(Path(td) / "out"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("照片目录", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
