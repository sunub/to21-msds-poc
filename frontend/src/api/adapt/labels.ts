/*
 * 계약의 코드값(class_code, law, 규제 항목 코드)을 화면 이름으로 바꾸는 표.
 * 계약에는 이름표가 없어 화면이 가진다. 표에 없는 코드는 코드 그대로 보여 준다.
 * 규제 항목 코드(item_code) 목록은 계약에 없다: 아래 이름은 시안·데모에서 쓴 것이고 실제 코드는 서버 확정 후 맞출 것.
 */
import type { Finding } from "../contract/consistency";

/** 법령 이름 (화면의 법령 알약 이름과 같다) */
export const LAW_LABEL: Record<string, string> = {
  OSH: "산안법",
  KREACH: "화평법",
  CCA: "화관법",
  DG: "위험물법",
  WASTE: "폐기물관리법",
  POPS: "잔류성오염물질관리법",
  KR_ETC: "기타 국내법",
  INTL: "해외 법령",
};

/** 판정 표의 항목 이름 */
export const CLASS_LABEL: Record<string, string> = {
  HH_ACUTE_ORAL: "급성 독성(경구)",
  HH_ACUTE_DERMAL: "급성 독성(경피)",
  HH_ACUTE_INHAL: "급성 독성(흡입)",
  HH_SKIN_CORR: "피부 부식성/자극성",
  HH_EYE_DMG: "심한 눈 손상성/자극성",
  HH_RESP_SENS: "호흡기 과민성",
  HH_SKIN_SENS: "피부 과민성",
  HH_MUTAGEN: "생식세포 변이원성",
  HH_CARCINOGEN: "발암성",
  HH_REPRO: "생식독성",
  HH_STOT_SE: "특정표적장기(1회)",
  HH_STOT_RE: "특정표적장기(반복)",
  HH_ASPIRATION: "흡인 유해성",
  ENV_AQ_ACUTE: "급성 수생환경",
  ENV_AQ_CHRONIC: "만성 수생환경",
  ENV_OZONE: "오존층 유해성",
  PH_FLAM_GAS: "인화성 가스",
  PH_PRESS_GAS: "고압가스",
  PH_EXPLOSIVE: "폭발성 물질",
  PH_AEROSOL: "에어로졸",
  PH_OXID_GAS: "산화성 가스",
  PH_FLAM_LIQ: "인화성 액체",
  PH_FLAM_SOL: "인화성 고체",
  PH_SELF_REACT: "자기반응성 물질",
  PH_PYRO_LIQ: "자연발화성 액체",
  PH_PYRO_SOL: "자연발화성 고체",
  PH_SELF_HEAT: "자기발열성 물질",
  PH_WATER_REACT: "물반응성 물질",
  PH_OXID_LIQ: "산화성 액체",
  PH_OXID_SOL: "산화성 고체",
  PH_ORG_PEROX: "유기과산화물",
  PH_METAL_CORR: "금속부식성",
  PH_DESENS_EXPL: "둔감화된 폭발물",
  ETC_UNMAPPED: "분류 미매핑",
};

/** 성분 요약의 분류 칩 이름 (짧은 이름) */
export const CLASS_SHORT: Record<string, string> = {
  HH_SKIN_CORR: "피부",
  HH_EYE_DMG: "눈",
  HH_CARCINOGEN: "발암성",
  HH_STOT_SE: "표적장기(1회)",
  PH_FLAM_GAS: "인화성 가스",
  PH_PRESS_GAS: "고압가스",
};

/** 규제 항목 이름. 키는 계약의 item 에서 법령 부분을 뺀 코드 (예: CCA.CCA_TOXIC → CCA_TOXIC) */
export const REGULATION_LABEL: Record<string, string> = {
  OSH_MEASURE: "작업환경측정 대상",
  OSH_HEALTH_EXAM: "특수건강진단 대상",
  OSH_PSM: "공정안전보고서 대상",
  OSH_PERMISSIBLE: "허용기준 설정물질",
  CCA_TOXIC: "유독물질",
  CCA_ACCIDENT: "사고대비물질",
  CCA_EMISSION: "배출량조사 대상",
  KREACH_REG_EXIST: "등록대상기존화학물질",
};

/** ATE 를 가져오는 6단계의 이름과 순서 (시안) */
export const ATE_STEP_LABELS = ["독성DB 수치", "분류 구분 → 환산값", "MSDS 11항 수치", "부등호 값만 있음", "무독성 성분", "자료 없음"];

/** 급성 독성 경로 이름 (성분 요약의 사용 ATE 문장) */
export const ACUTE_ROUTE: Record<string, string> = { HH_ACUTE_ORAL: "경구", HH_ACUTE_DERMAL: "경피", HH_ACUTE_INHAL: "흡입" };

/** 판정 표에 보이는 항목 이름 */
export function itemName(f: Pick<Finding, "kind" | "item">): string {
  switch (f.kind) {
    case "class":
      return CLASS_LABEL[f.item] ?? f.item;
    case "label":
      return f.item === "SIGNAL" ? "신호어" : `표시 요소 ${f.item}`;
    case "regulation": {
      const code = f.item.includes(".") ? f.item.slice(f.item.indexOf(".") + 1) : f.item;
      return REGULATION_LABEL[code] ?? code;
    }
    case "dangerous_goods":
      return "위험물";
    case "product_type":
      return "제품 유형(단일·혼합)";
  }
}

/** 규제 판정의 법령 이름. 규제가 아니면 null */
export function lawName(f: Pick<Finding, "kind" | "item">): string | null {
  if (f.kind === "dangerous_goods") return LAW_LABEL.DG;
  if (f.kind !== "regulation") return null;
  const law = f.item.split(".")[0];
  return LAW_LABEL[law] ?? law;
}
