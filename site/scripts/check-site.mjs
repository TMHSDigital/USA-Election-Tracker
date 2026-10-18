// Post-build checks over dist/. Fails the build on:
//  1. citation coverage: any element marked data-figure without a citation
//     marker, or a citation to a source id missing from the Sources page;
//  2. neutrality: banned framing words in rendered text;
//  3. copy style: em dashes or emoji in rendered text;
//  4. JS budget on race and state pages.
import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'node-html-parser';

const dist = path.resolve(import.meta.dirname, '..', 'dist');
const BANNED = [
  /\bkey race\b/i, /\bbattleground\b/i, /\btoss[- ]?up\b/i, /\bsurge[sd]?\b/i, /\blandslide\b/i,
  /\bprojected winner\b/i, /\bwinner\b/i, /\bfrontrunner\b/i, /\bfront-runner\b/i, /\bupset\b/i,
  /\bswing (state|district)\b/i, /\bcompetitive\b/i, /\bsafe seat\b/i, /\bleans? (democratic|republican)\b/i,
];
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}]/u;
const EM_DASH = new RegExp(String.fromCharCode(0x2014));
const JS_BUDGET = 100 * 1024;

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? walk(p) : [p];
  });
}

const files = walk(dist);
const html = files.filter((f) => f.endsWith('.html') && !f.includes(`${path.sep}pagefind${path.sep}`));
const sourcesHtml = fs.readFileSync(path.join(dist, 'sources', 'index.html'), 'utf8');
const sourceAnchors = new Set([...sourcesHtml.matchAll(/id="(src-[^"]+)"/g)].map((m) => m[1]));

const errors = [];
let figures = 0;
for (const file of html) {
  const rel = path.relative(dist, file);
  const raw = fs.readFileSync(file, 'utf8');
  const doc = parse(raw);
  for (const fig of doc.querySelectorAll('[data-figure]')) {
    figures++;
    const cites = fig.querySelectorAll('a[data-cite]');
    if (cites.length === 0) errors.push(`${rel}: figure without citation: "${fig.text.trim().slice(0, 80)}"`);
  }
  for (const a of doc.querySelectorAll('a[data-cite]')) {
    const anchor = (a.getAttribute('href') ?? '').split('#')[1];
    if (!sourceAnchors.has(anchor)) errors.push(`${rel}: citation to missing source anchor ${anchor}`);
  }
  const main = doc.querySelector('main');
  const text = (main ?? doc).text;
  for (const re of BANNED) if (re.test(text)) errors.push(`${rel}: banned framing ${re}`);
  if (EM_DASH.test(doc.text)) errors.push(`${rel}: em dash in page text`);
  if (EMOJI.test(doc.text)) errors.push(`${rel}: emoji in page text`);

  if (/^(races|states)[\\/]/.test(rel)) {
    let bytes = 0;
    for (const s of doc.querySelectorAll('script[src]')) {
      const src = s.getAttribute('src');
      if (!src || /^https?:/.test(src)) continue;
      const local = path.join(dist, src.replace(/^\/USA-Election-Tracker\//, ''));
      if (fs.existsSync(local)) bytes += fs.statSync(local).size;
    }
    for (const s of doc.querySelectorAll('script:not([src])')) bytes += s.text.length;
    if (bytes > JS_BUDGET) errors.push(`${rel}: ${bytes} bytes of JS exceeds budget`);
  }
}

if (figures === 0) errors.push('no data-figure elements found; citation check would be vacuous');
if (errors.length) {
  console.error(errors.slice(0, 100).join('\n'));
  console.error(`\n${errors.length} problem(s) in ${html.length} pages`);
  process.exit(1);
}
console.log(`site checks passed: ${html.length} pages, ${figures} cited figures`);
