# 데이터 합성 기록 — 과정과 산출물 (2026-06-25)

> 이 문서는 **데이터 합성(synthetic study data)의 과정과 산출물을 추적하는 러닝 기록**이다.
> 설계 배경/이론은 [`progress-report-synthesis-2026-06-11.md`](progress-report-synthesis-2026-06-11.md)에 있고,
> 여기서는 **"무엇을 했고, 무엇이 나왔는지"**를 현재 시점(v2, 스케일업 후)으로 적는다.
> ⚠️ 2026-06-11 보고서 §2의 global/local 2층 framing은 **F1로 폐기**됨(가치=상황의 산물).
> 아래 §4 참조. 권위 있는 결정 기록은 [`ontology-graph-design.md`](ontology-graph-design.md) 노트 F1.

---

## 0. 한 줄

말하지 않은 hidden intention을 service agent가 얼마나 복원하는지 **채점 가능한 형태로** 만들기 위해,
페르소나에서 정답(GT)을 만들고 → LLM user agent가 그 사람이 되어 service agent와 대화하게 한
합성 데이터. **GT는 user agent만 알고 service agent엔 숨긴다.** 현재 **페르소나 200명** 규모.

---

## 1. 왜 합성인가 (요약)

- 실데이터(PSCon 648건)는 거래형 대화라 **Utilitarian이 압도적이고 hidden intention이 거의 없음** →
  복원 능력을 시험할 데이터가 부족 → **합성이 필요**.
- GT를 미리 고정하고 service agent엔 숨기므로, **복원율을 채점**할 수 있음(= 합성의 존재 이유).

---

## 2. 과정 — v2 파이프라인 4단계 (각 단계: 무엇을 / 산출물)

모두 **실 LLM 호출**(`.env` = deepseek). 재실행 시 이미 만든 항목은 건너뜀(멱등). 동시성 `VC_SYNTH_CONCURRENCY`.

| # | 단계 | 스크립트 | 입력 → 산출물 |
|---|---|---|---|
| 1 | **페르소나 표집** | `sample_nemotron_personas.py` | `nvidia/Nemotron-Personas-Korea` → `seed/personas_nemotron.json` |
| 2 | **GT 도출** | `derive_persona_profiles_v2.py` | 페르소나 서사 → `seed/personas_nemotron_profiles_v2.json` (persona×scenario GT) |
| 3 | **단일세션 합성** | `run_llm_simulations_v2.py` | GT + service agent → `data/synthesis_v2/*.md` + `summary.json` |
| 4 | **멀티세션 합성** | `run_multi_session_simulations_v2.py` | 같은 persona × 2시나리오(Participant 묶음) → `data/synthesis_multi_v2/*.md` + `summary.json` |

**단계별 핵심 처리**

1. **표집** — 인구통계 비례로 표집(seed 42). 쇼핑 취향은 서사에 직접 없음 → 다음 단계에서 추론.
2. **GT 도출** — LLM이 서사에서 쇼핑 가치를 *추론*해 정해진 칸을 채움:
   - **TCV 5가치** 각 등급(`dominant`/`present`/`trace`) + **동기 7축** 등급(`high`/`medium`/`low`) + 숨은 의도 2~3개 + 말투(speechStyle).
   - **GT 단위 = persona × scenario** (가치는 상황의 산물). 시나리오 쌍 = 매칭 + 대비(자기용↔선물).
   - **도출 temperature 0.8** — 기본 0.1은 96건이 전부 최빈값(Functional/Utilitarian)으로 수렴(mode-collapse). temp0.1 백업: `*_v2_temp01.json`(Functional 54%).
   - 형식 미달(5축 누락 등)은 버리고 재생성. 통과분은 파일로 저장 → 사람이 검토·수정 가능.
3. **단일세션** — user agent가 GT대로 연기(짧게·한 턴 한 조건·숨은 의도는 간접 노출), service agent가 말·행동만으로 복원. 매 턴 파이프라인(의도추출→병합→anchor/concept/relation/conflict→스냅샷).
4. **멀티세션** — 한 사람을 Participant로 묶어 2세션. **세션마다 그 시나리오의 GT를 따로 주입**(세션1 매칭, 세션2 대비 → GT 다름). Participant spec·RIG는 "안정 trait 추정"이 아니라 **상황을 가로지른 반복 패턴의 기억**으로 누적.

**불변 규칙**

