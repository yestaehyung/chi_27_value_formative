"use client";

// 전체 종료 설문 — 모달에서 페이지로 전환 (2026-08-25 QA).
//
// 왜 페이지인가: 모달은 URL이 없어 상태가 브라우저 메모리에만 산다 — 설문 1/8에서
// 새로고침하면 통째로 증발하고 종료 절차를 재진행해야 했다. 페이지는 URL이 곧
// 상태이고, 응답 드래프트를 sessionStorage에 저장해 새로고침에도 이어 쓴다.
// 8구간을 내부 스크롤 한 덩어리로 주던 피로도 문제도 구간당 한 화면으로 나눈다.
//
// 조건은 튜토리얼과 같은 패턴으로 sessionStorage(vc:studyCond)에서 읽는다 —
// URL에 실으면 참가자가 자기 조건을 보게 되어 블라인딩이 깨진다.
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";
import MainSurveyForm from "@/components/study/MainSurveyForm";
import { allQuestions, computeSectionScores, SHOWS_CRITERIA, type StudyCondition } from "@/lib/mainSurvey";
import { canonicalizeStudyAnswers, postStudySectionsLocalized } from "@/lib/localizedMainSurvey";
import { STUDY_UI, tr } from "@/lib/studyI18n";

function FinalSurveyInner() {
  const router = useRouter();
  const params = useSearchParams();
  const pid = params.get("pid") ?? "";
  const draftKey = `vc:draft:final:${pid || "anon"}`;

  const condition: StudyCondition = useMemo(() => {
    const raw = typeof window !== "undefined" ? sessionStorage.getItem("vc:studyCond") : null;
    return raw && raw in SHOWS_CRITERIA ? (raw as StudyCondition) : "ours";
  }, []);
  const sections = useMemo(() => postStudySectionsLocalized(condition), [condition]);

  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [showErrors, setShowErrors] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // 실패는 alert가 아니라 페이지 안 배너로 — 자동화·브라우저 설정으로 alert가
  // 억제되면 "조용히 원상복귀"로 보인다 (2026-08-25 QA #6).
  const [submitError, setSubmitError] = useState(false);
  const [restored, setRestored] = useState(false);

  // 드래프트 복원 — 새로고침·재접속에도 쓰던 응답이 유지된다
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(draftKey);
      if (raw) {
        const d = JSON.parse(raw);
        if (d && typeof d === "object") {
          setAnswers(d.answers ?? {});
          if (typeof d.step === "number") setStep(Math.min(d.step, sections.length - 1));
        }
      }
    } catch { /* 드래프트 없음/파손 — 빈 상태로 시작 */ }
    setRestored(true);
  }, [draftKey, sections.length]);
  useEffect(() => {
    if (!restored) return;
    try { sessionStorage.setItem(draftKey, JSON.stringify({ answers, step })); } catch { /* quota */ }
  }, [answers, step, restored, draftKey]);

  const section = sections[step];
  const sectionIds = useMemo(
    () => (section ? allQuestions([section]).map((q) => q.id) : []),
    [section],
  );
  const missingHere = sectionIds.filter((id) => !answers[id]);
  const allIds = useMemo(() => allQuestions(sections).map((q) => q.id), [sections]);
  const answeredTotal = allIds.filter((id) => answers[id]).length;

  const next = () => {
    if (missingHere.length > 0) {
      setShowErrors(true);
      document.getElementById(`fq-${missingHere[0]}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setShowErrors(false);
    setStep((s) => Math.min(s + 1, sections.length - 1));
    window.scrollTo({ top: 0 });
  };

  const submit = async () => {
    if (missingHere.length > 0) { setShowErrors(true); return; }
    setSubmitting(true);
    setSubmitError(false);
    try {
      if (pid) {
        await api.submitPostStudySurvey(
          pid, canonicalizeStudyAnswers(answers), computeSectionScores(sections, answers));
      }
      try { sessionStorage.removeItem(draftKey); } catch { /* noop */ }
      router.push("/study/done");
    } catch (e) {
      console.error(e);
      setSubmitError(true);
      setSubmitting(false);
    }
  };

  // 물을 섹션이 없는 조건 — 설문 없이 종료
  useEffect(() => {
    if (restored && sections.length === 0) router.replace("/study/done");
  }, [restored, sections.length, router]);
  if (!restored || sections.length === 0 || !section) return null;

  const last = step === sections.length - 1;
  return (
    <div className="mx-auto max-w-lg px-4 pb-28 pt-6">
      <h1 className="text-lg font-bold text-[#191919]">{STUDY_UI.surveyModal.finalTitle}</h1>
      <p className="mt-1 text-xs leading-relaxed text-[#9aa0a6]">{STUDY_UI.surveyModal.finalDescription}</p>

      <div className="mt-3 flex items-center gap-3">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-[#f0f2f4]">
          <div
            className="h-full rounded-full bg-[#4f46e5] transition-[width] duration-300"
            style={{ width: `${(answeredTotal / Math.max(1, allIds.length)) * 100}%` }}
          />
        </div>
        <span className="text-[11px] font-semibold tabular-nums text-slate-400">
          {step + 1} / {sections.length}
        </span>
      </div>

      <div className="mt-5">
        <MainSurveyForm
          sections={[section]}
          answers={answers}
          onChange={(id, v) => setAnswers((p) => ({ ...p, [id]: v }))}
          missingIds={showErrors ? missingHere : []}
        />
        {sectionIds.map((id) => <span key={id} id={`fq-${id}`} className="sr-only" />)}
      </div>

      <div className="fixed inset-x-0 bottom-0 border-t border-[#f0f2f4] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-lg items-center justify-between gap-3 px-4 py-3">
          <div className="text-xs">
            {step > 0 ? (
              <button onClick={() => { setShowErrors(false); setStep((s) => s - 1); }} className="btn px-4 py-2">
                {tr("이전", "Back")}
              </button>
            ) : (
              <span className="tabular-nums text-slate-400">{answeredTotal} / {allIds.length}</span>
            )}
          </div>
          {submitError && (
            <span className="text-xs font-semibold text-rose-600">
              {STUDY_UI.surveyModal.saveFailed}
            </span>
          )}
          {showErrors && missingHere.length > 0 && (
            <span className="text-xs font-semibold text-rose-600">
              {tr(`${missingHere.length}개 문항이 남았어요.`, `${missingHere.length} ${missingHere.length === 1 ? "question remains" : "questions remain"}.`)}
            </span>
          )}
          <button
            onClick={last ? submit : next}
            disabled={submitting}
            className="btn btn-primary px-5 py-2"
          >
            {submitting ? STUDY_UI.surveyModal.submitting
              : last ? STUDY_UI.surveyModal.finalSubmit : tr("다음", "Next")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function FinalSurveyPage() {
  return (
    <Suspense fallback={null}>
      <FinalSurveyInner />
    </Suspense>
  );
}
