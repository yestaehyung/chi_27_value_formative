"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Scenario } from "@/lib/types";

export default function NewSessionPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [participantId, setParticipantId] = useState<string>(""); // 설문/튜토리얼에서 넘어온 pid
  const [creating, setCreating] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [customTitle, setCustomTitle] = useState("");
  const [customContext, setCustomContext] = useState("");

  useEffect(() => {
    // 사전 설문 제출 후 넘어온 참가자 자동 선택 (?pid=...)
    const pid = new URLSearchParams(window.location.search).get("pid");
    if (pid) setParticipantId(pid);
    api.scenarios().then((d) => setScenarios(d.scenarios)).catch(console.error);
  }, []);

  // 시나리오 선택 즉시 세션 생성 후 이동 (study condition은 correctable 고정)
  const enter = async (scenarioId: string, custom?: { title?: string; context?: string }) => {
    if (creating) return;
    setCreating(true);
    try {
      const res = await api.createSession(scenarioId, "correctable", custom, participantId || undefined);
      router.push(`/study/session/${res.sessionId}`);
    } catch (e) {
      console.error(e);
      setCreating(false);
      alert("세션을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.");
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">에이전트와 쇼핑을 시작해 볼까요?</h1>
        <p className="mt-1 text-sm text-slate-500">
          시나리오를 선택하면 바로 대화가 시작됩니다. 어떤 기준이 중요한지는 직접 말하지 않아도 돼요 —
          제가 대화와 반응을 보고 짐작하면, 맞는지 확인하고 고쳐주시면 돼요.
        </p>
      </div>

      <section className="card border-dashed border-[#4f46e5] bg-[#eef2ff] p-4">
        <button
          onClick={() =>
            enter("custom", {
              title: "자유 대화",
              context: "시나리오 없이 자유롭게 상품을 물어보는 세션.",
            })
          }
          disabled={creating}
          className="btn btn-primary w-full py-2.5"
        >
          {creating ? "세션 생성 중…" : "바로 대화 시작 (시나리오 없이)"}
        </button>
        <p className="mt-2 text-xs text-slate-500">
          시나리오 선택 없이 바로 대화. &quot;무선 이어폰 추천해줘&quot;처럼 찾으시는 걸 자유롭게 입력해 보세요.
        </p>
      </section>

      <section className="card p-5">
        <h2 className="text-sm font-semibold">시나리오를 선택하세요</h2>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {scenarios.map((s) => (
            <button
              key={s.id}
              onClick={() => enter(s.id)}
              disabled={creating}
              className="rounded-xl border border-[#e4e8eb] bg-white p-3.5 text-left text-sm transition-colors duration-150 hover:border-[#4f46e5] hover:bg-[#eef2ff] disabled:opacity-50"
            >
              <div className="font-medium">{s.title}</div>
              <div className="mt-1 text-xs text-slate-500">{s.initialUserNeed}</div>
            </button>
          ))}
          {/* 회상 인터뷰 기반 자유 시나리오 (FS1) */}
          <button
            onClick={() => setCustomOpen((v) => !v)}
            disabled={creating}
            className={`rounded-xl border border-dashed p-3.5 text-left text-sm transition-colors duration-150 disabled:opacity-50 ${
              customOpen
                ? "border-[#4f46e5] bg-[#eef2ff]"
                : "border-[#c9cdd2] bg-white hover:border-[#4f46e5]"
            }`}
          >
            <div className="font-medium">직접 입력 (회상 인터뷰 기반)</div>
            <div className="mt-1 text-xs text-slate-500">
              참가자의 실제 쇼핑 경험을 초기 맥락으로 사용합니다
            </div>
          </button>
        </div>

        {customOpen && (
          <div className="msg-in mt-3 space-y-2 rounded-xl bg-[#f5f6f8] p-4">
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
            <button
              onClick={() =>
                customContext.trim()
                  ? enter("custom", { title: customTitle.trim() || undefined, context: customContext.trim() })
                  : alert("쇼핑 맥락을 입력해 주세요.")
              }
              disabled={creating}
              className="btn btn-primary w-full py-2"
            >
              {creating ? "세션 생성 중…" : "이 맥락으로 시작하기"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
