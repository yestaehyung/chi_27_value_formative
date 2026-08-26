"""Semantic merge of newly extracted topics into the session ontology (spec §16.3)."""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models

PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "must_have": 3}


def structural_explicitness(ext: dict, source: str) -> str:
    """explicitness를 출처 기반으로 구조적으로 결정한다 (이론모듈 §2.2).

    LLM(특히 소형 모델)의 explicitness 자기 라벨은 explicit 편향이 심하다
    (PSCon 사전검증에서 100% explicit). hidden의 이론적 정의는 'query에 직접
    표현되지 않음'이므로, 발화가 아닌 반응/비교에서 나온 topic은 구조적으로
    implicit 이상이다:
      - user_utterance + 사용자가 직접 말한 조건/맥락        → explicit
      - user_utterance + 회피(avoidance)/가치성 라벨          → implicit
      - feedback (좋아요·싫어요 반응에서 역추론)              → implicit
      - feedback + 회피(반응이 드러낸 더 깊은 가치)           → latent (user-emergent)
      - product_comparison / wimhf_discovery / agent_inference → latent
    LLM이 implicit/latent로 표시한 건 절대 explicit으로 올리지 않는다.
    """
    llm_label = ext.get("explicitness", "implicit")
    kind = ext.get("kind", "preference")
    if source in ("product_comparison", "wimhf_discovery", "agent_inference"):
        return "latent"
    if source == "feedback":
        return "latent" if kind == "avoidance" else "implicit"
    # user_utterance
    if kind in ("constraint", "context"):
        return "explicit" if llm_label == "explicit" else llm_label
    if kind == "avoidance":
        return "latent" if llm_label == "latent" else "implicit"
    # preference: 사용자가 직접 말한 선호는 explicit이되, LLM이 더 약하게 봤으면 존중
    return llm_label if llm_label in ("implicit", "latent") else "explicit"


def _evidence_type(ev_id: str, stored: dict | None) -> str:
    """Infer the evidence table from the id prefix (matches api/preferences.py)."""
    if stored and stored.get("type") == "product_cue":
        return "product_cue"
    if ev_id.startswith("turn"):
        return "turn"
    if ev_id.startswith("fb"):
        return "feedback"
    return "unknown"


def attach_evidence_edges(
    db: DbSession,
    topic: models.IntentionTopic,
    ev_entries: list[dict],
    ext: dict,
    source: str,
) -> None:
    """Write Dialogue→Intention evidence edges with per-edge explicitness
    (graph design D1), then refresh the node-level explicitness cache.

    Cache rule: explicit if ANY explicit edge, else latent if ALL edges latent,
    else implicit. A node with no explicit edge is *hidden* by definition.
    """
    edge_explicitness = structural_explicitness(ext, source)
    seen = {
        (e.evidence_id, e.channel)
        for e in db.query(models.IntentionEvidence)
        .filter(models.IntentionEvidence.topic_id == topic.id)
        .all()
    }
    for entry in ev_entries:
        ev_id = entry.get("id")
        edge_channel = entry.get("channel") or source
        if not ev_id or (ev_id, edge_channel) in seen:
            continue
        explicitness = entry.get("explicitness")
        if explicitness not in ("explicit", "implicit", "latent"):
            explicitness = edge_explicitness
        db.add(models.IntentionEvidence(
            id=new_id("ev"),
            topic_id=topic.id,
            evidence_type=_evidence_type(ev_id, entry),
            evidence_id=ev_id,
            channel=edge_channel,
            explicitness=explicitness,
            kind=ext.get("kind", "preference"),
        ))
        seen.add((ev_id, edge_channel))
    db.flush()
    refresh_explicitness_cache(db, topic)


def refresh_explicitness_cache(db: DbSession, topic: models.IntentionTopic) -> None:
    """Derive the node-level explicitness label from its evidence edges."""
    labels = [
        e.explicitness
        for e in db.query(models.IntentionEvidence)
        .filter(models.IntentionEvidence.topic_id == topic.id)
        .all()
    ]
    if not labels:
        return  # pre-backfill topic — keep the stored label
    if "explicit" in labels:
        topic.explicitness = "explicit"
    elif all(l == "latent" for l in labels):
        topic.explicitness = "latent"
    else:
        topic.explicitness = "implicit"


def _normalize(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum())


def _bigrams(s: str) -> set[str]:
    s = _normalize(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}


def _similar(a: str, b: str) -> bool:
    """한국어 친화 유사도: 공백 토큰은 한국어에서 신뢰할 수 없으므로
    문자 bigram Jaccard(≥0.55) + 정규화 포함관계로 판정한다.
    예: "가격이 낮을수록 좋음" vs "가격이 낮은 게 좋음" → bigram 겹침으로 동일 판정.
    """
    if a == b:
        return True
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return False
    # 짧은 라벨이 긴 라벨에 그대로 포함되면 같은 기준의 축약/확장으로 본다
    if len(min(na, nb, key=len)) >= 4 and (na in nb or nb in na):
        return True
    ba, bb = _bigrams(a), _bigrams(b)
    return len(ba & bb) / len(ba | bb) >= 0.55


