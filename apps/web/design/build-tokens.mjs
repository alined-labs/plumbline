// Writes src/styles/tokens.css, src/styles/theme.css and design/contrast-report.md from
// design/tokens.json and design/pairs.json, after you edit either of them:
//
//   pnpm --filter @plumbline/web exec node design/build-tokens.mjs
//
// Node 22.18 or later loads tokens.ts directly; on 22.12 to 22.17 add --experimental-strip-types
// after `node`. src/styles/tokens.test.ts fails until the files are rewritten.
import { readFileSync, writeFileSync } from "node:fs";

import { contrastReport, themeCss, tokensCss } from "./tokens.ts";

const web = new URL("../", import.meta.url);
const read = (path) => JSON.parse(readFileSync(new URL(path, web), "utf8"));
const tokens = read("design/tokens.json");
const checks = read("design/pairs.json");

writeFileSync(new URL("src/styles/tokens.css", web), tokensCss(tokens));
writeFileSync(new URL("src/styles/theme.css", web), themeCss(tokens));
writeFileSync(new URL("design/contrast-report.md", web), contrastReport(tokens, checks));
console.log("wrote src/styles/tokens.css, src/styles/theme.css and design/contrast-report.md");
