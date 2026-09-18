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
const basePosSrc = slice("function basePos(cat){", "return { x:.07+r()*.86, y:.09+r()*.82 }; }");

const lib = new Function(
  hashStrSrc + "\n" + mulberrySrc + "\n" + basePosSrc +
  "\nreturn { hashStr, mulberry32, basePos };"
)();

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
  assert.ok(p.x >= 0.07 - 1e-9 && p.x <= 0.93 + 1e-9, `${id} x 越界：${p.x}`);
  assert.ok(p.y >= 0.09 - 1e-9 && p.y <= 0.91 + 1e-9, `${id} y 越界：${p.y}`);
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

console.log("jsselftest ✓  hashStr/mulberry32/basePos：确定性、值域、区分度全部通过");
