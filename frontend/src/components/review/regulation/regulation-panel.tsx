"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { DEMO_VALIDATION_ID } from "@/api/demo-findings";
import { findingsQuery } from "@/api/findings";
import type { FindingSummary, Verdict } from "@/api/findings-schemas";
import { Foot, Pane, Row } from "@/components/shell/layout";
import { Button, Callout, Checkbox, PillTabs, Skeleton } from "@/components/ui";
import { FindingSourceViewer } from "../source-viewer";
import type { SortKey } from "../hazard/findings-table";
import { VERDICT_ORDER, severityRank, unresolvedNote } from "../hazard/verdict";
import { useReviewState } from "../review-state";
import { RegulationDetail } from "./regulation-detail";
import { RegulationTable } from "./regulation-table";

const LAWS = ["화관법", "산안법", "화평법", "위험물법"] as const;

/** "불일치만 보기"에 들어가는 판정. 구버전도 고칠 것이 있어 함께 보여 준다 */
const MISMATCH_VIEW: Verdict[] = ["mismatch", "outdated"];

const SORTS: { id: SortKey; label: string }[] = [
  { id: "verdict", label: "판정 순" },
  { id: "severity", label: "심각도 순" },
];

const verdictRank = (v: Verdict) => VERDICT_ORDER.indexOf(v);

/** 기본은 판정 종류 순 안에서 심각도 높음→낮음. 심각도 순은 심각도를 먼저 본다. */
function sortRows(rows: FindingSummary[], sort: SortKey) {
  return [...rows].sort((a, b) =>
    sort === "severity"
      ? severityRank(a.severity) - severityRank(b.severity) || verdictRank(a.verdict) - verdictRank(b.verdict)
      : verdictRank(a.verdict) - verdictRank(b.verdict) || severityRank(a.severity) - severityRank(b.severity),
  );
}

/** 2 검수 · 15항 법적 규제 탭: 왼쪽 원문, 오른쪽 위 선택한 판정의 상세, 아래 15항 판정 표 */
export function RegulationPanel({ docId, onSave }: { docId: string; onSave: () => void }) {
  const { data, isPending, isError, refetch } = useQuery(findingsQuery(docId, DEMO_VALIDATION_ID, { section: 15 }));
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
    return (
      <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
        <span>15항 판정을 불러오지 못했습니다.</span>
        <Button onClick={() => void refetch()}>다시 불러오기</Button>
      </Callout>
    );
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
                    label="불일치만 보기"
                    checked={onlyMismatch}
                    onChange={(e) => setOnlyMismatch(e.target.checked)}
                  />
                  <span className="text-xs text-mut">구버전 판정도 함께 보여 줍니다.</span>
                </div>
                <div role="group" aria-label="정렬 기준" className="flex items-center gap-1 text-sm text-mut">
                  <span>정렬</span>
                  {SORTS.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      aria-pressed={sort === s.id}
                      onClick={() => setSort(s.id)}
                      className={
                        sort === s.id
                          ? "rounded-sm bg-blue-soft px-2 py-0.5 font-bold text-blue2"
                          : "rounded-sm px-2 py-0.5 text-mut"
                      }
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
              <RegulationTable
                rows={rows}
                groups={data.groups}
                filtered={law !== "all" || onlyMismatch}
                selectedId={current?.finding_id}
                onSelect={setSelected}
              />
              <p className="text-sm text-mut">
                구버전: MSDS 개정 뒤에 시행된 개정이 있으면 시행일과 함께 표시합니다.
              </p>
            </div>
          </Pane>
        </div>
      </Row>

      <Foot>
        <p className="text-mut">
          {unresolvedNote(unresolvedByVerdict(15), "15항")}
        </p>
        <Button variant="primary" size="lg" onClick={onSave}>
          저장하기
        </Button>
      </Foot>
    </>
  );
}
