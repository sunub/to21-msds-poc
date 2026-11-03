/*
 * 추출 API 호출의 공통 입구. 모든 응답은 여기서 스키마로 parse 한 뒤에 돌려준다.
 * 실패는 두 가지로 나눈다:
 *   - ApiRequestError: 서버가 4xx·5xx 로 거절함 (본문은 ApiError 모양)
 *   - ApiContractError: 서버는 성공했는데 응답 모양이 계약(schemas.ts)과 다름 → 어느 쪽 버그인지 바로 보이게
 */
import type { z } from "zod";
import { apiErrorSchema } from "./schemas";

/**
 * API 주소 앞부분. 정적 export 라 빌드할 때 값이 박힌다.
 * 비워 두면 같은 출처(/api/...)로 부른다. 개발 중에 FastAPI 를 따로 띄우면 NEXT_PUBLIC_API_BASE 로 넘긴다.
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export class ApiContractError extends Error {
  constructor(
    readonly path: string,
    readonly issues: z.core.$ZodIssue[],
  ) {
    super(`응답 모양이 계약과 다릅니다: ${path} (${issues.map((i) => i.path.join(".") || "(최상위)").join(", ")})`);
    this.name = "ApiContractError";
  }
}

/** 다시 물어도 결과가 같은 실패: 4xx 와 계약 위반. 연결 끊김·5xx 는 나아질 수 있다 */
export function isPermanentError(error: unknown) {
  return (error instanceof ApiRequestError && error.status < 500) || error instanceof ApiContractError;
}

export function apiUrl(path: string, query?: Record<string, string>) {
  const q = query ? `?${new URLSearchParams(query).toString()}` : "";
  return `${BASE}${path}${q}`;
}

/**
 * FastAPI 오류 본문 { detail } 을 ApiRequestError 로 바꾼다.
 * detail 이 문장이면 그대로, 422 의 항목 목록이면 "어디: 무엇" 을 이어 붙인다. code 는 http_<상태> 또는 validation.
 */
export async function toRequestError(res: Response): Promise<ApiRequestError> {
  const body: unknown = await res.json().catch(() => null);
  const parsed = apiErrorSchema.safeParse(body);
  if (!parsed.success) return new ApiRequestError(res.status, "unknown", `서버가 ${res.status} 로 응답했습니다.`);
  const { detail } = parsed.data;
  if (typeof detail === "string") return new ApiRequestError(res.status, `http_${res.status}`, detail);
  const message = detail.map((d) => `${d.loc.join(".")}: ${d.msg}`).join("; ");
  return new ApiRequestError(res.status, "validation", message);
}

/** JSON 을 받아 schema 로 확인한다. 실패는 위 두 오류 중 하나로 던진다. */
export async function requestJson<S extends z.ZodType>(
  schema: S,
  path: string,
  init?: RequestInit & { query?: Record<string, string> },
): Promise<z.infer<S>> {
  const { query, ...rest } = init ?? {};
  const res = await fetch(apiUrl(path, query), {
    ...rest,
    headers: { Accept: "application/json", ...rest.headers },
  });
  if (!res.ok) throw await toRequestError(res);

  const parsed = schema.safeParse(await res.json());
  if (!parsed.success) throw new ApiContractError(path, parsed.error.issues);
  return parsed.data;
}
