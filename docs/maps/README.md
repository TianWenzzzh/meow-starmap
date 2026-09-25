# docs/maps · 底图素材

| 文件 | 是什么 |
|---|---|
| `手绘版-日间-全分辨率-v2.jpg` | 手绘日间原图（10114×5905，宽高比 1.7128） |
| `手绘版-夜空-v2.jpg` | 手绘夜空素材版，**按原比例**由 `tools/make_hand_night_map.py` 重出——v1 那份被 `_finalize_maps.py` 硬 resize 进官方图比例（1.7128→1.5489，纵向拉伸 10.6%），已修复 |
| `官方底图-夜空版-web-参考.jpg` | 旧官方夜空底图（自 `schools/nuc/map/` 退场前留档），仅作夜空配色拟合的参照物，不再进产物 |

产线：`uv run --python 3.12 --with pillow --with numpy python tools/make_hand_night_map.py --out <路径>`（默认出 `schools/nuc/map/手绘版-夜空-web.jpg`；断言长边 1920、宽高比与源差 <0.002、体积 <300KB）。

现役产物底图 = `schools/nuc/map/手绘版-夜空-web.jpg`（1920×1121，原字节嵌入）。
