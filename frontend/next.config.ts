import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://host.docker.internal:1000/api/:path*",
      },
      {
        source: "/ws/:path*",
        destination: "http://host.docker.internal:1000/ws/:path*",
      },
    ];
  },
};

export default nextConfig;
