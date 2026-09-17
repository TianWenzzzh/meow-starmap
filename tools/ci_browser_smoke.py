#!/usr/bin/env python3
"""CI 浏览器冒烟：Pages 托管产物的真实渲染、懒加载网络行为与交互回归。

http 模式（默认，CI browser-smoke job）：
  /gallery/  两卡片四按钮、封面解码、0 pageerror；
  /demo/、/nuc/：
    - 初始只加载 photo-data-00.js（底图关键片），猫片零请求、初始字节 ≤700KB；
    - 计数 0/N；影廊灯箱打开后猫片按需到达、照片解码；翻 5 页后分片有界；
    - 搜索面板列表 __bindLazy 缩略图解码 → 点行开卡，档案卡大图解码（连开 3 张无串图）。
file:// 模式（--file）：同样路径打 file:// URI，守双击离线红线。

任一断言失败/页面报错/请求失败即退出码 1。
用法：python tools/ci_browser_smoke.py [--port 8141] [--shots 目录] [--file]
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
MAX_INITIAL_BYTES = 700_000        # 初始（HTML+00 底图片）预算，目标 ≤0.6MB


class _Server(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8141)
    ap.add_argument("--shots", default="/tmp/ci-smoke-shots")
    ap.add_argument("--file", action="store_true",
                    help="用 file:// 打开仓库内托管产物（离线红线）")
    args = ap.parse_args()

    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    httpd = None
    if not args.file:
        httpd = _Server(("127.0.0.1", args.port),
                        partial(SimpleHTTPRequestHandler,
                                directory=str(REPO_ROOT)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def url(path: str) -> str:
        if args.file:
            target = REPO_ROOT / path.strip("/") / "index.html"
            return target.as_uri()
        return f"http://127.0.0.1:{args.port}{path}"

    failures: list[str] = []
    summary: dict[str, object] = {}

    def check_starmap(browser, path: str, cats: int) -> None:
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errs: list[str] = []
        failed: list[str] = []
        shard_req: list[str] = []
        shard_bytes = {"total": 0}
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(r.url))

        def on_resp(resp):
            if "photo-data-" in resp.url:
                shard_req.append(resp.url.split("/")[-1])
                try:
                    shard_bytes["total"] += len(resp.body())
                except Exception:
                    pass
        page.on("response", on_resp)

        tag = ("file" if args.file else "http") + path
        try:
            page.goto(url(path), wait_until="networkidle", timeout=45000)
            page.click("#introBtn")
            page.wait_for_selector("#intro.fade", timeout=8000)
            seen = page.inner_text("#seenCount")
            if not seen.endswith(f"/ {cats}"):
                failures.append(f"{tag} 计数错误：{seen!r}")

            # 初始：仅 00 关键片
            init_shards = sorted(set(shard_req))
            if init_shards != ["photo-data-00.js"]:
                failures.append(
                    f"{tag} 初始分片应为仅 00，实际 {init_shards}")
            init_bytes = shard_bytes["total"]
            if init_bytes > MAX_INITIAL_BYTES:
                failures.append(
                    f"{tag} 初始照片字节 {init_bytes} > {MAX_INITIAL_BYTES}")

            # 影廊灯箱：按需取片
            page.evaluate("document.getElementById('btnGallery').click()")
            page.wait_for_selector("#lightbox.open #lbImg.show", timeout=15000)
            lb_nw = page.evaluate("document.getElementById('lbImg').naturalWidth")
            if lb_nw < 100:
                failures.append(f"{tag} 灯箱照片未解码：naturalWidth={lb_nw}")
            after_open = sorted(set(shard_req))
            if len(after_open) < 2:
                failures.append(
                    f"{tag} 开灯廊后未按需拉取猫片：{after_open}")
            for _ in range(5):
                page.evaluate("document.getElementById('lbNext').click()")
                page.wait_for_timeout(180)
            page.wait_for_selector("#lightbox.open #lbImg.show", timeout=10000)
            after_flip = sorted(set(shard_req))

            # 关影廊 → 搜索列表缩略图（__bindLazy）→ 连开 3 张档案卡
            page.evaluate("document.getElementById('lbClose').click()")
            page.wait_for_selector("#lightbox", state="hidden")
            page.evaluate("document.getElementById('btnFind').click()")
            page.wait_for_selector("#find.open")
            page.wait_for_selector("#fdBody .fRow", timeout=8000)
            # 原生 loading=lazy 只在入屏后解析：逐批滚动列表到底，再断言全解码
            page.evaluate(
                "new Promise(res=>{const el=document.getElementById('find');"
                "let y=0;const t=setInterval(()=>{y+=600;el.scrollTop=y;"
                "if(y>=el.scrollHeight){clearInterval(t);res();}},16);})")
            page.wait_for_function(
                "Array.from(document.querySelectorAll('#fdBody img')).every("
                "i=>!i.dataset.pkey||i.naturalWidth>0)", timeout=15000)
            rows = page.evaluate(
                "Array.from(document.querySelectorAll('#fdBody .fRow')).slice(0,3)"
                ".map(r=>r.dataset.id)")
            last_nw = 0
            for cid in rows:
                page.evaluate(
                    "id=>{const r=document.querySelector('#fdBody .fRow[data-id=\"'+id+'\"]');"
                    "if(r)r.click();}", cid)
                page.wait_for_selector("#card.open", timeout=8000)
                page.wait_for_function(
                    "document.getElementById('cardImg').naturalWidth>0",
                    timeout=10000)
                cur_id = page.evaluate(
                    "document.getElementById('cardTitle').textContent")
                if cid not in cur_id:
                    failures.append(f"{tag} 开卡身份错位：点 {cid} 开成 {cur_id}")
                last_nw = page.evaluate(
                    "document.getElementById('cardImg').naturalWidth")
                page.keyboard.press("Escape")
                page.wait_for_timeout(60)
            if last_nw < 100:
                failures.append(f"{tag} 档案卡照片未解码：{last_nw}")

            if errs:
                failures.append(f"{tag} pageerror：{errs[:3]}")
            if failed:
                failures.append(f"{tag} 失败请求：{sorted(set(failed))[:3]}")
            page.screenshot(path=str(shots /
                                     f"smoke_{'file' if args.file else 'http'}"
                                     f"_{path.strip('/')}.png"))
            summary[tag] = {
                "seen": seen, "initial_shards": init_shards,
                "initial_photo_bytes": init_bytes,
                "shards_after_lightbox": after_open,
                "shards_after_5flips_and_cards": after_flip,
                "lightbox_natural_width": lb_nw,
                "card_natural_width": last_nw,
            }
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{tag} 冒烟异常：{exc}")
            try:
                page.screenshot(path=str(shots / f"fail_{path.strip('/')}.png"))
            except Exception:
                pass
        finally:
            page.close()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])

        if not args.file:
            g = browser.new_page(viewport={"width": 1280, "height": 900})
            gerr: list[str] = []
            g.on("pageerror", lambda e: gerr.append(str(e)))
            try:
                g.goto(url("/gallery/"), wait_until="networkidle", timeout=45000)
                btns = g.evaluate(
                    "Array.from(document.querySelectorAll('.mini'))"
                    ".map(a=>a.getAttribute('href'))")
                # 每校卡片 2 个 + 页尾 1 个；M2 起另含「申请收录/种子流程」入口，
                # 故只卡下限与有效性，不锁死总数
                if len(btns) < 4 or any(not b for b in btns):
                    failures.append(f"/gallery/ 按钮集合异常：{btns}")
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

        check_starmap(browser, "/demo/", 2)
        check_starmap(browser, "/nuc/", 76)
        browser.close()

    if httpd:
        httpd.shutdown()
    print(json.dumps({"ok": not failures, "mode": "file" if args.file else
                      "http", "summary": summary, "failures": failures},
                     ensure_ascii=False, indent=1))
    if failures:
        print(f"::error::浏览器冒烟 {len(failures)} 项失败（截图：{args.shots}）",
              file=sys.stderr)
        return 1
    print(f"浏览器冒烟全部通过（{'file://' if args.file else 'http'}），"
          f"截图：{args.shots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
