import Link from "next/link";

// 랜딩은 마케팅 히어로가 아니라 3개 기능으로 들어가는 "런처".
// 01 = 참가자 면, 02·03 = 연구자 도구 (두 청중 구조를 역할 칩으로 드러냄).
const entries = [
  {
    href: "/study/survey",
    index: "01",
    role: "참가자",
    title: "formative study",
    desc: "사전 설문을 작성한 뒤, 참가자가 쇼핑 에이전트와 대화하고 상품에 반응하는 과제로 들어갑니다.",
  },
  {
    href: "/simulate",
    index: "02",
    role: "연구자",
    title: "시뮬레이션",
    desc: "user agent 자동 대화로 합성 데이터를 생성하고, LLM 합성 대화의 주입 의도(GT)↔복원을 검수합니다.",
  },
  {
    href: "/research/sessions",
    index: "03",
    role: "연구자",
    title: "연구자 대시보드",
    desc: "세션 replay · ontology graph · conflict 검토 · pair mining · feature 승인.",
  },
  {
    href: "/pscon",
    index: "04",
    role: "데이터",
    title: "PSCon 대화 시각화",
    desc: "PSCon 실제 쇼핑 대화 648건 — 발화·명료화·추천·좋아요/싫어요를 그대로 시각화.",
  },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-2xl pt-2 sm:pt-6">
      <p className="mb-5 text-xs font-semibold uppercase tracking-[0.2em] text-[#9aa0a6]">
        연구 콘솔
      </p>

      <div className="space-y-3">
        {entries.map((e, i) => (
          <Link
            key={e.href}
            href={e.href}
            style={{ animationDelay: `${i * 70}ms` }}
            className="msg-in card group flex items-center gap-5 p-5 transition-all duration-150 hover:-translate-y-px hover:border-[#4f46e5] hover:shadow-[0_6px_20px_-6px_rgba(79,70,229,0.25)] sm:gap-6 sm:p-6"
          >
            <span className="font-mono text-sm tabular-nums text-[#c2c7cd]">
              {e.index}
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-bold tracking-tight text-[#191919] transition-colors duration-150 group-hover:text-[#4f46e5]">
                  {e.title}
                </h2>
                <span className="rounded-full bg-[#f1f3f5] px-2 py-0.5 text-[11px] font-semibold text-[#868b94]">
                  {e.role}
                </span>
              </div>
              <p className="mt-1 text-sm leading-relaxed text-[#606060]">{e.desc}</p>
            </div>

            <span className="shrink-0 text-lg text-[#c9cdd2] transition-all duration-150 group-hover:translate-x-0.5 group-hover:text-[#4f46e5]">
              →
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
