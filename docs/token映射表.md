# Token 映射表（v2.7 → 开放模板）

- 基准文件：`05_git仓库_最新v2.6/中北喵星图.html`（3605 行，v2.7）
- 源 sha256：`c91bb67bac00dc517c26704e491c7a6b327fe2d537434991552459968c3851f3`
- 提取器：[`tools/extract_template.py`](../tools/extract_template.py)（52 条规则：8 整块 + 44 字面量）
- 凭据：[`tests/fixtures/nuc_literals.json`](../tests/fixtures/nuc_literals.json)（每条规则的原始字节）
- 硬门禁：[`tests/test_template_roundtrip.py`](../tests/test_template_roundtrip.py) —— 凭据灌回模板必须与基准**逐字节相同**

行号均指基准文件 v2.7。

## 1. 整块 token（8 个）

| Token | 源行号 | 内容 | nuc 值要点 | build.py 来源 |
|---|---|---|---|---|
| `__CATS_BLOCK__` | 964–1193 | `const CATS=[…];` 全量名册 | 76 条 12 字段对象 | 名册 CSV + SPEC §1 推导（coatGroup/features/bio/brightness），JSON 注入 |
| `__CALIB_BLOCK__` | 1247–1277 | `const CALIB={…};` 人工校准坐标（含中北分区注释） | **54 键**（见 §4 事实修正） | `schools/<校>/data/calib.json`（可选；缺失则输出 `{}`，浏览器 basePos 兜底） |
| `__PHOTO_SCRIPTS__` | 950 | 8 个 `<script src="assets/photo-data-NN.js">` 标签 | 8 片 | 按 1,500,000 字节分片计划生成；同条线上的 PH 函数 script **不替换、原样保留** |
| `__AREAS_BLOCK__` | 1740–1745 | 12 个星域标注 `{x,y,t}` | 12 个中北地名 | calib 数据包附带（nuc）；新校按 CSV 出没区 + ZONES 锚点推导 |
| `__AREA_KEYS_BLOCK__` | 2668–2672 | 出没区关键词→分区索引映射 | 29 个中北关键词 | 新校输出 `[]`，`areaIndexOf()` 自动走几何最近回退（源 L2673-2677） |
| `__REL_BLOCK__` | 1736–1739 | 星域关系网 | 2 条实证搭档 | 数据包可选 `relations.json`；缺省 `[]` |
| `__CONST_BLOCK__` | 2821–2834 | 十二星宿名/英文名/故事 | 12 座 | 数据包可选；缺省用 AREAS 地名 + 通用故事占位（数量随 AREAS） |
| `__POSTER_STARS__` | 2724–2725 | 寻猫海报「明星指路」4 只推荐 | 4 个 CAT id + 中北描述 | 缺省按 photoCount 取前 4 只自动生成 |

## 2. 标量与整句 token（44 条规则）

### 2.1 全局叶子（多处复用，字符白名单内可安全落在 HTML/JS/注释三种上下文）

| Token | nuc 值 | 出现点（源行号） |
|---|---|---|
| `__PRODUCT__` | 中北喵星图 | 4, 737, 747, 959, 1598（注释）, 2407, 3159（JS 字符串） |
| `__EN__` | NUC CAT GALAXY | 4, 747, 2407, 3159 |
| `__VERSION__` | v2.7 | 4 |
| `__REPO_URL__` | https://github.com/TianWenzzzh/nuc-cat-starmap | 6, 743（href） |
| `__REPO_DISPLAY__` | github.com/TianWenzzzh/nuc-cat-starmap | 743（文本）, 2413, 2736, 3162, 3313（导出水印） |
| `__CAT_COUNT__` | 76 | 5, 750（chip 首帧）, 823（图鉴环首帧）, 960, 963, 2514, 2624, 3160 及各整句内嵌 |
| `__PHOTO_COUNT__` | 194 | 5（其余 194 均在整句 token 内：740/804/meta） |
| `__SURVEY_DATE__` | 2026-08 | 960, 963, 2411, 2711, 3160 及整句内嵌（791/877/1246） |
| `__LS_PREFIX__` | nuc | 1196（LS_KEY）, 1890/1895（fx）, 2608/2609（seen）, 3364/3371（tip-dismiss） |
| `__MAP_FILE__` | 校园地图-夜空版-web.jpg | 960（注释）, 1195（MAP_SRC） |

### 2.2 整句 / 整块文案（每处一条规则，build.py 按参数拼装）