def plan_new_topics(
    existing: list[models.IntentionTopic],
    extracted: list[dict],
) -> list[dict]:
    """Pure planning (no writes): which extracted topics will become new rows.
    Used to run anchor/concept/relation/conflict LLM calls before any DB write."""
    new: list[dict] = []
    for ext in extracted:
        if not isinstance(ext, dict):
            continue
        label = (ext.get("label") or "").strip()
        if not label:
            continue
        # revision은 기존 기준의 내용 교체다 — 새 라벨이 기존 라벨과 안 닮았어도
        # 새 토픽이 아니다 (merge_topics의 revision 경로와 판정을 맞춘다).
        if _find_revision_target(existing, ext) is not None:
            continue
        if next((t for t in existing if _similar(t.label, label)), None) is None:
            new.append(ext)
    return new


def _find_revision_target(
    existing: list[models.IntentionTopic], ext: dict,
) -> models.IntentionTopic | None:
    """revisesLabel이 지목한 기존 기준 — 정확 일치 우선, 유사도 폴백."""
    revises = (ext.get("revisesLabel") or "").strip()
    if not revises or ext.get("confidenceLevel") != "directly_stated":
        return None
    target = next((t for t in existing if t.label == revises), None)
    if target is None:
        target = next((t for t in existing if _similar(t.label, revises)), None)
    if target is not None and target.status == "rejected_by_user":
        return None  # 사용자가 거부한 기준은 수정으로도 되살리지 않는다
    return target


def _apply_label_revision(
    db: DbSession,
    session: models.Session,
    match: models.IntentionTopic,
    label: str,
    ext: dict,
) -> None:
    """기준 내용 교체 + CorrectionEvent 기록 — 칩에서 고치든 말로 고치든
    '사용자가 시스템 이해를 수정했다'는 같은 사건이므로 같은 로그에 남긴다.
    사용자가 칩에서 손수 쓴 라벨(corrected_by_user)은 문구를 보존한다."""
    if match.status == "corrected_by_user" or label == match.label:
        return
    before = {"label": match.label, "status": match.status,
              "priority": match.priority, "confidence": match.confidence,
              "kind": (match.hints or {}).get("kind")}
    match.label = label
    if ext.get("description"):
        match.description = ext["description"]
    # 전체 갱신 (2026-08-26 승인): 반전 revision("서랍 필수"→"서랍 회피")은 라벨만
    # 바꾸면 안 된다 — 검색 스펙 컴파일러는 화면 라벨이 아니라 kind·implied 파생을
    # 읽으므로, 옛 impliedHardConstraint가 남으면 화면("no drawers")과 정반대 집행
    # ("서랍 포함" 하드 제약)이 된다 (5차 QA: no drawers인데 서랍 3개 책상 1위).
    hints = dict(match.hints or {})
    if ext.get("kind") in ("preference", "constraint", "avoidance", "context"):
        hints["kind"] = ext["kind"]
    hints["impliedHardConstraint"] = ext.get("impliedHardConstraint")
    hints["impliedAvoidance"] = ext.get("impliedAvoidance")
    match.hints = hints
    last_turn = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index.desc())
        .first()
    )
    db.add(models.CorrectionEvent(
        id=new_id("corr"),
        session_id=session.id,
        topic_id=match.id,
        action="revised_by_utterance",
        turn_index=last_turn.turn_index if last_turn else 0,
        before=before,
        after={"label": match.label, "status": match.status,
               "priority": match.priority, "confidence": match.confidence,
               "kind": (match.hints or {}).get("kind")},
    ))


