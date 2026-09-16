#!/usr/bin/env python3
"""CI 浏览器冒烟：对 Pages 托管产物做真实渲染与交互回归。

静态服务仓库根目录，用 headless Chromium 验证：
  /gallery/  两张卡片、四个按钮、封面解码、0 pageerror；
  /demo/     开场 → 计数 0/2 → 影廊灯箱照片解码；
  /nuc/      开场 → 计数 0/76 → 9 个照片分片全 200 → 灯箱照片解码。

任一断言失败/页面报错/请求失败即退出码 1（CI 红）。
仅依赖 playwright（CI: uv run --with playwright 并先 playwright install chromium）。

用法：python tools/ci_browser_smoke.py [--port 8141] [--shots 目录]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Server(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8141)
    ap.add_argument("--shots", default="/tmp/ci-smoke-shots")
    args = ap.parse_args()

    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    httpd = _Server(("127.0.0.1", args.port),
                    partial(SimpleHTTPRequestHandler, directory=str(REPO_ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{args.port}"
    failures: list[str] = []
    summary: dict[str, object] = {}

    def check_starmap(browser, path: str, cats: int, shards: int,
                      min_img: int) -> None:
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errs: list[str] = []
        failed: list[str] = []
        codes: list[int] = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(r.url))
        page.on("response",
                lambda r: codes.append(r.status) if "photo-data" in r.url
                else None)
        try:
            page.goto(base + path, wait_until="networkidle", timeout=45000)
            page.click("#introBtn")
            page.wait_for_selector("#intro.fade", timeout=8000)
            seen = page.inner_text("#seenCount")
            if not seen.endswith(f"/ {cats}"):
                failures.append(f"{path} 计数错误：{seen!r}（期望 / {cats}）")
            page.evaluate("document.getElementById('btnGallery').click()")
            page.wait_for_selector("#lightbox.open #lbImg.show", timeout=15000)
            nw = page.evaluate("document.getElementById('lbImg').naturalWidth")
            if nw < min_img:
                failures.append(f"{path} 灯箱照片未解码：naturalWidth={nw}")
            ok200 = sum(1 for c in codes if c == 200)
            if ok200 != shards:
                failures.append(
                    f"{path} 照片分片：期望 {shards} 个 200，实际 {ok200}")
            if errs:
                failures.append(f"{path} pageerror：{errs[:3]}")
            if failed:
                failures.append(f"{path} 失败请求：{failed[:3]}")
            page.screenshot(path=str(shots / f"smoke{path.strip('/') or '_root'}.png"))
            summary[path] = {"seen": seen, "shards200": ok200,
                             "lightboxNaturalWidth": nw}
        except Exception as exc:  # noqa: BLE001 - 冒烟脚本任何异常都要红
            failures.append(f"{path} 冒烟异常：{exc}")
            try:
                page.screenshot(path=str(shots / f"fail{path.strip('/')}.png"))
            except Exception:
                pass
        finally:
            page.close()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])

        # ---- 展示墙 ----
        g = browser.new_page(viewport={"width": 1280, "height": 900})
        gerr: list[str] = []
        g.on("pageerror", lambda e: gerr.append(str(e)))
        try:
            g.goto(base + "/gallery/", wait_until="networkidle", timeout=45000)
            btns = g.evaluate(
                "Array.from(document.querySelectorAll('.mini'))"
                ".map(a=>a.getAttribute('href'))")
            if btns != ["../nuc/",
                        "https://github.com/TianWenzzzh/nuc-cat-starmap",
                        "../demo/",
                        "https://github.com/TianWenzzzh/meow-starmap/"
                        "blob/main/docs/快速上手.md"]:
                failures.append(f"/gallery/ 按钮集合漂移：{btns}")
            covers = g.evaluate(
                "Array.from(document.images).map(i=>i.naturalWidth)")
            if [w for w in covers if w < 100]:
                failures.append(f"/gallery/ 有封面未解码：{covers}")
            if gerr:
                failures.append(f"/gallery/ pageerror：{gerr[:3]}")
            g.screenshot(path=str(shots / "smoke_gallery.png"))
            summary["/gallery/"] = {"buttons": len(btns), "covers": covers}
        except Exception as exc:  # noqa: BLE001
            failures.append(f"/gallery/ 冒烟异常：{exc}")
        finally:
            g.close()

        # ---- 两个在线产物 ----
        check_starmap(browser, "/demo/", 2, 1, 300)
        check_starmap(browser, "/nuc/", 76, 9, 300)
        browser.close()

    print(json.dumps({"ok": not failures, "summary": summary,
                      "failures": failures}, ensure_ascii=False, indent=1))
    if failures:
        print(f"::error::浏览器冒烟 {len(failures)} 项失败（截图：{args.shots}）",
              file=sys.stderr)
        return 1
    print(f"浏览器冒烟全部通过，截图：{args.shots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
