"use client";

import Link from "next/link";
import { StatusLabel } from "@/components/ui";
import { verdictTone, type LimitationCard } from "@/lib/components";

/** 시안 '제약사항 · 검토 필요': 근거부족·경계 사유 카드. 판정이 있으면 그 판정 탭으로 간다 */
export function LimitationList({
  cards,
  hrefFor,
}: {
  cards: LimitationCard[];
  /** 판정 번호가 있는 카드의 이동 주소 */
  hrefFor: (card: LimitationCard) => string | null;
}) {
  return (
    <section aria-labelledby="limitations-title" className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2.5">
        <h2 id="limitations-title" className="text-base font-bold">
          제약사항 · 검토 필요
        </h2>
        {cards.length > 0 && <span className="text-sm text-mut">근거부족과 경계 사유를 한곳에 모았습니다. 먼저 확인해 주세요.</span>}
      </div>
      {cards.length === 0 ? (
        <div role="status" className="rounded-md border border-line bg-white px-4 py-3.5">
          <b>제약사항 없음</b>
          <p className="text-sm text-mut">근거부족이나 경계로 남은 판정이 없습니다.</p>
        </div>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {cards.map((card) => {
            const href = hrefFor(card);
            return (
              <li key={card.key} className="flex flex-col gap-1.5 rounded-md border border-line bg-white px-4 py-3.5">
                <div className="flex items-center justify-between gap-2">
                  <b className="break-words">{card.title}</b>
                  {card.verdict && <StatusLabel tone={verdictTone(card.verdict)}>{card.verdict}</StatusLabel>}
                </div>
                <p className="text-sm leading-relaxed break-words text-sub">{card.text}</p>
                {href && (
                  <Link href={href} className="text-sm font-medium text-blue2">
                    {card.section === "2" ? "2항" : "15항"} 판정에서 보기 ›
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
