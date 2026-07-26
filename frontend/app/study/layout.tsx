// 참가자 화면: 헤더 없음. 다른 화면으로 나가는 길이 없도록 네비를 두지 않는다.
// (root layout이 <html>/<body>를 담당 — 여기선 컨테이너만.)
export default function StudyLayout({ children }: { children: React.ReactNode }) {
  // 모바일은 여백을 줄여 대화 영역을 확보 (세션 카드가 100dvh 기준으로 높이를 잡음)
  return <main className="mx-auto max-w-7xl px-3 py-3 sm:px-5 sm:py-6">{children}</main>;
}
