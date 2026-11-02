"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { documentKeys } from "@/api/documents";
import { FINAL_STATUSES, type JobStatus } from "@/api/schemas";
import { isDocumentChildQuery } from "./use-retry-document";

/**
 * 진행 상태가 바뀌는 순간의 캐시 처리.
 * 끝나면 목록을 새로 받고, 끝났던 문서가 다시 돌면(다른 탭에서 다시 시도) 이전 실행의 값을 버린다.
 */
export function useDocumentTransitions(id: string, status: JobStatus | undefined) {
  const queryClient = useQueryClient();
  const previous = useRef(status);

  useEffect(() => {
    const before = previous.current;
    previous.current = status;
    if (!before || !status || before === status) return;
    const wasFinal = FINAL_STATUSES.includes(before);
    const isFinal = FINAL_STATUSES.includes(status);
    if (!wasFinal && isFinal) void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    if (wasFinal && !isFinal) queryClient.removeQueries({ predicate: (q) => isDocumentChildQuery(id, q.queryKey) });
  }, [id, status, queryClient]);
}
