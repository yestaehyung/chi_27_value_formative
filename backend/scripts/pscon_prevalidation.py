"""PSCon 실대화 사전검증 (포럼 덱 '가치 정량화 파이프라인' 1단계).

기존 CRS 벤치마크(PSCon EN) 대화를 본 시스템의 topic 추출 + 6-anchor 매핑에
통과시켜, 실대화에서 hidden intention 추론이 가능한지 검증한다.

실행: backend/ 에서  .venv/bin/python scripts/pscon_prevalidation.py
출력: ../docs/pscon_prevalidation_results.json
"""
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.prompts import SYSTEM_BY_TASK, render_user_context  # noqa: E402
from app.llm.provider import LLMMessage, get_provider  # noqa: E402

PSCON = Path(__file__).resolve().parents[3] / "PSCon" / "dataset" / "conversation_en.json"
OUT = Path(__file__).resolve().parents[2] / "docs" / "pscon_prevalidation_results.json"

# 층화 표본: 시나리오 신호별로 추출
STRATA = {
    "gift": (r"\bgift|present for|for my (mom|dad|wife|husband|friend|girlfriend|boyfriend)", 3),
    "budget": (r"budget|cheap|under \d|below \d|price range", 3),
    "brand": (r"\b(prefer|like|don't like).{0,20}\b(brand|samsung|apple|sony|lg)\b|no specific brand", 3),
    "quality": (r"durable|last long|reliable|warranty|good quality", 3),
    "explore": (r"not sure|don't know|first time|never bought", 2),
    "replace": (r"broke|broken|old one|upgrade", 2),
    "situation": (r"home office|travel|trip|camping|ergonomic", 2),
}

# 좋은 topic 라벨 휴리스틱 (코딩가이드 §17.1: 선택 기준/동기 표현 여부)
CRITERION_MARKERS = ["원함", "필요", "선호", "중요", "않기", "싶", "회피", "신뢰", "적합", "기준",
                     "이하", "이상", "맞아야", "되어야", "줄이기", "피하"]


def sample_conversations():
    convs = json.load(open(PSCON, encoding="utf-8"))
    picked, used = [], set()
    for stratum, (pat, k) in STRATA.items():
        found = 0
        for c in convs:
            if c["conv_id"] in used or found >= k:
                continue
            users = [m["content"] for m in c["conversation"] if m.get("role") == "user"]
            if re.search(pat, " ".join(users).lower()):
                picked.append((stratum, c))
                used.add(c["conv_id"])
                found += 1
    return picked


async def run_one(provider, stratum, conv):
    users = [m for m in conv["conversation"] if m.get("role") == "user"]
    turns = [
        {"id": f"turn_{conv['conv_id']}_{i}", "role": "user", "content": m["content"]}
        for i, m in enumerate(users)
    ]
    valid_ids = {t["id"] for t in turns}
    ctx = {"turns": turns, "feedback": [], "state": {"activeTopicLabels": []}}
    msgs = [LLMMessage(role="system", content=SYSTEM_BY_TASK["topic_extraction"]),
            LLMMessage(role="user", content=render_user_context(ctx))]
    out = await provider.generate_json(msgs, task="topic_extraction", context=ctx)
    topics = [t for t in (out.get("topics") or []) if isinstance(t, dict) and t.get("label")]

    anchors_by_label = {}
    if topics:
        actx = {"topics": [{"label": t["label"], "sourceEvidence": t.get("sourceEvidence", [])} for t in topics]}
        amsgs = [LLMMessage(role="system", content=SYSTEM_BY_TASK["anchor_mapping"]),
                 LLMMessage(role="user", content=render_user_context(actx))]
        aout = await provider.generate_json(amsgs, task="anchor_mapping", context=actx)
        for m in aout.get("mappings") or []:
            if isinstance(m, dict) and m.get("topicLabel"):
                anchors_by_label[m["topicLabel"]] = m.get("anchors") or []

    results = []
    for t in topics:
        ev = t.get("sourceEvidence") or []
        ev_valid = all(isinstance(e, dict) and e.get("id") in valid_ids for e in ev) and len(ev) > 0
        is_criterion = any(mk in t["label"] for mk in CRITERION_MARKERS) or len(t["label"]) >= 10
        results.append({
            "label": t["label"],
            "explicitness": t.get("explicitness"),
            "confidence": t.get("confidence"),
            "evidenceValid": ev_valid,
            "criterionLike": is_criterion,
            "anchors": [
                {"anchor": a.get("anchor"), "score": a.get("score")}
                for a in anchors_by_label.get(t["label"], []) if isinstance(a, dict)
            ],
        })
    return {
        "convId": conv["conv_id"],
        "stratum": stratum,
        "userTurns": len(turns),
        "firstUtterance": turns[0]["content"][:90] if turns else "",
        "topics": results,
    }


async def main():
    provider = get_provider()
    print(f"provider: {provider.name}")
    picked = sample_conversations()
    print(f"sampled {len(picked)} conversations: {Counter(s for s, _ in picked)}")

    results = await asyncio.gather(*(run_one(provider, s, c) for s, c in picked))

    total_topics = sum(len(r["topics"]) for r in results)
    with_topic = sum(1 for r in results if r["topics"])
    ev_valid = sum(1 for r in results for t in r["topics"] if t["evidenceValid"])
    criterion = sum(1 for r in results for t in r["topics"] if t["criterionLike"])
    anchor_hist = Counter(a["anchor"] for r in results for t in r["topics"] for a in t["anchors"])
    expl_hist = Counter(t["explicitness"] for r in results for t in r["topics"])

    summary = {
        "conversations": len(results),
        "withAtLeastOneTopic": with_topic,
        "totalTopics": total_topics,
        "topicsPerConv": round(total_topics / len(results), 2),
        "evidenceTraceRate": round(ev_valid / total_topics, 2) if total_topics else 0,
        "criterionLikeRate": round(criterion / total_topics, 2) if total_topics else 0,
        "anchorDistribution": dict(anchor_hist.most_common()),
        "explicitnessDistribution": dict(expl_hist),
    }
    OUT.parent.mkdir(exist_ok=True)
    json.dump({"summary": summary, "results": results}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\nsaved → {OUT}")
    # 정성 확인용 샘플 출력
    for r in results[:6]:
        print(f"\n[{r['stratum']}] \"{r['firstUtterance']}\"")
        for t in r["topics"]:
            marks = ("✓근거" if t["evidenceValid"] else "✗근거") + (" ✓기준성" if t["criterionLike"] else " ✗기준성")
            anchors = ",".join(f"{a['anchor']}({a['score']})" for a in t["anchors"][:3])
            print(f"   - {t['label']} [{t['explicitness']}] {marks} | {anchors}")


if __name__ == "__main__":
    asyncio.run(main())
