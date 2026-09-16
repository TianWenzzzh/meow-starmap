#!/usr/bin/env python3
"""把 05 正式版的内嵌资产与中北专属数据反解进 schools/nuc/ 数据包。

产出（CC BY-NC-SA 4.0，仅限中北数据包）：
  photos/                 75 张猫代表照（JPEG，原字节 base64 解码）
  map/                    1 张夜空底图
  data/猫咪名册.csv        12 列契约原件（拷自 05/data）
  data/归并决策摘要.md      拷自 05 仓库根
  data/cats_override.json  76 条人工富数据（bio 小传/features/coatGroup/brightness 真值）
  data/calib.json         54 个人工校准锚点（其余 22 只浏览器 basePos 兜底）
  data/areas.json 等       AREAS / AREA_KEYS / REL / CONST / POSTER_STARS 反解
  data/assets_manifest.json 每个反解文件的字节数 + sha256 + 数据口径

用法：python3 tools/extract_nuc_assets.py
"""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KU = Path(__import__("os").environ.get(
    "STARMAP_HOME", "/media/tianwen/KINGSTON/猫咪星图_总库"))
SRC_REPO = KU / "05_git仓库_最新v2.6"
OUT = REPO_ROOT / "schools" / "nuc"

PHOTO_LINE_RE = re.compile(
    r'__PHOTOS\["((?:[^"\\]|\\.)*)"\]="data:([^;]+);base64,([^"]*)";')


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def block(name: str) -> str:
    fx = json.loads((REPO_ROOT / "tests" / "fixtures" /
                     "nuc_literals.json").read_text("utf-8"))
    return next(r["old"] for r in fx["rules"] if r["name"] == name)


def js_str_fields(obj_text: str, keys: list[str]) -> dict:
    out: dict[str, str] = {}
    for k in keys:
        m = re.search(r'\b' + k + r':"((?:[^"\\]|\\.)*)"', obj_text, re.S)
        if not m:
            raise SystemExit(f"字段 {k} 未找到：{obj_text[:80]}")
        out[k] = m.group(1)
    return out


def decode_photos() -> dict[str, dict]:
    """8 个分片 → 76 个文件。返回 {键: {bytes, mime}}。"""
    assets: dict[str, dict] = {}
    for js in sorted((SRC_REPO / "assets").glob("photo-data-*.js")):
        for name, mime, b64 in PHOTO_LINE_RE.findall(js.read_text("utf-8")):
            if name in assets:
                raise SystemExit(f"照片键重复：{name}")
            raw = base64.b64decode(b64)
            assets[name] = {"bytes": raw, "mime": mime}
    if len(assets) != 76:
        raise SystemExit(f"反解键数应为 76，实际 {len(assets)}")
    return assets


def parse_cats() -> list[dict]:
    """CATS 块 → 76 条人工富数据（bio 等 CSV 无法推导的创作内容）。"""
    text = block("cats_block")
    entries = re.findall(
        r'\{ id:"CAT-.*?brightness:[\d.]+\s*\}', text, flags=re.S)
    if len(entries) != 76:
        raise SystemExit(f"CATS 切条 {len(entries)} ≠ 76")
    cats: list[dict] = []
    for e in entries:
        s = js_str_fields(e, ["id", "name", "rank", "title", "coat",
                              "coatGroup", "features", "area", "bio", "photo"])
        pc = re.search(r'photoCount:(\d+)', e)
        br = re.search(r'brightness:([\d.]+)', e)
        cats.append({
            **s,
            "photo": s["photo"].replace("assets/photos/", "").split("/")[-1],
            "photoCount": int(pc.group(1)),
            "brightness": float(br.group(1)),
        })
    return cats


def parse_calib() -> dict:
    out = {cid: {"x": float(x), "y": float(y)}
           for cid, x, y in re.findall(
               r'"(CAT-\d+)":\{x:([\d.]+),y:([\d.]+)\}', block("calib_block"))}
    if len(out) != 54:
        raise SystemExit(f"CALIB 键数 {len(out)} ≠ 54")
    return out


def parse_areas() -> list[dict]:
    return [{"x": float(x), "y": float(y), "t": t}
            for x, y, t in re.findall(
                r'\{x:([-\d.]+),y:([-\d.]+),t:"((?:[^"\\]|\\.)*)"\}',
                block("areas_block"))]


def parse_area_keys() -> list[list]:
    return [[k, int(i)] for k, i in
            re.findall(r'\["((?:[^"\\]|\\.)*)",(\d+)\]',
                       block("area_keys_block"))]


def parse_rel() -> list[dict]:
    return [{"a": a, "b": b, "label": label}
            for a, b, label in re.findall(
                r'\{ a:"(CAT-\d+)", b:"(CAT-\d+)", label:"((?:[^"\\]|\\.)*)" \}',
                block("rel_block"))]


