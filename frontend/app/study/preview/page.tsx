"use client";

// 채팅 UI 리디자인 미리보기 (작업용 데모). localhost:3000/study/preview
// 실제 study 세션 페이지 로직을 그대로 복사 — API·상태관리·피드백·충돌·기준패널 동일.
// 차이: (1) 마운트 시 데모 세션 자동 생성, (2) 입력창=ChatComposer, 로딩=ThinkingSkeleton (새 UI).
// 확정되면 이 UI 변경을 실제 session/[sessionId] 페이지에 반영한다. (인디고 고정)
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Conflict, Impression, PreferenceState, Scenario, Turn } from "@/lib/types";
import MessageBubble from "@/components/chat/MessageBubble";
import AgentAvatar from "@/components/chat/AgentAvatar";
import ChatComposer from "@/components/chat/ChatComposer";
import ThinkingSkeleton from "@/components/chat/ThinkingSkeleton";
import ProductCard from "@/components/products/ProductCard";
import { FeedbackPayload } from "@/components/products/ProductFeedbackButtons";
import CurrentUnderstandingPanel from "@/components/preference/CurrentUnderstandingPanel";
import ConflictCard from "@/components/preference/ConflictCard";
import EvidenceDrawer from "@/components/preference/EvidenceDrawer";
import TutorialDemo from "@/components/tutorial/TutorialDemo";

