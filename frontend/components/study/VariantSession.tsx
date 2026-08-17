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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import CurrentUnderstandingPanel from "@/components/preference/CurrentUnderstandingPanel";
import EvidenceDrawer from "@/components/preference/EvidenceDrawer";
import SimpleUnderstandingPanel from "@/components/preference/SimpleUnderstandingPanel";
import FinalChoiceModal, { type FinalChoicePayload, type SeenProduct } from "@/components/study/FinalChoiceModal";
import SurveyModal from "@/components/study/SurveyModal";
import CriterionCheckModal, { type CriterionCandidate } from "@/components/study/CriterionCheckModal";
import {
  ALLOWS_CORRECTION, CRITERION_CHECK_MAX, INFERS_INTENTION,
  POST_TASK_LOCALIZED as POST_TASK,
  SHOWS_CRITERIA, TEST_SURVEY_SKIP,
  postStudySectionsLocalized as postStudySectionsFor,
  type StudyCondition,
} from "@/lib/localizedMainSurvey";
import { completeTask, nextTask } from "@/lib/taskQueue";
import { categoryLabel, productTitle, productUsd, STUDY_UI, tr } from "@/lib/studyI18n";

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
  // ③ 최종 선택 확정 (2026-08-11) — 마치기 → 최종 선택 → 사후설문 → 기준검증 순.
  const [finalChoiceOpen, setFinalChoiceOpen] = useState(false);
  const [finalSubmitting, setFinalSubmitting] = useState(false);
  const [postSurveyOpen, setPostSurveyOpen] = useState(false);
  const [postSubmitting, setPostSubmitting] = useState(false);
  const [finished, setFinished] = useState(false);
  // 본실험 설문 흐름: 과제직전 → (대화) → 과제직후 → 기준별 검증 → 완료 → (전체종료 설문)
  // between-subjects 조건 — 백엔드가 참가자에 배정한 값 (요청값은 무시된다)
  const [condition, setCondition] = useState<StudyCondition | null>(null);
  // 조건별 UI 게이트. study 모드가 아니면(UI 수정안 비교·데모) 조건 설계 밖이므로 전부 보인다.
  // condition이 아직 안 들어온 첫 렌더에서도 기준을 노출하지 않도록 기본값은 false로 둔다
  // — baseline 참가자에게 한 프레임이라도 기준이 스치면 조건이 오염된다.
  const showsCriteria = !study || (condition ? SHOWS_CRITERIA[condition] : false);
  const allowsCorrection = !study || (condition ? ALLOWS_CORRECTION[condition] : false);
  const infersIntention = !study || (condition ? INFERS_INTENTION[condition] : false);
  // 본실험 사이드바 (2026-08-08) — 기준·충돌 외재화가 채팅 인라인(안 E)에서 우측 패널로
  // 이동했다. ours 조건에서만 켜지고, 켜지면 E의 인라인 위젯(순차확인·충돌발화·앵커바)은
  // 중복 표면이므로 끈다. baseline1·2는 사이드바 자체가 없다(빈 패널을 보여주면 "뭔가
  // 숨겨져 있다"는 힌트가 되어 조건이 오염된다).
  const studySidebar = study && showsCriteria;
  // 과제 큐 — 카테고리 선택 화면이 세운 4과제 계획의 남은 개수 (lib/taskQueue.ts)
  const [queueLeft, setQueueLeft] = useState(0);
  const [startingNext, setStartingNext] = useState(false);
  // 완료 표시는 한 번만. finished가 껐다 켜져도(전체종료 설문 취소 등) 큐가 두 칸 가면 안 된다.
  const advancedRef = useRef(false);
  const [criterionOpen, setCriterionOpen] = useState(false);
  const [criteria, setCriteria] = useState<CriterionCandidate[]>([]);
  const [postStudyOpen, setPostStudyOpen] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const loadedRef = useRef(false); // 초기 로드 1회 가드 — 늦게 온 getSession이 낙관적 첫 발화를 덮어쓰는 레이스 방지

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  // 과제를 마치면 큐를 한 칸 전진 — "남은 쇼핑 N번" 표시와 다음 버튼 노출의 근거가 된다.
  // 로컬 큐는 즉시값일 뿐, 서버 진행(task-progress: finalChoice+postSurvey 마커 집계)이
  // 도착하면 그 값으로 덮는다 — 탭 유실·이전 라운드 잔존 큐의 조기 "전부 완료" 방지.
  useEffect(() => {
    if (!study || !finished || advancedRef.current) return;
    advancedRef.current = true;
    setQueueLeft(completeTask(sessionId));
    if (participantId) {
      api.getTaskProgress(participantId)
        .then((p) => { if (p.tasks.length > 0) setQueueLeft(p.remaining); })
        .catch(() => {});
    }
  }, [study, finished, participantId]);

  /** 다음 과제로 이동 — 과제 직전 지식 설문(/study/knowledge)을 경유한다 (2026-08-17).
      설문 페이지가 서버 진행(task-progress)에서 다음 카테고리를 정하고, 그 카테고리의
      지식 설문을 받은 뒤 세션을 연다 (이미 낸 카테고리는 재질문 없이 바로 쇼핑). */
  const startNextTask = async () => {
    if (startingNext) return;
    if (participantId) {
      setStartingNext(true);
      router.push(`/study/knowledge?pid=${participantId}`);
      return;
    }
    // pid 없는 개발 폴백 — 종전처럼 로컬 큐에서 바로 세션 생성
    const task = nextTask(undefined);
    if (!task) return;
    setStartingNext(true);
    try {
      const res = await api.createCategorySession(
        task.category, task.familiarity, participantId || undefined,
      );
      router.push(`/study/session/${res.sessionId}`);
    } catch (e) {
      console.error(e);
      showToast(tr("다음 쇼핑을 열지 못했어요 — 다시 눌러 주세요.", "We could not open the next shopping task. Please try again."));
      setStartingNext(false);
    }
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
        setCondition((d.session?.metadata?.studyCondition as StudyCondition) ?? null);
      }
    }).catch(console.error);
  }, [sessionId, study]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, impressionsByTurn, conflicts]);

  // ----- actions (기존 페이지의 낙관적 업데이트 + 재동기화 로직 유지) ---------
  // 답변 칩은 턴 응답과 분리해 따로 받는다 (백엔드 크리티컬 패스 단축, 2026-08-14).
  // reqId 가드: 칩이 오기 전에 새 턴이 시작되면 낡은 칩을 버린다.
  const suggestionsReqRef = useRef(0);
  const loadChipSuggestions = useCallback(() => {
    const reqId = ++suggestionsReqRef.current;
    void api.fetchReplySuggestions(sessionId)
      .then((r) => {
        if (suggestionsReqRef.current === reqId) {
          setChipSuggestions(r.suggestions?.length ? r.suggestions : null);
        }
      })
      .catch(() => {});
  }, [sessionId]);

  // 응답 없이 남은 마지막 사용자 턴 (배포 재시작·파이프라인 실패의 흔적) — 재시도 대상
  const lastTurn = turns[turns.length - 1];
  const unansweredTurn =
    !busy && lastTurn && lastTurn.role === "user" && !String(lastTurn.id).startsWith("optimistic")
      ? lastTurn : null;

  const retryUnanswered = async () => {
    if (!unansweredTurn || busy) return;
    setBusy(true);
    try {
      const res = await api.retryTurn(sessionId, unansweredTurn.id);
      setTurns((prev) => [...prev.filter((t) => t.id !== unansweredTurn.id), res.turn, res.agentResponse]);
      if (res.recommendedProducts?.length) {
        setImpressionsByTurn((prev) => ({ ...prev, [res.agentResponse.id]: res.recommendedProducts }));
      }
      if (res.preferenceState) setState(res.preferenceState);
      if (res.conflicts?.length) setConflicts((prev) => [...prev, ...res.conflicts]);
      setChipSuggestions(null);
      loadChipSuggestions();
    } catch (e) {
      console.error(e);
      // 409 = 원본 파이프라인이 아직 생성 중 (shield) — 겹쳐 돌리지 않고 기다린다
      const stillWorking = e instanceof Error && e.message.startsWith("API 409");
      showToast(stillWorking
        ? tr("응답을 아직 만드는 중이에요 — 잠시 후 자동으로 나타나요.",
             "The reply is still being generated — it will appear shortly.")
        : tr("다시 시도해 주세요.", "Please try again."));
      if (stillWorking) {
        setTimeout(() => {
          api.getSession(sessionId).then((d) => {
            setTurns(d.turns);
            if (d.preferenceState) setState(d.preferenceState);
            setConflicts(d.conflicts);
          }).catch(() => {});
        }, 10000);
      }
    } finally {
      setBusy(false);
    }
  };

  const sendMessage = useCallback(async (text: string, inputSource?: "suggestion" | "typed") => {
    const optimisticId = `optimistic_${Date.now()}`;
    // 멱등 키 (2026-08-18): 502/타임아웃 후 재전송이 같은 발화를 두 번 저장하지 않게
    const clientRequestId =
      typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : optimisticId;
    setTurns((prev) => [...prev, {
      id: optimisticId, sessionId, turnIndex: prev.length, role: "user",
      content: text, dialogueActs: [], relatedProductIds: [],
      createdAt: new Date().toISOString(),
    } as Turn]);
    setBusy(true);
    try {
      const res = await api.postTurn(sessionId, text, clientRequestId, inputSource);
      if (res.duplicate) {
        // 이미 같은 전송이 저장돼 있음(이전 시도의 재전송) — 서버 상태를 다시 불러온다
        const d = await api.getSession(sessionId);
        setTurns(d.turns);
        if (d.preferenceState) setState(d.preferenceState);
        setConflicts(d.conflicts);
        setBusy(false);
        return;
      }
      setTurns((prev) => [...prev.filter((t) => t.id !== optimisticId), res.turn, res.agentResponse]);
      if (res.recommendedProducts?.length) {
        setImpressionsByTurn((prev) => ({ ...prev, [res.agentResponse.id]: res.recommendedProducts }));
      }
      if (res.preferenceState) setState(res.preferenceState);
      if (res.conflicts?.length) setConflicts((prev) => [...prev, ...res.conflicts]);
      if (res.replySuggestions?.length) {
        setChipSuggestions(res.replySuggestions); // 구버전 백엔드 호환(인라인 제공 시 그대로)
      } else {
        setChipSuggestions(null);
        loadChipSuggestions();
      }
    } catch (e) {
      console.error(e);
      try {
        const d = await api.getSession(sessionId);
        setTurns(d.turns);
        if (d.preferenceState) setState(d.preferenceState);
        setConflicts(d.conflicts);
        showToast(STUDY_UI.chat.reloaded);
        // 연결이 끊겨도 서버는 응답 생성을 완주한다(백엔드 shield) — 잠시 뒤 다시
        // 불러와 완성된 답변을 자동으로 붙인다 (생성 시간 ~20초 커버).
        for (const delay of [8000, 20000]) {
          setTimeout(() => {
            api.getSession(sessionId).then((d2) => {
              setTurns(d2.turns);
              if (d2.preferenceState) setState(d2.preferenceState);
              setConflicts(d2.conflicts);
            }).catch(() => {});
          }, delay);
        }
      } catch {
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
        showToast(STUDY_UI.chat.sendFailed);
      }
    } finally {
      setBusy(false);
    }
  }, [sessionId, loadChipSuggestions]);

  const sendFeedback = useCallback(async (productId: string, payload: FeedbackPayload) => {
    setBusy(true);
    try {
      const res = await api.postFeedback(sessionId, productId, payload.type, payload.reasonCode, payload.reasonText);
      setFeedbackByProduct((prev) => ({ ...prev, [productId]: [...(prev[productId] ?? []), payload.type] }));
      if (res.updatedPreferenceState) setState(res.updatedPreferenceState);
      if (res.newConflicts?.length) setConflicts((prev) => [...prev, ...res.newConflicts]);
      if (res.agentTurn) {
        setTurns((prev) => [...prev, res.agentTurn]);
        if (res.replySuggestions?.length) {
          setChipSuggestions(res.replySuggestions);
        } else {
          setChipSuggestions(null);
          loadChipSuggestions();
        }
      }
      if (payload.type === "purchase") showToast(STUDY_UI.chat.selectedProduct);
    } catch (e) {
      console.error(e);
      showToast(STUDY_UI.chat.feedbackFailed);
    } finally {
      setBusy(false);
    }
  }, [sessionId, loadChipSuggestions]);

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
      showToast(STUDY_UI.chat.conflictFailed);
      return false;
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  // 칩 액션 — 기존 API 그대로 (안 B: edit_label / 안 3: confirm·reject)
  const chipAction = useCallback(async (topicId: string, action: string, manualLabel?: string) => {
    setBusy(true);
    try {
      const res = await api.chipAction(topicId, action, manualLabel);
      setState(res.newPreferenceState);
      if (res.recommendTurn) {
        setTurns((prev) => prev.some((t) => t.id === res.recommendTurn.id)
          ? prev : [...prev, res.recommendTurn]);
        setImpressionsByTurn((prev) => ({
          ...prev,
          [res.recommendTurn.id]: res.recommendedProducts ?? [],
        }));
        setChipSuggestions(null);
        loadChipSuggestions();
      }
      showToast(res.message);
      return true;
    } catch (e) {
      console.error(e);
      showToast(STUDY_UI.chat.criterionFailed);
      return false;
    } finally {
      setBusy(false);
    }
  }, [loadChipSuggestions]);

  const saveChipEdit = useCallback(async (topicId: string, label: string) => {
    const saved = await chipAction(topicId, "edit_label", label);
    if (saved) setEditingChip(null);
    return saved;
  }, [chipAction]);

  // ③ 최종 선택 확정 — 이번 세션에서 본 상품(중복 제거). 정렬: 구매 → 좋아요 → 최근 본 순.
  // 최근 턴부터 도는 이유: 대화가 진행될수록 기준이 다듬어지므로 마지막에 본 상품이
  // 실제 선택일 확률이 높다. 긴 세션(수십 개 노출)에서도 위쪽 몇 개가 유력 후보가 된다.
  const seenProducts = useMemo<SeenProduct[]>(() => {
    const seen = new Set<string>();
    const recent: SeenProduct[] = [];
    for (let i = turns.length - 1; i >= 0; i--) {
      for (const imp of impressionsByTurn[turns[i].id] ?? []) {
        if (seen.has(imp.productId)) continue;
        seen.add(imp.productId);
        const fb = feedbackByProduct[imp.productId] ?? [];
        recent.push({
          productId: imp.productId,
          title: imp.product ? productTitle(imp.product) : "",
          price: imp.product?.price ?? null,
          priceUsd: imp.product ? productUsd(imp.product) : null,
          imageUrl: imp.product?.imageUrl ?? null,
          liked: fb.includes("like"),
          purchased: fb.includes("purchase"),
        });
      }
    }
    return [
      ...recent.filter((p) => p.purchased),
      ...recent.filter((p) => !p.purchased && p.liked),
      ...recent.filter((p) => !p.purchased && !p.liked),
    ];
  }, [turns, impressionsByTurn, feedbackByProduct]);

  const openFinalChoice = () => {
    if (seenProducts.length === 0) {
      // 본 상품이 없으면 고를 것도 없다 — 기록만 남기고 바로 확신 설문으로.
      api.submitFinalChoice(sessionId, { status: "none_suitable", noneReason: "no_products" })
        .catch(console.error);
      setPostSurveyOpen(true);
      return;
    }
    setFinalChoiceOpen(true);
  };

  const confirmFinalChoice = async (payload: FinalChoicePayload) => {
    setFinalSubmitting(true);
    try {
      await api.submitFinalChoice(sessionId, payload);
      setFinalChoiceOpen(false);
      setPostSurveyOpen(true);
    } catch (e) {
      console.error(e);
      showToast(STUDY_UI.chat.saveFailed);
    } finally {
      setFinalSubmitting(false);
    }
  };

  /** 확신 설문 다음 단계 — 기준 감사. A파트(내 기준 나열)는 **세 조건 공통**이므로
   *  추론 기준이 없어도(baseline1) 감사는 항상 연다. B파트만 후보 유무로 갈린다. */
  const proceedAfterPostSurvey = async () => {
    const list = infersIntention
      ? (((await api.criterionCandidates(sessionId, CRITERION_CHECK_MAX))?.criteria ??
          []) as CriterionCandidate[])
      : [];
    setCriteria(list);
    setCriterionOpen(true);
  };

  // 첫 발화 자동 전송 (시작 화면에서 넘어온 것) — dev StrictMode 이중 실행 가드
  const sentFirstRef = useRef(false);
  useEffect(() => {
    if (pendingFirst && !sentFirstRef.current) {
      sentFirstRef.current = true;
      setPendingFirst(null);
      sendMessage(pendingFirst);
    }
  }, [pendingFirst, sendMessage]);

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

  const thinkingSteps = STUDY_UI.chat.thinkingSteps;

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
              <button className="btn px-2 py-0.5 text-[11px]" onClick={() => setEditingChip(null)}>{tr("취소", "Cancel")}</button>
              <button className="btn btn-primary px-2 py-0.5 text-[11px]" onClick={() => saveChipEdit(chip.id, editText)}>{tr("저장", "Save")}</button>
            </div>
          </div>
        ) : (
          <>
            <span className="text-xs font-medium text-[#191919]">{chip.label}</span>
            {/* 확인 상태 — E에서 맞아요 누른 기준은 ✓ 확인됨 (앵커에 확인 기록 반영) */}
            {chip.status === "confirmed" && (
              <span className="ml-1.5 text-[10px] font-semibold text-emerald-700">✓ {tr("확인됨", "Confirmed")}</span>
            )}
            {/* 한 줄 근거 — 이 기준이 어디서 나왔는지 */}
            {chip.displayRationale && (
              <p className="mt-0.5 text-[11px] leading-snug text-[#9aa0a6]">{chip.displayRationale}</p>
            )}
          </>
        )}
      </div>
      {/* 수정은 ours 조건에서만 — 기준을 보여주기만 하는 조건과 구분되는 지점이다 */}
      {allowsCorrection && editingChip !== chip.id && (
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
      {/* 헤더 — 스터디면 마치기(→최종 선택 확정), 프로토타입이면 수정안 배지.
          대화 복사 버튼은 제거(2026-08-11) — 참가자 기능이 아니고, 데이터는 서버에 있다. */}
      <div className="flex items-center justify-between gap-2 border-b border-[#f0f2f4] px-3 py-2.5 sm:px-5 sm:py-3">
        <div className="min-w-0 truncate text-sm font-bold text-[#191919]">
          {STUDY_UI.chat.title}
          {scenarioTitle && <span className="ml-1.5 rounded-md bg-indigo-50 px-2 py-0.5 text-sm font-semibold text-[#4F46E5]">{categoryLabel(scenarioTitle)}</span>}
        </div>
        {study ? (
          <button onClick={openFinalChoice} className="btn btn-primary shrink-0 whitespace-nowrap px-2.5 py-1 text-xs">
            <span className="sm:hidden">{STUDY_UI.chat.finishShort}</span>
            <span className="hidden sm:inline">{STUDY_UI.chat.finish}</span>
          </button>
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
              {STUDY_UI.chat.greeting} <span className="text-[#4f46e5]">{STUDY_UI.chat.prompt}</span>
            </div>
            {scenarioTitle && (
              <div className="mt-2 rounded-lg bg-indigo-50/60 px-3 py-2 text-xs leading-relaxed text-[#4b5563]">
                {tr(
                  `'${categoryLabel(scenarioTitle)}'을(를) 구매하는 상황이라고 생각하고, 에이전트와 대화하며 실제로 살 만한 상품을 찾아보세요.`,
                  `Imagine you're shopping for ${categoryLabel(scenarioTitle).toLowerCase()}. Chat with the agent to find one you would actually buy.`,
                )}
              </div>
            )}
            {initialNeed && <div className="mt-2 text-xs text-[#9aa0a6]">{STUDY_UI.chat.example}: &quot;{initialNeed}&quot;</div>}
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
                    {[tr("네, 맞아요", "Yes, that's right"), tr("조금 달라요 — ", "Not quite — ")].map((s) => (
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
            {variant === "e" && showsCriteria && !studySidebar && t.id === latestAgentTurnId && eAskable.length > 0 && !busy && conflicts.length === 0 && (
              <div className="msg-in mt-3">
                <SequentialCriteriaConfirm
                  askable={eAskable}
                  alreadyKnown={eKnown}
                  onConfirm={(id) => chipAction(id, "confirm")}
                  onReject={(id) => chipAction(id, "reject")}
                  onSaveEdit={(id, label) => chipAction(id, "edit_label", label)}
                  onEscapeToChat={(chip) => setChatInput(tr(
                    `‘${chip.label}’ 기준을 이렇게 바꾸고 싶어요: `,
                    `I'd like to revise the “${chip.label}” criterion as follows: `,
                  ))}
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
        {/* 안 E — conflict 발화 + 옵션 칩 (ConflictUtterance — ConflictCard 비사용, manual_edit 제외).
            본실험 사이드바가 켜져 있으면 충돌은 패널의 ConflictCard가 담당한다. */}
        {variant === "e" && showsCriteria && !studySidebar && conflicts.map((c) => (
          <div key={c.id} className="msg-in">
            <ConflictUtterance
              conflict={c}
              onResolve={(optionId) => resolveConflict(c.id, optionId)}
              disabled={busy}
            />
          </div>
        ))}

        {busy && <ThinkingSkeleton steps={thinkingSteps} />}
        {unansweredTurn && (
          <div className="msg-in mx-auto my-2 flex w-full max-w-md items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-900">
            <span>{tr("응답이 완성되지 않았어요.", "The agent's reply didn't finish.")}</span>
            <button
              onClick={retryUnanswered}
              className="shrink-0 rounded-lg bg-[#4f46e5] px-3 py-1.5 font-semibold text-white transition-colors duration-150 hover:bg-[#4338ca]"
            >
              {tr("응답 다시 생성", "Retry the reply")}
            </button>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* 안 B·E — 입력창 위 접힌 한 줄 앵커: "이해한 기준: 착용감 · 가성비 ▾".
          사이드바 없이 '지금 전체 이해'를 한눈에(Q2). E는 확인 상태(✓)까지 앵커에 반영. */}
      {(variant === "b" || variant === "e") && showsCriteria && !studySidebar && core.length > 0 && (
        <div className="border-t border-[#f0f2f4] bg-[#fafbfc] px-5 py-2">
          <button
            onClick={() => { setAnchorOpen((v) => !v); setShowAllCriteria(false); }}
            className="flex w-full items-center gap-1.5 text-left text-xs text-[#5f6368]"
          >
            <span className="font-semibold text-[#9aa0a6]">{tr("이해한 기준:", "Understood criteria:")}</span>
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
          onSend={(msg, src) => { setChatInput(""); sendMessage(msg, src); }}
          disabled={busy}
          loading={busy}
          placeholder={STUDY_UI.chat.inputPlaceholder}
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

  // ----- 본실험 사이드 패널 (2026-08-08) — 이전 사이드바 UI(CurrentStudySession)에서
  // 방사형 그래프 2종(가치·동기)만 뺀 것. 충돌 카드가 위, 기준 칩(맞아요/아니에요·
  // 중요도·수정·근거)이 아래. 근거 클릭은 EvidenceDrawer + DG3 inspect 로깅.
  const studyPanel = (
    <div className="min-h-0 space-y-3 overflow-y-auto pb-4 pr-1">
      {conflicts.map((c) => (
        <ConflictCard
          key={c.id}
          conflict={c}
          onResolve={(optionId, manualText) => resolveConflict(c.id, optionId, manualText)}
          disabled={busy}
        />
      ))}

      <CurrentUnderstandingPanel
        state={state}
        showRadar={false}
        editable={allowsCorrection}
        onChipAction={chipAction}
        onShowEvidence={(id) => { setEvidenceTopic(id); api.logInspect(sessionId, id).catch(() => {}); }}
      />
    </div>
  );

  const withSidebar = variant === "c" || studySidebar;

  return (
    <>
      {/* 카드 높이 = 뷰포트 − 스터디 레이아웃 여백(모바일 py-3=1.5rem, 데스크톱 py-6=3rem).
          헤더가 없으므로 여백만 빼면 카드가 정확히 화면을 채운다(아래 공백 제거). */}
      {withSidebar ? (
        <div className="grid h-[calc(100dvh-1.5rem)] grid-cols-1 gap-4 sm:h-[calc(100dvh-3rem)] lg:grid-cols-[minmax(0,1fr)_440px]">
          {chatCard}
          {studySidebar ? studyPanel : lightPanel}
        </div>
      ) : (
        <div className="mx-auto flex h-[calc(100dvh-1.5rem)] max-w-5xl flex-col sm:h-[calc(100dvh-3rem)]">{chatCard}</div>
      )}

      {withSidebar && (
        <EvidenceDrawer topicId={evidenceTopic} onClose={() => setEvidenceTopic(null)} />
      )}

      {/* 스터디 생명주기 — 마치기 → ③최종 선택 확정 → 사후설문 → ④기준검증 → 완료 화면 */}
      {study && finalChoiceOpen && (
        <FinalChoiceModal
          products={seenProducts}
          submitting={finalSubmitting}
          onConfirm={confirmFinalChoice}
        />
      )}

      {/* 과제직전 설문은 폐지(2026-08-13) — 제품군 지식·초기 명확성은 /study/knowledge
          행렬에서 카테고리 확정 직후 1회 수집한다 (측정 계획 §4). */}
      {study && postSurveyOpen && (
        <SurveyModal
          title={STUDY_UI.surveyModal.postTitle}
          desc={STUDY_UI.surveyModal.postDescription}
          sections={POST_TASK}
          submitLabel={STUDY_UI.surveyModal.next}
          submitting={postSubmitting}
          onSkip={TEST_SURVEY_SKIP ? () => {
            setPostSurveyOpen(false);
            proceedAfterPostSurvey().catch(() => setFinished(true));
          } : undefined}
          onSubmit={async (answers, profile) => {
            setPostSubmitting(true);
            try {
              await api.submitPostSurvey(sessionId, answers, profile);
              setPostSurveyOpen(false);
              await proceedAfterPostSurvey();
            } catch (e) {
              console.error(e);
              showToast(STUDY_UI.surveyModal.saveFailed);
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
          onSkip={TEST_SURVEY_SKIP ? () => { setCriterionOpen(false); setFinished(true); } : undefined}
          onSubmit={async (items, ownCriteria, missingCriteria) => {
            setPostSubmitting(true);
            try {
              await api.submitCriterionValidations(sessionId, items, ownCriteria, missingCriteria);
              setCriterionOpen(false);
              setFinished(true);
            } catch (e) {
              console.error(e);
              showToast(STUDY_UI.surveyModal.saveFailed);
            } finally {
              setPostSubmitting(false);
            }
          }}
        />
      )}

      {study && postStudyOpen && (
        <SurveyModal
          title={STUDY_UI.surveyModal.finalTitle}
          desc={STUDY_UI.surveyModal.finalDescription}
          sections={postStudySectionsFor(condition)}
          submitLabel={STUDY_UI.surveyModal.finalSubmit}
          submitting={postSubmitting}
          onSkip={TEST_SURVEY_SKIP ? () => { setPostStudyOpen(false); router.push("/study/done"); } : undefined}
          onSubmit={async (answers, profile) => {
            setPostSubmitting(true);
            try {
              if (participantId) await api.submitPostStudySurvey(participantId, answers, profile);
              setPostStudyOpen(false);
              router.push("/study/done");
            } catch (e) {
              console.error(e);
              showToast(STUDY_UI.surveyModal.saveFailed);
            } finally {
              setPostSubmitting(false);
            }
          }}
        />
      )}

      {/* 완료 화면 — 큐가 남았으면 다음 쇼핑으로 가는 길 하나뿐이다 (2026-08-11:
          "모든 쇼핑을 마쳤어요" 중도 이탈 버튼 제거 — 4과제 완주가 설계 전제).
          큐를 다 돌았으면 전체종료 설문으로만 이어진다. */}
      {study && finished && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="card max-w-sm p-6 text-center">
            <AgentAvatar className="mx-auto block h-12 w-12" />
            <h2 className="mt-3 text-lg font-bold text-[#191919]">{STUDY_UI.completion.taskTitle}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {queueLeft > 0 ? STUDY_UI.completion.remaining(queueLeft) : STUDY_UI.completion.allTasks}
            </p>
            {/* 큐에 다음 과제가 있으면 그 카테고리로 바로 연다 — 참가자가 매번 고르면
                자기선택 편향이 친숙도 요인과 교락되므로 순서는 설계가 정한다. */}
            {queueLeft > 0 ? (
              <button
                onClick={startNextTask}
                disabled={startingNext}
                className="btn btn-primary mt-4 w-full py-2"
              >
                {startingNext ? STUDY_UI.completion.opening : STUDY_UI.completion.nextTask}
              </button>
            ) : (
              <button
                onClick={() => {
                  setFinished(false);
                  // 이 조건에 물을 섹션이 하나도 없으면 설문 없이 종료 화면으로
                  if (postStudySectionsFor(condition).length === 0) router.push("/study/done");
                  else setPostStudyOpen(true);
                }}
                className="btn btn-primary mt-4 w-full py-2"
              >
                {STUDY_UI.completion.finalSurvey}
              </button>
            )}
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
