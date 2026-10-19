# Design

Plumbline is built on the Alined DS, the design system of Alined Labs: calm, precise and evidence-first. It is dense where data is dense, generous where people read, and neutral almost everywhere, with one accent (indigo) and one highlighter (yellow). Plumbline is the system's first product, and the tokens in this repository are Plumbline's theme.

Every value the interface uses comes from the tokens. A colour, size, radius, shadow or duration written anywhere else is a bug.

## Where it lives

| What | Where |
| --- | --- |
| The tokens, the source of truth: W3C design tokens format, light and dark | [`apps/web/design/tokens.json`](apps/web/design/tokens.json) |
| CSS variables (`--pl-*`), generated | [`apps/web/src/styles/tokens.css`](apps/web/src/styles/tokens.css) |
| Tailwind 4 theme, generated | [`apps/web/src/styles/theme.css`](apps/web/src/styles/theme.css) |
| The generator: the script, and the module that reads, checks and converts the tokens | [`apps/web/design/build-tokens.mjs`](apps/web/design/build-tokens.mjs), [`apps/web/design/tokens.ts`](apps/web/design/tokens.ts) |
| Contrast pairs and colours that must stay apart, and the test that enforces them and the generated files | [`apps/web/design/pairs.json`](apps/web/design/pairs.json), [`apps/web/src/styles/tokens.test.ts`](apps/web/src/styles/tokens.test.ts) |
| Contrast report: every pair in both themes, with colour-vision distances, generated | [`apps/web/design/contrast-report.md`](apps/web/design/contrast-report.md) |
| Component specs | [`apps/web/design/components.md`](apps/web/design/components.md) |
| Reference markup and CSS for every component | [`apps/web/design/reference/`](apps/web/design/reference/) |
| Fonts (SIL Open Font License) and their loader | [`apps/web/src/fonts/`](apps/web/src/fonts/), [`apps/web/src/lib/fonts.ts`](apps/web/src/lib/fonts.ts) |
| Icons (Lucide, ISC licence) | [`apps/web/src/components/icons.tsx`](apps/web/src/components/icons.tsx) |
| The logo: files, and an inline component | [`apps/web/public/brand/`](apps/web/public/brand/), [`apps/web/src/components/brand/logo.tsx`](apps/web/src/components/brand/logo.tsx) |
| Favicons, app icons, the web manifest and the link preview | [`apps/web/src/app/`](apps/web/src/app/), [`apps/web/public/icons/`](apps/web/public/icons/) |

## Principles

1. **Evidence first.** Every claim about the law carries a citation marker, and every marker opens the passage on its page. Design the citation before the sentence.
2. **The law speaks in serif.** The statutes' own words, verbatim, are set in Source Serif 4. Plumbline's words are set in Atkinson Hyperlegible Next. The two never mix in one block.
3. **Abstaining is an answer.** When no passage supports an answer, Plumbline says so in neutral colours, names what it checked and offers a next step. Never red, never an apology.
4. **One accent.** `accent` marks the one primary action, links, selection, focus and citation markers. `highlight` marks only the cited span. Everything else is ink on paper.
5. **Show the work.** Status steps while an answer streams, a trace behind every answer, an interval beside every metric.

## Using the tokens

The theme resets Tailwind's colours, type sizes, radii, shadows (box, inset, drop and text) and easings to the system's, so `text-sm`, `bg-white`, `shadow-md`, `rounded-2xl` and `ease-in` do not exist. A class outside the system compiles to nothing: it fails silently rather than drifting, so search for leftovers when you restyle. Spacing, breakpoints, font weights, line heights and tracking keep Tailwind's defaults; prefer the type styles to `leading-*` and `tracking-*`.

