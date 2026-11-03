import react from '@vitejs/plugin-react';
import { build } from 'vite';
import { writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

let commit = process.env.VERCEL_GIT_COMMIT_SHA || 'unknown';
if (commit === 'unknown') {
  try { commit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); }
  catch { /* builds from source archives may not have .git metadata */ }
}
await writeFile(resolve('public/version.json'), JSON.stringify({
  commit: commit.slice(0, 40),
  build_date: new Date().toISOString(),
}, null, 2));

await build({
  configFile: false,
  plugins: [react()],
  build: { outDir: 'dist' },
});
