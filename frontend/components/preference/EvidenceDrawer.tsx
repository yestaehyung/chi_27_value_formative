"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AnchorMapping, Concept, EvidenceItem, Topic } from "@/lib/types";

const TYPE_ICON: Record<string, string> = {
  turn: "💬", feedback: "👆", product_cue: "🏷️", unknown: "•",
};

export default function EvidenceDrawer({
  topicId,
  onClose,
}: {
  topicId: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<{
    topic: Topic; evidence: EvidenceItem[];
    anchorMappings: AnchorMapping[]; concepts: Concept[];
  } | null>(null);

  useEffect(() => {
    if (!topicId) { setData(null); return; }
    api.topicEvidence(topicId).then(setData).catch(console.error);
  }, [topicId]);

  if (!topicId) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onClick={onClose}>
      <div
        className="msg-in h-full w-full max-w-md overflow-y-auto rounded-l-2xl border-l border-[#e4e8eb] bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <h3 className="text-base font-bold">왜 이렇게 이해했나요?</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>

        {!data ? (
          <div className="mt-8 text-center text-sm text-slate-400">불러오는 중…</div>
        ) : (
          <div className="mt-4 space-y-5">
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-sm font-semibold">{data.topic.label}</div>
              <div className="mt-1 text-xs text-slate-500">{data.topic.description}</div>
              <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-slate-400">
                <span className="rounded bg-white px-1.5 py-0.5">source: {data.topic.source}</span>
                <span className="rounded bg-white px-1.5 py-0.5">status: {data.topic.status}</span>
                <span className="rounded bg-white px-1.5 py-0.5">confidence: {data.topic.confidence.toFixed(2)}</span>
                <span className="rounded bg-white px-1.5 py-0.5">{data.topic.explicitness}</span>
              </div>
            </div>

            <section>
              <h4 className="text-xs font-bold uppercase tracking-wide text-slate-400">근거</h4>
              <ol className="mt-2 space-y-2">
                {data.evidence.map((ev, i) => (
                  <li key={ev.id + i} className="rounded-lg border border-slate-100 p-2.5 text-xs">
                    <div className="flex items-center gap-1.5 text-[10px] font-medium text-slate-400">
                      <span>{TYPE_ICON[ev.type] ?? "•"}</span>
                      <span>{i + 1}. {ev.type === "turn" ? "직접 하신 말" : ev.type === "feedback" ? `피드백 (${ev.feedbackType})` : "상품 단서"}</span>
                      {ev.productTitle && <span className="text-slate-500">— {ev.productTitle}</span>}
                    </div>
                    <div className="mt-1 text-slate-700">&quot;{ev.quote}&quot;</div>
                  </li>
                ))}
              </ol>
            </section>

            {data.concepts.length > 0 && (
              <section>
                <h4 className="text-xs font-bold uppercase tracking-wide text-slate-400">연결된 concept</h4>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {data.concepts.map((c) => (
                    <span key={c.id} className="rounded-full bg-[#ecfdf5] px-2.5 py-1 text-xs font-medium text-[#047857]">
                      {c.label}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {data.anchorMappings.length > 0 && (
              <section>
                <h4 className="text-xs font-bold uppercase tracking-wide text-slate-400">가치 anchor</h4>
                <div className="mt-2 space-y-1.5">
                  {data.anchorMappings.map((a) => (
                    <div key={a.id} className="rounded-lg border border-slate-100 p-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-orange-600">{a.anchor}</span>
                        <span className="text-slate-400">{a.score.toFixed(2)} · {a.confidence}</span>
                      </div>
                      {a.rationale && <div className="mt-0.5 text-slate-500">{a.rationale}</div>}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
