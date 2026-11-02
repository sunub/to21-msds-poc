/*
 * 추출값 탭의 칸 이름(한글). 서버(review 응답)는 자기 사전에 없는 칸 이름을 영어 키 그대로 내려 준다
 * (예: department, health, class_code). 추출스키마 v0.6 의 칸 이름 중 서버 사전(backend service/review.py _LABEL)에
 * 없는 것을 여기서 한글로 바꾼다. 뜻은 스키마의 칸 설명(description)을 따랐다.
 * 사전에 없는 영어 키는 화면에 그대로 두고, 개발 모드에서만 콘솔로 알린다.
 */
export const FIELD_LABELS: Record<string, string> = {
  // 문서·추출 정보
  doc: "문서", doc_id: "문서 ID", source_file: "원본 파일명", page_count: "전체 쪽수", text_layer: "텍스트층", language: "문서 언어",
  msds_count: "MSDS 수", schema_version: "스키마 버전", dictionary_version: "동의어 사전 버전", extraction: "추출 정보",
  engine: "추출 엔진", extracted_at: "추출 일시", msds: "MSDS", meta: "문서 정보", page_start: "시작 쪽", page_end: "끝 쪽",
  // 제품·회사
  product: "제품", use_category_code: "용도분류 코드", companies: "회사", site: "사업장명", postcode: "우편번호", department: "담당부서",
  contacts: "연락처", hours: "운영시간",
  // 유해성·표지
  hazard: "유해성", classified: "분류 해당 여부", classes: "분류", group: "유해성 구분", class_code: "분류 코드", category: "구분",
  route_form: "노출 형태", effect: "영향 구분", target_organs: "표적장기", pictograms: "그림문자", detection: "판독 방식",
  h_statements: "유해·위험 문구", system: "코드 체계", mark: "각주 기호", p_statements: "예방조치 문구", other_hazards: "기타 유해성",
  nfpa: "NFPA", health: "NFPA 보건", fire: "NFPA 화재", reactivity: "NFPA 반응성", special: "NFPA 특수",
  // 구성성분
  composition: "구성", no_hazardous_component: "유해성분 미함유 표기", components: "성분", content: "함유량", narratives: "서술 문장",
  statements: "문장 목록",
  // 노출 기준
  exposure_limits: "노출 기준", standard: "기준 출처", limit_type: "기준 종류", q: "기준값", form: "입자 형태", kr_basis: "국내 기준 구분",
  bio_medium: "시료 매체", bio_timing: "채취 시기", bio_determinant: "지표 물질", notations: "표기",
  // 물리화학·독성·환경
  physchem: "물리화학적 특성", toxicity: "독성", endpoint: "독성 항목", descriptor: "지표", species: "시험종", sex: "성별",
  duration_value: "노출 시간", duration_unit: "노출 시간 단위", physical_form: "흡입 형태", exposure_type: "노출 형태",
  converted: "환산값", guideline: "시험 지침", classification: "분류 결과", cmr: "발암성 등", agency: "분류 기관·법령",
  class: "분류 등급", ecotox: "환경 영향", temp: "온도", temp_unit: "온도 단위", pressure: "압력", pressure_unit: "압력 단위",
  reference: "기준 물질", conc_value: "농도", conc_unit: "농도 단위",
  // 운송
  transport: "운송", mode: "운송 규정", basis_raw: "적용 규정 원문", regulated: "운송 규제 해당", un_no: "유엔번호",
  shipping_name: "적정 선적명", hazard_class: "위험성 등급", sub_risk: "부위험성", packing_group: "용기등급",
  marine_pollutant: "해양오염물질", ems_fire: "화재 비상조치(EmS)", ems_spill: "유출 비상조치(EmS)",
  // 규제·위험물·폐기물·국제 분류
  regulations: "규제", law: "법령", item_raw: "항목 원문", applicable: "해당 여부", threshold: "기준 농도", qty: "규제 수량",
  qty_alt: "규제 수량(병기 단위)", sub_class: "세부 구분", cycle: "측정·진단 주기", country: "국가", value_raw: "값 원문",
  remark: "부가 표기", dangerous_goods: "위험물", item: "품명", water_soluble: "수용성 구분", grade: "위험등급",
  designated_qty: "지정수량", waste: "폐기", designated: "지정폐기물", waste_type: "폐기물 종류", intl_class: "국제 분류",
  class_raw: "분류 표기", h_code: "H 코드",
  // 근거·검증·검토 (추출 결과에 같이 오는 칸)
  evidence: "근거", field: "대상 칸", bbox: "영역 좌표", source_text: "근거 원문", confidence: "신뢰도", method: "추출 방식",
  needs_review: "사람 검토 필요", validation: "검증", rule: "위반 규칙", level: "수준", message: "내용", review_status: "검토 상태",
  review_note: "검토 메모", extras: "기타", _comment: "메모", conc: "농도",
};

const warned = new Set<string>();
/** 영어 키처럼 보이는 낱말: 소문자로 시작하는 영문·숫자·밑줄 */
const RAW_KEY = /^[a-z][a-z0-9_]*$/;

/**
 * 서버가 준 칸 이름 중 영어 키를 한글로 바꾼다. 이름이 "이명 value"처럼 여러 낱말이면 낱말마다 본다.
 * 한글이거나 사전에 없는 것은 그대로 둔다 (사전에 없는 영어 키는 개발 모드에서만 콘솔로 알린다).
 */
export function fieldLabel(label: string): string {
  return label
    .split(" ")
    .map((word) => {
      if (!RAW_KEY.test(word)) return word;
      const ko = FIELD_LABELS[word];
      if (ko) return ko;
      if (process.env.NODE_ENV !== "production" && !warned.has(word)) {
        warned.add(word);
        console.warn(`[field-labels] 한글 이름이 없는 칸: ${word} (lib/field-labels.ts 에 추가하세요)`);
      }
      return word;
    })
    .join(" ");
}
