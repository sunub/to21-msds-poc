"use client";

import Link from "next/link";
import type { ComponentSummary } from "@/api/components-schemas";
import type { FindingSummary } from "@/api/findings-schemas";
import { StatusLabel, type Tone } from "@/components/ui";
import { VERDICT_LABEL } from "../hazard/verdict";
import { findingHref } from "../unresolved-list";
import { CONFIDENCE } from "./format";

type Card = { key: string; title: string; label: string; tone: Tone; text: string; href: string | null; linkText: string };

/**
 * 제약사항·검토 필요: 성분들의 근거부족·경계 사유와, 신뢰도가 높지 않은 이유를 한곳에 모은다.
 * 신뢰도와 사유는 서버가 준 값을 그대로 쓴다.
 */
function buildCards(docId: string, items: ComponentSummary[], findingsById: Map<string, FindingSummary>): Card[] {
  const cards: Card[] = [];
  const seen = new Set<string>();
  const add = (card: Card) => {
    if (!seen.has(card.key)) {
      seen.add(card.key);
      cards.push(card);
    }
  };
  for (const c of items) {
    for (const l of c.limitations) {
      const f = l.finding_id ? findingsById.get(l.finding_id) : undefined;
      add({
        key: `lim:${l.finding_id ?? c.component_id}:${l.kind}`,
        title: f?.item ?? c.name,
        label: l.kind === "insufficient" ? VERDICT_LABEL.insufficient_evidence : VERDICT_LABEL.borderline,
        tone: l.kind === "insufficient" ? "neutral" : "warning",
        text: l.reason,
        href: f ? findingHref(docId, f) : null,
        linkText: f ? `${f.section}항 판정에서 보기 ›` : "",
      });
    }
    if (c.confidence.level === "medium" || c.confidence.level === "low") {
      const link = c.target_links.find((t) => t.section === 2);
      const f = link ? findingsById.get(link.finding_id) : undefined;
      add({
        key: `conf:${c.component_id}`,
        title: f?.item ?? c.name,
        label: `신뢰도 ${CONFIDENCE[c.confidence.level].label}`,
        tone: CONFIDENCE[c.confidence.level].tone,
        text: c.confidence.reason,
        href: f ? findingHref(docId, f) : null,
        linkText: f ? `${f.section}항 판정에서 보기 ›` : "",
      });
    }
  }
  return cards;
}

export function Constraints({
  docId,
  items,
  findingsById,
}: {
  docId: string;
  items: ComponentSummary[];
  findingsById: Map<string, FindingSummary>;
}) {
  const cards = buildCards(docId, items, findingsById);
  if (cards.length === 0) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-md border border-dashed border-field-line bg-white p-5">
        <span className="font-bold">제약사항 없음</span>
        <span className="text-mut">근거부족이나 경계로 남은 판정이 없습니다.</span>
      </div>
    );
  }
  return (
    <ul className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(15rem,1fr))] gap-3 p-0">
      {cards.map((c) => (
        <li key={c.key} className="flex flex-col gap-1.5 rounded-md border border-line bg-white px-4 py-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <b className="break-keep">{c.title}</b>
            <StatusLabel tone={c.tone}>{c.label}</StatusLabel>
          </div>
          <p className="text-sm leading-relaxed break-keep text-sub">{c.text}</p>
          {c.href && (
            <Link href={c.href} className="self-start text-sm">
              {c.linkText}
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}
