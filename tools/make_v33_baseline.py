#!/usr/bin/env python3
"""v32 → v33 golden：backdrop-filter 补 -webkit- 前缀（Safari 毛玻璃，确定性补丁）。

iOS/macOS Safari 至今只认 `-webkit-backdrop-filter`（Blink 系两条都认）。
v32 模板有 17 处标准 `backdrop-filter:blur(...)`，其中只有 2 处带前缀
（674/716 行的顶栏与底部条），其余 15 处面板在 Safari 上背景完全不糊,
直接透出满亮度底图 → 面板文字对比度掉底。这就是迭代 4 候选里说的
「v33 Safari 毛玻璃补丁」（另 1 处在 gallery/index.html，非模板、不在本
golden 链内，由 tests/test_css_compat_prefixes.py 统一看守）。

前缀一律加在标准声明**之后**（`标准; -webkit-标准;`），与 v32 已有的 2 处
写法保持一致；两条值逐字符相同，顺序不改变任何引擎的计算值。

引擎实测（2026-09-23，19_全库深扫报告_20260918/v33前缀生效实测.py）：
Chromium 忽略前缀（计算值 none、像素零变化），headless WebKit 解析前缀但
不落笔绘制 → 本补丁在可自动化验证的引擎上**不可能造成观感回归**，
Safari 真机收益仍需人类在手机上看一眼（红线：不可验证处要写明）。

产出（--check 只比对不落盘）：
  tests/fixtures/v32_template.html  v32 模板冻结快照（历史回归用）
  tests/fixtures/v33_baseline.html  v33 基线（= v32 基线 + U3）
  template/starmap.html             v33 token 模板（= v32 模板 + U3）

用法：
  python3 tools/make_v33_baseline.py          # 生成
  python3 tools/make_v33_baseline.py --check  # CI 金新鲜度门禁
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
# v34 起 template/starmap.html 归 make_v34 独占写；本代的模板产物即此冻结件
TEMPLATE_PATH = FIX / "v33_template.html"

V32_TEMPLATE = FIX / "v32_template.html"        # 冻结输出（历史回归）
V32_BASELINE = FIX / "v32_baseline.html"        # 上一代输入（勿改）
V32_RULES = FIX / "nuc_literals.v33.json"       # 规则集不变（v34 起冻结；nuc_literals.json 归 make_v34）
V33_BASELINE = FIX / "v33_baseline.html"

# 本代不碰的 token 集（与 v29~v32 一致）
TOKENS = ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__",
          "__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__")

# 一条标准毛玻璃声明：`backdrop-filter:blur(12px);` 或带 saturate 的第二参。
# 前置 (?<!-webkit-) 排除已有的前缀行，否则会把 `-webkit-backdrop-filter:`
# 当成标准声明二次配对（前缀串以 `backdrop-filter:` 结尾，是真实翻车点）。
_DECL = re.compile(
    r'(?<!-webkit-)'
    r'(backdrop-filter:blur\([0-9.]+px\)(?: saturate\([0-9.]+\))?;)')
# 未配对的声明：后面没有紧跟 ` -webkit-` 同值声明。补丁只作用于这一部分，
# 因此对已打好补丁的文本重跑会命中 0 处并立即报错（幂等保护）。
_UNPAIRED = re.compile(_DECL.pattern + r'(?! -webkit-backdrop-filter:)')

# v32 现状逐值清点（由 grep -oE 'backdrop-filter:[^;}]*' 数出，改一处即断言失败）
V32_EXPECT: dict[str, int] = {
    "backdrop-filter:blur(14px) saturate(1.2);": 1,
    "backdrop-filter:blur(14px);": 2,
    "backdrop-filter:blur(12px);": 6,
    "backdrop-filter:blur(10px);": 4,
    "backdrop-filter:blur(8px);": 2,
    "backdrop-filter:blur(7px);": 1,
    "backdrop-filter:blur(6px);": 1,
}
STD_TOTAL = sum(V32_EXPECT.values())            # 17
V32_PAIRED = 2                                  # 674/716 行已带前缀
U3_COUNT = STD_TOTAL - V32_PAIRED               # 15 处待补


def _check_inventory(text: str, tag: str, expect: dict[str, int]) -> None:
    got = Counter(_DECL.findall(text))
    if dict(got) != expect:
        diff = ", ".join(
            f"{v}: {got[v]}≠{n}" for v, n in expect.items() if got[v] != n)
        raise SystemExit(
            f"U3 毛玻璃声明清点与预期不符（{tag}）：{diff}\n"
            f"  实测 {dict(got)}\n"
            f"  预期 {expect}\n"
            f"  → 有人增删/改值了 backdrop-filter，请同步升级本脚本预期")


def apply_u3(text: str, tag: str) -> str:
    """给全部未配对声明补同值 -webkit- 前缀，前后各断言一次。"""
    _check_inventory(text, f"补丁前 {tag}", V32_EXPECT)
    missing = _UNPAIRED.findall(text)
    if len(missing) != U3_COUNT:
        raise SystemExit(
            f"U3 在 {tag} 命中未配对声明 {len(missing)} 处，预期 {U3_COUNT} 处"
            f"（基座可能已打过补丁或已漂移）")
    out = _UNPAIRED.sub(lambda m: m.group(1) + " -webkit-" + m.group(1), text)
    # 终态：值分布不变（U3 只增前缀不改值），且再无未配对、前缀数 == 标准数
    _check_inventory(out, f"补丁后 {tag}", V32_EXPECT)
    if len(_UNPAIRED.findall(out)) != 0:
        raise SystemExit(f"U3 在 {tag} 打完补丁仍有未配对声明")
    if out.count("-webkit-backdrop-filter:") != STD_TOTAL:
        raise SystemExit(
            f"U3 后 {tag} 前缀声明 {out.count('-webkit-backdrop-filter:')} 处 "
            f"≠ 标准声明 {STD_TOTAL} 处")
    return out


def _fill(template: str, rules: list[dict]) -> str:
    """模板正序灌回规则 → 基线形态（v33 与 v32 共用同一规则集）。"""
    text = template
    for r in rules:
        text = text.replace(r["new"], r["old"])
    return text


# 🔴 换行纪律：本仓 .gitattributes 是 `* text=auto eol=lf`，工作树必须是 LF。
# Path.write_text 在 Windows 上会把 \n 翻成 \r\n（整整 3376 行伪 diff），
# 所以这里一律 read_bytes/write_bytes 手工定换行；读到 CRLF 就报警并归一。
class _NL:
    def __init__(self, crlf: int) -> None:
        self.crlf = crlf


def _read(path: Path) -> tuple[str, _NL]:
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    if crlf:
        print(f"⚠️ {path.relative_to(REPO)} 工作树含 {crlf} 处 CRLF，"
              f"已按 eol=lf 归一（本仓规定 LF）")
    return raw.replace(b"\r\n", b"\n").decode("utf-8"), _NL(crlf)


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def main() -> int:
    check = "--check" in sys.argv

    v32_baseline, _ = _read(V32_BASELINE)
    v32_rules = json.loads(V32_RULES.read_text("utf-8"))["rules"]

    if not V32_TEMPLATE.exists():
        raise SystemExit("缺 fixtures/v32_template.html 冻结快照——"
                         "活模板已是 v34，请从 git 历史恢复 v32 冻结件，"
                         "不得从现役模板重冻")
    v32_template, nl32 = _read(V32_TEMPLATE)
    if not check and nl32.crlf:
        _write(V32_TEMPLATE, v32_template)      # 只换换行，内容不动

    # 自验 0（防「冻结件过期 → 本地假绿」，AGENTS 红线 2 的元凶）：
    # 冻结的 v32 模板正序灌回规则必须 == v32 基线。若 template/starmap.html
    # 已被改过而忘了重冻，这条会红。
    if _fill(v32_template, v32_rules) != v32_baseline:
        raise SystemExit(
            "fixtures/v32_template.html 与 v32_baseline.html 不自洽（灌回规则"
            " ≠ 基线）——冻结件是旧内容。删除它重跑本脚本以重新冻结。")
    # 冻结件必须是「未打补丁的 v32」，不能是已含前缀的 v33 副本
    if len(_UNPAIRED.findall(v32_template)) != U3_COUNT:
        raise SystemExit(
            "fixtures/v32_template.html 里未配对毛玻璃声明数不是 "
            f"{U3_COUNT} —— 冻结件已被 U3 污染，请删除后重新冻结。")

    template = apply_u3(v32_template, "v32 模板")
    baseline = apply_u3(v32_baseline, "v32 基线")

    # 自验 1：token 全部原样保留（U3 不新增 token）
    for token in TOKENS:
        if template.count(token) != 1:
            raise SystemExit(f"v33 模板 token {token} 次数 ≠ 1")

    # 自验 2：规则集规模不变
    if len(v32_rules) != 55:
        raise SystemExit(
            f"v32 规则数 {len(v32_rules)} ≠ 55——规则变了要升级本脚本")

    # 自验 3：模板正序灌回全部规则 == v33 基线（字节往返）
    filled = _fill(template, v32_rules)
    if filled != baseline:
        for i, (a, b) in enumerate(zip(filled, baseline)):
            if a != b:
                raise SystemExit(
                    f"v33 灌回与基线首个差异在偏移 {i}：\n"
                    f"  灌回={filled[max(0, i - 40):i + 40]!r}\n"
                    f"  基线={baseline[max(0, i - 40):i + 40]!r}")
        raise SystemExit(
            f"v33 灌回与基线长度不同：{len(filled)} vs {len(baseline)}")

    # 自验 4（F11 红线的 v33 形态）：空 F11 渲染 == v32 模板 + U3
    empty = template
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        empty = empty.replace(token, "")
    v32_with_u3 = apply_u3(v32_template, "冻结 v32 模板")
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        v32_with_u3 = v32_with_u3.replace(token, "")
    if empty != v32_with_u3:
        raise SystemExit("F11 空值路径与「v32 模板 + U3」不一致")

    outputs = {V33_BASELINE: baseline, TEMPLATE_PATH: template}
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists():
                drift.append(f"{path.relative_to(REPO)}（不存在）")
                continue
            on_disk, nl = _read(path)
            if on_disk != content:
                drift.append(f"{path.relative_to(REPO)}（内容与 U3 补丁不符）")
            elif nl.crlf:
                drift.append(f"{path.relative_to(REPO)}（{nl.crlf} 处 CRLF，"
                             f"违反 eol=lf）")
        if drift:
            print("v33 golden 漂移，请运行 python3 tools/make_v33_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print(f"v33 golden 新鲜：baseline/template 均与 U3 补丁一致（"
              f"{STD_TOTAL} 处标准 + {STD_TOTAL} 处前缀）、工作树 LF；"
              "冻结件自洽；F11 空值路径 == v32 模板 + U3")
        return 0

    for path, content in outputs.items():
        _write(path, content)
    print(f"v33 baseline : {V33_BASELINE.relative_to(REPO)}"
          f"（{baseline.count(chr(10)) + 1} 行）")
    print(f"v33 template : {TEMPLATE_PATH.relative_to(REPO)}"
          f"（{template.count(chr(10)) + 1} 行，U3 补 {U3_COUNT} 处前缀）")
    print(f"v32 冻结件   : {V32_TEMPLATE.relative_to(REPO)}（历史回归基座）")
    print("自验：冻结件灌回==v32基线；U3 逐值清点；灌回规则==基线；"
          "F11 空值渲染==v32模板+U3 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
