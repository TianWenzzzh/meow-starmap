#!/usr/bin/env python3
"""v2.7 正式版 HTML → 开放 token 模板（历史提取器，可复跑）。

现役模板已演进到 v2.8-lazy，基线生成走 tools/make_v28_baseline.py；
本脚本仅用于复核 v2.7 提取真相（配套 tests/fixtures/nuc_literals.v27.json
与 v27_template.html 的历史往返测试）。

输入：05 仓库的「中北喵星图.html」（3605 行 v2.7，只读基准）
输出：
  template/starmap.html          —— token 化模板（除替换外不得改动任何字节）
  tests/fixtures/nuc_literals.json —— 每条替换规则的原始字面量（字节级往返凭据）

铁律：本脚本只做「整段锚点切分」与「逐字面量替换」两类操作；
不得重排、格式化、补全任何字符。tests/test_template_roundtrip.py
会把 fixtures 里的 old 全部灌回模板，断言与源 HTML 逐字节相同。

用法：
  python3 tools/extract_template.py            # 用 STARMAP_HOME 定位总库
  python3 tools/extract_template.py <源HTML路径>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ───────────────────────── 阶段 A：整块锚点切分 ─────────────────────────
# (token 名, 起始标记, 结束标记) —— old = [起, 止] 闭区间全文，new = token 独占
BLOCKS = [
    ("__CATS_BLOCK__",       "const CATS = [",        "];" ),
    ("__CALIB_BLOCK__",      "const CALIB={",         "};" ),
    ("__AREAS_BLOCK__",      "const AREAS=[",         "];" ),
    ("__AREA_KEYS_BLOCK__",  "const AREA_KEYS=[",     "];" ),
    ("__REL_BLOCK__",        "const REL=[",           "];" ),
    ("__CONST_BLOCK__",      "const CONST=[",         "];" ),
    ("__POSTER_STARS__",     "const stars=[",         "];" ),
]

# 8 个照片分片标签（PH 函数内联 script 不在此列，必须原样保留在模板）
PHOTO_TAGS_RE = re.compile(r'(?:<script src="assets/photo-data-\d+\.js"></script>)+')

# ───────────────────── 阶段 B：逐字面量替换（先长句/全称，后短词） ─────────────────────
# (规则名, old, new, 期望出现次数)。顺序敏感：含「中北大学」全称的整句必须
# 排在 SCHOOL 叶子之前；含长串的行（meta/console）排在短叶子之前。
LITERALS: list[tuple[str, str, str, int]] = [
    # ---- 文件头：版权计数行（© 2026 原作者署名刻意保留） ----
    ("copy_line",
     "  原创作品 © 2026 TianWenzzzh ｜ 76 只猫的普查数据与 194 张照片均为实地采集",
     "  原创作品 © 2026 TianWenzzzh ｜ __CAT_COUNT__ 只猫的普查数据与 __PHOTO_COUNT__ 张照片均为实地采集", 1),
    ("meta_desc",
     '<meta name="description" content="中北喵星图：76 只中北大学校园猫的实地普查星图。'
     '每只猫是一颗星——星色取毛色、星等看实拍数、星位即真实出没区。'
     '原创开源：github.com/TianWenzzzh/nuc-cat-starmap">',
     '<meta name="description" content="__META_DESC__">', 1),
    ("title_tag",
     "<title>中北喵星图 · 校园猫咪星系</title>",
     "<title>__TITLE_TAG__</title>", 1),

    # ---- 开场屏文案 ----
    ("tagline",
     "人民兵工第一校的喵星编制 · 每颗星都是一只真实生活的中北猫",
     "__TAGLINE__", 1),
    ("stats_line",
     "中北校园实地普查 ｜ 76 只在编基米 ｜ 194 张学长学姐实拍",
     "__STATS_LINE__", 1),

    # ---- 指南面板：整句中北语义，全部整块参数化 ----
    ("guide_bound",
     "档案数据仅覆盖中北大学（2026-08 实地普查 76 只），别校的猫查不到；"
     "玩法谁都可用，想给母校复刻一份，完整流程在 SKILL.md。",
     "__GUIDE_BOUND__", 1),
    ("guide_reuse",
     "档案数据不能（那是中北的猫），方法论可以：普查、归并、建星图到打包的完整流程都写在 SKILL.md 里。",
     "__GUIDE_REUSE__", 1),
    ("guide_accuracy",
     "194 张照片逐张比对归并出 76 只，存疑的一律不收；每一条取舍都记在《归并决策摘要.md》，欢迎抽查。",
     "__GUIDE_ACCURACY__", 1),

    # ---- 星图志页脚 ----
    ("stats_foot",
     "数据源：猫咪名册.csv · 2026-08 实地普查 · 仅中北校园<br>星色 = 毛色 ｜ 环绕光点 = 收录照片数",
     "__STATS_FOOT__", 1),

    # ---- 主脚本头注释 ----
    ("banner_sub",
     " * 底图: 校园地图-夜空版-web.jpg | 数据: CATS（76只真猫名册 · 2026-08普查）",
     " * 底图: __MAP_FILE__ | 数据: CATS（__CAT_COUNT__只真猫名册 · __SURVEY_DATE__普查）", 1),
    ("cats_lead_comment",
     "// ---- 真实名册数据（源自 猫咪档案/猫咪名册.csv · 76只=52原有+24补充归并 · 2026-08普查）----",
     "// ---- 真实名册数据（build.py 自名册 CSV 注入 · __CAT_COUNT__ 只在编 · __SURVEY_DATE__ 普查）----", 1),
    ("calib_lead_comment",
     "/* 固化校准坐标（2026-08-17 v6 · 全员限定红框核心建成区 x.332-.848/y.164-.827 · "
     "语义聚簇落位 · 手动校准 localStorage 仍优先覆盖） */",
     "/* __CALIB_LEAD_COMMENT__ */", 1),

    # ---- 常量 ----
    ("map_src",
     'const MAP_SRC = "校园地图-夜空版-web.jpg";',
     'const MAP_SRC = "__MAP_FILE__";', 1),
    ("ls_key",
     'const LS_KEY  = "nuc-cat-galaxy-positions";',
     'const LS_KEY  = "__LS_PREFIX__-cat-galaxy-positions";', 1),
    ("js_title",
     'const TITLE="中北喵星图";',
     'const TITLE="__PRODUCT__";', 1),

    # ---- localStorage 其余三键（各读/写两处） ----
    ("ls_fx",  '"nuc-cat-fx"',          '"__LS_PREFIX__-cat-fx"', 2),
    ("ls_seen", '"nuc-cat-seen"',       '"__LS_PREFIX__-cat-seen"', 2),
    ("ls_tip", '"nuc-cat-tip-dismiss"', '"__LS_PREFIX__-cat-tip-dismiss"', 2),

    # ---- 档案卡 / 导出水印 ----
    ("card_title_expr",
     'c.id+" ｜ 中北大学猫咪编制委员会 · 登记在册"',
     'c.id+" ｜ __COMMITTEE__ · 登记在册"', 1),
    ("card_meta_expr",
     '"2026-08 实地普查 · 第 "+(+c.id.slice(4))+" 号星"',
     '"__SURVEY_DATE__ 实地普查 · 第 "+(+c.id.slice(4))+" 号星"', 1),

    # ---- 校准导出里的底图名 ----
    ("export_map_name",
     'map:"中北大学校园图2023秋季版"',
     'map:"__EXPORT_MAP_NAME__"', 1),

    # ---- 图鉴里程碑（裸 JS 数组，build 按猫数推导） ----
    ("milestones", "[10,30,50,76]", "__MILESTONES__", 2),
    # 护照称号阈值表（与里程碑同构，build 按猫数推导，"喵星传奇"恒挂满编阈值）
    ("pass_titles",
     '[[0,"初来乍到"],[10,"猫门常客"],[30,"校园通"],[50,"猫学长认证"],[76,"喵星传奇"]]',
     '__PASS_TITLES_JS__', 1),
    ("milestone_toast",
     'm===76?"🏆 喵图鉴全收集！你就是中北猫王！"',
     'm===__CAT_COUNT__?"🏆 喵图鉴全收集！你就是__KING_NAME__！"', 1),
    # 搜索无结果时的「清筛选」按钮文案
    ("clear_filter",
     'cb.textContent="清筛选 · 看全部76只"',
     'cb.textContent="清筛选 · 看全部__CAT_COUNT__只"', 1),

    # ---- 寻猫海报 ----
    ("poster_title",
     'g.fillText("中北寻猫地图",pw/2,118)',
     'g.fillText("__POSTER_TITLE__",pw/2,118)', 1),
    ("poster_sub",
     '"跟着星图走遍它们的地盘 · "+CATS.length+" 只在编基米 · 2026-08 实地普查"',
     '"跟着星图走遍它们的地盘 · "+CATS.length+" 只在编基米 · __SURVEY_DATE__ 实地普查"', 1),
    ("poster_open_hint",
     "打开「中北喵星图」点击任意星星，即可查看它的档案与出没星域",
     "打开「__PRODUCT__」点击任意星星，即可查看它的档案与出没星域", 1),
    ("skill_foot_line",
     "中北大学—校园猫咪档案Skill · 人民兵工第一校的喵星编制",
     "__SKILL_FOOT_LINE__", 2),
    ("poster_file",
     'a.download="中北寻猫海报.png"',
     'a.download="__POSTER_FILE__"', 1),

    # ---- 录制角标 ----
    ("rec_badge",
     '" ｜ 图鉴 "+SEEN.size+"/"+CATS.length+" ｜ 中北喵星图"',
     '" ｜ 图鉴 "+SEEN.size+"/"+CATS.length+" ｜ __PRODUCT__"', 1),

    # ---- 本命猫卡 ----
    ("soul_line",
     "和它一样：真实、在编、被记录在册的中北猫",
     "__SOUL_LINE__", 1),
    ("soul_meta",
     '"76只在编基米 · 2026-08实地普查 · 图鉴 "+SEEN.size+"/"+CATS.length',
     '"__CAT_COUNT__只在编基米 · __SURVEY_DATE__实地普查 · 图鉴 "+SEEN.size+"/"+CATS.length', 1),

    # ---- 表情包 / 护照 ----
    ("meme_brand",
     '"中北喵星图原创 · "+(MEME.cat?MEME.cat.name:"")',
     '"__PRODUCT__原创 · "+(MEME.cat?MEME.cat.name:"")', 1),
    ("passport_hint",
     "打开「中北喵星图」· 按十二星宿寻访 · 遇见即可盖章",
     "打开「__PRODUCT__」· 按十二星宿寻访 · 遇见即可盖章", 1),

    # ---- 控制台彩蛋（源码里是反斜杠+n 两字符） ----
    ("console_line1",
     "%c🐱 中北喵星图 · NUC CAT GALAXY v2.7",
     "%c🐱 __PRODUCT__ · __EN__ __VERSION__", 1),
    ("console_line2",
     "%c原创作品 © 2026 TianWenzzzh · 76 只猫的实地普查档案\\n"
     "开源仓库：https://github.com/TianWenzzzh/nuc-cat-starmap\\n"
     "转载请署名并附仓库链接 · 一起给更多学校点亮喵星系 ✦",
     "%c原创作品 © 2026 TianWenzzzh · __CAT_COUNT__ 只猫的实地普查档案\\n"
     "开源仓库：__REPO_URL__\\n"
     "转载请署名并附仓库链接 · 一起给更多学校点亮喵星系 ✦", 1),

    # ---- chips / 图鉴环静态首帧计数（JS 启动同步重算，这里仅为占位保真） ----
    ("chip_all",
     ">全部<b class=\"n\">76</b>",
     ">全部<b class=\"n\">__CAT_COUNT__</b>", 1),
    ("seen_ring",
     "已遇见 0 / 76",
     "已遇见 0 / __CAT_COUNT__", 1),
]

# ───────────────────── 阶段 C：全局短叶子（所有长句之后） ─────────────────────
# (规则名, old, new, 期望次数)。次数 = 原文总次数减去已被整句规则吃掉的次数。
GLOBALS: list[tuple[str, str, str, int]] = [
    # 原文 4 处：L6 / L15(meta 已吃) / L743 href / L3604(console 已吃) → 剩 2
    ("repo_url",
     "https://github.com/TianWenzzzh/nuc-cat-starmap", "__REPO_URL__", 2),
    # 原文 5 处：L743 文本 + 4 个导出水印
    ("repo_display",
     "github.com/TianWenzzzh/nuc-cat-starmap", "__REPO_DISPLAY__", 5),
    # 原文 15 处，8 处已随整句/专属规则处理 → 剩 7：
    # L4 注释 / L737 / L747 / L959 注释 / L1598 注释 / L2407 / L3159
    ("product", "中北喵星图", "__PRODUCT__", 7),
    # L4 / L747 brand / L2407 / L3159
    ("en", "NUC CAT GALAXY", "__EN__", 4),
    # 原文 2 处（L4、L3603），console 已吃 → 剩 1
    ("version", "v2.7", "__VERSION__", 1),
]

# 模板中必须清零的残留模式（© 2026 署名、静态 chips 毛色分布、幸运星占位不在此列）
FORBIDDEN_RESIDUE = [
    r"中北", r"NUC", r"(?<![A-Za-z])nuc(?![A-Za-z])", r"SKILL\.md",
    r"2026-08", r"(?<!\d)194(?!\d)",
]

# 独立数字 76 的视觉白名单：金色 #ffd76a、SVG 星 path 的 1.76/-1.76、动画参数 h:76。
# 其余任何 76 都意味着还有猫数文案没被参数化。
ALLOW_76_NEIGHBORHOOD = ("ffd76a", "1.76", "h:76", "76%")


def extract_blocks(text: str) -> tuple[str, list[dict]]:
    """阶段 A：锚点切分。返回 (新文本, rules)。"""
    rules: list[dict] = []
    for token, start, end in BLOCKS:
        i = text.find(start)
        if i < 0:
            raise SystemExit(f"块起始标记未找到：{start}")
        j = text.find(end, i + len(start))
        if j < 0:
            raise SystemExit(f"块结束标记未找到：{end}（起于 {start}）")
        j += len(end)
        old = text[i:j]
        if text.count(start) != 1:
            raise SystemExit(f"块起始标记不唯一：{start}")
        text = text[:i] + token + text[j:]
        rules.append({"name": token.lower().strip("_"), "old": old,
                      "new": token, "count": 1})

    m = PHOTO_TAGS_RE.search(text)
    if not m:
        raise SystemExit("照片分片标签串未找到")
    old = m.group(0)
    n_tags = old.count('<script')
    if n_tags != 8:
        raise SystemExit(f"照片分片标签数应为 8，实际 {n_tags}")
    text = text[:m.start()] + "__PHOTO_SCRIPTS__" + text[m.end():]
    rules.append({"name": "photo_scripts", "old": old,
                  "new": "__PHOTO_SCRIPTS__", "count": 1})
    return text, rules


def apply_literals(text: str, rules_out: list[dict],
                   table: list[tuple[str, str, str, int]]) -> str:
    """阶段 B/C：逐条字面量替换，次数不符即失败。"""
    for name, old, new, expected in table:
        actual = text.count(old)
        if actual != expected:
            raise SystemExit(
                f"规则 {name}：old 出现 {actual} 次，预期 {expected} 次\n"
                f"  old={old[:80]!r}")
        text = text.replace(old, new)
        rules_out.append({"name": name, "old": old, "new": new,
                          "count": expected})
    return text


def check_residue(text: str) -> None:
    """模板中不得残留任何中北专属字面量；独立 76 仅允许视觉白名单形态。"""
    bad: list[str] = []
    for pat in FORBIDDEN_RESIDUE:
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(pat, line):
                bad.append(f"  L{i} /{pat}/: {line.strip()[:100]}")
    for m in re.finditer(r"(?<!\d)76(?!\d)", text):
        window = text[max(0, m.start() - 8):m.end() + 4]
        if not any(tag in window for tag in ALLOW_76_NEIGHBORHOOD):
            line_no = text.count("\n", 0, m.start()) + 1
            bad.append(f"  L{line_no} 独立数字76: …{window}…")
    if bad:
        raise SystemExit("模板残留中北专属字面量：\n" + "\n".join(bad))


def main() -> int:
    if len(sys.argv) > 1:
        src_path = Path(sys.argv[1])
    else:
        home = Path(__import__("os").environ.get(
            "STARMAP_HOME", "/media/tianwen/KINGSTON/猫咪星图_总库"))
        src_path = home / "05_git仓库_最新v2.6" / "中北喵星图.html"
    src = src_path.read_text(encoding="utf-8")
    src_sha = hashlib.sha256(src.encode("utf-8")).hexdigest()

    rules: list[dict] = []
    text, block_rules = extract_blocks(src)
    rules.extend(block_rules)
    text = apply_literals(text, rules, LITERALS)
    text = apply_literals(text, rules, GLOBALS)
    check_residue(text)

    out_html = REPO_ROOT / "template" / "starmap.html"
    out_fix = REPO_ROOT / "tests" / "fixtures" / "nuc_literals.json"
    out_html.write_text(text, encoding="utf-8")
    out_fix.write_text(json.dumps(
        {"source": str(src_path), "source_sha256": src_sha,
         "rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8")

    tpl_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"源文件  : {src_path}")
    print(f"源 sha256: {src_sha}")
    print(f"模板    : {out_html}（{text.count(chr(10)) + 1} 行）")
    print(f"模板 sha: {tpl_sha}")
    print(f"规则数  : {len(rules)}（块 {len(block_rules)} + 字面量 "
          f"{len(rules) - len(block_rules)}）")
    print(f"fixtures: {out_fix}")
    print("残留校验: 0 处中北专属字面量 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
