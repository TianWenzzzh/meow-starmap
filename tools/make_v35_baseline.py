#!/usr/bin/env python3
"""v34 → v35 golden：STAR_ZONE 多边形撒点区（确定性拒绝采样）。

v35 相对 v34 的模板变化：basePos 增加 STAR_ZONE 分支——当注入的 zone 非空
时，在 STAR_BOX 包络内做确定性拒绝采样（mulberry32 种子流不变 ⇒ 同 id 恒同
点），把星位约束到任意多边形（v2.9.1 起 nuc 用用户手绘校区边界）；
zone 缺省字面量为 `const STAR_ZONE=null;` ⇒ 纯矩形行为与 v34 逐字节一致。

产出（--check 只比对不落盘）：
  tests/fixtures/v34_template.html  v34 模板冻结快照（历史回归用）
  tests/fixtures/v35_baseline.html  v35 基线（= v34 基线 + U5，STAR_ZONE=null）
  tests/fixtures/nuc_literals.json  v35 规则（= v34 规则 + star_zone 一条）
  template/starmap.html             v35 token 模板（= v34 模板 + U5）

用法：
  python3 tools/make_v35_baseline.py          # 生成
  python3 tools/make_v35_baseline.py --check  # CI 金新鲜度门禁
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
TEMPLATE_PATH = REPO / "template" / "starmap.html"   # 现役，归本脚本独占写

V34_TEMPLATE = FIX / "v34_template.html"        # 冻结输出（历史回归）
V34_BASELINE = FIX / "v34_baseline.html"        # 上一代输入（勿改）
V34_RULES = FIX / "nuc_literals.v34.json"       # 上一代冻结规则（勿改）
V35_BASELINE = FIX / "v35_baseline.html"
V35_RULES_OUT = FIX / "nuc_literals.json"       # 从此代表 v35（+star_zone 一条）

# 本代不碰的 token 集（v29~v34 同款 + 本代新增）
TOKENS = ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__",
          "__CATS_BLOCK__", "__CALIB_BLOCK__", "__PHOTO_SCRIPTS__",
          "__STAR_BOX__", "__STAR_ZONE__")

# U5 补丁：只动 basePos 这一处。逐值清点（出现次数必须恰为 1，否则 raise）。
U5_OLD = ("function basePos(cat){ const r=mulberry32(hashStr(cat.id));\n"
          "  return { x:STAR_BOX.x0+r()*STAR_BOX.w, "
          "y:STAR_BOX.y0+r()*STAR_BOX.h }; }")
U5_TOKEN = "__STAR_ZONE__"
U5_NULL = "const STAR_ZONE=null;"
U5_NEW_BASEPOS = ("function basePos(cat){ const r=mulberry32(hashStr(cat.id));\n"
                  "  if(STAR_ZONE){ let x=0,y=0; do{ x=STAR_BOX.x0+r()*STAR_BOX.w; "
                  "y=STAR_BOX.y0+r()*STAR_BOX.h; }while(!inZone(x,y)); "
                  "return {x:x,y:y}; }\n"
                  "  return { x:STAR_BOX.x0+r()*STAR_BOX.w, "
                  "y:STAR_BOX.y0+r()*STAR_BOX.h }; }")
U5_INZONE = ("function inZone(x,y){ let t=false; const Z=STAR_ZONE;\n"
             "  for(let i=0,j=Z.length-1;i<Z.length;j=i++){ "
             "if(((Z[i][1]>y)!==(Z[j][1]>y))&&(x<(Z[j][0]-Z[i][0])*(y-Z[i][1])"
             "/(Z[j][1]-Z[i][1])+Z[i][0])) t=!t; }\n"
             "  return t; }")

STAR_ZONE_RULE = {"name": "star_zone", "old": U5_NULL, "new": U5_TOKEN,
                  "count": 1}


def apply_u5(text: str, tag: str, token_form: bool) -> str:
    """basePos 换成带 STAR_ZONE 分支的形态；模板插 token 裸行，基线插 null 字面量。"""
    if "STAR_ZONE" in text:
        raise SystemExit(f"U5 前的 {tag} 已含 STAR_ZONE——基座可能已打过补丁")
    n = text.count(U5_OLD)
    if n != 1:
        raise SystemExit(f"U5 在 {tag} 命中 basePos 块 {n} 处，必须恰好 1 处"
                         f"（基座已漂移，禁止盲改）")
    insert = "\n".join([
        U5_TOKEN if token_form else U5_NULL,
        U5_NEW_BASEPOS,
        U5_INZONE,
    ])
    out = text.replace(U5_OLD, insert)
    if token_form:
        if out.count(U5_TOKEN) != 1 or U5_NULL in out:
            raise SystemExit(f"U5 后 {tag} token 形态清点不符")
    else:
        if out.count(U5_NULL) != 1 or U5_TOKEN in out:
            raise SystemExit(f"U5 后 {tag} 字面量形态清点不符")
    if out.count(U5_NEW_BASEPOS) != 1 or out.count(U5_INZONE) != 1 or U5_OLD in out:
        raise SystemExit(f"U5 后 {tag} basePos/inZone 新形态清点不符")
    return out


def _fill(template: str, rules: list[dict]) -> str:
    text = template
    for r in rules:
        text = text.replace(r["new"], r["old"])
    return text


# 🔴 换行纪律：本仓 .gitattributes 是 `* text=auto eol=lf`，一律 read_bytes/
# write_bytes 手工定换行；读到 CRLF 就报警并归一。
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

    v34_baseline, _ = _read(V34_BASELINE)
    v34_rules = json.loads(V34_RULES.read_text("utf-8"))["rules"]

    if not V34_TEMPLATE.exists():
        raise SystemExit("缺 fixtures/v34_template.html 冻结快照——"
                         "活模板已是 v35，不得从现役模板重冻 v34；"
                         "请从 git 历史（16 仓 v1.8.0 的 template/starmap.html）恢复")
    v34_template, nl34 = _read(V34_TEMPLATE)
    if not check and nl34.crlf:
        _write(V34_TEMPLATE, v34_template)      # 只换换行，内容不动

    # 自验 0（防「冻结件过期 → 本地假绿」）：冻结的 v34 模板正序灌回 v34 规则
    # 必须 == v34 基线；且冻结件不得已含 STAR_ZONE。
    if _fill(v34_template, v34_rules) != v34_baseline:
        raise SystemExit(
            "fixtures/v34_template.html 与 v34_baseline.html 不自洽（灌回规则"
            " ≠ 基线）——冻结件是旧内容。从 git 历史恢复后重跑。")
    for tag, text in (("冻结 v34 模板", v34_template), ("v34 基线", v34_baseline)):
        if "STAR_ZONE" in text:
            raise SystemExit(f"{tag} 已含 STAR_ZONE——冻结件被 U5 污染。")

    template = apply_u5(v34_template, "v34 模板", token_form=True)
    baseline = apply_u5(v34_baseline, "v34 基线", token_form=False)

    # 自验 1：token 全部恰 1 处（含本代新增）
    for token in TOKENS:
        if template.count(token) != 1:
            raise SystemExit(f"v35 模板 token {token} 次数 ≠ 1")

    # 自验 2：规则集恰好多一条，且就是 star_zone 挂尾
    if not v34_rules:
        raise SystemExit("v34 规则集为空？")
    v35_rules = v34_rules + [dict(STAR_ZONE_RULE)]
    if v35_rules[-1]["name"] != "star_zone" or len(v35_rules) != len(v34_rules) + 1:
        raise SystemExit("v35 规则追加形态不符")

    # 自验 3：模板正序灌回全部规则 == v35 基线（字节往返）
    filled = _fill(template, v35_rules)
    if filled != baseline:
        for i, (a, b) in enumerate(zip(filled, baseline)):
            if a != b:
                raise SystemExit(
                    f"v35 灌回与基线首个差异在偏移 {i}：\n"
                    f"  灌回={filled[max(0, i - 40):i + 40]!r}\n"
                    f"  基线={baseline[max(0, i - 40):i + 40]!r}")
        raise SystemExit(
            f"v35 灌回与基线长度不同：{len(filled)} vs {len(baseline)}")

    # 自验 3b（缺省 STAR_ZONE=null 灌回 == v34 基线 + U5）：两条推导路径必须
    # 字节相同——保证「不设 zone 的学校」行为与 v34 逐字节一致。
    if baseline != filled or U5_NULL not in baseline:
        raise SystemExit("缺省 STAR_ZONE 灌回与「v34 基线 + U5」不一致")

    # 自验 4（F11 红线的 v35 形态）：F11 空 token 渲染 == v34 模板 + U5（F11 空）
    empty = template
    v34_with_u5 = apply_u5(v34_template, "冻结 v34 模板", token_form=True)
    for token in ("__THEME_CSS__", "__LOGO_INTRO__", "__LOGO_TOPBAR__"):
        empty = empty.replace(token, "")
        v34_with_u5 = v34_with_u5.replace(token, "")
    if empty != v34_with_u5:
        raise SystemExit("F11 空值路径与「v34 模板 + U5」不一致")

    outputs = {V35_BASELINE: baseline, TEMPLATE_PATH: template}
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists():
                drift.append(f"{path.relative_to(REPO)}（不存在）")
                continue
            on_disk, nl = _read(path)
            if on_disk != content:
                drift.append(f"{path.relative_to(REPO)}（内容与 U5 补丁不符）")
            elif nl.crlf:
                drift.append(f"{path.relative_to(REPO)}（{nl.crlf} 处 CRLF，"
                             f"违反 eol=lf）")
        if drift:
            print("v35 golden 漂移，请运行 python3 tools/make_v35_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print(f"v35 golden 新鲜：baseline/template 均与 U5 补丁一致"
              f"（basePos 1 处、缺省字面量 {U5_NULL}）；冻结件自洽；"
              f"F11 空值路径 == v34 模板 + U5")
        return 0

    for path, content in outputs.items():
        _write(path, content)
    rules_out = json.dumps({"rules": v35_rules}, ensure_ascii=False,
                           indent=2) + "\n"
    V35_RULES_OUT.write_bytes(rules_out.encode("utf-8"))
    print(f"v35 baseline : {V35_BASELINE.relative_to(REPO)}"
          f"（{baseline.count(chr(10)) + 1} 行）")
    print(f"v35 template : {TEMPLATE_PATH.relative_to(REPO)}"
          f"（{template.count(chr(10)) + 1} 行，U5 补 basePos 拒绝采样 1 处）")
    print(f"v34 冻结件   : {V34_TEMPLATE.relative_to(REPO)}（历史回归基座）")
    print(f"v35 规则     : {V35_RULES_OUT.relative_to(REPO)}"
          f"（{len(v35_rules)} 条 = v34 + star_zone）")
    print("自验：冻结件灌回==v34基线；U5 逐值清点；灌回规则==基线；"
          "缺省 STAR_ZONE=null 灌回==v34基线+U5；F11 空值渲染==v34模板+U5 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