- **Colours:** `bg-surface`, `text-fg-muted`, `border-border-control`, `fill-brand`, `ring-focus`, and so on for every colour role below.
- **Type:** `text-body`, `text-heading-2`, `text-quote` and the rest set size, line height, tracking and weight together. Pair `text-quote` and `text-quote-sm` with `font-serif`; `text-eyebrow` with `font-mono uppercase`; `text-code` and `text-code-sm` with `font-mono`. Add `tabular-nums` in tables, metrics and timers.
- **Space:** Tailwind's 4px scale, unchanged: `p-4` is 16px, `gap-2` is 8px.
- **Radii, shadows, easing:** `rounded-md`, `shadow-2`, `ease-standard`. A bare `transition` runs for `--pl-duration-fast` (140ms) with `ease-standard`.
- **Widths:** `max-w-content` (720px reading column), `max-w-panel` (440px source panel).
- **Breakpoints:** Tailwind's defaults, which are the system's: 640, 768, 1024, 1280, 1536.
- **Everything else** through the variable shorthand: `w-(--pl-sidebar-width)`, `h-(--pl-control-md)`, `z-(--pl-z-dialog)`, `duration-(--pl-duration-base)`.

Outside Tailwind, read the variables directly: `var(--pl-color-surface)`, `var(--pl-text-body)`, `var(--pl-radius-lg)`. The base styles in `globals.css` sit in Tailwind's base layer, so a utility always wins over them.

### Colour roles

| Role | Tokens | Use |
| --- | --- | --- |
| Grounds | `bg`, `bg-subtle`, `surface`, `surface-raised`, `surface-sunken`, `bg-hover`, `bg-active`, `inverse`, `overlay` | Canvas; sidebar and table headers; cards and panels; popovers and dialogs; the composer well and code; hover and pressed fills; tooltips and toasts; scrims |
| Text | `fg`, `fg-muted`, `fg-subtle`, `fg-disabled`, `fg-inverse` | Primary, secondary, placeholder and tertiary, disabled (exempt from contrast), and text on `inverse` |
| Lines | `border-subtle`, `border`, `border-strong`, `border-control` | Decorative dividers, outlines and the edges of secondary buttons and chips; `border-control` (3:1) for anything that must be seen to be used, inputs and the composer included |
| Accent | `accent`, `accent-hover`, `accent-active`, `accent-fg`, `accent-subtle`, `accent-subtle-hover`, `accent-border`, `accent-text`, `focus`, `focus-inverse` | The primary button, links, selection, citation markers and the focus ring (`focus-inverse` on `inverse`) |
| Highlight | `highlight`, `highlight-strong`, `highlight-edge` | The cited span and its active state |
| Status | `success`, `warning`, `danger`, each with `-bg` and `-border`; `danger-hover`; `on-status`; `neutral`, `neutral-bg`, `neutral-border` | Verified, worth checking, conflicts with the law; `neutral` for abstentions |
| Paper | `paper`, `paper-highlight`, `paper-highlight-edge` | The statute's PDF page, which stays white in both themes |
| Brand | `brand`, `brand-facet`, `brand-fg` | The logo, which keeps its colours in both themes |
| Data | `chart-1` to `chart-5`, `chart-grid`, `chart-axis` | Series in jurisdiction order (AE-DU, ES, CO, US-FL), then the baseline |
| Code | `syntax-string`, `syntax-number`, `syntax-literal` | JSON in trace and log views |

Each token's usage note in `tokens.json` names the grounds it is checked on.

### Type

| Style | Size / line height | Family | Use |
| --- | --- | --- | --- |
| `display` | 44 / 48 | sans | Portfolio and landing headlines; never inside the app |
| `heading-1` | 28 / 34 | sans | Page titles |
| `heading-2` | 21 / 28 | sans | Sections, dialogs, the statute name in the source panel |
| `heading-3` | 17 / 24 | sans | Groups |
| `kpi` | 32 / 36 | sans | Headline metric values |
| `body-lg` | 17 / 28 | sans | Plumbline's answers |
| `body` | 15 / 24 | sans | Paragraphs in panels, dialogs and empty states; the page default |
| `input` | 16 / 24 | sans | Text typed into the composer, and into fields on phones, so the page doesn't zoom on focus |
| `ui`, `ui-strong` | 14 / 20 | sans | Controls, menus, tables; labels that lead a row |
| `small` | 13 / 18 | sans | Metadata, captions, helper text |
| `micro` | 12 / 16 | sans | Counts in badges, chart ticks; never body text |
| `quote` | 17 / 28 | serif | The law's own words in answers and the source panel |
| `quote-sm` | 15 / 24 | serif | Statute passages in cards and tables |
| `eyebrow` | 11 / 16, +0.08em, uppercase | mono | Labels above sections |
| `code`, `code-sm` | 13 / 20, 12 / 16 | mono | IDs, hashes, trace data; jurisdiction codes and citation numbers |

