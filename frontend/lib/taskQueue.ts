// 본실험 과제 큐 (2026-08-06, 2026-08-08 무작위 순서로 개편) — 참가자가 고른
// 카테고리 4개를 순서대로 진행시킨다.
//
// 왜 큐가 필요한가: "무엇을 몇 번째로 하는가"가 참가자 자율이면 자기선택 편향(쉬워
// 보이는 것부터 고름)이 생긴다. 순서는 설계가 정한다 — 무작위 셔플로 순서 효과를
// 참가자 간에 상쇄한다.
//
// 친숙/비친숙 interleave는 폐기했다 (2026-08-08): 친숙도는 이제 선택 시점의 이분법
// 자기신고가 아니라 과제 직전 설문(TPRE_K1/K2 "나는 {카테고리}에 대해 잘 알고 있다")
// 으로 측정하는 값이라, 순서를 친숙도로 짤 근거 자체가 사라졌다.
//
// 저장 위치는 sessionStorage다. 서버(Participant)에 두는 편이 견고하지만, 과제 순서는
// 세션 생성 시각으로 서버에 이미 남으므로 분석에 필요한 정보는 서버에 있다.
// 큐는 "다음에 무엇을 열까"라는 진행 상태일 뿐이라 클라이언트에 둔다.

export type PlannedTask = { category: string };

const KEY = "vc:taskQueue";

type StoredQueue = { participantId: string; tasks: PlannedTask[]; done: number };

/** 과제 순서를 무작위로 정한다 (Fisher–Yates). 참가자마다 다른 순서가 나와
 * 순서 효과(피로·학습)가 특정 카테고리에 몰리지 않는다. */
export function randomOrder(categories: string[]): PlannedTask[] {
  const arr = [...categories];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.map((category) => ({ category }));
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
