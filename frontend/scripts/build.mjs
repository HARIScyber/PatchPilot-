import react from '@vitejs/plugin-react';
import { build } from 'vite';
import { writeFile, mkdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(__dirname, '..');

let commit = process.env.VERCEL_GIT_COMMIT_SHA || 'unknown';
if (commit === 'unknown') {
  try { commit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); }
  catch { /* builds from source archives may not have .git metadata */ }
}
const publicDir = resolve(frontendDir, 'public');
await mkdir(publicDir, { recursive: true });
await writeFile(resolve(publicDir, 'version.json'), JSON.stringify({
  commit: commit.slice(0, 40),
  build_date: new Date().toISOString(),
}, null, 2));

await build({
  root: frontendDir,
  configFile: false,
  plugins: [react()],
  build: { outDir: resolve(frontendDir, 'dist') },
});

