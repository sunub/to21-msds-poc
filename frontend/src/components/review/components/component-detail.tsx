"use client";

import Link from "next/link";
import { useState } from "react";
import type { ComponentSummary } from "@/api/judgment";
import { Card, PillTabs, StatusLabel, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  ateKey,
  ateLadder,
  ateTabLabel,
  classChip,
  classLabel,
  componentHeadline,
  defaultAteKey,
  groupBySource,
  reliabilityTone,
  sourcesAgree,
  type AteEntry,
} from "@/lib/components";
import { FLOAT_CARD } from "../regulation/regulation-table";

const ACUTE: Record<AteEntry["route"], string> = { oral: "HH_ACUTE_ORAL", dermal: "HH_ACUTE_DERMAL", inhal: "HH_ACUTE_INHAL" };

/** 시안 '성분별 요약' 오른쪽 카드: 성분 머리, 기준 분류, ATE를 가져온 순서(혼합물), 판정으로 가는 버튼 */
export function ComponentDetail({
  component,
  single,
  hazardHref,
  regulationHref,
}: {
  component: ComponentSummary;
  single: boolean;
  hazardHref: string;
  /** 이 성분의 15항 판정이 없으면 null */
  regulationHref: string | null;
}) {
  const name = component.name ?? component.cas ?? `성분 ${component.comp_ref}`;
  return (
    <Card className={cn(FLOAT_CARD, "flex min-w-0 flex-col gap-4 lg:h-full lg:min-h-0 lg:overflow-y-auto")}>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <h2 className="text-lg font-bold">{name}</h2>
        <span className="text-mut">{componentHeadline(component)}</span>
        <StatusLabel tone={reliabilityTone(component.reliability)} className="font-medium">
          자료 신뢰도 {component.reliability}
        </StatusLabel>
      </div>

      {single ? <SingleClasses component={component} /> : <MixtureClasses component={component} />}
      {single ? (
        <p className="text-sm text-mut">
          단일물질은 혼합물 계산을 하지 않고 기준 분류와 직접 비교합니다. 그래서 ATE 수집 순서는 보여 주지 않습니다.
        </p>
      ) : (
        <AteLadder ate={component.ate} />
      )}

      {component.notes.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-mut">
          {component.notes.map((n, i) => (
            <li key={`${i}-${n}`}>{n}</li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <Link href={hazardHref} className={buttonStyles()}>
          2항 판정 보기
        </Link>
        {regulationHref ? (
          <Link href={regulationHref} className={buttonStyles()}>
            15항 · 이 성분의 규제 보기
          </Link>
        ) : (
          <span className="self-center text-sm text-mut">이 성분의 15항 판정이 없습니다</span>
        )}
      </div>
    </Card>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-1.5 text-sm font-medium text-mut">{children}</div>;
}

function Chips({ chips }: { chips: string[] }) {
  if (chips.length === 0) return <p className="text-sm text-mut">분류 없음</p>;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {chips.map((c, i) => (
        <li key={`${i}-${c}`}className="rounded-xs bg-tint px-2 py-0.5 text-sm">
          {c}
        </li>
      ))}
    </ul>
  );
}

function MixtureClasses({ component }: { component: ComponentSummary }) {
  const sources = [...new Set(component.reference_classes.map((c) => c.source))];
  return (
    <div>
      <Label>기준 분류{sources.length > 0 && ` (${sources.join(", ")})`}</Label>
      <Chips chips={[...new Set(component.reference_classes.map(classChip))]} />
    </div>
  );
}

function SingleClasses({ component }: { component: ComponentSummary }) {
  const groups = groupBySource(component.reference_classes);
  return (
    <div>
      <Label>기준 분류 (출처별)</Label>
      {groups.length === 0 ? (
        <p className="text-sm text-mut">기준정보에 분류가 없습니다</p>
      ) : (
        <div className="flex flex-col gap-2">
          {groups.map((g) => (
            <div key={g.source} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="w-32 flex-none text-sm font-medium">{g.source}</span>
              <Chips chips={g.chips} />
            </div>
          ))}
        </div>
      )}
      {sourcesAgree(groups) && <p className="mt-1.5 text-sm text-mut">두 출처가 같아 어느 쪽을 써도 결과가 같습니다.</p>}
    </div>
  );
}

function AteLadder({ ate }: { ate: AteEntry[] }) {
  const [picked, setPicked] = useState<string | null>(null);
  const key = picked && ate.some((a) => ateKey(a) === picked) ? picked : defaultAteKey(ate);
  const entry = ate.find((a) => ateKey(a) === key);
  if (!entry) {
    return (
      <div>
        <Label>급성 독성 ATE를 가져온 순서</Label>
        <p className="text-sm text-mut">이 성분의 ATE 기록이 없습니다.</p>
      </div>
    );
  }
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-mut">{classLabel(ACUTE[entry.route])}
          {entry.form && ` · ${entry.form}`} ATE를 가져온 순서</span>
        {ate.length > 1 && (
          <PillTabs
            label="경로"
            items={ate.map((a) => ({ id: ateKey(a), label: ateTabLabel(a) }))}
            value={ateKey(entry)}
            onChange={setPicked}
          />
        )}
      </div>
      <ol className="flex flex-col gap-1">
        {ateLadder(entry).map((s) => (
          <li
            key={s.no}
            aria-current={s.state === "used" || undefined}
            className={cn("flex items-center gap-2.5 rounded-xs px-2.5 py-1.5", s.state === "used" && "bg-blue-soft")}
          >
            <b className="w-4.5 flex-none">{s.no}</b>
            <span className={cn("flex-1", s.state === "used" ? "font-bold" : "font-normal")}>{s.name}</span>
            <span className={cn("text-sm", s.state === "used" ? "font-bold text-blue2" : "text-mut")}>{s.text}</span>
          </li>
        ))}
      </ol>
      <p className="mt-1.5 text-sm text-mut">1~2단계는 신뢰도 높음, 3~4단계는 보통, 미상이 있으면 낮음입니다.</p>
    </div>
  );
}
