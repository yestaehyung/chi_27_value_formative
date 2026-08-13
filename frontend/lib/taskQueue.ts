// 본실험 과제 큐 (2026-08-06, 2026-08-08 순서 무작위화) — 참가자가 친숙 2 + 비친숙 2로
// 고른 카테고리 4개를 순서대로 진행시킨다.
//
// 왜 큐가 필요한가: "무엇을 몇 번째로 하는가"가 참가자 자율이면 자기선택 편향(쉬워
// 보이는 것부터 고름)이 생긴다. 순서는 설계가 정한다.
//
// 순서는 친숙/비친숙 interleave(교차 배치)가 아니라 **완전 무작위 셔플**이다 (2026-08-08):
// 참가자마다 다른 순서가 나와 순서 효과(피로·학습)가 참가자 간에 상쇄된다. 친숙도
// 이분법(2+2 선택)은 within-subjects 요인으로 유지되어 과제마다 세션에 기록되고,
// 과제 직전 설문(TPRE_K1/K2)이 그 조작 점검(연속 측정) 역할을 한다.
//
// 저장 위치는 sessionStorage다. 서버(Participant)에 두는 편이 견고하지만, 분석에 필요한
// 정보(카테고리·친숙도·순서)는 세션마다 meta.familiarity + startedAt으로 서버에 남는다.
// 큐는 "다음에 무엇을 열까"라는 진행 상태일 뿐이라 클라이언트에 둔다.

import type { Familiarity } from "@/lib/types";

export type PlannedTask = { category: string; familiarity: Familiarity };

const KEY = "vc:taskQueue";

type StoredQueue = { participantId: string; tasks: PlannedTask[]; done: number };

/** 친숙 2 + 비친숙 2를 합쳐 무작위 순서로 정한다 (Fisher–Yates). */
export function randomOrder(familiar: string[], unfamiliar: string[]): PlannedTask[] {
  const arr: PlannedTask[] = [
    ...familiar.map((c): PlannedTask => ({ category: c, familiarity: "familiar" })),
    ...unfamiliar.map((c): PlannedTask => ({ category: c, familiarity: "unfamiliar" })),
  ];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
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

/** 한 과제를 마쳤다고 표시하고, 남은 개수를 돌려준다. */
export function completeTask(): number {
  const q = read();
  if (!q) return 0;
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
