// What the lease page says about a file before anything is sent: its limit, its types and its
// size in words. Kept apart from the form's schema, so the pages that only show a file load no
// schema library.

/** The API's upload limit (MAX_BYTES in ingest/upload.py), which the dropzone and the schema
 * both say. The Dropzone spec's example reads 20 MB; the server's number is the one to state. */
export const MAX_LEASE_MB = 10;
export const MAX_LEASE_BYTES = MAX_LEASE_MB * 1024 * 1024;

const PDF = "application/pdf";
const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** The `accept` attribute of the file picker. */
export const LEASE_ACCEPT = `.pdf,.docx,${PDF},${DOCX}`;

/** A PDF or a DOCX, by its extension (some browsers give no type for a dropped file) and, when
 * the browser does give one, by its type: a ".pdf" that says it is a picture is refused. */
export function isLeaseFile(file: File): boolean {
  const name = file.name.toLowerCase();
  const byName = name.endsWith(".pdf") || name.endsWith(".docx");
  const byType = file.type === "" || file.type === PDF || file.type === DOCX;
  return byName && byType;
}

/** "1.4 MB", "820 KB": sizes as digits with their unit spelled out (DESIGN.md: Content). */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}
