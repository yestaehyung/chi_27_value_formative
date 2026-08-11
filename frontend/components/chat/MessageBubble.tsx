import { Turn } from "@/lib/types";
import AgentAvatar from "./AgentAvatar";
import StructuredText from "./StructuredText";
import { STUDY_UI } from "@/lib/studyI18n";

const ROLE_LABEL: Record<string, string> = {
  user: STUDY_UI.chat.user,
  user_agent: "User Agent",
  service_agent: STUDY_UI.chat.agent,
  system: STUDY_UI.chat.system,
};

// showMeta: 연구용 라벨(dialogueActs·agentAction) 노출 여부.
// 기본 false → 참가자 화면(§36: 추론·내부 코드 비노출). 연구자 replay에서만 true.
// 에이전트 답변 렌더는 StructuredText가 담당한다 (2026-08-06) — 문단에 더해
// 불릿·번호 목록·표·굵게를 렌더한다. 이전에는 whitespace-pre-wrap 평문이었고
// 백엔드가 마크다운을 제거했다.

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
          <StructuredText content={turn.content} />
        </div>
      </div>
    </div>
  );
}
