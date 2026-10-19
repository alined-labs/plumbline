import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/brand/logo";
import { DISCLAIMER, PRODUCT_LINE } from "@/lib/copy";
import { fontVariables } from "@/lib/fonts";

import { colorOf, type Tokens } from "../../design/tokens";
import tokens from "../../design/tokens.json";

import "./globals.css";

const design = tokens as Tokens;

export const metadata: Metadata = {
  // The live origin, so the link preview resolves; the deployment sets it.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"),
  title: "Plumbline",
  description: PRODUCT_LINE,
};

// The browser chrome follows the page canvas in each theme.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: colorOf(design, "bg", "light") },
    { media: "(prefers-color-scheme: dark)", color: colorOf(design, "bg", "dark") },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={fontVariables}>
      <body className="min-h-dvh bg-bg text-fg antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <header className="border-b border-border">
          <div className="mx-auto flex max-w-content items-center justify-between px-4 py-1">
            <Link
              href="/"
              aria-label="Plumbline home"
              className="inline-flex min-h-11 items-center rounded-sm"
            >
              <Logo className="h-5.5 w-auto" />
            </Link>
            <p className="text-small text-fg-muted">Legal information, not legal advice</p>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-content px-4 py-8">
          {children}
        </main>
        <footer className="border-t border-border">
          <p className="mx-auto max-w-content px-4 py-4 text-small text-fg-muted">{DISCLAIMER}</p>
        </footer>
      </body>
    </html>
  );
}
