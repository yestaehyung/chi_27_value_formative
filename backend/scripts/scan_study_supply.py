"""본실험(main study) 3개 과제 카테고리의 Amazon 공급량 실측.

`scan_amazon_supply.py`(구 시나리오 5종 대상)와 별개다. 본실험은 3조건 between-subjects ×
3카테고리 within-subjects 설계이고, 세 카테고리의 **풀 깊이를 같게 맞춰야** 과제 간 차이가
'카테고리 특성'인지 '풀이 얕아서'인지 구분된다. 그 상한을 알기 위한 스캔이다.

대상:
  블루투스 스피커  meta_Electronics                 (노드 확정)
  티셔츠           meta_Clothing_Shoes_and_Jewelry  (노드 확정)
  책상·의자        meta_Office_Products             (노드 미확정 → 이 스크립트가 발견)

수집 게이트는 augment_amazon_electronics.py와 동일하게 맞춘다: 가격 파싱 가능 + 이미지 존재
+ 리뷰 MIN_REVIEWS개 이상. 게이트 통과분이 실제로 쓸 수 있는 상품 수다.

  cd backend && LINE_CAP=400000 PYTHONPATH=. .venv/bin/python scripts/scan_study_supply.py
"""
import collections
import json
import os
from pathlib import Path
import urllib.request

BACKEND = Path(__file__).resolve().parent.parent
HF = ""
for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("HF_API_TOKEN="):
        HF = line.split("=", 1)[1].strip().strip('"')

BASE = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/meta_categories"
LINE_CAP = int(os.environ.get("LINE_CAP", "400000"))
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "30"))

#: 노드가 확정된 카테고리 — leaf(마지막 경로 노드)가 이 집합에 있으면 매치.
KNOWN = {
    "meta_Electronics": {
        "블루투스 스피커": {"Portable Bluetooth Speakers", "Bluetooth Speakers"},
    },
    "meta_Clothing_Shoes_and_Jewelry": {
        "티셔츠": {"T-Shirts"},
    },
}
#: 노드 미확정 — leaf 이름에 이 키워드가 들어간 노드의 분포를 뽑아서 사람이 고른다.
#: 홈오피스 책상·의자는 Office Products(Office Furniture)와 Home & Kitchen(Home Office
#: Furniture) 양쪽에 걸쳐 있어 둘 다 훑는다. 어느 쪽 공급이 큰지도 이 스캔으로 정해진다.
DISCOVER = {
    "meta_Office_Products": ("Desk", "Chair"),
    "meta_Home_and_Kitchen": ("Desk", "Chair"),
}


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


def file_size_bytes(fname: str) -> int:
    """HF에서 파일 크기를 직접 받는다 (하드코딩한 FILE_MB 표를 안 쓰기 위해)."""
    req = urllib.request.Request(
        f"{BASE}/{fname}.jsonl",
        headers={"Authorization": f"Bearer {HF}"} if HF else {},
        method="HEAD",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers.get("x-linked-size") or r.headers.get("Content-Length") or 0)


def scan(fname: str):
    known = KNOWN.get(fname, {})
    keywords = DISCOVER.get(fname)
    matched = collections.Counter()   # 라벨 → 서브카 전체
    passed = collections.Counter()    # 라벨 → 게이트 통과
    disc_matched = collections.Counter()   # 발견 모드: leaf 이름 → 전체
    disc_passed = collections.Counter()    # 발견 모드: leaf 이름 → 게이트 통과

    total = file_size_bytes(fname)
    req = urllib.request.Request(
        f"{BASE}/{fname}.jsonl", headers={"Authorization": f"Bearer {HF}"} if HF else {}
    )
    resp = urllib.request.urlopen(req, timeout=300)
    bytes_read, n = 0, 0
    for raw in resp:
        n += 1
        bytes_read += len(raw)
        if n > LINE_CAP:
            break
        try:
            r = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        cats = r.get("categories") or []
        if not cats:
            continue
        leaf = str(cats[-1]).strip()
        ok = (
            parse_price(r.get("price")) is not None
            and has_image(r.get("images"))
            and (r.get("rating_number") or 0) >= MIN_REVIEWS
        )
        for label, nodes in known.items():
            if leaf in nodes:
                matched[label] += 1
                if ok:
                    passed[label] += 1
                break
        if keywords and any(k.lower() in leaf.lower() for k in keywords):
            disc_matched[leaf] += 1
            if ok:
                disc_passed[leaf] += 1

    scale = total / max(bytes_read, 1)
    print(f"=== {fname} ===")
    print(f"    스캔 {n:,}줄 / {bytes_read/1e6:.0f}MB · 전체 {total/1e6:,.0f}MB · ×{scale:.1f} 외삽")
    for label in known:
        m, p = matched[label], passed[label]
        rate = p / m * 100 if m else 0
        print(f"    {label:14} 서브카 {m:6,}  게이트통과 {p:6,} ({rate:3.0f}%)  → 전체추정 ~{int(p*scale):,}개")
    if keywords:
        print(f"    [발견 모드] leaf 이름에 {keywords} 포함 — 상위 20개:")
        for leaf, m in disc_matched.most_common(20):
            p = disc_passed[leaf]
            print(f"      {leaf[:46]:46} 전체 {m:5,}  통과 {p:5,}  → 추정 ~{int(p*scale):,}개")
    print()


def main():
    print(f"LINE_CAP={LINE_CAP:,}/file · MIN_REVIEWS={MIN_REVIEWS}\n")
    for fname in list(KNOWN) + list(DISCOVER):
        try:
            scan(fname)
        except Exception as e:  # noqa: BLE001
            print(f"=== {fname} === 실패: {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
