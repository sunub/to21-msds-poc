"use client";

import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import {
  AiChip,
  Button,
  Card,
  Field,
  Input,
  PillTabs,
  Progress,
  Skeleton,
  Spinner,
  StatusLabel,
  Stepper,
  Table,
  TableHead,
  TableRow,
  Textarea,
  UnderlineTabs,
  type Tone,
} from "@/components/ui";

const SWATCHES: { group: string; items: { name: string; cls: string }[] }[] = [
  {
    group: "글자와 선",
    items: [
      { name: "ink", cls: "bg-ink" },
      { name: "sub", cls: "bg-sub" },
      { name: "mut", cls: "bg-mut" },
      { name: "outline", cls: "bg-outline" },
      { name: "field-line", cls: "bg-field-line" },
      { name: "line", cls: "bg-line" },
      { name: "line2", cls: "bg-line2" },
    ],
  },
  {
    group: "바탕",
    items: [
      { name: "surface", cls: "bg-surface" },
      { name: "bg", cls: "bg-bg" },
      { name: "tint", cls: "bg-tint" },
      { name: "sel", cls: "bg-sel" },
    ],
  },
  {
    group: "강조",
    items: [
      { name: "blue", cls: "bg-blue" },
      { name: "blue2", cls: "bg-blue2" },
      { name: "blue-soft", cls: "bg-blue-soft" },
      { name: "blue-line", cls: "bg-blue-line" },
    ],
  },
  {
    group: "상태",
    items: [
      { name: "red", cls: "bg-red" },
      { name: "amb", cls: "bg-amb" },
      { name: "warn", cls: "bg-warn" },
      { name: "grn", cls: "bg-grn" },
      { name: "gry", cls: "bg-gry" },
      { name: "stale", cls: "bg-stale" },
    ],
  },
];

const TONES: { tone: Tone; label: string }[] = [
  { tone: "info", label: "검수 중" },
  { tone: "success", label: "확정" },
  { tone: "warning", label: "확인 필요" },
  { tone: "danger", label: "원문과 다름" },
  { tone: "stale", label: "오래된 값" },
  { tone: "neutral", label: "미검수" },
];

const TYPE_SCALE = [
  { cls: "text-2xl font-bold", name: "2xl 24px · 화면 제목" },
  { cls: "text-xl font-bold", name: "xl 18px · 구역 제목" },
  { cls: "text-lg font-bold", name: "lg 16px · 머리글, 브랜드" },
  { cls: "text-base", name: "base 14px · 본문" },
  { cls: "text-sm text-mut", name: "sm 13px · 보조 설명" },
  { cls: "text-xs", name: "xs 12px · 주석, 칩" },
];

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-xl font-bold">{title}</h2>
        {note && <p className="mt-0.5 text-sm text-mut">{note}</p>}
      </div>
      {children}
    </Card>
  );
}

type SampleForm = { reviewer: string; memo: string };

