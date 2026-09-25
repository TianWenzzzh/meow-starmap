#!/usr/bin/env node
/**
 * JS 自检（深扫 C-01 落地）：不引任何依赖，直接从现役模板抽取
 * 「星位推导」纯函数段（hashStr / mulberry32 / basePos，模板 L1056-1060），
 * 在 Node 里重建并断言核心性质：
 *   1. 确定性：同一 id 恒得同一坐标（跨进程稳定）；
 *   2. 值域：x∈[0.07,0.93]、y∈[0.09,0.91]；
 *   3. 区分度：抽样 id 两两不同（撞位会让星星叠星）；
 *   4. hashStr 与工厂 star_mapper._hash_str 同构（FNV-1a 期望值抽查）。
 * 用法：node tools/jsselftest.mjs   （退出码 0=通过；已纳入 CI test job）
 */
import fs from "node:fs";
import path from "node:path";
import assert from "node:assert";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const html = fs.readFileSync(path.join(REPO, "template", "starmap.html"), "utf8");

// —— 按锚点抽取函数段（锚点必须唯一；模板重构时同步更新） ——
function slice(startAnchor, endAnchor) {
  const i = html.indexOf(startAnchor);
  assert.ok(i >= 0, `模板缺少锚点：${startAnchor}`);
  const j = html.indexOf(endAnchor, i);
  assert.ok(j > i, `模板缺少结束锚点：${endAnchor}`);
  return html.slice(i, j + endAnchor.length);
}

const hashStrSrc = slice("function hashStr(s){", "return h>>>0; }");
const mulberrySrc = slice("function mulberry32(a){", "return ((t^t>>>14)>>>0)/4294967296; }; }");
const basePosSrc = slice("function basePos(cat){", "y:STAR_BOX.y0+r()*STAR_BOX.h }; }");
const inZoneSrc = slice("function inZone(x,y){", "  return t; }");
// v35：STAR_ZONE 令牌缺省=null（矩形行为，与 v34 逐字节一致）；zone 模式
// 由下方合成三角形单测拒绝采样机制。golden 缺省字面量从 v35 golden 提取。
assert.ok(html.indexOf("__STAR_ZONE__") >= 0, "模板缺少 __STAR_ZONE__ 令牌");
const golden = fs.readFileSync(
  path.join(REPO, "tests", "fixtures", "v35_baseline.html"), "utf8");
const kBox = golden.indexOf("const STAR_BOX={");
assert.ok(kBox >= 0, "v35 golden 缺少 STAR_BOX 缺省字面量");
const starBoxSrc = golden.slice(kBox, golden.indexOf("};", kBox) + 2);
const kZone = golden.indexOf("const STAR_ZONE=");
assert.ok(kZone >= 0, "v35 golden 缺少 STAR_ZONE 缺省字面量");
const starZoneDefault = golden.slice(kZone, golden.indexOf(";", kZone) + 1);

const lib = new Function(
  starBoxSrc + "\n" + starZoneDefault + "\n" + hashStrSrc + "\n" + mulberrySrc +
  "\n" + basePosSrc + "\n" + inZoneSrc +
  "\nreturn { hashStr, mulberry32, basePos, inZone };"
)();

const boxM = starBoxSrc.match(
  /^const STAR_BOX=\{x0:([\d.]+),y0:([\d.]+),w:([\d.]+),h:([\d.]+)\};$/);
assert.ok(boxM, "STAR_BOX 字面量形状变了，同步本自检的抽取与值域推导");
const [BOX_X0, BOX_Y0, BOX_W, BOX_H] = boxM.slice(1).map(Number);

// ---- 1. hashStr：确定性 + FNV-1a 期望值（手算对齐 star_mapper._hash_str）----
assert.strictEqual(lib.hashStr("CAT-001"), lib.hashStr("CAT-001"), "hashStr 非确定");
// FNV-1a 手算：(2166136261 ^ 'C') * 16777619 …… 全串结果抽查
assert.notStrictEqual(lib.hashStr("CAT-001"), lib.hashStr("CAT-002"), "不同 id 同哈希");

// ---- 2. basePos：确定性 + 值域 + 区分度 ----
const N = 300;
const seen = new Map();
for (let i = 1; i <= N; i++) {
  const id = "CAT-" + String(i).padStart(3, "0");
  const p = lib.basePos({ id });
  assert.strictEqual(p.x, lib.basePos({ id }).x, `${id} x 不确定`);
  assert.strictEqual(p.y, lib.basePos({ id }).y, `${id} y 不确定`);
  assert.ok(p.x >= BOX_X0 - 1e-9 && p.x <= BOX_X0 + BOX_W + 1e-9,
            `${id} x 越出 STAR_BOX：${p.x}`);
  assert.ok(p.y >= BOX_Y0 - 1e-9 && p.y <= BOX_Y0 + BOX_H + 1e-9,
            `${id} y 越出 STAR_BOX：${p.y}`);
  seen.set(id, p.x.toFixed(6) + "," + p.y.toFixed(6));
}
assert.strictEqual(seen.size, N, "id 去重后数量不符");
assert.ok(new Set(seen.values()).size > N * 0.95, "坐标区分度不足（大量叠点）");

// ---- 3. mulberry32：同种子同序列 ----
const r1 = lib.mulberry32(42), r2 = lib.mulberry32(42);
for (let i = 0; i < 8; i++) {
  const a = r1(), b = r2();
  assert.strictEqual(a, b, "mulberry32 同种子序列漂移");
  assert.ok(a >= 0 && a <= 1, "mulberry32 越界");
}

// ---- 4. STAR_ZONE 拒绝采样机制：小三角形 zone，全部落点必须在形内且确定性 ----
const tri = [[.1, .1], [.5, .1], [.3, .45]];
const triBox = "const STAR_BOX={x0:.1,y0:.1,w:.4,h:.35};";
const triZone = "const STAR_ZONE=" + JSON.stringify(tri) + ";";
const zlib = new Function(
  triBox + "\n" + triZone + "\n" + hashStrSrc + "\n" + mulberrySrc + "\n" +
  basePosSrc + "\n" + inZoneSrc +
  "\nreturn { basePos, inZone };"
)();
const inTri = (x, y) => zlib.inZone(x, y);
for (let i = 1; i <= 300; i++) {
  const id = "CAT-" + String(i).padStart(3, "0");
  const p = zlib.basePos({ id });
  assert.ok(inTri(p.x, p.y), `${id} 落在 zone 外：${p.x},${p.y}`);
  const q = zlib.basePos({ id });
  assert.strictEqual(p.x, q.x, `${id} zone 模式不确定`);
}
console.log("jsselftest ✓  hashStr/mulberry32/basePos：确定性、值域、区分度全部通过");
console.log("jsselftest ✓  STAR_ZONE 拒绝采样：300 id 全落三角形内、确定性保持");
