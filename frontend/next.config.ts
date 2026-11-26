import type { NextConfig } from "next";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

// 폐쇄망에는 빌드 결과물(정적 파일)만 반입한다. 서버 런타임을 쓰지 않는다.
// NEXT_PUBLIC_DEMO_MODE 를 명시적 기본값("0")으로 고정해 기본 빌드에서 데모 대역 코드가 완전히 트리 쉐이킹되게 한다.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  ...(basePath ? { basePath } : {}),
  env: {
    NEXT_PUBLIC_DEMO_MODE: process.env.NEXT_PUBLIC_DEMO_MODE ?? "0",
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
};

export default nextConfig;
