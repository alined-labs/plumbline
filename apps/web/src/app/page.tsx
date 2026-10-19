import { Chat } from "@/components/chat/chat";
import { PRODUCT_LINE } from "@/lib/copy";

export default function Home() {
  return (
    <>
      <h1 className="text-heading-1">Ask about tenancy law</h1>
      <p className="mt-2 text-fg-muted">{PRODUCT_LINE}</p>
      <Chat />
    </>
  );
}
