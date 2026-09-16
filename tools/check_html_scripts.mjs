#!/usr/bin/env node
/**
 * 通用内联脚本语法门禁（移植自主仓库 scripts/check_inline_scripts.mjs，MIT）。
 *
 * 用法：
 *   node tools/check_html_scripts.mjs <html文件或目录> [更多路径...]
 *   node tools/check_html_scripts.mjs   # 无参 = 检查 template/starmap.html
 *
 * 检查项：HTML 内所有不带 src 的 <script> 块、以及路径下的 .js 文件，
 * 逐一 `node --check`。token 占位符（__FOO__）都是合法 JS 标识符形态，
 * 模板本身也能过；构建产物里则是灌好的真值。
 */
import { readdirSync, readFileSync, statSync, mkdtempSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const args = process.argv.slice(2);
const inputs = args.length
  ? args.map((a) => resolve(a))
  : [join(root, 'template', 'starmap.html')];

for (const p of inputs) {
  if (!existsSync(p)) {
    console.error(`路径不存在：${p}`);
    process.exit(2);
  }
}

const htmlFiles = [];
const jsFiles = [];
function collect(p) {
  const st = statSync(p);
  if (st.isDirectory()) {
    for (const name of readdirSync(p)) {
      if (name === '.git' || name === 'node_modules') continue;
      collect(join(p, name));
    }
  } else if (basename(p).toLowerCase().endsWith('.html')) {
    htmlFiles.push(p);
  } else if (basename(p).toLowerCase().endsWith('.js')) {
    jsFiles.push(p);
  }
}
for (const p of inputs) collect(p);

function inlineScripts(htmlPath) {
  const html = readFileSync(htmlPath, 'utf8');
  const out = [];
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(html))) {
    if (/\bsrc\s*=/i.test(m[1] || '')) continue;
    if (m[2].trim()) out.push(m[2]);
  }
  return out;
}

const tmp = mkdtempSync(join(tmpdir(), 'html-script-check-'));
let total = 0;
let bad = 0;
function check(label, code) {
  total += 1;
  const f = join(tmp, `chunk-${total}.js`);
  writeFileSync(f, code);
  const r = spawnSync(process.execPath, ['--check', f], { encoding: 'utf8' });
  if (r.status !== 0) {
    bad += 1;
    console.error(`✗ ${label}\n${(r.stderr || '').trim()}\n`);
  }
}

for (const f of htmlFiles) {
  inlineScripts(f).forEach((code, i) =>
    check(`${f} 第${i + 1}个内联块`, code));
}
for (const f of jsFiles) check(f, readFileSync(f, 'utf8'));
rmSync(tmp, { recursive: true, force: true });

console.log(`检查完成：${htmlFiles.length} 个 HTML + ${jsFiles.length} 个 .js，共 ${total} 块，失败 ${bad}`);
process.exit(bad ? 1 : 0);
