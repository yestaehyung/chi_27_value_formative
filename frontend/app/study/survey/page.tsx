"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import {
  SURVEY, SURVEY_INTRO, REQUIRED_IDS, computeProfile,
  LIKERT_MIN, LIKERT_MID, LIKERT_MAX, SurveyQuestion,
} from "@/lib/survey";

type Answers = Record<string, string | string[]>;

export default function SurveyPage() {
  const router = useRouter();
  const [answers, setAnswers] = useState<Answers>({});
  const [submitting, setSubmitting] = useState(false);
  const [showErrors, setShowErrors] = useState(false);

  const set = (id: string, value: string | string[]) => setAnswers((p) => ({ ...p, [id]: value }));
  const toggleMulti = (id: string, opt: string) =>
    setAnswers((p) => {
      const cur = (p[id] as string[]) || [];
      return { ...p, [id]: cur.includes(opt) ? cur.filter((o) => o !== opt) : [...cur, opt] };
    });

  // 참여 제외 / 필수 미응답
  const excluded = useMemo(
    () => SURVEY.some((s) => s.questions.some((q) => q.excludeIf && answers[q.id] === q.excludeIf)),
    [answers]
  );
  const missing = useMemo(
    () => REQUIRED_IDS.filter((id) => { const v = answers[id]; return v === undefined || v === ""; }),
    [answers]
  );
  // 화면 표시용 전체 누적 문항 번호 (id → 1..N)
  const qNumbers = useMemo(() => {
    const m: Record<string, number> = {};
    let n = 0;
    SURVEY.forEach((s) => s.questions.forEach((q) => { m[q.id] = ++n; }));
    return m;
  }, []);
  const canSubmit = !excluded && missing.length === 0 && !submitting;

  const proceed = async () => {
    setSubmitting(true);
    try {
      const profile = computeProfile(answers);
      const res = await api.submitSurvey(answers, profile); // 비어 있어도 참가자 생성(흐름 동일)
      router.push(`/study/tutorial?pid=${res.participantId}`);
    } catch (e) {
      console.error(e);
      setSubmitting(false);
      alert("설문 제출에 실패했어요. 잠시 후 다시 시도해 주세요.");
    }
  };
  const submit = () => {
    if (excluded || missing.length > 0) { setShowErrors(true); return; }
    proceed();
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 pb-32">
      <div>
        <h1 className="text-xl font-bold">Formative Study 사전 설문</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">{SURVEY_INTRO}</p>
      </div>

      {SURVEY.map((section) => (
        <section key={section.id} className="card space-y-5 p-5">
          <div>
            <h2 className="text-sm font-bold text-[#4f46e5]">{section.title}</h2>
            {section.desc && <p className="mt-1 text-xs text-slate-500">{section.desc}</p>}
          </div>
          {section.questions.map((q) => (
            <Question
              key={q.id}
              q={q}
              num={qNumbers[q.id]}
              value={answers[q.id]}
              showError={showErrors}
              onSingle={(v) => set(q.id, v)}
              onMulti={(opt) => toggleMulti(q.id, opt)}
              onText={(v) => set(q.id, v)}
            />
          ))}
        </section>
      ))}

      {/* sticky 제출 바 */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[#e9ecef] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <div className="text-xs">
            {excluded ? (
              <span className="font-semibold text-rose-600">참여 기준/동의에 &apos;아니오&apos;가 있어 연구 참여 대상이 아닙니다.</span>
            ) : missing.length > 0 ? (
              <span className="text-slate-500">필수(참여기준·동의) {missing.length}개 남음</span>
            ) : (
              <span className="text-emerald-600">제출 준비 완료 — 제출 후 쇼핑 대화로 이동합니다.</span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={proceed}
              disabled={submitting}
              title="테스트용 — 응답 없이 바로 대화로 이동"
              className="rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs text-slate-500 transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] disabled:opacity-40 enabled:active:scale-[0.96]"
            >
              건너뛰기 (테스트)
            </button>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="btn btn-primary px-5 py-2 disabled:opacity-40"
            >
              {submitting ? "제출 중…" : "제출하고 대화 시작하기"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Question({
  q, num, value, showError, onSingle, onMulti, onText,
}: {
  q: SurveyQuestion;
  num: number;
  value: string | string[] | undefined;
  showError: boolean;
  onSingle: (v: string) => void;
  onMulti: (opt: string) => void;
  onText: (v: string) => void;
}) {
  const isMissing = showError && q.required && (value === undefined || value === "");
  const excludedHere = q.excludeIf && value === q.excludeIf;

  return (
    <div className={isMissing ? "rounded-lg bg-rose-50 p-2 -m-2" : ""}>
      <label className="block text-sm font-medium text-[#191919]">
        <span className="mr-1 text-slate-400">{num}.</span>{q.label}
        {q.required && <span className="ml-1 text-rose-500">*</span>}
      </label>

      {q.type === "likert" && (
        <div className="mt-2">
          <div className="flex gap-1.5">
            {[1, 2, 3, 4, 5, 6, 7].map((n) => {
              const on = value === String(n);
              return (
                <button
                  key={n}
                  type="button"
                  onClick={() => onSingle(String(n))}
                  className={`h-9 flex-1 rounded-md border text-sm font-semibold transition-colors ${
                    on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                  }`}
                >
                  {n}
                </button>
              );
            })}
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-slate-400">
            <span>{LIKERT_MIN}</span><span>{LIKERT_MID}</span><span>{LIKERT_MAX}</span>
          </div>
        </div>
      )}

      {q.type === "single" && (
        <div className="mt-2 space-y-1.5">
          {q.options!.map((opt) => {
            const on = value === opt;
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onSingle(opt)}
                className={`block w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                  on ? "border-[#4f46e5] bg-[#eef2ff] font-medium" : "border-[#e4e8eb] hover:border-[#4f46e5]"
                }`}
              >
                {opt}
              </button>
            );
          })}
          {excludedHere && <p className="text-xs text-rose-500">이 응답은 연구 참여 제외 사유입니다.</p>}
        </div>
      )}

      {q.type === "multi" && (
        <div className="mt-2 flex flex-wrap gap-2">
          {q.options!.map((opt) => {
            const on = ((value as string[]) || []).includes(opt);
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onMulti(opt)}
                className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                  on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                }`}
              >
                {opt}
              </button>
            );
          })}
        </div>
      )}

      {q.type === "text" && (
        <input
          value={(value as string) || ""}
          onChange={(e) => onText(e.target.value)}
          placeholder={q.placeholder}
          className="mt-2 w-full rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none"
        />
      )}

      {q.type === "textlong" && (
        <textarea
          value={(value as string) || ""}
          onChange={(e) => onText(e.target.value)}
          placeholder={q.placeholder}
          rows={3}
          className="mt-2 w-full resize-none rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none"
        />
      )}
    </div>
  );
}
