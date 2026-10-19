import Link from "next/link";

/** A destination whose content has not shipped yet: its title, what it will hold, and the
 * one thing that works today. */
export function PagePending({ title, children }: { title: string; children: string }) {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="text-heading-1">{title}</h1>
      <p className="text-body text-fg-muted">{children}</p>
      <p className="text-body">
        <Link href="/" className="text-accent underline underline-offset-2 hover:text-accent-hover">
          Ask a question instead
        </Link>
      </p>
    </div>
  );
}
