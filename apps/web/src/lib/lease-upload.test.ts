import { formatBytes, isLeaseFile, MAX_LEASE_BYTES, uploadSchema } from "./lease-upload";

const pdf = (name = "lease.pdf", size = 1000, type = "application/pdf") =>
  new File([new Uint8Array(size)], name, { type });

describe("isLeaseFile", () => {
  it("takes a PDF or a DOCX by its name, and by its type when it has one", () => {
    expect(isLeaseFile(pdf())).toBe(true);
    expect(isLeaseFile(pdf("Lease.PDF"))).toBe(true);
    expect(isLeaseFile(pdf("lease.pdf", 10, ""))).toBe(true);
    expect(
      isLeaseFile(
        pdf(
          "lease.docx",
          10,
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
      ),
    ).toBe(true);
  });

  it("refuses anything else, including a .pdf that says it is a picture", () => {
    expect(isLeaseFile(pdf("lease.doc", 10, "application/msword"))).toBe(false);
    expect(isLeaseFile(pdf("scan.png", 10, "image/png"))).toBe(false);
    expect(isLeaseFile(pdf("fake.pdf", 10, "image/png"))).toBe(false);
  });
});

describe("uploadSchema", () => {
  const messages = (input: unknown) => {
    const result = uploadSchema.safeParse(input);
    return result.success ? [] : result.error.issues.map((issue) => issue.message);
  };
  const filters = { jurisdiction: "", signedOn: "" } as const;

  it("accepts a lease with no filters", () => {
    expect(uploadSchema.safeParse({ file: pdf(), ...filters }).success).toBe(true);
  });

  it("says what to do when there is no file, the type is wrong, or it is empty or too big", () => {
    expect(messages({ file: undefined, ...filters })).toEqual(["Choose a lease to check"]);
    expect(messages({ file: pdf("lease.txt", 10, "text/plain"), ...filters })).toEqual([
      "Upload a PDF or DOCX file",
    ]);
    expect(messages({ file: pdf("lease.pdf", 0), ...filters })).toEqual([
      "This file is empty: choose a lease with text in it",
    ]);
    expect(messages({ file: pdf("lease.pdf", MAX_LEASE_BYTES + 1), ...filters })).toEqual([
      "Choose a file of 10 MB or less",
    ]);
  });

  it("takes a jurisdiction and a signing date, or neither", () => {
    expect(
      uploadSchema.safeParse({ file: pdf(), jurisdiction: "spain", signedOn: "2024-03-01" })
        .success,
    ).toBe(true);
    expect(messages({ file: pdf(), jurisdiction: "texas", signedOn: "" })).not.toEqual([]);
    expect(messages({ file: pdf(), jurisdiction: "", signedOn: "2024-02-30" })).toEqual([
      "Enter the date as day, month and year",
    ]);
  });
});

describe("formatBytes", () => {
  it("writes sizes as digits with their unit", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(820 * 1024)).toBe("820 KB");
    expect(formatBytes(1.4 * 1024 * 1024)).toBe("1.4 MB");
  });
});
