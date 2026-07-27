"use client";

// 추론된 구매 기준별 직접 검증 (본실험 설문 §5).
// 에이전트가 추론한 주요 기준 3–5개를 **한 번에 하나씩** 제시하고, 기준마다 4문항을 묻는다.
// 한 화면에 전부 깔면 3~5×4 = 12~20문항이라 응답 품질이 무너진다 — 세션 중 기준 확인
// (SequentialCriteriaConfirm)과 같은 순차 패턴을 유지한다.
//
// 근거(evidence)를 함께 보여주는 게 핵심이다. 3번 문항이 "제시된 근거가 이 기준을
// 뒷받침하는가"를 묻기 때문에, 근거를 안 보여주면 그 문항 자체가 성립하지 않는다.
import { useMemo, useState } from "react";

import { CRITERION_CHECK } from "@/lib/mainSurvey";
import { QuestionRow } from "@/components/study/MainSurveyForm";

export type CriterionCandidate = {
  topic: { id: string; label: string; priority?: string | null };
  evidence: { id: string; type: string; quote?: string; role?: string; productTitle?: string; feedbackType?: string }[];
};

export type CriterionAnswer = {
  topicId: string;
  topicLabel: string;
  matches?: string;
  importance?: number;
  evidenceSupports?: string;
  formation?: string;
};

/** 응답 키 → 백엔드 필드 */
const FIELD: Record<string, keyof CriterionAnswer> = {
  CRIT_MATCH: "matches",
  CRIT_IMPORTANCE: "importance",
  CRIT_EVIDENCE: "evidenceSupports",
  CRIT_FORMATION: "formation",
};

/** 화면 표기 → 저장 값 (분석 시 문자열 비교가 깨지지 않게 짧은 키로 박제) */
const FORMATION_CODE: Record<string, string> = {
  "처음부터 가지고 있었지만 대화에서 직접 표현하지 않았다": "처음부터_미표현",
  "원래 가지고 있었지만 대화 중 더 명확해졌다": "대화중_명확해짐",
  "상품 탐색과 대화 중 새롭게 형성되었다": "대화중_새로형성",
};

function EvidenceList({ items }: { items: CriterionCandidate["evidence"] }) {
  if (!items.length) {
    return <p className="text-[11px] text-slate-400">이 기준에 연결된 근거 기록이 없습니다.</p>;
  }
  return (
    <ul className="space-y-1.5">
      {items.slice(0, 4).map((e) => (
        <li key={e.id} className="rounded-md bg-white px-2.5 py-1.5 text-[11px] leading-relaxed text-slate-600">
          <span className="mr-1.5 rounded bg-[#eef2ff] px-1.5 py-0.5 text-[10px] font-semibold text-[#4f46e5]">
            {e.type === "turn" ? (e.role === "user" ? "내 발화" : "에이전트") : e.type === "feedback" ? "상품 반응" : "상품 특성"}
          </span>
          {e.type === "feedback" && e.productTitle ? (
            <span>
              <b>{e.productTitle}</b>
              {e.feedbackType ? ` — ${e.feedbackType === "like" ? "좋아요" : e.feedbackType === "dislike" ? "싫어요" : e.feedbackType}` : ""}
              {e.quote ? ` · “${e.quote}”` : ""}
            </span>
          ) : (
            <span>{e.quote || "(내용 없음)"}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function CriterionCheckModal({
  candidates,
  onSubmit,
  submitting = false,
}: {
  candidates: CriterionCandidate[];
  onSubmit: (items: CriterionAnswer[]) => void;
  submitting?: boolean;
}) {
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>({});
  const [showErrors, setShowErrors] = useState(false);

  const current = candidates[idx];
  const currentAnswers = answers[current?.topic.id ?? ""] ?? {};
  const missing = useMemo(
    () => CRITERION_CHECK.filter((q) => !currentAnswers[q.id]).map((q) => q.id),
    [currentAnswers],
  );
  const isLast = idx === candidates.length - 1;

  const setAnswer = (qid: string, v: string) =>
    setAnswers((p) => ({ ...p, [current.topic.id]: { ...(p[current.topic.id] ?? {}), [qid]: v } }));

  const next = () => {
    if (missing.length > 0) { setShowErrors(true); return; }
    setShowErrors(false);
    if (!isLast) { setIdx((i) => i + 1); return; }

    const items: CriterionAnswer[] = candidates.map((c) => {
      const a = answers[c.topic.id] ?? {};
      const out: CriterionAnswer = { topicId: c.topic.id, topicLabel: c.topic.label };
      for (const q of CRITERION_CHECK) {
        const raw = a[q.id];
        if (raw === undefined) continue;
        const field = FIELD[q.id];
        if (field === "importance") out.importance = Number(raw);
        else if (field === "formation") out.formation = FORMATION_CODE[raw] ?? raw;
        else if (field === "matches") out.matches = raw;
        else if (field === "evidenceSupports") out.evidenceSupports = raw;
      }
      return out;
    });
    onSubmit(items);
  };

  if (!current) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4">
      <div className="card flex max-h-[92dvh] w-full max-w-lg flex-col overflow-hidden">
        <div className="border-b border-[#f0f2f4] px-5 py-4 sm:px-6">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-[#191919]">추론한 기준이 맞는지 확인해 주세요</h2>
            <span className="tabular-nums text-xs text-slate-400">
              {idx + 1} / {candidates.length}
            </span>
          </div>
          <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-[#f0f2f4]">
            <div
              className="h-full rounded-full bg-[#4f46e5] transition-[width] duration-300"
              style={{ width: `${((idx + (missing.length ? 0 : 1)) / candidates.length) * 100}%` }}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 sm:px-6">
          <div className="rounded-lg border border-[#e4e8eb] bg-[#f8f9fa] p-3">
            <div className="text-[11px] font-semibold text-[#9aa0a6]">에이전트가 추론한 기준</div>
            <div className="mt-1 text-sm font-bold leading-relaxed text-[#191919]">
              {current.topic.label}
            </div>
            <div className="mt-2.5 text-[11px] font-semibold text-[#9aa0a6]">이렇게 판단한 근거</div>
            <div className="mt-1">
              <EvidenceList items={current.evidence} />
            </div>
          </div>

          <div className="mt-4 space-y-3.5">
            {CRITERION_CHECK.map((q) => (
              <QuestionRow
                key={q.id}
                q={q}
                value={currentAnswers[q.id]}
                onChange={(v) => setAnswer(q.id, v)}
                invalid={showErrors && missing.includes(q.id)}
              />
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[#f0f2f4] px-5 py-3 sm:px-6">
          <div className="text-xs">
            {showErrors && missing.length > 0 ? (
              <span className="font-semibold text-rose-600">
                <span className="tabular-nums">{missing.length}</span>개 문항이 남았어요.
              </span>
            ) : idx > 0 ? (
              <button
                onClick={() => { setShowErrors(false); setIdx((i) => i - 1); }}
                disabled={submitting}
                className="text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline disabled:opacity-40"
              >
                이전 기준
              </button>
            ) : null}
          </div>
          <button onClick={next} disabled={submitting} className="btn btn-primary px-5 py-2">
            {submitting ? "제출 중…" : isLast ? "제출하고 마치기" : "다음 기준"}
          </button>
        </div>
      </div>
    </div>
  );
}
