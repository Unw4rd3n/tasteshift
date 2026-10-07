// Encoding only: original artwork and transparency are preserved.
// Usage: node scripts/optimize-assets.mjs [path-to-sharp-package]
import { createRequire } from "node:module";
import { readdir, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const sharp = require(process.argv[2] || "sharp");
const source = fileURLToPath(
  new URL("../design/source-assets/", import.meta.url),
);
const target = fileURLToPath(new URL("../public/assets/", import.meta.url));
let total = 0;
for (const file of await readdir(source)) {
  if (!file.endsWith(".png")) continue;
  const background = file === "space-background.png";
  const orbits = file === "orbits.png";
  const out = `${target}${file.replace(/\.png$/, ".webp")}`;
  await sharp(`${source}${file}`)
    .resize({
      width: background ? 1440 : orbits ? 1550 : 512,
      withoutEnlargement: true,
    })
    .webp({ quality: orbits ? 95 : 84, alphaQuality: 100, effort: 6 })
    .toFile(out);
  const bytes = (await stat(out)).size;
  total += bytes;
  console.log(`${file}: ${Math.round(bytes / 1024)} KiB`);
}
console.log(`Total: ${Math.round(total / 1024)} KiB`);
