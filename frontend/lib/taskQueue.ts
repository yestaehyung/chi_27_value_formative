// 본실험 과제 큐 — 참가자가 친숙 2 + 비친숙 2로 고른 카테고리 4개를 순서대로 진행시킨다.
//
// 왜 큐가 필요한가: "무엇을 몇 번째로 하는가"가 참가자 자율이면 자기선택 편향(쉬워
// 보이는 것부터 고름)이 생긴다. 순서는 설계가 정한다.
//
// 순서는 **(친숙 1 → 비친숙 1) 묶음 × 2**다 (2026-08-17 연구자 결정; 이전의 완전
// 무작위 셔플을 대체). 친숙-비친숙이 인접 쌍으로 반복되어 참가자 안에서 직접 대비가
// 생기고, 각 측 안에서 어떤 카테고리가 먼저 올지는 무작위로 남긴다. 친숙이 항상
// 먼저라는 고정 순서 효과는 설계가 감수하는 트레이드오프(친숙 워밍업).
//
// 저장 위치는 sessionStorage다. 서버(Participant)에 두는 편이 견고하지만, 분석에 필요한
// 정보(카테고리·친숙도·순서)는 세션마다 meta.familiarity + startedAt으로 서버에 남는다.
// 큐는 "다음에 무엇을 열까"라는 진행 상태일 뿐이라 클라이언트에 둔다.

import type { Familiarity } from "@/lib/types";

export type PlannedTask = { category: string; familiarity: Familiarity };

const KEY = "vc:taskQueue";

type StoredQueue = {
  participantId: string;
  tasks: PlannedTask[];
  done: number;
  advancedSessions?: string[]; // 큐를 전진시킨 세션 id — 재방문/리마운트 이중 전진 방지
};

function shuffled(items: string[]): string[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/** (친숙 1 → 비친숙 1) 묶음 × 2 — 각 측 안의 카테고리 순서만 무작위(Fisher–Yates). */
export function pairedOrder(familiar: string[], unfamiliar: string[]): PlannedTask[] {
  const f = shuffled(familiar);
  const u = shuffled(unfamiliar);
  const out: PlannedTask[] = [];
  for (let i = 0; i < Math.max(f.length, u.length); i++) {
    if (f[i]) out.push({ category: f[i], familiarity: "familiar" });
    if (u[i]) out.push({ category: u[i], familiarity: "unfamiliar" });
  }
  return out;
}

export function saveQueue(participantId: string, tasks: PlannedTask[]): void {
  const q: StoredQueue = { participantId, tasks, done: 0 };
  sessionStorage.setItem(KEY, JSON.stringify(q));
}

function read(): StoredQueue | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as StoredQueue) : null;
  } catch {
    return null;
  }
}

/** 큐의 전체 과제 목록 (지식 행렬 화면이 4개 카테고리를 읽는다). 큐가 없으면 []. */
export function queuedTasks(participantId?: string): PlannedTask[] {
  const q = read();
  if (!q) return [];
  if (participantId && q.participantId !== participantId) return [];
  return q.tasks;
}

/** 아직 시작하지 않은 다음 과제. 큐가 없거나 다 끝났으면 null. */
export function nextTask(participantId?: string): PlannedTask | null {
  const q = read();
  if (!q) return null;
  // 다른 참가자의 큐가 남아 있으면 무시한다 (같은 브라우저로 연속 진행하는 랩 세션).
  if (participantId && q.participantId !== participantId) return null;
  return q.tasks[q.done] ?? null;
}

/** 한 과제를 마쳤다고 표시하고, 남은 개수를 돌려준다.
 * sessionId를 주면 같은 세션은 한 번만 전진한다(완료 화면 재방문·리마운트 안전). */
export function completeTask(sessionId?: string): number {
  const q = read();
  if (!q) return 0;
  const advanced = q.advancedSessions ?? [];
  if (sessionId && advanced.includes(sessionId)) return q.tasks.length - q.done;
  if (sessionId) q.advancedSessions = [...advanced, sessionId];
  q.done = Math.min(q.done + 1, q.tasks.length);
  sessionStorage.setItem(KEY, JSON.stringify(q));
  return q.tasks.length - q.done;
}

/** 진행 표시용 — {완료, 전체}. 큐가 없으면 null. */
export function queueProgress(): { done: number; total: number } | null {
  const q = read();
  return q ? { done: q.done, total: q.tasks.length } : null;
}

export function clearQueue(): void {
  sessionStorage.removeItem(KEY);
}
