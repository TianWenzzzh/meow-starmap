"""CSV 名册 → 星图 CATS 字段推导 + 可选的服务端落位算法。

vendored from 喵星图工厂 app/star_mapper.py（MIT License, © TianWenzzzh）
来源仓库：https://github.com/TianWenzzzh/catgalaxy-factory （v1.0.0, app/star_mapper.py）
改动（仅清理跨模块依赖，算法一字未动）：
  - 去掉 pydantic CatRow，改用本文件 dataclass RosterCat；
  - 内联 csv_loader.normalize_id / id_number；
  - 未引入工厂的 ZONES token 体系（本仓库模板以 v2.7 正式版为基准）。

注意：v2.7 正式版页面内置浏览器端 basePos()（mulberry32(FNV(id))）兜底，
新学校即使 CALIB 为空也能正常落位；本模块的 layout_positions 仅在需要
服务端预生成 calib.json（--derive-calib）时使用，默认构建不调用。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional

ID_RE = re.compile(r"^CAT[-_ ]?(\d{1,4})$", re.IGNORECASE)

# ---- 毛色分组：顺序即优先级，先命中先归类 ----
COAT_GROUPS: list[tuple[str, tuple[str, ...], str]] = [
    ("三花", ("三花", "三色", "calico"), "255,170,200"),
    ("玳瑁", ("玳瑁", "龟壳"), "210,160,120"),
    ("奶牛", ("奶牛", "黑白花", "宾士"), "225,235,250"),
    ("纯白", ("纯白", "全白", "白猫"), "235,245,255"),
    ("纯黑", ("纯黑", "全黑", "黑猫", "通黑"), "150,160,200"),
    ("重点色", ("重点色", "暹罗", "布偶", "海豹"), "190,200,235"),
    ("狸花", ("狸花", "狸貓", "虎斑狸", "彩狸", "麻狸"), "168,190,220"),
    ("橘", ("橘", "桔", "黄", "奶油", "金"), "255,190,110"),
]
FALLBACK_GROUP = "其他"
FALLBACK_COLOR = "200,200,220"

# ---- 出没区域 → 分区锚点（归一化坐标，落在核心区）----
ZONES: list[tuple[str, tuple[str, ...], float, float]] = [
    ("宿舍居民区", ("宿舍", "居民", "公寓", "寝室", "楼内", "窗台"), 0.62, 0.53),
    ("教学楼食堂区", ("教学", "食堂", "教室", "大厅", "走廊", "门厅", "楼梯"), 0.42, 0.43),
    ("道路沿线", ("道路", "路边", "马路", "小径", "人行道", "水泥"), 0.52, 0.36),
    ("草地植被区", ("草地", "绿化", "草坪", "树", "灌木", "花"), 0.38, 0.58),
    ("车库停车区", ("车库", "电动", "停车", "自行车", "车棚"), 0.70, 0.46),
    ("围墙护栏区", ("围墙", "护栏", "栅栏", "铁", "施工", "墙"), 0.79, 0.47),
    ("投喂点", ("投喂", "喂食", "猫粮", "饭点"), 0.57, 0.55),
    ("石台高台区", ("石台", "高台", "台阶", "平台", "石砖", "花岗岩"), 0.47, 0.55),
    ("老旧房区", ("老旧", "废弃", "平房", "锅炉", "仓库"), 0.37, 0.70),
    ("排水格栅区", ("排水", "格栅", "下水", "沟"), 0.36, 0.42),
]
GENERIC_ANCHORS = [
    (0.30, 0.30), (0.50, 0.25), (0.70, 0.30), (0.85, 0.40),
    (0.30, 0.75), (0.50, 0.80), (0.70, 0.75), (0.20, 0.50),
    (0.85, 0.60), (0.45, 0.65), (0.60, 0.20), (0.25, 0.62),
]
BOUND_X = (0.10, 0.90)
BOUND_Y = (0.12, 0.88)


@dataclass
class RosterCat:
    """名册一行（CSV 12 列规整化结果）。"""
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


def normalize_id(raw: str) -> Optional[str]:
    """'CAT-001' / 'cat_1' / 'CAT 001' → 'CAT-001'。"""
    if not raw:
        return None
    m = ID_RE.match(raw.strip())
    return f"CAT-{int(m.group(1)):03d}" if m else None


def id_number(cat_id: str) -> Optional[int]:
    m = ID_RE.match((cat_id or "").strip())
    return int(m.group(1)) if m else None


def classify_coat(coat: str) -> str:
    text = (coat or "").strip().lower()
    if not text:
        return FALLBACK_GROUP
    for group, keys, _ in COAT_GROUPS:
        for k in keys:
            if k.lower() in text:
                return group
    return FALLBACK_GROUP


def brightness_from_count(n: int) -> float:
    """照片数 → 星等。与中北版实测值逐项对齐：1→.50 2→.61 … 5→.94 8→1.05。"""
    n = max(1, int(n or 1))
    return round(min(0.5 + 0.11 * (n - 1), 1.05), 2)


def normalize_area(area: str) -> str:
    return re.sub(r"\s+", "", (area or "").strip())


def zone_of(area: str) -> Optional[str]:
    text = normalize_area(area)
    if not text:
        return None
    for name, keys, _, _ in ZONES:
        for k in keys:
            if k in text:
                return name
    return None


def split_features(features: str) -> list[str]:
    parts = re.split(r"[\s,，、;；/]+", (features or "").strip())
    return [p for p in parts if p]


def join_features(features: str) -> str:
    return "、".join(split_features(features))


def make_bio(row: RosterCat) -> str:
    """只用 CSV 中的事实字段合成小传，不虚构行为故事。"""
    name = row.name or row.id
    bits = [f"{name}，编制军衔「{row.rank or '未定衔'}」，职务「{row.title or '未定岗'}」。"]
    if row.area:
        bits.append(f"常驻{normalize_area(row.area)}。")
    feats = join_features(row.features)
    if feats:
        bits.append(f"可辨识特征：{feats}。")
    if row.photo_count:
        bits.append(f"收录实拍{row.photo_count}张。")
    if row.note:
        bits.append(f"档案备注：{row.note.strip()}。")
    return "".join(bits)


def assign_anchors(areas: Iterable[str]) -> dict[str, tuple[float, float]]:
    """给每个出现过的 area 分配一个锚点坐标。"""
    uniq: list[str] = []
    for a in areas:
        key = normalize_area(a)
        if key and key not in uniq:
            uniq.append(key)
    anchors: dict[str, tuple[float, float]] = {}
    generic_i = 0
    for area in uniq:
        zone = zone_of(area)
        if zone:
            for name, _, ax, ay in ZONES:
                if name == zone:
                    anchors[area] = (ax, ay)
                    break
        else:
            anchors[area] = GENERIC_ANCHORS[generic_i % len(GENERIC_ANCHORS)]
            generic_i += 1
    return anchors


def _hash_str(s: str) -> int:
    """FNV-1a，与模板 JS 端 hashStr 同构，保证坐标稳定可复现。"""
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _rand2(seed: str) -> tuple[float, float]:
    h1 = _hash_str(seed)
    h2 = _hash_str(seed + "::y")
    return (h1 % 10000) / 10000.0, (h2 % 10000) / 10000.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _relax(pos: dict[str, dict[str, float]], min_dist: float,
           iterations: int) -> None:
    ids = list(pos)
    for _ in range(iterations):
        moved = False
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = pos[ids[i]], pos[ids[j]]
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                d = math.hypot(dx, dy)
                if d >= min_dist:
                    continue
                moved = True
                if d < 1e-6:
                    dx, dy, d = 0.01, 0.01, 0.0141
                push = (min_dist - d) / 2
                ux, uy = dx / d, dy / d
                a["x"] = round(_clamp(a["x"] - ux * push, *BOUND_X), 3)
                a["y"] = round(_clamp(a["y"] - uy * push, *BOUND_Y), 3)
                b["x"] = round(_clamp(b["x"] + ux * push, *BOUND_X), 3)
                b["y"] = round(_clamp(b["y"] + uy * push, *BOUND_Y), 3)
        if not moved:
            break


def layout_positions(rows: list[RosterCat]) -> dict[str, dict[str, float]]:
    """按 area 聚簇 + 黄金角螺旋散开 + 最小间距松弛，输出 {id: {x,y}}。"""
    if not rows:
        return {}
    anchors = assign_anchors([r.area for r in rows])
    groups: dict[str, list[RosterCat]] = {}
    for r in rows:
        groups.setdefault(normalize_area(r.area), []).append(r)

    pos: dict[str, dict[str, float]] = {}
    golden = math.pi * (3 - math.sqrt(5))
    for area, members in groups.items():
        ax, ay = anchors.get(area, (0.5, 0.5))
        n = len(members)
        spread = min(0.10, 0.022 + 0.012 * math.sqrt(n))
        for i, r in enumerate(members):
            jx, jy = _rand2(r.id)
            ang = i * golden + jx * 1.7
            rad = spread * math.sqrt((i + 0.5) / n)
            x = ax + rad * math.cos(ang) + (jx - 0.5) * 0.012
            y = ay + rad * math.sin(ang) * 0.72 + (jy - 0.5) * 0.012
            pos[r.id] = {"x": round(_clamp(x, *BOUND_X), 3),
                         "y": round(_clamp(y, *BOUND_Y), 3)}
    _relax(pos, min_dist=0.032, iterations=6)
    return pos