export default function DesignSystemPage() {
  const [tab, setTab] = useState("sec2");
  const [view, setView] = useState("all");
  const [selected, setSelected] = useState(1);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SampleForm>({ defaultValues: { reviewer: "", memo: "" } });
  const [saved, setSaved] = useState<string | null>(null);

  return (
    <>
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex min-h-14 max-w-page items-center gap-2.5 px-8">
          <strong className="text-lg">MSDS 검수</strong>
          <span className="text-outline">/</span>
          <strong className="text-lg">디자인 시스템</strong>
          <span className="text-mut">v2 · 파랑 계열, 14px 본문, 얇은 선과 8px 모서리</span>
        </div>
      </header>
      <div className="border-b border-line bg-white">
        <div className="mx-auto max-w-page px-8">
          <Stepper
            current="review"
            steps={[
              { id: "extract", label: "추출" },
              { id: "review", label: "검수", note: "2항 · 15항" },
              { id: "save", label: "저장" },
            ]}
          />
        </div>
      </div>

      <main className="mx-auto flex max-w-page flex-col gap-5 px-8 pt-7 pb-14">
        <Section title="색" note="토큰은 src/styles/tokens.css 에서만 바꿉니다. 클래스 이름은 토큰 이름과 같습니다.">
          <div className="flex flex-col gap-3">
            {SWATCHES.map((g) => (
              <div key={g.group}>
                <p className="mb-1.5 text-sm font-bold text-mut">{g.group}</p>
                <ul className="m-0 flex list-none flex-wrap gap-3 p-0">
                  {g.items.map((s) => (
                    <li key={s.name} className="w-24">
                      <div className={`h-10 rounded-sm border border-line ${s.cls}`} />
                      <code className="text-xs">{s.name}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>

        <Section title="글자" note="한 글꼴(Noto Sans KR → Pretendard → 맑은 고딕)만 씁니다. 폐쇄망이라 웹폰트를 받지 않습니다.">
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {TYPE_SCALE.map((t) => (
              <li key={t.name} className="flex flex-wrap items-baseline gap-4">
                <span className={`w-72 ${t.cls}`}>CAS 7664-93-9 황산</span>
                <code className="text-xs text-mut">{t.name}</code>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="버튼">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">저장</Button>
            <Button variant="primary" size="lg">확정하고 다음 문서</Button>
            <Button>취소</Button>
            <Button variant="outline">원문 보기</Button>
            <Button variant="link">변경</Button>
            <Button variant="primary" disabled>저장</Button>
          </div>
        </Section>

        <Section title="상태 표시" note="색 점은 항상 글자와 함께 씁니다. 색만으로 뜻을 전하지 않습니다.">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {TONES.map((t) => (
              <StatusLabel key={t.tone} tone={t.tone}>
                {t.label}
              </StatusLabel>
            ))}
            <span className="inline-flex items-center gap-1.5 text-sm">
              <AiChip /> 모델이 채운 값
            </span>
          </div>
        </Section>

        <Section title="탭과 목록">
          <UnderlineTabs
            label="검수 구역"
            value={tab}
            onChange={setTab}
            items={[
              { id: "sec2", label: "2항" },
              { id: "sec15", label: "15항" },
              { id: "comp", label: "성분별 요약" },
              { id: "hist", label: "검토 이력" },
              { id: "raw", label: "추출값" },
            ]}
          />
          <PillTabs
            label="보기 필터"
            value={view}
            onChange={setView}
            items={[
              { id: "all", label: "전체" },
              { id: "todo", label: "미검수" },
              { id: "diff", label: "원문과 다름" },
            ]}
          />
          <Table>
            <TableHead>
              <span className="w-24">문서</span>
              <span className="flex-1">물질</span>
              <span className="w-28">상태</span>
            </TableHead>
            {[
              { id: "T21-M012", name: "황산", tone: "info" as Tone, s: "검수 중" },
              { id: "T21-S014", name: "수산화나트륨", tone: "success" as Tone, s: "확정" },
              { id: "T21-S016", name: "톨루엔", tone: "neutral" as Tone, s: "미검수" },
            ].map((r, i) => (
              <TableRow key={r.id} selected={i === selected} onClick={() => setSelected(i)}>
                <span className="w-24 font-mono text-sm">{r.id}</span>
                <span className="flex-1">{r.name}</span>
                <StatusLabel tone={r.tone} className="w-28">
                  {r.s}
                </StatusLabel>
              </TableRow>
            ))}
          </Table>
        </Section>

        <Section title="입력" note="react-hook-form 의 register() 를 그대로 펼쳐 씁니다. 오류 문구는 무엇이 잘못됐고 어떻게 고치는지 적습니다.">
          <form
            className="grid max-w-xl gap-4"
            onSubmit={handleSubmit((v) => setSaved(`${v.reviewer} 님의 검토를 저장했습니다.`))}
          >
            <Field id="reviewer" label="검토자" error={errors.reviewer?.message} hint="이름을 입력하세요.">
              <Input
                id="reviewer"
                aria-invalid={!!errors.reviewer}
                aria-describedby={errors.reviewer ? "reviewer-error" : "reviewer-hint"}
                {...register("reviewer", { required: "검토자 이름을 입력해야 저장할 수 있습니다." })}
              />
            </Field>
            <Field id="memo" label="메모">
              <Textarea id="memo" rows={3} {...register("memo")} />
            </Field>
            <div className="flex items-center gap-3 border-t border-line pt-4">
              <Button type="submit" variant="primary">저장</Button>
              {saved && <span role="status" className="text-sm text-grn">{saved}</span>}
            </div>
          </form>
        </Section>

        <Section title="진행과 불러오기">
          <div className="flex max-w-xl flex-col gap-4">
            <Progress value={62} label="쪽별 추출 진행률" />
            <div className="flex items-center gap-3">
              <Spinner /> <span className="text-mut">쪽 이미지를 만드는 중입니다.</span>
            </div>
            <div className="flex flex-col gap-2">
              <Skeleton className="w-2/3" />
              <Skeleton className="w-full" />
              <Skeleton className="w-1/2" />
            </div>
          </div>
        </Section>
      </main>
    </>
  );
}
