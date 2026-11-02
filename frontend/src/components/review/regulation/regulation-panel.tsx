"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { findingsQuery } from "@/api/findings";
import type { Verdict } from "@/api/findings-schemas";
import { Foot, Pane, Row } from "@/components/shell/layout";
import { Button, Checkbox, PillTabs, Skeleton } from "@/components/ui";
import { FindingSourceViewer } from "../source-viewer";
import { unresolvedNote } from "../hazard/verdict";
import { useReviewState } from "../review-state";
import { LoadError } from "../shared/load-error";
import { sortRows, type SortKey } from "../shared/sort";
import { SortToggle } from "../shared/sort-toggle";
import { useValidationId } from "../shared/use-validation-id";
import { RegulationDetail } from "./regulation-detail";
import { RegulationTable } from "./regulation-table";

const LAWS = ["화관법", "산안법", "화평법", "위험물법"] as const;

/** "불일치만 보기"에 들어가는 판정. 구버전도 고칠 것이 있어 함께 보여 준다 */
const MISMATCH_VIEW: Verdict[] = ["mismatch", "outdated"];

/** 2 검수 · 15항 법적 규제 탭: 왼쪽 원문, 오른쪽 위 선택한 판정의 상세, 아래 15항 판정 표 */
export function RegulationPanel({ docId, onSave }: { docId: string; onSave: () => void }) {
  const validation = useValidationId(docId);
  const { data, isPending, isError, refetch } = useQuery(findingsQuery(docId, validation, { section: 15 }));
  const [law, setLaw] = useState("all");
  const [onlyMismatch, setOnlyMismatch] = useState(false);
  const [sort, setSort] = useState<SortKey>("verdict");
  // 다른 탭의 "이동"이 ?finding= 으로 넘긴 판정을 먼저 고른다. 값이 바뀌면(같은 탭에서 이동) 다시 그 판정으로 간다
  const findingParam = useSearchParams().get("finding") ?? undefined;
  const [selected, setSelected] = useState<string | undefined>(findingParam);
  const [seenParam, setSeenParam] = useState(findingParam);
  if (findingParam !== seenParam) {
    setSeenParam(findingParam);
    setSelected(findingParam);
    setLaw("all");
    setOnlyMismatch(false);
  }
  const { unresolvedByVerdict } = useReviewState();

  const rows = useMemo(
    () =>
      sortRows(data?.items ?? [], sort).filter(
        (r) => (law === "all" || r.law === law) && (!onlyMismatch || MISMATCH_VIEW.includes(r.verdict)),
      ),
    [data, law, onlyMismatch, sort],
  );

  if (isPending) return <Skeleton className="w-2/3" />;
  if (isError) {
    return <LoadError message="15항 판정을 불러오지 못했습니다." onRetry={() => void refetch()} />;
  }

  // 고른 행이 없거나 거르기로 사라졌으면 보이는 첫 행을 고른다
  const current = rows.find((r) => r.finding_id === selected) ?? rows[0];
  const lawItems = [
    { id: "all", label: `전체 ${data.items.length}` },
    ...LAWS.map((l) => ({ id: l, label: `${l} ${data.items.filter((f) => f.law === l).length}` })),
  ];

  return (
    <>
      <Row>
        <FindingSourceViewer
          docId={docId}
          refs={current?.source_refs.map((r) => r.page_no) ?? []}
          resetKey={current?.finding_id}
        />
        <div className="flex min-w-0 grow basis-105 flex-col gap-5">
          <Pane title="선택한 판정의 상세">
            {current ? (
              <RegulationDetail
                key={current.finding_id}
                docId={docId}
                validationId={data.validation_id}
                finding={current}
              />
            ) : (
              <p className="text-sm text-mut">표에서 판정을 고르면 상세가 여기에 나옵니다.</p>
            )}
          </Pane>
          <Pane title="15항 판정 표">
            <div className="flex flex-col gap-3">
              <PillTabs label="법령으로 거르기" items={lawItems} value={law} onChange={setLaw} />
              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <div className="flex flex-col">
                  <Checkbox
                    label="불일치·구버전만 보기"
                    checked={onlyMismatch}
                    onChange={(e) => setOnlyMismatch(e.target.checked)}
                  />
                </div>
                <SortToggle sort={sort} onSort={setSort} />
              </div>
              <RegulationTable
                rows={rows}
                groups={data.groups}
                filtered={law !== "all" || onlyMismatch}
                selectedId={current?.finding_id}
                onSelect={setSelected}
              />
              <p className="text-sm text-mut">구버전: MSDS 개정 뒤에 시행된 개정이 있으면 시행일과 함께 표시합니다.</p>
            </div>
          </Pane>
        </div>
      </Row>

      <Foot>
        <p className="text-mut">{unresolvedNote(unresolvedByVerdict(15), "15항")}</p>
        <Button variant="primary" size="lg" onClick={onSave}>
          저장하기
        </Button>
      </Foot>
    </>
  );
}
