"use client";

// 본실험 종료 화면 — 전체 종료 설문까지 제출한 참가자가 도착하는 마지막 페이지.
// 여기서 더 진행할 곳이 없어야 한다(세션으로 되돌아가면 사후 응답이 오염될 수 있다).
// Prolific 참가자(2026-08-19): completion code env가 있으면 자동으로 Prolific에
// 복귀시킨다 — 수동 버튼도 함께 둔다(자동 이동이 팝업 차단 등으로 막힐 때의 안전망).
import { useEffect, useState } from "react";
import AgentAvatar from "@/components/chat/AgentAvatar";
import { prolificCompletionUrl } from "@/lib/prolific";
import { STUDY_UI } from "@/lib/studyI18n";

export default function StudyDonePage() {
  const [prolificUrl, setProlificUrl] = useState<string | null>(null);

  useEffect(() => {
    const url = prolificCompletionUrl();
    setProlificUrl(url);
    if (url) {
      const t = setTimeout(() => { window.location.href = url; }, 3000);
      return () => clearTimeout(t);
    }
  }, []);

  return (
    <div className="flex min-h-[70dvh] items-center justify-center px-4">
      <div className="card max-w-sm p-7 text-center">
        <AgentAvatar className="mx-auto block h-14 w-14" />
        <h1 className="mt-4 text-lg font-bold text-[#191919]">{STUDY_UI.completion.doneTitle}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">
          {STUDY_UI.completion.doneBody}
        </p>
        {prolificUrl ? (
          <>
            <p className="mt-4 text-xs text-slate-400">{STUDY_UI.completion.prolificRedirecting}</p>
            <a href={prolificUrl} className="btn btn-primary mt-3 inline-block px-5 py-2">
              {STUDY_UI.completion.prolificReturn}
            </a>
          </>
        ) : (
          <p className="mt-4 text-xs text-slate-400">{STUDY_UI.completion.close}</p>
        )}
      </div>
    </div>
  );
}
