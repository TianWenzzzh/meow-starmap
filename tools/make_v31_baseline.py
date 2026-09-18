#!/usr/bin/env python3
"""v30 → v31 golden：字栈顺序修正（确定性补丁，可重跑）。

v31 相对 v30 的唯一变化是 2 个 U 补丁——把 HarmonyOS Sans SC / MiSans 从
Microsoft YaHei **之前**移到**之后**：
  U1a  全局 CSS 字体栈（html,body）
  U1b  海报 SVG 字体栈
动机：装有 HarmonyOS Sans SC 或 MiSans 的 Windows 设备（华为/小米本、设计师机）
会从雅黑漂移到定制黑体，违反设计规范自述红线「macOS/Windows 首选不变」。
重排后 macOS（苹方居首）/纯净 Windows（雅黑）/Linux（思源/Noto 兜底，雅黑不存在）
三端均与历史产物观感一致。

与 v30 的 TYPO 补丁一样：U 补丁**同时作用于模板与基线**（排版属于产物本身，
与 token 无关），规则集不变、不新增 token。v30 模板在打补丁前冻结为
tests/fixtures/v30_template.html（V30RoundtripTest 随之转为历史回归）。

产出（--check 只比对不落盘）：
  tests/fixtures/v30_template.html  v30 模板冻结快照（历史回归用）
  tests/fixtures/v31_baseline.html  v31 基线（= v30 基线 + U）
  template/starmap.html             v31 token 模板（= v30 模板 + U）
规则文件 nuc_literals.json 不变（U 不新增 token，脚本会断言这点）。

用法：
  python3 tools/make_v31_baseline.py          # 生成
  python3 tools/make_v31_baseline.py --check  # CI 金新鲜度门禁
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
# 排版迭代 v32 起，现役模板 template/starmap.html 归 make_v32 所有；
# 本脚本的模板产物改为落冻结快照，供 V31RoundtripTest 历史回归。
TEMPLATE_PATH = FIX / "v31_template.html"

V30_TEMPLATE = FIX / "v30_template.html"        # 冻结输出（历史回归）
V30_BASELINE = FIX / "v30_baseline.html"        # 上一代输入（勿改）
V30_RULES = FIX / "nuc_literals.json"           # 上一代规则（勿改，本代不变）
V31_BASELINE = FIX / "v31_baseline.html"

# 字栈顺序补丁：(编号, v30 原文, v31 新形态, 次数)。锚点均唯一（已 grep 核实）。
U_PATCHES: list[tuple[str, str, str, int]] = [
    ("U1a-css-stack",
     '    font-family:"PingFang SC","HarmonyOS Sans SC","MiSans",'
     '"Microsoft YaHei","Source Han Sans SC","Noto Sans CJK SC",sans-serif; }',
     '    font-family:"PingFang SC","Microsoft YaHei","HarmonyOS Sans SC",'
     '"MiSans","Source Han Sans SC","Noto Sans CJK SC",sans-serif; }',
     1),
    ("U1b-svg-stack",
     'font-family="PingFang SC,HarmonyOS Sans SC,MiSans,'
     'Microsoft YaHei,Source Han Sans SC,Noto Sans CJK SC,sans-serif"',
     'font-family="PingFang SC,Microsoft YaHei,HarmonyOS Sans SC,MiSans,'
     'Source Han Sans SC,Noto Sans CJK SC,sans-serif"',
     1),
]


def _apply(text: str, patches, tag: str) -> str:
    for name, old, new, expected in patches:
        actual = text.count(old)
        if actual != expected:
            raise SystemExit(
                f"U 补丁 {name} 在 {tag} 出现 {actual} 次，预期 {expected}")
        text = text.replace(old, new)
    return text


def main() -> int:
    check = "--check" in sys.argv

    v30_template = V30_TEMPLATE.read_text("utf-8") \
        if V30_TEMPLATE.exists() else TEMPLATE_PATH.read_text("utf-8")
    v30_baseline = V30_BASELINE.read_text("utf-8")
    v30_rules = json.loads(V30_RULES.read_text("utf-8"))["rules"]

    # 冻结 v30 模板快照（首次运行时落盘；--check 时只要求已存在）
    if not check and not V30_TEMPLATE.exists():
        V30_TEMPLATE.write_text(v30_template, encoding="utf-8")
    if not V30_TEMPLATE.exists():
        raise SystemExit("缺 fixtures/v30_template.html 冻结快照")

    # 模板与基线同步应用 U 补丁（次数逐一断言）
    template = _apply(v30_template, U_PATCHES, "v30 模板")
    baseline = _apply(v30_baseline, U_PATCHES, "v30 基线")

    # 自验 1：F11 三 token 与数据块 token 全部原样保留
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__",
                  "__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__"):
        if template.count(token) != 1:
            raise SystemExit(f"v31 模板 token {token} 次数 ≠ 1")

    # 自验 2：规则集规模不变（U 不新增 token、不碰规则；名字集完整性
    # 由自验 3 的整链往返兜底——任何一条失配都会在灌回时暴露）
    if len(v30_rules) != 55:
        raise SystemExit(
            f"v30 规则数 {len(v30_rules)} ≠ 55——规则变了要升级本脚本")

    # 自验 3：模板正序灌回全部规则 == v31 基线（字节往返）
    filled = template
    for r in v30_rules:
        filled = filled.replace(r["new"], r["old"])
    if filled != baseline:
        for i, (a, b) in enumerate(zip(filled, baseline)):
            if a != b:
                raise SystemExit(
                    f"v31 灌回与基线首个差异在偏移 {i}：\n"
                    f"  灌回={filled[max(0, i - 40):i + 40]!r}\n"
                    f"  基线={baseline[max(0, i - 40):i + 40]!r}")
        raise SystemExit(
            f"v31 灌回与基线长度不同：{len(filled)} vs {len(baseline)}")

    # 自验 4（F11 红线的 v31 形态）：空 F11 渲染 == v30 模板 + U（同样去 token）
    empty = template
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        empty = empty.replace(token, "")
    v30_with_u = _apply(
        V30_TEMPLATE.read_text("utf-8"), U_PATCHES, "冻结 v30 模板")
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        v30_with_u = v30_with_u.replace(token, "")
    if empty != v30_with_u:
        raise SystemExit("F11 空值路径与「v30 模板 + U」不一致")

    outputs = {
        V31_BASELINE: baseline,
        TEMPLATE_PATH: template,
    }
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists() or path.read_text("utf-8") != content:
                drift.append(str(path.relative_to(REPO)))
        if drift:
            print("v31 golden 漂移，请运行 python3 tools/make_v31_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print("v31 golden 新鲜：baseline/template 均与补丁脚本一致；"
              "F11 空值路径 == v30 模板 + U")
        return 0

    for path, content in outputs.items():
        path.write_text(content, "utf-8")
    print(f"v31 baseline : {V31_BASELINE}（{baseline.count(chr(10))+1} 行）")
    print(f"v31 template : {TEMPLATE_PATH}（{template.count(chr(10))+1} 行，"
          f"{len(U_PATCHES)} 个字栈顺序补丁）")
    print("自验：灌回规则 == 基线；F11 空值渲染 == v30 模板 + U ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
