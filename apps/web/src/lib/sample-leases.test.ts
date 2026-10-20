import { leasePath, parseLeaseHeader, parseLeasePlaces, sortLeases } from "./sample-leases";
import { loadSampleLeases, readLeaseText } from "./sample-leases-files";

const HEADER = `# Lease of a Dwelling (Contrato de arrendamiento de vivienda)

Synthetic lease for Plumbline's lease checker.

- Lease id: es-lease-02
- Jurisdiction: Spain
- Signed on: 2026-04-01

## Parties
`;

describe("parseLeaseHeader", () => {
  it("reads the title, id, jurisdiction and signing date a lease opens with", () => {
    expect(parseLeaseHeader(HEADER)).toEqual({
      id: "es-lease-02",
      place: "Lease of a Dwelling (Contrato de arrendamiento de vivienda)",
      title: "Lease of a Dwelling (Contrato de arrendamiento de vivienda)",
      jurisdiction: { id: "spain", code: "ES", name: "Spain" },
      signedOn: "2026-04-01",
    });
  });

  it("reads the jurisdiction's first word, as the Florida and Dubai leases write it", () => {
    const text = HEADER.replace("Spain", "Florida, United States");
    expect(parseLeaseHeader(text)?.jurisdiction.id).toBe("florida");
  });

  it("leaves out a lease that strays from the format", () => {
    expect(parseLeaseHeader(HEADER.replace("- Signed on: 2026-04-01", ""))).toBeNull();
    expect(parseLeaseHeader(HEADER.replace("Spain", "Portugal"))).toBeNull();
  });
});

describe("parseLeasePlaces", () => {
  it("reads each lease's description from the README's table", () => {
    const readme = [
      "| Lease | Signed | Planted findings | Lawful lookalikes |",
      "| --- | --- | --- | --- |",
      "| `fl-lease-01`, Miami apartment | 2026-08-15 | waiver | notice |",
      "| `es-lease-02`, Valencia flat, company landlord | 2026-04-01 | term | guarantee |",
    ].join("\n");
    expect(Object.fromEntries(parseLeasePlaces(readme))).toEqual({
      "fl-lease-01": "Miami apartment",
      "es-lease-02": "Valencia flat, company landlord",
    });
  });
});

describe("the committed leases", () => {
  const leases = loadSampleLeases();

  it("are the ten invented leases, in the jurisdictions' order, each told apart by its place", () => {
    expect(leases).toHaveLength(10);
    expect(leases.map((lease) => lease.jurisdiction.code)).toEqual([
      "AE-DU",
      "AE-DU",
      "ES",
      "ES",
      "ES",
      "CO",
      "CO",
      "US-FL",
      "US-FL",
      "US-FL",
    ]);
    expect(new Set(leases.map((lease) => lease.place)).size).toBe(10);
    expect(leases.find((lease) => lease.id === "fl-lease-01")?.place).toBe("Miami apartment");
  });

  it("are served as their own text", () => {
    expect(readLeaseText("fl-lease-01")).toContain("- Lease id: fl-lease-01");
    expect(leasePath("fl-lease-01")).toBe("/leases/fl-lease-01.md");
  });

  it("keep their order whatever order they are read in", () => {
    expect(sortLeases([...leases].reverse())).toEqual(leases);
  });
});
