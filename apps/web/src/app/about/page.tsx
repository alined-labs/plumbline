import type { Metadata } from "next";
import type { ReactNode } from "react";

import { DISCLAIMER, PRODUCT_LINE } from "@/lib/copy";

export const metadata: Metadata = {
  title: "About · Plumbline",
  description:
    "What Plumbline is, what it cannot do, how it is built and how it is made accessible.",
};

const REPO = "https://github.com/alined-labs/plumbline";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-heading-2">{title}</h2>
      {children}
    </section>
  );
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="text-accent underline underline-offset-2 hover:text-accent-hover">
      {children}
    </a>
  );
}

const KEYS: [string, string][] = [
  ["/", "Move to the question box from anywhere on the page"],
  ["Enter", "Send the question"],
  ["Shift + Enter", "Start a new line in the question"],
  ["Escape", "Stop an answer while it is written, or close a menu or popup"],
];

/** The limitations, the disclaimer, the accessibility statement and how Plumbline is built,
 * in that order: what a reader needs before relying on an answer comes first. */
export default function AboutPage() {
  return (
    <article className="flex flex-col gap-10 text-body">
      <header className="flex flex-col gap-3">
        <h1 className="text-heading-1">About Plumbline</h1>
        <p className="text-body-lg">{PRODUCT_LINE}</p>
        <p className="text-fg-muted">
          Plumbline gives legal information, not legal advice. It answers in English, quotes each
          statute in its own language, and declines when the law it holds does not answer the
          question.
        </p>
      </header>

      <Section title="Before you rely on an answer">
        <p className="rounded-lg border border-border bg-bg-subtle px-4 py-3">{DISCLAIMER}</p>
        <ul className="flex list-disc flex-col gap-2 pl-5">
          <li>
            Plumbline holds the tenancy law of Dubai, Spain, Colombia and Florida only. Each law is
            pinned to one edition, listed with its date at the foot of every page; a later amendment
            is not in it until the corpus is updated.
          </li>
          <li>
            The Arabic text of Dubai&apos;s laws is the authoritative one. Plumbline reads the
            official English translations and does not read Arabic.
          </li>
          <li>
            Decrees, ordinances and regulations outside the indexed statutes are not covered. When a
            question depends on them, the answer says which part it cannot cover.
          </li>
          <li>
            A language model writes each answer. Every quotation is checked against the statute text
            it came from, and a quotation that cannot be found is removed, but the explanation
            around it can still be wrong: read the cited article.
          </li>
          <li>
            Plumbline cannot weigh the facts of your case. For that, a tenant-rights organisation or
            a lawyer licensed where the property is can help.
          </li>
        </ul>
      </Section>

      <Section title="Accessibility">
        <p>
          The target is WCAG 2.2 level AA, in the light and the dark theme. Plumbline uses native
          HTML controls where they exist and Base UI&apos;s accessible headless primitives for the
          rest: the phone menu and the source panel are Base UI Dialogs that keep focus inside them
          and return it to what opened them, the panel&apos;s Sources and Trace are Base UI Tabs,
          the jurisdiction filter is a Base UI Combobox, the theme switch is a Base UI Switch, and
          the names of the compact sidebar&apos;s icons are Base UI Tooltips. The panel&apos;s edge
          is a keyboard-operable splitter, so its width can be set without a mouse.
        </p>
        <p>
          Everything works from the keyboard, with a visible focus ring. While an answer is written,
          one polite live region names the step in progress, and the finished answer is announced
          once rather than word by word. Each colour pair is checked for contrast in both themes,
          colour is never the only cue, and motion stops when your system asks for less of it.
        </p>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2">
          {KEYS.map(([key, action]) => (
            <div key={key} className="contents">
              <dt>
                <kbd className="rounded-xs border border-border-strong bg-surface px-1.5 font-mono text-code-sm text-fg-muted">
                  {key}
                </kbd>
              </dt>
              <dd>{action}</dd>
            </div>
          ))}
        </dl>
        <p>
          Automated checks run on every change: axe on every page, on a desktop and a phone, and
          Lighthouse. If something stands in your way, please{" "}
          <ExternalLink href={`${REPO}/issues`}>open an issue</ExternalLink> and say what you were
          trying to do.
        </p>
      </Section>

      <Section title="How it is built">
        <p>
          Plumbline is built in public, and the{" "}
          <ExternalLink href={`${REPO}#readme`}>README</ExternalLink> says which parts work today.
          This is how the whole is designed to work.
        </p>
        <p>
          The statutes are fetched from their official publishers, pinned by hash and split by
          article. A question is matched against them two ways at once, by meaning and by exact
          words such as article numbers, inside Postgres; the best passages are re-ranked, and a
          language model writes the answer from them alone, citing each claim. A verifier then
          checks every quotation against the passage it cites, and Plumbline declines when no
          passage supports an answer.
        </p>
        <p>
          It was built evaluation first: a golden set of questions over the statutes exists before
          the system does, every change passes an evaluation gate, and every model output is
          recorded so the published numbers rebuild at no cost. The details are in the{" "}
          <ExternalLink href={`${REPO}/blob/main/docs/architecture.md`}>
            architecture notes
          </ExternalLink>
          , the interface in the{" "}
          <ExternalLink href={`${REPO}/blob/main/DESIGN.md`}>design system</ExternalLink>, the
          sources and their licences in{" "}
          <ExternalLink href={`${REPO}/blob/main/DATA_LICENSES.md`}>DATA_LICENSES.md</ExternalLink>,
          and how coding agents were used and checked in{" "}
          <ExternalLink href={`${REPO}/blob/main/AI_USAGE.md`}>AI_USAGE.md</ExternalLink>.
        </p>
      </Section>
    </article>
  );
}
