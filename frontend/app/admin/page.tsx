"use client";

// 관리자 대시보드 (2026-08-16) — 연구자 1인용, 한국어.
// 인증: 비밀번호 = 백엔드 VC_RESEARCH_KEY. 입력값을 sessionStorage에 두고 모든 요청에
// X-Research-Key 헤더로 붙인다 — 검증은 백엔드 research_gate가 한다(프론트에 키를 굽지 않음).
// study 모드 미들웨어 matcher에 /admin이 없으므로 라이브에서도 접근 가능하다.
import { Fragment, useCallback, useEffect, useState } from "react";

const KEY_STORAGE = "vc:adminKey";

type Balance = {
  conditions: { condition: string; assigned: number; started: number }[];
  totalStarted: number;
  dropped: number;
};
type Participant = {
  id: string;
  label: string | null;
  studyCondition: string | null;
  hasSurvey: boolean;
  sessionCount: number;
  createdAt: string | null;
};
type SessionRow = {
  id: string;
  participantId: string | null;
  status: string;
  mode: string;
  startedAt?: string | null;
  turnCount: number;
  feedbackCount: number;
  topicCount: number;
  metadata?: { category?: string; studyCondition?: string; familiarity?: string; finalChoice?: { status?: string } } | null;
};
type Turn = { role: string; content: string; agentAction?: string | null };
type SessionDetail = {
  turns: Turn[];
  feedback: { type: string; reasonText?: string | null; productId?: string | null }[];
  impressions: { productId: string; recommendationReason?: string | null; product?: { title?: string; price?: number } }[];
};

const COND_LABEL: Record<string, string> = {
  baseline1: "베이스라인1 (추론 없음)",
  baseline2: "베이스라인2 (추론 숨김)",
  ours: "제안 시스템 (ours)",
};

