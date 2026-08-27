// Thin API client — all calls proxied via Next.js rewrite to the FastAPI backend.
import type { CategoryOption, Familiarity } from "@/lib/types";

// 연구자 키 (스터디 분리, 2026-07-02): 라이브 백엔드의 research/exports API는
// X-Research-Key를 요구한다. 로컬 프론트를 라이브 백엔드에 물려 모니터링할 때
// frontend/.env.local 에 NEXT_PUBLIC_RESEARCH_KEY를 넣으면 모든 요청에 실린다
// (키 없는 로컬 백엔드는 이 헤더를 무시하므로 로컬 개발에는 영향 없음).
const RESEARCH_KEY = process.env.NEXT_PUBLIC_RESEARCH_KEY;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(RESEARCH_KEY ? { "X-Research-Key": RESEARCH_KEY } : {}),
    },
    cache: "no-store",
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createSession: (
    scenarioId: string,
    // 기본은 **미지정** — 서버가 균형 배정한다. 예전에는 "correctable"을 하드코딩해
    // 보냈는데, 서버가 그걸 무시하고 배정하고 있어서 실제 조건과 어긋나 보였다.
    // 값을 주는 경우는 테스트·데모가 조건을 고정할 때뿐이다.
    studyCondition?: "baseline1" | "baseline2" | "ours",
    custom?: { title?: string; context?: string },
    participantId?: string,
    // "demo" = 상품 풀 확인용. 조건 배정을 받지 않고 조건 균형 집계에도 안 잡힌다.
    mode: "manual" | "demo" = "manual",
  ) =>
    request<{ sessionId: string }>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        mode, scenarioId, studyCondition,
        customTitle: custom?.title, customContext: custom?.context,
        participantId,
      }),
    }),

  // 데모용 상품 풀 요약 (카테고리별 개수) — "새 상품이 실제로 들어왔나"를 눈으로 확인
  productPoolSummary: () => request<any>("/api/meta/product-pool"),

  participants: () => request<any>("/api/research/participants"),
  participantSurvey: (id: string) => request<any>(`/api/research/participants/${id}/survey`),

  getSession: (sessionId: string) => request<any>(`/api/sessions/${sessionId}`),

  // ours-v3: 칩 확인 게이트 통과 — 확인된 기준으로 추천을 수행한다
  proceedRecommend: (sessionId: string) =>
    request<any>(`/api/sessions/${sessionId}/proceed-recommend`, { method: "POST" }),

  postTurn: (sessionId: string, content: string, clientRequestId?: string, inputSource?: "suggestion" | "typed") =>
    request<any>(`/api/sessions/${sessionId}/turns`, {
      method: "POST",
      body: JSON.stringify({ role: "user", content, clientRequestId, inputSource }),
    }),

  // 응답 없이 남은 사용자 턴(pending/failed)을 같은 턴으로 재처리 — 새 턴 없음 (2026-08-18)
  retryTurn: (sessionId: string, turnId: string) =>
    request<any>(`/api/sessions/${sessionId}/turns/${turnId}/retry`, { method: "POST" }),

  // 입력창 위 답변 칩 — 턴 응답과 분리 (백엔드가 크리티컬 패스에서 뺌, 2026-08-14).
  // 턴/피드백 응답 표시 직후 호출한다. forTurnId로 낡은 응답을 걸러낸다.
  fetchReplySuggestions: (sessionId: string) =>
    request<{ suggestions: string[]; forTurnId: string | null }>(
      `/api/sessions/${sessionId}/reply-suggestions`,
      { method: "POST" },
    ),

  postFeedback: (
    sessionId: string,
    productId: string,
    type: string,
    reasonCode?: string,
    reasonText?: string
  ) =>
    request<any>(`/api/sessions/${sessionId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ productId, type, reasonCode, reasonText }),
    }),

  resolveConflict: (conflictId: string, optionId: string, manualText?: string) =>
    request<any>(`/api/conflicts/${conflictId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ optionId, manualText }),
    }),

  chipAction: (topicId: string, action: string, manualLabel?: string, deferRecommend?: boolean) =>
    request<any>(`/api/preferences/chips/${topicId}/action`, {
      method: "POST",
      body: JSON.stringify({ action, manualLabel, deferRecommend }),
    }),

  // 디바운스된 수정 묶음에 대한 재추천 1회 (corrections는 표시용 요약)
  refreshRecommendation: (sessionId: string, corrections: { action: string; criterionLabel?: string }[]) =>
    request<any>(`/api/preferences/sessions/${sessionId}/refresh-recommendation`, {
      method: "POST",
      body: JSON.stringify({ corrections }),
    }),

  topicEvidence: (topicId: string) =>
    request<any>(`/api/preferences/topics/${topicId}/evidence`),

  scenarios: () => request<any>("/api/meta/scenarios"),
  personas: () => request<any>("/api/meta/personas"),

  /** 참가자가 고를 수 있는 쇼핑 카테고리 — DB에 상품이 실제로 있는 것만 온다. */
  categories: () =>
    request<{ categories: CategoryOption[] }>("/api/meta/categories"),

  /** 본실험 세션 생성 — 시나리오 대신 카테고리 + 참가자가 매긴 친숙도(2+2)로 연다. */
  createCategorySession: (category: string, familiarity: Familiarity, participantId?: string) =>
    request<{ sessionId: string }>("/api/sessions", {
      method: "POST",
      // studyCondition은 보내지 않는다 — 서버가 참가자 단위로 균형 배정한다.
      body: JSON.stringify({ mode: "manual", category, familiarity, participantId }),
    }),

  runSimulation: (scenarioId: string, userAgentProfileId: string, maxTurns = 8) =>
    request<any>("/api/simulations/run", {
      method: "POST",
      body: JSON.stringify({ scenarioId, userAgentProfileId, maxTurns, autoResolveConflicts: true }),
    }),

  llmCalls: (sessionId: string, task?: string) =>
    request<any[]>(`/api/research/sessions/${sessionId}/llm-calls${task ? `?task=${task}` : ""}`),

  researchSessions: (mode?: string) =>
    request<any>(`/api/research/sessions${mode ? `?mode=${mode}` : ""}`),
  sessionReplay: (sessionId: string) => request<any>(`/api/research/sessions/${sessionId}/replay`),
  pairs: (sessionId?: string) =>
    request<any>(`/api/research/pairs${sessionId ? `?sessionId=${sessionId}` : ""}`),
  runPairMining: (minPairs = 5) =>
    request<any>("/api/research/pair-mining/run", {
      method: "POST",
      body: JSON.stringify({ minPairs }),
    }),
  features: () => request<any>("/api/research/features"),
  concepts: () => request<any>("/api/research/concepts"),
  smeInsights: () => request<any>("/api/research/sme-insights"),
  valueProfile: (sessionId: string) =>
    request<any>(`/api/research/sessions/${sessionId}/value-profile`),
  latentYield: (sessionId?: string) =>
    request<any>(`/api/research/metrics/latent-yield${sessionId ? `?sessionId=${sessionId}` : ""}`),
  setFeatureStatus: (featureId: string, status: string) =>
    request<any>(`/api/research/features/${featureId}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  runExport: () => request<any>("/api/exports/run", { method: "POST" }),

  // Formative study (FS1) 계측
  addMarker: (sessionId: string, tag: string, note?: string) =>
    request<any>(`/api/study/sessions/${sessionId}/markers`, {
      method: "POST",
      body: JSON.stringify({ tag, note }),
    }),
  logInspect: (sessionId: string, topicId: string) =>
    request<any>(`/api/study/sessions/${sessionId}/inspect`, {
      method: "POST",
      body: JSON.stringify({ topicId }),
    }),
  setGroundTruth: (sessionId: string, items: string[]) =>
    request<any>(`/api/study/sessions/${sessionId}/ground-truth`, {
      method: "PUT",
      body: JSON.stringify({ items }),
    }),
  gap: (sessionId: string) => request<any>(`/api/study/sessions/${sessionId}/gap`),

  // 세션 종료 사후 설문 (이해·만족·신뢰 + 확장) — sessions.meta.postSurvey
  /** ③ 결정 상태 확정 (4범주) — 사후 설문·기준 감사 전에 잠근다 (2026-08-13). */
  submitFinalChoice: (sessionId: string, payload: {
    status: "final" | "shortlist" | "explore_more" | "none_suitable";
    productId?: string | null;
    shortlistIds?: string[];
    noneReason?: string;
    fitReason?: string;          // 선택이 과제 상황에 맞는 이유 (2026-08-26)
    earlyFinish?: boolean;       // 추천 2라운드 전 종료 (소프트 게이트 기록)
    roundsAtFinish?: number;
  }) =>
    request<{ ok: boolean }>(`/api/study/sessions/${sessionId}/final-choice`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  /** 제품군별 지식 행렬 (카테고리 확정 직후 1회) — Participant.survey.productKnowledge */
  submitKnowledgeSurvey: (
    participantId: string,
    answers: Record<string, string>,
    scores: Record<string, number>,
    categories: string[],
  ) =>
    request<{ ok: boolean }>(`/api/study/participants/${participantId}/knowledge-survey`, {
      method: "PUT",
      body: JSON.stringify({ answers, scores, categories }),
    }),

  submitPostSurvey: (sessionId: string, answers: Record<string, unknown>, profile: Record<string, number>) =>
    request<{ ok: boolean }>(`/api/study/sessions/${sessionId}/post-survey`, {
      method: "PUT",
      body: JSON.stringify({ answers, profile }),
    }),

  // 본실험 과제 계획(4과제)의 서버 저장 + 서버 기준 진행 조회 — sessionStorage 큐는 캐시일 뿐
  saveTaskPlan: (participantId: string, tasks: { category: string; familiarity: Familiarity }[], extras?: Record<string, unknown>) =>
    request<{ ok: boolean; count: number }>(`/api/study/participants/${participantId}/task-plan`, {
      method: "PUT",
      body: JSON.stringify({ tasks, ...extras }),
    }),
  getTaskProgress: (participantId: string) =>
    request<{
      tasks: { category: string; familiarity: Familiarity; done: boolean }[];
      remaining: number;
      knowledgeDone?: string[];
      next: { category: string; familiarity: Familiarity } | null;
    }>(`/api/study/participants/${participantId}/task-progress`),

  // FS1 사전 설문 → 참가자 생성(설문 저장). 본실험 사전 설문도 같은 채널을 쓴다(문항 id만 다름).
  submitSurvey: (
    answers: Record<string, unknown>,
    profile: Record<string, number>,
    label?: string,
    prolific?: { pid?: string; studyId?: string; sessionId?: string },
  ) =>
    request<{ participantId: string; label: string; studyCondition?: string }>("/api/study/survey", {
      method: "POST",
      body: JSON.stringify({ answers, profile, label, prolific }),
    }),

  // ── 본실험(메인 스터디) 설문 ─────────────────────────────────────────
  // 과제 직전 — 상품군 지식·경험 + 구매 기준 명확성(사전). 직후 응답과 짝지어 Δ를 낸다.
  submitPreTaskSurvey: (
    sessionId: string,
    answers: Record<string, unknown>,
    profile: Record<string, number>,
    category?: string,
  ) =>
    request<{ ok: boolean }>(`/api/study/sessions/${sessionId}/pre-task-survey`, {
      method: "PUT",
      body: JSON.stringify({ answers, profile, category }),
    }),

  // 전체 과제 종료 후 — 참가자 단위 회고(해석 이해가능성·근거·수정 사용성)
  submitPostStudySurvey: (
    participantId: string,
    answers: Record<string, unknown>,
    profile: Record<string, number>,
  ) =>
    request<{ ok: boolean }>(`/api/study/participants/${participantId}/post-study-survey`, {
      method: "PUT",
      body: JSON.stringify({ answers, profile }),
    }),

  // 기준별 검증에 제시할 주요 기준 3–5개 + 각 기준의 근거
  criterionCandidates: (sessionId: string, limit = 5) =>
    request<any>(`/api/study/sessions/${sessionId}/criterion-candidates?limit=${limit}`),

  /** 기준 감사 저장 — B파트(items) + A파트 자기 기준(ownCriteria) + 누락 기준 */
  submitCriterionValidations: (
    sessionId: string,
    items: unknown[],
    ownCriteria: { label: string; necessity?: string; influence?: string }[] = [],
    missingCriteria: string[] = [],
  ) =>
    request<{ saved: number }>(`/api/study/sessions/${sessionId}/criterion-validations`, {
      method: "POST",
      body: JSON.stringify({ items, ownCriteria, missingCriteria }),
    }),

  // RIG — Relational Intention Graph (메타경로 기반 예측·설명)
  rigTheoryTransitions: () => request<any>("/api/research/rig/theory-transitions"),
  rigMetaPath: (sessionId: string) => request<any>(`/api/research/sessions/${sessionId}/meta-path`),
  rigPredict: (sessionId: string) => request<any>(`/api/research/sessions/${sessionId}/predict`),
  participantSpec: (participantId: string) => request<any>(`/api/research/participants/${participantId}/spec`),

  // 합성(LLM user agent) 대화 검수 뷰어 (읽기 전용)
  synthesisRuns: () => request<any>("/api/synthesis/runs"),
  synthesisRun: (personaId: string) => request<any>(`/api/synthesis/runs/${personaId}`),

  // 온디맨드 직접 실행 — 선택한 persona로 LLM 합성을 백그라운드 시작 + 진행 폴링
  runSynthesis: (personaId: string, scenarioId: string, maxTurns = 6,
                 model = "deepseek-v4-flash", thinking = "off") =>
    request<any>("/api/synthesis/run", {
      method: "POST",
      body: JSON.stringify({ personaId, scenarioId, maxTurns, model, thinking }),
    }),
  synthesisRunStatus: (personaId: string) =>
    request<{ running: boolean; sessionId: string | null }>(
      `/api/synthesis/run-status?personaId=${encodeURIComponent(personaId)}`
    ),
  stopSynthesis: (personaId: string) =>
    request<any>("/api/synthesis/stop", { method: "POST", body: JSON.stringify({ personaId }) }),

  // PSCon CRS 실대화 데이터셋 (읽기 전용 시각화)
  psconConversations: () => request<any>("/api/pscon/conversations"),
  psconConversation: (convId: string | number) => request<any>(`/api/pscon/conversations/${convId}`),
  psconTimeline: (convId: string | number) => request<any>(`/api/pscon/conversations/${convId}/timeline`),
  psconEvidence: (convId: string | number) => request<any>(`/api/pscon/conversations/${convId}/evidence`),
};
