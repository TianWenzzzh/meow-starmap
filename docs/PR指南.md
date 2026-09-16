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
   ├─ map/                       # 必需，1 张底图
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

在 `gallery/index.html` 的 `SCHOOLS` 数组里加一条（卡片由此数组驱动）：

```js
{ short:"<短名>", name:"<校名>", cats: 76, status:"live",
  shots:"../schools/<短名>/", cover:"../docs/screenshots/<封面>.png",
  note:"<一句话亮点>" }
```

`status`：`live`（已完整发布）/ `beta`（收集中）。封面图建议自存一张
16:9 截图放入你们的学校目录（如 `schools/<短名>/cover.png`）。

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
