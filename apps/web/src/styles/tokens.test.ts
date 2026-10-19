// @vitest-environment node
import { readFileSync } from "node:fs";

import {
  THEMES,
  VISIONS,
  contrast,
  contrastReport,
  distances,
  pairsOf,
  resolveColors,
  themeCss,
  tokensCss,
  type Checks,
  type Tokens,
} from "../../design/tokens";

const REGENERATE = "run pnpm --filter @plumbline/web exec node design/build-tokens.mjs";
const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const tokens = JSON.parse(read("../../design/tokens.json")) as Tokens;
const checks = JSON.parse(read("../../design/pairs.json")) as Checks;
const colors = resolveColors(tokens);

describe("design tokens", () => {
  it(`tokens.css is generated from tokens.json (${REGENERATE})`, () => {
    expect(read("./tokens.css")).toBe(tokensCss(tokens));
  });

  it(`theme.css is generated from tokens.json (${REGENERATE})`, () => {
    expect(read("./theme.css")).toBe(themeCss(tokens));
  });

  it(`contrast-report.md is up to date (${REGENERATE})`, () => {
    expect(read("../../design/contrast-report.md")).toBe(contrastReport(tokens, checks));
  });

  it("pairs.json names only colours that exist", () => {
    const names = [
      ...checks.pairs.flatMap((pair) => [pair.fg, ...pair.grounds]),
      ...checks.distinct.groups.flat(),
    ];
    expect(names.filter((name) => !(name in tokens.color))).toEqual([]);
  });

  it.each(THEMES)("every colour pair meets its WCAG 2.2 minimum in the %s theme", (theme) => {
    const c = colors[theme];
    const failures = checks.pairs.flatMap((pair) =>
      pair.grounds
        .map((ground) => ({
          ground,
          ratio: contrast(c[pair.fg] ?? "", c[ground] ?? "", c.bg ?? ""),
        }))
        .filter(({ ratio }) => ratio < pair.min)
        .map(({ ground, ratio }) => `${pair.fg} on ${ground}: ${ratio.toFixed(2)} < ${pair.min}`),
    );
    expect(failures).toEqual([]);
  });

  it.each(THEMES)("colours that must be told apart stay apart in the %s theme", (theme) => {
    const c = colors[theme];
    const close = pairsOf(checks.distinct.groups).flatMap(([one, two]) => {
      const d = distances(c[one] ?? "", c[two] ?? "");
      return VISIONS.filter((vision) => d[vision] < checks.distinct.min).map(
        (vision) => `${one} / ${two}, ${vision}: ${d[vision].toFixed(1)} < ${checks.distinct.min}`,
      );
    });
    expect(close).toEqual([]);
  });
});
