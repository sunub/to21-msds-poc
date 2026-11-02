/*
 * 계약의 구조값(category, route_form, code, applicable, threshold, content, dg)을
 * 화면이 보여 주던 문장형 텍스트로 바꾼다 (예: "구분2 (증기)", "해당 (10% 이상)").
 * 판정 변환 계층(api/adapt)이 쓴다.
 */
import type { z } from "zod";
import type { Q } from "@/api/contract/common";
import type { Finding, Side } from "@/api/contract/consistency";

type QValue = z.infer<typeof Q>;

const UNIT_SPACED = (unit: string) => (unit === "%" ? unit : ` ${unit}`);

/**
 * TO21 수치 객체(Q)를 짧은 글로. 숫자가 있으면 숫자로 만들고(범위 "93~98%", 하한 "10% 이상"), 없으면 원문(raw), 그것도 없으면 상태.
 * symbol 이 true 면 부등호를 기호로 쓴다 ("≥ 10%"): 검증 결과 쪽 표기.
 */
export function formatQ(q: QValue | null | undefined, symbol = false): string {
  if (!q) return "";
  const unit = q.unit ? UNIT_SPACED(q.unit) : "";
  const hasLower = typeof q.lower === "number";
  const hasUpper = typeof q.upper === "number";
  if (hasLower && hasUpper) return `${q.lower}~${q.upper}${unit}`;
  if (typeof q.value === "number") return `${q.value}${unit}`;
  if (hasLower) {
    const ge = q.lower_op !== ">";
    return symbol ? `${ge ? "≥" : ">"} ${q.lower}${unit}` : `${q.lower}${unit} ${ge ? "이상" : "초과"}`;
  }
  if (hasUpper) {
    const le = q.upper_op !== "<";
    return symbol ? `${le ? "≤" : "<"} ${q.upper}${unit}` : `${q.upper}${unit} ${le ? "이하" : "미만"}`;
  }
  return q.raw ?? q.status ?? "";
}

function formatClass(side: Side, expected: boolean, status?: Finding["expected"]["status"], low?: string | null, high?: string | null) {
  if (expected && status === "근거부족") return "— (근거부족)";
  if (expected && status === "경계" && low && high && low !== high) return `구분${low}~${high}`;
  if (!side.present) return expected ? "분류안됨" : "미기재";
  if (!side.category) return "—";
  return `구분${side.category}${side.route_form ? ` (${side.route_form})` : ""}`;
}

function formatRegulation(side: Side, expected: boolean) {
  if (!side.present) return "미기재";
  const threshold = formatQ(side.threshold, expected);
  return `${side.applicable ?? "미기재"}${threshold ? ` (${threshold})` : ""}`;
}

function formatDg(side: Side, expected: boolean) {
  if (!side.present) return "미기재";
  const dg = side.dg;
  const empty = !dg || (!dg.class && !dg.item);
  if (empty) return expected ? "비해당" : "해당없음";
  return [dg.class, dg.item].filter(Boolean).join(" ") + (dg.grade ? ` ${dg.grade}` : "");
}

/** 한쪽(MSDS 기재 또는 검증 결과)의 값을 화면 문장으로. kind 마다 쓰는 칸이 다르다 */
export function formatSide(finding: Finding, which: "msds" | "expected"): string {
  const side = finding[which];
  const expected = which === "expected";
  switch (finding.kind) {
    case "class":
      return formatClass(side, expected, finding.expected.status, finding.expected.low, finding.expected.high);
    case "label":
      if (!side.present) return expected ? "기재 대상 아님" : "미기재";
      return `${side.code ?? "—"} 기재`;
    case "regulation":
      return formatRegulation(side, expected);
    case "dangerous_goods":
      return formatDg(side, expected);
    case "product_type":
      return side.product_type ?? "—";
  }
}
