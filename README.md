# meow-starmap · 校园猫喵星图开放模板

[![CI](https://github.com/TianWenzzzh/meow-starmap/actions/workflows/ci.yml/badge.svg)](https://github.com/TianWenzzzh/meow-starmap/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data: CC BY-NC-SA 4.0](https://img.shields.io/badge/data-CC%20BY--NC--SA%204.0-ef9421.svg)](DATA-LICENSE)

> 一份名册 CSV + 一个照片文件夹 → 一张**全离线、单文件、可直接发给同学**的校园猫星图。
> 军训断网也能用，零前端基础也能做。

中北大学的 76 只校园猫第一次证明了这件事可行；这个仓库把它做成任何学校都能复刻的开放模板。

🌌 **多校展示墙**：<https://tianwenzzzh.github.io/meow-starmap/gallery/>
（可直接在浏览器里玩：[中北大学 76 只完整版](https://tianwenzzzh.github.io/meow-starmap/nuc/) · [示例校 2 只轻量版](https://tianwenzzzh.github.io/meow-starmap/demo/)）

## 三层架构

```
meow-starmap/
├─ template/starmap.html   # 模板层：从 v2.7 正式版（3320 行）无损提取的 token 模板（MIT）
│                           #   极光开场 / 星图 / 影廊 / 本命猫 / 喵星护照 / 分享卡 全特性
├─ tools/                  # 工具层（仅依赖 Pillow）
│  ├─ build.py             #   构建器：CSV+照片+底图 → 离线星图（含 EXIF 矫正/压缩/分片/转义）
│  ├─ extract_template.py  #   模板提取器（可复跑，52 处替换有次数断言）
│  ├─ extract_nuc_assets.py#   中北资产反解器
│  ├─ starmap_layout.py    #   星位推导（vendor 自 MIT 的喵星图工厂）
│  ├─ check_html_scripts.mjs   # 内联 JS 语法门禁
│  └─ smoke_browser.py     #   Playwright 七项浏览器冒烟
├─ schools/                # 数据层（CC BY-NC-SA 4.0，各校自有）
│  ├─ nuc/                 #   中北大学：76 只名册 + 75 代表照 + 夜空底图 + 归并摘要
│  └─ 示例校/               #   2 只虚构样本 + 占位图，用来跑通流水线
├─ tests/                  # v27…v32 六代字节往返 + 构建等价 + 注入安全 + 产物漂移 + 名册校验（131 项；5 个 golden 自证 skip 属设计内）
├─ gallery/                # 多校展示墙（纯静态，GitHub Pages）
├─ nuc/ · demo/            # Pages 托管的在线体验产物（build.py 生成，勿手改；重建见 docs/PR指南.md §7）
└─ docs/                   # 快速上手 / 普查拍摄规范 / PR 指南 / 自检清单 / 验收证据
```

## 15 分钟快速开始

需要 [uv](https://docs.astral.sh/uv/)；无需手动装 Python 或任何依赖。

```bash
git clone https://github.com/TianWenzzzh/meow-starmap.git
cd meow-starmap

# 用自带示例校（2 只虚构猫）构建
uv run --with pillow tools/build.py --pkg schools/示例校 --out dist/示例校
# 双击 dist/示例校/示例校喵星图.html ✦
```

换成你们学校：复制 `schools/示例校/` → 填名册、放照片、换底图 → 同一条命令。
完整步骤见 **[docs/快速上手.md](docs/快速上手.md)**，
普查拍摄见 **[docs/普查与拍摄规范.md](docs/普查与拍摄规范.md)**，
提交前过一遍 **[docs/复刻自检清单.md](docs/复刻自检清单.md)**，
公开数据按 **[docs/PR指南.md](docs/PR指南.md)** 提 PR。

## 已收录的学校

| 学校 | 在册 | 数据包 | 说明 |
|---|---|---|---|
| 中北大学 | 76 只 | [`schools/nuc/`](schools/nuc/) | 首个全量真实数据包，54 颗星手工校准 |
| 示例校 | 2 只（虚构） | [`schools/示例校/`](schools/示例校/) | 占位样本，可随意删除替换 |

你们学校会是下一颗星吗 ✦

## 质量门禁（本仓库如何保证不翻车）

GitHub Actions（[CI 状态](https://github.com/TianWenzzzh/meow-starmap/actions)）
> 浏览器基线：Chrome/Edge 80+、Safari 13.1+（2020 年起；模板 JS 使用可选链）。更老浏览器不保证渲染。

在每次 push/PR 跑两条线：**131 项 Python 测试**（5 个 golden 自证 skip 属设计内）+ **全仓 HTML/分片语法门禁**，
以及 headless Chromium 对 `/gallery/ /nuc/ /demo/` 的 **http + file:// 双冒烟**
（懒加载网络断言：初始仅底图关键片、灯箱/档案卡按需取片解码、0 pageerror）。
照片默认**分片懒加载**：中北版首屏照片仅 216KB（约为原 11MB eager 全量的 2%），
`--eager-photos` 可出旧整包；两种模式双击 file:// 都能离线玩。

- **字节级往返**：模板由 v2.7 正式版机器提取，把原始数据灌回后与正式版逐字节相同
  （sha256 锁定，golden 基线入库 `tests/fixtures/`，CI 无需私有资产）；
- **中北构建等价**：76 条 CATS 逐字段一致、54 个 CALIB 坐标差 ≤0.02、
  76 个照片键与 v2.7 解码字节/分片行双重 sha256 清单相同；
- **托管产物零漂移**：CI 现场构建 `schools/` 并与 Pages 上的 `nuc/ demo/`
  逐字节比对，模板或数据更新后忘记重建会立即变红；
- **脏数据前置拒绝**：空编号/重复编号/缺照片目录等新手坑在构建期带行号报错；
- **浏览器冒烟**：另有本机完整版 7 项（本命猫/分享卡等），
  证据见 [docs/验收证据-M1.md](docs/验收证据-M1.md)。

## 参与贡献

新手友好、无需前端基础：[CONTRIBUTING.md](CONTRIBUTING.md) /
[快速上手](docs/快速上手.md) / [PR 指南](docs/PR指南.md)，
也可以先用「[新学校意向](https://github.com/TianWenzzzh/meow-starmap/issues/new/choose)」占坑。

## 协议（双层）

- **代码与模板**（template/tools/tests/gallery）：[MIT License](LICENSE)——
  随便改、随便用，保留版权声明即可，包括商业使用；
- **数据与照片**（schools/ 下的名册、照片、底图、普查摘要）：
  [CC BY-NC-SA 4.0](DATA-LICENSE)——署名、非商业、相同方式共享；
  照片著作权归拍摄者，可随时联系下架。

## 相关仓库

- 🏛 [TianWenzzzh/nuc-cat-starmap](https://github.com/TianWenzzzh/nuc-cat-starmap)
  —— 中北喵星图正式版（v2.7），本模板的字节级来源
- 🛠 [TianWenzzzh/catgalaxy-factory](https://github.com/TianWenzzzh/catgalaxy-factory)
  —— 喵星图工厂（FastAPI 在线生成器），本项目的 CSV 契约与落位算法上游；
  T6 收敛后更是**渲染唯一真相**：本仓 `tools/starmap_render.py` 是其
  `app/starmap_render.py` 的 vendor 快照（sha256 由 tests/test_vendor_snapshot.py 锁定，
  升级走「改工厂 → 同步快照 → 发版」）
- 🏫 [TianWenzzzh/nuc-cat-starmap](https://github.com/TianWenzzzh/nuc-cat-starmap)
  —— 中北大学实例（nuc/ 托管产物的来源校），v2.8 起产物由工厂渲染器直出、
  与本仓 `nuc/` 逐字节一致
- 本仓库为纯离线本地模板；原第三方托管在线版已下线，自己构建的产物可免费部署到
  GitHub Pages。

## 给项目点颗 Star ⭐

让更多学校的猫被看见、被记住。Issue 区欢迎提普查问题、兼容问题与新学校 PR。