Atkinson Hyperlegible Next keeps `1`, `l` and `I` apart, which matters in "s. 83.49(3)(a)1." and "art. 9(1)(l)", and its zero is slashed. Source Serif 4 is pinned to its text optical size.

### Space, radius, elevation, motion, layout

- A 4px grid. Controls pad 12 to 14px across, cards 16px, panels 24px; 32px between conversation turns.
- Radii: `xs` 3 for highlights and keys, `sm` 5 for badges and markers, `md` 8 for buttons and inputs, `lg` 12 for cards and panels, `xl` 16 for dialogs and sheets, `full` for pills.
- Elevation is mostly borders: `shadow-1` for the composer and sticky headers, `shadow-2` for popovers, `shadow-3` for dialogs and sheets. In the dark theme `shadow-2` and `shadow-3` add a faint white edge, so raised surfaces still separate.
- Motion is short and functional: 80ms feedback, 140ms popovers, 200ms panels, 320ms sheets. Under `prefers-reduced-motion` every duration is 0.
- The app is three panes: the sidebar (248px, rail 56px), the conversation in a 720px column, and the source panel (440px, resizable from 360 to 640). Below 1024px the panel overlays; below 768px it becomes a bottom sheet and every target is at least 44px.

## Themes

The light theme is the default and `prefers-color-scheme: dark` switches to dark. `data-theme="light"` or `data-theme="dark"` on `<html>` overrides both, for a theme switch. The variables change, so components need no `dark:` variants. The statute page (`paper`) and the logo (`brand`) keep their colours in both themes.

## Fonts

The three families are self-hosted through `next/font/local` and subset to Latin, Spanish included. Put `fontVariables` from [`src/lib/fonts.ts`](apps/web/src/lib/fonts.ts) on `<html>`, not on `<body>`: `tokens.css` reads the `--pl-face-*` variables at the root. Only the sans family is preloaded; the serif and mono faces load when a page uses them.

## Icons

Lucide, outline, 1.75 stroke, `currentColor`: 16px in controls and badges, 20px in empty and error states. Import them from `@/components/icons` (`CircleCheckIcon`, `ArrowUpIcon`, and so on). A status keeps its icon: `circle-check` success, `triangle-alert` warning, `octagon-alert` danger, `circle-dashed` abstained, `info` info.

## Logo

The mark is a plumb bob on its string, hanging from the top edge of an indigo tile and split down the plumb axis into a lit facet and a shaded one. A plumb line defines the true vertical; Plumbline holds each lease clause against the statute in the same way.

- In the app, use `Logo` (the lockup) or `LogoMark` (the tile) from [`src/components/brand/logo.tsx`](apps/web/src/components/brand/logo.tsx), inside a link named "Plumbline home" whose target is at least 24px high (44px on touch layouts). They draw with the `brand` tokens, and the wordmark takes the current text colour, so one component serves both themes.
- Files for everything else are in [`public/brand/`](apps/web/public/brand/): `lockup.svg` on light grounds, `lockup-dark.svg` on dark ones, `lockup-stacked*.svg` for square spaces, `mark-display*.svg` (finer string) above 200px, and `*-mono-black.svg` and `*-mono-white.svg` for one colour, with the bob cut out of the tile.
- Clear space is half the tile's width on every side. The minimum is 16px for the tile and 18px high (about 96px wide) for the lockup.
- Never draw the logo with `accent`, which turns lavender in the dark theme. Never set the wordmark in live text, recolour, rotate or outline the mark, add a dot or a line under the tip (it becomes a download icon), or round the bob into a teardrop (it becomes a map pin).

For the README header:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="apps/web/public/brand/lockup-dark.svg">
  <img src="apps/web/public/brand/lockup.svg" alt="Plumbline" height="48">
