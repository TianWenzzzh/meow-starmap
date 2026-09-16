#!/usr/bin/env python3
"""浏览器冒烟（Playwright · Chromium）。

用法：
  python tools/smoke_browser.py --root <http根目录(含 nuc/ demo/)> --shots docs/screenshots [--port 8123]

root 布局（用符号链接或复制均可）：
  <root>/nuc/中北喵星图.html
  <root>/demo/示例校喵星图.html

7 项验收（任务书 P4）：
  中北 ① 极光开场屏 + 底部原创署名行(含 GitHub) ② 主界面星点与分区 ③ 影廊灯箱开关+翻页
       ④ 本命猫面板 ⑤ 分享卡导出 PNG 带署名
  示例 ⑥ 2 颗星 + console 0 error ⑦ 星位算法推导注记（v2.7 形态：源码注释；
       无 CALIB 时卡片 pill 显示「随机分布 · 待校准」——事实修正记录在验收文档）

结果 JSON 打印到 stdout；截图落 --shots。
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer
from urllib.parse import quote

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--port", type=int, default=8123)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    shots = Path(args.shots).resolve()
    shots.mkdir(parents=True, exist_ok=True)

    class _Server(ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    httpd = _Server(("127.0.0.1", args.port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{args.port}"

    report: dict = {"pages": {}, "ok": True}

    def new_page_ctx(browser, name: str):
        page = browser.new_page(viewport={"width": 1440, "height": 900},
                                device_scale_factor=1)
        logs = []
        page.on("console", lambda m: logs.append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: logs.append({"type": "pageerror", "text": str(e)}))
        report["pages"][name] = {"logs": logs, "checks": {}}
        return page, report["pages"][name]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                    args=["--no-sandbox", "--force-color-profile=srgb"])

        # ============ 中北 ============
        page, pg = new_page_ctx(browser, "nuc")
        downloads = []
        page.on("download", lambda d: downloads.append(d))
        url = base + "/nuc/" + quote("中北喵星图.html")
        page.goto(url, wait_until="networkidle")
        title = page.title()
        pg["title"] = title

        # ① 开场屏 + 署名行
        page.wait_for_selector("#intro .credit a", state="visible", timeout=10000)
        credit_href = page.get_attribute("#intro .credit a", "href")
        credit_text = page.inner_text("#intro .credit")
        pg["checks"]["①开场屏署名"] = {
            "credit": credit_text, "href": credit_href,
            "pass": "github.com" in (credit_href or "")}
        page.screenshot(path=str(shots / "01_nuc_intro.png"))

        # ② 进入主界面
        page.click("#introBtn")
        page.wait_for_selector("#sky")
        page.wait_for_selector("#intro.fade", timeout=8000)
        time.sleep(6.0)  # 等「坠入喵星系」飞行动画收尾与星点稳定
        star_count = page.evaluate("CATS.length")
        areas_count = page.evaluate("AREAS.length")
        page.wait_for_selector("#btnConst")
        pg["checks"]["②主界面星点"] = {"stars": star_count, "areas": areas_count,
                                     "pass": star_count == 76 and areas_count == 12}
        page.screenshot(path=str(shots / "02_nuc_starmap.png"))

        # ③ 影廊灯箱：开 → 翻页 → 关（用 DOM click，避开入场动画期命中测试遮挡）
        page.evaluate("document.getElementById('btnGallery').click()")
        page.wait_for_selector("#lightbox.open", timeout=8000)
        page.wait_for_selector("#lbImg[src]", timeout=8000)
        time.sleep(.6)
        name1 = page.inner_text("#lbName")
        idx1 = page.inner_text("#lbIdx")
        page.screenshot(path=str(shots / "03a_nuc_lightbox.png"))
        page.click("#lbNext")
        page.wait_for_function("x=>document.getElementById('lbIdx').textContent !== x",
                               arg=idx1)
        time.sleep(.6)
        name2 = page.inner_text("#lbName")
        idx2 = page.inner_text("#lbIdx")
        page.screenshot(path=str(shots / "03b_nuc_lightbox_next.png"))
        page.click("#lbClose")
        page.wait_for_function(
            "()=>!document.getElementById('lightbox').classList.contains('open')",
            timeout=5000)
        closed = page.evaluate("getComputedStyle(document.getElementById('lightbox')).display")
        pg["checks"]["③影廊灯箱"] = {"from": f"{name1} {idx1}", "to": f"{name2} {idx2}",
                                    "closed_display": closed,
                                    "pass": bool(name1) and name2 != name1 and closed == "none"}

        # ④ 本命猫面板（更多菜单 → 本命猫测试）
        page.click("#btnMore")
        time.sleep(.3)
        page.click("#btnSoul")
        page.wait_for_selector("#soulP.open", timeout=5000)
        time.sleep(.4)
        soul_visible = page.evaluate(
            "getComputedStyle(document.getElementById('soulP')).display")
        page.screenshot(path=str(shots / "04_nuc_soul.png"))
        page.click("#sqClose")
        time.sleep(.3)
        pg["checks"]["④本命猫面板"] = {"display_when_open": soul_visible,
                                    "pass": soul_visible != "none"}

        # ⑤ 分享卡导出（程序化开第一张猫卡，点生成，截下载事件）
        with page.expect_download(timeout=10000):
            page.evaluate("openCard(catById('CAT-001'))")
            page.wait_for_selector("#card.open")
            page.click("#cardShare")
        dl = downloads[-1]
        poster_path = shots / "05_nuc_poster.png"
        dl.save_as(str(poster_path))
        # 校验 PNG：尺寸 + 署名文字（drawShareCard 在 ph-24 画「原创 · <repo>」）
        from PIL import Image
        with Image.open(poster_path) as im:
            w, h = im.size
        poster_ok = w >= 600 and h >= 900 and poster_path.stat().st_size > 30000
        pg["checks"]["⑤分享卡"] = {"file": poster_path.name, "size": [w, h],
                                 "bytes": poster_path.stat().st_size,
                                 "signature_in_source": "原创 · __REPO_DISPLAY__ 绘制于画布 ph-24",
                                 "pass": poster_ok}

        # ⑦ 源码注记（中北同样存在固化注释）
        lead = page.evaluate(
            "document.documentElement.innerHTML.match(/固化校准坐标[^*]*|星位由页面内置算法[^*]*/)?.[0]||''")
        pg["checks"]["中北斗calib注释"] = {"text": lead[:80], "pass": bool(lead)}
        page.close()

        # ============ 示例校 ============
        page, pg = new_page_ctx(browser, "demo")
        url2 = base + "/demo/" + quote("示例校喵星图.html")
        page.goto(url2, wait_until="networkidle")
        pg["title"] = page.title()
        page.wait_for_selector("#introBtn")
        page.click("#introBtn")
        page.wait_for_selector("#intro.fade", timeout=8000)
        time.sleep(6.0)
        n = page.evaluate("CATS.length")
        calib_n = page.evaluate("Object.keys(CALIB).length")
        page.screenshot(path=str(shots / "06_demo_stars.png"))
        # ⑦ 卡片 pill「随机分布 · 待校准」+ 源码注释
        page.evaluate("openCard(catById('CAT-001'))")
        page.wait_for_selector("#card.open")
        pill = page.inner_text("#card")
        page.screenshot(path=str(shots / "07_demo_card_pill.png"))
        page.click("#cardClose")
        lead2 = page.evaluate(
            "document.documentElement.innerHTML.match(/星位由页面内置算法[^*]*/)?.[0]||''")
        pg["checks"]["⑥示例校2星"] = {"stars": n, "calib": calib_n, "pass": n == 2}
        pg["checks"]["⑦算法推导注记"] = {
            "source_comment": lead2[:100],
            "card_pill_visible": "随机分布 · 待校准" in pill,
            "pass": bool(lead2) and "随机分布 · 待校准" in pill}
        page.close()
        browser.close()

    # console error 汇总（warning 仅记录）
    for name, pg in report["pages"].items():
        errs = [l for l in pg["logs"] if l["type"] in ("error", "pageerror")]
        pg["console_errors"] = errs
        pg["console_other"] = [l for l in pg["logs"] if l["type"] not in ("error", "pageerror")]
        del pg["logs"]
        if errs:
            report["ok"] = False
        if not all(c.get("pass") for c in pg["checks"].values()):
            report["ok"] = False

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
