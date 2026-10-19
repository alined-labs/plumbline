import { DISCLAIMER } from "@/lib/copy";
import { formatDate } from "@/lib/dates";
import { lawsByJurisdiction } from "@/lib/laws";

/** The full disclaimer and each law's last-updated date, built into every page. */
export function SiteFooter() {
  const groups = lawsByJurisdiction();
  return (
    <footer className="border-t border-border px-4 py-6 md:px-8">
      <div className="mx-auto flex max-w-content flex-col gap-4 text-small text-fg-muted">
        <p>{DISCLAIMER}</p>
        <section aria-labelledby="law-dates">
          <h2 id="law-dates" className="font-mono text-eyebrow uppercase text-fg-muted">
            Statutes indexed
          </h2>
          <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
            {groups.map(({ id, code, name, laws }) => (
              <div key={id} className="contents">
                <dt className="flex items-center gap-2 text-fg">
                  {name} <span className="font-mono text-code-sm text-fg-muted">{code}</span>
                </dt>
                <dd className="max-sm:mb-2">
                  {laws.length === 0
                    ? "Not indexed yet"
                    : laws.map((law, i) => (
                        <span key={law.id}>
                          {i > 0 && "; "}
                          {law.title}, updated{" "}
                          <time dateTime={law.updatedOn}>{formatDate(law.updatedOn)}</time>
                        </span>
                      ))}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </footer>
  );
}
