#!/usr/bin/env python3
"""T6 F7 · vendor 快照锁定门禁。

tools/starmap_render.py 是从喵星图工厂 catgalaxy-factory 反向 vendor 的
**唯一渲染真相**（基线：feat/v29-template `8284332`，v1.1.0）。本测试锁定
快照内容：要升级渲染层，就走「改工厂 → 更新快照 → 改这里的钉定哈希与基线
标注」的显式流程，不许在快照文件里悄悄改字节——那会让三仓渲染真相重新分叉。

运行：python -m unittest tests.test_vendor_snapshot
"""
import hashlib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENDOR = REPO / "tools" / "starmap_render.py"

# 与文件头「vendor 基线」标注绑定；升基线时两处一起改
PINNED_SHA256 = "a52ef84290d0f6b2ec96e6f1911d668e5ed9daa1a3349921ab4ce1fd2d79d212"
FACTORY_REF = "feat/v29-template 8284332 (v1.1.0)"


class VendorSnapshotLockTests(unittest.TestCase):
    def test_snapshot_matches_pinned_baseline(self) -> None:
        data = VENDOR.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(
            digest, PINNED_SHA256,
            f"{VENDOR.name} 内容与钉定基线不一致——渲染真相被改动。"
            f"若是刻意升级：先改工厂上游，再同步快照并更新本测试的 "
            f"PINNED_SHA256 与文件头基线标注（当前 {FACTORY_REF}）。")

    def test_header_carries_factory_provenance(self) -> None:
        head = VENDOR.read_text(encoding="utf-8")[:600]
        self.assertIn("catgalaxy-factory", head, "缺上游仓库来源标注")
        self.assertIn("vendor", head.lower(), "缺 vendor 基线标注")


if __name__ == "__main__":
    unittest.main()
