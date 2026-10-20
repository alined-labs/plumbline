import { Chat } from "@/components/chat/chat";

export default function Home() {
  return (
    <>
      {/* The empty state's question is the visible title; the page keeps one h1 throughout. */}
      <h1 className="sr-only">Ask about tenancy law</h1>
      <Chat />
    </>
  );
}