function isTestId(id: string | null | undefined): boolean {
  const v = (id ?? "").toLowerCase();
  return v.startsWith("test") || v.startsWith("verify");
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("ko-KR", {
      month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function AdminPage() {
  const [key, setKey] = useState<string | null>(null);
  const [pwInput, setPwInput] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const [balance, setBalance] = useState<Balance | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [openSession, setOpenSession] = useState<string | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [hideTest, setHideTest] = useState(false);

  // 실험 조건 배정 모드 — null이면 자동 균형, 조건 슬러그면 신규 참가자 전원 그 조건으로
  const [forcedCondition, setForcedCondition] = useState<string | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  // 조건 지정 테스트 세션 생성 — 서버의 조건 배정 경로 ②(요청 명시, 신규 참가자)를 쓴다.
  // 조건은 참가자 단위로 고정되므로 조건마다 새 test_admin_* 참가자를 만든다.
  const [categories, setCategories] = useState<string[]>([]);
  const [newCond, setNewCond] = useState<"ours" | "baseline1" | "baseline2">("ours");
  const [newCat, setNewCat] = useState("");
  const [newFam, setNewFam] = useState<"familiar" | "unfamiliar">("familiar");
  const [creating, setCreating] = useState(false);
  const [createdLinks, setCreatedLinks] = useState<{ url: string; label: string }[]>([]);

  const fetchWithKey = useCallback(async (path: string, k: string) => {
    const res = await fetch(path, { headers: { "X-Research-Key": k } });
    if (res.status === 401 || res.status === 403) throw new Error("unauthorized");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }, []);

  const loadAll = useCallback(async (k: string) => {
    setLoadError(null);
    try {
      const [bal, parts, sess, cfg] = await Promise.all([
        fetchWithKey("/api/research/condition-balance", k),
        fetchWithKey("/api/research/participants", k),
        fetchWithKey("/api/research/sessions?mode=manual", k),
        fetchWithKey("/api/research/study-config", k),
      ]);
      setBalance(bal);
      setForcedCondition(cfg.forcedCondition ?? null);
      const plist: Participant[] = Array.isArray(parts) ? parts : parts.participants ?? [];
      plist.sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
      setParticipants(plist);
      setSessions(sess.sessions ?? []);
    } catch (e) {
      if ((e as Error).message === "unauthorized") {
        sessionStorage.removeItem(KEY_STORAGE);
        setKey(null);
        setAuthError("비밀번호가 올바르지 않아요. 다시 입력해 주세요.");
      } else {
        setLoadError("데이터를 불러오지 못했어요. 새로고침을 눌러 다시 시도해 주세요.");
      }
    }
  }, [fetchWithKey]);

  useEffect(() => {
    const saved = sessionStorage.getItem(KEY_STORAGE);
    if (saved) {
      setKey(saved);
      void loadAll(saved);
    }
    void fetch("/api/meta/categories")
      .then((r) => r.json())
      .then((d) => {
        const cats = (d.categories ?? []).map((c: { category: string }) => c.category);
        setCategories(cats);
        if (cats.length) setNewCat((prev) => prev || cats[0]);
      })
      .catch(() => {});
  }, [loadAll]);

  const createTestSession = async () => {
    if (!newCat) return;
    setCreating(true);
    try {
      const pid = `test_admin_${newCond}_${Date.now().toString(36).slice(-5)}`;
      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "manual", category: newCat, familiarity: newFam,
          participantId: pid, studyCondition: newCond,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setCreatedLinks((prev) => [
        { url: `${window.location.origin}/study/session/${d.sessionId}`, label: `${newCat} · ${newCond} · ${newFam}` },
        ...prev,
      ]);
      void loadAll(key!);
    } catch {
      setLoadError("세션 생성에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setCreating(false);
    }
  };

  const submitPassword = async () => {
    const k = pwInput.trim();
    if (!k) return;
    setChecking(true);
    setAuthError(null);
    try {
      await fetchWithKey("/api/research/condition-balance", k);
      sessionStorage.setItem(KEY_STORAGE, k);
      setKey(k);
      setPwInput("");
      void loadAll(k);
    } catch {
      setAuthError("비밀번호가 올바르지 않아요.");
    } finally {
      setChecking(false);
    }
  };

  const saveForcedCondition = async (value: string | null) => {
    if (!key) return;
    setSavingConfig(true);
    try {
      const res = await fetch("/api/research/study-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Research-Key": key },
        body: JSON.stringify({ forcedCondition: value }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setForcedCondition(value);
    } catch {
      setLoadError("조건 설정 저장에 실패했어요.");
    } finally {
      setSavingConfig(false);
    }
  };

  const toggleSession = async (sid: string) => {
    if (openSession === sid) {
      setOpenSession(null);
      setDetail(null);
      return;
    }
    setOpenSession(sid);
    setDetail(null);
    try {
      const res = await fetch(`/api/sessions/${sid}`);
      if (res.ok) setDetail(await res.json());
    } catch {
      /* 상세 로드 실패는 행 접기만으로 충분 */
    }
  };

  // ---------- 비밀번호 게이트 ----------
  if (!key) {
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
        <h1 className="mb-1 text-xl font-bold text-gray-900">관리자 페이지</h1>
        <p className="mb-6 text-sm text-gray-500">연구자 전용입니다. 비밀번호를 입력해 주세요.</p>
        <input
          type="password"
          value={pwInput}
          onChange={(e) => setPwInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void submitPassword(); }}
          placeholder="비밀번호"
          className="mb-3 w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-[#4F46E5] focus:outline-none"
          autoFocus
        />
        {authError && <p className="mb-3 text-sm text-red-600">{authError}</p>}
        <button
          onClick={() => void submitPassword()}
          disabled={checking || !pwInput.trim()}
          className="w-full rounded-lg bg-[#4F46E5] py-2.5 text-sm font-semibold text-white disabled:opacity-40"
        >
          {checking ? "확인 중…" : "입장"}
        </button>
      </main>
    );
  }

  // ---------- 대시보드 ----------
  const shownParticipants = hideTest ? participants.filter((p) => !isTestId(p.id)) : participants;
  const shownSessions = hideTest ? sessions.filter((s) => !isTestId(s.participantId)) : sessions;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">관리자 대시보드</h1>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-1.5 text-gray-600">
            <input type="checkbox" checked={hideTest} onChange={(e) => setHideTest(e.target.checked)} />
            테스트 계정 숨기기
          </label>
          <button onClick={() => void loadAll(key)} className="rounded-lg border border-gray-300 px-3 py-1.5 hover:bg-gray-50">
            새로고침
          </button>
          <button
            onClick={() => { sessionStorage.removeItem(KEY_STORAGE); setKey(null); }}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-gray-500 hover:bg-gray-50"
          >
            잠그기
          </button>
        </div>
      </div>

      {loadError && <p className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{loadError}</p>}

      {/* 실험 조건 배정 모드 */}
      <section className="mb-6 rounded-xl border border-amber-300 bg-amber-50/50 p-4">
        <h2 className="mb-1 text-sm font-semibold text-gray-700">실험 조건 배정 (신규 참가자)</h2>
        <p className="mb-3 text-xs text-gray-500">
          조건을 고르면 <b>지금부터 설문을 제출하는 모든 신규 참가자</b>가 그 조건으로 배정됩니다.
          목표 인원이 차면 다음 조건으로 바꿔주세요. 이미 배정된 참가자는 바뀌지 않습니다.
        </p>
        <div className="flex flex-wrap gap-2">
          {([["ours", "ours (제안 시스템)"], ["baseline2", "baseline2 (추론 숨김)"],
             ["baseline1", "baseline1 (추론 없음)"], [null, "자동 균형 배정"]] as [string | null, string][]).map(([v, label]) => (
            <button
              key={label}
              disabled={savingConfig}
              onClick={() => void saveForcedCondition(v)}
              className={`rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-50 ${
                forcedCondition === v
                  ? "border-[#4F46E5] bg-[#4F46E5] text-white"
                  : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs font-medium text-gray-700">
          현재: {forcedCondition ? `${COND_LABEL[forcedCondition] ?? forcedCondition} 고정 모집 중` : "자동 균형 배정"}
        </p>
      </section>

      {/* 조건 밸런스 */}
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-gray-500">조건별 모집 현황</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(balance?.conditions ?? []).map((c) => (
            <div key={c.condition}
                 className={`rounded-xl border p-4 ${forcedCondition === c.condition ? "border-[#4F46E5] bg-indigo-50/40" : "border-gray-200"}`}>
              <p className="text-xs text-gray-500">
                {COND_LABEL[c.condition] ?? c.condition}
                {forcedCondition === c.condition && <span className="ml-1 font-semibold text-[#4F46E5]">← 모집 중</span>}
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {c.started}
                <span className="ml-1 text-sm font-normal text-gray-400">시작 / 배정 {c.assigned}</span>
              </p>
            </div>
          ))}
        </div>
        {balance && (
          <p className="mt-2 text-xs text-gray-500">
            과제 시작 {balance.totalStarted}명 · 설문만 하고 이탈 {balance.dropped}명
          </p>
        )}
      </section>

      {/* 조건 지정 테스트 세션 생성 */}
      <section className="mb-8 rounded-xl border border-indigo-200 bg-indigo-50/40 p-4">
        <h2 className="mb-3 text-sm font-semibold text-gray-700">테스트 세션 만들기 (조건 직접 지정)</h2>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select value={newCond} onChange={(e) => setNewCond(e.target.value as typeof newCond)}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-2">
            <option value="ours">ours (제안 시스템)</option>
            <option value="baseline2">baseline2 (추론 숨김)</option>
            <option value="baseline1">baseline1 (추론 없음)</option>
          </select>
          <select value={newCat} onChange={(e) => setNewCat(e.target.value)}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-2">
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={newFam} onChange={(e) => setNewFam(e.target.value as typeof newFam)}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-2">
            <option value="familiar">잘 아는 상품군</option>
            <option value="unfamiliar">잘 모르는 상품군</option>
          </select>
          <button onClick={() => void createTestSession()} disabled={creating || !newCat}
                  className="rounded-lg bg-[#4F46E5] px-4 py-2 font-semibold text-white disabled:opacity-40">
            {creating ? "만드는 중…" : "세션 생성"}
          </button>
        </div>
        {createdLinks.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {createdLinks.map((l) => (
              <li key={l.url} className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-gray-600">{l.label}</span>
                <a href={l.url} target="_blank" rel="noreferrer" className="font-mono text-[#4F46E5] underline">{l.url}</a>
                <button onClick={() => void navigator.clipboard.writeText(l.url)}
                        className="rounded border border-gray-300 bg-white px-1.5 py-0.5 text-gray-600 hover:bg-gray-50">
                  복사
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] text-gray-500">
          생성된 세션은 test_admin_* 참가자로 묶여요 — 실험 데이터 정리 때 일괄 삭제 대상입니다.
        </p>
      </section>

      {/* 참가자 */}
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-gray-500">참가자 ({shownParticipants.length})</h2>
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2">참가자</th>
                <th className="px-3 py-2">조건</th>
                <th className="px-3 py-2">사전 설문</th>
                <th className="px-3 py-2">세션</th>
                <th className="px-3 py-2">생성</th>
              </tr>
            </thead>
            <tbody>
              {shownParticipants.map((p) => (
                <tr key={p.id} className={`border-t border-gray-100 ${isTestId(p.id) ? "text-gray-400" : "text-gray-800"}`}>
                  <td className="px-3 py-2 font-mono text-xs">
                    {p.label ?? p.id}
                    {isTestId(p.id) && <span className="ml-1 rounded bg-gray-100 px-1 text-[10px]">테스트</span>}
                  </td>
                  <td className="px-3 py-2">{p.studyCondition ?? "-"}</td>
                  <td className="px-3 py-2">{p.hasSurvey ? "제출" : "-"}</td>
                  <td className="px-3 py-2">{p.sessionCount}</td>
                  <td className="px-3 py-2 text-xs text-gray-500">{fmtTime(p.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 세션 */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-gray-500">쇼핑 세션 ({shownSessions.length})</h2>
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2">세션</th>
                <th className="px-3 py-2">참가자</th>
                <th className="px-3 py-2">카테고리</th>
                <th className="px-3 py-2">조건</th>
                <th className="px-3 py-2">턴</th>
                <th className="px-3 py-2">피드백</th>
                <th className="px-3 py-2">칩</th>
                <th className="px-3 py-2">최종선택</th>
              </tr>
            </thead>
            <tbody>
              {shownSessions.map((s) => {
                const m = s.metadata ?? {};
                const open = openSession === s.id;
                return (
                  <Fragment key={s.id}>
                    <tr
                      onClick={() => void toggleSession(s.id)}
                      className={`cursor-pointer border-t border-gray-100 hover:bg-indigo-50/40 ${isTestId(s.participantId) ? "text-gray-400" : "text-gray-800"} ${open ? "bg-indigo-50/60" : ""}`}
                    >
                      <td className="px-3 py-2 font-mono text-xs">{s.id.slice(-10)}</td>
                      <td className="px-3 py-2 font-mono text-xs">{s.participantId ?? "-"}</td>
                      <td className="px-3 py-2">{m.category ?? "-"}</td>
                      <td className="px-3 py-2">{m.studyCondition ?? "-"}</td>
                      <td className="px-3 py-2">{s.turnCount}</td>
                      <td className="px-3 py-2">{s.feedbackCount}</td>
                      <td className="px-3 py-2">{s.topicCount}</td>
                      <td className="px-3 py-2 text-xs">{m.finalChoice?.status ?? "-"}</td>
                    </tr>
                    {open && (
                      <tr className="border-t border-gray-100 bg-gray-50/60">
                        <td colSpan={8} className="px-4 py-3">
                          {!detail ? (
                            <p className="text-xs text-gray-400">불러오는 중…</p>
                          ) : (
                            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                              {/* 대화 */}
                              <div className="space-y-2">
                                <p className="text-[11px] font-semibold text-gray-500">대화 ({detail.turns.length}턴)</p>
                                {detail.turns.map((t, i) => (
                                  <p key={i} className="text-xs leading-relaxed">
                                    <span className={`mr-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold ${t.role === "user" ? "bg-indigo-100 text-indigo-700" : "bg-gray-200 text-gray-600"}`}>
                                      {t.role === "user" ? "참가자" : "에이전트"}
                                    </span>
                                    {t.content}
                                  </p>
                                ))}
                              </div>
                              {/* 추천·선택 */}
                              <div className="space-y-2">
                                <p className="text-[11px] font-semibold text-gray-500">
                                  추천된 상품 ({detail.impressions.length}) · 선택: {m.finalChoice?.status ?? "미확정"}
                                </p>
                                <ul className="space-y-1.5">
                                  {detail.impressions.map((imp, i) => {
                                    const fb = detail.feedback.filter((f) => f.productId === imp.productId);
                                    const liked = fb.some((f) => f.type === "like");
                                    const disliked = fb.some((f) => f.type === "dislike");
                                    const purchased = fb.some((f) => f.type === "purchase");
                                    return (
                                      <li key={i} className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs">
                                        <span className="font-medium text-gray-800">{imp.product?.title ?? imp.productId}</span>
                                        {typeof imp.product?.price === "number" && (
                                          <span className="ml-1 text-gray-500">{imp.product.price.toLocaleString("ko-KR")}원</span>
                                        )}
                                        {purchased && <span className="ml-1 rounded bg-[#4F46E5] px-1 text-[10px] text-white">최종 선택</span>}
                                        {liked && <span className="ml-1 rounded bg-emerald-100 px-1 text-[10px] text-emerald-700">좋아요</span>}
                                        {disliked && <span className="ml-1 rounded bg-red-100 px-1 text-[10px] text-red-600">싫어요</span>}
                                        {imp.recommendationReason && (
                                          <p className="mt-0.5 text-[11px] text-gray-500">{imp.recommendationReason}</p>
                                        )}
                                      </li>
                                    );
                                  })}
                                </ul>
                                {detail.feedback.length > 0 && (
                                  <p className="text-[11px] text-gray-500">
                                    피드백 이유: {detail.feedback.filter((f) => f.reasonText).map((f) => `"${f.reasonText}"`).join(", ") || "없음"}
                                  </p>
                                )}
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
