import Link from "next/link";

// 연구자/쇼케이스 화면 공통 레이아웃 = 헤더(네비) + 컨테이너.
// route group `(researcher)`는 URL에 안 나타난다 (/research, /simulate, /pscon, / 그대로).
// 참가자 /study/*는 이 layout을 안 쓰므로 헤더가 없다.
export default function ResearcherLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
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
    </>
  );
}
