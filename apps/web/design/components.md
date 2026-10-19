# Components

The specs for Plumbline's thirty components, from the Alined DS: anatomy, tokens, states and
accessibility. Each one is drawn in [`reference/`](reference/): open `reference/<Component>.html`
in a browser to see it, and set `data-theme="dark"` on its `<html>` for the dark theme.

The specs name tokens, not classes. In the app, a colour token such as `accent` is `bg-accent`,
`text-accent` or `border-accent` in a class and `--pl-color-accent` in CSS; a type style such as
`small` is `text-small`; `radius-md` is `rounded-md`; `shadow-2` is `shadow-2`; `space-3` is
Tailwind's `3` (12px); `control-md` is `h-(--pl-control-md)`. Class names that start with `al-`
belong to the reference stylesheet (`reference/components.css`), whose `var(--name)` variables are
the same tokens without the app's `--pl-` and `--pl-color-` prefixes. Build the components with
the Tailwind theme rather than copying the `al-` classes. Logo files named without a path are in
`public/brand/`.

Contents: [Logo](#logo) · [Button](#button) · [Badge](#badge) · [CitationMarker](#citationmarker) · [SourceCard](#sourcecard) · [StatuteQuote](#statutequote) · [SourcePanel](#sourcepanel) · [Answer](#answer) · [PartialAnswer](#partialanswer) · [Abstention](#abstention) · [StatusSteps](#statussteps) · [Composer](#composer) · [Field](#field) · [Callout](#callout) · [Feedback](#feedback) · [Dialog](#dialog) · [Toast](#toast) · [Dropzone](#dropzone) · [FindingCard](#findingcard) · [Table](#table) · [Metric](#metric) · [TraceWaterfall](#tracewaterfall) · [Chart](#chart) · [Tabs](#tabs) · [Sidebar](#sidebar) · [AppShell](#appshell) · [EmptyState](#emptystate) · [Skeleton](#skeleton) · [ErrorState](#errorstate) · [UsageMeter](#usagemeter).

## Logo

_Brand_ · reference: [`reference/Logo.html`](reference/Logo.html)

The Plumbline logo is the app icon (a plumb bob hanging on its string inside an indigo tile) beside the wordmark; the files live in the Logos asset group.

### Pick the file

| Where                                                 | File                                                                                                                                                |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| App header, README, slides on light                   | `lockup.svg`                                                                                                                                        |
| Sidebar and other UI chrome                           | `lockup.svg` inlined, with the wordmark fill set to `fg` so it follows the theme                                                                    |
| The same on dark grounds                              | `lockup-dark.svg`                                                                                                                                   |
| Square spaces (avatar, splash)                        | `lockup-stacked.svg`, `lockup-stacked-dark.svg`                                                                                                     |
| Favicon                                               | `src/app/favicon.ico` (16, 32, 48) and `src/app/icon.svg` (the pixel-fitted 32px drawing); `favicon-16.svg` and `favicon-32.svg` in `public/brand/` |
| Home screen, PWA                                      | `src/app/apple-icon.png` (180, full bleed); `public/icons/icon-192.png`, `icon-512.png` and `icon-maskable-512.png`                                 |
| Hero and print over 200px                             | `mark-display.svg`, `mark-display-dark.svg` (finer string)                                                                                          |
| One colour (emboss, stamps, on the accent or a photo) | `lockup-mono-black.svg`, `lockup-mono-white.svg`, `mark-tile-mono-*.svg`: the bob is cut out, so the ground shows through                           |
| Link previews                                         | `src/app/opengraph-image.png` (1200×630)                                                                                                            |

### Rules

- Clear space on every side: half the tile's width. Minimum size: tile 16px; lockup 96px wide.
- Never recolour the tile outside indigo #4A3FD6 (`indigo-600`), the ink variant (`mark-tile-ink.svg`) and the one-colour files. Code it with the `brand`, `brand-facet` and `brand-fg` tokens, never `accent`: `accent` turns lavender in the dark theme and the bob disappears.
- Never set the wordmark in live text: it is outlined Atkinson Hyperlegible Next at weight 620 with −0.02em tracking.
- Never rotate the mark, add a shadow, or put the bob without its string: the string is what makes it a plumb line.
- The free mark (no tile) is for large sizes only; below 48px use the tile.

## Button

_Actions_ · reference: [`reference/Button.html`](reference/Button.html)

Buttons start an action; one primary button per view, for the thing the view is for.

### Use

- **Primary** (`accent` fill, `accent-fg` label): Ask, Check lease, Try again. At most one per view.
- **Secondary** (`surface` with a `border-strong` edge): the alternative next to a primary (Cancel, Copy reference).
- **Ghost** (no fill until hover): toolbars, answer actions, table row actions.
- **Danger** (`danger` fill, `on-status` label): destructive actions only (Delete conversation), always confirmed in a dialog.
- **Icon-only**: same variants at a square size; always carries `aria-label` and a tooltip.

Labels are a verb in sentence case: "Check lease", not "Submit" or "CHECK LEASE". Add a keyboard hint with `al-kbd` when a shortcut exists (Stop `Esc`).

### Sizes

| Size | Height            | Use                                                    |
| ---- | ----------------- | ------------------------------------------------------ |
| `sm` | `control-sm` 28px | Dense tables, toolbars, inside cards                   |
| `md` | `control-md` 36px | Default                                                |
| `lg` | `control-lg` 44px | Empty states and every button on phones (touch target) |

### States

Hover: `accent-hover` or `bg-hover`. Pressed: `accent-active` or `bg-active`. Focus: the 2px `focus` ring, offset 2px. Disabled: 45% opacity, `aria-disabled`, no hover. Loading: keep the label, swap the leading icon for `al-spinner`, set `aria-busy="true"`.

### The consumer provides

A label (or `aria-label` for icon-only), an optional leading icon (Lucide, 16px), and the action. Never a link styled as a button for navigation: use `al-link`.

## Badge

_Status_ · reference: [`reference/Badge.html`](reference/Badge.html)

Badges label a status or a code in one or two words; a status badge always pairs its colour with an icon and a word.

### Status badges

| Variant   | Word                              | Icon             | Meaning                                                  |
| --------- | --------------------------------- | ---------------- | -------------------------------------------------------- |
| `success` | Verified, Matches the law, Passed | `circle-check`   | The passage was found and supports the claim             |
| `warning` | Worth checking, Partial, Slow     | `triangle-alert` | Depends on facts the lease or the corpus does not settle |
| `danger`  | Conflicts with the law, Failed    | `octagon-alert`  | The clause or the run contradicts the statute            |
| `neutral` | Abstained, Skipped                | `circle-dashed`  | A decision not to answer: never an error                 |
| `info`    | New corpus, Beta                  | `info`           | Neutral news                                             |

The fills are `*-bg` with a `*-border` edge and the `*` colour for text and icon. `al-badge--solid` fills with the status colour and sets the label in `on-status`; keep it for the one badge that must shout (a blocking finding count).

### Codes and counts

- **Jurisdiction code** (`al-badge--code`): the ISO 3166 code in mono, `AE-DU`, `ES`, `CO`, `US-FL`. Never a flag: flags stand for nations and render differently on every system.
- **Count** (`al-count`): a number beside a label ("Sources 4"), tabular numerals.

### The consumer provides

The variant, the word, and the icon for status badges; the code for code badges. Write the word in sentence case.

## CitationMarker

_Citations_ · reference: [`reference/CitationMarker.html`](reference/CitationMarker.html)

A citation marker is the small number after a claim that points to the statute passage supporting it; hovering or focusing it previews the passage, activating it opens the source panel.

### Anatomy

- **Marker** (`al-cite`): the source number in mono on `accent-subtle`, `accent-text`. It follows the claim it supports, before the full stop of a clause it closes: "...within 15 days [1]."
- **Preview** (`al-popover`): jurisdiction code, statute and article in `ui-strong`, the verified state, the passage in `quote-sm` serif with the cited span in `al-mark`, and "Open in source panel".

### Behaviour

- Hover or focus shows the preview after 150 ms (`duration-fast`); Escape closes it.
- Click, Enter or Space opens the source panel at the passage and marks the marker active (`accent` fill, `accent-fg` number, `aria-expanded="true"`).
- Every marker in an answer is verified before it is shown: an unverified citation is dropped, never displayed in a weaker style.
- Markers are buttons, so they are in the tab order; the accessible name is "Source 1: Fla. Stat. § 83.49(3)(a)".

### Don't

Don't use domain pills or statute names inline: answers cite the same few statutes many times, and numbers keep the sentence readable.

## SourceCard

_Citations_ · reference: [`reference/SourceCard.html`](reference/SourceCard.html)

A source card lists one cited passage under an answer: its number, the statute and article, the jurisdiction, the version, and the first lines of the passage in the law's own words.

### Anatomy

1. **Number** (`al-source__n`): the same number as the inline marker.
2. **Title** (`ui-strong`): the citation in the jurisdiction's own style: `Fla. Stat. § 83.49(3)(a)`, `Ley 29/1994, art. 9.1`, `Ley 820 de 2003, art. 20`, `Law No. 26 of 2007, Art. 25(2)`.
3. **Meta** (`small`, `fg-muted`): jurisdiction code badge, the statute's version, the page in the source PDF.
4. **Passage** (`quote-sm` serif, three lines): quoted exactly as published, Spanish statutes in Spanish. The cited span is wrapped in `al-mark`.

### States

Hover: `bg-subtle` and `border-strong`. Selected (its passage is open in the source panel): a 2px `accent` edge. Cards sit in a grid of `minmax(260px, 1fr)` columns under the answer, numbered in the order the answer first cites them.

### The consumer provides

Number, citation, jurisdiction code, version, page, passage text and the cited character range, and the action that opens the source panel.

## StatuteQuote

_Citations_ · reference: [`reference/StatuteQuote.html`](reference/StatuteQuote.html)

A statute quote shows the law's own words: a passage set in the serif on a sunken ground, headed by its citation and verification state.

### The rule it carries

Serif means the statute speaks; sans means Plumbline speaks. Set only verbatim statute text in `quote` or `quote-sm` (Source Serif 4), never Plumbline's explanation, never a paraphrase. A reader can tell at a glance which words are the law's.

### Anatomy

- **Reference line** (`al-quote__ref`, `small`): jurisdiction code, citation in bold, version, and `al-verified`.
- **Passage**: `quote` (17/28) in answers and the source panel; `al-quote--sm` (15/24) in cards and tables. The cited span is `al-mark`; the span the reader opened is `al-mark is-active`.
- No left rule and no quotation-mark ornament: the ground and the serif already say "quotation".

### Language

Quote Spain and Colombia in Spanish, as published; Dubai and Florida in English. Never machine-translate a passage inside the quote; Plumbline's answer explains it in English.

## SourcePanel

_Citations_ · reference: [`reference/SourcePanel.html`](reference/SourcePanel.html)

The source panel shows a cited passage where it lives: the statute's own page with the cited box outlined, the passage text below it, and the actions to copy or open the original.

### Anatomy

1. **Header**: jurisdiction code, the citation as the title (`heading-3`), the statute's name and version in `small`, close button.
2. **Tabs**: Sources (with count) and Trace.
3. **Page**: the PDF page rendered as an image on `paper` (white in both themes), the cited box in `paper-highlight` with a 2px `paper-highlight-edge` outline. The page scrolls so the box sits in the upper third.
4. **Pager**: "Page 3 of 41", previous and next.
5. **Passage**: the extracted text in `quote` serif with the cited span in `al-mark is-active`, then `al-verified` and the character range.
6. **Actions**: Copy reference (secondary), Open original (ghost, external link).

### Layout

`panel-width` 440px on desktop, resizable from 360 to 640px, beside the conversation. Below 1024px it overlays the conversation (`z-panel`, `shadow-3`); below 768px it is a bottom sheet with a grab handle at 90% height. Opening it moves focus to the title; Escape closes it and returns focus to the marker that opened it.

## Answer

_Answers_ · reference: [`reference/Answer.html`](reference/Answer.html)

An answer is Plumbline's reply to one question: a one-line summary of what was checked, the explanation in plain English with a citation after every claim, the sources it cites, and the actions.

### Anatomy

1. **Question** (`al-question`): the reader's words on `bg-active`, right-aligned.
2. **Meta line** (`al-answer__meta`, `small`): "Answered in 4.2 s · 2 sources · Trace". While streaming it is the status steps (see StatusSteps); when done it collapses to this line.
3. **Body** (`body-lg`, sans): Plumbline's own words. Every sentence that states the law ends with a citation marker. Quote the law only inside a StatuteQuote, never inline in the serif.
4. **Sources** (`al-answer__sources`): a SourceCard per cited passage, in first-citation order.
5. **Actions** (`al-answer__actions`): copy, helpful, not helpful (see Feedback).
6. **Disclaimer** (`al-disclaimer`) under the composer, once per page: "Legal information, not legal advice."

### States

| State     | What changes                                                                                      |
| --------- | ------------------------------------------------------------------------------------------------- |
| Streaming | Status steps replace the meta line; text appears as it arrives; Stop `Esc` is visible             |
| Answered  | All citations verified; meta line shows time and source count                                     |
| Partial   | The supported part, then an `al-gap` block, "Not covered by the statutes I hold", with the reason |
| Abstained | See Abstention: no body, no sources                                                               |
| Error     | A danger Callout in place of the body, with Try again                                             |

### Voice

Plain English, second person, short sentences. Say what the law requires, then what it means for the reader. Never "you should sue" or "this is illegal": say what the statute says and that a lawyer can advise on the reader's case.

## PartialAnswer

_Answers_ · reference: [`reference/PartialAnswer.html`](reference/PartialAnswer.html)

A partial answer gives the part of a question the statutes support, with citations, and then names the part they don't, so the reader never mistakes silence for a "no".

### Anatomy

- The supported part is an ordinary answer body with citation markers.
- The gap (`al-gap`): a dashed `neutral-border` block on `neutral-bg`, titled "Not covered by the statutes I hold" in `neutral` with the `circle-dashed` icon, then one or two sentences: what is missing and why (the decree isn't in the corpus yet, the question needs facts the lease doesn't give).
- The meta line says "Partial answer" with a warning badge.

### Rules

- Never guess the missing part, and never soften the gap into the body text.
- If the gap is the whole question, it is an Abstention, not a partial answer.
- One gap block per answer; list several missing parts inside it.

## Abstention

_Answers_ · reference: [`reference/Abstention.html`](reference/Abstention.html)

An abstention is Plumbline deciding not to answer because no statute it holds supports an answer; it is a designed result, shown calmly in neutral colours, never as an error.

### Anatomy

1. **Title** (`heading-3` size, `fg`, `circle-dashed` icon): one sentence that says what happened in the reader's terms: "Texas isn't one of the jurisdictions I hold."
2. **What I checked** (`dl`): jurisdictions searched, corpus version, the closest passage found and why it doesn't apply.
3. **What you can do** (list): ask within scope, rephrase, or the kind of professional who can help. No links to outside legal services unless they are official.
4. The usual answer actions (copy, feedback) still apply.

### Reasons and titles

| Reason                              | Title                                            |
| ----------------------------------- | ------------------------------------------------ |
| Outside the four jurisdictions      | "<Place> isn't one of the jurisdictions I hold." |
| No passage supports an answer       | "I couldn't find a statute that answers this."   |
| Passages conflict                   | "The statutes I hold point both ways on this."   |
| Needs facts only a lawyer can weigh | "This depends on facts I can't check."           |

### Don't

Red, warning triangles, apologies, "As an AI". The abstention is part of Plumbline working correctly, and the public eval page scores it.

## StatusSteps

_Answers_ · reference: [`reference/StatusSteps.html`](reference/StatusSteps.html)

Status steps show what Plumbline is doing while an answer streams, one row per stage, so the wait reads as work being checked rather than a spinner.

### Source

Each row is one transient `data-status` part from the answer stream. The stages, in order: Reading your question, Searching <n> jurisdictions, Ranking passages, Checking citations, Writing the answer. Detail text carries the counts the stream sends ("40 passages", "3 of 4 verified").

### Row states

| State   | Icon                         | Text                                    |
| ------- | ---------------------------- | --------------------------------------- |
| Done    | `circle-check` in `success`  | `fg-muted`, time on the right in `code` |
| Active  | `al-spinner` in `accent`     | `fg`, medium weight                     |
| Pending | `circle` in `border-control` | `fg-subtle`                             |
| Failed  | `circle-x` in `danger`       | `danger`, with the reason as detail     |

### Behaviour

- The working bar (`al-working`) above the composer shows the active step's label, elapsed time, and Stop with `Esc`.
- When the answer finishes, the list collapses into the answer's meta line ("Answered in 4.2 s · 2 sources verified · Trace"); the full list stays one click away under Trace.
- The list is an `aria-live="polite"` region that announces the active step only, so screen readers are not flooded.
- Under `prefers-reduced-motion` the spinner stops turning and shows a static ring.

## Composer

_Inputs_ · reference: [`reference/Composer.html`](reference/Composer.html)

The composer is where the reader asks: a growing text area, the jurisdiction scope, an attach-lease button, and send; the legal-information disclaimer sits under it on every page that has one.

### Anatomy

1. **Text area** (`input`, 16/24, so phones don't zoom on focus): placeholder "Ask about a lease in Dubai, Spain, Colombia or Florida". Grows to eight lines, then scrolls.
2. **Scope chip** (`al-chip`): the jurisdiction the question is about, "All four" by default; opens a menu of the four with their codes.
3. **Attach** (ghost icon button, `paperclip`): opens the lease checker's upload with this conversation.
4. **Send** (primary icon button, `arrow-up`): disabled until there is text. While an answer streams it becomes Stop (`square`) with the `Esc` hint.
5. **Disclaimer** (`al-disclaimer`): the short form, "Legal information, not legal advice." The full disclaimer sits in the page footer.

### Keys

Enter sends, Shift+Enter adds a line, Escape stops a streaming answer, `/` focuses the composer from anywhere.

### States

Edge: `border-control`, so the box holds 3:1 like every input. Focus: `focus` border plus a 1px `focus` ring (the whole box is the control; the text area itself shows no outline). Disabled while the demo quota is spent, with the reason in the disclaimer slot.

## Field

_Inputs_ · reference: [`reference/Field.html`](reference/Field.html)

Fields collect short structured input: a text input or select with a visible label, optional help, and an error that says how to fix it.

### Anatomy

Label (`ui` medium, `fg`) above the control; help (`small`, `fg-muted`) below; error (`small` medium, `danger`, `circle-alert` icon) replaces the help. Controls are `control-md` high with a `border-control` edge, which holds 3:1 on every ground, so the control is visible without its label. Text in inputs is `ui` (14px); on phones (below 768px) inputs grow to `control-lg` with `input` text (16px), so the page doesn't zoom on focus.

### Controls

- **Input** (`al-input`): text, number, date.
- **Select** (`al-select`): a native select with a chevron icon; use for four to twelve options, a chip group below four.
- **Checkbox and radio** (`al-choice`): 16px boxes, accent when checked, the whole label clickable.
- **Switch** (`al-switch`): settings that apply at once (Show trace). Not for choices that need a submit.

### Errors

Write the fix, not the fault: "Upload a PDF or DOCX file", not "Invalid file type". Set `aria-invalid="true"` and point `aria-describedby` at the error.

## Callout

_Feedback_ · reference: [`reference/Callout.html`](reference/Callout.html)

A callout puts one short message inside the page, in the tone of what it reports: info, success, warning, danger or neutral, each with its icon and a title.

### Use

- **Info** (`accent-subtle`): facts about the service ("Statutes as of 1 Oct 2026").
- **Success**: a check that passed ("All 4 citations verified").
- **Warning**: something the reader should look at before relying on the result.
- **Danger**: something stopped or failed, with the way forward and a button.
- **Neutral**: context that is neither good nor bad.

Title in the tone colour, body in `fg`, an action (ghost or secondary `sm` button) at the end when there is one. Callouts never stack more than two; more than that is a list of findings.

### Don't

No coloured left border, no full-saturation fills, no dismiss on danger callouts.

## Feedback

_Feedback_ · reference: [`reference/Feedback.html`](reference/Feedback.html)

Feedback lets a reader mark an answer helpful or not, and say why when it wasn't.

### Anatomy

Ghost icon buttons under the answer: copy, helpful (`thumbs-up`), not helpful (`thumbs-down`). After "not helpful", an inline panel opens: "What went wrong?", reason chips (`al-chip`, multi-select), an optional note, Send. After sending, the panel collapses to "Thanks, that helps."

### Reasons

Wrong citation · Missed a statute · Outdated law · Hard to follow · Something else. Keep them in this order and keep them few: five reasons a reader can choose in a second.

## Dialog

_Overlays_ · reference: [`reference/Dialog.html`](reference/Dialog.html)

A dialog interrupts for a decision that cannot wait: confirming a destructive action, or the one-time notice before the first lease upload.

### Anatomy

Title (`heading-2`), one or two paragraphs (`body`; the second in `fg-muted`), actions right-aligned: the safe choice as secondary on the left, the main choice as primary (or danger) on the right. `radius-xl`, `shadow-3`, `surface-raised`, over the `overlay` scrim.

### Behaviour

Focus moves to the first action on open and returns to the trigger on close. Escape and the scrim close it unless the action is destructive. Tab cycles inside. On phones it becomes a bottom sheet.

### When not to use

Not for the legal-information disclaimer on every answer (that is a line under the composer), not for success messages (toast), not for errors that have a fix in place (callout).

## Toast

_Overlays_ · reference: [`reference/Toast.html`](reference/Toast.html)

A toast confirms something finished or keeps a long job visible after the reader moves on; it sits bottom-right (bottom-centre on phones) on `inverse`.

### Use

- Confirmation of an action the reader took: "Reference copied".
- A long job running in the background: "Checking lease · 8 of 14 clauses" with Cancel.
- A finished job with one action: "Lease checked: 4 findings · View".

One line, one action at most, set as an underlined `al-toast__action` in `fg-inverse`; its focus ring is `focus-inverse`, because `focus` falls under 3:1 on `inverse`. Confirmation toasts leave after 4 s (paused on hover and focus); job toasts stay until the job ends. Announce with `role="status"`.

### Tooltip

Tooltips (`al-tooltip`) share the inverse ground: the name of an icon-only button and its shortcut ("Stop generating `Esc`"). They appear on hover after 400 ms and on focus at once, and never hold anything the reader must act on.

## Dropzone

_Lease check_ · reference: [`reference/Dropzone.html`](reference/Dropzone.html)

The dropzone takes a lease for checking and then shows each file moving through its stages: uploaded, redacted, read, checked.

### Anatomy

1. **Zone** (`al-drop`): a dashed `border-control` edge on `bg-subtle`, the upload icon, "Drop a lease here or choose a file", accepted types and limit ("PDF or DOCX, up to 20 MB"), and the redaction promise in one line. On drag-over: `accent` edge on `accent-subtle`.
2. **File row** (`al-file`): file icon, name, size, a progress bar while uploading, then the stage line.
3. **Stages**: Uploaded, Redacting, Reading, Checking clauses. Done stages carry a check in `success`; the active one is `fg` medium with a spinner; pending ones are `fg-subtle`.

### Rules

- The whole zone is one button (keyboard: Enter or Space opens the picker).
- Scanned PDFs: say so in a warning callout and offer OCR, don't fail silently.
- Show the redaction notice dialog before the first upload of a session.

## FindingCard

_Lease check_ · reference: [`reference/FindingCard.html`](reference/FindingCard.html)

A finding card sets one lease clause beside the statute passage it was checked against, with the verdict and the reason in plain English.

### Anatomy

1. **Head**: severity badge, a one-line title that states the finding ("The yearly rent rise can exceed the legal cap"), jurisdiction code, and the clause number.
2. **Two columns**: "Your lease" (eyebrow, then the clause in sans, as written, in its language) and "The law" (eyebrow with the citation, then the passage in `quote-sm` serif with the cited span marked). They stack below 560px.
3. **Why** (`al-finding__why`, on `bg-subtle`): two or three sentences in Plumbline's voice: what the statute requires and what that means for this clause.

### Severity

| Group                  | Badge                       | When                                                |
| ---------------------- | --------------------------- | --------------------------------------------------- |
| Conflicts with the law | `danger`, `octagon-alert`   | The clause contradicts the passage                  |
| Worth checking         | `warning`, `triangle-alert` | It depends on facts or rules Plumbline doesn't hold |
| Notes                  | `info`                      | Useful context, no conflict                         |
| Matches the law        | `success`, `circle-check`   | The clause follows the passage                      |

Group findings in that order under headings with counts (`al-group-title` + `al-count`). Never a score or a grade for the whole lease.

## Table

_Data_ · reference: [`reference/Table.html`](reference/Table.html)

Tables hold records people compare: eval cases, runs, findings exports; dense, with tabular numerals and status as an icon and a word.

### Anatomy

- Header row on `bg-subtle`, `micro`-sized medium labels in `fg-muted`, sticky while the body scrolls.
- Body rows `ui` 14/20, 10px vertical padding (6px with `al-table--compact`), `border-subtle` dividers, `bg-hover` on hover.
- Numbers right-aligned with `.num` and tabular numerals; text left-aligned; the first column that names the row in `.lead` (semibold).
- Status cells are badges, never coloured text alone.
- IDs and hashes in `code` mono, truncated in the middle ("9f7d…6dd7") with the full value in a tooltip.

### Behaviour

Sortable headers carry `aria-sort`. Wide tables scroll horizontally inside their own box; the page never scrolls sideways. Selecting a row opens its detail in the side panel, not a new page.

## Metric

_Data_ · reference: [`reference/Metric.html`](reference/Metric.html)

A metric shows one headline number from an eval run with its uncertainty and its change against main, so a reader can tell a real improvement from noise.

### Anatomy

Label (`small` medium, `fg-muted`), value (`kpi` 32/36, tabular), confidence interval (`code` 12px, `fg-subtle`: "95% CI 0.91–0.96"), delta against main (`al-delta`).

### Delta

`al-delta--better` (success, `arrow-up-right`), `al-delta--worse` (danger, `arrow-down-right`), `al-delta--same` (muted, `minus`). Better and worse follow the metric's direction: lower latency is better. A delta whose interval crosses zero is "same", whatever its sign, and says "no change" rather than a number.

### Layout

`al-metrics` grid, 170px minimum columns: five fit on desktop, two on phones. Headline metrics go first in this order: citation precision, faithfulness, abstention accuracy, p95 latency, cost per question.

## TraceWaterfall

_Data_ · reference: [`reference/TraceWaterfall.html`](reference/TraceWaterfall.html)

The trace waterfall shows how one answer was produced: each span of the pipeline as a row with its duration bar on a shared time axis, nested under its parent.

### Source

The `data-trace` part of the answer stream (an `AnswerTrace`): spans for reading, retrieval (keyword, vector, fusion), reranking, generation and citation verification, each with start, duration, status, and the cache mode (record, replay, live).

### Anatomy

- Axis row: millisecond ticks in `code` 11px.
- Span rows: name with indent per depth (14px), the bar positioned by `--start` and `--width` as percentages of the answer's total time, the duration right-aligned in mono.
- Bar colours by kind: retrieval `chart-3`, model calls `chart-1`, verification `chart-2`, everything else `chart-5`; a replayed span is an outline only. A failed span is hatched in `danger` with a `danger` outline, so it reads without colour.
- Selecting a row opens its detail (inputs, outputs, model, tokens, cost, cache key) in the side panel, IDs in mono.

## Chart

_Data_ · reference: [`reference/Chart.html`](reference/Chart.html)

Charts on the evals page compare a metric across jurisdictions or runs; they are plain SVG dots, bars and lines in the chart tokens, with every series labelled directly.

### Rules

- Series colours in order: `chart-1` to `chart-4` for the four jurisdictions (AE-DU, ES, CO, US-FL, always that order), `chart-5` for the baseline or main.
- Label series at the bar or line end; a legend only when direct labels don't fit.
- Scores near 1 are dots with whiskers (95% intervals in `fg`), never bars on a cut axis; bars always start at zero.
- The main baseline is a dashed `fg-muted` rule.
- Gridlines `chart-grid` (decorative), axes and ticks `chart-axis` (3:1).
- Values in `micro` tabular numerals; never rotate tick labels, shorten them.
- Status-coloured charts (pass, fail, abstain) use the status tokens and hatch the failure series, never the chart series colours.
- Every chart has a text alternative: a caption that states the takeaway and a table behind a "Show data" toggle.

## Tabs

_Navigation_ · reference: [`reference/Tabs.html`](reference/Tabs.html)

Tabs switch between views of the same thing (Sources and Trace of one answer; Findings and Lease text of one check), with an `accent` underline on the current tab.

### Anatomy

`ui` medium labels in `fg-muted`, the selected one in `fg` with a 2px `accent` underline sitting on the `border` rule; an optional `al-count`. Chips (`al-chip` with `aria-pressed`) are the filter version: they narrow a list rather than switch the view.

### Behaviour

Roving focus with the arrow keys, `role="tablist"`, `aria-selected`, Home and End jump to the ends. Never more than five tabs; never tabs inside tabs.

## Sidebar

_Navigation_ · reference: [`reference/Sidebar.html`](reference/Sidebar.html)

The sidebar holds the product's few destinations and the reader's recent questions, on `bg-subtle` beside the canvas.

### Anatomy

1. **Brand**: the horizontal lockup at 22px high, linking home. The tile is drawn with the `brand` tokens, so it stays indigo in both themes; the wordmark takes `fg`.
2. **New question** (secondary button, full width, `/` shortcut).
3. **Destinations** (`al-nav`): Ask, Check a lease, Evals, About. Icon 16px, label, optional count; current page `bg-active` with `aria-current="page"`.
4. **Recent** (eyebrow, then `al-history` rows, one line each, truncated).
5. **Footer**: the demo usage meter and the theme switch.

### Layout

`sidebar-width` 248px; collapses to the 56px `sidebar-rail` (icons only, names in tooltips) from 1024px down, and to a drawer behind the menu button below 768px.

## AppShell

_Layout_ · reference: [`reference/AppShell.html`](reference/AppShell.html)

The app shell is three panes: the sidebar, the conversation in a reading column, and the source panel that opens beside it when a citation is followed.

### Grid

| Pane         | Width                                      | Notes                              |
| ------------ | ------------------------------------------ | ---------------------------------- |
| Sidebar      | `sidebar-width` 248px (rail 56px)          | `bg-subtle`                        |
| Conversation | fluid, content `content-max` 720px centred | `bg`, top bar `topbar-height` 52px |
| Source panel | `panel-width` 440px, 360 to 640px          | `surface`, opens on demand         |

### Breakpoints

- 1280px and up: all three panes.
- 1024 to 1279px: sidebar becomes the rail when the source panel is open.
- 768 to 1023px: rail; the source panel overlays the conversation.
- Below 768px: one column; sidebar is a drawer; sources are a bottom sheet; every target is at least 44px.

Spacing: 32px between turns, 24px panel padding, 16px gutters on phones. The composer sits at the bottom of the conversation column, `shadow-1`, above the disclaimer.

## EmptyState

_States_ · reference: [`reference/EmptyState.html`](reference/EmptyState.html)

The empty state is the first screen of a new question: what Plumbline covers, in one sentence, and four example questions, one per jurisdiction.

### Anatomy

Title (`heading-1`), one sentence of scope (`body`, `fg-muted`), example cards (`al-example`): jurisdiction code over the question. Choosing one fills the composer and sends it. Below 640px the examples stack in one column.

### Other empty states

- No results in a list: what was searched and one action ("No cases match 'deposit' in Spain. Clear filters").
- No findings yet: the dropzone itself is the empty state.
- Write the sentence in the reader's terms, never "No data".

## Skeleton

_States_ · reference: [`reference/Skeleton.html`](reference/Skeleton.html)

A skeleton holds the shape of content that is about to arrive, so the layout doesn't jump when it does; it always comes with a label saying what is loading.

### Use

- An answer before the first token: the meta line, three body lines of falling width, two source-card blocks.
- A table while a run loads: the header row real, five body rows of bars.
- Never for less than 300 ms (show nothing), never for more than 10 s (switch to status steps or a toast with progress).

Bars are `bg-active` with `radius-sm`; `al-skel--shimmer` adds a slow sweep that stops under `prefers-reduced-motion`. The region carries `aria-busy="true"` and the label is the accessible name.

## ErrorState

_States_ · reference: [`reference/ErrorState.html`](reference/ErrorState.html)

An error state replaces a view that failed to load: what happened in plain words, the one thing to do next, and an error ID the reader can quote.

### Anatomy

Icon in a `danger-bg` disc, title (`heading-2`) that names what failed in the reader's terms, body (`body`, `fg-muted`) whose first sentence is bold and carries the fix, primary Try again, secondary Copy error ID, and the ID with time in `code`, `fg-subtle`.

### Copy

| Failure          | Title                                 | First sentence                                                                      |
| ---------------- | ------------------------------------- | ----------------------------------------------------------------------------------- |
| Retrieval down   | Plumbline couldn't reach the statutes | **The search service didn't answer.** Your question is kept; try again in a moment. |
| Demo limit       | Today's demo questions are used up    | **The demo allows 20 questions a day.** It resets at 00:00 UTC.                     |
| Lease unreadable | This lease couldn't be read           | **The file has no selectable text.** Upload a text PDF or a DOCX.                   |

Inline failures inside an answer use a danger Callout instead; this full state is for whole views.

## UsageMeter

_States_ · reference: [`reference/UsageMeter.html`](reference/UsageMeter.html)

The usage meter shows how much of the public demo's daily allowance is left, so a limit never arrives as a surprise.

### Anatomy

Label and count on one row ("Demo questions", "12 of 20", tabular), a 6px track on `bg-active` with an `accent` fill, and the reset time in `small`. At 80% used the fill turns `warning` and the line says how many are left; at 100% the composer is disabled and says when it resets.

### Placement

Sidebar footer on desktop, under the composer on phones. The meter is a `meter` element (or `role="meter"`) with the value and maximum.
