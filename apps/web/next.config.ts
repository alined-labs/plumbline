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
  // `next dev` would otherwise write its own AGENTS.md here; the repository's agent rules
  // live in the root AGENTS.md alone.
  agentRules: false,
  // Always defined, so outside a profiling build ChatProfiler's condition is the constant
  // "" === "1" and the minifier drops the Profiler (docs/notes/streamed-answer-profile.md).
  env: { NEXT_PUBLIC_PROFILE: process.env.NEXT_PUBLIC_PROFILE ?? "" },
};

export default config;
