# PR 指南：把你们学校的喵星图加进多校展示墙

所有学校数据包以 Pull Request 合入，保证每一份数据都有人审、可溯源。

## 1. Fork 与目录约定

1. Fork 本仓库，clone 你的 fork，新建分支：
   ```bash
   git checkout -b school/<英文短名>
   ```
2. 以 `schools/示例校/` 为蓝本复制目录：
   ```
   schools/<英文短名>/
   ├─ data/
   │  ├─ 猫咪名册.csv            # 必需，UTF-8
   │  ├─ build_meta.json         # 必需，校名与参数
   │  └─ 归并决策摘要_<校名>.md   # 必需
   ├─ photos/                    # 必需，每只猫 1 张代表照
   ├─ map/                       # 可选，1 张底图（缺失构建时自动生成星野底图）
   └─ README.md                  # 必需，见下方模板
   ```
   英文短名用小写字母数字与连字符（如 `tongji`、`sjtu`、`no3-highschool`）。

## 2. 必交内容

- [ ] 名册 12 列完整，编号连续、弃用号留痕；
- [ ] 每只猫有代表照且文件名与名册一致；照片无人脸、无个人信息；
- [ ] 归并决策摘要写明合并/弃用依据；
- [ ] `build_meta.json` 的 `school/product/en/ls_prefix/repo_url` 已改；
- [ ] 本地构建通过：
  ```bash
  uv run --with pillow tools/build.py --pkg schools/<短名> --out /tmp/pr-dist
  python -m unittest discover -s tests   # 不破坏既有测试（模板/工具改动时）
  ```
- [ ] 浏览器打开产物过一遍 [复刻自检清单](复刻自检清单.md)；
- [ ] 数据包总体积建议 < 15MB；单文件不得超过 40MB
      （Git 仓库与 FAT32 介质双重限制），照片超限先按拍摄规范压缩。

## 3. 学校目录 README.md 模板

```markdown
# <校名> 喵星图数据包

- 普查团队：<社团/小组名>
- 联系人：<GitHub 用户名 或 专用邮箱>（不要写私人手机号）
- 普查时段：2026-XX ~ 2026-XX
- 在册数量：N 只 / 代表照 N 张
- 数据与照片许可：CC BY-NC-SA 4.0（默认，如有调整在此声明）
- 照片拍摄者：<名单或「普查团队成员」>；拍摄者可随时联系下架
- 在线浏览：<你们自己的部署链接，可选>
```

## 4. 更新展示墙

在 `gallery/index.html` 的 `SCHOOLS` 数组里加一条（卡片由该数组驱动）：

```js
{ short:"<短名>", name:"<校名>", cats: 12, photos: 12, status:"live",
  cover:"covers/<短名>.jpg",
  try:"../<短名>/", tryBytes:"约 N MB",
  src:"https://github.com/<你>/<fork>",
  note:"<一句话亮点>" }
```

- `status`：`live`（已完整发布，计入「真实校园 / 在编」统计）/ `beta`（样例或收集中，不计入总数）；
- 封面放 `gallery/covers/<短名>.jpg`，800×500（16:10），建议 ≤100 KB（Pillow 压缩或截图后导出）；
- `try` 指向仓库根目录下由 Pages 托管的产物目录（见第 7 节）；`src` 指向你的数据包仓库或教程。

## 5. 提交与 PR 信息

- 提交信息建议：`feat(school): 新增<校名>数据包（N只）`；
- PR 标题：`[新学校] <校名>（N 只）`；
- PR 描述里勾选第 2 节清单，并附：普查团队授权说明
  （「照片已获拍摄者授权用于本开源项目」）+ 你们自己的浏览器截图
  （至少开场屏与星图主界面各一张）。

## 6. 审查会看什么

- 数据红线（人脸、隐私、证据链、置信度）；
- 构建是否通过、产物有无模板 token 残留；
- 许可声明是否完整；
- 不审查小传文笔——故事属于你们，但拒绝人身攻击与商业广告。

合入后维护者会把卡片上线到展示墙，并视情况打 tag。

## 7. 在线体验产物（Pages 托管）如何重建

仓库根目录的 `nuc/`、`demo/` 是 GitHub Pages 上可直接玩的构建产物，**不要手工修改**。
模板或数据包更新后，用同一条构建命令重建并覆盖（产物名统一改为 `index.html`）：

```bash
# 示例校（约 0.4 MB）
uv run --with pillow tools/build.py --pkg schools/示例校 --out /tmp/demo
cp /tmp/demo/示例校喵星图.html demo/index.html
cp /tmp/demo/assets/photo-data-*.js demo/assets/

# 中北（约 11 MB，9 个照片分片）
uv run --with pillow tools/build.py --pkg schools/nuc --out /tmp/nuc
cp /tmp/nuc/中北喵星图.html nuc/index.html
cp /tmp/nuc/assets/photo-data-*.js nuc/assets/
```

重建后必做：`node tools/check_html_scripts.mjs .`（全仓 HTML 与照片分片语法）
+ 浏览器打开 `/nuc/`、`/demo/` 点一次「影廊」确认照片能解码（见 `docs/screenshots/13、14`）。
新学校 PR 还需要两处登记：
`tests/test_hosted_artifacts.py` 的 `HOSTED` 元组（漂移门禁）
与 `tools/ci_browser_smoke.py` 的期望列表（只数/分片数/按钮 href），
CI 会自动对新托管页跑 headless 冒烟。
新学校 PR 合入后，由维护者按同样方式把产物放到 `<短名>/` 并连通展示墙卡片。
