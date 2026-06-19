# 설문 후 기능 소개(튜토리얼) 설계

**작성일:** 2026-06-17
**성격:** 설계문서 (durable decisions + rationale). 구현 세부는 코드가 진실.
관련: `formative-study-deploy-design.md`, 코딩스펙 §36, `frontend/lib/survey.ts`

## 1. 목적
참가자가 본 세션 전에 **낯선 기능 4가지**(상품카드+4칩, 기준 칩, 근거 보기, 가치·동기 그래프)를 이해하게 해서, 혼란이 hidden-intention 관찰을 오염시키는 걸 막는다. 진행자가 있어도 **참가자마다 동일한 사전 노출**이 study 타당도에 중요.

## 2. 확정된 결정 (Decisions + Rationale)
| # | 결정 | 이유 |
|---|---|---|
| T1 | **포맷 = "더미 데모 화면 + 스포트라이트 코치마크"** | 실제 채팅 UI 위 코치마크(B안)는 카드·패널·충돌카드가 *상호작용 후에야* 나타나 타이밍 문제. **더미 데이터로 모든 요소를 미리 띄운 데모 화면**에서 코치마크를 돌려 우회. |
| T2 | **실제 컴포넌트 재사용 + 더미 props 주입** | `MessageBubble`·`ProductGrid`·`CurrentUnderstandingPanel`을 그대로 사용 → 진짜 화면과 100% 동일, UI 변경 시 자동 동기화(드리프트 0). |
| T3 | **스포트라이트 = 커스텀 ~130줄, 의존성 0** | 타깃이 전부 고정 위치(정적 데모)라 driver.js 같은 라이브러리 불필요. `box-shadow: 0 0 0 9999px`로 도려내기. |
| T4 | **범위 = 6단계** | ①대화(예시 대화 + 입력창) ②상품카드+4칩(추천 3개) ③충돌 카드(기준 부딪힐 때 뜨는 노란 확인 카드) ④기준 칩(수정·맞아요/아니에요) ⑤근거 보기 ⑥가치·동기 그래프. 데모는 실제 세션처럼 대화·추천3·충돌카드·입력창을 모두 구성. (충돌 카드는 2026-06-17 사용자 요청으로 추가.) |
| T5 | **흐름 = 설문→튜토리얼→세션 (자동, 선형)** | 설문 제출 후 `/study/tutorial`로 자동 이동 → "시작하기" → `/study/session/new`. 코치마크에 "건너뛰기"(테스트용). |
| T6 | **데모는 보기 전용(no-op 핸들러)** | `onFeedback/onChipAction/onShowEvidence = () => {}`, ProductGrid `disabled` → 클릭해도 동작 없음(혼란 방지). |

## 3. 파일
| 파일 | 역할 |
|---|---|
| `app/study/tutorial/page.tsx` (신규) | 데모 2단 레이아웃(세션과 동일 `lg:grid-cols-[minmax(0,1fr)_440px]`) + Spotlight 호스트. pid를 세션으로 패스스루. |
| `components/tutorial/Spotlight.tsx` (신규) | 커스텀 코치마크(딤+하이라이트+툴팁, 이전/다음/시작하기/건너뛰기). selector로 타깃 탐색, resize/scroll 추적. |
| `lib/tutorialFixtures.ts` (신규) | 타입 맞춘 더미 `Turn[]`(예시 대화)·`Impression[]`(추천 3개: 이어폰/스마트워치/스피커)·`PreferenceState`. 데모 좌측엔 `UserInputBox`(disabled)도 렌더해 실제 채팅과 동일. |
| `components/preference/CurrentUnderstandingPanel.tsx` (수정) | 코치마크 타깃 `data-tutorial` 마커 3개(`criteria`/`evidence`/`radars`) 추가 — 실사용 무해. |
| `app/study/survey/page.tsx` (수정) | 제출 후 리다이렉트 `→ /study/tutorial?pid=...`. |

## 4. 타깃팅
코치마크는 `data-tutorial="..."` selector로 요소를 찾는다: `chat`(메시지 영역)·`products`(추천 카드 래퍼)는 데모 페이지, `criteria`/`evidence`/`radars`는 패널 내부. 공유 컴포넌트에 단 마커는 실제 세션에서도 존재하지만 미사용(무해).

## 5. 열린 항목
- 상품 카드 이미지: 데모 fixture는 `imageUrl` 생략(깨진 외부이미지 방지) → 레터마크 헤더로 렌더. 실제감 더 원하면 안정적 플레이스홀더 추가.
- "다시 보기": 현재 없음(YAGNI). 필요 시 세션 화면에 도움말 버튼으로 추가.
- 반응형: 데모는 `lg:` 2단, 좁은 화면에선 1단으로 쌓임 → 코치마크는 selector 기반이라 동작하나 스크롤 점프 가능. FS1은 데스크톱 원격이라 수용.
