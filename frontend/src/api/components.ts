/*
 * 성분별 요약 쿼리. 계약에 성분 요약 API 가 없어, 판정 한 벌(judgment_view)에서 만든다 (adapt/components.ts).
 * product 는 데모 문서에서만 듣는다 (&product=single·unknown, 백엔드 없이 단일물질·판별 불가 화면을 보려는 용도).
 */
import { queryOptions } from "@tanstack/react-query";
import { adaptComponents } from "./adapt/components";
import { judgmentViewQuery } from "./judgments";

export type ComponentsParams = { msdsId?: string; product?: "single" | "unknown" };

export const componentsQuery = (doc: string, version = "latest", params: ComponentsParams = {}) =>
  queryOptions({ ...judgmentViewQuery(doc, version, params.product), select: adaptComponents });
