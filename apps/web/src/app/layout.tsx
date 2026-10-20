import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { MobileBar } from "@/components/shell/mobile-bar";
import { SidebarContent } from "@/components/shell/sidebar";
import { SiteFooter } from "@/components/shell/site-footer";
import { PRODUCT_LINE } from "@/lib/copy";
import { fontVariables } from "@/lib/fonts";
import { THEME_SCRIPT } from "@/lib/theme";

import { colorOf, type Tokens } from "../../design/tokens";
import tokens from "../../design/tokens.json";

import { Providers } from "./providers";

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
    // The head script may set data-theme before React hydrates, hence suppressHydrationWarning.
    <html lang="en" className={fontVariables} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-dvh bg-bg text-fg antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-(--pl-z-tooltip) focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <Providers>
          {/* AppShell: the sidebar (rail from 768px, drawer below), then the page column.
              The source panel joins as a third pane in E3. */}
          <div className="flex min-h-dvh">
            <div className="sticky top-0 hidden h-dvh w-(--pl-sidebar-rail) shrink-0 flex-col border-r border-border bg-bg-subtle px-2.5 py-3 md:flex lg:w-(--pl-sidebar-width)">
              <SidebarContent mode="aside" />
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
              <MobileBar />
              <main id="main" tabIndex={-1} className="flex-1 px-4 py-8 md:px-8">
                <div className="mx-auto w-full max-w-content">{children}</div>
              </main>
              <SiteFooter />
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
