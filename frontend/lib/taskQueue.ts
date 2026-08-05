// 본실험 과제 큐 (2026-08-06) — 참가자가 고른 카테고리 4개를 순서대로 진행시킨다.
//
// 왜 큐가 필요한가: 시나리오를 폐기하고 카테고리 선택으로 바꾸면서, "무엇을 몇 번째로
// 하는가"가 참가자 자율이 아니라 **설계가 정하는 값**이 됐다. 매번 고르게 두면 자기선택
// 편향(쉬워 보이는 것부터 고름)이 친숙도 요인과 교락된다.
//
// 저장 위치는 sessionStorage다. 서버(Participant)에 두는 편이 견고하지만, 과제 순서는
// 세션마다 `session.meta.familiarity`로 이미 남으므로 분석에 필요한 정보는 서버에 있다.
// 큐는 "다음에 무엇을 열까"라는 진행 상태일 뿐이라 클라이언트에 둔다.

import type { Familiarity } from "@/lib/types";

export type PlannedTask = { category: string; familiarity: Familiarity };

const KEY = "vc:taskQueue";

type StoredQueue = { participantId: string; tasks: PlannedTask[]; done: number };

/** 친숙/비친숙을 번갈아 배치한다 — 앞뒤 순서 효과가 한쪽 친숙도에 몰리지 않게.
 *
 * 시작 유형은 참가자 id 해시로 정한다(무작위가 아니라 결정적). 참가자 절반은
 * 친숙한 것부터, 절반은 낯선 것부터 시작하므로 순서 효과가 두 수준에 균형 있게 걸린다.
 * 완전한 카운터밸런싱(4! = 24셀)은 표본이 감당 못 하므로, 통제해야 할 축(친숙도 × 순서)
 * 하나만 잡는 절충이다.
 */
export function interleave(
  familiar: string[],
  unfamiliar: string[],
  participantId: string,
): PlannedTask[] {
  const hash = Array.from(participantId).reduce((a, c) => a + c.charCodeAt(0), 0);
  const familiarFirst = hash % 2 === 0;
  const a: PlannedTask[] = familiar.map((c) => ({ category: c, familiarity: "familiar" }));
  const b: PlannedTask[] = unfamiliar.map((c) => ({ category: c, familiarity: "unfamiliar" }));
  const [first, second] = familiarFirst ? [a, b] : [b, a];
  const out: PlannedTask[] = [];
  for (let i = 0; i < Math.max(first.length, second.length); i++) {
    if (first[i]) out.push(first[i]);
    if (second[i]) out.push(second[i]);
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
