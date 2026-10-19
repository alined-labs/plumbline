// Dates as the content rules write them ("19 Oct 2026"), always in UTC so the static build
// and every visitor's browser print the same day.
const day = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

const minute = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});

/** "2026-10-19" or a Date → "19 Oct 2026". A bare ISO date is read as a UTC calendar day. */
export function formatDate(value: string | Date): string {
  return day.format(typeof value === "string" ? new Date(`${value}T00:00:00Z`) : value);
}

/** A moment → "19 Oct 2026, 14:32 UTC", for error IDs and timestamps a reader may quote. */
export function formatDateTime(value: Date): string {
  return `${day.format(value)}, ${minute.format(value)} UTC`;
}
