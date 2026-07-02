"""Amazon 메타를 샘플 스캔해서 우리 5개 서브카테고리별로 '가격+이미지 둘 다 있는' 상품이
얼마나 되는지 파악(전체 파일로 외삽). 풀 크기 상한 추정용. 통째 다운로드 X — LINE_CAP까지만.

  cd backend && LINE_CAP=400000 PYTHONPATH=. .venv/bin/python scripts/scan_amazon_supply.py
"""
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
FILE_MB = {"meta_Electronics": 5246, "meta_Clothing_Shoes_and_Jewelry": 17960}


def _leaf_in(cats, names):
    return bool(cats) and str(cats[-1]).strip() in names


SUBCATS = {
    "태블릿": ("meta_Electronics", lambda t, c: _leaf_in(c, {"Tablets"})),
    "노트북": ("meta_Electronics", lambda t, c: "Laptops" in (c or []) and _leaf_in(c, {"Traditional Laptops", "2 in 1 Laptops", "Gaming Laptops", "Laptops"})),
    "무선이어폰": ("meta_Electronics", lambda t, c: _leaf_in(c, {"Earbud Headphones", "In-Ear Headphones"}) and not any(x in t for x in ["skin", "case", "cover", "cushion", "ear pad", "tips", "replacement", "sticker"])),
    "원피스": ("meta_Clothing_Shoes_and_Jewelry", lambda t, c: "Dresses" in (c or [])),
    "코트": ("meta_Clothing_Shoes_and_Jewelry", lambda t, c: any(n in (c or []) for n in ["Coats, Jackets & Vests", "Jackets & Coats"])),
}
FILES = sorted({v[0] for v in SUBCATS.values()})


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


def main():
    print(f"LINE_CAP={LINE_CAP:,}/file\n")
    for fname in FILES:
        subs = {lab: pred for lab, (f, pred) in SUBCATS.items() if f == fname}
        matched = {lab: 0 for lab in subs}    # 서브카 전체
        both = {lab: 0 for lab in subs}       # 가격+이미지 둘 다
        bytes_read, n = 0, 0
        req = urllib.request.Request(f"{BASE}/{fname}.jsonl", headers={"Authorization": f"Bearer {HF}"} if HF else {})
        resp = urllib.request.urlopen(req, timeout=180)
        for raw in resp:
            n += 1
            bytes_read += len(raw)
            if n > LINE_CAP:
                break
            try:
                r = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            title_l = (r.get("title") or "").lower()
            cats = r.get("categories") or []
            ok_both = parse_price(r.get("price")) is not None and has_image(r.get("images"))
            for lab, pred in subs.items():
                if pred(title_l, cats):
                    matched[lab] += 1
                    if ok_both:
                        both[lab] += 1
                    break
        # 외삽: 읽은 바이트 대비 전체 파일 크기 비율
        scale = (FILE_MB[fname] * 1_000_000) / max(bytes_read, 1)
        print(f"=== {fname}  (스캔 {n:,}줄 ≈ {bytes_read/1e6:.0f}MB / 전체 {FILE_MB[fname]:,}MB, ×{scale:.1f} 외삽) ===")
        for lab in subs:
            rate = both[lab] / matched[lab] * 100 if matched[lab] else 0
            print(f"  {lab:7} | 서브카 {matched[lab]:6,}  가격+이미지 {both[lab]:6,} ({rate:4.0f}%)  → 전체추정 ~{int(both[lab]*scale):,}개")
        print()


if __name__ == "__main__":
    main()
