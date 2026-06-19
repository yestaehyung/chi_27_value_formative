"""정크 정화 — products_stratified.labeled.json 에서 카테고리 오분류(비-상품)를 제거
→ products_stratified.clean.json.

판정 우선순위:
  1) 라벨러(서브에이전트)의 `offCategory` 플래그 — LLM 의미판단(정확). True면 제거, False면 유지.
  2) (레거시 폴백) 플래그가 없고 태그도 없는 상품만 도메인별 regex 정크 패턴으로 판정.
라벨링이 offCategory를 내면 regex는 거의 안 쓰임. 제거 목록을 전부 출력해 검수 가능.
사용: .venv/bin/python scripts/clean_pool.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "seed"
SRC = SEED / "products_stratified.labeled.json"
OUT = SEED / "products_stratified.clean.json"

# 위험한 단어(충전/케이블/마이크/정/패턴/SSD/모니터암)는 제외 — 실제 상품 오제거 방지.
ELEC = (r"무전기|리시버|이어마이크|측정기|이산화탄소|CCTV|베이비모니터|혈압|혈당|앰프|DAC|굿노트|"
        r"속지|다이어리|플래너|리딤|영양제|비니거|비타민|백팩|가방|슬리브|키스킨|키캡|스위치|이어패드|"
        r"도킹|USB허브|멀티허브|보조배터리|외장하드|동글|게임패드|장패드|마우스워시|마우스피스|입벌리개|"
        r"가글|마우스스프레이|보틀|독서등|목업|브라켓|선택기|레이저포인터|핫슈|메모보드|보안경|저울표시|"
        r"호출벨|슬리퍼|스니커즈|거치대|받침대|쿨러|케이스|충전기|테이블|소파|책상")
CLO = (r"변기|앞치마|우의|레인코트|침구|이불|페인트|마감재|코팅제|착색제|발수제|단추|부자재|뜨개|콘사|"
       r"줄바늘|대바늘|떡|이바지|예단|교구|펠트|옷본|도안|강아지|반려|애견|세탁세제|스포츠세제|무릎보호대|기저귀")


def main() -> None:
    prods = json.loads(SRC.read_text(encoding="utf-8"))
    removed: dict[str, list[str]] = defaultdict(list)
    clean = []
    n_flag = n_regex = 0
    for x in prods:
        # 1) 라벨러 명시 판정 우선
        if x.get("offCategory") is True:
            removed[x["category"]].append(x.get("title", "")[:42]); n_flag += 1; continue
        if x.get("offCategory") is False or x.get("tags"):
            clean.append(x); continue
        # 2) 레거시 폴백 — 플래그도 태그도 없을 때만 regex
        dom = (x.get("attributes") or {}).get("domain")
        text = f"{x.get('title','')} {x.get('description','')}"
        pat = ELEC if dom == "전자기기" else CLO if dom == "의류" else None
        if pat and re.search(pat, text):
            removed[x["category"]].append(x.get("title", "")[:42]); n_regex += 1
        else:
            clean.append(x)
    OUT.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in removed.values())  # NOTE: .values() — 카테고리 합계
    print(f"removed {total} junk (offCategory flag {n_flag} / regex fallback {n_regex}) → {len(clean)} clean ({OUT})\n")
    for cat, items in removed.items():
        print(f"━ {cat}: {len(items)}")
        for t in items:
            print(f"    - {t}")


if __name__ == "__main__":
    main()
