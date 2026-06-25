import { Turn } from "@/lib/types";
import AgentAvatar from "./AgentAvatar";

const ROLE_LABEL: Record<string, string> = {
  user: "나",
  user_agent: "User Agent",
  service_agent: "쇼핑 에이전트",
  system: "시스템",
};

// showMeta: 연구용 라벨(dialogueActs·agentAction) 노출 여부.
// 기본 false → 참가자 화면(§36: 추론·내부 코드 비노출). 연구자 replay에서만 true.
// 에이전트 답변 렌더 — 가독성 향상.
//  · 빈 줄(\n\n)로 문단 분리 → 문단 간 간격
//  · 추천 항목("A. … B. … C. …")이 한 줄로 붙어 나오면 항목 앞에서 줄바꿈
//  · 단일 줄바꿈(\n)은 보존
function AgentText({ content }: { content: string }) {
  // "A. " "B. " 같은 항목 표식 앞에 줄바꿈 삽입 (문장 끝 뒤에 올 때만 — 오검출 방지)
  const withItemBreaks = content.replace(/([.!?…)\]]\s)([A-E]\.\s)/g, "$1\n$2");
  const paragraphs = withItemBreaks.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return (
    <div className="space-y-2.5">
      {paragraphs.map((para, i) => (
        <p key={i} className="whitespace-pre-wrap">{para}</p>
      ))}
    </div>
  );
}

export default function MessageBubble({ turn, showMeta = false }: { turn: Turn; showMeta?: boolean }) {
  const isUser = turn.role === "user" || turn.role === "user_agent";

  if (isUser) {
    // user bubble — brand indigo
    return (
      <div className="msg-in flex justify-end">
        <div className="max-w-[80%]">
          <div className="mb-1 flex items-center justify-end gap-2 text-[11px] text-[#9aa0a6]">
            {showMeta && turn.dialogueActs?.length > 0 && (
              <span className="rounded bg-[#eef2ff] px-1.5 py-0.5 font-mono text-[10px] text-[#4f46e5]">
                {turn.dialogueActs.join("·")}
              </span>
            )}
            <span>{ROLE_LABEL[turn.role] ?? turn.role}</span>
          </div>
          <div
            className="whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed text-white"
            style={{ backgroundColor: "var(--brand, #4f46e5)" }}
          >
            {turn.content}
          </div>
        </div>
      </div>
    );
  }

  // agent — white bubble with thin border + "N" mark avatar
  return (
    <div className="msg-in flex gap-2.5">
      <AgentAvatar className="mt-1 h-7 w-7" />
      <div className="min-w-0 max-w-[85%]">
        <div className="mb-1 flex items-center gap-2 text-[11px] text-[#9aa0a6]">
          <span className="font-medium text-[#404040]">{ROLE_LABEL[turn.role] ?? turn.role}</span>
          {showMeta && turn.agentAction && (
            <span className="rounded bg-[#f5f6f8] px-1.5 py-0.5 font-mono text-[10px] text-[#787c82]">
              {turn.agentAction}
            </span>
          )}
        </div>
        <div className="rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-3 text-sm leading-[1.7] text-[#191919]">
          <AgentText content={turn.content} />
        </div>
      </div>
    </div>
  );
}
