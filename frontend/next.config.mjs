/** @type {import('next').NextConfig} */
const API_BASE = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // 한 턴에 LLM을 여러 번 호출하므로 응답이 길다 (DeepSeek reasoning 모델은 더). 기본
  // dev 프록시 30초 한도를 넘겨 끊기지 않게 늘린다. (없으면 무거운 턴이 30초에 500)
  experimental: {
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
