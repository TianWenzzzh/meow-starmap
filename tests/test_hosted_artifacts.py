#!/usr/bin/env python3
"""托管产物漂移门禁。

仓库根的 nuc/ 与 demo/ 是 GitHub Pages 上的在线体验产物（构建生成物，
见 docs/PR指南.md §7）。模板或 schools/ 数据一旦更新而忘记重建，本测试
在 CI 立即变红：现场构建产物必须与入库托管文件**逐字节**相同。

运行：python3 -m unittest tests.test_hosted_artifacts -v
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# (数据包目录, 托管目录, 构建出的 HTML 文件名)
HOSTED = [
    ("schools/nuc", "nuc", "中北喵星图.html"),
    ("schools/示例校", "demo", "示例校喵星图.html"),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HostedArtifactDriftTests(unittest.TestCase):
    def _check_one(self, pkg: str, hosted: str, html_name: str) -> None:
        with tempfile.TemporaryDirectory(prefix="hosted-drift-") as td:
            out = Path(td)
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "build.py"),
                 "--pkg", str(REPO / pkg), "--out", str(out)],
                capture_output=True, text=True, cwd=str(REPO))
            self.assertEqual(proc.returncode, 0,
                             f"构建 {pkg} 失败：\n{proc.stderr[-800:]}")

            hosted_dir = REPO / hosted

            # 1) HTML 逐字节相同（产物重命名为 index.html）
            built_html = out / html_name
            self.assertTrue(built_html.exists(),
                            f"构建缺少 {html_name}（产物名是否改了？）")
            self.assertEqual(
                _sha(built_html), _sha(hosted_dir / "index.html"),
                f"{hosted}/index.html 与现场构建不一致——"
                f"按 docs/PR指南.md §7 重建托管产物")

            # 2) 照片分片集合与字节逐一相同
            built_js = {p.name: p for p in (out / "assets").glob("*.js")}
            hosted_js = {p.name: p
                         for p in (hosted_dir / "assets").glob("*.js")}
            self.assertEqual(set(built_js), set(hosted_js),
                             f"{hosted}/assets 分片清单漂移（忘拷/多拷）")
            for name in built_js:
                self.assertEqual(
                    _sha(built_js[name]), _sha(hosted_js[name]),
                    f"{hosted}/assets/{name} 字节漂移")

            # 3) 托管目录不得混入其它文件（只允许 index.html + assets/*.js）
            allowed = {"index.html"} | {f"assets/{n}" for n in hosted_js}
            actual = {str(p.relative_to(hosted_dir))
                      for p in hosted_dir.rglob("*") if p.is_file()}
            self.assertEqual(actual - allowed, set(),
                             f"{hosted}/ 存在非构建产物文件：{actual - allowed}")

    def test_nuc_hosted_fresh(self) -> None:
        self._check_one(*HOSTED[0])

    def test_demo_hosted_fresh(self) -> None:
        self._check_one(*HOSTED[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
