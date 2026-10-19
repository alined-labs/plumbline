import type { MetadataRoute } from "next";

import { PRODUCT_LINE } from "@/lib/copy";

import { colorOf, type Tokens } from "../../design/tokens";
import tokens from "../../design/tokens.json";

export const dynamic = "force-static";

// The browser chrome around an installed Plumbline: the page canvas in the light theme.
const canvas = colorOf(tokens as Tokens, "bg", "light");

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Plumbline",
    short_name: "Plumbline",
    description: PRODUCT_LINE,
    start_url: "/",
    display: "standalone",
    background_color: canvas,
    theme_color: canvas,
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
