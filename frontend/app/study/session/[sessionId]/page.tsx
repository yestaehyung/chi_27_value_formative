"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Conflict, Impression, PreferenceState, Turn } from "@/lib/types";
import MessageBubble from "@/components/chat/MessageBubble";
import AgentAvatar from "@/components/chat/AgentAvatar";
import ChatComposer from "@/components/chat/ChatComposer";
import ThinkingSkeleton from "@/components/chat/ThinkingSkeleton";
import ProductCard from "@/components/products/ProductCard";
import { FeedbackPayload } from "@/components/products/ProductFeedbackButtons";
import CurrentUnderstandingPanel from "@/components/preference/CurrentUnderstandingPanel";
import ConflictCard from "@/components/preference/ConflictCard";
import EvidenceDrawer from "@/components/preference/EvidenceDrawer";

export default function StudySessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();

  const [turns, setTurns] = useState<Turn[]>([]);
  const [impressionsByTurn, setImpressionsByTurn] = useState<Record<string, Impression[]>>({});
  const [state, setState] = useState<PreferenceState | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [feedbackByProduct, setFeedbackByProduct] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [evidenceTopic, setEvidenceTopic] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [condition, setCondition] = useState("correctable");
  const [scenarioTitle, setScenarioTitle] = useState("");
  const [initialNeed, setInitialNeed] = useState<string | null>(null);
  const [chipSuggestions, setChipSuggestions] = useState<string[] | null>(null);
  const [finished, setFinished] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [participantId, setParticipantId] = useState<string>("");
  const [chatInput, setChatInput] = useState(""); // 입력창 값 (답변 칩 클릭 시 여기에 채움)
  const [pendingFirst, setPendingFirst] = useState<string | null>(null); // 시작 화면에서 넘어온 첫 발화

  const chatEndRef = useRef<HTMLDivElement>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  // ----- initial load -------------------------------------------------------
  useEffect(() => {
    if (!sessionId) return;
    api.getSession(sessionId).then((d) => {
      setTurns(d.turns);
      setState(d.preferenceState);
      setConflicts(d.conflicts);
      setCondition((d.session.metadata?.studyCondition as string) ?? "correctable");
      setScenarioTitle(d.scenario?.title ?? "");
      setParticipantId(d.session?.participantId ?? "");
      setInitialNeed(d.scenario?.initialUserNeed || null);
      const byTurn: Record<string, Impression[]> = {};
      for (const imp of d.impressions as Impression[]) {
        (byTurn[imp.turnId] ??= []).push(imp);
      }
      setImpressionsByTurn(byTurn);
      const fb: Record<string, string[]> = {};
      for (const f of d.feedback) {
        (fb[f.productId] ??= []).push(f.type);
      }
      setFeedbackByProduct(fb);
      // 시작 화면(session/new)에서 넘긴 첫 발화 — 빈 세션이면 자동 전송 (새로고침엔 재전송 안 됨)
      const first = sessionStorage.getItem(`vc_first_${sessionId}`);
      if (first && d.turns.length === 0) {
        sessionStorage.removeItem(`vc_first_${sessionId}`);
        setPendingFirst(first);
      }
    }).catch(console.error);
  }, [sessionId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, impressionsByTurn, conflicts]);

  // ----- actions ------------------------------------------------------------
  const sendMessage = useCallback(async (text: string) => {
    // 1) 사용자 메시지를 즉시 화면에 반영 (낙관적 업데이트) — 응답을 기다리지 않음
    const optimisticId = `optimistic_${Date.now()}`;
    setTurns((prev) => [...prev, {
      id: optimisticId, sessionId, turnIndex: prev.length, role: "user",
      content: text, dialogueActs: [], relatedProductIds: [],
      createdAt: new Date().toISOString(),
    } as Turn]);
    setBusy(true);
    try {
      // 2) 응답이 오면 임시 메시지를 실제 turn으로 교체하고 에이전트 답변을 이어붙임
      const res = await api.postTurn(sessionId, text);
      setTurns((prev) => [...prev.filter((t) => t.id !== optimisticId), res.turn, res.agentResponse]);
      if (res.recommendedProducts?.length) {
        setImpressionsByTurn((prev) => ({
          ...prev,
          [res.agentResponse.id]: res.recommendedProducts,
        }));
      }
      if (res.preferenceState) setState(res.preferenceState);
      if (res.conflicts?.length) setConflicts((prev) => [...prev, ...res.conflicts]);
      // 입력창 위 답변 칩 — 백엔드가 대화 맥락에 맞춰 동적 생성
      setChipSuggestions(res.replySuggestions?.length ? res.replySuggestions : null);
    } catch (e) {
      console.error(e);
      // 느린 턴(LLM ~30초+)에서 연결이 끊겨도 백엔드는 완료해 저장했을 수 있다 —
      // 서버 상태로 재동기화해 진실을 화면에 맞춘다 (조용한 유실 방지).
      try {
        const d = await api.getSession(sessionId);
        setTurns(d.turns);
        if (d.preferenceState) setState(d.preferenceState);
        setConflicts(d.conflicts);
        showToast("연결이 불안정해 대화를 다시 불러왔어요.");
      } catch {
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId)); // 재동기화도 실패 → 임시 메시지 제거
        showToast("메시지 전송에 실패했어요.");
      }
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const sendFeedback = useCallback(async (productId: string, payload: FeedbackPayload) => {
    setBusy(true);
    try {
      const res = await api.postFeedback(sessionId, productId, payload.type, payload.reasonCode, payload.reasonText);
      setFeedbackByProduct((prev) => ({
        ...prev,
        [productId]: [...(prev[productId] ?? []), payload.type],
      }));
      if (res.updatedPreferenceState) setState(res.updatedPreferenceState);
      if (res.newConflicts?.length) setConflicts((prev) => [...prev, ...res.newConflicts]);
      if (res.chosenRejectedPairsCreated?.length) {
        showToast("반응이 기록됐어요.");
      }
      if (payload.type === "purchase") {
        showToast("이 상품을 선택했어요.");
      }
    } catch (e) {
      console.error(e);
      showToast("피드백 전송에 실패했어요.");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const resolveConflict = useCallback(async (conflictId: string, optionId: string, manualText?: string) => {
    setBusy(true);
    try {
      const res = await api.resolveConflict(conflictId, optionId, manualText);
      setConflicts((prev) => prev.filter((c) => c.id !== conflictId));
      setState(res.newPreferenceState);
      // 해소 발화는 서버가 Turn으로 영속화해 돌려준다(새로고침·replay 생존). 구버전 응답 폴백 유지.
      setTurns((prev) => [...prev, res.turn ?? {
        id: `local_${Date.now()}`,
        sessionId, turnIndex: prev.length, role: "service_agent",
        content: res.message, dialogueActs: [], relatedProductIds: [],
        agentAction: "resolution", createdAt: new Date().toISOString(),
      } as Turn]);
    } catch (e) {
      console.error(e);
      showToast("충돌 해결에 실패했어요.");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const chipAction = useCallback(async (topicId: string, action: string, manualLabel?: string) => {
    if (action === "show_evidence") {
      setEvidenceTopic(topicId);
      api.logInspect(sessionId, topicId).catch(() => {}); // DG3: 근거 확인 시점 로깅
      return;
    }
    try {
      const res = await api.chipAction(topicId, action, manualLabel);
      setState(res.newPreferenceState);
      showToast(res.message);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const copyConversation = useCallback(async () => {
    const label = (r: string) => (r === "user" ? "나" : "에이전트");
    const lines: string[] = [];
    if (scenarioTitle) lines.push(`# ${scenarioTitle}`, "");
    for (const t of turns) {
      if (t.id.startsWith("optimistic_")) continue; // 전송 중 임시 메시지 제외
      lines.push(`${label(t.role)}: ${t.content}`);
      for (const imp of impressionsByTurn[t.id] ?? []) {
        const p = imp.product;
        if (p) lines.push(`  · ${p.title}${p.price != null ? ` (${p.price.toLocaleString()}원)` : ""}`);
      }
      lines.push("");
    }
    const text = lines.join("\n").trim();
    try {
      await navigator.clipboard.writeText(text);
      showToast("대화를 클립보드에 복사했어요.");
    } catch {
      showToast("복사 실패 — 브라우저 권한을 확인해 주세요.");
    }
  }, [turns, impressionsByTurn, scenarioTitle]);

  // 시작 화면에서 넘어온 첫 발화 자동 전송 (sendMessage 정의 이후에 실행).
  // ref 가드: dev StrictMode의 effect 이중 실행에서 중복 전송 방지.
  const sentFirstRef = useRef(false);
  useEffect(() => {
    if (pendingFirst && !sentFirstRef.current) {
      sentFirstRef.current = true;
      setPendingFirst(null);
      sendMessage(pendingFirst);
    }
  }, [pendingFirst, sendMessage]);

  const correctable = condition === "correctable";
  const showState = condition !== "baseline";
  const latestRecommendTurnId = Object.keys(impressionsByTurn).at(-1);

  // 로딩 단계 문구 — 실제 파이프라인 단계(발화 이해 → 가치/기준 파악 → 충돌 검사 → 추천 준비)를
  // 맥락에 따라 순서대로 보여준다. 마지막 단계는 응답 올 때까지 유지 (ThinkingSkeleton).
  const hasRecommended = Object.keys(impressionsByTurn).length > 0;
  const thinkingSteps = conflicts.length > 0
    ? ["방금 말씀을 살펴보고 있어요…", "기존 기준과 다른 점을 확인하고 있어요…", "어떻게 반영할지 정리하고 있어요…"]
    : hasRecommended
      ? ["말씀을 살펴보고 있어요…", "바뀐 기준을 반영하고 있어요…", "기준에 맞는 상품을 다시 고르고 있어요…"]
      : turns.filter((t) => t.role === "user").length <= 1
        ? ["말씀을 이해하고 있어요…", "어떤 가치를 중요하게 보는지 살펴보고 있어요…", "맞는 상품을 고르고 있어요…"]
        : ["말씀을 이해하고 있어요…", "기준을 정리하고 있어요…", "더 나은 추천을 준비하고 있어요…"];

  // ----- layout: chat (with inline product carousel) + preference panel -----
  return (
    <div className="grid h-[calc(100vh-7rem)] grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_440px]">
      {/* 마치기 확인 (브라우저 기본 confirm 대신 커스텀 모달) */}
      {confirmEnd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="card max-w-xs p-6 text-center">
            <h2 className="text-base font-bold text-[#191919]">이 쇼핑을 마칠까요?</h2>
            <p className="mt-1 text-sm text-slate-500">지금까지의 대화는 저장돼요.</p>
            <div className="mt-4 flex gap-2">
              <button onClick={() => setConfirmEnd(false)} className="btn flex-1 py-2">취소</button>
              <button
                onClick={() => { setConfirmEnd(false); setFinished(true); }}
                className="btn btn-primary flex-1 py-2"
              >
                마치기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 쇼핑 마치기 → 완료 화면 (추후 순차 플로우에서 '다음 쇼핑으로'로 대체) */}
      {finished && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="card max-w-sm p-6 text-center">
            <AgentAvatar className="mx-auto block h-12 w-12" />
            <h2 className="mt-3 text-lg font-bold text-[#191919]">이 쇼핑을 마쳤어요</h2>
            <p className="mt-1 text-sm text-slate-500">이어서 다음 쇼핑을 진행할게요.</p>
            <button
              onClick={() => router.push(participantId ? `/study/session/new?pid=${participantId}` : "/study/session/new")}
              className="btn btn-primary mt-4 w-full py-2"
            >
              다음 쇼핑으로 넘어가기
            </button>
            <button onClick={() => router.push("/")} className="mt-2 text-xs text-slate-400 hover:text-slate-600">
              오늘은 여기까지
            </button>
          </div>
        </div>
      )}

      {/* Left: Chat with inline products */}
      <div className="card flex min-h-0 flex-col">
        <div className="flex items-center justify-between border-b border-[#f0f2f4] px-5 py-3">
          <div className="text-sm font-bold text-[#191919]">
            쇼핑 대화 {scenarioTitle && <span className="ml-1 text-xs font-normal text-[#9aa0a6]">— {scenarioTitle}</span>}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={copyConversation}
              disabled={turns.length === 0}
              title="대화 내용을 클립보드에 복사"
              className="rounded-lg border border-[#e4e8eb] px-2.5 py-1 text-xs text-[#5f6368] transition-colors hover:border-[#4f46e5] hover:text-[#4f46e5] disabled:opacity-40"
            >
              📋 대화 복사
            </button>
            <button
              onClick={() => setConfirmEnd(true)}
              className="btn btn-primary px-3 py-1 text-xs"
            >
              이 쇼핑 마치기
            </button>
          </div>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {turns.length === 0 && (
            <div className="mt-16 text-center">
              <AgentAvatar className="mx-auto block h-12 w-12" />
              <div className="mt-3 text-xl font-extrabold text-[#191919]">
                안녕하세요! <span className="text-[#4f46e5]">무엇을 찾아드릴까요?</span>
              </div>
              {initialNeed && (
                <div className="mt-2 text-xs text-[#9aa0a6]">
                  예: &quot;{initialNeed}&quot;
                </div>
              )}
            </div>
          )}

          {turns.map((t) => (
            <div key={t.id}>
              <MessageBubble turn={t} />
              {/* inline product carousel under the recommending agent turn */}
              {impressionsByTurn[t.id] && (
                <div className="msg-in mt-3 pl-9">
                  <div className="flex gap-3 overflow-x-auto pb-2">
                    {impressionsByTurn[t.id].map((imp, i) => (
                      <div key={imp.id} className="w-[284px] shrink-0">
                        <ProductCard
                          impression={imp}
                          index={i}
                          givenFeedback={feedbackByProduct[imp.productId] ?? []}
                          onFeedback={sendFeedback}
                          disabled={busy || t.id !== latestRecommendTurnId}
                        />
                      </div>
                    ))}
                  </div>
                  {t.id !== latestRecommendTurnId && (
                    <div className="mt-1 text-[10px] text-[#b0b8c1]">이전 추천 — 최신 추천에서 반응을 남겨주세요</div>
                  )}
                </div>
              )}
            </div>
          ))}

          {busy && <ThinkingSkeleton steps={thinkingSteps} />}
          <div ref={chatEndRef} />
        </div>
        {/* 리디자인 입력창 (프리뷰 확정안) — 칩 클릭 시 입력창에 채움, 사용자가 다듬어 전송 */}
        <div className="border-t border-[#f0f2f4] p-3">
          <ChatComposer
            value={chatInput}
            onChange={setChatInput}
            onSend={(msg) => { setChatInput(""); sendMessage(msg); }}
            disabled={busy}
            loading={busy}
            placeholder="무엇을 찾고 계세요?"
            suggestions={
              chipSuggestions /* 대화 중: 백엔드 동적 칩 */
              ?? (initialNeed && turns.length === 0 ? [initialNeed] : undefined) /* 첫 턴: 시나리오 기반 */
            }
          />
        </div>
      </div>

      {/* Right: Preference panel (understanding chips · conflict · radar) */}
      <div className="min-h-0 space-y-3 overflow-y-auto pb-4 pr-1">
        {correctable && conflicts.map((c) => (
          <ConflictCard
            key={c.id}
            conflict={c}
            onResolve={(optionId, manualText) => resolveConflict(c.id, optionId, manualText)}
            disabled={busy}
          />
        ))}

        {showState ? (
          <CurrentUnderstandingPanel
            state={state}
            editable={correctable}
            onChipAction={chipAction}
            onShowEvidence={(id) => { setEvidenceTopic(id); api.logInspect(sessionId, id).catch(() => {}); }}
          />
        ) : (
          <div className="card p-4 text-xs text-[#9aa0a6]">
            baseline 조건: 시스템이 이해한 기준은 표시되지 않습니다.
          </div>
        )}
      </div>

      {correctable && <EvidenceDrawer topicId={evidenceTopic} onClose={() => setEvidenceTopic(null)} />}

      {toast && (
        <div className="msg-in fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl bg-[#191919] px-5 py-3 text-xs text-white shadow-xl">
          <span className="font-extrabold text-[#a5b4fc]">V</span> {toast}
        </div>
      )}
    </div>
  );
}
