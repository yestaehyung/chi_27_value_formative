"use client";

// UI 수정안 프로토타입 (2026-07-16, 교수님 피드백 반영). 백엔드 무수정 —
// 기존 API(getSession/postTurn/postFeedback/chipAction/resolveConflict)만 사용.
//
// variant "a" — 안 A: 완전 채팅 인라인. 별도 패널 없음. 에이전트가 이해한 기준을
//   대화 흐름 안의 문장("~중요하게 보고 계신 것 같아요. 맞을까요?")으로 꺼내고,
//   수정도 대화로 한다 (빠른 답변 칩은 입력창에 채우기만 — 전송은 사용자가).
// variant "b" — 안 B: A + 최소 앵커. 입력창 위에 "이해한 기준: 착용감 · 가성비 ▾"
//   접힌 한 줄을 상시 유지 — 펼치면 핵심 기준 2~3개 + 한 줄 근거 + [수정] 하나.
// variant "c" — 수정안 3: 사이드 패널 유지·경량화. 디자인 언어는 현재 버전
//   (CurrentUnderstandingPanel) 그대로 — SimpleUnderstandingPanel 은 그 포크이며
//   레이더 2종·중요도 ⬆⬇·[수정]만 뺐다. 남긴 것: 우선순위 번호 목록 + ✓맞아요 ·
//   ✗아니에요 · 근거(EvidenceDrawer). 패널 폭도 현재와 동일(440px). 외재화는 패널이
//   담당하므로 채팅 인라인 확인 문장은 없음. 충돌 카드는 패널에 (현재 버전과 동일).

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Conflict, Impression, PreferenceChip, PreferenceState, Turn } from "@/lib/types";
import { selectCoreCriteria, understandingSentence } from "@/lib/criteria";
import CriteriaConfirmWidget from "@/components/study/CriteriaConfirmWidget";
import SequentialCriteriaConfirm from "@/components/study/SequentialCriteriaConfirm";
import ConflictUtterance from "@/components/study/ConflictUtterance";
import MessageBubble from "@/components/chat/MessageBubble";
import AgentAvatar from "@/components/chat/AgentAvatar";
import ChatComposer from "@/components/chat/ChatComposer";
import ThinkingSkeleton from "@/components/chat/ThinkingSkeleton";
import ProductCard from "@/components/products/ProductCard";
import ProductCarousel from "@/components/products/ProductCarousel";
import ProductListRow from "@/components/products/ProductListRow";
import { FeedbackPayload } from "@/components/products/ProductFeedbackButtons";
import ConflictCard from "@/components/preference/ConflictCard";
import ChipTypeBadge from "@/components/preference/ChipTypeBadge";
import EvidenceDrawer from "@/components/preference/EvidenceDrawer";
import SimpleUnderstandingPanel from "@/components/preference/SimpleUnderstandingPanel";
import SurveyModal from "@/components/study/SurveyModal";
import CriterionCheckModal, { type CriterionCandidate } from "@/components/study/CriterionCheckModal";
import {
  CRITERION_CHECK_MAX, POST_TASK, PRE_TASK, fillTemplate, postStudySectionsFor,
  type StudyCondition,
} from "@/lib/mainSurvey";

export type UiVariant = "a" | "b" | "c" | "d" | "e";

export const VARIANT_META: Record<UiVariant, { label: string; desc: string }> = {
  a: { label: "수정안 1 — 채팅 인라인", desc: "외재화가 전부 대화 문장 안에. 별도 UI 표면 없음." },
  b: { label: "수정안 2 — 채팅 + 접힌 요약", desc: "대화 중심 + 입력창 위 '이해한 기준' 한 줄 앵커." },
  c: { label: "수정안 3 — 경량 패널", desc: "현재 디자인 유지 · 그래프/중요도/수정 제거 · 우선순위 번호 + 맞아요·아니에요·근거." },
  d: { label: "수정안 D — 솔리드 카드 확인", desc: "단일 컬럼 · 각 기준을 맞아요로 확인하거나 달라요로 바로 수정" },
  e: { label: "수정안 E — 에이전트 능동 질문", desc: "독립 질문 턴 기준 확인 · conflict 발화+옵션칩" },
};


