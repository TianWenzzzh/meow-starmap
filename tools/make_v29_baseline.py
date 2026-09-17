#!/usr/bin/env python3
"""v28-lazy → v29 golden：合入 F11 主题/校徽三 token（确定性补丁，可重跑）。

v29 相对 v28 的唯一变化是三个 F11 扩展锚点（为 T6 工厂收敛预备）：
  __THEME_CSS__    自定义主题 CSS（空串=v28 默认观感）
  __LOGO_INTRO__   极光开场校徽位（空串=无校徽）
  __LOGO_TOPBAR__  顶栏品牌校徽位（空串=无校徽）

与 v28 加载器补丁不同：这三个 token **只加进模板，不加进基线**——基线是
中北产物（F11 全空），保持 v28 原文；规则记录「锚点原文 ↔ 锚点+token」。
token 全部紧贴锚点、无额外空白，因此空串注入逐字节还原 v28。

产出（--check 只比对不落盘）：
  tests/fixtures/v29_baseline.html  中北 v29 基线（F11 空值，字节 == v28 基线）
  tests/fixtures/nuc_literals.json  v29 规则（v28 规则 + 3 条 F11）
  template/starmap.html             v29 token 模板
另存 v28 模板快照 tests/fixtures/v28_template_lazy.html（历史回归用）。

用法：
  python3 tools/make_v29_baseline.py          # 生成
  python3 tools/make_v29_baseline.py --check  # CI 金新鲜度门禁
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
# T6 F7/排版迭代起，现役模板 template/starmap.html 归 make_v30 所有；
# 本脚本的模板产物改为落冻结快照，供 V29RoundtripTest 历史回归。
TEMPLATE_PATH = FIX / "v29_template.html"

V28_TEMPLATE = FIX / "v28_template_lazy.html"
V28_BASELINE = FIX / "v28_baseline_lazy.html"
V28_RULES = FIX / "nuc_literals.v28.json"   # 上一代冻结快照（勿指向输出文件）
V29_BASELINE = FIX / "v29_baseline.html"
V29_RULES_OUT = FIX / "nuc_literals.json"

# F11 token 补丁：只作用于模板。(name, v28 锚点原文, 模板新形态, 次数)
# 锚点在 v28 模板/基线均唯一（已 grep 核实）。
F11_PATCHES: list[tuple[str, str, str, int]] = [
    ("theme_css",
     "</style>",
     "</style>__THEME_CSS__",
     1),
    ("logo_intro",
     '<div id="intro">',
     '<div id="intro">__LOGO_INTRO__',
     1),
    ("logo_topbar",
     '<div class="brand">',
     '<div class="brand">__LOGO_TOPBAR__',
     1),
]


def main() -> int:
    check = "--check" in sys.argv

    v28_template = V28_TEMPLATE.read_text("utf-8")
    v28_baseline = V28_BASELINE.read_text("utf-8")
    v28_rules = json.loads(V28_RULES.read_text("utf-8"))["rules"]

    # 模板：逐个应用 F11 token 补丁（次数断言）
    template = v28_template
    for name, old, new, expected in F11_PATCHES:
        actual = template.count(old)
        if actual != expected:
            raise SystemExit(
                f"F11 补丁 {name} 在 v28 模板出现 {actual} 次，预期 {expected}")
        template = template.replace(old, new)

    # 基线：F11 空值，保持 v28 原文一字不动
    baseline = v28_baseline

    # 规则：v28 规则 + 3 条 F11（old=中北锚点原文，new=模板 token 形态）
    rules = [dict(r) for r in v28_rules]
    existing = {r["name"] for r in rules}
    for name, old, new, expected in F11_PATCHES:
        if name in existing:
            raise SystemExit(f"规则 {name} 已存在，F11 追加冲突")
        if baseline.count(old) != expected:
            raise SystemExit(
                f"F11 规则 {name} 的 old 在 v28 基线出现 "
                f"{baseline.count(old)} 次，预期 {expected}")
        rules.append({"name": name, "old": old, "new": new,
                      "count": expected})

    # 自验 1：模板里三个 token 都在；基线里一个都没有（空值真相）
    for _, _, new, _ in F11_PATCHES:
        token = new.split("__", 1)[1].rsplit("__", 1)[0]
        token_full = "__" + token + "__"
        if token_full not in template:
            raise SystemExit(f"v29 模板缺少 {token_full}")
        if token_full in baseline:
            raise SystemExit(f"v29 基线（空值）不应含 {token_full}")

    # 自验 2：模板正序灌回全部规则 == v29 基线（字节往返）
    filled = template
    for r in rules:
        if filled.count(r["new"]) != int(r["count"]):
            raise SystemExit(
                f"v29 规则 {r['name']} token 次数 {filled.count(r['new'])} "
                f"≠ 凭据 {r['count']}")
        filled = filled.replace(r["new"], r["old"])
    if filled != baseline:
        # 定位首个差异便于排错
        for i, (a, b) in enumerate(zip(filled, baseline)):
            if a != b:
                ctx_f = filled[max(0, i - 40):i + 40]
                ctx_b = baseline[max(0, i - 40):i + 40]
                raise SystemExit(
                    f"v29 灌回与基线首个差异在偏移 {i}：\n  灌回={ctx_f!r}\n"
                    f"  基线={ctx_b!r}")
        raise SystemExit(
            f"v29 灌回与基线长度不同：{len(filled)} vs {len(baseline)}")

    # 自验 3（核心红线）：空 F11 渲染后 v29 中北产物 == v28 中北产物
    empty = template
    for _, _, new, _ in F11_PATCHES:
        token = "__" + new.split("__", 1)[1].rsplit("__", 1)[0] + "__"
        empty = empty.replace(token, "")
    if empty != v28_template:
        raise SystemExit(
            "F11 空值路径与 v28 模板不字节一致——token 锚点引入了额外字符")

    rules_json = json.dumps({"rules": rules}, ensure_ascii=False, indent=2)
    outputs = {
        V29_BASELINE: baseline,
        V29_RULES_OUT: rules_json + "\n",
        TEMPLATE_PATH: template,
    }
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists() or path.read_text("utf-8") != content:
                drift.append(str(path.relative_to(REPO)))
        if drift:
            print("v29 golden 漂移，请运行 python3 tools/make_v29_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print("v29 golden 新鲜：baseline/rules/template 均与补丁脚本一致；"
              "空值路径 == v28")
        return 0

    for path, content in outputs.items():
        path.write_text(content, "utf-8")
    print(f"v29 baseline : {V29_BASELINE}（{baseline.count(chr(10))+1} 行，"
          f"== v28 基线 {V28_BASELINE.name}）")
    print(f"v29 rules    : {V29_RULES_OUT}（{len(rules)} 条 = v28 {len(v28_rules)} + F11×3）")
    print(f"v29 template : {TEMPLATE_PATH}（{template.count(chr(10))+1} 行）")
    print("自验：模板灌回规则 == 基线；F11 空值渲染 == v28 模板 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
