import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow isolated verification when OneDrive locks the usual build directory.
  distDir: process.env.NEXT_BUILD_DIR ?? ".next",
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
