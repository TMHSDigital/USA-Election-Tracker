// Repository copy-style check: no em dashes and no emoji in tracked text files
// (site copy, docs, code comments, seeds). Run: node scripts/check-copy.mjs
import { execSync } from 'node:child_process';
import fs from 'node:fs';

const EXT = /\.(md|mdx|astro|ts|tsx|js|mjs|json|ya?ml|py|toml|css|html|csv|txt)$/i;
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}]/u;
const files = execSync('git ls-files -co --exclude-standard', { encoding: 'utf8' })
  .split('\n')
  .filter((f) => f && EXT.test(f) && !f.includes('package-lock.json') && !f.includes('uv.lock') && !f.startsWith('ingest/tests/fixtures/'));

const problems = [];
for (const f of files) {
  if (!fs.existsSync(f)) continue;
  const lines = fs.readFileSync(f, 'utf8').split('\n');
  lines.forEach((line, i) => {
    if (line.includes(String.fromCharCode(0x2014))) problems.push(`${f}:${i + 1}: em dash`);
    if (EMOJI.test(line)) problems.push(`${f}:${i + 1}: emoji`);
  });
}
if (problems.length) {
  console.error(problems.join('\n'));
  process.exit(1);
}
console.log(`copy check passed (${files.length} files)`);
