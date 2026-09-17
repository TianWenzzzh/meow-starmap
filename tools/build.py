#!/usr/bin/env python3
"""零门槛星图构建器：名册 CSV + 照片 + 底图 + v2.7 token 模板 → 离线单文件星图。

用法（仅依赖 Pillow）：
  # 学校数据包模式（推荐，约定目录布局）：
  uv run --with pillow tools/build.py --pkg schools/nuc --out dist/nuc
  uv run --with pillow tools/build.py --pkg schools/示例校 --out dist/demo
  # 散件模式：
  uv run --with pillow tools/build.py --school 示例校 \\
      --data roster.csv --photos photos/ --map map.jpg --out dist/demo
  # 照片懒加载（底图 00 关键片 eager，猫照片分片按交互取；需 v28+ 模板）：
  uv run --with pillow tools/build.py --pkg schools/nuc --out dist/nuc --photo-loading lazy
  # 强制旧整包（覆盖 build_meta 的 photo_loading，群文件/U 盘分发用）：
  uv run --with pillow tools/build.py --pkg schools/nuc --out dist/nuc --eager-photos

数据包目录约定：
  <pkg>/data/猫咪名册.csv        12 列名册（utf-8-sig）
  <pkg>/data/build_meta.json    可选：校名/副标题/里程碑等富参数
  <pkg>/data/cats_override.json 可选：人工小传等 CSV 无法推导的富数据
  <pkg>/data/calib.json         可选：人工校准星位（缺失则浏览器 basePos 兜底）
  <pkg>/data/areas.json 等       可选：星域/星宿/关系/海报推荐
  <pkg>/photos/*.jpg            代表照（文件名 = 名册“代表照片文件”列 basename）
  <pkg>/map/*.jpg               底图（一张；缺失时自动生成星野底图）

本文件 vendor 自喵星图工厂（MIT License, © TianWenzzzh,
https://github.com/TianWenzzzh/catgalaxy-factory v1.0.0）：
  app/injector.py 的 _js_str / _js / _chunk_plan / 分片外壳；
  app/image_proc.py 的长边缩放 + JPEG 质量二分（并补上 EXIF 旋转矫正）；
  app/csv_loader.py 的 12 列容错解析。
落位算法在同目录 starmap_layout.py（仅 --derive-calib 时使用）。
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import math
import random
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "template" / "starmap.html"

MAX_PHOTO_SIDE = 1200
MAX_PHOTO_BYTES = 200 * 1024
MAX_MAP_SIDE = 1920
CHUNK_BYTES = 1_500_000
ROSTER_COLUMNS = ["编号", "昵称", "军衔", "工位", "毛色", "特征描述",
                  "代表照片文件", "照片数量", "出没区域", "关联照片编号",
                  "置信度", "备注"]
ALIASES = {
    "编号": ("编号", "id", "ID", "cat_id", "序号"),
    "昵称": ("昵称", "名字", "name", "Name"),
    "军衔": ("军衔", "职级", "rank"),
    "工位": ("工位", "职务", "title", "岗位"),
    "毛色": ("毛色", "coat", "花色"),
    "特征描述": ("特征描述", "特征", "features"),
    "代表照片文件": ("代表照片文件", "代表照片", "photo", "照片文件"),
    "照片数量": ("照片数量", "照片数", "photoCount", "photo_count"),
    "出没区域": ("出没区域", "区域", "area", "出没地点"),
    "关联照片编号": ("关联照片编号", "关联照片", "related"),
    "置信度": ("置信度", "confidence", "可信度"),
    "备注": ("备注", "note", "说明"),
}

# ---------- 渲染（T6 F7 反向 vendor：上游真相 = 工厂 starmap_render） ----------
# 注入转义、JS 数据块渲染、分片规划全部收敛到 tools/starmap_render.py
# （vendor 自 catgalaxy-factory，见该文件头）；本文件只做数据装配与落盘。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from starmap_render import V29RenderInput, render  # noqa: E402


# ---------- CSV（vendor: app/csv_loader.py 简化，去 pydantic） ----------

@dataclass
class RosterCat:
    line: int = 0
    id: str = ""
    name: str = ""
    rank: str = ""
    title: str = ""
    coat: str = ""
    features: str = ""
    photo_file: str = ""
    photo_count: int = 0
    area: str = ""
    related: str = ""
    confidence: str = ""
    note: str = ""


def parse_roster(text: str):
    reader = csv.reader(io.StringIO(text))
    raw = [r for r in reader]
    if not raw:
        raise SystemExit("名册 CSV 为空")
    header = [c.strip().lstrip("﻿") for c in raw[0]]
    norm = [(h or "").strip().lstrip("﻿") for h in header]
    col: dict[str, int] = {}
    for std, alts in ALIASES.items():
        for idx, h in enumerate(norm):
            if h in alts and std not in col:
                col[std] = idx
                break
    missing = [c for c in ROSTER_COLUMNS if c not in col]
    if missing:
        raise SystemExit(f"名册缺少必需列：{missing}（实际表头：{header}）")

    def cell(row, name):
        idx = col[name]
        return (row[idx] if idx < len(row) else "").strip()

    rows = []
    for i, line in enumerate(raw[1:], start=2):
        if not any((c or "").strip() for c in line):
            continue
        m = re.search(r"\d+", cell(line, "照片数量"))
        rows.append(RosterCat(
            line=i, id=cell(line, "编号"), name=cell(line, "昵称"),
            rank=cell(line, "军衔"), title=cell(line, "工位"),
            coat=cell(line, "毛色"), features=cell(line, "特征描述"),
            photo_file=cell(line, "代表照片文件"),
            photo_count=int(m.group()) if m else 0,
            area=cell(line, "出没区域"), related=cell(line, "关联照片编号"),
            confidence=cell(line, "置信度"), note=cell(line, "备注")))
    if not rows:
        raise SystemExit("名册没有数据行")
    return rows


# ---------- 图片（vendor: app/image_proc.py 策略 + EXIF 矫正） ----------

def _fit_bytes(img: Image.Image, max_bytes: int):
    """质量二分：找到 ≤max_bytes 的最高质量。"""
    lo, hi, best, best_q = 25, 88, None, 0
    while lo <= hi:
        q = (lo + hi) // 2
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            best, best_q = buf.getvalue(), q
            lo = q + 1
        else:
            hi = q - 1
    return best, best_q


def prepare_jpeg(path: Path, max_side: int, max_bytes: int | None):
    """EXIF 矫正 → 长边压缩 → JPEG。

    保真优先（与 v2.7 实测产物对齐：75 张里 11 张为 207–387KB、长边 1100，
    内嵌渲染正常）：长边合格、无需旋转的 JPEG 一律原字节嵌入，不做二次压损；
    仅在长边超限、非 JPEG 格式或 EXIF 方向需要矫正时重编码。
    ``max_bytes`` 只在“必须重编码”时作为质量二分目标（新学校大图走这条）。
    """
    raw = path.read_bytes()
    img = Image.open(io.BytesIO(raw))
    fixed = ImageOps.exif_transpose(img)
    w0, h0 = img.size
    w, h = fixed.size
    rotated = (w, h) != (w0, h0)
    long_side = max(w, h)
    is_jpeg = path.suffix.lower() in (".jpg", ".jpeg")
    if not rotated and long_side <= max_side and is_jpeg:
        return raw, False
    if long_side > max_side:
        scale = max_side / float(long_side)
        fixed = fixed.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                             Image.LANCZOS)
    fixed = fixed.convert("RGB")
    if max_bytes is not None:
        out, _q = _fit_bytes(fixed, max_bytes)
        if out is None:
            buf = io.BytesIO()
            fixed.save(buf, "JPEG", quality=30, optimize=True,
                       progressive=True)
            out = buf.getvalue()
    else:
        buf = io.BytesIO()
        fixed.save(buf, "JPEG", quality=86, optimize=True, progressive=True)
        out = buf.getvalue()
    return out, True


# vendor: app/image_proc.py generate_default_map（MIT，© TianWenzzzh/catgalaxy-factory）
def generate_default_map(dest: Path, width: int = MAX_MAP_SIDE,
                         height: int = 1239, seed: int = 20260906) -> Path:
    """生成深空星野底图（渐变+星云+星点+淡网格），保证零素材也能出成品。"""
    rng = random.Random(seed)
    col = Image.new("RGB", (1, height))                     # 1px 列再横向拉伸
    for y in range(height):
        t = y / height
        col.putpixel((0, y), (int(7 + 9 * (1 - t)), int(12 + 12 * (1 - t)),
                              int(28 + 26 * (1 - t))))
    img = col.resize((width, height))

    neb = Image.new("RGB", (width, height), (0, 0, 0))
    nd = ImageDraw.Draw(neb)
    for _ in range(9):
        cx, cy = rng.randrange(width), rng.randrange(height)
        r = rng.randrange(180, 460)
        c = rng.choice([(70, 52, 20), (18, 52, 50), (44, 26, 62)])
        nd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    neb = neb.filter(ImageFilter.GaussianBlur(140))
    img = Image.blend(img, Image.eval(neb, lambda v: min(255, v + 8)), 0.34)

    d = ImageDraw.Draw(img)
    for _ in range(1500):
        x, y = rng.randrange(width), rng.randrange(height)
        b = rng.randint(40, 190)
        s = 1 if rng.random() > 0.9 else 0
        d.ellipse([x, y, x + s, y + s], fill=(b, b + 8, min(255, b + 24)))
    for gx in range(0, width, width // 12):               # 淡网格=校园区块感
        d.line([(gx, 0), (gx, height)], fill=(28, 40, 74), width=1)
    for gy in range(0, height, height // 8):
        d.line([(0, gy), (width, gy)], fill=(28, 40, 74), width=1)

    img.save(dest, "JPEG", quality=86, optimize=True)
    return dest


# ---------- JS 字面量渲染（v2.7 风格：去前导零的紧凑数字） ----------

def js_num(v) -> str:
    """0.5→.5、0.61→.61、1.05→1.05（与 v2.7 的 JS 数字风格一致）。"""
    s = str(round(float(v), 2))
    return s[1:] if s.startswith("0.") else s


def js_num3(v) -> str:
    s = f"{float(v):.3f}".rstrip("0").rstrip(".")
    return s[1:] if s.startswith("0.") else s


def render_cats(cats: list[dict]) -> str:
    out = ["const CATS = ["]
    for i, c in enumerate(cats):
        tail = " " if i == len(cats) - 1 else ","
        out.append(
            f'  {{ id:"{js_str(c["id"])}", name:"{js_str(c["name"])}", '
            f'rank:"{js_str(c["rank"])}", title:"{js_str(c["title"])}", '
            f'coat:"{js_str(c["coat"])}", coatGroup:"{js_str(c["coatGroup"])}",\n'
            f'    features:"{js_str(c["features"])}", area:"{js_str(c["area"])}", '
            f'bio:"{js_str(c["bio"])}",\n'
            f'    photo:"{js_str("assets/photos/" + c["photo"])}", '
            f'photoCount:{int(c["photoCount"])}, '
            f'brightness:{js_num(c["brightness"])}}}' + tail)
    out.append("];")
    return "\n".join(out)


def render_calib(calib: dict) -> str:
    if not calib:
        return "const CALIB={};"
    items = list(calib.items())
    lines = ["const CALIB={"]
    for i in range(0, len(items), 4):
        row = ",".join(
            f'"{js_str(cid)}":{{x:{js_num3(p["x"])},y:{js_num3(p["y"])}}}'
            for cid, p in items[i:i + 4])
        lines.append("  " + row + ("," if i + 4 < len(items) else ""))
    lines.append("};")
    return "\n".join(lines)


def render_areas(areas: list[dict]) -> str:
    if not areas:
        return "const AREAS=[];"
    lines = ["const AREAS=["]
    for i in range(0, len(areas), 3):
        row = "".join(
            f'{{x:{js_num3(a["x"])},y:{js_num3(a["y"])},'
            f't:"{js_str(a["t"])}"}}' + ("," if not (
                i + 3 >= len(areas) and j == len(areas[i:i + 3]) - 1) else "")
            for j, a in enumerate(areas[i:i + 3]))
        lines.append("  " + row)
    lines.append("];")
    return "\n".join(lines)


def render_area_keys(keys: list[list]) -> str:
    if not keys:
        return "const AREA_KEYS=[];"
    lines = ["const AREA_KEYS=["]
    for i in range(0, len(keys), 6):
        row = ",".join(f'["{js_str(k)}",{int(idx)}]' for k, idx in keys[i:i + 6])
        lines.append("  " + row + ("," if i + 6 < len(keys) else ""))
    lines.append("];")
    return "\n".join(lines)


def render_rel(rel: list[dict]) -> str:
    if not rel:
        return "const REL=[];"
    lines = ["const REL=["]
    for i, r in enumerate(rel):
        lines.append(
            f'  {{ a:"{js_str(r["a"])}", b:"{js_str(r["b"])}", '
            f'label:"{js_str(r["label"])}" }}'
            + ("," if i < len(rel) - 1 else ""))
    lines.append("];")
    return "\n".join(lines)


def render_const(consts: list[dict]) -> str:
    if not consts:
        return "const CONST=[];"
    lines = ["const CONST=["]
    for i, c in enumerate(consts):
        lines.append(
            f' {{n:"{js_str(c["n"])}",en:"{js_str(c["en"])}",'
            f's:"{js_str(c["s"])}"}}' + ("," if i < len(consts) - 1 else ""))
    lines.append("];")
    return "\n".join(lines)


def render_poster_stars(stars: list[list]) -> str:
    return "const stars=" + js(stars) + ";"


# ---------- 数据装配 ----------

def cats_from_csv(rows: list[RosterCat]) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from starmap_layout import (brightness_from_count, classify_coat,
                                join_features, make_bio, normalize_area,
                                normalize_id)
    cats = []
    for r in rows:
        cid = normalize_id(r.id) or r.id
        fname = r.photo_file.replace("\\", "/").split("/")[-1]
        cats.append({
            "id": cid, "name": r.name, "rank": r.rank, "title": r.title,
            "coat": r.coat, "coatGroup": classify_coat(r.coat),
            "features": join_features(r.features),
            "area": normalize_area(r.area), "bio": make_bio(r),
            "photo": fname, "photoCount": max(1, r.photo_count),
            "brightness": brightness_from_count(r.photo_count)})
    return cats


def validate_roster(rows: list[RosterCat]) -> None:
    """行级硬校验：空编号/空昵称必须带行号报错（新手最高频的表格坑）。"""
    problems = []
    for r in rows:
        if not str(r.id).strip():
            problems.append(f"第 {r.line} 行：编号为空")
        if not str(r.name).strip():
            problems.append(f"第 {r.line} 行：昵称为空")
    if problems:
        raise SystemExit("名册存在空字段（每只猫都必须有编号和昵称）：\n  "
                         + "\n  ".join(problems[:10]))


def validate_cats_unique(cats: list[dict], source: str) -> None:
    """猫 ID 是星图全系统主键（CALIB/影廊/海报/搜索都按它索引），
    重复 ID 必须在构建期拒绝，而不是产出静默串档的坏星图。"""
    seen: dict[str, list[int]] = {}
    for i, c in enumerate(cats, start=1):
        cid = str(c.get("id", "")).strip()
        seen.setdefault(cid, []).append(i)
    dups = {cid: ps for cid, ps in seen.items() if len(ps) > 1}
    if dups:
        detail = "；".join(
            f"{cid} 出现 {len(ps)} 次（{source}第 {'、'.join(map(str, ps))} 条）"
            for cid, ps in dups.items())
        raise SystemExit(f"{source}猫编号重复，请先在数据里去重：{detail}")


def derive_areas(rows: list[RosterCat]) -> list[dict]:
    from starmap_layout import assign_anchors, normalize_area
    uniq = []
    for r in rows:
        a = normalize_area(r.area)
        if a and a not in uniq:
            uniq.append(a)
    anchors = assign_anchors(uniq)
    return [{"x": anchors[a][0], "y": anchors[a][1], "t": a} for a in uniq]


def derive_const(areas: list[dict], counts: dict[str, int]) -> list[dict]:
    out = []
    for i, a in enumerate(areas):
        t = a["t"]
        out.append({
            "n": (t[:6] + "座") if len(t) > 6 else t + "座",
            "en": f"STAR {i + 1}",
            "s": f"{t}是它们常来常往的地盘，{counts.get(t, 0)} 颗星在此落脚。"
                 f"路过时放慢脚步，也许就能撞见一颗会打呼的星。"})
    return out


def derive_poster_stars(cats: list[dict]) -> list[list]:
    top = sorted(cats, key=lambda c: -int(c["photoCount"]))[:4]
    return [[c["id"], f'{c["name"]} · {c["area"]}'] for c in top]


def milestones_for(n: int) -> list[int]:
    if n <= 3:
        return [n]
    ms = [math.ceil(n / 4), math.ceil(n / 2), math.ceil(3 * n / 4), n]
    return sorted(set(ms))


def pass_titles_for(ms: list[int]) -> list[list]:
    names = ["猫门常客", "校园通", "猫学长认证"]
    titles = [[0, "初来乍到"]]
    for i, m in enumerate(ms[:-1]):
        titles.append([m, names[min(i, len(names) - 1)]])
    titles.append([ms[-1], "喵星传奇"])
    return titles


# ---------- 主流程 ----------

SAFE_RE = re.compile(r'^[\w\u4e00-\u9fff ··—\-，。！？：；、（）()【】「」✅🐱🏆🎉◈｜/\.]+$')
URL_RE = re.compile(r"^https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")


def check_safe(name: str, value: str) -> str:
    value = str(value or "").strip()
    if not value or not SAFE_RE.match(value):
        raise SystemExit(f"参数 {name} 含不被允许的字符（防注入白名单）：{value!r}")
    return value


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return default


def main() -> int:
    ap = argparse.ArgumentParser(description="CSV+照片+模板 → 离线喵星图")
    ap.add_argument("--pkg", help="学校数据包目录（约定布局，最简用法）")
    ap.add_argument("--school")
    ap.add_argument("--data", help="名册 CSV")
    ap.add_argument("--photos", help="照片目录")
    ap.add_argument("--map", help="底图文件")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--product")
    ap.add_argument("--en")
    ap.add_argument("--version")
    ap.add_argument("--tagline")
    ap.add_argument("--survey-date")
    ap.add_argument("--ls-prefix")
    ap.add_argument("--repo-url")
    ap.add_argument("--docs-ref")
    ap.add_argument("--photo-count", type=int,
                    help="普查照片总量文案（缺省=名册照片数合计）")
    ap.add_argument("--photo-loading", choices=["eager", "lazy"], default=None,
                    help="照片分片加载：eager=旧整包全量立即加载（缺省）；"
                         "lazy=仅底图关键片 eager，猫照片按交互动态取片")
    ap.add_argument("--eager-photos", action="store_true",
                    help="照片分片强制 eager（覆盖 build_meta 的 photo_loading）")
    ap.add_argument("--derive-calib", action="store_true",
                    help="用服务端落位算法预生成 CALIB（缺省留空，"
                         "浏览器 basePos 兜底）")
    args = ap.parse_args()

    pkg = Path(args.pkg) if args.pkg else None
    if pkg:
        csv_path = pkg / "data" / "猫咪名册.csv"
        photos_dir = pkg / "photos"
        map_dir = pkg / "map"
        maps = list(map_dir.glob("*.jp*g")) if map_dir.exists() else []
        if maps:
            map_path = maps[0]
        else:
            # 零素材兜底：自动生成星野底图放进数据包（幂等，下次运行直接复用）
            map_dir.mkdir(parents=True, exist_ok=True)
            map_path = map_dir / "自动生成星野底图.jpg"
            generate_default_map(map_path)
            print(f"· 未提供底图，已自动生成星野底图：{map_path}（可随时替换为校园实拍地图）")
        data_dir = pkg / "data"
    else:
        if not (args.school and args.data and args.photos and args.map):
            raise SystemExit("散件模式必须同时给 --school --data --photos --map")
        csv_path = Path(args.data)
        photos_dir = Path(args.photos)
        map_path = Path(args.map)
        data_dir = csv_path.parent

    meta = load_json(data_dir / "build_meta.json", {}) if data_dir else {}

    def opt(cli, key, default=None):
        return cli if cli is not None else meta.get(key, default)

    school = check_safe("school", opt(args.school, "school"))
    product = check_safe("product", opt(args.product, "product",
                                        school + "喵星图"))
    short = re.sub(r"(大学|学院|学校)$", "", school) or school
    en = check_safe("en", opt(args.en, "en", "CAMPUS CAT GALAXY"))
    version = check_safe("version", opt(args.version, "version", "v1.0"))
    survey_date = opt(args.survey_date, "survey_date",
                      date.today().strftime("%Y-%m"))
    check_safe("survey_date", survey_date)
    tagline = check_safe("tagline", opt(
        args.tagline, "tagline",
        f"{school}的喵星编制 · 每颗星都是一只真实生活的校园猫"))
    ls_prefix = opt(args.ls_prefix, "ls_prefix", "starmap")
    ls_prefix = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]", "-", ls_prefix)[:32]
    repo_url = opt(args.repo_url, "repo_url",
                   "https://github.com/TianWenzzzh/meow-starmap")
    if not URL_RE.match(repo_url):
        raise SystemExit(f"repo-url 非法：{repo_url}")
    repo_display = repo_url.replace("https://", "")
    docs_ref = opt(args.docs_ref, "docs_ref", "docs/快速上手.md")
    map_file = map_path.name
    if not re.match(r"^[0-9A-Za-z\u4e00-\u9fff_.\- ]+\.(jpe?g)$", map_file,
                    re.IGNORECASE):
        raise SystemExit(f"底图文件名不安全：{map_file}")

    # --- 名册 ---
    rows = parse_roster(csv_path.read_text("utf-8-sig"))
    validate_roster(rows)
    n = len(rows)
    override = load_json(data_dir / "cats_override.json", None) if data_dir else None
    if override is not None:
        if len(override) != n:
            raise SystemExit(
                f"cats_override.json 条数 {len(override)} ≠ 名册 {n} 行")
        validate_cats_unique(override, "cats_override.json ")
        cats = override
    else:
        cats = cats_from_csv(rows)
        validate_cats_unique(cats, "名册 ")
    photo_sum = sum(int(c["photoCount"]) for c in cats)
    p_total = opt(args.photo_count, "survey_photo_total", photo_sum)

    # 照片分片加载策略：CLI --photo-loading / --eager-photos 压过 build_meta；
    # v2.8 起缺省 lazy（底图关键片 eager + 猫照片按需取）；--eager-photos 出旧整包。
    photo_loading = args.photo_loading or meta.get("photo_loading")
    if args.eager_photos:
        photo_loading = "eager"
    photo_loading = photo_loading or "lazy"
    if photo_loading not in ("eager", "lazy"):
        raise SystemExit(
            f"photo_loading 非法：{photo_loading!r}（仅支持 eager/lazy）")

    # --- 照片：缺失严格报错；共用照只存一份 ---
    if not photos_dir.is_dir():
        raise SystemExit(f"照片目录不存在：{photos_dir}（数据包应含 photos/*.jpg）")
    need = {c["photo"] for c in cats}
    have = {p.name for p in photos_dir.glob("*.jp*g")}
    missing = sorted(need - have)
    if missing:
        raise SystemExit("名册引用的代表照在照片目录缺失：\n  "
                         + "\n  ".join(missing[:10])
                         + (f"\n  ……共 {len(missing)} 张" if len(missing) > 10 else ""))
    blobs: dict[str, bytes] = {}
    recompressed = 0
    for name in sorted(need):
        blob, changed = prepare_jpeg(photos_dir / name, MAX_PHOTO_SIDE,
                                     MAX_PHOTO_BYTES)
        recompressed += int(changed)
        blobs[name] = blob
    map_blob, map_changed = prepare_jpeg(map_path, MAX_MAP_SIDE, None)
    blobs[map_file] = map_blob

    # --- 星位 / 星域 / 星宿 / 关系 / 海报推荐 ---
    calib = load_json(data_dir / "calib.json", {}) if data_dir else {}
    if args.derive_calib and not calib:
        from starmap_layout import layout_positions
        calib = layout_positions(rows)
    areas = load_json(data_dir / "areas.json", None) if data_dir else None
    if areas is None:
        areas = derive_areas(rows)
    area_keys = load_json(data_dir / "area_keys.json", []) if data_dir else []
    rel = load_json(data_dir / "relations.json", []) if data_dir else []
    consts = load_json(data_dir / "constellations.json", None) \
        if data_dir else None
    if consts is None:
        counts: dict[str, int] = {}
        for c in cats:
            counts[c["area"]] = counts.get(c["area"], 0) + 1
        consts = derive_const(areas, counts)
    if len(consts) != len(areas):
        raise SystemExit(
            f"星宿数 {len(consts)} ≠ 星域数 {len(areas)}（两者必须一一对应）")
    stars = load_json(data_dir / "poster_stars.json", None) if data_dir else None
    if stars is None:
        stars = derive_poster_stars(cats)

    # --- 里程碑 / 称号 ---
    ms = opt(None, "milestones", milestones_for(n))
    pass_titles = opt(None, "pass_titles", pass_titles_for(ms))

    # --- 文案富参数（meta 可逐句覆写以保真） ---
    committee = f"{school}猫咪编制委员会"
    king_name = opt(None, "king_name", short + "猫王")
    poster_title = opt(None, "poster_title", short + "寻猫地图")
    poster_file = opt(None, "poster_file", short + "寻猫海报.png")
    export_map_name = opt(None, "export_map_name", f"{school}校园图")
    skill_foot = opt(None, "skill_foot_line",
                     f"{school}—校园猫咪档案 · {tagline}")
    soul_line = opt(None, "soul_line",
                    f"和它一样：真实、在编、被记录在册的{short}猫")
    calib_lead = opt(None, "calib_note", None)
    if calib_lead is None:
        calib_lead = ("人工固化校准坐标 · 手动校准 localStorage 仍优先覆盖"
                      if calib else
                      "星位由页面内置算法按编号稳定推导（basePos）· "
                      "可在页面上手拖校准后导出坐标")

    # ---------- 52 条规则的最终值（顺序同提取器） ----------
    # F11 主题/校徽（v29）：开放仓库是本地构建、build_meta 由普查团队自写，
    # 这里透传字符串；工厂在线侧（T6 F2）会在适配层做 Theme 规范化与
    # logo src 白名单，不吃任意用户输入。默认全空 → 产物与 v28 字节一致。
    f11_theme_css = str(meta.get("theme_css", "") or "")
    f11_logo_intro = str(meta.get("logo_intro", "") or "")
    f11_logo_topbar = str(meta.get("logo_topbar", "") or "")
    if "</script" in f11_theme_css.lower():
        raise SystemExit("theme_css 不允许含 </script>（主题只接受纯 CSS）")
    for _label, _tag in (("logo_intro", f11_logo_intro),
                         ("logo_topbar", f11_logo_topbar)):
        if _tag and not (
                _tag.lstrip().startswith("<img")
                and "</script" not in _tag.lower()):
            raise SystemExit(f"{_label} 只允许单个 <img> 标签")

    # ---------- 渲染（T6 F7 反向 vendor：唯一渲染真相 = starmap_render） ----------
    # CATS.photo 统一为 assets/photos/ 前缀（渲染器按现值输出，不再自拼）
    for c in cats:
        if c["photo"] and not c["photo"].startswith("assets/photos/"):
            c["photo"] = "assets/photos/" + c["photo"]

    inp = V29RenderInput(
        school=school, cats=cats, photos=blobs, map_bytes=map_blob,
        map_key=map_file, calib=calib, photo_loading=photo_loading,
        product=product, en=en, version=version, tagline=tagline,
        survey_date=survey_date, photo_total=p_total, ls_prefix=ls_prefix,
        repo_url=repo_url, docs_ref=docs_ref,
        theme_css=f11_theme_css, logo_intro=f11_logo_intro,
        logo_topbar=f11_logo_topbar,
        milestones=ms, pass_titles=pass_titles,
        king_name=king_name, poster_title=poster_title,
        poster_file=poster_file, export_map_name=export_map_name,
        skill_foot_line=skill_foot, soul_line=soul_line,
        calib_note=calib_lead,
        areas=areas, area_keys=area_keys, rel=rel, consts=consts,
        poster_stars=stars)
    bundle = render(inp)
    html = bundle.html

    # --- 落盘 ---
    out = Path(args.out)
    assets = out / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    assets.mkdir(parents=True, exist_ok=True)
    for name, text in bundle.iter_chunks(lambda k: blobs[k]):
        # newline 固定 LF：托管产物门禁要求任意平台构建逐字节一致
        (assets / name).write_text(text, "utf-8", newline="\n")
    (out / f"{product}.html").write_text(bundle.html, "utf-8", newline="\n")
    d_out = out / "data"
    d_out.mkdir(exist_ok=True)
    shutil.copy2(csv_path, d_out / "猫咪名册.csv")
    src_summary = (data_dir / "归并决策摘要.md") if data_dir else None
    if src_summary and src_summary.exists():
        shutil.copy2(src_summary, d_out / "归并决策摘要.md")

    print(f"✓ {product} 构建完成 → {out.resolve()}")
    print(f"  猫 {n} 只 · 照片 {len(need)} 个文件（重压缩 {recompressed}"
          f" 张）· 底图{'重压缩' if map_changed else '原样'} · "
          f"分片 {len(bundle.groups)} 个 · CALIB {len(calib)} 键 · "
          f"星域 {len(areas)} · 星宿 {len(consts)}")
    print(f"  打开方式：直接双击 {product}.html（全离线，无需服务器）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
