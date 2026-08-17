// Prolific 연동 (2026-08-19) — 모집 파라미터 캡처·보관 + 완료 리다이렉트.
//
// 모집 URL: https://<host>/study/survey?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
// 파라미터는 첫 진입에서 sessionStorage로 옮겨 전체 플로우(튜토리얼→과제 4개→최종 설문)를
// 살아남는다. 완료 코드는 빌드타임 env — 미설정이면 모든 동작이 기존과 동일(내부 테스트 경로).
const KEY = "vc:prolific";

export type ProlificParams = { pid?: string; studyId?: string; sessionId?: string };

/** 현재 URL의 Prolific 파라미터를 sessionStorage에 저장하고 돌려준다 (첫 진입에서 호출). */
export function captureProlificParams(): ProlificParams {
  if (typeof window === "undefined") return {};
  const q = new URLSearchParams(window.location.search);
  const fresh: ProlificParams = {
    pid: q.get("PROLIFIC_PID") || undefined,
    studyId: q.get("STUDY_ID") || undefined,
    sessionId: q.get("SESSION_ID") || undefined,
  };
  if (fresh.pid) {
    sessionStorage.setItem(KEY, JSON.stringify(fresh));
    // PID가 주소창·히스토리·스크린샷에 남지 않게 캡처 직후 URL에서 제거한다
    // (저장은 이미 끝났으므로 새로고침에도 안전).
    window.history.replaceState(null, "", window.location.pathname);
    return fresh;
  }
  return getProlificParams();
}

/** 저장된 Prolific 파라미터 (없으면 {}). */
export function getProlificParams(): ProlificParams {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(sessionStorage.getItem(KEY) || "{}");
  } catch {
    return {};
  }
}

export function isProlificParticipant(): boolean {
  return !!getProlificParams().pid;
}

const completionUrl = (code: string) => `https://app.prolific.com/submissions/complete?cc=${code}`;

/** 정상 완료 복귀 URL — 완료 코드 env 미설정이거나 Prolific 참가자가 아니면 null. */
export function prolificCompletionUrl(): string | null {
  const code = process.env.NEXT_PUBLIC_PROLIFIC_COMPLETION_CODE;
  return code && isProlificParticipant() ? completionUrl(code) : null;
}

/** 부적격(동의 거부·스크리닝 탈락) 복귀 URL — screenout 코드 기준. */
export function prolificScreenoutUrl(): string | null {
  const code = process.env.NEXT_PUBLIC_PROLIFIC_SCREENOUT_CODE;
  return code && isProlificParticipant() ? completionUrl(code) : null;
}
