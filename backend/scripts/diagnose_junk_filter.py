"""JUNK_ELECTRONICS 필터가 블루투스 스피커를 얼마나 오탈락시키는지 실측.

배경: 같은 데이터에 대해 두 스크립트가 다른 수를 낸다.
    scan_study_supply.py    3,588개   게이트 = 가격 + 이미지 + 리뷰 MIN_REVIEWS
    augment_…main_study.py  2,318개   게이트 = 위 + JUNK_ELECTRONICS
차이 1,270개(35%)가 전부 JUNK 필터에서 나온다. 그런데 그 목록은 이어폰·헤드폰용으로
만들어진 것을 스피커에 재사용한 것이라, 본품을 죽이고 있을 가능성이 크다
("Speaker with Carrying Strap" → strap, "Speaker Stand Included" → stand).

이 스크립트는 어떤 키워드가 무엇을 죽이는지 **제목을 실제로 보여준다**. 판단은 사람이 한다.
LLM 호출 없음 · 파일 쓰기는 결과 JSON 하나뿐.

측정 항목 (키워드별):
  killed        이 키워드가 걸리는 상품 수 (다른 키워드와 중복 가능)
  killed_only   이 키워드 **하나만** 걸리는 수 → 제거 시 그대로 되살아나는 수
  samples       제목 표본 — 본품인지 액세서리인지 눈으로 판정하기 위한 근거

  cd backend && PYTHONPATH=. .venv/bin/python scripts/diagnose_junk_filter.py
"""
import collections
import json
import os
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
HF = ""
for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("HF_API_TOKEN="):
        HF = line.split("=", 1)[1].strip().strip('"')

BASE = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/meta_categories"
FILE = "meta_Electronics"
NODE = "Portable Bluetooth Speakers"
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "10"))
LINE_CAP = int(os.environ.get("LINE_CAP", "0"))  # 0 = 무제한
SAMPLES_PER_KW = int(os.environ.get("SAMPLES", "12"))

# augment_amazon_main_study.py 와 **동일**해야 진단이 의미를 갖는다. 복사본이 아니라
# 원본에서 읽어오면 좋겠지만, 그 모듈은 import 시 .env/LLM provider를 건드리므로 여기서는
# 값을 명시한다. 원본이 바뀌면 이 목록도 같이 고쳐야 한다.
JUNK = ("case", "cover", "protector", "band", "strap", "replacement", "charger",
        "cable", "adapter", "stand", "mount", "skin", "sticker", "hub", "sleeve",
        "earpad", "ear pad", "cushion", "tips", "hook")


def parse_price(p):
    if not p:
        return None
    try:
        v = float(str(p).replace("$", "").replace(",", "").split()[0])
        return v if v > 0 else None
    except Exception:  # noqa: BLE001
        return None


def has_image(images):
    return any(im.get("large") or im.get("hi_res") or im.get("thumb") for im in (images or []))


