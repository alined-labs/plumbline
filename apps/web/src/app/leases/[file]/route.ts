import { loadSampleLeases, readLeaseText } from "@/lib/sample-leases-files";

// Each invented lease as a static text file in the export (/leases/fl-lease-01.md), for the
// lease page's picker to send and for a reader to open.
export const dynamic = "force-static";

export function generateStaticParams() {
  return loadSampleLeases().map((lease) => ({ file: `${lease.id}.md` }));
}

export async function GET(_request: Request, { params }: RouteContext<"/leases/[file]">) {
  const { file } = await params;
  const id = file.replace(/\.md$/, "");
  return new Response(readLeaseText(id), {
    headers: { "Content-Type": "text/markdown; charset=utf-8" },
  });
}
