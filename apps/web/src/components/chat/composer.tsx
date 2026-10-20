"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { memo, useEffect, useId, useRef, type KeyboardEvent } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";

import { ArrowUpIcon, CircleAlertIcon, SquareIcon } from "@/components/icons";
import { buttonClass } from "@/components/ui/button";
import { askSchema, EMPTY_ASK, type AskValues } from "@/lib/ask-form";

import { JurisdictionFilter } from "./jurisdiction-filter";

function isEditable(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

type ComposerProps = {
  busy: boolean;
  onAsk: (values: AskValues) => void;
  onStop: () => void;
  /** Set when no question can be sent (the demo quota is spent): shown in the disclaimer's
   * place, and every control is disabled. */
  disabledReason?: string;
};

/** Composer spec: the question, its jurisdictions and as-of date, and send. Enter sends,
 * Shift+Enter adds a line, Escape stops a streaming answer, "/" focuses it from anywhere. The
 * filters stay set from one question to the next. Memoized: the chat re-renders on every
 * streamed update, and the form need not (docs/notes/streamed-answer-profile.md). The
 * callbacks are compared out because the chat rebuilds them each render with the same
 * behaviour: they reach only refs and the one useChat instance. */
export const Composer = memo(
  ComposerForm,
  (before, after) => before.busy === after.busy && before.disabledReason === after.disabledReason,
);

function ComposerForm({ busy, onAsk, onStop, disabledReason }: ComposerProps) {
  const ids = { question: useId(), asOf: useId(), error: useId() };
  const { register, handleSubmit, control, reset, formState } = useForm<AskValues>({
    resolver: zodResolver(askSchema),
    defaultValues: EMPTY_ASK,
  });
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const { ref: registerQuestion, ...question } = register("question");
  const error = formState.errors.question?.message ?? formState.errors.asOf?.message;
  const empty = useWatch({ control, name: "question" }).trim() === "";

  const submit = handleSubmit((values) => {
    onAsk(values);
    reset({ ...values, question: "" });
  });

  useEffect(() => {
    function focusComposer(event: globalThis.KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || isEditable(event.target)) return;
      event.preventDefault();
      textarea.current?.focus();
    }
    document.addEventListener("keydown", focusComposer);
    return () => document.removeEventListener("keydown", focusComposer);
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!busy) void submit();
    } else if (event.key === "Escape" && busy) {
      event.preventDefault();
      onStop();
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <fieldset disabled={disabledReason !== undefined} className="disabled:opacity-60">
        <div className="flex flex-col gap-2 rounded-lg border border-border-control bg-surface py-2.5 pl-4 pr-3 shadow-1 focus-within:border-focus focus-within:ring-1 focus-within:ring-focus">
          <label htmlFor={ids.question} className="sr-only">
            Your question
          </label>
          <textarea
            id={ids.question}
            rows={2}
            placeholder="Ask about a lease in Dubai, Spain, Colombia or Florida"
            aria-invalid={formState.errors.question ? true : undefined}
            aria-describedby={error ? ids.error : undefined}
            onKeyDown={onKeyDown}
            {...question}
            ref={(element) => {
              registerQuestion(element);
              textarea.current = element;
            }}
            className="field-sizing-content min-h-12 max-h-[calc(8*var(--pl-text-input--line-height))] resize-none bg-transparent pt-0.5 text-input text-fg placeholder:text-fg-subtle focus-visible:outline-none"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Controller
              control={control}
              name="jurisdictions"
              render={({ field }) => (
                <JurisdictionFilter value={field.value} onChange={field.onChange} />
              )}
            />
            <label
              htmlFor={ids.asOf}
              className="inline-flex items-center gap-1.5 text-small text-fg-muted"
            >
              Law as of
              <input
                id={ids.asOf}
                type="date"
                aria-invalid={formState.errors.asOf ? true : undefined}
                aria-describedby={error ? ids.error : undefined}
                {...register("asOf")}
                className="h-8 rounded-md border border-border-control bg-surface px-2 text-ui text-fg max-md:h-(--pl-control-lg) max-md:text-input"
              />
            </label>
            {busy ? (
              <button
                type="button"
                onClick={onStop}
                className={buttonClass({ size: "sm", className: "ml-auto" })}
              >
                <SquareIcon />
                Stop
                <kbd className="rounded-xs border border-border-strong px-1 font-mono text-code-sm text-fg-muted">
                  Esc
                </kbd>
              </button>
            ) : (
              <button
                type="submit"
                aria-label="Send question"
                disabled={empty}
                className={buttonClass({ variant: "primary", icon: true, className: "ml-auto" })}
              >
                <ArrowUpIcon />
              </button>
            )}
          </div>
        </div>
      </fieldset>
      {disabledReason ? (
        <p role="status" className="mt-2 text-center text-small text-fg-muted">
          {disabledReason}
        </p>
      ) : error ? (
        <p
          id={ids.error}
          role="alert"
          className="mt-2 flex items-center gap-1.5 text-small font-medium text-danger"
        >
          <CircleAlertIcon className="shrink-0" />
          {error}
        </p>
      ) : (
        <p className="mt-2 text-center text-small text-fg-subtle">
          Legal information, not legal advice.
        </p>
      )}
    </form>
  );
}
