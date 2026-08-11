import { NextRequest, NextResponse } from "next/server";

// 스터디 배포 분리 (2026-07-02) + 진입점 단일화 (2026-08-11).
// - `/` → 사전 설문으로 즉시 리다이렉트 — **모드와 무관하게 항상**. 연구자 런처는 더
//   쓰지 않으므로(참가자 흐름이 곧 제품) 웹에 접속하면 바로 pre-survey가 뜬다.
// - 연구자 표면(/simulate·/research·/pscon 등)은 APP_MODE=study 에서만 404 rewrite —
//   로컬 개발에선 직접 URL로는 여전히 열린다 (데이터 리플레이·디버깅용, 삭제 아님).
// 백엔드도 같은 모드(VC_APP_MODE=study)로 해당 라우터를 잠근다 (이중 차단).
const STUDY_MODE = process.env.APP_MODE === "study";

export function middleware(req: NextRequest) {
  if (req.nextUrl.pathname === "/") {
    return NextResponse.redirect(new URL("/study/survey", req.url));
  }
  if (!STUDY_MODE) return NextResponse.next();
  // 존재하지 않는 경로로 rewrite → Next 404 렌더 (URL은 유지)
  return NextResponse.rewrite(new URL("/__study-blocked", req.url));
}

// matcher에 걸리는 경로에서만 실행 — 참가자용 /study/* 와 /api/* 프록시는 건드리지 않는다.
// 예외: /study/compare 와 세션 UI 수정안(/study/session/*/v/*)은 연구자용 프로토타입 표면이라 차단.
// /demo는 matcher에 없다 = study 모드에서도 열린다 (상품 풀 확인용, mode="demo"라 실험 데이터와 분리).
export const config = {
  matcher: [
    "/", "/simulate/:path*", "/research/:path*", "/pscon/:path*",
    "/study/compare/:path*", "/study/session/:sessionId/v/:path*", "/study/session/:sessionId/compare/:path*",
    "/study/vdemo/:path*",
  ],
};
