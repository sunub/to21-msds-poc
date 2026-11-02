/*
 * 2항·15항 판정 쿼리. 서버 응답은 판정 한 벌(judgment_view)이고, 판정 목록·상세는 거기서 화면 모델로 바꿔 쓴다 (api/adapt).
 * 판정·성분 요약·검토 상태가 같은 요청 하나를 나눠 쓴다. version 은 "latest"(기본)나 판정 버전 번호.
 */
import { queryOptions } from "@tanstack/react-query";
import { adaptDetail, adaptFindings, type FindingsParams } from "./adapt/findings";
import { judgmentViewQuery } from "./judgments";

export type { FindingsParams };

/** 판정 목록 */
export const findingsQuery = (doc: string, version = "latest", params: FindingsParams = {}) =>
  queryOptions({ ...judgmentViewQuery(doc, version), select: (view) => adaptFindings(view, params) });

/** 판정 한 건의 상세 */
export const findingDetailQuery = (doc: string, version: string, findingId: string) =>
  queryOptions({ ...judgmentViewQuery(doc, version), select: (view) => adaptDetail(view, findingId) });
