/*
 * 경고표지 그림문자 카탈로그 조회 (고시 별표의 분류별 그림문자·신호어·H/P 코드).
 * 이미지와 원본 기록은 public/msds-labels/<분류>/ 에 있고, catalog.json 은 원본 기록으로 만든다 (scripts/build-label-catalog.mjs).
 * 용도: GHS 그림문자는 경고표지, RTDG 그림문자는 운송 표지다.
 * 이전 판 분류(supersededBy)는 categoryById 로만 볼 수 있고 나머지 조회에서는 빠진다.
 */
import data from "../../public/msds-labels/catalog.json" with { type: "json" };

export type GhsImage = { file: string; src: string; code: string };
export type RtdgImage = {
  file: string;
  src: string;
  /** '8', '2.1', 수생환경 표지는 'environmental' */
  division: string;
  /** 같은 그림문자의 흑·백 판. 따로 없으면 null */
  variant: "black" | "white" | null;
};

export type LabelEntry = {
  /** 구분. 예: '피부 부식성 1A, 1B, 1C' */
  class: string;
  signal: string | null;
  ghs: { images: GhsImage[]; note: string | null };
  rtdg: {
    images: RtdgImage[];
    /** images 를 쓰는 방법. one_of: 하나만, all: 모두, null: 1개 이하 */
    pick: "one_of" | "all" | null;
    /** images 와 별도로 늘 함께 쓰는 그림문자 */
    required: RtdgImage[];
    note: string | null;
    requiredNote: string | null;
    altNote: string | null;
  };
  /** 급성 독성처럼 노출 경로마다 문구가 다를 때의 경로. 예: 'oral', '경구' */
  route: string | null;
  routeLabel: string | null;
  statements: {
    hazard: string[];
    prevention: string[];
    response: string[];
    storage: string[];
    disposal: string[];
    responseNote: string | null;
  };
};

export type LabelCategory = {
  /** public/msds-labels 아래 폴더 이름 */
  id: string;
  /** 고시 별표의 번호. 예: '1.2.2' */
  article: string;
  name: string;
  group: "physical" | "health" | "environmental";
  source: string;
  note: string | null;
  supersededBy: string | null;
  /** 원본 기록(codes.json) 경로 */
  record: string;
  entries: LabelEntry[];
};

export type LabelMatch = { category: LabelCategory; entry: LabelEntry };

const allCategories = data.categories as unknown as LabelCategory[];

/** 지금 쓰는 분류. 고시 번호 순서다 */
export const labelCategories: LabelCategory[] = allCategories.filter((category) => !category.supersededBy);

const allEntries: LabelMatch[] = labelCategories.flatMap((category) => category.entries.map((entry) => ({ category, entry })));

/** 'H360FD' → 'H360', 'P370+P380+P375[+P378]' → P370, P380, P375, P378 */
const baseCodes = (text: string) => text.match(/[HP]\d{3}/g) ?? [];

const usesGhs = ({ entry }: LabelMatch, code: string) => entry.ghs.images.some((image) => image.code === code);

function usesStatement({ entry }: LabelMatch, codes: string[]) {
  const { hazard, prevention, response, storage, disposal } = entry.statements;
  const own = [...hazard, ...prevention, ...response, ...storage, ...disposal].flatMap(baseCodes);
  return codes.some((code) => own.includes(code));
}

/**
 * 코드에 해당하는 분류 항목 전부. GHS05 같은 그림문자 코드, H314 같은 유해·위험 문구, P280 같은 예방조치 문구를 받는다.
 * 결합 코드(H302+H312)는 어느 하나라도 쓰는 항목을 찾고, 접미 문자(H360FD)는 떼고 찾는다.
 * 한 코드가 여러 분류에 걸칠 수 있어(H242는 자기반응성·유기과산화물) 늘 목록이다.
 */
export function entriesByCode(code: string): LabelMatch[] {
  if (/^GHS0[1-9]$/.test(code)) return allEntries.filter((match) => usesGhs(match, code));
  const codes = baseCodes(code);
  return codes.length ? allEntries.filter((match) => usesStatement(match, codes)) : [];
}

/** 이전 판을 포함해 폴더 이름으로 분류를 찾는다 */
export function categoryById(id: string): LabelCategory | undefined {
  return allCategories.find((category) => category.id === id);
}

/** 운송 등급의 RTDG 이미지 전부. 등급 하나에 분류별 판과 흑·백 판이 여러 장 있으니 variant 로 좁힐 수 있다 */
export function rtdgImagesByDivision(division: string, variant?: "black" | "white"): RtdgImage[] {
  const found = new Map<string, RtdgImage>();
  for (const { entry } of allEntries) {
    for (const image of [...entry.rtdg.images, ...entry.rtdg.required]) {
      if (image.division === division && (!variant || image.variant === variant)) found.set(image.src, image);
    }
  }
  return [...found.values()];
}
