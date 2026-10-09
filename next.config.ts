import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // TL 2026-10-09: NEXT_DIST_DIR (set for `next build`/`next start` only)
  // puts the production build in .next-prod while the dev server keeps its
  // own cache in .next — they never collide (2026-10-06 poisoned-cache
  // lesson; dev hot-reloads next.config.ts, so a hard-coded distDir made
  // the running dev follow the prod dir mid-build). Why prod: dev-mode RSS
  // grew ~130MB/min under UI frame polling (external buffer memory the
  // 1024MB V8 old-space cap can't see) and OOM-killed the console twice
  // (15:59Z, ~17:07Z). Production next start holds flat memory.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  // CDP bridge endpoints run python helpers; keep long-running screenshot calls allowed
  serverExternalPackages: [],
  async rewrites() {
    return [];
  },
};

export default nextConfig;
