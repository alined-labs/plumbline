import { useState } from "react";

/** Copies text to the clipboard and says so for two seconds. A refused clipboard leaves the
 * text on the page to select by hand, so the failure is not an error. */
export function useCopy(): [copied: boolean, copy: (text: string) => Promise<void>] {
  const [copied, setCopied] = useState(false);
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }
  return [copied, copy];
}
