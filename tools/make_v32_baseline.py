#!/usr/bin/env python3
"""v31 → v32 golden：canvas/SVG 导出字体栈补全（确定性补丁，可重跑）。

迭代 2 审计（tools/audit_typography.py）发现：v31 只给 CSS 补了字体兜底，
而 canvas 导出图（喵星护照 FT / 分享卡 _FT / 灯箱 / 海报）的 44 处字体赋值
仍是 `"PingFang SC","Microsoft YaHei"` 裸栈——装有 HarmonyOS/MiSans 的
Windows 设备与 Linux 上，页面文字与导出图字体不一致（后者跌回系统默认）。

v32 相对 v31 的唯一变化是 5 个 U2 补丁（YaHei 之后追加系统兜底，
macOS/Windows 首选不变 → 零观感回归；离线红线不破）：
  U2a/U2b  FT 与 _FT 字体栈常量（一处覆盖 27 处导出赋值）
  U2c      动态拼接+尾 sans-serif 形态（2 处）
  U2d      静态无尾形态（14 处）
  U2e      单引号栈形态（1 处）

字号档位经全量审计判定为**全部保留**（见 docs/迭代2-字号档位评审.md），
本代不动任何 font-size。

与 v31 的 TYPO 补丁一样：U2 **同时作用于模板与基线**（导出渲染属于产物
本身，与 token 无关），规则集不变、不新增 token。v31 模板在打补丁前冻结为
tests/fixtures/v31_template.html（V31RoundtripTest 随之转为历史回归）。

产出（--check 只比对不落盘）：
  tests/fixtures/v31_template.html  v31 模板冻结快照（历史回归用）
  tests/fixtures/v32_baseline.html  v32 基线（= v31 基线 + U2）
  template/starmap.html             v32 token 模板（= v31 模板 + U2）

用法：
  python3 tools/make_v32_baseline.py          # 生成
  python3 tools/make_v32_baseline.py --check  # CI 金新鲜度门禁
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
TEMPLATE_PATH = REPO / "template" / "starmap.html"

V31_TEMPLATE = FIX / "v31_template.html"        # 冻结输出（历史回归）
V31_BASELINE = FIX / "v31_baseline.html"        # 上一代输入（勿改）
V31_RULES = FIX / "nuc_literals.json"           # 上一代规则（勿改，本代不变）
V32_BASELINE = FIX / "v32_baseline.html"

# v31 CSS 栈已定的兜底序列（与 make_v31_baseline._FALLBACK 保持一致）
_FALLBACK = ('"HarmonyOS Sans SC","MiSans","Source Han Sans SC",'
             '"Noto Sans CJK SC"')
_FALLBACK_SQ = ("'HarmonyOS Sans SC','MiSans','Source Han Sans SC',"
                "'Noto Sans CJK SC'")

# canvas 字体栈补丁：(编号, v31 原文, v32 新形态, 次数)。次数为全文件精确计数，
# 由审计工具清点得出；补丁同时在模板与基线上断言。
U2_PATCHES: list[tuple[str, str, str, int]] = [
    # 喵星护照导出字体栈常量（27 处 '... '+FT 赋值的唯一来源）；
    # 锚点带前导空格边界——否则 `FT=` 会命中 `_FT=` 子串
    ("U2a-FT-const",
     ' FT=\'"PingFang SC","Microsoft YaHei",sans-serif\'',
     ' FT=\'"PingFang SC","Microsoft YaHei",' + _FALLBACK + ',sans-serif\'',
     1),
    # 分享卡导出字体栈常量（27 处 '... '+_FT 赋值的唯一来源）
    ("U2b-_FT-const",
     '_FT=\'"PingFang SC","Microsoft YaHei",sans-serif\'',
     '_FT=\'"PingFang SC","Microsoft YaHei",' + _FALLBACK + ',sans-serif\'',
     1),
    # 动态拼接 + 尾 sans-serif（灯箱/海报标题渲染）
    ("U2c-dynamic-tail",
     'px "PingFang SC","Microsoft YaHei",sans-serif\'',
     'px "PingFang SC","Microsoft YaHei",' + _FALLBACK + ',sans-serif\'',
     2),
    # 静态无尾双引号栈
    ("U2d-static-plain",
     'px "PingFang SC","Microsoft YaHei"\'',
     'px "PingFang SC","Microsoft YaHei",' + _FALLBACK + '\'',
     14),
    # 单引号栈（寻猫海报 DOM 预览）
    ("U2e-single-quoted",
     "\"12px 'PingFang SC','Microsoft YaHei'\"",
     "\"12px 'PingFang SC','Microsoft YaHei'," + _FALLBACK_SQ + "\"",
     1),
]


def _apply(text: str, patches, tag: str) -> str:
    for name, old, new, expected in patches:
        actual = text.count(old)
        if actual != expected:
            raise SystemExit(
                f"U2 补丁 {name} 在 {tag} 出现 {actual} 次，预期 {expected}")
        text = text.replace(old, new)
    return text


def main() -> int:
    check = "--check" in sys.argv

    v31_template = V31_TEMPLATE.read_text("utf-8") \
        if V31_TEMPLATE.exists() else TEMPLATE_PATH.read_text("utf-8")
    v31_baseline = V31_BASELINE.read_text("utf-8")
    v31_rules = json.loads(V31_RULES.read_text("utf-8"))["rules"]

    # 冻结 v31 模板快照（首次运行时落盘；--check 时只要求已存在）
    if not check and not V31_TEMPLATE.exists():
        V31_TEMPLATE.write_text(v31_template, encoding="utf-8")
    if not V31_TEMPLATE.exists():
        raise SystemExit("缺 fixtures/v31_template.html 冻结快照")

    # 模板与基线同步应用 U2 补丁（次数逐一断言——任何一处漂移立即失败）
    template = _apply(v31_template, U2_PATCHES, "v31 模板")
    baseline = _apply(v31_baseline, U2_PATCHES, "v31 基线")

    # 自验 1：F11 三 token 与数据块 token 全部原样保留
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__",
                  "__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__"):
        if template.count(token) != 1:
            raise SystemExit(f"v32 模板 token {token} 次数 ≠ 1")

    # 自验 2：规则集规模不变（U2 不新增 token、不碰规则；名字集完整性
    # 由自验 3 的整链往返兜底——任何一条失配都会在灌回时暴露）
    if len(v31_rules) != 55:
        raise SystemExit(
            f"v31 规则数 {len(v31_rules)} ≠ 55——规则变了要升级本脚本")

    # 自验 3：模板正序灌回全部规则 == v32 基线（字节往返）
    filled = template
    for r in v31_rules:
        filled = filled.replace(r["new"], r["old"])
    if filled != baseline:
        for i, (a, b) in enumerate(zip(filled, baseline)):
            if a != b:
                raise SystemExit(
                    f"v32 灌回与基线首个差异在偏移 {i}：\n"
                    f"  灌回={filled[max(0, i - 40):i + 40]!r}\n"
                    f"  基线={baseline[max(0, i - 40):i + 40]!r}")
        raise SystemExit(
            f"v32 灌回与基线长度不同：{len(filled)} vs {len(baseline)}")

    # 自验 4（F11 红线的 v32 形态）：空 F11 渲染 == v31 模板 + U2（同样去 token）
    empty = template
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        empty = empty.replace(token, "")
    v31_with_u2 = _apply(
        V31_TEMPLATE.read_text("utf-8"), U2_PATCHES, "冻结 v31 模板")
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        v31_with_u2 = v31_with_u2.replace(token, "")
    if empty != v31_with_u2:
        raise SystemExit("F11 空值路径与「v31 模板 + U2」不一致")

    outputs = {
        V32_BASELINE: baseline,
        TEMPLATE_PATH: template,
    }
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists() or path.read_text("utf-8") != content:
                drift.append(str(path.relative_to(REPO)))
        if drift:
            print("v32 golden 漂移，请运行 python3 tools/make_v32_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print("v32 golden 新鲜：baseline/template 均与补丁脚本一致；"
              "F11 空值路径 == v31 模板 + U2")
        return 0

    for path, content in outputs.items():
        path.write_text(content, "utf-8")
    print(f"v32 baseline : {V32_BASELINE}（{baseline.count(chr(10))+1} 行）")
    print(f"v32 template : {TEMPLATE_PATH}（{template.count(chr(10))+1} 行，"
          f"{len(U2_PATCHES)} 个 canvas 字体栈补丁）")
    print("自验：灌回规则 == 基线；F11 空值渲染 == v31 模板 + U2 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
