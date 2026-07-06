"""DSPy Phase 1 — searchText 프롬프트 컴파일 (추천 관점 한정, 2026-07-06).

목표: ACTION_DECISION_SYSTEM의 searchText 작성 규칙을 손-반례 대신 MIPROv2
(Opsahl-Ong et al., EMNLP 2024)로 탐색 — metric은 전부 결정론(풀 카테고리 정합
- 오염 토큰 감점), 학습/검증은 스윕 케이스 재활용. 산출물은 지시문+예시 텍스트이며
검수 후 prompts.py에 이식한다 (서빙 경로에 dspy 의존성 0 — 오프라인 도구 전용,
requirements.txt에 넣지 말 것).

  cd backend && VC_SEED_DIR=seed_amazon VC_LLM_PROVIDER=deepseek PYTHONPATH=. \
      .venv/bin/python scripts/dspy_compile_searchtext.py
출력: data/dspy_searchtext_compiled.json (컴파일된 프로그램),
      data/dspy_searchtext_report.json (baseline vs compiled, val 케이스별)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_SEED_DIR", str(BACKEND / "seed_amazon"))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_dspy_"), "d.db"))

import dspy

# ── 케이스 (스윕 24 중 c5(풀밖·공급부재) 제외한 23) ──────────────────────────
# (id, 기대 카테고리들, 발화, 오염 토큰들 — searchText에 있으면 감점)
CASES = [
    ("a1", ["시계"], "가볍게 찰 손목시계 추천해줘", []),
    ("a2", ["스커트"], "여름에 입을 스커트 찾고 있어요", []),
    ("a3", ["모니터"], "사무용 모니터 하나 추천해주세요", []),
    ("a4", ["텀블러·머그"], "텀블러 하나 사려고요", []),
    ("b1", ["주얼리"], "여자친구 생일 선물로 주얼리를 찾고 있어요. 너무 저렴해 보이는 건 싫어요", ["생일", "캔들"]),
    ("b2", ["캔들·디퓨저"], "집들이 선물로 캔들이나 디퓨저 추천해줘", []),
    ("b3", ["스카프·머플러"], "어머니 생신 선물로 스카프 알아보고 있어요", ["생신"]),
    ("b4", ["스마트워치"], "아버지 은퇴 선물로 스마트워치 어떨까 해서요", ["은퇴"]),
    ("c1", ["가방·핸드백"], "출퇴근할 때 노트북 넣고 다닐 가방을 찾고 있어요", ["노트북"]),
    ("c2", ["양말"], "러닝화 신을 때 신을 양말 추천해줘", ["러닝화"]),
    ("c3", ["키보드·마우스"], "맥북이랑 같이 쓸 키보드 찾아요", ["맥북", "노트북"]),
    ("c4", ["지갑"], "카드 많이 들어가는 지갑 찾고 있어요. 휴대폰도 같이 들어가면 좋고요", ["휴대폰"]),
    ("d1", ["청바지"], "청바지 찾는데 스키니는 싫어요", ["스키니"]),
    ("d2", ["니트·스웨터"], "니트 사고 싶은데 따가운 소재는 싫어요", ["따가"]),
    ("d3", ["샌들"], "여름 샌들 찾는데 굽 높은 건 싫어요", ["굽 높", "하이힐"]),
    ("d4", ["원피스"], "원피스 찾고 있어요. 화려한 무늬는 싫고 단색이 좋아요", ["화려"]),
    ("e1", ["반바지"], "무릎 위로 오는 여름 반바지 추천해줘", []),
    ("e2", ["수영복"], "래시가드 스타일 수영복 찾아요", []),
    ("e3", ["후드·맨투맨"], "기모 있는 따뜻한 후드티 추천해줘", []),
    ("e4", ["블루투스 스피커"], "캠핑에서 쓸 방수 블루투스 스피커 추천해주세요", []),
    ("f1", ["지갑"], "남자친구 선물로 10만원대 지갑 보고 있어요", []),
    ("f2", ["텀블러·머그"], "회사 동료 선물로 부담 없는 머그컵 추천해줘", []),
    ("f3", ["시계"], "부모님 선물로 고급스러운 시계 찾고 있어요", []),
]
VAL_IDS = {"a2", "b3", "c2", "c4", "d3", "e3", "f2", "f1"}  # 층화 8 (유형별 1+)

# ── Signature: 초기 지시문 = 현행 규칙의 요약 (baseline) ─────────────────────
class WriteSearchSpec(dspy.Signature):
    """사용자 발화에서 상품 검색문을 만든다. searchText는 찾는 상품 종류와 원하는
    특징(긍정 신호)만 담은 완결된 한국어 검색문이고, 예산·비선호 같은 제약은
    constraintsNote에 쓴다."""
    utterances: str = dspy.InputField(desc="사용자 발화 (오래된 것부터, 줄바꿈 구분)")
    search_text: str = dspy.OutputField(desc="한국어 상품 검색문")
    constraints_note: str = dspy.OutputField(desc="예산·필수·비선호 요약, 없으면 '없음'")


def main():
    from app.core.config import settings
    from app.db.database import SessionLocal, engine
    from app.db import models
    models.Base.metadata.create_all(engine)
    from app.products.seed_loader import load_seed_products
    from app.products.search_index import build_index
    from app.products import embeddings
    from app.products.search import search_products

    db = SessionLocal()
    load_seed_products(db)
    build_index(db)
    embeddings.ensure_product_vectors(db.query(models.Product).all())
    assert embeddings.enabled(), "임베딩 비활성"

    lm = dspy.LM(
        "openai/" + settings.deepseek_model,
        api_base="https://api.deepseek.com/v1",
        api_key=settings.deepseek_api_key,
        max_tokens=1500,
        # DeepSeek V4는 thinking 기본 on — dspy는 우리 provider를 우회하므로 여기서 직접 끈다
        # (안 끄면 max_tokens가 전부 reasoning에 소진돼 본문이 빈 응답 → AdapterParseError).
        extra_body={"thinking": {"type": "disabled"}},
    )
    dspy.settings.configure(lm=lm)

    def to_example(c):
        cid, cats, utt, forbidden = c
        return dspy.Example(
            utterances=utt, cid=cid, expected=cats, forbidden=forbidden,
        ).with_inputs("utterances")

    train = [to_example(c) for c in CASES if c[0] not in VAL_IDS]
    val = [to_example(c) for c in CASES if c[0] in VAL_IDS]
    print(f"train {len(train)} / val {len(val)}", flush=True)

    def metric(example, pred, trace=None):
        st = (getattr(pred, "search_text", "") or "").strip()
        if not st:
            return False if trace is not None else 0.0
        pool = search_products(db, query=st, category=None, hard_constraints=[],
                               return_pool=True, pool_size=30, alpha=0.3)
        fit = sum(1 for sp in pool if sp.product.category in example.expected) / max(len(pool), 1)
        pen = 0.6 if any(tok in st for tok in example.forbidden) else 0.0
        score = max(0.0, fit - pen)
        if trace is not None:          # bootstrap 채택 기준: 사실상 만점만 데모로
            return score >= 0.9
        return score

    program = dspy.Predict(WriteSearchSpec)

    def evaluate(prog, dataset, label):
        rows = []
        for ex in dataset:
            try:
                pred = prog(utterances=ex.utterances)
                s = metric(ex, pred)
                rows.append({"cid": ex.cid, "score": round(s, 3),
                             "searchText": getattr(pred, "search_text", ""),
                             "constraintsNote": getattr(pred, "constraints_note", "")})
            except Exception as e:  # noqa: BLE001
                rows.append({"cid": ex.cid, "score": 0.0, "error": str(e)[:100]})
        avg = sum(r["score"] for r in rows) / len(rows)
        print(f"[{label}] 평균 {avg:.3f} | " + " ".join(f"{r['cid']}={r['score']}" for r in rows), flush=True)
        return avg, rows

    base_avg, base_rows = evaluate(program, val, "baseline(val)")

    from dspy.teleprompt import MIPROv2
    tp = MIPROv2(metric=metric, auto="light", num_threads=4)
    compiled = tp.compile(program, trainset=train, valset=val)

    comp_avg, comp_rows = evaluate(compiled, val, "compiled(val)")

    compiled.save(str(BACKEND / "data" / "dspy_searchtext_compiled.json"))
    report = {"baselineValAvg": base_avg, "compiledValAvg": comp_avg,
              "baseline": base_rows, "compiled": comp_rows,
              "instruction": compiled.signature.instructions,
              "demos": [dict(d) for d in (compiled.demos or [])]}
    (BACKEND / "data" / "dspy_searchtext_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== 컴파일된 지시문 ===\n" + compiled.signature.instructions, flush=True)
    print(f"\n데모 수: {len(compiled.demos or [])}")
    print(f"\nbaseline {base_avg:.3f} → compiled {comp_avg:.3f}")
    print("→ data/dspy_searchtext_report.json")


if __name__ == "__main__":
    main()
