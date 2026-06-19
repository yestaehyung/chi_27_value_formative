#!/usr/bin/env bash
# 200명 확장 전체 파이프라인 — 한 번 띄우면 끝까지 순차 진행 (터미널 닫아도 됨).
#
# 실행:
#   setsid nohup bash ~/yeo/naver_value_evaluation/valuecommit/backend/scripts/run_expansion_200.sh \
#     > /tmp/expansion_200.log 2>&1 < /dev/null &
# 모니터:
#   tail -f /tmp/expansion_200.log
#
# 모든 단계가 재개 가능(이미 된 것은 스킵)이라, 중간에 죽으면 같은 명령으로 다시 띄우면 이어서 돈다.
set -euo pipefail
cd "$(dirname "$0")/.."   # → backend/

echo "[1/4] 페르소나 풀 확장 → 200명 (기존 50 보존 + 신규 추가)  $(date '+%H:%M:%S')"
.venv/bin/python scripts/sample_nemotron_personas.py 200

echo ""
echo "[2/4] 신규 캐스팅(scenario_match) + GT 도출 (동시 6, temp 0.8)  $(date '+%H:%M:%S')"
VC_SYNTH_CONCURRENCY=6 .venv/bin/python scripts/derive_persona_profiles_v2.py

echo ""
echo "[3/4] 단일 세션 대화 합성 — 미합성 persona만 (동시 4)  $(date '+%H:%M:%S')"
VC_SYNTH_CONCURRENCY=4 .venv/bin/python scripts/run_llm_simulations_v2.py

echo ""
echo "[4/4] 멀티 세션 20명 × 2 (동시 2)  $(date '+%H:%M:%S')"
.venv/bin/python scripts/run_multi_session_simulations_v2.py 20

echo ""
echo "✅ 전부 완료  $(date '+%H:%M:%S') — 검수: data/synthesis_v2/ · data/synthesis_multi_v2/ · /simulate 합성 검수"
