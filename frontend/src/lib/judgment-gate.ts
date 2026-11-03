/*
 * 판정 입구(components/review/judgment-gate)가 무엇을 보일지 고르는 규칙. 화면과 분리한 순수 함수라
 * 서버 없이 시험한다 (judgment-gate.test.ts). 문서 상태와 판정 상태 조회 결과만 보고 정한다.
 */
import type { JudgmentStatus } from "@/api/judgment";

export type GateView<D = { status: string }> =
  /** 문서나 판정 상태를 아직 받는 중 */
  | { kind: "loading" }
  /** 추출이 끝나지 않아 판정할 수 없음 */
  | { kind: "not-extracted" }
  /** 판정 API가 서버에 아직 없음 */
  | { kind: "not-connected" }
  /** 판정 상태를 한 번도 받지 못함 */
  | { kind: "error"; error: unknown }
  /** 판정으로 넘긴 적이 없음 */
  | { kind: "start" }
  /** 판정이 돌고 있음 */
  | { kind: "judging" }
  /** 판정이 실패했거나, 있다는데 버전이 없음 */
  | { kind: "failed"; error: string | null }
  | {
      kind: "ready";
      doc: D;
      latest: number;
      /** 추출값이 바뀌어 다시 판정하는 중 */
      pending: boolean;
      /** 마지막으로 다시 묻기에 실패함 (이전 상태로 보여 준다) */
      offline: boolean;
    };

/** react-query 결과 중 여기서 쓰는 칸만 */
export type StatusQuery = {
  isPending: boolean;
  isError: boolean;
  isRefetchError: boolean;
  data?: JudgmentStatus;
  error: unknown;
};

export function gateView<D extends { status: string }>(
  doc: D | undefined,
  status: StatusQuery,
  isApiMissing: (error: unknown) => boolean,
): GateView<D> {
  if (!doc || (doc.status === "done" && status.isPending)) return { kind: "loading" };
  if (doc.status !== "done") return { kind: "not-extracted" };
  // 다시 묻기만 실패했으면 이전에 받은 상태로 계속 보인다 (offline)
  if (status.isError && !status.data) {
    return isApiMissing(status.error) ? { kind: "not-connected" } : { kind: "error", error: status.error };
  }
  const data = status.data as JudgmentStatus;
  if (data.state === "판정 없음") return { kind: "start" };
  if (data.state === "판정 중") return { kind: "judging" };
  if (data.state === "판정 실패" || data.latest_version === null) return { kind: "failed", error: data.error ?? null };
  return { kind: "ready", doc, latest: data.latest_version, pending: data.pending_handoff !== null, offline: status.isRefetchError };
}
