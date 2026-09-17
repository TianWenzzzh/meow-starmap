#!/usr/bin/env python3
"""v2.7 golden 基线 → v2.8-lazy golden 基线与模板（确定性补丁，可重跑/可校验）。

为什么需要本脚本：05 正式版仓库本阶段只读，模板在开放仓库独立演进到 v2.8。
为避免手改 golden，本脚本把 v2.7→v2.8 的每一处变化固化成带次数断言的补丁，
同时作用于「基线 HTML」与「token 模板」，并自验正序灌回逐字节相等。

产出（--check 时只比对不落盘）：
  tests/fixtures/v28_baseline_lazy.html  v2.8 中北懒加载产物基线
  tests/fixtures/nuc_literals.json       v2.8 提取/注入规则（build.py 使用）
  template/starmap.html                  v2.8 token 模板

补丁来源：docs/照片分片懒加载改造方案.md §3。
T2 仅含加载器基础设施补丁；§3.3 十个消费点异步化补丁在 T3 追加到 CODE_PATCHES。

用法：
  python3 tools/make_v28_baseline.py          # 重新生成三份文件
  python3 tools/make_v28_baseline.py --check  # CI 金新鲜度门禁（漂移即非零退出）
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
TEMPLATE_PATH = REPO / "template" / "starmap.html"
V27_BASELINE = FIX / "v27_baseline.html"
V27_TEMPLATE = FIX / "v27_template.html"
V27_RULES = FIX / "nuc_literals.v27.json"
V28_BASELINE = FIX / "v28_baseline_lazy.html"
V28_RULES = FIX / "nuc_literals.json"

# ───────── v2.7→v2.8 公共代码补丁（基线与模板同构区域，各替换 1 次） ─────────

_PH_ANCHOR = (
    '<script>function PH(p){var k=String(p||"").split("/").pop();'
    'return (window.__PHOTOS&&window.__PHOTOS[k])||p}</script>')

# §3.2 加载器：PH 同步查表保留（底图 eager）；其后挂懒加载运行时。
# const __PM 在 eager 整包里不存在，typeof 守卫保证同一模板两种产物都安全。
_LOADER = _PH_ANCHOR + """<script>
const __PHOTO_BOOT=(typeof __PM!=="undefined")?__PM:null;
const __PHOTO_JOBS={},__PHOTO_PEND={};
function __ensureChunk(i){
  if(__PHOTO_JOBS[i]) return __PHOTO_JOBS[i];
  const job=new Promise((res,rej)=>{
    const s=document.createElement("script");
    s.src="assets/photo-data-"+String(i).padStart(2,"0")+".js";
    s.onload=()=>{__flushPhotoJobs(i);res();};
    s.onerror=()=>{delete __PHOTO_JOBS[i];rej(new Error("photo chunk "+i));};
    document.head.appendChild(s);
  });
  __PHOTO_JOBS[i]=job; return job;
}
function __flushPhotoJobs(i){
  if(!__PHOTO_BOOT) return;
  for(const k of Object.keys(__PHOTO_BOOT.m)){
    if(__PHOTO_BOOT.m[k]!==i||!(window.__PHOTOS&&__PHOTOS[k])) continue;
    const q=__PHOTO_PEND[k]; if(q){delete __PHOTO_PEND[k];q.forEach(fn=>fn(__PHOTOS[k]));}
  }
}
function __ensurePhoto(p){
  const k=String(p==null?"":p).split("/").pop();
  if(window.__PHOTOS&&__PHOTOS[k]) return Promise.resolve(__PHOTOS[k]);
  if(!__PHOTO_BOOT) return Promise.resolve(PH(p));
  const i=__PHOTO_BOOT.m[k];
  if(i==null) return Promise.resolve(PH(p));
  return __ensureChunk(i).then(()=>(window.__PHOTOS&&__PHOTOS[k])||PH(p));
}
function __whenPhoto(p,fn){
  const k=String(p==null?"":p).split("/").pop();
  if(window.__PHOTOS&&__PHOTOS[k]){fn(__PHOTOS[k]);return;}
  if(!__PHOTO_BOOT||__PHOTO_BOOT.m[k]==null){fn(PH(p));return;}
  (__PHOTO_PEND[k]||(__PHOTO_PEND[k]=[])).push(fn);
  __ensureChunk(__PHOTO_BOOT.m[k]).catch(()=>{
    if(typeof toast==="function") toast("一张照片分片没加载出来 · 检查网络或用整包版");
  });
}
</script>"""

# (name, old, new, expected_count)。T3 在本表追加 §3.3 消费点补丁。
CODE_PATCHES: list[tuple[str, str, str, int]] = [
    ("photo_loader_runtime", _PH_ANCHOR, _LOADER, 1),

    # ---- §3.3 十个照片消费点异步化（+ §3.3.1 竞态身份防护） ----
    # 列表绑定器（挂在加载器尾部）；__whenPhoto 已带等待者唤醒
    ("bind_lazy_helper",
     '  __ensureChunk(__PHOTO_BOOT.m[k]).catch(()=>{\n'
     '    if(typeof toast==="function") toast("一张照片分片没加载出来 · 检查网络或用整包版");\n'
     '  });\n'
     '}\n'
     '</script>',
     '  __ensureChunk(__PHOTO_BOOT.m[k]).catch(()=>{\n'
     '    if(typeof toast==="function") toast("一张照片分片没加载出来 · 检查网络或用整包版");\n'
     '  });\n'
     '}\n'
     'function __bindLazy(root){\n'
     '  root.querySelectorAll("img[data-pkey]").forEach(img=>{\n'
     '    if(img.dataset.lbound)return; img.dataset.lbound="1";\n'
     '    __whenPhoto(img.dataset.pkey,url=>{ if(img.isConnected) img.src=url; });\n'
     '  });\n'
     '}\n'
     '</script>', 1),

    # 2) 档案卡：ensure + selected 身份校验，失败走既有 onerror 占位
    ("card_img_async",
     '  if(c.photo){ img.classList.add("loading");'
     '                 // 星座徽记占位：加载完淡入\n'
     '    if(imgWrap) imgWrap.classList.add("loading");\n'
     '    img.src=photoSrc(c);\n'
     '    if(img.complete&&img.naturalWidth>0) imgDone(); }'
     '        // 缓存直出的不闪占位',
     '  if(c.photo){ img.classList.add("loading");'
     '                 // 星座徽记占位：加载完淡入\n'
     '    if(imgWrap) imgWrap.classList.add("loading");\n'
     '    __ensurePhoto(c.photo).then(u=>{ if(selected!==c) return;'
     '   // 身份防护：连开猫不串图\n'
     '      img.src=u; if(img.complete&&img.naturalWidth>0) imgDone(); })\n'
     '      .catch(()=>{ if(selected===c) img.dispatchEvent(new Event("error")); }); }'
     '        // 缓存直出的不闪占位', 1),

    # 3) 分享卡 makePoster
    ("poster_img_async",
     '    im.onload=()=>finish(im);\n'
     '    im.onerror=()=>finish(null);\n'
     '    im.src=photoSrc(c);\n'
     '    setTimeout(()=>finish(null),3500);',
     '    im.onload=()=>finish(im);\n'
     '    im.onerror=()=>finish(null);\n'
     '    __ensurePhoto(c.photo).then(u=>{im.src=u;}).catch(()=>finish(null));\n'
     '    setTimeout(()=>finish(null),3500);', 1),

    # 4) 搜索/星宿两个列表：src → data-pkey（出现 2 次）
    ("list_img_data_pkey",
     '\'<img loading="lazy" src="\'+photoSrc(c)+\'" alt="\'+c.name+\'">\'',
     '\'<img loading="lazy" data-pkey="\'+c.photo.split("/").pop()+\'" alt="\'+c.name+\'">\'',
     2),

    # 4b) 搜索面板渲染后绑定
    ("find_panel_bind",
     '  }).join("");\n'
     '  findPanel.querySelectorAll(".fRow").forEach(r=>r.onclick=()=>{ closeFind(); openCard(catById(r.dataset.id)); });',
     '  }).join("");\n'
     '  __bindLazy(document.getElementById("fdBody"));\n'
     '  findPanel.querySelectorAll(".fRow").forEach(r=>r.onclick=()=>{ closeFind(); openCard(catById(r.dataset.id)); });',
     1),

    # 5) 星宿面板渲染后绑定
    ("const_panel_bind",
     '      \'<span class="ff">\'+(c.features||"").split("、")[0]+\'</span></span></div>\').join("");\n'
     '  constP.querySelectorAll(".fRow").forEach(r=>r.onclick=()=>{ closeConst(); openCard(catById(r.dataset.id)); });',
     '      \'<span class="ff">\'+(c.features||"").split("、")[0]+\'</span></span></div>\').join("");\n'
     '  __bindLazy(document.getElementById("cpBody"));\n'
     '  constP.querySelectorAll(".fRow").forEach(r=>r.onclick=()=>{ closeConst(); openCard(catById(r.dataset.id)); });',
     1),

    # 6) 星尘变身：MORPH 身份 + onload 守卫 + ensure
    ("morph_identity",
     '  if(!c.photo) return;\n  const small=Math.min(W,H)<700;',
     '  if(!c.photo) return;\n'
     '  MORPH.cat=c.id;                                  // 身份防护：连开猫时旧图作废\n'
     '  const small=Math.min(W,H)<700;', 1),
    ("morph_onload_guard",
     '  img.onload=()=>{\n    try{',
     '  img.onload=()=>{ if(MORPH.cat!==c.id) return;\n    try{', 1),
    ("morph_img_async",
     '  img.onerror=()=>{};\n  img.src=photoSrc(c);\n}',
     '  img.onerror=()=>{};\n'
     '  __ensurePhoto(c.photo).then(u=>{ if(MORPH.cat===c.id) img.src=u; }).catch(()=>{});\n}',
     1),

    # 7) 本命猫结果图 data-pkey + 绑定
    ("soul_result_data_pkey",
     '"<img class=\'sqRImg\' src=\'"+photoSrc(best)+"\' alt=\'"+best.name+"\'>"',
     '"<img class=\'sqRImg\' data-pkey=\'"+best.photo.split("/").pop()+"\' alt=\'"+best.name+"\'>"',
     1),
    ("soul_result_bind",
     '    "<div class=\'sqRBtns\'><div id=\'sqGo\'>→ 去看它的那颗星</div><div id=\'sqCard\'>⤓ 专属卡</div><div id=\'sqRe\'>↺ 再测一次</div></div>";\n'
     '  document.getElementById("sqGo").onclick=()=>{ sqClose(); openCard(best); };',
     '    "<div class=\'sqRBtns\'><div id=\'sqGo\'>→ 去看它的那颗星</div><div id=\'sqCard\'>⤓ 专属卡</div><div id=\'sqRe\'>↺ 再测一次</div></div>";\n'
     '  __bindLazy(document.getElementById("sqBody"));\n'
     '  document.getElementById("sqGo").onclick=()=>{ sqClose(); openCard(best); };',
     1),

    # 8) 本命卡 canvas 取图
    ("soul_card_img_async",
     '  if(c.photo){ const im=new Image();\n'
     '    im.onload=()=>finish(im); im.onerror=()=>finish(null); im.src=photoSrc(c); }',
     '  if(c.photo){ const im=new Image();\n'
     '    im.onload=()=>finish(im); im.onerror=()=>finish(null);\n'
     '    __ensurePhoto(c.photo).then(u=>im.src=u).catch(()=>finish(null)); }', 1),

    # 9) 表情包工坊取图（复用既有 MEME.cat 身份）
    ("meme_img_async",
     '      im.onerror=()=>{ if(MEME.cat===selected){ MEME.img=null; memeRender(); } };\n'
     '      im.src=photoSrc(selected); }',
     '      im.onerror=()=>{ if(MEME.cat===selected){ MEME.img=null; memeRender(); } };\n'
     '      __ensurePhoto(selected.photo).then(u=>{ if(MEME.cat===selected) im.src=u; })\n'
     '        .catch(()=>{ if(MEME.cat===selected){ MEME.img=null; memeRender(); } }); }',
     1),

    # 10) 影廊灯箱：ensure 复用既有 GALLERY[lbIdx] 身份
    ("lightbox_p_src_drop",
     '  const pSrc=(typeof photoSrc==="function")?photoSrc:(c=>c.photo);\n', "", 1),
    ("lightbox_img_async",
     '    pre.onerror=()=>{ if(lbOpen&&GALLERY[lbIdx]===c){ lbImg.removeAttribute("src"); toast("这张照片没加载出来 · 左右翻页看看别的"); } };\n'
     '    pre.src=pSrc(c);',
     '    pre.onerror=()=>{ if(lbOpen&&GALLERY[lbIdx]===c){ lbImg.removeAttribute("src"); toast("这张照片没加载出来 · 左右翻页看看别的"); } };\n'
     '    __ensurePhoto(c.photo).then(u=>{ if(lbOpen&&GALLERY[lbIdx]===c) pre.src=u; })\n'
     '      .catch(()=>{ if(lbOpen&&GALLERY[lbIdx]===c) pre.onerror(); });', 1),
    ("lightbox_prefetch",
     '    lbIdx=i>=0?i:0; lbOpen=true; box.classList.add("open");\n'
     '    document.body.style.overflow="hidden"; lbRender();\n  }',
     '    lbIdx=i>=0?i:0; lbOpen=true; box.classList.add("open");\n'
     '    document.body.style.overflow="hidden"; lbRender();\n'
     '    if(!(navigator.connection&&navigator.connection.saveData)){'
     '   // 邻近片预取（尊重省流模式）\n'
     '      const ric=self.requestIdleCallback?self.requestIdleCallback.bind(self):setTimeout;\n'
     '      [lbIdx-1,lbIdx+1].forEach(j=>{ const pc=GALLERY[(j+GALLERY.length)%GALLERY.length];\n'
     '        if(pc) ric(()=>__ensurePhoto(pc.photo).catch(()=>{})); });\n    }\n  }', 1),

    # 10b) 星星悬停预告：ensure + hovered 身份
    ("peek_img_async",
     '        if(peekCat.photo){\n'
     '          peek.querySelector("img").src=pSrc(peekCat);\n',
     '        if(peekCat.photo){\n'
     '          __ensurePhoto(peekCat.photo).then(u=>{ if(hovered===peekCat&&peek.classList.contains("on")) peek.querySelector("img").src=u; }).catch(()=>{});\n',
     1),
]

_BOOTSTRAP_RE = re.compile(
    r'<script src="assets/photo-data-00\.js"></script>'
    r'<script>const __PM=\{.*?\};</script>', re.S)


def apply_patches(text: str, where: str) -> str:
    for name, old, new, expected in CODE_PATCHES:
        actual = text.count(old)
        if actual != expected:
            raise SystemExit(
                f"补丁 {name} 在{where}出现 {actual} 次，预期 {expected} 次")
        text = text.replace(old, new)
    return text


def build_nuc_lazy_bootstrap() -> str:
    """实跑 build.py 出中北懒加载产物，提取 __PHOTO_SCRIPTS__ 被替换成的
    引导串（00 eager 标签 + __PM 清单）。杜绝手抄，保证与构建器永远一致。"""
    with tempfile.TemporaryDirectory(prefix="v28-gen-") as td:
        out = Path(td) / "nuc"
        r = subprocess.run(
            [sys.executable, str(REPO / "tools" / "build.py"),
             "--pkg", str(REPO / "schools" / "nuc"),
             "--out", str(out), "--photo-loading", "lazy"],
            capture_output=True, text=True, cwd=str(REPO))
        if r.returncode != 0:
            raise SystemExit("生成中北懒加载产物失败：\n" + r.stderr[-1200:])
        html = (out / "中北喵星图.html").read_text("utf-8")
    m = _BOOTSTRAP_RE.search(html)
    if not m:
        raise SystemExit("懒加载产物中未找到引导串（__PM bootstrap）")
    return m.group(0)


def main() -> int:
    check = "--check" in sys.argv

    v27_baseline = V27_BASELINE.read_text("utf-8")
    v27_template = V27_TEMPLATE.read_text("utf-8")
    v27_rules = json.loads(V27_RULES.read_text("utf-8"))["rules"]

    bootstrap = build_nuc_lazy_bootstrap()

    # 基线：打公共补丁 + 把 v27 的 8 个 eager 标签换成 v28 懒引导串
    baseline = apply_patches(v27_baseline, "v27 基线")
    eager_tags = next(r["old"] for r in v27_rules if r["name"] == "photo_scripts")
    if baseline.count(eager_tags) != 1:
        raise SystemExit("v27 基线中 eager 照片标签串不唯一/缺失")
    baseline = baseline.replace(eager_tags, bootstrap)

    # 模板：只打公共补丁（__PHOTO_SCRIPTS__ token 原样保留）
    template = apply_patches(v27_template, "v27 模板")

    # v28 规则：51 条沿用，photo_scripts 的 old 更新为懒引导串
    rules = [dict(r) for r in v27_rules]
    for r in rules:
        if r["name"] == "photo_scripts":
            r["old"] = bootstrap
    rules_json = json.dumps({"rules": rules}, ensure_ascii=False, indent=2)

    # 自验：正序把规则灌回 v28 模板必须逐字节 == v28 基线
    filled = template
    for r in rules:
        if filled.count(r["new"]) != int(r["count"]):
            raise SystemExit(
                f"v28 规则 {r['name']} token 次数 {filled.count(r['new'])} "
                f"≠ 凭据 {r['count']}")
        filled = filled.replace(r["new"], r["old"])
    if filled != baseline:
        raise SystemExit("v28 模板灌回规则后与基线不逐字节相等")

    outputs = {
        V28_BASELINE: baseline,
        V28_RULES: rules_json + "\n",
        TEMPLATE_PATH: template,
    }
    if check:
        drift = []
        for path, content in outputs.items():
            if not path.exists() or path.read_text("utf-8") != content:
                drift.append(str(path.relative_to(REPO)))
        if drift:
            print("v28 golden 漂移，请运行 python3 tools/make_v28_baseline.py：\n  "
                  + "\n  ".join(drift))
            return 1
        print("v28 golden 新鲜：baseline/rules/template 均与补丁脚本一致")
        return 0

    for path, content in outputs.items():
        path.write_text(content, "utf-8")
    print(f"v28 baseline : {V28_BASELINE}（{baseline.count(chr(10))+1} 行）")
    print(f"v28 rules    : {V28_RULES}（{len(rules)} 条）")
    print(f"v28 template : {TEMPLATE_PATH}（{template.count(chr(10))+1} 行）")
    print("自验：模板灌回规则 == 基线 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
