#!/usr/bin/env python3
"""溯源核对：名册「关联照片编号」token ↔ 08_原始照片视频 实体照片 三方机检。

深扫 B-05 后续（16h 会话 P4）：关联列实测语义全部最终指向照片文件名——
  hash:XXXX[;XXXX…]      文件名 sha/前缀
  812批:N                2026-08-12 组、序号 N（文件名 微信图片_20260812…_N_*.jpg）
  816批:N[;m…]           2026-08-16 组、序号 N（同上）
  补<TS>:N               TS=补充组时间戳（如 235021），序号 N
解析器把每个 token 解析成「(时间戳前缀, 序号) 或文件名前缀」，在 08 目录的
文件名索引里核验存在性。某行 ≥1 个 token 命中即视为可溯源；
token 全部无法解析/命中的行列入待补注清单。退出码 0 = 无断链。

只读；证据落 docs/溯源核对-最近一次.txt。
用法：STARMAP_HOME=总库根 python tools/verify_traceability.py
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
E_ROOT = Path(os.environ.get("STARMAP_HOME") or r"E:\猫咪星图_总库")
ROSTER = E_ROOT / "07_普查原始数据" / "猫咪名册.csv"
PHOTO_DIRS = [E_ROOT / "08_原始照片视频" / "照片视频",
              E_ROOT / "08_原始照片视频" / "补充视频照片"]
BATCH_DIR = E_ROOT / "07_普查原始数据"

FNAME_RE = re.compile(r"^(微信图片_)?(\d{10,})_(\d{1,3})_\d+\.(jpg|jpeg)$", re.I)
HASH_RE = re.compile(r"[0-9A-Fa-f]{4,}")
TOK_BATCH_RE = re.compile(r"(\d{3,8})\s*批\s*[:：]\s*([\d;，,\s]+)")
TOK_BU_RE = re.compile(r"补\s*(\d{5,8})\s*[:：]\s*([\d;，,\s]+)")


def main() -> int:
    # 08 文件名索引：{(时间戳, 序号): 文件名} ∪ {stem前缀大写: 文件名}
    ts_idx: dict[tuple[str, int], str] = {}
    pre_idx: dict[str, str] = {}
    total_files = 0
    for d in PHOTO_DIRS:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            total_files += 1
            m = FNAME_RE.match(f.name)
            if m:
                ts_idx.setdefault((m.group(2), int(m.group(3))), f.name)
            pre_idx.setdefault(Path(f.name).stem.upper()[:8], f.name)

    # 批次文件索引：{文件: (日期集合, {序号: 行文件名})}
    # 「NNN批:M」= 拍摄日期 mmdd 的批次文件里、文件名序号 M 的那条记录
    batch_dates: dict[Path, set[str]] = {}
    batch_idx: dict[Path, dict[int, str]] = {}
    for b in sorted(BATCH_DIR.glob("普查-batch*.txt")):
        dates: set[str] = set()
        idx: dict[int, str] = {}
        for line in b.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            fn = line.split("|")[0].strip()
            md = re.search(r"_(\d{14})_", fn)
            mi = re.search(r"_(\d{1,3})_\d+\.(?:jpg|jpeg)$", fn, re.I)
            if md:
                dates.add(md.group(1)[:8])
            if mi:
                idx[int(mi.group(1))] = fn
        batch_dates[b] = dates
        batch_idx[b] = idx

    text = ROSTER.read_bytes().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    broken: list[str] = []
    unresolved: list[str] = []
    ok = 0
    for r in rows:
        rid = r["编号"]
        rel = (r.get("关联照片编号") or "").strip()
        if not rel:
            unresolved.append(f"{rid} 关联列为空")
            continue

        def resolve(rel: str) -> tuple[bool, list[str]]:
            """返回 (是否至少一个 token 命中, 未命中 token 说明)。

            实测语义（16h 会话 P4 破译）：
              812批:N / 816批:N  → 「2026 年 8 月 12/16 日组、序号 N」，
                  文件名形如 微信图片_20260812143555_100_56.jpg（序号=_100_）
              补33805:N / 补35021:N → 补充组时间戳【尾缀】33805/35021、序号 N
              hash:XXXX          → 文件名 stem 的十六进制前缀（0812 原始命名）
            """
            hit, miss = False, []
            checked = False

            def day_pref(day: str) -> str:
                # 812 → 20260812（月不补零写法）；兼容已写全的 20260812
                if day.startswith("2026"):
                    return day
                mm, dd = day[0], day[1:]
                return f"2026{int(mm):02d}{int(dd):02d}"

            for m in re.finditer(r"(\d{3,4})\s*批\s*[:：]\s*([\d;，,\s]+)", rel):
                pref = day_pref(m.group(1))
                cands = [b for b, ds in batch_dates.items() if pref in ds]
                checked = True
                if not cands:
                    miss.append(f"{m.group(1)}批（无该日期批次文件）")
                    continue
                for x in re.split(r"[;，,\s]+", m.group(2)):
                    if not x:
                        continue
                    n = int(x)
                    if any(n in batch_idx[b] for b in cands):
                        hit = True
                    else:
                        miss.append(f"{m.group(1)}批:{x}")
            for m in TOK_BU_RE.finditer(rel):
                for x in re.split(r"[;，,\s]+", m.group(2)):
                    if not x:
                        continue
                    checked = True
                    cands = [k for k in ts_idx
                             if k[0].endswith(m.group(1)) and k[1] == int(x)]
                    if cands:
                        hit = True
                    else:
                        miss.append(f"补{m.group(1)}:{x}")
            for h in HASH_RE.findall(rel):
                if len(h) < 4:
                    continue
                checked = True
                cands = [k for k in pre_idx if k.startswith(h.upper())]
                if cands:
                    hit = True
                else:
                    miss.append(f"hash:{h}")
            return hit, ([] if hit else miss or ["无可解析 token"])

        hit, miss = resolve(rel)
        if hit:
            ok += 1
        elif HASH_RE.search(rel) or TOK_BATCH_RE.search(rel) or TOK_BU_RE.search(rel):
            broken.append(f"{rid} ← {rel}（未命中：{', '.join(miss)}）")
        else:
            unresolved.append(f"{rid} ← {rel}")

    print(f"名册 {len(rows)} 行 | 08 实体照片 {total_files} | 文件名索引 "
          f"{len(ts_idx)}+{len(pre_idx)}")
    print(f"可溯源: {ok} | token 断链: {len(broken)} | 待补注: {len(unresolved)}")
    for x in broken[:8]:
        print("  ✗ 断链:", x)
    for x in unresolved[:8]:
        print("  ? 补注:", x)

    evidence = REPO / "docs" / "溯源核对-最近一次.txt"
    evidence.write_text(
        f"名册 {len(rows)} 行 | 08 照片 {total_files} | 可溯源 {ok} | "
        f"断链 {len(broken)} | 待补注 {len(unresolved)}\n"
        + ("\n".join("✗ " + x for x in broken)
           + "\n".join("? " + x for x in unresolved)) + "\n", encoding="utf-8")
    print(f"证据 → {evidence}")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
