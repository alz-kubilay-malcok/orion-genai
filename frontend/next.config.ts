import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: frontendRoot,
  },
};

export default nextConfig;
