// Copies the client-side parts of the data bundle (boundaries, downloads, live)
// into public/data so they are served as static files. Pages themselves read
// the bundle at build time. Works on Windows and Linux.
import fs from 'node:fs';
import path from 'node:path';

const site = path.resolve(import.meta.dirname, '..');
const dataDir = path.resolve(site, process.env.DATA_DIR ?? '../.data/site');
const out = path.join(site, 'public', 'data');

if (!fs.existsSync(path.join(dataDir, 'meta.json'))) {
  console.error(`No data bundle at ${dataDir}. Run "uv run ingest compose" first or set DATA_DIR.`);
  process.exit(1);
}
fs.rmSync(out, { recursive: true, force: true });
for (const sub of ['boundaries', 'downloads', 'live']) {
  const src = path.join(dataDir, sub);
  if (fs.existsSync(src)) fs.cpSync(src, path.join(out, sub), { recursive: true });
}
console.log(`prepared ${out} from ${dataDir}`);