def main() -> None:
    req = urllib.request.Request(
        f"{BASE}/{FILE}.jsonl", headers={"Authorization": f"Bearer {HF}"} if HF else {}
    )
    resp = urllib.request.urlopen(req, timeout=300)

    n = 0
    in_node = 0        # 노드 일치 (게이트 이전)
    base_pass = 0      # 가격+이미지+리뷰 통과 = JUNK 적용 전 공급량
    junk_killed = 0    # 그중 JUNK 에 걸린 수
    survived = 0       # 최종 생존 = 현재 augment 결과에 해당
    killed = collections.Counter()
    killed_only = collections.Counter()
    samples: dict[str, list[str]] = collections.defaultdict(list)
    survivor_samples: list[str] = []
    # 게이트 어느 항목에서 떨어지는지 — JUNK보다 이쪽이 훨씬 큰 병목이라 내역이 필요하다.
    gate_fail = collections.Counter()
    # 리뷰 임계를 낮추면 공급이 얼마나 느는가 (가격·이미지는 충족한 것만 센다).
    review_curve = collections.Counter()
    REVIEW_THRESHOLDS = (0, 1, 3, 5, 10, 20, 30, 50)
    # 탈락 제목 전량 — 규칙을 바꿔가며 오프라인에서 재평가하기 위해 (재스캔 없이).
    killed_titles: list[str] = []

    for raw in resp:
        n += 1
        if LINE_CAP and n > LINE_CAP:
            break
        if n % 50_000 == 0:
            print(f"  … {n:,}줄  노드 {in_node:,}  게이트통과 {base_pass:,}  "
                  f"JUNK탈락 {junk_killed:,}", flush=True)
        try:
            r = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        cats = r.get("categories") or []
        if not cats or str(cats[-1]).strip() != NODE:
            continue
        in_node += 1
        has_price = parse_price(r.get("price")) is not None
        img = has_image(r.get("images"))
        nrev = r.get("rating_number") or 0
        if has_price and img:
            for t in REVIEW_THRESHOLDS:
                if nrev >= t:
                    review_curve[t] += 1
        if not (has_price and img and nrev >= MIN_REVIEWS):
            # 어느 항목 때문에 떨어졌는지 (복수 사유는 조합으로 기록)
            why = "+".join(k for k, ok in
                           (("가격없음", has_price), ("이미지없음", img),
                            (f"리뷰<{MIN_REVIEWS}", nrev >= MIN_REVIEWS)) if not ok)
            gate_fail[why] += 1
            continue
        base_pass += 1

        title = (r.get("title") or "").strip()
        tl = title.lower()
        hits = [j for j in JUNK if j in tl]
        if not hits:
            survived += 1
            if len(survivor_samples) < SAMPLES_PER_KW:
                survivor_samples.append(title)
            continue
        junk_killed += 1
        killed_titles.append(title)
        for j in hits:
            killed[j] += 1
            if len(samples[j]) < SAMPLES_PER_KW:
                samples[j].append(title)
        if len(hits) == 1:
            killed_only[hits[0]] += 1

    print(f"\n{'='*74}")
    print(f"{FILE} · leaf='{NODE}' · MIN_REVIEWS={MIN_REVIEWS} · {n:,}줄 스캔")
    print(f"{'='*74}")
    print(f"노드 내 전체            {in_node:,}")
    print(f"게이트 통과(JUNK 이전)  {base_pass:,}   ← scan_study_supply 기준")
    print(f"  JUNK 탈락             {junk_killed:,}  ({junk_killed/max(base_pass,1)*100:.1f}%)")
    print(f"  최종 생존             {survived:,}   ← 현재 augment 기준")

    print(f"\n게이트 탈락 내역 (총 {in_node - base_pass:,}개) — JUNK보다 큰 병목")
    print("-" * 74)
    for why, c in gate_fail.most_common():
        print(f"  {why:<28} {c:>7,}")

    print(f"\n리뷰 임계별 공급 (가격·이미지 충족분 기준) — JUNK 적용 전")
    print("-" * 74)
    for t in REVIEW_THRESHOLDS:
        print(f"  리뷰 >= {t:<3}  {review_curve[t]:>7,}")

    print(f"\n{'키워드':<12} {'탈락':>6} {'단독탈락':>8}   (단독탈락 = 이 키워드만 빼면 되살아나는 수)")
    print("-" * 74)
    for kw, c in killed.most_common():
        print(f"{kw:<12} {c:>6,} {killed_only[kw]:>8,}")

    print(f"\n{'='*74}\n키워드별 제목 표본 — 본품인지 액세서리인지 판정용\n{'='*74}")
    for kw, _ in killed.most_common():
        print(f"\n▶ {kw}  (탈락 {killed[kw]:,} / 단독 {killed_only[kw]:,})")
        for t in samples[kw]:
            print(f"    {t[:96]}")

    print(f"\n▶ [참고] 필터를 통과한 생존 상품 표본")
    for t in survivor_samples:
        print(f"    {t[:96]}")

    out = BACKEND / "data" / "junk_filter_diagnosis.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "file": FILE, "node": NODE, "minReviews": MIN_REVIEWS, "linesScanned": n,
        "inNode": in_node, "basePass": base_pass, "junkKilled": junk_killed, "survived": survived,
        "killed": dict(killed), "killedOnly": dict(killed_only),
        "samples": {k: v for k, v in samples.items()},
        "survivorSamples": survivor_samples,
        "gateFail": dict(gate_fail),
        "reviewCurve": {str(k): v for k, v in sorted(review_curve.items())},
        # 규칙을 바꿔가며 재평가할 수 있게 탈락 제목 전량을 남긴다 (재스캔 회피).
        "killedTitles": killed_titles,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
