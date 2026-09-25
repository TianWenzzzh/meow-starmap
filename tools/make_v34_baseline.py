#!/usr/bin/env python3
"""v33 → v34 golden：basePos 建成区框 STAR_BOX（确定性补丁）。

v34 相对 v33 的唯一模板变化：星位撒点从整幅画写死四个常量改为读一个
可选框 STAR_BOX（缺省值 == v33 的四个常量 ⇒ 不设 star_box 的学校产物
在渲染参数意义上逐字节不变）。星位仍由 mulberry32(hashStr(cat.id))
确定性推导，只是取值域从整幅画收窄到框内。

模板侧令牌落在裸行（`__STAR_BOX__` 独占一行，注释行单列其上）——
常量若被 `/* */` 裹住就成了死代码，页面会 ReferenceError，这是本代
补丁刻意绕开的坑。

产出（--check 只比对不落盘）：
  tests/fixtures/v33_template.html  v33 模板冻结快照（历史回归用，新增）
  tests/fixtures/v34_baseline.html  v34 基线（= v33 基线 + U4）
  tests/fixtures/nuc_literals.json  v34 规则（= v33 规则 + star_box 一条）
  template/starmap.html             v34 token 模板（= v33 模板 + U4）

用法：
  python3 tools/make_v34_baseline.py          # 生成
  python3 tools/make_v34_baseline.py --check  # CI 金新鲜度门禁
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
TEMPLATE_PATH = REPO / "template" / "starmap.html"   # 现役，归本脚本独占写

V33_TEMPLATE = FIX / "v33_template.html"        # 冻结输出（历史回归）
V33_BASELINE = FIX / "v33_baseline.html"        # 上一代输入（勿改）
V33_RULES = FIX / "nuc_literals.v33.json"       # 上一代冻结规则（勿改）
V34_BASELINE = FIX / "v34_baseline.html"
V34_RULES_OUT = FIX / "nuc_literals.json"       # 从此代表 v34（+star_box 一条）

# 本代不碰的 token 集（v29~v33 同款 + 本代新增）
TOKENS = ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__",
          "__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__",
          "__STAR_BOX__")

# U4 补丁：只动 basePos 这一处。逐值清点（出现次数必须恰为 1，否则 raise）。
U4_OLD = ("function basePos(cat){ const r=mulberry32(hashStr(cat.id));\n"
          "  return { x:.07+r()*.86, y:.09+r()*.82 }; }")
U4_COMMENT = "/* 建成区框：basePos 只在此框内撒点（v34 起；缺省=下行四常量，同 v33） */"
U4_CONST = "const STAR_BOX={x0:.07,y0:.09,w:.86,h:.82};"   # = 渲染层缺省字面量
U4_TOKEN = "__STAR_BOX__"
U4_NEW_BASEPOS = ("function basePos(cat){ const r=mulberry32(hashStr(cat.id));\n"
                  "  return { x:STAR_BOX.x0+r()*STAR_BOX.w, "
                  "y:STAR_BOX.y0+r()*STAR_BOX.h }; }")

STAR_BOX_RULE = {"name": "star_box", "old": U4_CONST, "new": U4_TOKEN,
                 "count": 1}


def apply_u4(text: str, tag: str, token_form: bool) -> str:
    """basePos 换成读框形态；模板侧插 token 裸行，基线侧插缺省字面量。"""
    if "STAR_BOX" in text:
        raise SystemExit(f"U4 前的 {tag} 已含 STAR_BOX——基座可能已打过补丁")
    n = text.count(U4_OLD)
    if n != 1:
        raise SystemExit(f"U4 在 {tag} 命中 basePos 老块 {n} 处，必须恰好 1 处"
                         f"（基座已漂移，禁止盲改）")
    insert = "\n".join([
        U4_COMMENT,
        U4_TOKEN if token_form else U4_CONST,
        U4_NEW_BASEPOS,
    ])
    out = text.replace(U4_OLD, insert)
    # 终态逐值清点：token/字面量、新 basePos 各恰 1 处，且互斥（防死代码形态）
    if token_form:
        if out.count(U4_TOKEN) != 1 or U4_CONST in out:
            raise SystemExit(f"U4 后 {tag} token 形态清点不符")
    else:
        if out.count(U4_CONST) != 1 or U4_TOKEN in out:
            raise SystemExit(f"U4 后 {tag} 字面量形态清点不符")
    if out.count(U4_NEW_BASEPOS) != 1 or U4_OLD in out:
        raise SystemExit(f"U4 后 {tag} basePos 新形态清点不符")
    return out


def _fill(template: str, rules: list[dict]) -> str:
    """模板正序灌回规则 → 基线形态。"""
    text = template
    for r in rules:
        text = text.replace(r["new"], r["old"])
    return text


# 🔴 换行纪律：本仓 .gitattributes 是 `* text=auto eol=lf`，工作树必须是 LF。
# Path.write_text 在 Windows 上会把 \n 翻成 \r\n（整份文件伪 diff），
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

    v33_baseline, _ = _read(V33_BASELINE)
    v33_rules = json.loads(V33_RULES.read_text("utf-8"))["rules"]

    if not V33_TEMPLATE.exists():
        raise SystemExit("缺 fixtures/v33_template.html 冻结快照——"
                         "活模板已是 v34，不得从现役模板重冻 v33；"
                         "请从 git 历史（16 仓 v1.7.0 的 template/starmap.html）恢复")
    v33_template, nl33 = _read(V33_TEMPLATE)
    if not check and nl33.crlf:
        _write(V33_TEMPLATE, v33_template)      # 只换换行，内容不动

    # 自验 0（防「冻结件过期 → 本地假绿」，v33 代已踩过的坑）：
    # 冻结的 v33 模板正序灌回 v33 规则必须 == v33 基线。若冻结件是旧内容
    # 或已被 U4 污染，这条会红。
    if _fill(v33_template, v33_rules) != v33_baseline:
        raise SystemExit(
            "fixtures/v33_template.html 与 v33_baseline.html 不自洽（灌回规则"
            " ≠ 基线）——冻结件是旧内容。删除它重跑本脚本以重新冻结。")
    # 冻结件必须是「未打补丁的 v33」，不得已含 STAR_BOX
    for tag, text in (("冻结 v33 模板", v33_template), ("v33 基线", v33_baseline)):
        if "STAR_BOX" in text:
            raise SystemExit(f"{tag} 已含 STAR_BOX——冻结件被 U4 污染，"
                             f"请删除后重新冻结。")

    template = apply_u4(v33_template, "v33 模板", token_form=True)
    baseline = apply_u4(v33_baseline, "v33 基线", token_form=False)

    # 自验 1：token 全部恰 1 处（含本代新增）
    for token in TOKENS:
        if template.count(token) != 1:
            raise SystemExit(f"v34 模板 token {token} 次数 ≠ 1")

    # 自验 2：规则集恰好多一条，且就是 star_box 挂尾
    if not v33_rules:
        raise SystemExit("v33 规则集为空？")
    v34_rules = v33_rules + [dict(STAR_BOX_RULE)]
    if v34_rules[-1]["name"] != "star_box" or len(v34_rules) != len(v33_rules) + 1:
        raise SystemExit("v34 规则追加形态不符")

    # 自验 3：模板正序灌回全部规则 == v34 基线（字节往返）
    filled = _fill(template, v34_rules)
    if filled != baseline:
        for i, (a, b) in enumerate(zip(filled, baseline)):
            if a != b:
                raise SystemExit(
                    f"v34 灌回与基线首个差异在偏移 {i}：\n"
                    f"  灌回={filled[max(0, i - 40):i + 40]!r}\n"
                    f"  基线={baseline[max(0, i - 40):i + 40]!r}")
        raise SystemExit(
            f"v34 灌回与基线长度不同：{len(filled)} vs {len(baseline)}")

    # 自验 3b（默认 STAR_BOX 灌回 == v33 基线 + U4）：基线侧补丁与模板侧
    # 灌回两条推导路径必须字节相同，缺省字面量与渲染层缺省值一致。
    if baseline != filled or U4_CONST not in baseline:
        raise SystemExit("默认 STAR_BOX 灌回与「v33 基线 + U4」不一致")

    # 自验 4（F11 红线的 v34 形态）：F11 空 token 渲染 == v33 模板 + U4（F11 空）
    empty = template
    v33_with_u4 = apply_u4(v33_template, "冻结 v33 模板", token_form=True)
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        empty = empty.replace(token, "")
        v33_with_u4 = v33_with_u4.replace(token, "")
    if empty != v33_with_u4:
        raise SystemExit("F11 空值路径与「v33 模板 + U4」不一致")

    outputs = {V34_BASELINE: baseline, TEMPLATE_PATH: template}
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists():
                drift.append(f"{path.relative_to(REPO)}（不存在）")
                continue
            on_disk, nl = _read(path)
            if on_disk != content:
                drift.append(f"{path.relative_to(REPO)}（内容与 U4 补丁不符）")
            elif nl.crlf:
                drift.append(f"{path.relative_to(REPO)}（{nl.crlf} 处 CRLF，"
                             f"违反 eol=lf）")
        if drift:
            print("v34 golden 漂移，请运行 python3 tools/make_v34_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print(f"v34 golden 新鲜：baseline/template 均与 U4 补丁一致（basePos 1 处、"
              f"缺省字面量 {U4_CONST}）；冻结件自洽；F11 空值路径 == v33 模板 + U4")
        return 0

    for path, content in outputs.items():
        _write(path, content)
    rules_out = json.dumps({"rules": v34_rules}, ensure_ascii=False, indent=2) + "\n"
    V34_RULES_OUT.write_bytes(rules_out.encode("utf-8"))
    print(f"v34 baseline : {V34_BASELINE.relative_to(REPO)}"
          f"（{baseline.count(chr(10)) + 1} 行）")
    print(f"v34 template : {TEMPLATE_PATH.relative_to(REPO)}"
          f"（{template.count(chr(10)) + 1} 行，U4 补 basePos 建成区框 1 处）")
    print(f"v33 冻结件   : {V33_TEMPLATE.relative_to(REPO)}（历史回归基座）")
    print(f"v34 规则     : {V34_RULES_OUT.relative_to(REPO)}"
          f"（{len(v34_rules)} 条 = v33 + star_box）")
    print("自验：冻结件灌回==v33基线；U4 逐值清点；灌回规则==基线；"
          "默认 STAR_BOX 灌回==v33基线+U4；F11 空值渲染==v33模板+U4 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
