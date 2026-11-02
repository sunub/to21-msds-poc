"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError } from "@/api/client";
import { documentKeys, retryDocument } from "@/api/documents";

/** 이 문서의 진행 상태를 뺀 캐시(결과, 재생성, 항별 값, 쪽 글)를 버린다. 다시 돌리면 이전 실행의 값이 된다 */
export function isDocumentChildQuery(id: string, queryKey: readonly unknown[]) {
  const detail = documentKeys.detail(id);
  return queryKey.length > detail.length && detail.every((part, i) => queryKey[i] === part);
}

/**
 * 문서 다시 돌리기. 어디서 부르든 캐시를 같게 다룬다.
 * 먼저 cancelQueries 하는 까닭: 나가 있던 폴링의 옛 응답(failed)이 새 상태(queued)를 덮으면 폴링이 멈춘 채 남는다.
 */
export function useRetryDocument(id: string, onDone?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => retryDocument(id),
    onMutate: () => queryClient.cancelQueries({ queryKey: documentKeys.detail(id), exact: true }),
    onSuccess: (next) => {
      queryClient.setQueryData(documentKeys.detail(id), next);
      queryClient.removeQueries({ predicate: (q) => isDocumentChildQuery(id, q.queryKey) });
      void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      onDone?.();
    },
    onError: (error) => {
      // 409: 다른 곳에서 이미 다시 돌렸다. 지금 상태를 받아 보여 준다
      if (error instanceof ApiRequestError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: documentKeys.detail(id), exact: true });
        void queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
        onDone?.();
      }
    },
  });
}
