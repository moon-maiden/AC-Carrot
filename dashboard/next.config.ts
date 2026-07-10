import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Limit CPU and worker threads to prevent pinning CPU at 100% on 1 vCPU droplets
  experimental: {
    workerThreads: false,
    cpus: 1,
  } as any,
};

export default nextConfig;