</picture>
```

## Components

Thirty components, specified in [`apps/web/design/components.md`](apps/web/design/components.md) with their anatomy, tokens, states and accessibility, and drawn in [`apps/web/design/reference/`](apps/web/design/reference/):

- **Brand:** Logo.
- **Actions:** Button.
- **Status:** Badge.
- **Citations:** CitationMarker, SourceCard, StatuteQuote, SourcePanel.
- **Answers:** Answer, PartialAnswer, Abstention, StatusSteps.
- **Inputs:** Composer, Field.
- **Feedback:** Callout, Feedback.
- **Overlays:** Dialog, Toast.
- **Lease check:** Dropzone, FindingCard.
- **Data:** Table, Metric, Chart, TraceWaterfall.
- **Navigation:** Tabs, Sidebar.
- **Layout:** AppShell.
- **States:** EmptyState, Skeleton, ErrorState, UsageMeter.

## Content

- English with British spelling ("colour", "licence"). Statutes and leases are quoted in their own language, with `lang="es"` on Spanish passages.
- Plain English, second person, short sentences: "Your landlord has 15 days to return the deposit." Plumbline speaks as "I" in answers and abstentions, never "we" and never "As an AI".
- Buttons are a verb and its object in sentence case: "Check lease", "Copy reference". Errors say what happened, then the fix.
- Numbers as digits, units spelled out: "15 days", "4.2 s". Dates as "19 Oct 2026".
- Citations in each jurisdiction's own style: `Fla. Stat. § 83.49(3)(a)`, `Ley 29/1994, art. 9.1`, `Ley 820 de 2003, art. 20`. Jurisdictions by name in prose and by code in badges: `AE-DU`, `ES`, `CO`, `US-FL`, always in that order.
- Legal information, not legal advice. The full disclaimer is the API's, word for word, from [`src/lib/copy.ts`](apps/web/src/lib/copy.ts), in the page footer; the short line "Legal information, not legal advice." sits under the composer. Never "AI lawyer", "guaranteed" or "100% accurate", and no line that promises a lease is lawful.
- No emoji, no exclamation marks, no "simply", no "just".

## Accessibility

The target is WCAG 2.2 AA in both themes.

- **Contrast:** text holds 4.5:1 on every ground its usage note names, in light and dark; control edges, focus rings, meaningful icons and chart marks hold 3:1. `tokens.test.ts` checks every pair in `pairs.json` on every unit-test run, axe checks the rendered pages in the end-to-end tests, and Lighthouse checks again.
- **Colour is never the only cue:** a status pairs its colour with an icon and a word. `danger` is darker than `success` and `warning`, which differ in hue rather than lightness; the test keeps every status pair and every chart pair at least 7 CIEDE2000 apart, with normal vision and under simulated protanopia, deuteranopia and tritanopia.
- **Focus:** a 2px `focus` ring, offset 2px, on every interactive element, for keyboard focus only; on `inverse` (the toast) the ring is `focus-inverse`. `/` focuses the composer; Escape closes the panel, popover or dialog and returns focus to what opened it.
- **Screen readers:** the status steps are one polite live region; an answer announces when it is complete, not every token; charts carry a data table.
- **Targets, zoom and motion:** targets of at least 24px everywhere and 44px on touch layouts; text sizes in rem; no sideways scrolling at 320px; no motion under `prefers-reduced-motion`.

## Changing a token

1. Edit [`apps/web/design/tokens.json`](apps/web/design/tokens.json), with a dark value in `$extensions["co.alinedlabs.modes"].dark` whenever it differs from the light one.
2. For a colour that text or a mark is drawn in, add or update its pair in [`apps/web/design/pairs.json`](apps/web/design/pairs.json); for one that must be told apart from others, add it to a group under `distinct`.
3. Run `pnpm --filter @plumbline/web exec node design/build-tokens.mjs` to rewrite `tokens.css`, `theme.css` and the contrast report.
4. Run `pnpm --filter @plumbline/web test`: it fails if a generated file disagrees with the JSON, if a pair falls under its minimum, or if two colours that must stay apart come too close.
