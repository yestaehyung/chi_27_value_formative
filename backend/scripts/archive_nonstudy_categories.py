"""본실험 과제 카테고리 외 상품을 활성 풀에서 아카이브로 분리 (2026-07-28).

본실험은 3과제(블루투스 스피커 / 티셔츠 / 홈오피스 책상·데스크체어)로 고정이다. 나머지
28개 카테고리를 활성 풀에 남기면 두 가지 문제가 생긴다:

  1. 연구 설계 — 스피커 과제에서 헤드폰·모니터가 후보 풀에 섞인다. 참가자마다 섞이는
     정도가 다르면 통제되지 않은 변인이 된다.
  2. 용량 — 과제 카테고리를 각 ~3,600개로 채우면 총 ~21,000개가 되고, 벡터 캐시가
     ~106MB로 GitHub 단일 파일 한도(100MB)를 넘는다. 28개를 빼면 ~51MB로 여유가 생겨
     벡터 저장소 이전(SQLite BLOB) 없이 현행 배포 방식을 유지할 수 있다.

**삭제가 아니라 이동이다.** 아카이브 파일을 되돌리면 복구된다 (--restore).

세 아티팩트를 함께 갈라야 정합이 유지된다 — products / profiles / vectors. 실제로 지금
product_profiles.json은 DB보다 35개 많은 고아 상태인데, 이런 어긋남이 아티팩트를 따로
관리해서 생긴 것이다.

  cd backend && PYTHONPATH=. .venv/bin/python scripts/archive_nonstudy_categories.py
  cd backend && PYTHONPATH=. .venv/bin/python scripts/archive_nonstudy_categories.py --restore
"""
import gzip
import json
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "seed_amazon"

#: 본실험 3과제가 쓰는 카테고리. 이 밖은 전부 아카이브.
STUDY_CATEGORIES = {"블루투스 스피커", "티셔츠", "책상", "데스크체어"}

PRODUCTS = SEED / "products.json"
PROFILES = SEED / "product_profiles.json"
VECTORS = SEED / "product_vectors.json.gz"

AR_PRODUCTS = SEED / "archive_28cat_products.json"
AR_PROFILES = SEED / "archive_28cat_profiles.json"
AR_VECTORS = SEED / "archive_28cat_vectors.json.gz"


def _read_vectors(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def _write_vectors(path: Path, data: dict) -> None:
    path.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode("utf-8")))


def _mb(path: Path) -> str:
    return f"{path.stat().st_size / 1e6:.1f}MB" if path.exists() else "없음"


def archive() -> None:
    products = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILES.read_text(encoding="utf-8")) if PROFILES.exists() else {}
    vectors = _read_vectors(VECTORS)

    keep = [p for p in products if p.get("category") in STUDY_CATEGORIES]
    move = [p for p in products if p.get("category") not in STUDY_CATEGORIES]
    if not move:
        print("아카이브할 상품이 없습니다 — 이미 분리된 상태로 보입니다.")
        return
    move_ids = {p["id"] for p in move}
    keep_ids = {p["id"] for p in keep}

    # 프로필/벡터는 id 기준으로 가른다. 어느 쪽 상품에도 없는 고아는 아카이브로 보낸다
    # (활성 풀을 깨끗하게 유지하는 쪽을 기본값으로).
    ar_profiles = {k: v for k, v in profiles.items() if k not in keep_ids}
    ar_vectors = {k: v for k, v in vectors.items() if k not in keep_ids}
    orphans = len([k for k in ar_profiles if k not in move_ids])

    by_cat: dict[str, int] = {}
    for p in move:
        by_cat[p.get("category") or "?"] = by_cat.get(p.get("category") or "?", 0) + 1

    print(f"활성 유지 {len(keep):,}개 · 아카이브 {len(move):,}개 ({len(by_cat)}개 카테고리)")
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"    {cat:14} {n:6,}")
    if orphans:
        print(f"  ※ 상품 없는 고아 프로필 {orphans}건도 아카이브로 이동")

    # 아카이브를 먼저 쓰고 검증한 뒤에야 활성 파일을 줄인다 (중간에 죽어도 원본 보존).
    AR_PRODUCTS.write_text(json.dumps(move, ensure_ascii=False, indent=1), encoding="utf-8")
    AR_PROFILES.write_text(json.dumps(ar_profiles, ensure_ascii=False), encoding="utf-8")
    _write_vectors(AR_VECTORS, ar_vectors)
    assert len(json.loads(AR_PRODUCTS.read_text(encoding="utf-8"))) == len(move)

    PRODUCTS.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    PROFILES.write_text(
        json.dumps({k: v for k, v in profiles.items() if k in keep_ids}, ensure_ascii=False),
        encoding="utf-8")
    _write_vectors(VECTORS, {k: v for k, v in vectors.items() if k in keep_ids})

    print(f"\n활성  products {_mb(PRODUCTS)} · profiles {_mb(PROFILES)} · vectors {_mb(VECTORS)}")
    print(f"보관  products {_mb(AR_PRODUCTS)} · profiles {_mb(AR_PROFILES)} · vectors {_mb(AR_VECTORS)}")
    kept_cats: dict[str, int] = {}
    for p in keep:
        kept_cats[p.get("category") or "?"] = kept_cats.get(p.get("category") or "?", 0) + 1
    print("활성 카테고리: " + " · ".join(f"{c}={n:,}" for c, n in sorted(kept_cats.items())))


def restore() -> None:
    if not AR_PRODUCTS.exists():
        print("아카이브 파일이 없습니다 — 되돌릴 것이 없습니다.")
        return
    products = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    have = {p["id"] for p in products}
    back = [p for p in json.loads(AR_PRODUCTS.read_text(encoding="utf-8")) if p["id"] not in have]
    products.extend(back)
    PRODUCTS.write_text(json.dumps(products, ensure_ascii=False, indent=1), encoding="utf-8")

    profiles = json.loads(PROFILES.read_text(encoding="utf-8")) if PROFILES.exists() else {}
    profiles.update(json.loads(AR_PROFILES.read_text(encoding="utf-8")))
    PROFILES.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")

    vectors = _read_vectors(VECTORS)
    vectors.update(_read_vectors(AR_VECTORS))
    _write_vectors(VECTORS, vectors)
    print(f"복원 +{len(back):,}개 → 총 {len(products):,}개 · vectors {_mb(VECTORS)}")


if __name__ == "__main__":
    restore() if "--restore" in sys.argv else archive()