- **GT는 service agent에 절대 노출 안 함** — 세션 meta엔 `gtVersion` 스탬프만(세션↔GT 파일 링크). meta를 service agent가 읽으므로 GT를 넣으면 복원이 오염됨.
- **자동 일치 판정(✅/❌)을 만들지 않음** — md엔 주입 GT와 복원 결과를 **나란히 기록만**. 채점(human + LLM judge)은 **의도적으로 분리된 후속 단계**. 생성은 *evaluability*만 보존.

---

## 3. 산출물 — 현재 상태

### 3.1 파일 산출물

| 산출물 | 위치 | 개수 | 내용 |
|---|---|---|---|
| 페르소나 풀 | `seed/personas_nemotron.json` | **200** | Nemotron 표집 인물(서사) |
| **GT (v2)** | `seed/personas_nemotron_profiles_v2.json` | **200** | persona×scenario GT (가치5·동기7 등급, 숨은의도, speechStyle) |
| **단일세션 합성** | `data/synthesis_v2/` | **200 md** + `summary.json`(152 인덱싱) | 세션별 대화+주입GT+복원 나란히 |
| **멀티세션 합성** | `data/synthesis_multi_v2/` | **200 md** + `summary.json` | persona×2세션, 세션별 GT |

`summary.json` 한 항목 = `{personaId, name, scenario, sessionId, ended(purchase/browse), userTurns, topics, injected{valueDominant[], motivationHigh[]}, recovered{valueTop[], motivationTop[]}}` — **주입 vs 복원 나란히, 판정 없음**.
(주의: 단일 `summary.json`은 현재 152건 인덱싱 — 증분 실행분 일부 미집계 가능. md 200건이 실제 산출.)

### 3.2 DB 산출물 (`backend/nv_study.db`)

| | 수 |
|---|---|
| simulation 모드 세션 | **631** (≈ 단일 200 + 멀티 200×2 + 레거시) |
| 그중 `gtVersion` 링크 | **607** |

### 3.3 레거시(보존 — pre-F1 기록, 재생성 금지)

`personas_nemotron_profiles.json`(v1 GT), `data/synthesis_test/`(48), `data/synthesis_multi/`(10),
`data/synthesis_v2_temp01/`(10, temp0.1 백업), `run_llm_simulations.py`·`run_multi_session_simulations.py`(v1).

---

## 4. 2026-06-11 보고서 대비 바뀐 것 (v2 / F1)

| 항목 | 2026-06-11 (v1) | 현재 (v2) |
|---|---|---|
| 가치 framing | global(사람 trait) / local(상황 동기) 2층 | **상황적 가치 모델**(F1) — 가치도 상황의 산물 |
| GT 단위 | persona 단독 | **persona × scenario** |
| 멀티세션 GT | (해당 없음) | **세션마다 다른 GT 주입** |
| 일치 판정 | ✅/❌ 자동 표시 | **자동 판정 제거** — 나란히 기록만, 채점은 후속 |
| GT 도출 온도 | — | **temp 0.8** (mode-collapse 방지) |
| 규모 | 페르소나 10 | **페르소나 200** |

---

## 5. 채점/평가는 아직 (의도적 분리)

생성 단계는 **주입 GT와 복원 결과를 나란히 보존**할 뿐, 일치 여부를 판정하지 않는다.
평가(사람 검수 + LLM judge, 평가자 간 일치율 κ 포함)는 **별도 후속 단계**다 — 생성이 평가를 미리
규정하면 측정이 오염되기 때문. `/simulate` 합성 뷰어가 주입↔복원을 나란히 보여줌(검수용).

---

## 6. 재생성 / 검토 방법

```bash
cd valuecommit/backend
.venv/bin/python scripts/sample_nemotron_personas.py            # 1. 페르소나 표집
.venv/bin/python scripts/derive_persona_profiles_v2.py          # 2. GT 도출 (persona×scenario)
.venv/bin/python scripts/run_llm_simulations_v2.py              # 3. 단일세션 → data/synthesis_v2/
.venv/bin/python scripts/run_multi_session_simulations_v2.py    # 4. 멀티세션 → data/synthesis_multi_v2/
# 대규모 배치: VC_SYNTH_CONCURRENCY=4~6 권장
```

검토: 프론트 `/simulate`(합성 뷰어, 주입↔복원 나란히) · `data/synthesis_*_v2/*.md`(세션별 전문).
