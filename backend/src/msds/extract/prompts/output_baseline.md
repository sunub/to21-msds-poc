# 근거 (evidence)
값을 넣은 곳마다 evidence 항목을 하나씩 만든다.
- field: msds 항목 안의 경로. 목록은 항목 단위(components[0], regulations[3]), 단일 칸은 칸 단위(meta.last_revision_date, hazard.signal_word)로 적는다.
- msds_index: 몇 번째 MSDS인지 (0부터).
- page: 그 값을 읽은 쪽 번호.
- source_text: 값을 가져온 원문을 그대로 옮긴다. 고치거나 요약하지 않는다. 200자 이내. 표에서 읽었으면 그 행의 글자를 " | "로 이어 적는다 (예: "황산 | 7664-93-9 | 93 ~ 98").

필수 칸(관리정보, 제품명·회사, 유해성 전체, 성분, 노출기준, 필수 물성, 급성독성, 운송, 국내 규제)은 근거를 빠짐없이 남긴다.
