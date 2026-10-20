import { z } from "zod";

import { JURISDICTION_IDS } from "./jurisdictions";

/** The API's upload limit, and what the dropzone says it takes ("PDF or DOCX, up to 20 MB"). */
export const MAX_LEASE_BYTES = 20 * 1024 * 1024;

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

// Errors say how to fix the input, not what is wrong with it (Field spec). The type and size
// are checked here, in the browser, before anything is sent.
export const uploadSchema = z.object({
  file: z
    .instanceof(File, { error: "Choose a lease to check" })
    .refine(isLeaseFile, "Upload a PDF or DOCX file")
    .refine((file) => file.size > 0, "This file is empty: choose a lease with text in it")
    .refine((file) => file.size <= MAX_LEASE_BYTES, "Choose a file of 20 MB or less"),
  // Empty: the checker reads the jurisdiction from the lease.
  jurisdiction: z.union([z.literal(""), z.enum(JURISDICTION_IDS)]),
  // Empty: the checker does not assume a signing date.
  signedOn: z.union([z.literal(""), z.iso.date("Enter the date as day, month and year")]),
});

export type UploadValues = z.infer<typeof uploadSchema>;
