"use client";

import { useId, useRef, useState, type DragEvent, type Ref } from "react";

import { UploadIcon } from "@/components/icons";
import { LEASE_ACCEPT, MAX_LEASE_MB } from "@/lib/lease-file";

/** Dropzone spec: the empty state of the lease page and the way to give it a lease. The whole
 * zone is one button, so Enter or Space opens the picker; a file dropped on it, or chosen, is
 * handed to `onFile`, and checking its type and size is the form's job. */
export function Dropzone({
  onFile,
  invalid = false,
  describedBy,
  disabled = false,
  buttonRef,
}: {
  onFile: (file: File) => void;
  invalid?: boolean;
  describedBy?: string;
  disabled?: boolean;
  /** The zone's button, for a form that moves the focus to it. */
  buttonRef?: Ref<HTMLButtonElement>;
}) {
  const input = useRef<HTMLInputElement | null>(null);
  const helpId = useId();
  const [over, setOver] = useState(false);

  function drop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file && !disabled) onFile(file);
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        data-invalid={invalid || undefined}
        aria-describedby={[helpId, describedBy].filter(Boolean).join(" ")}
        onClick={() => input.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        data-over={over || undefined}
        className="flex w-full flex-col items-center gap-2 rounded-lg border-[1.5px] border-dashed border-border-control bg-bg-subtle px-6 py-7 text-center hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-45 data-invalid:border-danger data-over:border-accent data-over:bg-accent-subtle"
      >
        <UploadIcon size={20} className="text-fg-muted" />
        <span className="text-body font-semibold">Drop a lease here or choose a file</span>
        <span id={helpId} className="text-small text-fg-muted">
          PDF or DOCX, up to {MAX_LEASE_MB} MB. Names, IDs and addresses are removed before any
          model reads it.
        </span>
      </button>
      {/* The picker itself stays out of the tab order and the accessibility tree: the button
          above is the control. */}
      <input
        ref={input}
        type="file"
        accept={LEASE_ACCEPT}
        tabIndex={-1}
        aria-hidden="true"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          // Choosing the same file again must still count as a change.
          event.target.value = "";
        }}
      />
    </>
  );
}
