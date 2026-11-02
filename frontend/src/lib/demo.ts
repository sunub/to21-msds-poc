/*
 * 데모 문서("demo") 스위치. 백엔드 없이 검수·저장 화면을 보려고 고정 데이터를 돌려주는 분기를 모두 여기서 켜고 끈다.
 * 개발 중에는 켜져 있고, production 빌드에서는 NEXT_PUBLIC_ENABLE_DEMO=1 로 빌드했을 때만 켜진다.
 *
 * 번들러(Turbopack)는 다른 모듈에서 가져온 상수까지는 접지 못한다. 그래서 demo-*.ts 를 부르는 import() 는
 * 스위치와 같은 이 파일 안(loadDemo)에만 두고, 다른 파일은 loadDemo 를 거쳐 부른다.
 * 스위치가 꺼진 빌드에서는 loadDemo 의 import() 가 통째로 빠져 demo 모듈이 번들에 들어가지 않는다.
 */
export const DEMO_ENABLED = process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_ENABLE_DEMO === "1";

export const DEMO_DOC_ID = "demo";

/** 데모 문서의 검증 번호 (demo-findings.ts 의 응답에 들어가는 값과 같다) */
export const DEMO_VALIDATION_ID = "val_demo";

/** 이 문서를 데모 데이터로 보여 주는가 (스위치가 켜져 있고 문서 번호가 "demo" 일 때만) */
export const isDemoDoc = (doc: string) => DEMO_ENABLED && doc === DEMO_DOC_ID;

/**
 * 판정 요청에 쓰는 검증 번호. 데모 문서는 데모 번호, 그 외에는 "latest".
 * 서버 확정 후 교체: 문서 응답에서 검증 번호를 받아 쓴다.
 */
export const validationIdFor = (doc: string) => (DEMO_ENABLED && doc === DEMO_DOC_ID ? DEMO_VALIDATION_ID : "latest");

const off = (): Promise<never> => Promise.reject(new Error("데모가 꺼져 있습니다."));

/** demo 모듈 로더. 스위치가 꺼진 빌드에서는 import() 가 빠진다 */
export const loadDemo = {
  detail: () => (DEMO_ENABLED ? import("@/api/demo") : off()),
  pages: () => (DEMO_ENABLED ? import("@/api/demo-pages") : off()),
  findings: () => (DEMO_ENABLED ? import("@/api/demo-findings") : off()),
  components: () => (DEMO_ENABLED ? import("@/api/demo-components") : off()),
  save: () => (DEMO_ENABLED ? import("@/api/demo-save") : off()),
};
