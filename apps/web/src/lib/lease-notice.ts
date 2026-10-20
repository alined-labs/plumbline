// The redaction notice (Dialog spec) is shown before the first lease upload of a session, and
// not again until the tab is closed. Storage can be refused (private browsing, a policy): then
// the notice is shown every time, which errs on the side of telling the reader.
const KEY = "pl-lease-notice";

export function noticeSeen(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function markNoticeSeen(): void {
  try {
    window.sessionStorage.setItem(KEY, "1");
  } catch {
    // Shown again next time.
  }
}
