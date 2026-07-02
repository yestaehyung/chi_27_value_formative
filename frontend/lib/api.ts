// Thin API client — all calls proxied via Next.js rewrite to the FastAPI backend.

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
    studyCondition = "correctable",
    custom?: { title?: string; context?: string },
    participantId?: string
  ) =>
    request<{ sessionId: string }>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        mode: "manual", scenarioId, studyCondition,
        customTitle: custom?.title, customContext: custom?.context,
        participantId,
      }),
    }),

  participants: () => request<any>("/api/research/participants"),
  participantSurvey: (id: string) => request<any>(`/api/research/participants/${id}/survey`),

  getSession: (sessionId: string) => request<any>(`/api/sessions/${sessionId}`),

  postTurn: (sessionId: string, content: string) =>
    request<any>(`/api/sessions/${sessionId}/turns`, {
      method: "POST",
      body: JSON.stringify({ role: "user", content }),
    }),

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

  chipAction: (topicId: string, action: string, manualLabel?: string) =>
    request<any>(`/api/preferences/chips/${topicId}/action`, {
      method: "POST",
      body: JSON.stringify({ action, manualLabel }),
    }),

  topicEvidence: (topicId: string) =>
    request<any>(`/api/preferences/topics/${topicId}/evidence`),

  scenarios: () => request<any>("/api/meta/scenarios"),
  personas: () => request<any>("/api/meta/personas"),

  runSimulation: (scenarioId: string, userAgentProfileId: string, maxTurns = 8) =>
    request<any>("/api/simulations/run", {
      method: "POST",
      body: JSON.stringify({ scenarioId, userAgentProfileId, maxTurns, autoResolveConflicts: true }),
    }),

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

  // FS1 사전 설문 → 참가자 생성(설문 저장)
  submitSurvey: (answers: Record<string, unknown>, profile: Record<string, number>, label?: string) =>
    request<{ participantId: string; label: string }>("/api/study/survey", {
      method: "POST",
      body: JSON.stringify({ answers, profile, label }),
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