def merge_topics(
    db: DbSession,
    session: models.Session,
    extracted: list[dict],
    source: str,
) -> tuple[list[models.IntentionTopic], list[models.IntentionTopic]]:
    """Returns (all touched topics, newly created topics)."""
    existing = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session.id)
        .all()
    )
    touched: list[models.IntentionTopic] = []
    created: list[models.IntentionTopic] = []

    for ext in extracted:
        if not isinstance(ext, dict):
            continue
        label = (ext.get("label") or "").strip()
        if not label:
            continue
        # M1: confidenceLevel 범주가 원본 — 숫자는 levels.py 테이블의 파생 캐시.
        # 레벨이 없으면 구(舊) 숫자 경로 하위호환 (mock·이전 계약).
        from app.ontology.levels import CONFIDENCE_LEVEL_VALUE

        conf_level = ext.get("confidenceLevel")
        if conf_level in CONFIDENCE_LEVEL_VALUE:
            ext["confidence"] = CONFIDENCE_LEVEL_VALUE[conf_level]
        else:
            try:
                ext["confidence"] = max(0.0, min(1.0, float(ext.get("confidence", 0.5))))
            except (TypeError, ValueError):
                ext["confidence"] = 0.5
        if ext.get("priority") not in ("low", "medium", "high", "must_have"):
            ext["priority"] = "medium"
        # 기준 수정(revision) — 발화가 기존 기준의 내용을 바꾼 경우 (2026-08-25).
        # 추출이 revisesLabel로 대상 기준을 지목하면 라벨을 새 내용으로 교체한다.
        # 가격 특례(아래 priceMin/priceMax 경로)의 일반화: $35→$50뿐 아니라
        # 색상 변경·완화도 같은 통로로 흐른다. directly_stated(사용자가 직접 말함)
        # 한정 — 약한 재추론이 라벨을 바꾸지 못하게 한다.
        match = _find_revision_target(existing, ext)
        if match is not None:
            _apply_label_revision(db, session, match, label, ext)
        else:
            match = next((t for t in existing if _similar(t.label, label)), None)
        evidence = [
            e for e in (ext.get("sourceEvidence") or [])
            if isinstance(e, dict) and e.get("id")
        ]
        ev_ids = [e["id"] for e in evidence]

        if match is not None:
            if match.status == "rejected_by_user":
                continue  # the user explicitly rejected this inference — do not resurrect
            new_ev = [i for i in ev_ids if i not in (match.evidence_ids or [])]
            if new_ev:
                match.evidence_ids = (match.evidence_ids or []) + new_ev
                match.confidence = min(0.98, max(match.confidence, ext.get("confidence", 0.5)) + 0.05)
                hints = dict(match.hints or {})
                hints["evidence"] = (hints.get("evidence") or []) + [
                    e for e in evidence if e["id"] in new_ev
                ]
                match.hints = hints
                # D1: 같은 의도가 다른 채널의 증거를 얻으면 explicitness가 다른 엣지가 생긴다
                attach_evidence_edges(
                    db, match, [e for e in evidence if e["id"] in new_ev], ext, source,
                )
            if PRIORITY_RANK.get(ext.get("priority", "medium"), 1) > PRIORITY_RANK.get(match.priority, 1):
                match.priority = ext["priority"]
            elif (ext.get("confidenceLevel") == "directly_stated"
                  and PRIORITY_RANK.get(ext.get("priority", "medium"), 1) < PRIORITY_RANK.get(match.priority, 1)):
                # 완화 발화("직접 확인할게요", "필수는 아니에요")의 하향은 사용자가 그 기준을
                # 직접 언급한 경우(directly_stated)에만 반영 — 약한 재추론이 must_have를
                # 조용히 깎지 못하게 한다. (2026-08-18 실측: 사이즈 완화 2회에도 must_have
                # 유지 → 있지도 않은 빈손 반복)
                match.priority = ext["priority"]
                new_kind = ext.get("kind")
                hints = dict(match.hints or {})
                if new_kind and new_kind != hints.get("kind"):
                    hints["kind"] = new_kind
                    if new_kind != "constraint":
                        hints["impliedHardConstraint"] = None
                    match.hints = hints
            # 정제 병합: 같은 의도가 새 가격 값으로 재추출되면 최신 값이 현재 제약이다.
            # 증거만 쌓고 값을 안 바꾸면 "$150로 좁혔는데 $300 유지" 스테일이 생긴다
            # (2026-08-16 라이브 실측). 라벨은 값을 표시하므로 함께 갱신하되,
            # 사용자가 직접 쓴 라벨(corrected_by_user)은 보존한다.
            new_pmin, new_pmax = ext.get("priceMin"), ext.get("priceMax")
            if new_pmin is not None or new_pmax is not None:
                hints = dict(match.hints or {})
                if (hints.get("priceMin"), hints.get("priceMax")) != (new_pmin, new_pmax):
                    hints["priceMin"], hints["priceMax"] = new_pmin, new_pmax
                    match.hints = hints
                    if match.status != "corrected_by_user":
                        match.label = label
                        if ext.get("description"):
                            match.description = ext["description"]
            touched.append(match)
        else:
            explicitness = structural_explicitness(ext, source)
            topic = models.IntentionTopic(
                id=new_id("topic"),
                session_id=session.id,
                label=label,
                description=ext.get("description"),
                source=source,
                status="inferred" if explicitness != "explicit" else "confirmed",
                priority=ext.get("priority", "medium"),
                confidence=ext.get("confidence", 0.5),
                explicitness=explicitness,
                evidence_ids=ev_ids,
                related_product_ids=[],
                hints={
                    "kind": ext.get("kind", "preference"),
                    "confidenceLevel": ext.get("confidenceLevel"),  # M1 범주 원본 (숫자는 캐시)
                    "impliedHardConstraint": ext.get("impliedHardConstraint"),
                    "impliedAvoidance": ext.get("impliedAvoidance"),
                    "priceMin": ext.get("priceMin"),
                    "priceMax": ext.get("priceMax"),
                    # 구매 옵션 속성 (사이즈·색상 선택 등) — unk 배제 면제의 근거
                    "purchaseOption": bool(ext.get("purchaseOption")),
                    "evidence": evidence,
                },
            )
            db.add(topic)
            attach_evidence_edges(db, topic, evidence, ext, source)
            existing.append(topic)
            touched.append(topic)
            created.append(topic)

    db.flush()
    return touched, created
