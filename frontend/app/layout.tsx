import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ValueCommit Shopping Agent Demo",
  description:
    "Value-grounded hidden intention ontology + Preference Commit research demo",
};

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
      <body className="min-h-screen antialiased">
        <header className="sticky top-0 z-40 border-b border-[#e4e8eb] bg-white">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-5">
            <Link href="/" className="flex items-center">
              <span className="text-lg font-extrabold tracking-tight text-[#191919]">
                ValueCommit
              </span>
            </Link>
            <nav className="flex items-center gap-0.5 text-sm">
              <Link
                href="/study/session/new"
                className="rounded-lg px-3.5 py-2 font-medium text-[#404040] transition hover:bg-[#f5f6f8] hover:text-[#4f46e5]"
              >
                참가자 세션
              </Link>
              <Link
                href="/simulate"
                className="rounded-lg px-3.5 py-2 font-medium text-[#404040] transition hover:bg-[#f5f6f8] hover:text-[#4f46e5]"
              >
                시뮬레이션
              </Link>
              <Link
                href="/research/sessions"
                className="rounded-lg px-3.5 py-2 font-medium text-[#404040] transition hover:bg-[#f5f6f8] hover:text-[#4f46e5]"
              >
                연구자 대시보드
              </Link>
              <Link
                href="/pscon"
                className="rounded-lg px-3.5 py-2 font-medium text-[#404040] transition hover:bg-[#f5f6f8] hover:text-[#4f46e5]"
              >
                PSCon 대화
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-5 py-6">{children}</main>
      </body>
    </html>
  );
}
