// 본실험 과제 4종 (2026-08-23 적용, 2026-08-21 확정·로컬 검증) — 친숙/비친숙 자기선택을
// 상황 기반 과제로 대체한다. 각 과제는 "시스템이 알 수 없는 개인 맥락(방 크기·통근 경로·
// 옷장·행사)"이 정답 조건이 되도록 설계됐다 — 숨은 기준 압력.
// 친숙도는 이제 배정 축이 아니라 측정 변수다(지식 행렬 + SPK 문항).
import { tr } from "@/lib/studyI18n";

export type StudyTask = {
  id: string;          // T1~T4 — 분석·로그 식별자
  category: string;    // 세션 카테고리 (검색 경계)
  title: string;
  description: string;
};

export const STUDY_TASKS: StudyTask[] = [
  {
    id: "T1",
    category: "Monitors",
    title: tr("홈 워크스페이스용 모니터", "A monitor for your home workspace"),
    description: tr(
      "현재 집에서 주로 하는 작업과 실제 책상 환경에 맞는 모니터 한 대를 찾아보세요. 자신의 작업 방식과 사용 환경을 반영하여 추천 상품을 검토하고, 가장 적합한 제품을 선택하세요.",
      "Find one monitor that fits the work you mainly do at home and your actual desk setup. Review the recommended products in light of how you work and where you will use it, and choose the product that fits you best.",
    ),
  },
  {
    id: "T2",
    category: "Headphones",
    title: tr("매일의 이동 시간을 위한 헤드폰", "Headphones for your daily commute"),
    description: tr(
      "매일 왕복 두 시간 정도 대중교통으로 이동하면서 쓸 헤드폰 하나를 찾아보세요. 실제로 다니는 경로의 환경과 이동 중 주로 듣는 것을 반영하여 추천 상품을 검토하고, 가장 적합한 제품을 선택하세요.",
      "Find one pair of headphones to use during a daily commute of about two hours round trip on public transport. Review the recommended products in light of your actual route and what you mostly listen to on the way, and choose the product that fits you best.",
    ),
  },
  {
    id: "T3",
    category: "Desks",
    title: tr("좁은 방에 맞는 작업 책상", "A desk for a small room"),
    description: tr(
      "현재 생활하거나 익숙하게 알고 있는 좁은 방에서 작업 공간을 확보하고 싶습니다. 실제로 그 방에서 하는 작업과 책상 위에 두어야 할 물건, 방 안에서 쓸 수 있는 공간을 고려하여 이 상황에 가장 적합한 책상 하나를 찾아보세요.",
      "You want to set up a workspace in a small room you live in or know well. Considering the work you actually do there, the items that need to stay on the desk, and the space available in the room, find the one desk that best fits this situation.",
    ),
  },
  {
    // 2026-08-23 교체: 원래 "여름 야외 결혼식"이었으나 참가자 발화의 "outdoor/summer"가
    // 임베딩 검색에서 아웃도어·트로피컬 셔츠를 끌어와 1턴 품질이 무너졌다 (하와이안·
    // 플란넬 혼입, 3회 검증 재현). 사무실 어휘는 카탈로그의 드레스 셔츠 공급과 정렬돼
    // 1턴부터 적합 — 행사 규범형 압력(격식 수위 해석·첫인상·옷장 조화)은 유지된다.
    id: "T4",
    category: "Shirts & Blouses",
    title: tr("새 직장 첫 출근을 위한 셔츠", "A shirt for your first week at a new job"),
    description: tr(
      "다음 주부터 새 직장으로 첫 출근을 합니다. 사무실은 비즈니스 캐주얼 분위기입니다. 자신이 실제로 가지고 있는 옷과 평소 스타일을 고려하여, 첫 주에 입을 셔츠/블라우스 하나를 찾아보세요.",
      "You are starting a new job next week, and the office has a business-casual dress code. Considering the clothes you actually own and your usual style, find one shirt or blouse to wear during your first week.",
    ),
  },
];

export function taskForCategory(category: string | null | undefined): StudyTask | null {
  if (!category) return null;
  return STUDY_TASKS.find((t) => t.category === category) ?? null;
}
