#!/usr/bin/env python3
"""排版属性审计工具（迭代基础设施）。

回答「产物里每一个字体/排版声明是什么、在哪」——供字号档位评审（迭代 2）、
字距令牌化（迭代 3）等持续迭代使用，替代一次性 grep。

覆盖四种声明形态：
  1. <style> 内 CSS 规则（含一层 @media / @supports 嵌套，选择器带媒体条件前缀）
  2. CSS font 简写（`font: 700 18px ...`，如控制台彩蛋）
  3. <script> 内 canvas 字体串（`ctx.font = '900 ' + fs + 'px "PingFang SC" ...'`，
     区分静态 px 与拼接表达式）
  4. SVG 表现属性（`font-size="34"` / `font-family="..."`）

输出：
  人读摘要（stdout）：font-size 档位分布表 + 各形态计数
  --json <path>：完整结构化结果（机器可读，供评审文档引用）

用法：
  python3 tools/audit_typography.py                       # 审计现役模板
  python3 tools/audit_typography.py template/starmap.html gallery/index.html
  python3 tools/audit_typography.py --json /tmp/audit.json template/starmap.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from bisect import bisect_left
from pathlib import Path
from typing import Iterator

# CSS 里需要登记的属性（font-size 单列成档位表，其余按值聚合）
_TRACKED_PROPS = ("font-size", "font-weight", "line-height",
                  "letter-spacing", "font-family", "font-variant-numeric")

_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
_CANVAS_FONT_RE = re.compile(r"\.font\s*=\s*([^;\n]+)")
_STATIC_PX_RE = re.compile(r"(\d+(?:\.\d+)?)px")
_SVG_FONT_SIZE_RE = re.compile(r'font-size="([^"]+)"')
_SVG_FONT_FAMILY_RE = re.compile(r'font-family="([^"]+)"')
# 带花括号块的 @ 规则（@keyframes 内含 from/to/百分比子块，必须按嵌套解析，
# 否则首个内部 `}` 会被误当作规则结束，污染后续选择器）
_AT_NESTED_RE = re.compile(
    r"^@(media|supports|layer|document|container|(-[a-z]+-)?keyframes)\b")


def _line_starts(text: str) -> list[int]:
    """每行行首偏移表，配合 bisect 做 O(log n) 行号查询。"""
    starts = [0]
    for m in re.finditer(r"\n", text):
        starts.append(m.end())
    return starts


def _line_no(starts: list[int], offset: int) -> int:
    """1 起始行号；offset 落在行首时计入该行。"""
    return bisect_left(starts, offset + 1)


def iter_css_blocks(text: str, line_offset: int = 1) -> Iterator[tuple[str, str, int]]:
    """产出 (selector, body, line_no_in_file)。

    支持一层 @media / @supports 嵌套；嵌套内规则的 selector 带媒体条件前缀
    （`@media (max-width:768px) :: .chip`），保证审计能区分桌面档与移动端覆盖档。
    line_offset：text 首行在源文件中的行号（<style> 内容紧跟标签同行开始，
    故传 <style> 标签所在行号即可对齐）。
    """
    starts = _line_starts(text)

    def line_at(offset: int) -> int:
        return line_offset + _line_no(starts, offset) - 1

    i, n = 0, len(text)
    while True:
        brace = text.find("{", i)
        if brace == -1:
            return
        header = text[i:brace].strip()
        # 判定 @ 规则前先剥离行内注释——模板惯例是「前一条规则 } 之后跟
        # 行内注释，紧接着 @keyframes」，此时 header 以 /*…*/ 开头
        header_test = re.sub(r"/\*.*?\*/", "", header, flags=re.S).strip()
        if _AT_NESTED_RE.match(header_test):
            depth, j = 1, brace + 1
            while j < n and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            if depth:
                raise ValueError(f"CSS 花括号不配对（@media 起始于偏移 {brace}）")
            inner = text[brace + 1:j - 1]
            for sel, body, ln in iter_css_blocks(inner, line_at(brace)):
                yield f"{header} :: {sel}", body, ln
            i = j
        else:
            end = text.find("}", brace)
            if end == -1:
                raise ValueError(f"CSS 花括号不配对（规则起始于偏移 {brace}）")
            if header:
                yield header, text[brace + 1:end], line_at(brace)
            i = end + 1


def _extract_style_blocks(html: str) -> Iterator[tuple[str, int]]:
    for m in re.finditer(r"<style\b[^>]*>(.*?)</style>", html, re.S | re.I):
        yield m.group(1), m.start()


def _split_declarations(body: str) -> Iterator[str]:
    """按分号切声明，忽略值内圆括号中的分号（如 clamp()）与引号串。"""
    buf: list[str] = []
    depth, quote = 0, ""
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0 and not quote:
            decl = "".join(buf).strip()
            if decl:
                yield decl
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        yield tail


def audit_css(html: str) -> dict:
    """解析全部 <style> 块，返回按属性聚合的声明清单。"""
    props: dict[str, list] = {k: [] for k in _TRACKED_PROPS}
    shorthand: list[dict] = []
    for css, base in _extract_style_blocks(html):
        style_line = _line_no(_line_starts(html), base)
        for selector, body, line in iter_css_blocks(css, style_line):
            for decl in _split_declarations(body):
                if ":" not in decl:
                    continue
                name, _, value = decl.partition(":")
                name = name.strip().lower()
                value = value.strip()
                entry = {"selector": selector, "line": line, "value": value}
                if name == "font":
                    if re.search(r"\d", value):  # 带尺寸的简写才登记（排除 inherit 等）
                        shorthand.append(entry)
                elif name in props:
                    props[name].append(entry)
    return {"props": props, "font_shorthand": shorthand}


def audit_canvas_scripts(html: str) -> list[dict]:
    """提取 <script> 内的 canvas 字体赋值（`.font = ...`）。"""
    out: list[dict] = []
    html_starts = _line_starts(html)
    for m in _SCRIPT_RE.finditer(html):
        script = m.group(1)
        script_starts = _line_starts(script)
        for fm in _CANVAS_FONT_RE.finditer(script):
            expr = fm.group(1).strip()
            if not expr:
                continue
            out.append({
                "line": _line_no(html_starts, m.start())
                        + _line_no(script_starts, fm.start()) - 1,
                "expr": expr,
                "static_px": [float(v) for v in _STATIC_PX_RE.findall(expr)],
                "dynamic": "+" in expr,
            })
    return out


def audit_svg_attrs(html: str) -> dict:
    html_starts = _line_starts(html)
    return {
        "font_size": [{"value": m.group(1),
                       "line": _line_no(html_starts, m.start())}
                      for m in _SVG_FONT_SIZE_RE.finditer(html)],
        "font_family": sorted({m.group(1)
                               for m in _SVG_FONT_FAMILY_RE.finditer(html)}),
    }


def _tier_table(entries: list[dict]) -> list[dict]:
    """按数值升序的档位表：值 → 处数 → 使用位置；非纯数值（clamp 等）排最后。"""

    def sort_key(e: dict):
        v = e["value"]
        try:
            return (0, float(v.removesuffix("px")))
        except ValueError:
            return (1, v)

    grouped: dict[str, dict] = {}
    for e in sorted(entries, key=sort_key):
        g = grouped.setdefault(e["value"], {"value": e["value"],
                                            "count": 0, "rules": []})
        g["count"] += 1
        g["rules"].append({"selector": e["selector"], "line": e["line"]})
    return list(grouped.values())


def audit_file(path: Path) -> dict:
    html = path.read_text("utf-8")
    css = audit_css(html)
    return {
        "file": str(path),
        "css_font_size_tiers": _tier_table(css["props"]["font-size"]),
        "css_props": css["props"],
        "css_font_shorthand": css["font_shorthand"],
        "canvas_fonts": audit_canvas_scripts(html),
        "svg": audit_svg_attrs(html),
    }


def print_summary(result: dict) -> None:
    tiers = result["css_font_size_tiers"]
    print(f"=== 排版审计：{result['file']} ===")
    print(f"-- CSS font-size：{sum(t['count'] for t in tiers)} 处 / "
          f"{len(tiers)} 档 --")
    for tier in tiers:
        shown = ", ".join(f"L{r['line']} {r['selector']}"
                          for r in tier["rules"][:3])
        more = "" if tier["count"] <= 3 else f" …(+{tier['count'] - 3})"
        print(f"  {tier['value']:>16} ×{tier['count']:<3} {shown}{more}")
    for prop in ("font-weight", "line-height", "letter-spacing",
                 "font-variant-numeric"):
        items = result["css_props"].get(prop, [])
        values: dict[str, int] = {}
        for it in items:
            values[it["value"]] = values.get(it["value"], 0) + 1
        dist = ", ".join(f"{v}×{c}" for v, c in sorted(values.items()))
        print(f"-- {prop}（{len(items)} 处）：{dist}")
    fams = sorted({it["value"]
                   for it in result["css_props"].get("font-family", [])})
    print(f"-- font-family（{len(result['css_props'].get('font-family', []))} 处 / "
          f"{len(fams)} 种）--")
    for f in fams:
        print(f"  {f}")
    print(f"-- font 简写：{len(result['css_font_shorthand'])} 处")
    dyn = [c for c in result["canvas_fonts"] if c["dynamic"]]
    static_vals: dict[float, int] = {}
    for c in result["canvas_fonts"]:
        for v in c["static_px"]:
            static_vals[v] = static_vals.get(v, 0) + 1
    print(f"-- canvas 字体串：{len(result['canvas_fonts'])} 处"
          f"（动态拼接 {len(dyn)}；静态 px {dict(sorted(static_vals.items()))}）")
    svg_sizes = [s["value"] for s in result["svg"]["font_size"]]
    print(f"-- SVG：font-size {len(svg_sizes)} 处 {svg_sizes}；"
          f"font-family {len(result['svg']['font_family'])} 种")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="排版属性审计工具")
    parser.add_argument("files", nargs="*",
                        default=["template/starmap.html"],
                        help="待审计 HTML（相对仓库根或绝对路径）")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="把完整结构化结果写入该 JSON 文件")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    results = []
    for f in args.files:
        p = Path(f) if Path(f).is_absolute() else repo_root / f
        if not p.exists():
            print(f"audit_typography: 文件不存在：{p}", file=sys.stderr)
            return 2
        results.append(audit_file(p))

    for r in results:
        print_summary(r)
        print()

    if args.json_out:
        out = Path(args.json_out) \
            if Path(args.json_out).is_absolute() else repo_root / args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"结构化结果已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