export default function VariantSession({
  sessionId,
  variant,
  study = false, // true면 실제 스터디 UI로 동작 — 마치기/사후설문/첫 발화 자동전송 포함
}: {
  sessionId: string;
  variant: UiVariant;
  study?: boolean;
}) {
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [impressionsByTurn, setImpressionsByTurn] = useState<Record<string, Impression[]>>({});
  const [state, setState] = useState<PreferenceState | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [feedbackByProduct, setFeedbackByProduct] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [scenarioTitle, setScenarioTitle] = useState("");
  const [initialNeed, setInitialNeed] = useState<string | null>(null);
  const [chipSuggestions, setChipSuggestions] = useState<string[] | null>(null);
  const [chatInput, setChatInput] = useState("");
  // 안 B 앵커 상태
  const [anchorOpen, setAnchorOpen] = useState(false);
  const [showAllCriteria, setShowAllCriteria] = useState(false);
  const [editingChip, setEditingChip] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  // 안 3: 근거 드로어 (현재 버전과 동일 동작)
  const [evidenceTopic, setEvidenceTopic] = useState<string | null>(null);
  // 안 D·E의 칩별 펜딩/수정 상태는 CriteriaConfirmWidget이 소유한다.
  // 스터디 생명주기 (study=true에서만) — 마치기/사후설문/완료/첫 발화 자동전송
  const [participantId, setParticipantId] = useState("");
  const [pendingFirst, setPendingFirst] = useState<string | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [postSurveyOpen, setPostSurveyOpen] = useState(false);
  const [postSubmitting, setPostSubmitting] = useState(false);
  const [finished, setFinished] = useState(false);
  // 본실험 설문 흐름: 과제직전 → (대화) → 과제직후 → 기준별 검증 → 완료 → (전체종료 설문)
  const [taskCategory, setTaskCategory] = useState("");
  // between-subjects 조건 — 백엔드가 참가자에 배정한 값 (요청값은 무시된다)
  const [condition, setCondition] = useState<StudyCondition | null>(null);
  const [preTaskOpen, setPreTaskOpen] = useState(false);
  const [criterionOpen, setCriterionOpen] = useState(false);
  const [criteria, setCriteria] = useState<CriterionCandidate[]>([]);
  const [postStudyOpen, setPostStudyOpen] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const loadedRef = useRef(false); // 초기 로드 1회 가드 — 늦게 온 getSession이 낙관적 첫 발화를 덮어쓰는 레이스 방지

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  // ----- initial load (1회만) — StrictMode 이중 실행/재렌더로 두 번째 getSession이
  // 낙관적으로 추가한 사용자 첫 메시지를 빈 배열로 덮어쓰지 않게 loadedRef로 가드 ----
  useEffect(() => {
    if (!sessionId || loadedRef.current) return;
    loadedRef.current = true;
    api.getSession(sessionId).then((d) => {
      setTurns(d.turns);
      setState(d.preferenceState);
      setConflicts(d.conflicts);
      setScenarioTitle(d.scenario?.title ?? "");
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
      // 시작 화면(session/new · /demo)에서 넘긴 첫 발화 — 빈 세션이면 자동 전송
      // (새로고침엔 재전송 안 됨). study 밖에 두는 이유: 데모도 같은 핸드오프를 쓴다.
      const first = sessionStorage.getItem(`vc_first_${sessionId}`);
      if (first && d.turns.length === 0) {
        sessionStorage.removeItem(`vc_first_${sessionId}`);
        setPendingFirst(first);
      }
      if (study) {
        setParticipantId(d.session?.participantId ?? "");
        setTaskCategory(d.scenario?.targetCategory ?? "");
        setCondition((d.session?.metadata?.studyCondition as StudyCondition) ?? null);
        // 과제 직전 설문은 대화가 시작되기 전에 받아야 한다 — 에이전트가 이미 추천을 하면
        // '지금 내 기준이 얼마나 명확한가'가 오염돼서 Δ(사전→사후) 자체가 무의미해진다.
        if (!d.session?.metadata?.preTaskSurvey) setPreTaskOpen(true);
      }
    }).catch(console.error);
  }, [sessionId, study]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, impressionsByTurn, conflicts]);

  // ----- actions (기존 페이지의 낙관적 업데이트 + 재동기화 로직 유지) ---------
  const sendMessage = useCallback(async (text: string) => {
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
      try {
        const d = await api.getSession(sessionId);
        setTurns(d.turns);
        if (d.preferenceState) setState(d.preferenceState);
        setConflicts(d.conflicts);
        showToast("연결이 불안정해 대화를 다시 불러왔어요.");
      } catch {
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
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
      setFeedbackByProduct((prev) => ({ ...prev, [productId]: [...(prev[productId] ?? []), payload.type] }));
      if (res.updatedPreferenceState) setState(res.updatedPreferenceState);
      if (res.newConflicts?.length) setConflicts((prev) => [...prev, ...res.newConflicts]);
      if (res.agentTurn) {
        setTurns((prev) => [...prev, res.agentTurn]);
        setChipSuggestions(res.replySuggestions?.length ? res.replySuggestions : null);
      }
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
      const resolutionTurn = res.turn ?? {
        id: `local_${Date.now()}`, sessionId, turnIndex: 0, role: "service_agent",
        content: res.message, dialogueActs: [], relatedProductIds: [],
        agentAction: "resolution", createdAt: new Date().toISOString(),
      } as Turn;
      // 기준이 바뀐 해소면 백엔드가 갱신 기준으로 재추천한 턴+상품을 함께 준다 — 이어붙인다.
      setTurns((prev) => [...prev, resolutionTurn, ...(res.recommendTurn ? [res.recommendTurn] : [])]);
      if (res.recommendTurn && res.recommendedProducts?.length) {
        setImpressionsByTurn((prev) => ({ ...prev, [res.recommendTurn.id]: res.recommendedProducts }));
      }
      return true;
    } catch (e) {
      console.error(e);
      showToast("충돌 해결에 실패했어요.");
      return false;
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  // 칩 액션 — 기존 API 그대로 (안 B: edit_label / 안 3: confirm·reject)
  const chipAction = useCallback(async (topicId: string, action: string, manualLabel?: string) => {
    try {
      const res = await api.chipAction(topicId, action, manualLabel);
      setState(res.newPreferenceState);
      showToast(res.message);
      return true;
    } catch (e) {
      console.error(e);
      showToast("기준 반영에 실패했어요.");
      return false;
    }
  }, []);

  const saveChipEdit = useCallback(async (topicId: string, label: string) => {
    const saved = await chipAction(topicId, "edit_label", label);
    if (saved) setEditingChip(null);
    return saved;
  }, [chipAction]);

  // 대화 복사 (스터디 헤더) — 텍스트로 클립보드에
  const copyConversation = useCallback(async () => {
    const label = (r: string) => (r === "user" ? "나" : "에이전트");
    const lines: string[] = [];
    if (scenarioTitle) lines.push(`# ${scenarioTitle}`, "");
    for (const t of turns) {
      if (t.id.startsWith("optimistic_")) continue;
      lines.push(`${label(t.role)}: ${t.content}`);
      for (const imp of impressionsByTurn[t.id] ?? []) {
        const p = imp.product;
        if (p) lines.push(`  · ${p.title}${p.price != null ? ` (${p.price.toLocaleString()}원)` : ""}`);
      }
      lines.push("");
    }
    const text = lines.join("\n").trim();
    // navigator.clipboard는 보안 컨텍스트(HTTPS/localhost)에서만 동작 — Tailscale http 접속엔
    // 없다. 그 경우 textarea + execCommand 폴백으로 http에서도 복사되게 한다.
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("execCommand copy failed");
      }
      showToast("대화를 클립보드에 복사했어요.");
    } catch {
      showToast("복사 실패 — 브라우저 권한을 확인해 주세요.");
    }
  }, [turns, impressionsByTurn, scenarioTitle]);

  // 첫 발화 자동 전송 (시작 화면에서 넘어온 것) — dev StrictMode 이중 실행 가드
  // 과제 직전 설문이 떠 있는 동안은 보류 — 설문을 내는 사이에 에이전트가 추천을 끝내면
  // 사전 측정이 사후 측정이 되어버린다.
  const sentFirstRef = useRef(false);
  useEffect(() => {
    if (pendingFirst && !preTaskOpen && !sentFirstRef.current) {
      sentFirstRef.current = true;
      setPendingFirst(null);
      sendMessage(pendingFirst);
    }
  }, [pendingFirst, preTaskOpen, sendMessage]);

  // ----- derived ------------------------------------------------------------
  const chips = state?.userVisibleSummary.chips ?? [];
  const core = selectCoreCriteria(chips);
  const rest = chips.filter((c) => !core.some((k) => k.id === c.id));
  // 안 E 순차 확인 — 물어볼 것은 '아직 사용자가 손대지 않은 추론·불확실' 기준뿐.
  // 사용자가 이미 처리한 상태는 제외한다: confirmed(명시 진술·확인), corrected_by_user
  // (충돌 해소/수정으로 정리), rejected_by_user(거부). 이걸 빼야 방금 충돌로 정리한 기준을
  // 곧바로 다시 확인 요청하는 '이중 질문'이 안 생긴다. 물어볼 게 없으면 위젯 자체를 안 띄움.
  const E_SETTLED = ["confirmed", "corrected_by_user", "rejected_by_user"];
  const eUnadjudicated = core.filter((c) => !E_SETTLED.includes(c.status ?? ""));
  const eAskable = [...eUnadjudicated]
    .sort((a, b) => (b.type === "uncertain" ? 1 : 0) - (a.type === "uncertain" ? 1 : 0))
    .slice(0, 2);
  const eKnown = core.filter((c) => !eAskable.some((x) => x.id === c.id));
  const latestRecommendTurnId = Object.keys(impressionsByTurn).at(-1);
  const latestAgentTurnId = [...turns].reverse().find((t) => t.role !== "user" && !t.id.startsWith("optimistic_"))?.id;

  const thinkingSteps = ["말씀을 살펴보고 있어요…", "기준을 정리하고 있어요…", "맞는 상품을 고르고 있어요…"];

  // 기준 한 줄 행 (안 B 앵커용) — 타입 배지(색+텍스트) + 라벨 + 한 줄 근거 + [수정] 하나.
  const renderCriterionRow = (chip: PreferenceChip) => (
    <div key={chip.id} className="flex items-start gap-2 py-1.5">
      <span className="mt-0.5"><ChipTypeBadge type={chip.type} /></span>
      <div className="min-w-0 flex-1">
        {editingChip === chip.id ? (
          <div>
            <input
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              autoFocus
              className="w-full rounded-lg border border-[#e4e8eb] px-2 py-1 text-xs focus:border-[#4f46e5] focus:outline-none"
            />
            <div className="mt-1 flex justify-end gap-1.5">
              <button className="btn px-2 py-0.5 text-[11px]" onClick={() => setEditingChip(null)}>취소</button>
              <button className="btn btn-primary px-2 py-0.5 text-[11px]" onClick={() => saveChipEdit(chip.id, editText)}>저장</button>
            </div>
          </div>
        ) : (
          <>
            <span className="text-xs font-medium text-[#191919]">{chip.label}</span>
            {/* 확인 상태 — E에서 맞아요 누른 기준은 ✓ 확인됨 (앵커에 확인 기록 반영) */}
            {chip.status === "confirmed" && (
              <span className="ml-1.5 text-[10px] font-semibold text-emerald-700">✓ 확인됨</span>
            )}
            {/* 한 줄 근거 — 이 기준이 어디서 나왔는지 */}
            {chip.displayRationale && (
              <p className="mt-0.5 text-[11px] leading-snug text-[#9aa0a6]">{chip.displayRationale}</p>
            )}
          </>
        )}
      </div>
      {editingChip !== chip.id && (
        <button
          className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-[#9aa0a6] transition-colors hover:text-[#4f46e5]"
          onClick={() => { setEditingChip(chip.id); setEditText(chip.label); }}
        >
          수정
        </button>
      )}
    </div>
  );

  // ----- 채팅 카드 (전 변형 공통 본체) ----------------------------------------
  // flex-1 h-full: 단일 컬럼(flex-col 부모)에서 내용이 적어도 카드가 부모 높이를 채우게 한다
  // (없으면 시작 화면처럼 내용이 짧을 때 카드가 줄고 아래에 공백이 생김). grid 부모(안 3)에선 무해.
  const chatCard = (
    <div className="card flex h-full min-h-0 flex-1 flex-col">
      {/* 헤더 — 스터디면 복사·마치기, 프로토타입이면 수정안 배지. 모바일에서 버튼 압축 */}
      <div className="flex items-center justify-between gap-2 border-b border-[#f0f2f4] px-3 py-2.5 sm:px-5 sm:py-3">
        <div className="min-w-0 truncate text-sm font-bold text-[#191919]">
          쇼핑 대화
          {scenarioTitle && <span className="ml-1 text-xs font-normal text-[#9aa0a6]">— {scenarioTitle}</span>}
        </div>
        {study ? (
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={copyConversation}
              disabled={turns.length === 0}
              title="대화 내용을 클립보드에 복사"
              className="rounded-lg border border-[#e4e8eb] px-2 py-1 text-xs text-[#5f6368] transition-colors hover:border-[#4f46e5] hover:text-[#4f46e5] disabled:opacity-40"
            >
              <span className="sm:hidden">📋</span>
              <span className="hidden sm:inline">📋 대화 복사</span>
            </button>
            <button onClick={() => setConfirmEnd(true)} className="btn btn-primary shrink-0 whitespace-nowrap px-2.5 py-1 text-xs">
              <span className="sm:hidden">마치기</span>
              <span className="hidden sm:inline">이 쇼핑 마치기</span>
            </button>
          </div>
        ) : (
          <span className="shrink-0 rounded-full bg-[#eef2ff] px-2.5 py-1 text-[10px] font-semibold text-[#4f46e5]">
            {VARIANT_META[variant].label}
          </span>
        )}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {turns.length === 0 && (
          <div className="mt-16 text-center">
            <AgentAvatar className="mx-auto block h-12 w-12" />
            <div className="mt-3 text-xl font-extrabold text-[#191919]">
              안녕하세요! <span className="text-[#4f46e5]">무엇을 찾아드릴까요?</span>
            </div>
            {initialNeed && <div className="mt-2 text-xs text-[#9aa0a6]">예: &quot;{initialNeed}&quot;</div>}
          </div>
        )}

        {turns.map((t) => (
          <div key={t.id}>
            <MessageBubble turn={t} />
            {impressionsByTurn[t.id] && (
              variant === "c" ? (
                /* 수정안 3 — 네이버 쇼핑형 세로 리스트 (캐러셀 카드 대신 1상품 1행) */
                <div className="msg-in mt-3 divide-y divide-[#f0f2f4] pl-9">
                  {impressionsByTurn[t.id].map((imp, i) => (
                    <ProductListRow
                      key={imp.id}
                      impression={imp}
                      index={i}
                      givenFeedback={feedbackByProduct[imp.productId] ?? []}
                      onFeedback={sendFeedback}
                      disabled={busy || t.id !== latestRecommendTurnId}
                    />
                  ))}
                </div>
              ) : (
                <div className="msg-in mt-3 pl-9">
                  <ProductCarousel>
                    {impressionsByTurn[t.id].map((imp, i) => (
                      <ProductCard
                        key={imp.id}
                        impression={imp}
                        index={i}
                        givenFeedback={feedbackByProduct[imp.productId] ?? []}
                        onFeedback={sendFeedback}
                        disabled={busy || t.id !== latestRecommendTurnId}
                      />
                    ))}
                  </ProductCarousel>
                </div>
              )
            )}

            {/* 채팅 인라인 외재화 (안 A·B) — 최신 에이전트 턴 아래, 대화 문장으로.
                안 3은 패널이 외재화를 담당하므로 없음. */}
            {(variant === "a" || variant === "b") && t.id === latestAgentTurnId && core.length > 0 && !busy && (
              <div className="msg-in mt-3 flex items-start gap-2.5 pl-9">
                <div className="max-w-[85%] rounded-2xl border border-dashed border-[#c7d2fe] bg-[#f5f7ff] px-4 py-2.5">
                  <p className="text-[13px] leading-relaxed text-[#3730a3]">
                    {understandingSentence(core)}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {["네, 맞아요", "조금 달라요 — "].map((s) => (
                      <button
                        key={s}
                        onClick={() => setChatInput(s)}
                        className="rounded-full border border-[#c7d2fe] bg-white px-2.5 py-1 text-[11px] text-[#4f46e5] transition-colors hover:bg-[#eef2ff]"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {/* 안 D — 추천 아래 확인 카드 (CriteriaConfirmWidget inline). 채팅 버블과 동일 표면.
                confirm/reject/edit은 위젯이 소유 — reject된 칩도 수정 끝날 때까지 행 유지. */}
            {variant === "d" && t.id === latestAgentTurnId && core.length > 0 && !busy && (
              <div className="msg-in mt-3 pl-9">
                <CriteriaConfirmWidget
                  chips={core}
                  presentation="inline"
                  onConfirm={(id) => chipAction(id, "confirm")}
                  onReject={(id) => chipAction(id, "reject")}
                  onSaveEdit={(id, label) => chipAction(id, "edit_label", label)}
                />
              </div>
            )}

            {/* 안 E — 순차 확인: '물어볼 것(추론/불확실 기준)'이 있을 때만 띄운다.
                충돌이 열려 있으면(conflicts>0) 충돌 해소가 곧 기준 정리이므로 확인 위젯을
                겹쳐 띄우지 않는다 — '충돌+기준확인' 이중 질문 방지. */}
            {variant === "e" && t.id === latestAgentTurnId && eAskable.length > 0 && !busy && conflicts.length === 0 && (
              <div className="msg-in mt-3">
                <SequentialCriteriaConfirm
                  askable={eAskable}
                  alreadyKnown={eKnown}
                  onConfirm={(id) => chipAction(id, "confirm")}
                  onReject={(id) => chipAction(id, "reject")}
                  onSaveEdit={(id, label) => chipAction(id, "edit_label", label)}
                  onEscapeToChat={(chip) => setChatInput(`‘${chip.label}’ 기준을 이렇게 바꾸고 싶어요: `)}
                />
              </div>
            )}
          </div>
        ))}

        {/* 충돌 (안 A·B·D) — 상시 패널이 아니라 발생 시에만 대화 흐름 안에 (축 3 "필요할 때").
            안 E는 ConflictCard 대신 발화+옵션칩으로 아래 별도 블록에서 처리. */}
        {(variant === "a" || variant === "b" || variant === "d") && conflicts.map((c) => (
          <div key={c.id} className="msg-in pl-9">
            <ConflictCard
              conflict={c}
              onResolve={(optionId, manualText) => resolveConflict(c.id, optionId, manualText)}
              disabled={busy}
            />
          </div>
        ))}
        {/* 안 E — conflict 발화 + 옵션 칩 (ConflictUtterance — ConflictCard 비사용, manual_edit 제외) */}
        {variant === "e" && conflicts.map((c) => (
          <div key={c.id} className="msg-in">
            <ConflictUtterance
              conflict={c}
              onResolve={(optionId) => resolveConflict(c.id, optionId)}
              disabled={busy}
            />
          </div>
        ))}

        {busy && <ThinkingSkeleton steps={thinkingSteps} />}
        <div ref={chatEndRef} />
      </div>

      {/* 안 B·E — 입력창 위 접힌 한 줄 앵커: "이해한 기준: 착용감 · 가성비 ▾".
          사이드바 없이 '지금 전체 이해'를 한눈에(Q2). E는 확인 상태(✓)까지 앵커에 반영. */}
      {(variant === "b" || variant === "e") && core.length > 0 && (
        <div className="border-t border-[#f0f2f4] bg-[#fafbfc] px-5 py-2">
          <button
            onClick={() => { setAnchorOpen((v) => !v); setShowAllCriteria(false); }}
            className="flex w-full items-center gap-1.5 text-left text-xs text-[#5f6368]"
          >
            <span className="font-semibold text-[#9aa0a6]">이해한 기준:</span>
            <span className="min-w-0 flex-1 truncate font-medium text-[#191919]">
              {core.map((c) => (c.status === "confirmed" ? "✓ " : "") + c.label).join(" · ")}
            </span>
            <span className="shrink-0 text-[#9aa0a6]">{anchorOpen ? "▴" : "▾"}</span>
          </button>
          {anchorOpen && (
            <div className="mt-1 border-t border-[#f0f2f4] pt-1">
              {core.map((c) => renderCriterionRow(c))}
              {showAllCriteria && rest.map((c) => renderCriterionRow(c))}
              {rest.length > 0 && !showAllCriteria && (
                <button
                  onClick={() => setShowAllCriteria(true)}
                  className="py-1 text-[11px] text-[#9aa0a6] hover:text-[#4f46e5]"
                >
                  외 {rest.length}개 더 보기
                </button>
              )}
            </div>
          )}
        </div>
      )}

      <div className="border-t border-[#f0f2f4] p-3">
        <ChatComposer
          value={chatInput}
          onChange={setChatInput}
          onSend={(msg) => { setChatInput(""); sendMessage(msg); }}
          disabled={busy}
          loading={busy}
          placeholder="무엇을 찾고 계세요?"
          suggestions={
            chipSuggestions
            ?? (initialNeed && turns.length === 0 ? [initialNeed] : undefined)
          }
        />
      </div>
    </div>
  );

  // ----- 안 3 전용 — 경량 사이드 패널 (현재 버전 레이아웃·디자인 유지) ---------
  const lightPanel = (
    <div className="min-h-0 space-y-3 overflow-y-auto pb-4 pr-1">
      {conflicts.map((c) => (
        <ConflictCard
          key={c.id}
          conflict={c}
          onResolve={(optionId, manualText) => resolveConflict(c.id, optionId, manualText)}
          disabled={busy}
        />
      ))}

      <SimpleUnderstandingPanel
        state={state}
        onChipAction={chipAction}
        onShowEvidence={(id) => { setEvidenceTopic(id); api.logInspect(sessionId, id).catch(() => {}); }}
      />
    </div>
  );

  return (
    <>
      {/* 카드 높이 = 뷰포트 − 스터디 레이아웃 여백(모바일 py-3=1.5rem, 데스크톱 py-6=3rem).
          헤더가 없으므로 여백만 빼면 카드가 정확히 화면을 채운다(아래 공백 제거). */}
      {variant === "c" ? (
        <div className="grid h-[calc(100dvh-1.5rem)] grid-cols-1 gap-4 sm:h-[calc(100dvh-3rem)] lg:grid-cols-[minmax(0,1fr)_440px]">
          {chatCard}
          {lightPanel}
        </div>
      ) : (
        <div className="mx-auto flex h-[calc(100dvh-1.5rem)] max-w-5xl flex-col sm:h-[calc(100dvh-3rem)]">{chatCard}</div>
      )}

      {variant === "c" && (
        <EvidenceDrawer topicId={evidenceTopic} onClose={() => setEvidenceTopic(null)} />
      )}

      {/* 스터디 생명주기 — 마치기 확인 → 사후설문 → 완료 화면 */}
      {study && confirmEnd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="card max-w-xs p-6 text-center">
            <h2 className="text-base font-bold text-[#191919]">이 쇼핑을 마칠까요?</h2>
            <p className="mt-1 text-sm text-slate-500">지금까지의 대화는 저장돼요.</p>
            <div className="mt-4 flex gap-2">
              <button onClick={() => setConfirmEnd(false)} className="btn flex-1 py-2">취소</button>
              <button
                onClick={() => { setConfirmEnd(false); setPostSurveyOpen(true); }}
                className="btn btn-primary flex-1 py-2"
              >
                마치기
              </button>
            </div>
          </div>
        </div>
      )}

      {study && preTaskOpen && (
        <SurveyModal
          title="쇼핑을 시작하기 전에"
          desc={`${taskCategory || "이 상품군"}에 대한 지금의 생각을 알려주세요. 대화가 끝난 뒤 같은 질문을 한 번 더 드립니다.`}
          sections={fillTemplate(PRE_TASK, { category: taskCategory || "이 상품군" })}
          submitLabel="쇼핑 시작하기"
          submitting={postSubmitting}
          onSubmit={async (answers, profile) => {
            setPostSubmitting(true);
            try {
              await api.submitPreTaskSurvey(sessionId, answers, profile, taskCategory);
              setPreTaskOpen(false);
            } catch (e) {
              console.error(e);
              showToast("설문 저장에 실패했어요 — 다시 시도해 주세요.");
            } finally {
              setPostSubmitting(false);
            }
          }}
        />
      )}

      {study && postSurveyOpen && (
        <SurveyModal
          title="이번 쇼핑은 어떠셨나요?"
          desc="방금 마친 대화를 떠올리며 답해 주세요."
          sections={POST_TASK}
          submitLabel="다음으로"
          submitting={postSubmitting}
          onSubmit={async (answers, profile) => {
            setPostSubmitting(true);
            try {
              await api.submitPostSurvey(sessionId, answers, profile);
              setPostSurveyOpen(false);
              // 이어서 기준별 검증 — 제시할 기준이 없으면(짧은 세션) 건너뛴다
              const res = await api.criterionCandidates(sessionId, CRITERION_CHECK_MAX);
              const list = (res?.criteria ?? []) as CriterionCandidate[];
              if (list.length > 0) { setCriteria(list); setCriterionOpen(true); }
              else setFinished(true);
            } catch (e) {
              console.error(e);
              showToast("설문 저장에 실패했어요 — 다시 제출해 주세요.");
              setPostSurveyOpen(true);
            } finally {
              setPostSubmitting(false);
            }
          }}
        />
      )}

      {study && criterionOpen && (
        <CriterionCheckModal
          candidates={criteria}
          submitting={postSubmitting}
          onSubmit={async (items) => {
            setPostSubmitting(true);
            try {
              await api.submitCriterionValidations(sessionId, items);
              setCriterionOpen(false);
              setFinished(true);
            } catch (e) {
              console.error(e);
              showToast("저장에 실패했어요 — 다시 제출해 주세요.");
            } finally {
              setPostSubmitting(false);
            }
          }}
        />
      )}

      {study && postStudyOpen && (
        <SurveyModal
          title="마지막으로 전체 경험에 대해"
          desc="오늘 진행한 쇼핑 전체를 떠올리며 답해 주세요. 이 설문을 마치면 연구가 종료됩니다."
          sections={postStudySectionsFor(condition)}
          submitLabel="제출하고 종료"
          submitting={postSubmitting}
          onSubmit={async (answers, profile) => {
            setPostSubmitting(true);
            try {
              if (participantId) await api.submitPostStudySurvey(participantId, answers, profile);
              setPostStudyOpen(false);
              router.push("/study/done");
            } catch (e) {
              console.error(e);
              showToast("설문 저장에 실패했어요 — 다시 제출해 주세요.");
            } finally {
              setPostSubmitting(false);
            }
          }}
        />
      )}

      {study && finished && (
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
            <button
              onClick={() => {
                setFinished(false);
                // 이 조건에 물을 섹션이 하나도 없으면(기준을 안 보여준 조건) 설문을 건너뛴다
                if (postStudySectionsFor(condition).length === 0) router.push("/study/done");
                else setPostStudyOpen(true);
              }}
              className="mt-2 text-xs text-slate-400 hover:text-slate-600"
            >
              모든 쇼핑을 마쳤어요
            </button>
          </div>
        </div>
      )}

      {toast && (
        <div className="msg-in fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl bg-[#191919] px-5 py-3 text-xs text-white shadow-xl">
          <span className="font-extrabold text-[#a5b4fc]">V</span> {toast}
        </div>
      )}
    </>
  );
}
