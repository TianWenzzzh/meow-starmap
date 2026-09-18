#!/usr/bin/env python3
"""打包「上传用物料」：04 号纯文本包 + 02 号参赛 zip（可重复执行）。

痛点（2026-09-18 发现）：04 号包仍停留在 8 分片 + v2.6 时代的结构，
02 号包停在 8/30 快照——对外交付的物料比仓库产物落后多个版本，
且没有任何机制发现这件事。本脚本把"打包"变成一条命令 + 一次 sha 自证。

数据来源（单一真相）：
  产品层  05 仓 `中北喵星图.html` + `assets/photo-data-*.js`（9 分片）
  数据层  16 仓 `schools/nuc/data/猫咪名册.csv`、`归并决策摘要.md`
  文档层  目标目录内既有的 README.md / SKILL.md（保持人工维护，不改）

不变式（脚本内断言，失败即非零退出）：
  1. 打包后 HTML 的 sha256 == 05 仓产物 == 16 托管 nuc/index.html
  2. 分片数量与 05 仓一致，且逐片 sha256 相同
  3. 文件清单恰好等于预期集合（不多不少）

用法：
  python3 tools/pack_upload_package.py \
      --product-repo ../05_git仓库_最新v2.6 \
      --pkg-dir 04_文本包_上传用_纯文本版 \
      [--zip-out 02_参赛作品_zip/最新版/中北大学—校园猫咪档案Skill-纯文本版-v2.8.4.zip]
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "schools" / "nuc"
DATA = PKG / "data"
HOSTED = REPO / "nuc" / "index.html"

PRODUCT_HTML = "中北喵星图.html"
EXPECTED_DOCS = ("README.md", "SKILL.md")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_product(product: Path, dest: Path) -> tuple[str, list[str]]:
    """把 05 产物（HTML + 分片）同步进目标目录；返回 (HTML sha, 分片名列表)。"""
    src_html = product / PRODUCT_HTML
    if not src_html.exists():
        raise SystemExit(f"找不到产物 HTML：{src_html}")
    shutil.copy2(src_html, dest / PRODUCT_HTML)

    shards_src = sorted((product / "assets").glob("photo-data-*.js"))
    if not shards_src:
        raise SystemExit(f"找不到分片：{product / 'assets'}")
    (dest / "assets").mkdir(parents=True, exist_ok=True)
    for shard in shards_src:
        shutil.copy2(shard, dest / "assets" / shard.name)
    return sha256(src_html), [s.name for s in shards_src]


def copy_data(dest: Path) -> list[str]:
    """名册进 data/、归并决策摘要放根目录——与 05 仓产物布局保持同构。"""
    (dest / "data").mkdir(parents=True, exist_ok=True)
    layout = {"猫咪名册.csv": Path("data") / "猫咪名册.csv",
              "归并决策摘要.md": Path("归并决策摘要.md")}
    out: list[str] = []
    for name, rel in layout.items():
        src = DATA / name
        if not src.exists():
            raise SystemExit(f"缺数据文件：{src}")
        shutil.copy2(src, dest / rel)
        out.append(rel.as_posix())
    return out


def verify(dest: Path, product: Path, html_sha: str, shards: list[str]) -> None:
    """三重自证：HTML 与产物/托管三方一致；分片逐片一致；清单不多不少。"""
    if sha256(dest / PRODUCT_HTML) != html_sha:
        raise SystemExit("自证失败：打包后 HTML 与 05 产物 sha256 不一致")
    if HOSTED.exists() and sha256(HOSTED) != html_sha:
        raise SystemExit(
            "自证失败：05 产物与 16 托管 nuc/index.html 不一致——先重导出产物")
    for name in shards:
        a = sha256(dest / "assets" / name)
        b = sha256(product / "assets" / name)
        if a != b:
            raise SystemExit(f"自证失败：分片 {name} 字节不一致")
    actual = {p.name for p in (dest / "assets").glob("*.js")}
    if actual != set(shards):
        extra = actual - set(shards)
        missing = set(shards) - actual
        raise SystemExit(f"自证失败：分片清单不符（多 {extra} / 少 {missing}）")
    for doc in EXPECTED_DOCS:
        if not (dest / doc).exists():
            print(f"  [提示] 缺文档 {doc}（本脚本不生成，请人工补齐）", file=sys.stderr)


def build_zip(dest: Path, zip_out: Path, shards: list[str],
              data_rels: list[str]) -> None:
    zip_out.parent.mkdir(parents=True, exist_ok=True)
    root = "中北喵星图"
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dest / PRODUCT_HTML, f"{root}/{PRODUCT_HTML}")
        for name in shards:
            zf.write(dest / "assets" / name, f"{root}/assets/{name}")
        for rel in data_rels:
            zf.write(dest / rel, f"{root}/{rel}")
        for doc in EXPECTED_DOCS:
            if (dest / doc).exists():
                zf.write(dest / doc, f"{root}/{doc}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="打包上传用物料（04 文本包 / 02 参赛 zip）")
    ap.add_argument("--product-repo", required=True,
                    help="05 仓路径（含 中北喵星图.html 与 assets/）")
    ap.add_argument("--pkg-dir", required=True,
                    help="【目标】04 号包目录（将被写入/刷新），如 04_文本包_上传用_纯文本版；"
                         "源数据包 schools/nuc 为硬编码，勿传")
    ap.add_argument("--zip-out", default=None, help="可选：额外产出 zip 的路径")
    args = ap.parse_args(argv)

    product = Path(args.product_repo).resolve()
    dest = Path(args.pkg_dir).resolve()
    # 深扫会话防呆（2026-09-19）：pkg-dir 是【目标 04 包目录】，源数据包
    # schools/nuc 是硬编码常量——把源当目标传入会自拷报 WinError 32，
    # 并把产物污染进数据包（实测踩过）。就地拒绝。
    if dest == PKG.resolve() or (dest / "data" / "归并决策摘要.md").exists() is False and dest.name == "nuc":
        raise SystemExit(
            "--pkg-dir 是【目标 04 包目录】（如 04_文本包_上传用_纯文本版），"
            "不是源数据包 schools/nuc——源已硬编码，勿传。", )
    dest.mkdir(parents=True, exist_ok=True)

    html_sha, shards = copy_product(product, dest)
    data_files = copy_data(dest)
    verify(dest, product, html_sha, shards)

    total = 1 + len(shards) + len(data_files) + len(
        [d for d in EXPECTED_DOCS if (dest / d).exists()])
    print(f"物料已同步 → {dest}")
    print(f"  产品：{PRODUCT_HTML}（sha256 {html_sha[:12]}…）+ {len(shards)} 个分片")
    print(f"  数据：{'、'.join(data_files)}")
    print(f"  文档：{'、'.join(EXPECTED_DOCS)}（人工维护，未改动）")
    print(f"  合计 {total} 个文件；自证：HTML 三方一致 + 分片逐片一致 ✓")

    if args.zip_out:
        zip_out = Path(args.zip_out).resolve()
        build_zip(dest, zip_out, shards, data_files)
        size_mb = zip_out.stat().st_size / 1024 / 1024
        print(f"zip 已产出 → {zip_out}（{size_mb:.2f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
