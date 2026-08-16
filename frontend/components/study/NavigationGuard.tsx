"use client";

// 스터디 중 브라우저 뒤로/앞으로 가기 방지 (2026-08-16).
// 참가자가 실수로 뒤로 가면 과제 큐·설문 상태가 깨지므로, history에 현재 페이지를
// 다시 밀어 넣어 popstate(뒤로/앞으로)를 무력화한다. 페이지 이동은 앱 내 버튼으로만.
// 새로고침·창 닫기에는 브라우저 기본 확인 대화상자를 띄운다 (진행 상태 보호).
import { useEffect } from "react";

export default function NavigationGuard() {
  useEffect(() => {
    const push = () => window.history.pushState(null, "", window.location.href);
    push();
    const onPop = () => push();
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("popstate", onPop);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, []);
  return null;
}
