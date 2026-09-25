#!/usr/bin/env python3
"""手绘日间图 → 夜空 web 底图（v34 产线，确定性、原比例）。

做法固化自 19_全库深扫报告_20260918/手绘底图-接入预览图.py 的 night_native()：
官方日间图（09_地图底图/学校地图.png，不可再生只读）对官方夜空图
（docs/maps/官方底图-夜空版-web-参考.jpg，自 nuc/map 旧底图留档）逐通道
线性拟合（night ≈ a*day + b，逐通道 lstsq），再把手绘日间图缩到长边
MAX_MAP_SIDE 后按系数转夜空色。同输入两次运行产出逐字节相同。

为什么保持原比例：手绘原图 w/h=1.7128，官方图 1.5489；旧 _finalize_maps.py
把 1.7128 硬 resize 进 (1600,1033)=1.5489 等于纵向拉伸 10.6%（已知缺陷）。
模板按真实长宽比绘制（工厂 app/main.py:_map_size 注释明示），底图不需要
凑官方比例。MAX_MAP_SIDE=1920 ⇒ build.py 原字节嵌入，不再二次压损。

断言（不满足即非零退出）：输出长边==MAX_MAP_SIDE；w/h 与源图差 <0.002；
字节数 <300,000。

用法：
  uv run --python 3.12 --with pillow --with numpy python tools/make_hand_night_map.py
  uv run --python 3.12 --with pillow --with numpy python tools/make_hand_night_map.py \
      --out docs/maps/手绘版-夜空-v2.jpg     # 阶段 4：素材版重出（修 10.6% 拉伸）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
KU = REPO.parent
DAY_HAND = REPO / "docs/maps/手绘版-日间-全分辨率-v2.jpg"
OFFICIAL_DAY = KU / "09_地图底图/学校地图.png"
OFFICIAL_NIGHT_REF = REPO / "docs/maps/官方底图-夜空版-web-参考.jpg"
DEFAULT_OUT = REPO / "schools/nuc/map/手绘版-夜空-web.jpg"

MAX_MAP_SIDE = 1920      # 与 build.py 同名常量同值：长边 1920 ⇒ 原字节嵌入
QUALITY = 78
MAX_BYTES = 300_000


def fit_channel_coefs() -> list[tuple[float, float]]:
    """官方日间图 → 官方夜空图 的逐通道线性系数（同尺寸下逐像素 lstsq）。"""
    night = np.asarray(Image.open(OFFICIAL_NIGHT_REF).convert("RGB"),
                       dtype=np.float64)
    nh, nw = night.shape[:2]
    day = np.asarray(Image.open(OFFICIAL_DAY).convert("RGB")
                     .resize((nw, nh), Image.LANCZOS), dtype=np.float64)
    coefs = []
    for c in range(3):
        x = day[..., c].ravel()
        y = night[..., c].ravel()
        (a, b), *_ = np.linalg.lstsq(np.stack([x, np.ones_like(x)], 1), y,
                                     rcond=None)
        coefs.append((float(a), float(b)))
    return coefs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    out_path = args.out.resolve()

    for p in (DAY_HAND, OFFICIAL_DAY, OFFICIAL_NIGHT_REF):
        if not p.exists():
            print(f"缺输入：{p}", file=sys.stderr)
            return 2

    src = Image.open(DAY_HAND).convert("RGB")
    sw, sh = src.size
    long_side = max(sw, sh)
    if long_side >= MAX_MAP_SIDE:
        w, h = (MAX_MAP_SIDE, round(sh * MAX_MAP_SIDE / sw))
    else:                                # 源图不足 1920 时不放大，保原比例
        w, h = sw, sh
    canvas = src.resize((w, h), Image.LANCZOS)

    coefs = fit_channel_coefs()
    arr = np.asarray(canvas, dtype=np.float64)
    out = np.zeros_like(arr)
    for c in range(3):
        a, b = coefs[c]
        out[..., c] = arr[..., c] * a + b
    rendered = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(out_path, quality=QUALITY, optimize=True, progressive=True)

    # ---- 断言：形状、比例、体积（读回磁盘上的真实字节，不吃内存里的数） ----
    blob = out_path.read_bytes()
    with Image.open(out_path) as im:
        ow, oh = im.size
    problems = []
    if max(ow, oh) != MAX_MAP_SIDE:
        problems.append(f"输出长边 {max(ow, oh)} ≠ {MAX_MAP_SIDE}")
    src_ratio = sw / sh
    out_ratio = ow / oh
    if abs(out_ratio - src_ratio) >= 0.002:
        problems.append(f"宽高比漂移：输出 {out_ratio:.4f} vs 源 {src_ratio:.4f}"
                        f"（差 {abs(out_ratio - src_ratio):.4f} ≥ 0.002）")
    if len(blob) >= MAX_BYTES:
        problems.append(f"字节数 {len(blob)} ≥ {MAX_BYTES}")
    if problems:
        for p_ in problems:
            print(f"✗ {p_}", file=sys.stderr)
        return 1
    print(f"✓ {out_path.relative_to(REPO)}  {ow}x{oh}"
          f"（比例 {out_ratio:.4f}，源 {src_ratio:.4f}）  {len(blob):,} B"
          f"  逐通道系数 {[(round(a, 4), round(b, 1)) for a, b in coefs]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
