"use client";

// 스터디 시작 화면 — 프리뷰(/study/preview)에서 확정된 리디자인을 본선에 반영 (2026-07-02).
// 중앙 입력창(ChatComposer) + 시나리오 칩: 칩을 누르면 그 시나리오가 선택되고 예시 발화가
// 입력창에 채워진다(수정 가능). 전송하면 세션 생성 → 첫 메시지는 sessionStorage로 세션
// 페이지에 넘겨 자동 전송(낙관적 UI 유지). 칩 없이 보내면 자유 대화(custom) 세션.
// 회상 인터뷰 기반 직접 입력(FS1 연구자 도구)은 하단 토글로 유지.
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Scenario } from "@/lib/types";
import ChatComposer from "@/components/chat/ChatComposer";

export default function NewSessionPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [participantId, setParticipantId] = useState<string>(""); // 설문/튜토리얼에서 넘어온 pid
  const [selected, setSelected] = useState<Scenario | null>(null);
  const [composeText, setComposeText] = useState("");
  const [creating, setCreating] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [customTitle, setCustomTitle] = useState("");
  const [customContext, setCustomContext] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    // 사전 설문 제출 후 넘어온 참가자 자동 선택 (?pid=...)
    const pid = new URLSearchParams(window.location.search).get("pid");
    if (pid) setParticipantId(pid);
    api.scenarios().then((d) => setScenarios(d.scenarios)).catch(console.error);
  }, []);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  // 시나리오 칩 토글 — 선택 + 예시 발화 채움 (같은 칩 다시 누르면 해제)
  const pickScenario = (sc: Scenario) => {
    if (selected?.id === sc.id) {
      setSelected(null);
      setComposeText("");
      return;
    }
    setSelected(sc);
    setComposeText(sc.initialUserNeed);
  };

  // 세션 생성 → 첫 메시지를 세션 페이지에 넘겨 자동 전송 (study condition은 correctable 고정)
  const start = useCallback(async (firstMsg: string) => {
    if (creating || !firstMsg.trim()) return;
    setCreating(true);
    try {
      const custom = customOpen && customContext.trim()
        ? { title: customTitle.trim() || undefined, context: customContext.trim() }
        : selected
          ? undefined
          : { title: "자유 대화" };
      const scenarioId = customOpen && customContext.trim() ? "custom" : selected?.id ?? "custom";
      const res = await api.createSession(scenarioId, "correctable", custom, participantId || undefined);
      sessionStorage.setItem(`vc_first_${res.sessionId}`, firstMsg.trim());
      router.push(`/study/session/${res.sessionId}`);
    } catch (e) {
      console.error(e);
      setCreating(false);
      showToast("세션을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.");
    }
  }, [creating, customOpen, customContext, customTitle, selected, participantId, router]);

  return (
    // 화면 세로 중앙 정렬 (study layout 컨테이너 안)
    <div className="flex min-h-[calc(100vh-9rem)] flex-col items-center justify-center">
      <div className="w-full max-w-2xl px-4">
        {/* 진입 애니메이션 — 타이틀 → 입력창 → 칩 순서로 살짝 시차 (stagger) */}
        <div className="msg-in">
          <h1 className="text-center text-2xl font-bold tracking-tight text-[#191919]">
            <span className="text-[#4f46e5]">에이전트와 쇼핑</span>을 시작해 볼까요?
          </h1>
          <p className="mt-2 text-center text-sm text-[#9aa0a6]">
            찾으시는 걸 입력하거나, 아래 상황에서 골라 바로 시작해 보세요.
          </p>
        </div>

        {/* 직접 입력 — 전송하면 세션 생성 + 첫 메시지 자동 전송 → 대화로 이동 */}
        <div className="msg-in mt-7" style={{ animationDelay: "80ms" }}>
          <ChatComposer
            value={composeText}
            onChange={setComposeText}
            onSend={start}
            disabled={creating}
            loading={creating}
            placeholder="무엇을 찾고 계세요?"
            disclaimer={false}
          />
        </div>

        {/* 시나리오 칩 — 제목만, hover 툴팁 = 예시 발화. 클릭 = 선택 + 입력창 채움 */}
        <div className="msg-in mt-5 flex flex-wrap justify-center gap-2" style={{ animationDelay: "160ms" }}>
          {scenarios.map((sc) => (
            <button
              key={sc.id}
              onClick={() => pickScenario(sc)}
              disabled={creating}
              title={sc.initialUserNeed}
              className={`rounded-full border px-4 py-2 text-sm transition-colors duration-150 active:scale-[0.97] disabled:opacity-50 ${
                selected?.id === sc.id
                  ? "border-[#4f46e5] bg-[#eef2ff] text-[#4f46e5]"
                  : "border-[#e4e8eb] bg-white text-[#404040] hover:border-[#4f46e5] hover:text-[#4f46e5]"
              }`}
            >
              {sc.title}
            </button>
          ))}
        </div>

        {/* 회상 인터뷰 기반 직접 입력 (FS1 연구자 도구) — 필요할 때만 펼침 */}
        <div className="msg-in mt-8 text-center" style={{ animationDelay: "240ms" }}>
          <button
            onClick={() => setCustomOpen((v) => !v)}
            disabled={creating}
            className="text-xs text-[#b0b8c1] underline-offset-2 transition-colors hover:text-[#4f46e5] hover:underline"
          >
            직접 입력 (회상 인터뷰 기반)
          </button>
          {customOpen && (
            <div className="msg-in mt-3 space-y-2 rounded-xl bg-[#f5f6f8] p-4 text-left">
              <input
                value={customTitle}
                onChange={(e) => setCustomTitle(e.target.value)}
                placeholder="시나리오 제목 (선택) — 예: 부모님 드릴 안마기"
                className="w-full rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none"
              />
              <textarea
                value={customContext}
                onChange={(e) => setCustomContext(e.target.value)}
                rows={3}
                placeholder={'회상 인터뷰에서 나온 쇼핑 맥락을 적어주세요.\n예: "친구에게 줄 스마트워치를 찾고 있었음. 친구는 운동을 좋아하지만, 참가자는 브랜드를 잘 모름."'}
                className="w-full resize-none rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none"
              />
              <p className="text-[11px] text-[#9aa0a6]">
                맥락을 적고, 위 입력창에 첫 발화를 입력해 전송하면 이 맥락으로 시작합니다.
              </p>
            </div>
          )}
        </div>

        <p className="mt-8 text-center text-[11px] text-[#b0b8c1]">
          AI 답변으로 정확하지 않은 정보가 포함될 수 있어요.
        </p>

        {toast && (
          <div className="msg-in fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-[#191919] px-5 py-3 text-xs text-white shadow-xl">
            {toast}
          </div>
        )}
      </div>
    </div>
  );
}