| Token | 源行 | 语义 |
|---|---|---|
| `__META_DESC__` | 15 | meta description 整句 |
| `__TITLE_TAG__` | 16 | `<title>` 文案（`{产品} · 校园猫咪星系`） |
| `__TAGLINE__` | 739 | 开场屏副标题 |
| `__STATS_LINE__` | 740 | 开场屏统计行（普查 ｜ 只数 ｜ 照片数） |
| `__GUIDE_BOUND__` | 791 | 指南：数据覆盖范围句（校名/日期/只数/文档引用） |
| `__GUIDE_REUSE__` | 803 | 指南：能否复刻问答 |
| `__GUIDE_ACCURACY__` | 804 | 指南：数据准确性问答 |
| `__STATS_FOOT__` | 877 | 星图志页脚留痕（数据源/日期/范围） |
| `__COMMITTEE__` | 2267 | 档案卡落款「XX大学猫咪编制委员会」 |
| `__KING_NAME__` | 2624 | 全收集祝词「中北猫王」 |
| `__POSTER_TITLE__` | 2709 | 寻猫海报大标题 |
| `__POSTER_FILE__` | 2737 | 海报下载文件名 |
| `__EXPORT_MAP_NAME__` | 2598 | 校准 JSON 导出里的底图名 |
| `__SKILL_FOOT_LINE__` | 2734, 3311 | 海报/护照底部署名行（2 处） |
| `__SOUL_LINE__` | 3157 | 本命猫卡金句 |
| `__MILESTONES__` | 2611, 2620 | 裸 JS 里程碑数组（nuc `[10,30,50,76]`；build 按只数推导，2 只 → `[2]`） |
| `__PASS_TITLES_JS__` | 3243 | 裸 JS 护照称号阈值表（满编称号恒挂总只数） |
| CATS 头注释（内嵌 CAT_COUNT/SURVEY_DATE 叶子） | 963 | 名册数据来源注释 |
| `__CALIB_LEAD_COMMENT__` | 1246 | CALIB 头注释（nuc 含「2026-08-17 v6」校准史；新校写「算法推导」） |
| 另：banner 子注释/card 两个 JS 拼接表达式/海报副行/rec 角标/console 两行等 | 960, 2267, 2411, 2711, 3035, 3160, 3202, 3309, 3603, 3604 | 均在提取器规则表逐字可查 |

> 完整权威清单以 `nuc_literals.json` 与提取器源码为准；本表只做导航。

## 3. 刻意保留、不参数化的字节

| 内容 | 位置 | 理由 |
|---|---|---|
| `© 2026 TianWenzzzh` 作者署名 | 5, 14, 3604 | 创作年与原作者署名只许追加不许抹除（MIT/CC BY-NC-SA 要求） |
| chips 静态毛色计数 `20/25/7/24` | 751–754, 825–828 | 首帧占位；源 L2451–2459 的 IIFE 在脚本执行时同步按 CATS 重算覆盖，且开场屏遮挡，无用户可见瞬间 |
| 幸运星「体操」 | 830 | 同上，`pickLucky()`（源 L2470-2475）每日重算覆盖 |
| 金色 `#ffd76a`、SVG path `1.76`、动画参数 `h:76`、CSS `76%` | 多处 | 视觉数值，含数字 76 但与猫数无关（提取器白名单固化） |
| 全部 CSS、星图引擎、交互逻辑（影廊灯箱/护照/本命猫/喵签/季节特效等） | 全文 | 模板即 v2.7 本体，除 token 替换外零改动 |

## 4. 事实修正（相对 6 小时提示词的预设）

1. **CALIB 是 54 键不是 76 键**。v2.7 仅固化建成区 54 个人工锚点，其余 22 只（CAT-002/004/005/006/007/008/012/013/017/018/020/023/025/030/033/038/042/044/045/046/047/049）运行时走 `basePos()`（mulberry32(FNV(id))，源 L1241-1245）。P3 验收按「54 键逐键一致、22 只算法兜底」执行。
2. 模板无裸 `__SCHOOL__` 落点：「中北大学」6 处全部嵌在整句 token 内（meta/指南/委员会/导出图名/两行海报署名）。school 是 build.py 必填参数，但只用于拼装整句。
3. `DOCS_REF`（SKILL.md）、`MAP_FILE`、`SURVEY_DATE` 等仅出现在复合句/表达式 token 内部，无独立替换点。

## 4-bis. P3 构建实测补充（2026-09-16）

1. **photo-data 是 76 键不是 195 键**：75 张猫代表照（basename；1 张被两只猫共用）+ 1 张底图。76 只猫的「照片数量」列合计 **167**；文案里的 **194** 是普查实拍总量（基准 111 + 补充 83，见《归并决策摘要.md》），不是内嵌张数。
2. CSV「代表照片文件」列有 23 行带 `补充视频照片/` 路径前缀，取 basename 后与照片键集 75/75 完全对齐。
3. 75 张原片全部长边 ≤1100、无 EXIF 方向标记；其中 11 张为 207–387KB（v2.7 手工流水线未执行工厂 ≤200KB 预算）。build.py 据此采取「长边合格的 JPEG 原字节嵌入」策略，只对超限/非 JPEG/需旋转重编码——76 个数据行与 v2.7 分片**逐字节相同**（见 test_build_nuc）。
4. v2.7 是手工 8 片（11/9/10/9/9/11/9/8），build.py 按工厂 1,500,000 贪心算法切成 **9 片**；仅分片边界不同，键集与数据行全等，不影响渲染。
5. 中北富数据（人工 bio 小传、54 键 CALIB、AREAS/AREA_KEYS/REL/CONST/POSTER_STARS、里程碑与称号表）存于 `schools/nuc/data/*.json` + `build_meta.json`；新学校只交 12 列 CSV 即可，其余全部自动推导。

## 5. 注入安全约定（build.py 实现）

- `school` / `product` / `en` 做字符集白名单校验（中文、字母、数字、空格、`·`、`—`、`-` 等），拒绝 `< > " ' \\ / &` 与换行——保证同一 token 在 HTML 文本、JS 字符串、注释三上下文同形。
- 结构化数据（CATS/REL/AREAS 等）走 JSON 注入，沿用工厂 `app/injector.py` 的 `_html / _js_str / _js`（`</`→`<\/`、U+2028/2029 处理），MIT 协议 vendor 进 `tools/`。
- `repo_url` 校验 `^https://[A-Za-z0-9.:/_-]+$`。