export default function ChatPreviewPage() {
  const [tutorialDone, setTutorialDone] = useState(false);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [composeText, setComposeText] = useState(""); // 첫 화면 입력창 값 (칩 클릭 시 여기에 채움)
  const [chatInput, setChatInput] = useState(""); // 대화 화면 입력창 값 (답변 칩 클릭 시 여기에 채움)
  const [starting, setStarting] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [scenarioTitle, setScenarioTitle] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [impressionsByTurn, setImpressionsByTurn] = useState<Record<string, Impression[]>>({});
  const [state, setState] = useState<PreferenceState | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [feedbackByProduct, setFeedbackByProduct] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [evidenceTopic, setEvidenceTopic] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [chipSuggestions, setChipSuggestions] = useState<string[] | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  // 대화 + 추천 상품을 플레인 텍스트로 클립보드에 복사 (session 페이지와 동일 로직)
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

  // 1단계: 시나리오 목록 로드 (실제 session/new와 동일)
  useEffect(() => {
    api.scenarios().then((d) => setScenarios(d.scenarios)).catch(console.error);
  }, []);

  // 시나리오 선택 → 세션 생성 → 대화 화면으로 (실제 플로우와 동일)
  // 세션 생성 + 첫 메시지 자동 전송 → 대화 전환 (시나리오/자유입력 공통).
  //  - 시나리오 칩: 그 시나리오의 initialUserNeed를 첫 메시지로 전송 (위 채팅바에 예시 발화가 보임)
  //  - 자유 입력: 사용자가 친 텍스트를 첫 메시지로
  const startSession = useCallback(async (sc: Scenario | null, firstMsg: string) => {
    if (starting || !firstMsg.trim()) return;
    setStarting(true);
    try {
      const d = sc
        ? await api.createSession(sc.id, "correctable")
        : await api.createSession("custom", "correctable", { title: "자유 대화" });
      setSessionId(d.sessionId);
      setScenarioTitle(sc?.title ?? "자유 대화");
      // 대화 화면으로 넘어간 뒤 첫 메시지를 보낸다 (낙관적 표시 + 실제 전송)
      const optimisticId = `optimistic_${Date.now()}`;
      setTurns([{ id: optimisticId, sessionId: d.sessionId, turnIndex: 0, role: "user",
        content: firstMsg, dialogueActs: [], relatedProductIds: [], createdAt: new Date().toISOString() } as Turn]);
      setBusy(true);
      try {
        const res = await api.postTurn(d.sessionId, firstMsg);
        setTurns([res.turn, res.agentResponse]);
        if (res.recommendedProducts?.length) setImpressionsByTurn({ [res.agentResponse.id]: res.recommendedProducts });
        if (res.preferenceState) setState(res.preferenceState);
        if (res.conflicts?.length) setConflicts(res.conflicts);
        setChipSuggestions(res.replySuggestions?.length ? res.replySuggestions : null);
      } catch (e) {
        console.error(e); setTurns([]); showToast("메시지 전송에 실패했어요.");
      } finally { setBusy(false); }
    } catch (e) {
      console.error(e); showToast("세션을 시작하지 못했어요.");
    } finally {
      setStarting(false);
    }
  }, [starting]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, impressionsByTurn, conflicts]);

  // ===== 아래 핸들러는 실제 세션 페이지와 동일 =====
  const sendMessage = useCallback(async (text: string) => {
    if (!sessionId) return;
    const optimisticId = `optimistic_${Date.now()}`;
    setTurns((prev) => [...prev, {
      id: optimisticId, sessionId, turnIndex: prev.length, role: "user",
      content: text, dialogueActs: [], relatedProductIds: [],
      createdAt: new Date().toISOString(),
    } as Turn]);
    setBusy(true);
    try {
      const res = await api.postTurn(sessionId, text);
      setTurns((prev) => [...prev.filter((t) => t.id !== optimisticId), res.turn, res.agentResponse]);
      if (res.recommendedProducts?.length) {
        setImpressionsByTurn((prev) => ({ ...prev, [res.agentResponse.id]: res.recommendedProducts }));
      }
      if (res.preferenceState) setState(res.preferenceState);
      if (res.conflicts?.length) setConflicts((prev) => [...prev, ...res.conflicts]);
      setChipSuggestions(res.replySuggestions?.length ? res.replySuggestions : null);
    } catch (e) {
      console.error(e);
      setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
      showToast("메시지 전송에 실패했어요.");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const sendFeedback = useCallback(async (productId: string, payload: FeedbackPayload) => {
    setBusy(true);
    try {
      const res = await api.postFeedback(sessionId, productId, payload.type, payload.reasonCode, payload.reasonText);
      setFeedbackByProduct((prev) => ({ ...prev, [productId]: [...(prev[productId] ?? []), payload.type] }));
      if (res.updatedPreferenceState) setState(res.updatedPreferenceState);
      if (res.newConflicts?.length) setConflicts((prev) => [...prev, ...res.newConflicts]);
      if (res.chosenRejectedPairsCreated?.length) showToast("반응이 기록됐어요.");
      if (payload.type === "purchase") showToast("이 상품을 선택했어요.");
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
      setTurns((prev) => [...prev, {
        id: `local_${Date.now()}`, sessionId, turnIndex: prev.length, role: "service_agent",
        content: res.message, dialogueActs: [], relatedProductIds: [],
        agentAction: "ask_correction", createdAt: new Date().toISOString(),
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
      api.logInspect(sessionId, topicId).catch(() => {});
      return;
    }
    try {
      const res = await api.chipAction(topicId, action, manualLabel);
      setState(res.newPreferenceState);
      showToast(res.message);
    } catch (e) {
      console.error(e);
    }
  }, [sessionId]);

  const latestRecommendTurnId = Object.keys(impressionsByTurn).at(-1);

  // 로딩 단계 문구 (A: 실제 파이프라인 단계를 시간 흐름에 따라 순서대로).
  // 우리 한 턴 흐름: 발화 이해 → 가치/기준 파악 → (충돌 검사) → 추천/질문 준비.
  // 맥락(B)으로 시작점·문구를 살짝 달리한다. 마지막 단계는 응답 올 때까지 유지됨.
  const hasRecommended = Object.keys(impressionsByTurn).length > 0;
  const thinkingSteps = conflicts.length > 0
    ? ["방금 말씀을 살펴보고 있어요…", "기존 기준과 다른 점을 확인하고 있어요…", "어떻게 반영할지 정리하고 있어요…"]
    : hasRecommended
      ? ["말씀을 살펴보고 있어요…", "바뀐 기준을 반영하고 있어요…", "기준에 맞는 상품을 다시 고르고 있어요…"]
      : turns.filter((t) => t.role === "user").length <= 1
        ? ["말씀을 이해하고 있어요…", "어떤 가치를 중요하게 보는지 살펴보고 있어요…", "맞는 상품을 고르고 있어요…"]
        : ["말씀을 이해하고 있어요…", "기준을 정리하고 있어요…", "더 나은 추천을 준비하고 있어요…"];

  // ===== 0단계: 튜토리얼 (코치마크) — 끝나면 시나리오 선택으로 =====
  if (!tutorialDone) {
    return <TutorialDemo onDone={() => setTutorialDone(true)} />;
  }

  // ===== 1단계: 시나리오 선택 화면 (이미지 ↳ 리스트 스타일) =====
  if (!sessionId) {
    return (
      // layout의 max-w-7xl/py-6 안에서 화면 세로 중앙 정렬 (-my-6로 패딩 상쇄)
      <div className="-my-6 flex min-h-[calc(100vh-3.5rem)] flex-col items-center justify-center">
      <div className="w-full max-w-2xl px-4">
        {/* 진입 애니메이션 — 타이틀 → 입력창 → 칩 순서로 살짝 시차 (stagger) */}
        <div className="msg-in">
          <h1 className="text-center text-2xl font-bold tracking-tight text-[#191919]">
            <span className="text-[#4f46e5]">에이전트와 쇼핑</span>을 시작해 볼까요?
          </h1>
          <p className="mt-2 text-center text-sm text-[#9aa0a6]">
            찾으시는 걸 입력하거나, 아래 추천에서 골라 바로 시작해 보세요.
          </p>
        </div>

        {/* 직접 입력 — 진짜 입력창. 치고 전송하면 자유대화 세션 생성 + 첫 메시지 자동 전송 → 대화 전환 */}
        <div className="msg-in mt-7" style={{ animationDelay: "80ms" }}>
          <ChatComposer
            value={composeText}
            onChange={setComposeText}
            onSend={(msg) => startSession(null, msg)}
            disabled={starting}
            placeholder="무엇을 찾고 계세요?"
            disclaimer={false}
          />
        </div>

        {/* 시나리오 추천 — 카테고리 칩 (제목만, 가로 wrap). 설명은 hover 툴팁. */}
        <div className="msg-in mt-5 flex flex-wrap justify-center gap-2" style={{ animationDelay: "160ms" }}>
          {scenarios.map((sc) => (
            <button key={sc.id} onClick={() => setComposeText(sc.initialUserNeed)} disabled={starting}
              title={sc.initialUserNeed}
              className="rounded-full border border-[#e4e8eb] bg-white px-4 py-2 text-sm text-[#404040] transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] active:scale-[0.97] disabled:opacity-50">
              {sc.title}
            </button>
          ))}
        </div>

        <p className="mt-8 text-center text-[11px] text-[#b0b8c1]">
          AI 답변으로 정확하지 않은 정보가 포함될 수 있어요.
        </p>
        {toast && (
          <div className="msg-in fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-[#191919] px-5 py-3 text-xs text-white shadow-xl">{toast}</div>
        )}
      </div>
      </div>
    );
  }

  // ===== 2단계: 대화 화면 =====
  return (
    <div className="grid h-[calc(100vh-5rem)] grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_440px]">
      {/* Left: Chat with inline products (새 UI) */}
      <div className="card flex min-h-0 flex-col">
        <div className="flex items-center justify-between border-b border-[#f0f2f4] px-5 py-3">
          <div className="text-sm font-bold text-[#191919]">쇼핑 대화 {scenarioTitle && <span className="ml-1 text-xs font-normal text-[#9aa0a6]">— {scenarioTitle}</span>}</div>
          <button
            onClick={copyConversation}
            disabled={turns.length === 0}
            title="대화 내용을 클립보드에 복사"
            className="rounded-lg border border-[#e4e8eb] px-2.5 py-1 text-xs text-[#5f6368] transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] active:scale-[0.96] disabled:opacity-40"
          >
            📋 대화 복사
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {turns.length === 0 && !busy && (
            <div className="mt-16 text-center">
              <AgentAvatar className="mx-auto block h-12 w-12" />
              <div className="mt-3 text-xl font-extrabold text-[#191919]">
                안녕하세요! <span className="text-[#4f46e5]">무엇을 찾아드릴까요?</span>
              </div>
              <div className="mt-2 text-xs text-[#9aa0a6]">예: &quot;운동할 때 쓸 무선 이어폰 추천해줘&quot;</div>
            </div>
          )}

          {turns.map((t) => (
            <div key={t.id}>
              <MessageBubble turn={t} />
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

        {/* 새 입력창 + 면책 문구 */}
        <div className="border-t border-[#f0f2f4] p-3">
          <ChatComposer
            value={chatInput}
            onChange={setChatInput}
            onSend={(msg) => { setChatInput(""); sendMessage(msg); }}
            disabled={busy || !sessionId}
            loading={busy}
            placeholder="무엇을 찾고 계세요?"
            suggestions={
              chipSuggestions /* 대화 중: 백엔드 동적 칩 */
              ?? (turns.length === 0 ? ["운동할 때 쓸 무선 이어폰 추천해줘", "예산 5만원 안쪽이면 좋겠어요", "선물용으로 괜찮은 거 있을까요?"] : undefined)
            }
          />
        </div>
      </div>

      {/* Right: Preference panel (실제와 동일) */}
      <div className="min-h-0 space-y-3 overflow-y-auto pb-4 pr-1">
        {conflicts.map((c) => (
          <ConflictCard key={c.id} conflict={c} onResolve={(optionId, manualText) => resolveConflict(c.id, optionId, manualText)} />
        ))}
        <CurrentUnderstandingPanel
          state={state}
          editable
          onChipAction={chipAction}
          onShowEvidence={(id) => { setEvidenceTopic(id); api.logInspect(sessionId, id).catch(() => {}); }}
        />
      </div>

      <EvidenceDrawer topicId={evidenceTopic} onClose={() => setEvidenceTopic(null)} />

      {toast && (
        <div className="msg-in fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl bg-[#191919] px-5 py-3 text-xs text-white shadow-xl">
          <span className="font-extrabold text-[#a5b4fc]">V</span> {toast}
        </div>
      )}
    </div>
  );
}
