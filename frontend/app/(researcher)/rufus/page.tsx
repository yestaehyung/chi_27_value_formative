"use client";

// Rufus형 호스트 테스트 UI (2026-07-07) — 도구 호출 trace가 보이는 개발용 채팅.
// 스터디 UI(/study)는 내부를 감추는 게 설계라, 호스트 검증용으로 별도 표면을 둔다:
// 좌측 대화 + 노출 상품, 우측 턴별 도구 호출(agentic_loop)·플래너 결정(action_decision).
// 백엔드가 VC_TURN_LOOP=agentic 으로 떠 있어야 agentic trace가 잡힌다 (아니면 파이프라인
// 결정 로그가 표시됨 — 어느 경로였는지 reason 필드로 구분).

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type ToolCall = { name: string; args: Record<string, unknown> };
type TurnLog = { task: string; request: any; response: any };
type Msg = {
  role: "user" | "agent";
  content: string;
  action?: string;
  products?: any[];
  logs?: TurnLog[];
};

export default function RufusTestPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  const newSession = async () => {
    setError(null);
    const r = await api.createSession("custom", "correctable", {
      title: "Rufus 호스트 테스트",
      context: "",
    });
    setSessionId(r.sessionId);
    setMsgs([]);
  };

  const send = async () => {
    const content = input.trim();
    if (!content || !sessionId || busy) return;
    setInput("");
    setError(null);
    setMsgs((m) => [...m, { role: "user", content }]);
    setBusy(true);
    try {
      const out = await api.postTurn(sessionId, content);
      const agentTurnId = out.agentResponse?.id;
      // 이 턴의 의사결정 로그 — 도구 trace(agentic_loop) + 플래너/rerank
      let logs: TurnLog[] = [];
      try {
        const calls = await api.llmCalls(sessionId);
        logs = calls
          .filter((c) => c.request?.turnId === agentTurnId)
          .map((c) => ({ task: c.task, request: c.request, response: c.response }));
      } catch {
        /* 로그 실패는 대화를 막지 않는다 */
      }
      setMsgs((m) => [
        ...m,
        {
          role: "agent",
          content: out.agentResponse?.content || "(응답 없음)",
          action: out.agentResponse?.agentAction,
          products: out.recommendedProducts || [],
          logs,
        },
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const lastLogs = [...msgs].reverse().find((m) => m.logs?.length)?.logs || [];

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Rufus형 호스트 테스트</h1>
          <p className="text-sm text-gray-500">
            도구 호출 trace가 보이는 개발용 채팅 — 백엔드 VC_TURN_LOOP=agentic 필요
            {sessionId && (
              <span className="ml-2 font-mono text-xs text-gray-400">{sessionId}</span>
            )}
          </p>
        </div>
        <button
          onClick={newSession}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          새 세션
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* 좌: 대화 */}
        <div className="lg:col-span-2 flex h-[70vh] flex-col rounded-xl border border-gray-200 bg-white">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {!sessionId && (
              <p className="text-sm text-gray-400">
                &quot;새 세션&quot;을 눌러 시작하세요.
              </p>
            )}
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl bg-indigo-600 px-4 py-2 text-sm text-white">
                    {m.content}
                  </div>
                </div>
              ) : (
                <div key={i} className="space-y-2">
                  <div className="flex items-start gap-2">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-gray-100 px-4 py-2 text-sm text-gray-900">
                      {m.action && (
                        <span className="mr-2 rounded bg-gray-200 px-1.5 py-0.5 font-mono text-[10px] text-gray-600">
                          {m.action}
                        </span>
                      )}
                      {m.content}
                    </div>
                  </div>
                  {!!m.products?.length && (
                    <div className="ml-2 space-y-1">
                      {m.products.map((imp: any) => (
                        <div
                          key={imp.id}
                          className="flex items-baseline gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-1.5 text-xs"
                        >
                          <span className="font-mono text-gray-400">#{imp.rank}</span>
                          <span className="font-medium text-gray-800">
                            {imp.product?.title}
                          </span>
                          <span className="text-gray-500">
                            {imp.product?.price?.toLocaleString()}원
                          </span>
                          {!!imp.weakIntentions?.length && (
                            <span className="text-amber-600">
                              ⚠ {imp.weakIntentions[0]}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            )}
            {busy && <p className="text-sm text-gray-400">에이전트 생각 중…</p>}
            <div ref={bottomRef} />
          </div>
          <div className="flex gap-2 border-t border-gray-200 p-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && send()}
              placeholder={sessionId ? "메시지를 입력하세요" : "먼저 새 세션을 시작하세요"}
              disabled={!sessionId || busy}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
            />
            <button
              onClick={send}
              disabled={!sessionId || busy || !input.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-40"
            >
              전송
            </button>
          </div>
        </div>

        {/* 우: 이번 턴 의사결정 trace */}
        <div className="h-[70vh] overflow-y-auto rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">
            최근 턴 의사결정 로그
          </h2>
          {lastLogs.length === 0 && (
            <p className="text-xs text-gray-400">아직 로그가 없어요.</p>
          )}
          <div className="space-y-3">
            {lastLogs.map((log, i) => (
              <div key={i} className="rounded-lg border border-gray-100 bg-gray-50 p-2">
                <div className="mb-1 font-mono text-[11px] font-semibold text-indigo-700">
                  {log.task}
                </div>
                {log.task === "agentic_loop" ? (
                  <div className="space-y-1">
                    {(log.response?.toolCalls || []).map((tc: ToolCall, j: number) => (
                      <div key={j} className="font-mono text-[11px] text-gray-700">
                        <span className="text-emerald-700">{tc.name}</span>(
                        {JSON.stringify(tc.args, null, 0)})
                      </div>
                    ))}
                    {!(log.response?.toolCalls || []).length && (
                      <div className="font-mono text-[11px] text-gray-500">
                        (도구 호출 없음 — 대화만)
                      </div>
                    )}
                  </div>
                ) : (
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-gray-600">
                    {JSON.stringify(log.response, null, 1)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
