import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ValueCommit Shopping Agent Demo",
  description:
    "Value-grounded hidden intention ontology + Preference Commit research demo",
};

// Root layout = 공통 <html>/<body> 껍데기 + 폰트만.
// 헤더(연구자 네비)는 (researcher) route group layout에서만 렌더 — 참가자 /study/*는 헤더 없음.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Google+Sans+Display:wght@400;500;700&family=Google+Sans+Text:wght@400;500;700&family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
