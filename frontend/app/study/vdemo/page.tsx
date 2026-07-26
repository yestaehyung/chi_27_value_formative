"use client";

// 안 E 위젯 데모 (2026-07-21) — 튜토리얼 픽스처(더미 데이터)로 안 E의 상태들을
// 한 화면에서 본다. 전부 로컬 시뮬레이션(서버/DB 무접촉)이라 반복 클릭 테스트 가능.
// 각 케이스는 [리셋]으로 초기 상태 복원.

import { ReactNode, useState } from "react";
import { PreferenceChip } from "@/lib/types";
import MessageBubble from "@/components/chat/MessageBubble";
import SequentialCriteriaConfirm from "@/components/study/SequentialCriteriaConfirm";
import ConflictUtterance from "@/components/study/ConflictUtterance";
import AgentAvatar from "@/components/chat/AgentAvatar";
import ProductCard from "@/components/products/ProductCard";
import ProductCarousel from "@/components/products/ProductCarousel";
import ChipTypeBadge from "@/components/preference/ChipTypeBadge";
import { tutorialTurns, tutorialImpressions, tutorialPreferenceState, tutorialConflict } from "@/lib/tutorialFixtures";

const FIXTURE_CHIPS = tutorialPreferenceState.userVisibleSummary.chips;
// 안 E 순차용 — 확실한 것(평점, must_have)은 알림, 애매한 것(예산 uncertain + 나머지)만 질문
const E_KNOWN: PreferenceChip[] = [FIXTURE_CHIPS[0]];
const E_ASKABLE: PreferenceChip[] = [
  FIXTURE_CHIPS[3], // 예산 20만원 이하? (uncertain)
  FIXTURE_CHIPS[1], // 너무 저렴해 보이지 않기 (important)
  { id: "t_avoid", label: "커널형(인이어)", type: "avoid", userEditable: true, evidenceCount: 1,
    displayRationale: "귀에 꽂는 타입은 싫다고 하셨어요." }, // 피하기 (avoid)
];

const wait = (ms = 450) => new Promise<boolean>((r) => setTimeout(() => r(true), ms));

// 안 E 순차 확인 시뮬레이터 — 위젯이 진행 상태를 소유하므로 핸들러는 지연 후 true만.
function SimSequential() {
  const ok = async () => wait();
  return (
    <SequentialCriteriaConfirm
      askable={E_ASKABLE}
      alreadyKnown={E_KNOWN}
      onConfirm={ok}
      onReject={ok}
      onSaveEdit={ok}
      onEscapeToChat={() => {}}
    />
  );
}

