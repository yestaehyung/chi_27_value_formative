import { NextRequest, NextResponse } from "next/server";

// 스터디 배포 분리 (2026-07-02): 참가자용 배포는 APP_MODE=study 로 띄운다.
// - `/`         → 사전 설문으로 즉시 리다이렉트 (참가자는 런처 존재 자체를 모름)
// - 연구자 표면 → 404 rewrite (/simulate·/research·/pscon — 존재를 숨김)
// 백엔드도 같은 모드(VC_APP_MODE=study)로 해당 라우터를 잠근다 (이중 차단).
// 플래그가 없으면(로컬 개발·연구자 배포) 전부 통과 — 기존 동작 그대로.
const STUDY_MODE = process.env.APP_MODE === "study";

export function middleware(req: NextRequest) {
  if (!STUDY_MODE) return NextResponse.next();
  if (req.nextUrl.pathname === "/") {
    return NextResponse.redirect(new URL("/study/survey", req.url));
  }
  // 존재하지 않는 경로로 rewrite → Next 404 렌더 (URL은 유지)
  return NextResponse.rewrite(new URL("/__study-blocked", req.url));
}

// matcher에 걸리는 경로에서만 실행 — /study/* 와 /api/* 프록시는 건드리지 않는다.
export const config = {
  matcher: ["/", "/simulate/:path*", "/research/:path*", "/pscon/:path*"],
};
