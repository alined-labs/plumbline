"use client";

import { useEffect, useState } from "react";

import { ErrorState } from "@/components/states/error-state";

/** Eight hex digits a reader can quote. getRandomValues, unlike randomUUID, also works on a
 * plain-HTTP origin such as a LAN address in development. */
function localErrorId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(4)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

/** Any page that throws while rendering. The shell stays, so the reader can still navigate. */
export default function PageError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // A digest only exists for errors from server rendering; the export renders in the
  // browser, so most errors get a local ID instead.
  const [errorId] = useState(() => error.digest ?? localErrorId());
  const [at] = useState(() => new Date());

  useEffect(() => {
    console.error(`err ${errorId}`, error);
  }, [error, errorId]);

  return (
    <ErrorState
      title="This page couldn't load"
      lead="Something broke while drawing this page."
      body="Try again; if it keeps failing, quote the error ID below."
      errorId={errorId}
      at={at}
      onRetry={reset}
    />
  );
}