def parse_const() -> list[dict]:
    return [{"n": n, "en": en, "s": s} for n, en, s in re.findall(
        r'\{n:"((?:[^"\\]|\\.)*)",en:"((?:[^"\\]|\\.)*)",'
        r's:"((?:[^"\\]|\\.)*)"\}', block("const_block"))]


def parse_poster_stars() -> list[list]:
    return [[cid, label] for cid, label in
            re.findall(r'\["(CAT-\d+)","((?:[^"\\]|\\.)*)"\]',
                       block("poster_stars"))]


def verify_csv(cats: list[dict], photo_keys: set[str]) -> None:
    rows = list(csv.DictReader(
        open(SRC_REPO / "data" / "猫咪名册.csv", encoding="utf-8-sig")))
    if len(rows) != 76:
        raise SystemExit(f"CSV 行数 {len(rows)} ≠ 76")
    csv_reps = {r["代表照片文件"].strip().replace("\\", "/").split("/")[-1]
                for r in rows}
    if csv_reps != photo_keys:
        raise SystemExit(
            f"CSV 代表照 basename 集与照片键不一致：\n"
            f"  仅 CSV：{sorted(csv_reps - photo_keys)}\n"
            f"  仅资产：{sorted(photo_keys - csv_reps)}")
    ids_csv = {r["编号"] for r in rows}
    ids_cats = {c["id"] for c in cats}
    if ids_csv != ids_cats:
        raise SystemExit(f"CSV 与 CATS 的 id 集不一致：{ids_csv ^ ids_cats}")


def main() -> int:
    photos_dir = OUT / "photos"
    map_dir = OUT / "map"
    data_dir = OUT / "data"
    photos_dir.mkdir(parents=True, exist_ok=True)
    map_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    assets = decode_photos()
    map_name = "校园地图-夜空版-web.jpg"
    if map_name not in assets:
        raise SystemExit("底图键缺失")

    manifest: dict = {"photos": {}, "map": None, "counts": {}}
    for name, item in assets.items():
        raw = item["bytes"]
        if not raw.startswith(b"\xff\xd8\xff"):
            raise SystemExit(f"非 JPEG：{name}")
        if name == map_name:
            (map_dir / name).write_bytes(raw)
            manifest["map"] = {"file": f"map/{name}", "bytes": len(raw),
                               "sha256": sha(raw), "mime": item["mime"]}
        else:
            (photos_dir / name).write_bytes(raw)
            manifest["photos"][name] = {"bytes": len(raw),
                                        "sha256": sha(raw)}
    photo_keys = set(assets) - {map_name}

    cats = parse_cats()
    verify_csv(cats, photo_keys)
    calib, areas = parse_calib(), parse_areas()
    area_keys, rel = parse_area_keys(), parse_rel()
    consts, stars = parse_const(), parse_poster_stars()

    payloads = {
        "cats_override.json": cats,
        "calib.json": calib,
        "areas.json": areas,
        "area_keys.json": area_keys,
        "relations.json": rel,
        "constellations.json": consts,
        "poster_stars.json": stars,
    }
    for fname, obj in payloads.items():
        (data_dir / fname).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    shutil.copy2(SRC_REPO / "data" / "猫咪名册.csv", data_dir / "猫咪名册.csv")
    shutil.copy2(SRC_REPO / "归并决策摘要.md", data_dir / "归并决策摘要.md")

    photocount_sum = sum(c["photoCount"] for c in cats)
    # 194 的口径来自归并摘要：基准 111 + 补充 83（普查总量，非内嵌数）
    fx = json.loads((REPO_ROOT / "tests" / "fixtures" /
                     "nuc_literals.json").read_text("utf-8"))
    survey_total = int(re.search(r"(\d+) 张学长学姐实拍",
                                 next(r["old"] for r in fx["rules"]
                                      if r["name"] == "stats_line")).group(1))
    manifest["counts"] = {
        "cats": len(cats),
        "photo_files_embedded": len(photo_keys),
        "map_files": 1,
        "photocount_sum": photocount_sum,
        "survey_photo_total": survey_total,
        "survey_photo_note": "普查实拍总量（基准111+补充83）；photoCount 合计"
                             "为归档计数；内嵌仅每猫1张代表照（1张被两猫共用）",
        "calib_manual": len(calib),
        "calib_basepos_fallback": len(cats) - len(calib),
        "areas": len(areas), "area_keys": len(area_keys),
        "relations": len(rel), "constellations": len(consts),
        "poster_stars": len(stars),
    }
    (data_dir / "assets_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    total = sum(p["bytes"] for p in manifest["photos"].values())
    print(f"猫照 {len(photo_keys)} 张 / 底图 1 张，合计 "
          f"{(total + manifest['map']['bytes']) / 1e6:.2f} MB")
    print(f"CATS {len(cats)} 条（photoCount 合计 {photocount_sum}），"
          f"CALIB {len(calib)} 键，AREAS {len(areas)}，"
          f"AREA_KEYS {len(area_keys)}，REL {len(rel)}，CONST {len(consts)}")
    print(f"CSV 代表照 basename 集合 == 照片键集合 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
