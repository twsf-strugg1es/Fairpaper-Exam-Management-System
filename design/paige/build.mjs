// Writes every Paige pose as an SVG file for the app and the landing page, and copies the
// drawing script the landing page uses inline. Run: node design/paige/build.mjs
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..', '..');
const Paige = createRequire(import.meta.url)('./paige.js');
const targets = [path.join(repo, 'frontend', 'public', 'paige'), path.join(repo, 'scrollcraft', 'builds', 'fairpaper-landing', 'paige')];

for (const dir of targets) {
  fs.mkdirSync(dir, { recursive: true });
  for (const pose of Paige.poses) fs.writeFileSync(path.join(dir, `${pose}.svg`), Paige.svg(pose) + '\n');
}
fs.copyFileSync(path.join(here, 'paige.js'), path.join(targets[1], 'paige.js'));
console.log(`Wrote ${Paige.poses.length} poses (${Paige.poses.join(', ')}) to ${targets.length} folders`);
