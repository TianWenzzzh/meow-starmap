#!/usr/bin/env python3
"""v29 → v30 golden：排版精修迭代 1（确定性补丁，可重跑）。

v30 相对 v29 的唯一变化是 5 个 TYPO 排版补丁（F7 后的「细到每一个字体」迭代）：
  T1a/T1b  中文字体栈跨平台补全——追加 HarmonyOS Sans SC / MiSans /
           Source Han Sans SC / Noto Sans CJK SC 兜底（macOS/Windows 首选
           字体不变 → 观感零回归；Linux/老旧 Windows 中文不再是系统默认黑体）
  T2a-c    计数器数字等宽（font-variant-numeric:tabular-nums）——
           开场统计行 / 图鉴计数 / 筛选 chips 的数字不再随数值变化抖动

与 F11 补丁不同：TYPO 补丁**同时作用于模板与基线**（排版属于产物本身，
与 token 无关），规则集不变、不新增 token。v29 模板在打补丁前冻结为
tests/fixtures/v29_template.html（V29RoundtripTest 随之转为历史回归）。

产出（--check 只比对不落盘）：
  tests/fixtures/v29_template.html  v29 模板冻结快照（历史回归用）
  tests/fixtures/v30_baseline.html  v30 基线（= v29 基线 + TYPO）
  template/starmap.html             v30 token 模板（= v29 模板 + TYPO）
规则文件 nuc_literals.json 不变（TYPO 不新增 token，脚本会断言这点）。

用法：
  python3 tools/make_v30_baseline.py          # 生成
  python3 tools/make_v30_baseline.py --check  # CI 金新鲜度门禁
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
# 排版迭代 v31 起，现役模板 template/starmap.html 归 make_v31 所有；
# 本脚本的模板产物改为落冻结快照，供 V30RoundtripTest 历史回归。
TEMPLATE_PATH = FIX / "v30_template.html"

V29_TEMPLATE = FIX / "v29_template.html"        # 冻结输出（历史回归）
V29_BASELINE = FIX / "v29_baseline.html"        # 上一代输入（勿改）
V29_RULES = FIX / "nuc_literals.json"           # 上一代规则（勿改，本代不变）
V30_BASELINE = FIX / "v30_baseline.html"

_FALLBACK = ("\"HarmonyOS Sans SC\",\"MiSans\",\"Microsoft YaHei\","
             "\"Source Han Sans SC\",\"Noto Sans CJK SC\"")

# 排版补丁：(编号, v29 原文, v30 新形态, 次数)。锚点均唯一（已 grep 核实）。
TYPO_PATCHES: list[tuple[str, str, str, int]] = [
    ("T1a-body-stack",
     '    font-family:"PingFang SC","Microsoft YaHei",sans-serif; }',
     '    font-family:"PingFang SC",' + _FALLBACK + ',sans-serif; }',
     1),
    ("T1b-svg-stack",
     'font-family="PingFang SC,Microsoft YaHei,sans-serif"',
     'font-family="PingFang SC,HarmonyOS Sans SC,MiSans,'
     'Microsoft YaHei,Source Han Sans SC,Noto Sans CJK SC,sans-serif"',
     1),
    ("T2a-chip-counters",
     "  .chip .n{ font-size:9.5px;",
     "  .chip .n{ font-variant-numeric:tabular-nums; font-size:9.5px;",
     1),
    ("T2b-lgseen-counter",
     "  #lgSeen b{ display:block; color:var(--ink); font-size:12.5px;"
     " letter-spacing:.04em; }",
     "  #lgSeen b{ display:block; color:var(--ink); font-size:12.5px;"
     " letter-spacing:.04em; font-variant-numeric:tabular-nums; }",
     1),
    ("T2c-intro-stats",
     "  #intro .stats{ margin-top:16px; color:var(--dim); font-size:11px;"
     " letter-spacing:.24em; white-space:nowrap;",
     "  #intro .stats{ margin-top:16px; color:var(--dim); font-size:11px;"
     " letter-spacing:.24em; white-space:nowrap;"
     " font-variant-numeric:tabular-nums;",
     1),
]


def _apply(text: str, patches, tag: str) -> str:
    for name, old, new, expected in patches:
        actual = text.count(old)
        if actual != expected:
            raise SystemExit(
                f"TYPO 补丁 {name} 在 {tag} 出现 {actual} 次，预期 {expected}")
        text = text.replace(old, new)
    return text


def main() -> int:
    check = "--check" in sys.argv

    v29_template = V29_TEMPLATE.read_text("utf-8") \
        if V29_TEMPLATE.exists() else (REPO / "template" / "starmap.html").read_text("utf-8")
    v29_baseline = V29_BASELINE.read_text("utf-8")
    v29_rules = json.loads(V29_RULES.read_text("utf-8"))["rules"]

    # 冻结 v29 模板快照（首次运行时落盘；--check 时只要求已存在）
    if not check and not V29_TEMPLATE.exists():
        V29_TEMPLATE.write_text(v29_template, encoding="utf-8")
    if not V29_TEMPLATE.exists():
        raise SystemExit("缺 fixtures/v29_template.html 冻结快照")

    # 模板与基线同步应用 TYPO 补丁（次数逐一断言）
    template = _apply(v29_template, TYPO_PATCHES, "v29 模板")
    baseline = _apply(v29_baseline, TYPO_PATCHES, "v29 基线")

    # 自验 1：F11 三 token 与数据块 token 全部原样保留
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__",
                  "__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__"):
        if template.count(token) != 1:
            raise SystemExit(f"v30 模板 token {token} 次数 ≠ 1")

    # 自验 2：规则集规模不变（TYPO 不新增 token、不碰规则；名字集完整性
    # 由自验 3 的整链往返兜底——任何一条失配都会在灌回时暴露）
    if len(v29_rules) != 55:
        raise SystemExit(
            f"v29 规则数 {len(v29_rules)} ≠ 55——规则变了要升级本脚本")

    # 自验 3：模板正序灌回全部规则 == v30 基线（字节往返）
    filled = template
    for r in v29_rules:
        filled = filled.replace(r["new"], r["old"])
    if filled != baseline:
        for i, (a, b) in enumerate(zip(filled, baseline)):
            if a != b:
                raise SystemExit(
                    f"v30 灌回与基线首个差异在偏移 {i}：\n"
                    f"  灌回={filled[max(0, i - 40):i + 40]!r}\n"
                    f"  基线={baseline[max(0, i - 40):i + 40]!r}")
        raise SystemExit(
            f"v30 灌回与基线长度不同：{len(filled)} vs {len(baseline)}")

    # 自验 4（F11 红线的 v30 形态）：空 F11 渲染 == v29 模板 + TYPO（同样去 token）
    empty = template
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        empty = empty.replace(token, "")
    v29_with_typo = _apply(
        V29_TEMPLATE.read_text("utf-8"), TYPO_PATCHES, "冻结 v29 模板")
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        v29_with_typo = v29_with_typo.replace(token, "")
    if empty != v29_with_typo:
        raise SystemExit("F11 空值路径与「v29 模板 + TYPO」不一致")

    outputs = {
        V30_BASELINE: baseline,
        TEMPLATE_PATH: template,
    }
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists() or path.read_text("utf-8") != content:
                drift.append(str(path.relative_to(REPO)))
        if drift:
            print("v30 golden 漂移，请运行 python3 tools/make_v30_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print("v30 golden 新鲜：baseline/template 均与补丁脚本一致；"
              "F11 空值路径 == v29 模板 + TYPO")
        return 0

    for path, content in outputs.items():
        path.write_text(content, "utf-8")
    print(f"v30 baseline : {V30_BASELINE}（{baseline.count(chr(10))+1} 行）")
    print(f"v30 template : {TEMPLATE_PATH}（{template.count(chr(10))+1} 行，"
          f"{len(TYPO_PATCHES)} 个排版补丁）")
    print("自验：灌回规则 == 基线；F11 空值渲染 == v29 模板 + TYPO ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
