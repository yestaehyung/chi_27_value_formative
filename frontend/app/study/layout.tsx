// 참가자 화면: 헤더 없음. 다른 화면으로 나가는 길이 없도록 네비를 두지 않는다.
// (root layout이 <html>/<body>를 담당 — 여기선 컨테이너만.)
export default function StudyLayout({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto max-w-7xl px-4 py-6 sm:px-5">{children}</main>;
}
