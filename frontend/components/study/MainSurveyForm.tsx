"use client";

// 본실험 설문 렌더러 — `lib/mainSurvey.ts`의 MSection[]을 그린다.
// 5개 도구(사전/과제직전/과제직후/전체종료/기준별)가 전부 이 컴포넌트를 공유하므로,
// 리커트 앵커가 문항마다 다른 경우(NASA-TLX)도 여기서 흡수한다.
import type { MQuestion, MSection } from "@/lib/mainSurvey";
import { LIKERT_POINTS } from "@/lib/mainSurvey";
import { LIKERT_MAX_LOCALIZED, LIKERT_MIN_LOCALIZED } from "@/lib/localizedMainSurvey";

const SCALE = Array.from({ length: LIKERT_POINTS }, (_, i) => i + 1);

export function QuestionRow({
  q,
  value,
  onChange,
  invalid = false,
}: {
  q: MQuestion;
  value?: string;
  onChange: (v: string) => void;
  invalid?: boolean;
}) {
  const min = q.minLabel ?? LIKERT_MIN_LOCALIZED;
  const max = q.maxLabel ?? LIKERT_MAX_LOCALIZED;

  return (
    <div
      className={`-m-1.5 rounded-lg p-1.5 transition-colors duration-200 ${
        invalid ? "bg-rose-50" : "bg-transparent"
      }`}
    >
      <div className="text-[13px] leading-relaxed text-[#191919]">{q.label}</div>

      {q.type === "likert" ? (
        <>
          <div className="mt-1.5 flex gap-1">
            {SCALE.map((n) => {
              const on = value === String(n);
              return (
                <button
                  key={n}
                  type="button"
                  onClick={() => onChange(String(n))}
                  aria-pressed={on}
                  className={`h-10 flex-1 rounded-md border text-xs font-semibold tabular-nums transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.96] ${
                    on
                      ? "border-[#4f46e5] bg-[#4f46e5] text-white"
                      : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                  }`}
                >
                  {n}
                </button>
              );
            })}
          </div>
          {/* 앵커는 양 끝만 — 문항마다 의미가 달라(부담↔성공도) 중앙 라벨을 고정할 수 없다 */}
          <div className="mt-0.5 flex justify-between text-[9px] text-slate-400">
            <span>{min}</span>
            <span>{max}</span>
          </div>
        </>
      ) : (
        <div className="mt-1.5 flex flex-col gap-1">
          {(q.options ?? []).map((opt) => {
            const on = value === opt;
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onChange(opt)}
                aria-pressed={on}
                className={`rounded-md border px-3 py-2 text-left text-xs leading-snug transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.99] ${
                  on
                    ? "border-[#4f46e5] bg-[#eef2ff] font-semibold text-[#4f46e5]"
                    : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                }`}
              >
                {opt}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function MainSurveyForm({
  sections,
  answers,
  onChange,
  missingIds = [],
}: {
  sections: MSection[];
  answers: Record<string, string>;
  onChange: (id: string, v: string) => void;
  /** 표시할 미응답 문항 id — 제출 시도 후에만 채워 보낸다 */
  missingIds?: string[];
}) {
  const missing = new Set(missingIds);
  return (
    <div className="space-y-5">
      {sections.map((sec) => (
        <section key={sec.id}>
          <h3 className="text-xs font-bold text-[#4f46e5]">{sec.title}</h3>
          {sec.desc && <p className="mt-0.5 text-[11px] text-[#9aa0a6]">{sec.desc}</p>}
          <div className="mt-2 space-y-3.5">
            {sec.questions.map((q) => (
              <QuestionRow
                key={q.id}
                q={q}
                value={answers[q.id]}
                onChange={(v) => onChange(q.id, v)}
                invalid={missing.has(q.id)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
