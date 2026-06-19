import { Turn } from "@/lib/types";
import AgentAvatar from "./AgentAvatar";

const ROLE_LABEL: Record<string, string> = {
  user: "나",
  user_agent: "User Agent",
  service_agent: "쇼핑 에이전트",
  system: "시스템",
};

export default function MessageBubble({ turn }: { turn: Turn }) {
  const isUser = turn.role === "user" || turn.role === "user_agent";

  if (isUser) {
    // user bubble — brand indigo
    return (
      <div className="msg-in flex justify-end">
        <div className="max-w-[80%]">
          <div className="mb-1 flex items-center justify-end gap-2 text-[11px] text-[#9aa0a6]">
            {turn.intentLabels?.length > 0 && (
              <span className="rounded bg-[#eef2ff] px-1.5 py-0.5 font-mono text-[10px] text-[#4f46e5]">
                {turn.intentLabels.join("·")}
              </span>
            )}
            <span>{ROLE_LABEL[turn.role] ?? turn.role}</span>
          </div>
          <div className="whitespace-pre-wrap rounded-2xl rounded-br-md bg-[#4f46e5] px-4 py-2.5 text-sm leading-relaxed text-white">
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
          {turn.agentAction && (
            <span className="rounded bg-[#f5f6f8] px-1.5 py-0.5 font-mono text-[10px] text-[#787c82]">
              {turn.agentAction}
            </span>
          )}
        </div>
        <div className="whitespace-pre-wrap rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-2.5 text-sm leading-relaxed text-[#191919]">
          {turn.content}
        </div>
      </div>
    </div>
  );
}
