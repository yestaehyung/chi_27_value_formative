// 쇼핑 에이전트(Service Agent) 프로필 아바타 — DiceBear "dylan" (seed 고정 → 항상 같은 얼굴).
// 사람 페르소나는 notionists, 에이전트는 dylan 으로 시각적으로 구분한다.
const AGENT_AVATAR_URL =
  "https://api.dicebear.com/9.x/dylan/svg?seed=Eden&backgroundColor=c4b5fd";

export default function AgentAvatar({ className = "h-7 w-7" }: { className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={AGENT_AVATAR_URL}
      alt="쇼핑 에이전트"
      className={`shrink-0 rounded-full bg-[#c4b5fd] object-cover ${className}`}
    />
  );
}
