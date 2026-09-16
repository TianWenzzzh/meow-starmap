# 参与贡献

欢迎把你们学校的猫点亮进喵星系 ✦ 这个项目对新手友好，不需要前端基础。

## 我想让我的学校上墙

1. 读 [快速上手](docs/快速上手.md)：一份 CSV 名册 + 一个照片文件夹，
   30 分钟、两条命令跑通；底图没有会自动生成。
2. 数据准备过程看 [普查与拍摄规范](docs/普查与拍摄规范.md)，
   提交前过一遍 [复刻自检清单](docs/复刻自检清单.md)。
3. 按 [PR 指南](docs/PR指南.md) 提 PR；不确定能不能做完也没关系，
   可以先在 [Issues](https://github.com/TianWenzzzh/meow-starmap/issues)
   用「新学校意向」模板占个坑。

## 我想改代码 / 修 bug

- 模板的唯一真相是 05 仓库 v2.7 基线；改动 `template/starmap.html` 必须同步
  提取规则与 fixtures，CI 的字节级往返测试会把关。
- `tools/build.py` 与 `tools/starmap_layout.py` vendor 自
  [喵星图工厂](https://github.com/TianWenzzzh/catgalaxy-factory)（MIT），
  两边逻辑需要同步演进，改动请在提交信息里注明。
- 本地门禁（与 CI 一致）：

  ```bash
  uv run --python 3.12 --with pillow python -m unittest discover -s tests -v   # 32 项
  node tools/check_html_scripts.mjs template/starmap.html gallery index.html 404.html nuc/index.html demo/index.html
  uv run --python 3.12 --with playwright python tools/ci_browser_smoke.py       # 可选：浏览器冒烟
  ```

## 数据与许可红线

- 代码 MIT；**各校照片与名册数据 CC BY-NC-SA 4.0**，详见 [DATA-LICENSE](DATA-LICENSE)。
- PR 前必须获得照片拍摄者授权；不接受清晰人脸、投喂点精确 GPS 等隐私信息。
- 小传文笔属于普查团队，但拒绝人身攻击与商业广告。
