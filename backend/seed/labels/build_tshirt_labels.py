import json

ALLOWED = ["반팔", "긴팔", "맨투맨", "후드", "셔츠", "블라우스", "오버핏", "슬림", "베이직", "프린트", "데일리"]

# Per-id manual labels. Each derived ONLY from the title text.
# tags: subset of ALLOWED; attributes: small dict of title-stated specs; shortDesc: one Korean sentence.
LABELS = {
    # 무인양품 베이비 동물 프린트 크루넥 반소매 티셔츠
    "nv_2149800637215321699": {
        "tags": ["반팔", "프린트"],
        "attributes": {"sleeve": "반팔", "type": "티셔츠", "neck": "크루넥", "print": "동물 프린트"},
        "shortDesc": "동물 프린트가 들어간 크루넥 반소매 베이비 티셔츠.",
    },
    # 남성 무브 우븐 맨투맨
    "nv_1953134448585415989": {
        "tags": ["맨투맨"],
        "attributes": {"type": "맨투맨", "material": "우븐"},
        "shortDesc": "우븐 소재의 남성 맨투맨.",
    },
    # JAJU 여 슬럽 7부 티셔츠 (7부 = 3/4 sleeve, not 반팔/긴팔)
    "nv_6384619949777916726": {
        "tags": [],
        "attributes": {"type": "티셔츠", "sleeve": "7부"},
        "shortDesc": "슬럽 소재의 여성 7부 티셔츠.",
    },
    # 모달스판 가을 겨울 긴팔 실내복 (실내복 = loungewear/homewear, not a tee/shirt)
    "nv_5616126361883702535": {
        "tags": [],
        "attributes": {"sleeve": "긴팔", "type": "실내복", "material": "모달스판"},
        "shortDesc": "모달스판 소재의 가을·겨울용 긴팔 실내복으로, 티셔츠·셔츠가 아닌 실내복이다.",
    },
    # 미즈노 티셔츠 엠씨라인 롱 슬리브 (롱 슬리브 = 긴팔)
    "nv_2458497851854820931": {
        "tags": ["긴팔"],
        "attributes": {"sleeve": "긴팔", "type": "티셔츠"},
        "shortDesc": "미즈노 엠씨라인 긴팔(롱 슬리브) 티셔츠.",
    },
    # 미쏘 셔츠배색 카라 풀오버 (풀오버; '셔츠배색'은 배색 디테일 표현)
    "nv_3611766724124868011": {
        "tags": [],
        "attributes": {"type": "풀오버", "neck": "카라"},
        "shortDesc": "셔츠 배색의 카라 풀오버.",
    },
    # 삠뽀요 델리티셔츠 1+1 (티셔츠, 1+1 세트)
    "nv_1652578039954541012": {
        "tags": [],
        "attributes": {"type": "티셔츠"},
        "shortDesc": "1+1 세트로 구성된 델리 티셔츠.",
    },
    # 믹스 기능성 드라이 쿨티 무지 반팔 티셔츠 (남녀공용)
    "nv_7421444428803566188": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "티셔츠", "pattern": "무지", "feature": "기능성 드라이"},
        "shortDesc": "기능성 드라이 소재의 무지 반팔 티셔츠(남녀공용).",
    },
    # 도씨 소프킨 토마 긴팔 키즈 실내복 세트 (실내복, not tee/shirt)
    "nv_6826955368779750902": {
        "tags": [],
        "attributes": {"sleeve": "긴팔", "type": "실내복"},
        "shortDesc": "키즈용 긴팔 실내복 세트로, 티셔츠·셔츠가 아닌 실내복이다.",
    },
    # 언더아머 남성 UA 트레일 런 그래픽 티셔츠
    "nv_664127530991547117": {
        "tags": ["프린트"],
        "attributes": {"type": "티셔츠", "print": "그래픽"},
        "shortDesc": "그래픽이 들어간 남성 트레일 런 티셔츠.",
    },
    # 성인용 단체티 맨투맨 스웻셔츠 프린트스타 팀복 (주문제작) — '프린트스타'는 브랜드명일 수 있어 프린트 태그 제외
    "nv_4886275776439430265": {
        "tags": ["맨투맨"],
        "attributes": {"type": "맨투맨", "use": "단체티/팀복", "custom": "주문제작"},
        "shortDesc": "주문제작이 가능한 성인용 단체 맨투맨 스웻셔츠.",
    },
    # 구치 핀턱 라운드 밑단 오버핏 긴팔 롱 셔츠
    "nv_6895795630357468710": {
        "tags": ["긴팔", "셔츠", "오버핏"],
        "attributes": {"sleeve": "긴팔", "type": "셔츠", "fit": "오버핏"},
        "shortDesc": "핀턱과 라운드 밑단의 오버핏 긴팔 롱 셔츠.",
    },
    # 키예르 덤블 플리스 크롭 후드티 양털 루즈핏 긴팔 맨투맨 (후드+맨투맨+긴팔+오버핏(루즈핏))
    "nv_2605946955059805639": {
        "tags": ["긴팔", "맨투맨", "후드", "오버핏"],
        "attributes": {"sleeve": "긴팔", "type": "후드/맨투맨", "fit": "루즈핏", "material": "플리스/양털"},
        "shortDesc": "양털 플리스 소재의 크롭 기장 루즈핏 긴팔 후드 맨투맨.",
    },
    # 밀레나 심플 더블단추 노카라넥 긴팔 셔츠 블라우스
    "nv_1436329568600689466": {
        "tags": ["긴팔", "셔츠", "블라우스"],
        "attributes": {"sleeve": "긴팔", "type": "셔츠/블라우스", "neck": "노카라넥"},
        "shortDesc": "더블 단추의 노카라넥 긴팔 셔츠형 블라우스.",
    },
    # 아이더 세이프티 카라티 등산 티셔츠 기능성 여름 아이스 냉감 반팔
    "nv_2619067252079737742": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "티셔츠", "neck": "카라", "feature": "기능성 냉감"},
        "shortDesc": "여름용 아이스 냉감 기능성 카라 반팔 등산 티셔츠.",
    },
    # 베베쥬 레서베어맨투맨
    "nv_6575157858268570850": {
        "tags": ["맨투맨"],
        "attributes": {"type": "맨투맨"},
        "shortDesc": "레서베어 디자인의 맨투맨.",
    },
    # 바니블라썸 아기 방한모자 (모자, not a top)
    "nv_2406001178370830553": {
        "tags": [],
        "attributes": {"type": "모자"},
        "shortDesc": "유아용 극세사 방한 바라클라바 모자로, 티셔츠·셔츠가 아닌 모자이다.",
    },
    # 나이키 x 드레이크 녹타 NRG 티셔츠 (로고/콜라보; 명시적 프린트 표현 없음)
    "nv_248054084727941866": {
        "tags": [],
        "attributes": {"type": "티셔츠"},
        "shortDesc": "나이키 x 드레이크 녹타 NRG 티셔츠.",
    },
    # 올젠 남성 와플 라운드 티셔츠
    "nv_1421508747977327560": {
        "tags": [],
        "attributes": {"type": "티셔츠", "neck": "라운드", "material": "와플"},
        "shortDesc": "와플 소재의 남성 라운드넥 티셔츠.",
    },
    # 지오다노 맨투맨 남자 기모 프린트 겨울 오버핏 긴팔티셔츠
    "nv_5792340907443568652": {
        "tags": ["긴팔", "맨투맨", "오버핏", "프린트"],
        "attributes": {"sleeve": "긴팔", "type": "맨투맨", "fit": "오버핏", "print": "프린트", "material": "기모"},
        "shortDesc": "기모 안감의 프린트 오버핏 긴팔 맨투맨.",
    },
    # 코니 뉴본 코튼메쉬 바디수트 반팔 (바디수트, not a tee/shirt)
    "nv_4549812805869449657": {
        "tags": [],
        "attributes": {"sleeve": "반팔", "type": "바디수트"},
        "shortDesc": "신생아용 코튼메쉬 반팔 바디수트로, 티셔츠·셔츠가 아닌 바디수트이다.",
    },
    # 스케쳐스 남성 기모 베이직 후드 티셔츠
    "nv_4044690366540112285": {
        "tags": ["후드", "베이직"],
        "attributes": {"type": "후드", "material": "기모"},
        "shortDesc": "기모 안감의 베이직 후드 티셔츠.",
    },
    # 트라이 남성 체크 반팔 인견 파자마 잠옷 세트 (잠옷, not a tee/shirt)
    "nv_2059174276610423009": {
        "tags": [],
        "attributes": {"sleeve": "반팔", "type": "잠옷", "pattern": "체크", "material": "인견"},
        "shortDesc": "인견 소재의 체크 반팔 파자마 세트로, 티셔츠·셔츠가 아닌 잠옷이다.",
    },
    # 무지 드라이 기능성 쿨링플러스 쿨론 반팔 티셔츠
    "nv_8312780550056271586": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "티셔츠", "pattern": "무지", "feature": "기능성 쿨링"},
        "shortDesc": "쿨링 기능성 쿨론 소재의 무지 반팔 티셔츠.",
    },
    # 노스페이스 반팔 티셔츠 리에주 반팔 라운드 티
    "nv_8614281950640190385": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "티셔츠", "neck": "라운드"},
        "shortDesc": "노스페이스 리에주 라운드넥 반팔 티셔츠.",
    },
    # 앤드지 남성 우븐 카라 반팔티
    "nv_1757462489882552330": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "티셔츠", "neck": "카라", "material": "우븐"},
        "shortDesc": "우븐 소재의 남성 카라 반팔 티셔츠.",
    },
    # 나이키 남성 NSW 클럽 기모 플리스 크루 긴팔티 맨투맨
    "nv_2417075755134290968": {
        "tags": ["긴팔", "맨투맨"],
        "attributes": {"sleeve": "긴팔", "type": "맨투맨", "neck": "크루", "material": "기모 플리스"},
        "shortDesc": "기모 플리스 소재의 크루넥 긴팔 맨투맨.",
    },
    # 캘빈클라인 여성 와이어프리 티셔츠 브라 (브라/속옷, not a top)
    "nv_6739835761391499202": {
        "tags": [],
        "attributes": {"type": "브라"},
        "shortDesc": "여성용 와이어프리 티셔츠 브라로, 티셔츠·셔츠가 아닌 속옷(브라)이다.",
    },
    # 비스트모드 럭비져지 농구 나시 티셔츠 헬스 오버핏 짐웨어 (나시=민소매)
    "nv_9217627741560978938": {
        "tags": ["오버핏"],
        "attributes": {"sleeve": "나시(민소매)", "type": "티셔츠", "fit": "오버핏", "use": "짐웨어"},
        "shortDesc": "헬스용 오버핏 나시(민소매) 짐웨어 티셔츠.",
    },
    # 요넥스 배드민턴 여성 반팔 티셔츠
    "nv_3113179640599217664": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "티셔츠", "use": "배드민턴"},
        "shortDesc": "요넥스 여성 배드민턴 반팔 티셔츠.",
    },
    # 재주소년 챔피온맨투맨 키즈
    "nv_7802868028930723654": {
        "tags": ["맨투맨"],
        "attributes": {"type": "맨투맨"},
        "shortDesc": "재주소년 챔피온 키즈 맨투맨.",
    },
    # 밀크베이비 마카롱베이직유아티셔츠
    "nv_9132562573426026061": {
        "tags": ["베이직"],
        "attributes": {"type": "티셔츠"},
        "shortDesc": "마카롱 컬러의 베이직 유아 티셔츠.",
    },
    # 남아동용 긴팔 래쉬가드 수영복 (래쉬가드/수영복, not a regular tee/shirt)
    "nv_8649521626308766550": {
        "tags": [],
        "attributes": {"sleeve": "긴팔", "type": "래쉬가드"},
        "shortDesc": "주니어용 긴팔 래쉬가드 수영복 상의로, 티셔츠·셔츠가 아닌 수영복이다.",
    },
    # 헤지스 골프 남성 화이트 로고장식 반팔폴로티셔츠
    "nv_4445322513046124749": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "폴로 티셔츠", "use": "골프"},
        "shortDesc": "로고 장식의 남성 골프 반팔 폴로 티셔츠.",
    },
    # 줄리 보들 면 레이스카라 반팔맨투맨
    "nv_3046772606993202854": {
        "tags": ["반팔", "맨투맨"],
        "attributes": {"sleeve": "반팔", "type": "맨투맨", "neck": "레이스 카라", "material": "면"},
        "shortDesc": "면 소재의 레이스 카라 반팔 맨투맨.",
    },
    # 극세사잠옷 털 파자마 수면 기모 긴팔 겨울 커플 잠옷 세트 (잠옷, not a tee/shirt)
    "nv_3254449226613043737": {
        "tags": [],
        "attributes": {"sleeve": "긴팔", "type": "잠옷", "material": "극세사 기모"},
        "shortDesc": "극세사 기모 소재의 긴팔 커플 잠옷 세트로, 티셔츠·셔츠가 아닌 잠옷이다.",
    },
    # 제리 프린팅 빅사이즈 루즈핏 하의실종 오버핏 박스티셔츠
    "nv_5831299258608483614": {
        "tags": ["오버핏", "프린트"],
        "attributes": {"type": "티셔츠", "fit": "오버핏", "print": "프린팅"},
        "shortDesc": "프린팅이 들어간 빅사이즈 루즈핏 오버핏 박스 티셔츠.",
    },
    # 플레키 체크 셔츠
    "nv_5169676936577078728": {
        "tags": ["셔츠"],
        "attributes": {"type": "셔츠", "pattern": "체크"},
        "shortDesc": "체크 패턴의 셔츠.",
    },
    # 미엘 로건 셔츠 남방 체크 긴팔 카라 긴팔
    "nv_7748779407908879625": {
        "tags": ["긴팔", "셔츠"],
        "attributes": {"sleeve": "긴팔", "type": "셔츠/남방", "pattern": "체크", "neck": "카라"},
        "shortDesc": "체크 패턴의 카라 긴팔 셔츠(남방).",
    },
    # 미쥬 랩 오프숄더 기모 티셔츠
    "nv_7677396151643660044": {
        "tags": [],
        "attributes": {"type": "티셔츠", "neck": "오프숄더", "material": "기모"},
        "shortDesc": "기모 소재의 랩 오프숄더 티셔츠.",
    },
    # 1+1 후드 스트링 바람막이 조끼 아노락 베스트 오버핏 집업 (조끼/바람막이=아우터, not a tee/shirt)
    "nv_57869793743679464": {
        "tags": [],
        "attributes": {"type": "조끼/바람막이", "fit": "오버핏"},
        "shortDesc": "후드가 달린 오버핏 바람막이 조끼(베스트)로, 티셔츠·셔츠가 아닌 아우터이다.",
    },
    # 데일리 오버핏 무지맨투맨 긴팔티셔츠
    "nv_5123225976782659801": {
        "tags": ["긴팔", "맨투맨", "오버핏", "데일리"],
        "attributes": {"sleeve": "긴팔", "type": "맨투맨", "fit": "오버핏", "pattern": "무지"},
        "shortDesc": "데일리하게 입기 좋은 무지 오버핏 긴팔 맨투맨.",
    },
    # 유솔 UNI 양면 반짚 맨투맨
    "nv_4624021491967481895": {
        "tags": ["맨투맨"],
        "attributes": {"type": "맨투맨"},
        "shortDesc": "양면으로 입는 반집업 맨투맨.",
    },
    # 비합리적 소비자 티셔츠 (문구 티셔츠로 추정되나 명시적 프린트 표현 없음)
    "nv_8753444051900384170": {
        "tags": [],
        "attributes": {"type": "티셔츠"},
        "shortDesc": "'비합리적 소비자' 콘셉트의 티셔츠.",
    },
    # 티셔츠 주문 제작 마라톤 캠퍼스 링거티 코튼 소량 인쇄 반티
    "nv_7000297221983182547": {
        "tags": [],
        "attributes": {"type": "티셔츠", "use": "반티/단체티", "custom": "주문제작/인쇄", "material": "코튼"},
        "shortDesc": "소량 인쇄가 가능한 코튼 링거 반티 주문제작 티셔츠.",
    },
    # 누즈 델타 티셔츠
    "nv_4985176739770381801": {
        "tags": [],
        "attributes": {"type": "티셔츠"},
        "shortDesc": "누즈 델타 티셔츠.",
    },
    # 테테 단가라 원오프 크롭티셔츠
    "nv_6720543459765384296": {
        "tags": [],
        "attributes": {"type": "티셔츠", "length": "크롭"},
        "shortDesc": "단가라 패턴의 크롭 티셔츠.",
    },
    # 라코스테 클래식핏 폴로 PK 반팔 카라티셔츠
    "nv_4744603600099110195": {
        "tags": ["반팔"],
        "attributes": {"sleeve": "반팔", "type": "폴로 티셔츠", "neck": "카라", "fit": "클래식핏"},
        "shortDesc": "라코스테 클래식핏 PK 카라 반팔 폴로 티셔츠.",
    },
    # 온앤온 벨트 스트라이프 셔츠
    "nv_106947896021798245": {
        "tags": ["셔츠"],
        "attributes": {"type": "셔츠", "pattern": "스트라이프"},
        "shortDesc": "벨트 디테일의 스트라이프 셔츠.",
    },
    # 카미스타 스포츠이너웨어 긴팔 언더티 라운드 라이벌 컴프레션 (언더티/이너웨어=속옷성 상의)
    "nv_6611550707371929877": {
        "tags": ["긴팔"],
        "attributes": {"sleeve": "긴팔", "type": "언더티/컴프레션", "neck": "라운드", "use": "스포츠 이너웨어"},
        "shortDesc": "라운드넥 긴팔 컴프레션 스포츠 이너웨어(언더티)이다.",
    },
}


def main():
    with open("seed/products_stratified.json", encoding="utf-8") as f:
        data = json.load(f)
    ts = [p for p in data if p.get("category") == "티셔츠·셔츠"]

    out = []
    missing = []
    bad_tags = []
    for p in ts:
        pid = p["id"]
        if pid not in LABELS:
            missing.append(pid)
            continue
        lab = LABELS[pid]
        for t in lab["tags"]:
            if t not in ALLOWED:
                bad_tags.append((pid, t))
        out.append({
            "id": pid,
            "tags": lab["tags"],
            "attributes": lab["attributes"],
            "shortDesc": lab["shortDesc"],
        })

    assert not missing, f"Missing labels for: {missing}"
    assert not bad_tags, f"Tags not in allowed vocab: {bad_tags}"
    assert len(out) == len(ts), f"count mismatch {len(out)} vs {len(ts)}"

    with open("seed/labels/티셔츠·셔츠.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    total_tags = sum(len(o["tags"]) for o in out)
    print(f"WROTE {len(out)} products to seed/labels/티셔츠·셔츠.json")
    print(f"avg tags/item: {total_tags/len(out):.2f}")
    print(f"empty-tag items: {sum(1 for o in out if not o['tags'])}")


if __name__ == "__main__":
    main()
