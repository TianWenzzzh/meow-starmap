"""重新生成「离线整包」zip（02 号物料里的 中北大学-校园猫咪星图-离线包-vX.zip）。

为什么单独一个脚本：`pack_upload_package.py --zip-out` 的布局就是这个离线包，
但它有两处在发版时会咬人——
① README/SKILL 只从目标 04 目录取，**缺了只往 stderr 打一行提示、照样出 zip**；
② 文件名里的版本号全靠人手工敲，没有「包名 == 05 tag == 产物内版本串」的断言。
本脚本把这两条变成硬失败，并做确定性打包（同输入两次跑出的 zip 字节相同）。

跑法（在 16 仓根目录）：
  uv run --python 3.12 python tools/pack_offline_package.py --dry-run   # 只写临时盘 + 与现役包对照
  uv run --python 3.12 python tools/pack_offline_package.py            # 正式产出到 02 号物料
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]                  # 16 仓
KU = REPO.parent
PRODUCT = KU / "05_git仓库_最新v2.6"
META = REPO / "schools/nuc/data/build_meta.json"
STAGING = KU / "02_参赛作品_zip/最新版"
ROOT_IN_ZIP = "中北喵星图"
DOCS = ("README.md", "SKILL.md")                            # 与 05 仓根同名文件
EXPECTED_ENTRIES = 14


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def latest_tag(repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), "describe", "--tags", "--abbrev=0"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"读不到 {repo.name} 的最新 tag：{r.stderr.strip()}")
    return r.stdout.strip()


def sources() -> list[tuple[str, Path]]:
    """返回 (包内相对路径, 源文件)；顺序即写入顺序，必须稳定。"""
    html = PRODUCT / "中北喵星图.html"
    shards = sorted((PRODUCT / "assets").glob("photo-data-*.js"))
    items = [(html.name, html)] + [(f"assets/{s.name}", s) for s in shards]
    items += [("data/猫咪名册.csv", PRODUCT / "data/猫咪名册.csv"),
              ("归并决策摘要.md", PRODUCT / "归并决策摘要.md")]
    items += [(d, PRODUCT / d) for d in DOCS]
    missing = [rel for rel, p in items if not p.exists()]
    if missing:
        raise SystemExit(f"05 仓缺文件，无法打包：{missing}")
    return items


def build(items: list[tuple[str, Path]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    # date_time 固定 → 同一份输入两次打包字节一致，包本身可以比 sha
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, src in items:
            info = zipfile.ZipInfo(f"{ROOT_IN_ZIP}/{rel}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, src.read_bytes())


def check(out: Path, items: list[tuple[str, Path]], tag: str) -> None:
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        if len(names) != EXPECTED_ENTRIES:
            raise SystemExit(f"自证失败：包内 {len(names)} 条，应为 {EXPECTED_ENTRIES} 条")
        expect = {f"{ROOT_IN_ZIP}/{rel}" for rel, _ in items}
        if set(names) != expect:
            raise SystemExit(
                f"自证失败：清单不符 多={set(names)-expect} 少={expect-set(names)}")
        for rel, src in items:
            got = zf.read(f"{ROOT_IN_ZIP}/{rel}")
            if sha(got) != sha(src.read_bytes()):
                raise SystemExit(f"自证失败：{rel} 与源文件字节不一致")
        html = zf.read(f"{ROOT_IN_ZIP}/中北喵星图.html").decode("utf-8", "ignore")
    v = tag.lstrip("v")
    if v not in html:
        raise SystemExit(f"自证失败：产物 HTML 里找不到版本串 {v}（版本串不变式没落地）")
    if v not in out.name:
        raise SystemExit(f"自证失败：包名 {out.name} 里没有版本号 {v}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成离线整包 zip")
    ap.add_argument("--out", default=None, help=f"输出路径（默认 {STAGING}/…-v<tag>.zip）")
    ap.add_argument("--dry-run", action="store_true",
                    help="写到临时盘并打印与现役包的差异，不碰 02 号物料")
    args = ap.parse_args(argv)

    meta_version = re.search(r'"version":\s*"(v[\d.]+)"', META.read_text("utf-8"))
    if not meta_version:
        raise SystemExit(f"读不到 {META} 里的 version 字段")
    tag = latest_tag(PRODUCT)
    if meta_version.group(1) != tag:
        raise SystemExit(f"版本串不变式破了：build_meta.version={meta_version.group(1)} "
                         f"≠ 05 最新 tag={tag}（发版顺序未完成，先别打包）")

    items = sources()
    if args.dry_run:
        tmp = Path(tempfile.mkdtemp(prefix="offline_zip_"))
        out = tmp / f"中北大学-校园猫咪星图-离线包-{tag}.zip"
    else:
        out = Path(args.out) if args.out else \
            STAGING / f"中北大学-校园猫咪星图-离线包-{tag}.zip"
    build(items, out)
    check(out, items, tag)

    again = out.with_suffix(".again.zip")
    build(items, again)
    same = sha(out.read_bytes()) == sha(again.read_bytes())
    again.unlink()
    if not same:
        raise SystemExit("自证失败：同一份输入两次打包字节不同（确定性没做到）")

    cur = sorted(STAGING.glob("*离线包-*.zip"))
    print(f"✓ 离线包 {out.name}（{out.stat().st_size/1024/1024:.2f} MB，{EXPECTED_ENTRIES} 条，"
          f"逐条 sha 与源一致；两次打包字节相同={same}）")
    print(f"  版本三方对齐：包内版本串 == build_meta.version == 05 tag == {tag}")
    if cur and cur[-1] != out:
        newest = cur[-1]
        with zipfile.ZipFile(newest) as a, zipfile.ZipFile(out) as b:
            drift = [n.split("/", 1)[1] for n in a.namelist()
                     if n in b.namelist() and sha(a.read(n)) != sha(b.read(n))]
        print(f"  ⚠ 现役最新包是 {newest.name}，与新包内容不同的条目：{drift or '无'}")
    if args.dry_run:
        out.unlink()
        print("  （--dry-run：临时产物已删除，02 号物料未改动）")
    else:
        print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
