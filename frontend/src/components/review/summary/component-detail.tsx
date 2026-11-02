"use client";

import Link from "next/link";
import type { ComponentSummary, ProductType } from "@/api/components-schemas";
import type { FindingSummary } from "@/api/findings-schemas";
import { StatusLabel, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { findingHref } from "../unresolved-list";
import { confidenceView, formatConcentration, groupBySource, sourcesAgree, stepStatus } from "./format";

const chip = "rounded-xs bg-blue-soft px-1.5 py-px text-xs font-medium text-blue2";

/** 성분 상세: 기준 분류, ATE 를 가져온 순서(혼합물) 또는 출처별 기준 분류 비교(단일물질), 판정으로 가는 버튼 */
export function ComponentDetail({
  docId,
  product,
  component: c,
  findingsById,
  ruleVersion,
}: {
  docId: string;
  product: ProductType;
  component: ComponentSummary;
  findingsById: Map<string, FindingSummary>;
  ruleVersion: string | null;
}) {
  const conf = confidenceView(c.confidence);
  const groups = groupBySource(c.classifications);
  const compare = product === "single" || groups.length > 1;
  const basis = c.classifications[0]?.basis ?? "기준";

  // 이 성분의 2항 판정으로 가는 버튼들, 15항 규제로 가는 버튼
  const hazardLinks = c.target_links
    .filter((t) => t.section === 2)
    .map((t) => ({ t, f: findingsById.get(t.finding_id) }));
  const firstLegal = c.legal_findings[0];
  const legalFinding = firstLegal ? findingsById.get(firstLegal.finding_id) : undefined;
  const legalHref = firstLegal
    ? legalFinding
      ? findingHref(docId, legalFinding)
      : `${routes.review(docId, "regulation")}&finding=${encodeURIComponent(firstLegal.finding_id)}`
    : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-xl font-bold">{c.name}</h3>
        <span className="text-mut">
          {c.cas_no ?? "—"} · {formatConcentration(c.concentration, true)}
        </span>
        <StatusLabel tone={conf.tone} className="text-base font-medium">
          자료 신뢰도 {conf.label}
        </StatusLabel>
      </div>

      {c.ate_steps.length === 0 && (
        <div className="rounded-sm bg-tint px-3.5 py-2.5 text-sm leading-relaxed">
          {product === "single"
            ? "단일물질은 혼합물 계산을 하지 않고 기준 분류와 직접 비교합니다. 그래서 ATE 수집 순서는 보여 주지 않습니다."
            : "이 성분에는 ATE 단계 정보가 없습니다."}
        </div>
      )}

      <div>
        <h4 className="mb-1.5 text-sm font-bold text-mut">{compare ? "기준 분류 (출처별)" : `기준 분류 (${basis})`}</h4>
        {compare ? (
          <div className="flex flex-col gap-1.5">
            {groups.map((g) => (
              <div key={g.source} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <b className="w-36 flex-none">{g.source}</b>
                {g.chips.map((x) => (
                  <span key={x} className={chip}>
                    {x}
                  </span>
                ))}
              </div>
            ))}
            {sourcesAgree(groups) && <p className="mt-1 text-sm text-mut">두 출처가 같아 어느 쪽을 써도 결과가 같습니다.</p>}
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {(groups[0]?.chips ?? []).map((x) => (
              <span key={x} className={chip}>
                {x}
              </span>
            ))}
          </div>
        )}
      </div>

      {c.ate_steps.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-sm font-bold text-mut">급성 독성(흡입) ATE를 가져온 순서</h4>
          <ol aria-label="ATE를 가져온 순서" className="m-0 flex list-none flex-col gap-1 p-0">
            {c.ate_steps.map((s) => (
              <li
                key={s.step}
                aria-current={s.adopted || undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-sm border px-2.5 py-1.5",
                  s.adopted ? "border-blue-line bg-blue-soft" : "border-transparent",
                )}
              >
                <b className="w-4.5 flex-none">{s.step}</b>
                <span className={cn("min-w-0 flex-1 break-keep", s.adopted ? "font-bold" : "font-normal")}>{s.label}</span>
                <span className={cn("text-sm", s.adopted ? "font-bold text-blue2" : "text-mut")}>
                  {s.adopted && <span aria-hidden="true">● </span>}
                  {stepStatus(s)}
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-1.5 text-sm text-mut">
            1~2단계는 신뢰도 높음, 3~4단계는 보통, 미상이 있으면 낮음입니다.
            {ruleVersion && ` (신뢰도 규칙 ${ruleVersion})`}
          </p>
        </div>
      )}

      {(hazardLinks.length > 0 || legalHref || product === "single") && (
        <div className="flex flex-wrap gap-2">
          {hazardLinks.length > 0 ? (
            hazardLinks.map(({ t, f }) => (
              <Link key={t.finding_id} href={f ? findingHref(docId, f) : `${routes.review(docId, "hazard")}&finding=${t.finding_id}`} className={buttonStyles()}>
                2항 · {f?.item ?? "판정"} 보기
              </Link>
            ))
          ) : (
            <Link href={routes.review(docId, "hazard")} className={buttonStyles()}>
              2항 판정 보기
            </Link>
          )}
          {legalHref && (
            <Link href={legalHref} className={buttonStyles()}>
              {product === "single" ? "15항 · 규제 보기" : "15항 · 이 성분의 규제 보기"}
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
