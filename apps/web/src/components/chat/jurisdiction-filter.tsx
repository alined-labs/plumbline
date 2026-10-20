"use client";

import { Combobox } from "@base-ui/react/combobox";
import type { Jurisdiction } from "@plumbline/ts-client";

import { CheckIcon, ChevronDownIcon } from "@/components/icons";
import { JURISDICTION_IDS, jurisdictionInfo } from "@/lib/jurisdictions";

/** What the scope chip says: "All four" until the reader narrows it. */
export function scopeLabel(selected: readonly Jurisdiction[]): string {
  if (selected.length === 0 || selected.length === JURISDICTION_IDS.length) return "All four";
  return JURISDICTION_IDS.filter((id) => selected.includes(id))
    .map((id) => jurisdictionInfo(id).name)
    .join(", ");
}

function matches(id: Jurisdiction, query: string): boolean {
  const { name, code } = jurisdictionInfo(id);
  const q = query.trim().toLowerCase();
  return name.toLowerCase().includes(q) || code.toLowerCase().includes(q);
}

/** Composer spec, scope chip: the jurisdictions a question is about, as a Base UI combobox
 * whose filter input sits in the popup. None selected means the API detects them. */
export function JurisdictionFilter({
  value,
  onChange,
  disabled = false,
}: {
  value: Jurisdiction[];
  onChange: (value: Jurisdiction[]) => void;
  disabled?: boolean;
}) {
  const only = value.length === 1 ? value[0] : undefined;
  return (
    <Combobox.Root
      items={JURISDICTION_IDS}
      multiple
      value={value}
      onValueChange={(next) => onChange(JURISDICTION_IDS.filter((id) => next.includes(id)))}
      itemToStringLabel={(id: Jurisdiction) => jurisdictionInfo(id).name}
      filter={matches}
      disabled={disabled}
    >
      <Combobox.Label className="sr-only">Jurisdictions</Combobox.Label>
      <Combobox.Trigger className="inline-flex h-8 items-center gap-1.5 rounded-full border border-border-strong bg-surface px-3 text-ui text-fg hover:bg-bg-hover disabled:opacity-45 max-md:h-(--pl-control-lg)">
        {scopeLabel(value)}
        {only && (
          <span className="font-mono text-code-sm font-medium text-fg-muted">
            {jurisdictionInfo(only).code}
          </span>
        )}
        <ChevronDownIcon />
      </Combobox.Trigger>
      <Combobox.Portal>
        <Combobox.Positioner align="start" sideOffset={6} className="z-(--pl-z-overlay)">
          <Combobox.Popup
            aria-label="Choose jurisdictions"
            className="flex w-64 flex-col gap-1 rounded-lg border border-border bg-surface-raised p-1.5 shadow-2"
          >
            <Combobox.Input
              aria-label="Filter jurisdictions"
              placeholder="Filter by name or code"
              className="h-(--pl-control-md) w-full rounded-md border border-border-control bg-surface px-2.5 text-ui text-fg placeholder:text-fg-subtle max-md:h-(--pl-control-lg) max-md:text-input"
            />
            <Combobox.Empty className="px-2.5 py-2 text-small text-fg-muted empty:hidden">
              No jurisdiction matches. Plumbline holds Dubai, Spain, Colombia and Florida.
            </Combobox.Empty>
            <Combobox.List>
              {(id: Jurisdiction) => (
                <Combobox.Item
                  key={id}
                  value={id}
                  className="grid cursor-default grid-cols-[--spacing(4)_1fr_auto] items-center gap-2 rounded-md px-2 py-1.5 text-ui text-fg data-highlighted:bg-bg-hover max-md:min-h-11"
                >
                  <Combobox.ItemIndicator className="text-accent">
                    <CheckIcon />
                  </Combobox.ItemIndicator>
                  <span className="col-start-2">{jurisdictionInfo(id).name}</span>
                  <span className="font-mono text-code-sm text-fg-muted">
                    {jurisdictionInfo(id).code}
                  </span>
                </Combobox.Item>
              )}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  );
}
