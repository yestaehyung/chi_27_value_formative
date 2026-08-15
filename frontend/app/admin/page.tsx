"use client";

// 관리자 대시보드 (2026-08-16) — 연구자 1인용, 한국어.
// 인증: 비밀번호 = 백엔드 VC_RESEARCH_KEY. 입력값을 sessionStorage에 두고 모든 요청에
// X-Research-Key 헤더로 붙인다 — 검증은 백엔드 research_gate가 한다(프론트에 키를 굽지 않음).
// study 모드 미들웨어 matcher에 /admin이 없으므로 라이브에서도 접근 가능하다.
import { useCallback, useEffect, useState } from "react";

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
  const [hideTest, setHideTest] = useState(false);

  // 실험 조건 배정 모드 — null이면 자동 균형, 조건 슬러그면 신규 참가자 전원 그 조건으로
  const [forcedCondition, setForcedCondition] = useState<string | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  // 데이터 관리 — 전체 다운로드(ZIP) + 전체 삭제(배치 리셋, 입력 확인 필수)
  const [downloading, setDownloading] = useState(false);
  const [wipeInput, setWipeInput] = useState("");
  const [wiping, setWiping] = useState(false);
  const [wipeResult, setWipeResult] = useState<string | null>(null);

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
  }, [loadAll]);

  const downloadAll = async () => {
    if (!key) return;
    setDownloading(true);
    try {
      const res = await fetch("/api/exports/archive", { headers: { "X-Research-Key": key } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vc_export_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setLoadError("데이터 다운로드에 실패했어요.");
    } finally {
      setDownloading(false);
    }
  };

  const wipeAll = async () => {
    if (!key || wipeInput !== "전체삭제") return;
    if (!window.confirm("정말 모든 참가자·세션 데이터를 삭제할까요? 되돌릴 수 없습니다.\n(다운로드를 먼저 했는지 확인하세요)")) return;
    setWiping(true);
    setWipeResult(null);
    try {
      const res = await fetch("/api/research/wipe", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Research-Key": key },
        body: JSON.stringify({ confirm: "전체삭제" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setWipeResult(`삭제 완료 — 총 ${d.totalRows}행 (참가자 ${d.deleted?.participants ?? 0}, 세션 ${d.deleted?.sessions ?? 0}, 턴 ${d.deleted?.turns ?? 0})`);
      setWipeInput("");
      void loadAll(key);
    } catch {
      setLoadError("전체 삭제에 실패했어요.");
    } finally {
      setWiping(false);
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
             ["baseline1", "baseline1 (추론 없음)"]] as [string, string][]).map(([v, label]) => (
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
          현재: {forcedCondition
            ? `${COND_LABEL[forcedCondition] ?? forcedCondition} 모집 중`
            : "⚠️ 조건 미설정 — 위에서 모집할 조건을 선택해 주세요"}
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
        <h2 className="mb-3 text-sm font-semibold text-gray-500">쇼핑 세션 ({shownSessions.length}) — 행을 클릭하면 참가자 화면 그대로 열립니다</h2>
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
                return (
                  <tr
                    key={s.id}
                    onClick={() => window.open(`/study/session/${s.id}`, "_blank")}
                    title="클릭하면 참가자와 동일한 채팅 화면이 새 탭으로 열립니다"
                    className={`cursor-pointer border-t border-gray-100 hover:bg-indigo-50/40 ${isTestId(s.participantId) ? "text-gray-400" : "text-gray-800"}`}
                  >
                    <td className="px-3 py-2 font-mono text-xs text-[#4F46E5] underline decoration-dotted">{s.id.slice(-10)}</td>
                    <td className="px-3 py-2 font-mono text-xs">{s.participantId ?? "-"}</td>
                    <td className="px-3 py-2">{m.category ?? "-"}</td>
                    <td className="px-3 py-2">{m.studyCondition ?? "-"}</td>
                    <td className="px-3 py-2">{s.turnCount}</td>
                    <td className="px-3 py-2">{s.feedbackCount}</td>
                    <td className="px-3 py-2">{s.topicCount}</td>
                    <td className="px-3 py-2 text-xs">{m.finalChoice?.status ?? "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 데이터 관리 */}
      <section className="mt-10 rounded-xl border border-red-200 bg-red-50/40 p-4">
        <h2 className="mb-1 text-sm font-semibold text-gray-700">데이터 관리</h2>
        <p className="mb-3 text-xs text-gray-500">
          다운로드는 모든 테이블(참가자·설문·세션·대화·추천·피드백·칩·충돌·교정·LLM 로그 전부)을
          JSONL로 묶은 ZIP입니다. <b>전체 삭제 전에는 반드시 먼저 다운로드하세요.</b>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => void downloadAll()} disabled={downloading}
                  className="rounded-lg bg-[#4F46E5] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            {downloading ? "내려받는 중…" : "전체 데이터 다운로드 (ZIP)"}
          </button>
          <span className="mx-2 h-6 w-px bg-red-200" />
          <input
            value={wipeInput}
            onChange={(e) => setWipeInput(e.target.value)}
            placeholder='삭제하려면 "전체삭제" 입력'
            className="rounded-lg border border-red-300 bg-white px-3 py-2 text-sm focus:outline-none"
          />
          <button onClick={() => void wipeAll()} disabled={wiping || wipeInput !== "전체삭제"}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
            {wiping ? "삭제 중…" : "전체 삭제 (배치 리셋)"}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-gray-500">
          삭제 대상: 참가자·세션·대화·추천·피드백·칩·충돌·교정·검증·LLM 로그. 상품 풀과 시드
          concept, 조건 설정은 유지됩니다. 되돌릴 수 없습니다.
        </p>
        {wipeResult && <p className="mt-2 text-xs font-medium text-emerald-700">{wipeResult}</p>}
      </section>
    </main>
  );
}
