import { z } from "zod";

import { JURISDICTION_IDS } from "./jurisdictions";

import { isLeaseFile, MAX_LEASE_BYTES, MAX_LEASE_MB } from "./lease-file";

export {
  formatBytes,
  isLeaseFile,
  LEASE_ACCEPT,
  MAX_LEASE_BYTES,
  MAX_LEASE_MB,
} from "./lease-file";

// Errors say how to fix the input, not what is wrong with it (Field spec). The type and size
// are checked here, in the browser, before anything is sent.
export const uploadSchema = z.object({
  file: z
    .instanceof(File, { error: "Choose a lease to check" })
    .refine(isLeaseFile, "Upload a PDF or DOCX file")
    .refine((file) => file.size > 0, "This file is empty: choose a lease with text in it")
    .refine((file) => file.size <= MAX_LEASE_BYTES, `Choose a file of ${MAX_LEASE_MB} MB or less`),
  // Empty: the checker reads the jurisdiction from the lease.
  jurisdiction: z.union([z.literal(""), z.enum(JURISDICTION_IDS)]),
  // Empty: the checker does not assume a signing date.
  signedOn: z.union([z.literal(""), z.iso.date("Enter the date as day, month and year")]),
});

export type UploadValues = z.infer<typeof uploadSchema>;
