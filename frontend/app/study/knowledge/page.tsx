"use client";

// 과제 직전 제품군 지식 설문 (2026-08-17 개편, 측정 계획 §4) — **다음 쇼핑 카테고리 1개만**.
//
// 해당 제품군에 대해: 주관적 지식 5문항(Flynn & Goldsmith 1999, 2·4·5 역채점)
// + 구매 경험 1 + 초기 기준 명확성 1 + 자유응답(현재 생각하는 기준).
//
// 이전에는 네 제품군을 한 행렬(28문항)로 한 번에 받았는데, 부담이 크고 뒤 카테고리의
// 응답 시점이 실제 과제와 멀어졌다 → 각 쇼핑 대화 직전에 그 카테고리만 받는다(연구자
// 결정). 각 카테고리의 "초기" 상태는 **그 카테고리 대화가 시작되기 전**이라는 성질은
// 유지된다. 자유응답은 기준 감사(precision/recall)의 사전 기준선이 된다.
//
// 진행 판단은 서버(task-progress)가 우선 — knowledgeDone에 있는 카테고리는 재질문
// 없이 바로 세션을 연다(새로고침 멱등). 서버 실패 시 로컬 큐 폴백.
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";
import MainSurveyForm from "@/components/study/MainSurveyForm";
import {
  KNOWLEDGE_SECTIONS_LOCALIZED, TEST_SURVEY_SKIP, computeKnowledgeScore,
  fillTemplate, canonicalizeStudyAnswerValue } from "@/lib/localizedMainSurvey";
import { allQuestions, type MSection } from "@/lib/mainSurvey";
import { nextTask } from "@/lib/taskQueue";
import type { Familiarity } from "@/lib/types";
import { STUDY_UI, categoryLabel, tr } from "@/lib/studyI18n";

type Target = { category: string; familiarity: Familiarity };

function KnowledgeInner() {
  const router = useRouter();
  const params = useSearchParams();
  const pid = params.get("pid") ?? "";
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [missing, setMissing] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [target, setTarget] = useState<Target | null>(null);
  const [taskNo, setTaskNo] = useState<{ n: number; total: number } | null>(null);
  const [loading, setLoading] = useState(true);

  const openSession = async (task: Target) => {
    const res = await api.createCategorySession(task.category, task.familiarity, pid || undefined);
    router.push(`/study/session/${res.sessionId}`);
  };

  // 다음 과제 결정 — 서버 진행(task-progress) 우선, 로컬 큐 폴백.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let task: Target | null = null;
      let knowledgeDone: string[] = [];
      if (pid) {
        try {
          const p = await api.getTaskProgress(pid);
          if (p.tasks.length > 0) {
            task = p.next;
            knowledgeDone = p.knowledgeDone ?? [];
            if (task) {
              const idx = p.tasks.findIndex((t) => t.category === task!.category);
              setTaskNo({ n: idx + 1, total: p.tasks.length });
            }
          }
        } catch { /* 서버 실패 → 로컬 큐 폴백 */ }
      }
      if (!task) task = nextTask(pid || undefined);
      if (cancelled) return;
      if (!task) {
        // 계획이 없다(직접 URL 진입·세션 유실) → 카테고리 선택부터.
        router.replace(pid ? `/study/categories?pid=${pid}` : "/study/categories");
        return;
      }
      if (knowledgeDone.includes(task.category)) {
        // 이미 이 카테고리 설문을 냈다(새로고침 등) → 바로 쇼핑으로.
        await openSession(task);
        return;
      }
      setTarget(task);
      setLoading(false);
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  // 이번 카테고리 섹션 — 문항 id를 "k:{카테고리}:" 프리픽스로 유일화한다.
  const sections = useMemo<MSection[]>(() => {
    if (!target) return [];
    const filled = fillTemplate(KNOWLEDGE_SECTIONS_LOCALIZED, { category: categoryLabel(target.category) });
    return filled.map((sec) => ({
      ...sec,
      id: `${sec.id}:${target.category}`,
      questions: sec.questions.map((q) => ({ ...q, id: `k:${target.category}:${q.id}` })),
    }));
  }, [target]);

  const requiredIds = useMemo(
    () => allQuestions(sections).filter((q) => q.type !== "text").map((q) => q.id),
    [sections],
  );

  const submit = async () => {
    if (!target) return;
    const miss = requiredIds.filter((id) => !answers[id]);
    if (miss.length > 0) { setMissing(miss); return; }
    setSubmitting(true);
    try {
      const scores: Record<string, number> = {};
      const s = computeKnowledgeScore(answers, `k:${target.category}:`);
      if (s !== null) scores[target.category] = s;
      // EN 모드: 표시값(영어 선택지)을 정본(한국어 선택지)으로 변환해 저장 — id가
      // k:{카테고리}:{문항id} 접두형이라 내부 문항 id로 벗겨서 매핑한다.
      const canonicalAnswers = Object.fromEntries(
        Object.entries(answers).map(([k, v]) => {
          const innerId = k.split(":").pop() ?? k;
          return [k, canonicalizeStudyAnswerValue(innerId, v)];
        }),
      );
      if (pid) await api.submitKnowledgeSurvey(pid, canonicalAnswers, scores, [target.category]);
      await openSession(target);
    } catch (e) {
      console.error(e);
      alert(STUDY_UI.survey.submitError);
      setSubmitting(false);
    }
  };

  const skip = async () => {
    if (!target) return;
    setSubmitting(true);
    try { await openSession(target); } catch (e) { console.error(e); setSubmitting(false); }
  };

  if (loading || !target) return null;

  return (
    <div className="mx-auto max-w-2xl space-y-5 pb-32 pt-2">
      <div>
        {taskNo && (
          <div className="text-[11px] font-semibold tabular-nums text-[#9aa0a6]">
            {tr(`쇼핑 ${taskNo.n} / ${taskNo.total}`, `Shopping task ${taskNo.n} of ${taskNo.total}`)}
          </div>
        )}
        <h1 className="mt-1 text-xl font-bold">
          {tr(
            `'${categoryLabel(target.category)}' 쇼핑 전에 알려주세요`,
            `Before You Shop for ${categoryLabel(target.category)}`,
          )}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">
          {tr(
            "이 상품군에 대한 지금의 생각을 알려주세요. 정답은 없어요.",
            "Tell us what you currently think about this category. There are no right answers.",
          )}
        </p>
      </div>

      <section className="card space-y-4 p-5">
        <MainSurveyForm
          sections={sections}
          answers={answers}
          onChange={(id, v) => setAnswers((p) => ({ ...p, [id]: v }))}
          missingIds={missing}
        />
      </section>

      {/* sticky 제출 바 */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[#e9ecef] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <div className="text-xs">
            {missing.length > 0 ? (
              <span className="font-semibold text-rose-600">{STUDY_UI.survey.requiredRemaining(missing.length)}</span>
            ) : (
              <span className="tabular-nums text-slate-400">
                {requiredIds.filter((id) => answers[id]).length} / {requiredIds.length}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {TEST_SURVEY_SKIP && (
              <button
                onClick={skip}
                disabled={submitting}
                className="rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs text-slate-500 transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] disabled:opacity-40"
              >
                {STUDY_UI.survey.skip}
              </button>
            )}
            <button onClick={submit} disabled={submitting} className="btn btn-primary px-5 py-2 disabled:opacity-40">
              {submitting ? STUDY_UI.survey.submitting : tr("제출하고 쇼핑 시작", "Submit and Start Shopping")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  return (
    <Suspense fallback={null}>
      <KnowledgeInner />
    </Suspense>
  );
}
