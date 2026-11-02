import type { NextConfig } from "next";

// 폐쇄망에는 빌드 결과물(정적 파일)만 반입한다. 서버 런타임을 쓰지 않는다.
const nextConfig: NextConfig = {
  output: "export",
  // 정의되지 않은 NEXT_PUBLIC 변수는 번들러가 접지 못해 demo 코드가 산출물에 남는다. 꺼짐("0")을 기본값으로 정의해 둔다 (lib/demo.ts)
  env: {
    NEXT_PUBLIC_ENABLE_DEMO: process.env.NEXT_PUBLIC_ENABLE_DEMO ?? "0",
    // 판정 API 주소(추출 API 와 따로 둘 때). 비워 두면 NEXT_PUBLIC_API_BASE 를 쓴다 (api/judgments.ts)
    NEXT_PUBLIC_JUDGMENT_API_BASE: process.env.NEXT_PUBLIC_JUDGMENT_API_BASE ?? "",
  },
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
