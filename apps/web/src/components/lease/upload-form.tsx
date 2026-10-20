"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { CircleCheckIcon, FileTextIcon, XIcon } from "@/components/icons";
import { buttonClass } from "@/components/ui/button";
import { controlClass, Field, FieldMessage, Select } from "@/components/ui/field";
import { JURISDICTIONS } from "@/lib/jurisdictions";
import { formatBytes, uploadSchema, type UploadValues } from "@/lib/lease-upload";

import { Dropzone } from "./dropzone";

type FormInput = z.input<typeof uploadSchema>;

/** The lease page's form: a lease, where the property is, and when the lease was signed (the
 * last two optional). Its type and size are checked here before anything is sent; a refused
 * file says how to fix it and keeps the focus on the zone. */
export function UploadForm({
  onSubmit,
  disabled = false,
  initial,
  focusJurisdiction = false,
  focusOnMount = false,
}: {
  onSubmit: (values: UploadValues) => void;
  disabled?: boolean;
  /** What the reader had chosen before a failure sent them back here. */
  initial?: Partial<UploadValues>;
  /** Puts the cursor on the jurisdiction, when that is what the reader has to fix. */
  focusJurisdiction?: boolean;
  /** Puts the cursor on the form's first control when it appears again after a check, so a
   * keyboard reader is not left at the top of the document. */
  focusOnMount?: boolean;
}) {
  const fileMessage = useId();
  const {
    register,
    handleSubmit,
    formState,
    setValue,
    resetField,
    setError,
    clearErrors,
    setFocus,
  } = useForm<FormInput, unknown, UploadValues>({
    resolver: zodResolver(uploadSchema),
    defaultValues: {
      file: initial?.file,
      jurisdiction: initial?.jurisdiction ?? "",
      signedOn: initial?.signedOn ?? "",
    },
  });
  // What the form shows. The value for the submit lives in the form too, set beside it.
  const [file, setFile] = useState<File | undefined>(initial?.file);
  const zone = useRef<HTMLButtonElement>(null);
  const submitButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (focusJurisdiction) setFocus("jurisdiction");
    else if (focusOnMount) (zone.current ?? submitButton.current)?.focus();
  }, [focusJurisdiction, focusOnMount, setFocus]);

  // The type and size are checked on the spot, so a refused file never shows as chosen, not
  // even for a frame. It is the same schema the submit runs, so the messages agree.
  function choose(chosen: File) {
    const result = uploadSchema.shape.file.safeParse(chosen);
    if (result.success) {
      clearErrors("file");
      setFile(chosen);
      setValue("file", chosen, { shouldDirty: true });
    } else {
      setFile(undefined);
      resetField("file");
      setError("file", { type: "validate", message: result.error.issues[0]?.message });
    }
  }
  const fileError = formState.errors.file?.message;

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        {file && !fileError ? (
          <ChosenFile
            file={file}
            onRemove={() => {
              setFile(undefined);
              resetField("file");
            }}
          />
        ) : (
          <Dropzone
            buttonRef={zone}
            disabled={disabled}
            invalid={Boolean(fileError)}
            describedBy={fileError ? fileMessage : undefined}
            onFile={choose}
          />
        )}
        <FieldMessage id={fileMessage} error={fileError} />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          label="Where is the property?"
          help="Optional. Otherwise I read it from the lease."
          error={formState.errors.jurisdiction?.message}
        >
          {(props) => (
            <Select {...props} disabled={disabled} {...register("jurisdiction")}>
              <option value="">Detect from the lease</option>
              {JURISDICTIONS.map(({ id, name, code }) => (
                <option key={id} value={id}>
                  {name} ({code})
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          label="Date signed"
          help="Optional. Some rules depend on when the lease was signed."
          error={formState.errors.signedOn?.message}
        >
          {(props) => (
            <input
              type="date"
              disabled={disabled}
              className={controlClass}
              {...props}
              {...register("signedOn")}
            />
          )}
        </Field>
      </div>
      <button
        ref={submitButton}
        type="submit"
        disabled={disabled}
        className={buttonClass({ variant: "primary", size: "lg", className: "self-start" })}
      >
        <CircleCheckIcon />
        Check lease
      </button>
    </form>
  );
}

/** The chosen file before it is sent: its name and size, and a way to choose another. */
function ChosenFile({ file, onRemove }: { file: File; onRemove: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3.5 py-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-surface-sunken text-fg-muted">
        <FileTextIcon />
      </span>
      <span className="min-w-0 flex-1 truncate text-ui-strong">{file.name}</span>
      <span className="text-small tabular-nums text-fg-muted">{formatBytes(file.size)}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${file.name}`}
        className={buttonClass({ variant: "ghost", size: "sm", icon: true })}
      >
        <XIcon />
      </button>
    </div>
  );
}
