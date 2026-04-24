import type { NextConfig } from "next";

const API_BACKEND = process.env.API_BACKEND_URL || "http://localhost:1000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BACKEND}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${API_BACKEND}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
