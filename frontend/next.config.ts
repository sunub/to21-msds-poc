import type { NextConfig } from "next";

// 폐쇄망에는 빌드 결과물(정적 파일)만 반입한다. 서버 런타임을 쓰지 않는다.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
