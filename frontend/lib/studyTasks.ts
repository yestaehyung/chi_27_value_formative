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
  /** 과제 이해 확인(comprehension check) 선택지용 한 줄 상황 요약 (2026-08-26) */
  situation: string;
};

// 2026-08-27 저구체화 개정 (ours-v3.1 파일럿): 이전 문구는 고려할 기준을 과제가
// 체크리스트로 불러줬다("하는 작업·둘 물건·쓸 공간을 고려하여") — 참가자가 그대로
// 발화해 칩이 받아쓰기가 되고 시스템이 추론할 것이 안 남는다 (v3 파일럿 실측: 칩
// 상호작용 저조의 주원인). 상황 앵커(자기 방·이동·첫 출근)는 남기고 기준 코칭 문장만
// 제거한다 — "추론 대상인 기준을 지시문이 프라이밍하지 않게" 하는 방법론적 교정.
export const STUDY_TASKS: StudyTask[] = [
  {
    id: "T1",
    category: "Monitors",
    title: tr("집에서 쓸 모니터", "A monitor for your home"),
    situation: tr("집에서 쓸 모니터 고르기", "Choosing a monitor to use at home"),
    description: tr(
      "집에서 쓸 모니터 한 대를 골라 주세요. 자신의 생활에 잘 맞는 것이어야 합니다.",
      "Choose one monitor to use at home. It should fit well with how you actually live and work.",
    ),
  },
  {
    id: "T2",
    category: "Headphones",
    title: tr("이동할 때 쓸 헤드폰", "Headphones for getting around"),
    situation: tr("평소 이동할 때 쓸 헤드폰 고르기", "Choosing headphones for my everyday travel"),
    description: tr(
      "평소 이동할 때 쓸 헤드폰 하나를 골라 주세요. 자신의 이동 생활에 잘 맞는 것이어야 합니다.",
      "Choose one pair of headphones to use while getting around. It should fit well with how you actually travel day to day.",
    ),
  },
  {
    id: "T3",
    category: "Desks",
    title: tr("내 방에 둘 작업 책상", "A desk for your room"),
    situation: tr("내 방에 둘 작업 책상 고르기", "Choosing a desk for my room"),
    description: tr(
      "자신의 방에 둘 작업 책상 하나를 골라 주세요. 그 방에 잘 맞는 것이어야 합니다.",
      "Choose one desk for your room. It should fit that room well.",
    ),
  },
  {
    // 2026-08-23 교체: 원래 "여름 야외 결혼식"이었으나 참가자 발화의 "outdoor/summer"가
    // 임베딩 검색에서 아웃도어·트로피컬 셔츠를 끌어와 1턴 품질이 무너졌다. 사무실 어휘는
    // 카탈로그의 드레스 셔츠 공급과 정렬된다. 저구체화 개정에서 "비즈니스 캐주얼" 명시를
    // 제거 — 격식 수위 해석이 참가자 몫이 되며 규범형 압력은 유지된다.
    id: "T4",
    category: "Shirts & Blouses",
    title: tr("새 직장 첫 출근을 위한 셔츠", "A shirt for your first week at a new job"),
    situation: tr("새 직장 첫 출근 주간에 입을 셔츠 고르기", "Choosing a shirt for my first week at a new job"),
    description: tr(
      "다음 주부터 새 직장으로 첫 출근을 합니다. 첫 주에 입을 셔츠/블라우스 하나를 골라 주세요.",
      "You are starting a new job next week. Choose one shirt or blouse to wear during your first week.",
    ),
  },
];

export function taskForCategory(category: string | null | undefined): StudyTask | null {
  if (!category) return null;
  return STUDY_TASKS.find((t) => t.category === category) ?? null;
}
