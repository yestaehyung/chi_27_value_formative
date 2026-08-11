"use client";

// 본실험 종료 화면 — 전체 종료 설문까지 제출한 참가자가 도착하는 마지막 페이지.
// 여기서 더 진행할 곳이 없어야 한다(세션으로 되돌아가면 사후 응답이 오염될 수 있다).
import AgentAvatar from "@/components/chat/AgentAvatar";
import { STUDY_UI } from "@/lib/studyI18n";

export default function StudyDonePage() {
  return (
    <div className="flex min-h-[70dvh] items-center justify-center px-4">
      <div className="card max-w-sm p-7 text-center">
        <AgentAvatar className="mx-auto block h-14 w-14" />
        <h1 className="mt-4 text-lg font-bold text-[#191919]">{STUDY_UI.completion.doneTitle}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">
          {STUDY_UI.completion.doneBody}
        </p>
        <p className="mt-4 text-xs text-slate-400">{STUDY_UI.completion.close}</p>
      </div>
    </div>
  );
}
