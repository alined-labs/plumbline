import { loadReplay } from "@/lib/replay-files";

// The stored dev answers as one static file in the export, fetched by the chat page only in
// the static tier.
export const dynamic = "force-static";

export function GET() {
  return Response.json(loadReplay());
}
