import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DemoBanner } from "@/components/shell/demo-banner";
import { QueryProvider } from "@/providers/query-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "MSDS 검수",
  description: "MSDS 추출값 검수 화면",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        {process.env.NEXT_PUBLIC_DEMO_MODE === "1" && <DemoBanner />}
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
