import type { NextConfig } from "next";

const config: NextConfig = {
  async rewrites() {
    const backend = (
      process.env.CLEAR_API_URL || "http://127.0.0.1:8000"
    ).replace(/\/$/, "");
    return [{ source: "/api/clear/:path*", destination: `${backend}/:path*` }];
  },
};

export default config;