// ② 입력창 위 앵커 — 사이드바 없이 '지금 내 기준 전체'를 한 줄로 늘 보여준다(안 B에서 가져옴).
// 대화가 진행되며 확인된 기준은 ✓로 앵커에 반영. 접힌 한 줄, 탭하면 펼침.
function AnchorBar({ items }: { items: { label: string; confirmed: boolean }[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-[#f0f2f4] bg-[#fafbfc] px-3 py-2">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-1.5 text-left text-xs text-[#5f6368]">
        <span className="shrink-0 font-semibold text-[#9aa0a6]">이해한 기준:</span>
        <span className="min-w-0 flex-1 truncate font-medium text-[#191919]">
          {items.map((it) => (it.confirmed ? "✓ " : "") + it.label).join(" · ")}
        </span>
        <span className="shrink-0 text-[#9aa0a6]">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="mt-1 space-y-1 border-t border-[#f0f2f4] pt-1.5">
          {items.map((it, i) => (
            <div key={i} className="flex items-center gap-1.5 text-xs">
              {it.confirmed && <span className="text-[10px] font-semibold text-emerald-700">✓</span>}
              <span className="font-medium text-[#191919]">{it.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 순차 확인 → 후속 대화 전체 흐름. 확인 결과를 기록해두고, 완료되면 에이전트가
// (1) "정리하면 이렇게 이해했어요" 인라인 요약 + (2) 그 기준으로 다시 추천을 이어붙인다.
// 그리고 하단에 ② 앵커를 늘 띄워 '지금 전체 이해'를 사이드바 없이 한눈에 보게 한다.
type Outcome = { kind: "confirmed" | "edited" | "handoff"; label: string };
function SimSequentialFlow() {
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [done, setDone] = useState(false);
  const record = (id: string, kind: Outcome["kind"], label: string) =>
    setOutcomes((o) => ({ ...o, [id]: { kind, label } }));

  // 최종 확정 기준 = 확실한 것(known) + 확인/수정된 것 (거부·대화이관 제외)
  const finalCriteria = [
    ...E_KNOWN.map((c) => ({ label: c.label, type: c.type })),
    ...E_ASKABLE.filter((c) => outcomes[c.id] && outcomes[c.id].kind !== "handoff").map((c) => ({
      label: outcomes[c.id].kind === "edited" ? outcomes[c.id].label : c.label,
      type: c.type,
    })),
  ];

  // ② 앵커 항목 — known(이미 반영=✓) + 확인/수정된 askable. 대화 진행에 따라 실시간 갱신.
  const anchorItems = [
    ...E_KNOWN.map((c) => ({ label: c.label, confirmed: true })),
    ...E_ASKABLE.filter((c) => outcomes[c.id] && outcomes[c.id].kind !== "handoff").map((c) => ({
      label: outcomes[c.id].kind === "edited" ? outcomes[c.id].label : c.label,
      confirmed: outcomes[c.id].kind === "confirmed",
    })),
  ];

  return (
    <div className="space-y-4">
      <SequentialCriteriaConfirm
        askable={E_ASKABLE}
        alreadyKnown={E_KNOWN}
        onConfirm={async (id) => { await wait(); const c = E_ASKABLE.find((x) => x.id === id)!; record(id, "confirmed", c.label); return true; }}
        onReject={async () => { await wait(); return true; }}
        onSaveEdit={async (id, label) => { await wait(); record(id, "edited", label); return true; }}
        onEscapeToChat={(chip) => record(chip.id, "handoff", chip.label)}
        onComplete={() => setDone(true)}
      />

      {done && (
        <div className="msg-in flex gap-2.5">
          <AgentAvatar className="mt-1 h-7 w-7" />
          <div className="min-w-0 flex-1 sm:max-w-[85%] space-y-3">
            <div className="mb-1 text-[11px] font-medium text-[#404040]">쇼핑 에이전트</div>
            <div className="rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-3">
              <p className="text-pretty text-sm leading-[1.7] text-[#191919]">
                정리하면, 지금 이렇게 이해하고 있어요:
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {finalCriteria.map((c, i) => (
                  <span key={i} className="inline-flex items-center gap-1.5 rounded-full border border-[#e4e8eb] bg-[#fafbfc] px-2.5 py-1 text-[12px] text-[#404040]">
                    <ChipTypeBadge type={c.type} />
                    {c.label}
                  </span>
                ))}
              </div>
              <p className="mt-2.5 text-pretty text-sm leading-[1.7] text-[#191919]">
                이 기준으로 다시 골라봤어요.
              </p>
            </div>
            <ProductCarousel>
              {tutorialImpressions.slice(0, 2).map((imp, i) => (
                <ProductCard key={imp.id} impression={imp} index={i} givenFeedback={[]} onFeedback={() => {}} disabled />
              ))}
            </ProductCarousel>
          </div>
        </div>
      )}

      {/* ② 입력창 위 앵커 — 대화가 진행돼도 늘 보이는 '지금 내 기준' 한 줄 (확인되면 ✓) */}
      <div className="border-t border-[#f0f2f4] pt-3">
        <p className="mb-1.5 text-[11px] font-semibold text-[#9aa0a6]">
          ② 입력창 위 앵커 — 사이드바 없이 &lsquo;지금 전체 이해&rsquo;를 한눈에 (확인하면 ✓ 반영)
        </p>
        <AnchorBar items={anchorItems} />
      </div>
    </div>
  );
}

// 해소 후 에이전트 발화
function ResolvedBubble({ label }: { label: string }) {
  return (
    <div className="flex gap-2.5">
      <AgentAvatar className="mt-1 h-7 w-7" />
      <div className="min-w-0 max-w-[85%]">
        <div className="mb-1 text-[11px] font-medium text-[#404040]">쇼핑 에이전트</div>
        <div className="rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-3 text-sm leading-[1.7] text-[#191919]">
          알겠어요 — &ldquo;{label}&rdquo;로 반영해서 다음 추천부터 적용할게요.
        </div>
      </div>
    </div>
  );
}

// 안 E conflict 시뮬레이터 — 옵션 클릭 → 해소 발화로 교체
function SimConflict() {
  const [resolvedLabel, setResolvedLabel] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (resolvedLabel) return <ResolvedBubble label={resolvedLabel} />;
  return (
    <ConflictUtterance
      conflict={tutorialConflict}
      disabled={busy}
      onResolve={async (optionId) => {
        setBusy(true);
        await wait();
        const opt = tutorialConflict.suggestedResolutions.find((o) => o.id === optionId);
        setResolvedLabel(opt?.label ?? optionId);
      }}
    />
  );
}

function Case({ title, desc, children }: { title: string; desc: string; children: ReactNode }) {
  const [key, setKey] = useState(0);
  return (
    <section className="card p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-[#191919]">{title}</h2>
          <p className="mt-0.5 text-xs text-[#9aa0a6]">{desc}</p>
        </div>
        <button onClick={() => setKey((k) => k + 1)} className="btn shrink-0 px-2.5 py-1 text-xs">
          리셋
        </button>
      </div>
      <div key={key}>{children}</div>
    </section>
  );
}

export default function VariantWidgetDemoPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 pb-10">
      <div>
        <h1 className="text-xl font-bold text-[#191919]">안 E 위젯 데모</h1>
        <p className="mt-1 text-sm text-[#606060]">
          더미 데이터 로컬 시뮬레이션 — 서버에 아무것도 쓰지 않으니 마음껏 반복 테스트하세요.
          버튼 반응 지연(450ms)은 실제 API 왕복을 흉내 낸 것입니다.
        </p>
      </div>

      <Case
        title="안 E — 전체 흐름 (순차 확인 → 후속 추천)"
        desc="채팅 맥락 → 한 개씩 확인 → 다 끝나면 에이전트가 '정리하면 이렇게 이해했어요' 요약 + 그 기준으로 다시 추천까지. 끝까지 클릭해보세요."
      >
        <div className="space-y-4">
          {tutorialTurns.slice(0, 2).map((t) => (
            <MessageBubble key={t.id} turn={t} />
          ))}
          <SimSequentialFlow />
        </div>
      </Case>

      <Case
        title="안 E — 순차 확인만 (한 개씩)"
        desc="확실한 건 '이미 반영해뒀어요'로 알림 · 애매한 것만 한 개씩 발화로 물음 · 답하면 다음 질문 · 달라요 → 인라인 수정 + '직접 말씀할게요' 탈출구"
      >
        <SimSequential />
      </Case>

      <Case
        title="안 E — 충돌 발화 + 옵션 칩"
        desc="기준이 부딪힐 때 — 발화 형식으로, [지금까지 ↔ 방금] 대비와 각 선택지 결과 미리보기 포함. 옵션 클릭 → 해소 발화까지"
      >
        <SimConflict />
      </Case>
    </div>
  );
}
