import type { NextConfig } from "next";

// One build serves both tiers: the static export is the whole front end, and the live
// chat talks to the API from the browser (NEXT_PUBLIC_API_BASE_URL).
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
  typedRoutes: true,
  transpilePackages: ["@plumbline/ts-client"],
};

export default config;
