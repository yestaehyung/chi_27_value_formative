"use client";

// 세션 종료 사후 설문 모달 — "이 쇼핑 마치기" 확인 후, 완료 화면 전에 표시.
// 핵심 3구인(이해·만족·신뢰)은 필수, 확장 4구인은 선택. 7점 리커트(사전 설문과 동일 언어).
import { useMemo, useState } from "react";
import {
  POST_SURVEY, POST_CORE_IDS, computePostProfile,
  LIKERT_MIN, LIKERT_MID, LIKERT_MAX,
} from "@/lib/survey";

export default function PostSurveyModal({
  onSubmit,
  onSkip,
  submitting = false,
}: {
  onSubmit: (answers: Record<string, string>, profile: Record<string, number>) => void;
  onSkip: () => void;
  submitting?: boolean;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [showErrors, setShowErrors] = useState(false);

  const missingCore = useMemo(
    () => POST_CORE_IDS.filter((id) => !answers[id]),
    [answers]
  );

  const submit = () => {
    if (missingCore.length > 0) { setShowErrors(true); return; }
    onSubmit(answers, computePostProfile(answers));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="card flex max-h-[88vh] w-full max-w-lg flex-col overflow-hidden">
        <div className="border-b border-[#f0f2f4] px-6 py-4">
          <h2 className="text-base font-bold text-[#191919]">이번 쇼핑 대화는 어떠셨나요?</h2>
          <p className="mt-1 text-xs text-[#9aa0a6]">
            방금 마친 대화에 대해 답해 주세요. <b className="text-[#4f46e5]">이해·만족·신뢰</b>는 필수, 나머지는 선택입니다.
          </p>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-4">
          {POST_SURVEY.map((g) => (
            <section key={g.id}>
              <h3 className="text-xs font-bold text-[#4f46e5]">
                {g.title}
                {!g.core && <span className="ml-1.5 font-normal text-[#b0b8c1]">(선택)</span>}
              </h3>
              <div className="mt-2 space-y-3.5">
                {g.items.map((item) => {
                  const isMissing = showErrors && g.core && !answers[item.id];
                  return (
                    <div key={item.id} className={`-m-1.5 rounded-lg p-1.5 transition-colors duration-200 ${isMissing ? "bg-rose-50" : "bg-transparent"}`}>
                      <div className="text-[13px] leading-relaxed text-[#191919]">{item.label}</div>
                      <div className="mt-1.5 flex gap-1">
                        {[1, 2, 3, 4, 5, 6, 7].map((n) => {
                          const on = answers[item.id] === String(n);
                          return (
                            <button
                              key={n}
                              type="button"
                              onClick={() => setAnswers((p) => ({ ...p, [item.id]: String(n) }))}
                              className={`h-8 flex-1 rounded-md border text-xs font-semibold tabular-nums transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.96] ${
                                on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                              }`}
                            >
                              {n}
                            </button>
                          );
                        })}
                      </div>
                      <div className="mt-0.5 grid grid-cols-7 gap-1 text-[9px] text-slate-400">
                        <span className="col-start-1 text-left">{LIKERT_MIN}</span>
                        <span className="col-start-4 text-center">{LIKERT_MID}</span>
                        <span className="col-start-7 text-right">{LIKERT_MAX}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[#f0f2f4] px-6 py-3">
          <div className="text-xs">
            {showErrors && missingCore.length > 0 ? (
              <span className="font-semibold text-rose-600">필수 문항 <span className="tabular-nums">{missingCore.length}</span>개가 남았어요.</span>
            ) : (
              <button onClick={onSkip} disabled={submitting} className="text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline disabled:opacity-40">
                건너뛰기
              </button>
            )}
          </div>
          <button onClick={submit} disabled={submitting} className="btn btn-primary px-5 py-2">
            {submitting ? "제출 중…" : "제출하고 마치기"}
          </button>
        </div>
      </div>
    </div>
  );
}
