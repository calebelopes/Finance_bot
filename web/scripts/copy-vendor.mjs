// Copies third-party browser bundles out of node_modules into the app's
// static/ tree so they are served from our own origin (no CDNs). Run as
// part of `npm run build`.

import { copyFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

const jobs = [
  ["node_modules/preline/dist/preline.js", "web/static/js/vendor/preline.js"],
  ["node_modules/htmx.org/dist/htmx.min.js", "web/static/js/vendor/htmx.min.js"],
];

for (const [src, dest] of jobs) {
  await mkdir(dirname(dest), { recursive: true });
  await copyFile(src, dest);
  console.log(`copied ${src} -> ${dest}`);
}
