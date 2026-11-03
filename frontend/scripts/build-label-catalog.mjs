// public/msds-labels/*/codes.json(고시 별표 원본 기록)을 하나의 형식으로 모아 public/msds-labels/catalog.json 을 만든다.
// 원본 JSON 은 고치지 않는다. 표에 없는 칸이나 파일이 있으면 정보가 빠지지 않도록 멈춘다.
// 실행: pnpm labels:catalog  (--check 는 쓰지 않고 파일과 같은지만 본다)
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(import.meta.dirname, "..", "public", "msds-labels");
const CATALOG = join(ROOT, "catalog.json");
const URL_ROOT = "/msds-labels";
/** 코드별 대표 이미지 폴더. 분류별 기록이 아니라서 카탈로그에 넣지 않는다 (src/lib/ghs.ts) */
const NOT_CATEGORIES = new Set(["ghs"]);
/** 대체 그림문자가 깨진 이전 판. 파일은 남기되 조회에서는 뺀다 */
const SUPERSEDED = { "1.1.2_flammable_gases_superseded": "1.1.2_flammable_gases" };

const TOP_KEYS = new Set(["source", "items", "note", "route_labels"]);
const ITEM_KEYS = new Set([
  "class", "signal", "ghs", "ghs_note", "rtdg", "rtdg_note", "rtdg_alt", "rtdg_alt_note", "rtdg_required", "rtdg_required_note",
  "hazard", "prevention", "response", "response_note", "storage", "disposal", "routes",
]);
const RTDG_FILE = /^RTDG_(\d(?:\.\d)?|environmental)(?:_.*)?\.png$/;
const RTDG_VARIANT = /_(black|white)\.png$/;
const GHS_FILE = /^(GHS0[1-9])(?:_.*)?\.png$/;
const GROUPS = { "1.1": "physical", "1.2": "health", "1.3": "environmental" };

const asList = (value) => (value == null ? [] : Array.isArray(value) ? value : [value]);

function checkKeys(where, object, allowed) {
  for (const key of Object.keys(object)) if (!allowed.has(key)) throw new Error(`${where}: 표에 없는 칸 ${key}`);
}

function matchFile(where, file, pattern) {
  const match = pattern.exec(file);
  if (!match) throw new Error(`${where}: 이름을 해석할 수 없는 파일 ${file}`);
  return match;
}

function rtdgPick(where, images, note) {
  if (images.length <= 1) return null;
  if (/함께/.test(note ?? "")) return "all";
  if (/택1|둘 중 하나/.test(note ?? "")) return "one_of";
  throw new Error(`${where}: 그림문자 ${images.length}개를 어떻게 쓰는지 비고에 없음`);
}

function statements(item) {
  return {
    hazard: item.hazard ?? [],
    prevention: item.prevention ?? [],
    response: item.response ?? [],
    storage: item.storage ?? [],
    disposal: item.disposal ?? [],
    responseNote: item.response_note ?? null,
  };
}

function buildCategory(id) {
  const raw = JSON.parse(readFileSync(join(ROOT, id, "codes.json"), "utf8"));
  checkKeys(id, raw, TOP_KEYS);
  const source = /제6조 관련\)\s*([\d.]+)\s+(.+)$/.exec(raw.source);
  if (!source) throw new Error(`${id}: 출처를 해석할 수 없음 ${raw.source}`);
  const [, article, name] = source;

  const used = new Set();
  const src = (file) => {
    if (!existsSync(join(ROOT, id, file))) throw new Error(`${id}: 없는 파일 ${file}`);
    used.add(file);
    return `${URL_ROOT}/${id}/${file}`;
  };
  const ghsImage = (file) => ({ file, src: src(file), code: matchFile(id, file, GHS_FILE)[1] });
  const rtdgImage = (file) => {
    const [, division] = matchFile(id, file, RTDG_FILE);
    return { file, src: src(file), division, variant: RTDG_VARIANT.exec(file)?.[1] ?? null };
  };

  const entries = raw.items.flatMap((item) => {
    const where = `${id} ${item.class}`;
    checkKeys(where, item, ITEM_KEYS);
    if (item.rtdg_alt != null) throw new Error(`${where}: rtdg_alt 값은 다루지 않음`);
    const images = asList(item.rtdg).map(rtdgImage);
    const base = {
      class: item.class,
      signal: item.signal ?? null,
      ghs: { images: asList(item.ghs).map(ghsImage), note: item.ghs_note ?? null },
      rtdg: {
        images,
        /** images 를 쓰는 방법. one_of: 하나만, all: 모두, null: 1개 이하 */
        pick: rtdgPick(where, images, item.rtdg_note),
        required: asList(item.rtdg_required).map(rtdgImage),
        note: item.rtdg_note ?? null,
        requiredNote: item.rtdg_required_note ?? null,
        altNote: item.rtdg_alt_note ?? null,
      },
    };
    if (!item.routes) return [{ ...base, route: null, routeLabel: null, statements: statements(item) }];
    return Object.entries(item.routes).map(([route, values]) => ({
      ...base,
      route,
      routeLabel: raw.route_labels?.[route] ?? route,
      statements: statements(values),
    }));
  });

  const orphan = readdirSync(join(ROOT, id)).filter((file) => file !== "codes.json" && !used.has(file));
  if (orphan.length) throw new Error(`${id}: 기록에 없는 파일 ${orphan.join(", ")}`);

  const group = GROUPS[article.split(".").slice(0, 2).join(".")];
  if (!group) throw new Error(`${id}: 알 수 없는 분류 번호 ${article}`);
  return {
    id,
    article,
    name,
    group,
    source: raw.source,
    note: raw.note ?? null,
    supersededBy: SUPERSEDED[id] ?? null,
    record: `${URL_ROOT}/${id}/codes.json`,
    entries,
  };
}

const articleOrder = (a, b) => a.article.localeCompare(b.article, "en", { numeric: true }) || a.id.localeCompare(b.id);

const categories = readdirSync(ROOT, { withFileTypes: true })
  .filter((item) => item.isDirectory() && !NOT_CATEGORIES.has(item.name))
  .map((item) => buildCategory(item.name))
  .sort(articleOrder);
const output = `${JSON.stringify({ categories }, null, 2)}\n`;

if (process.argv.includes("--check")) {
  if (!existsSync(CATALOG) || readFileSync(CATALOG, "utf8") !== output) {
    console.error("catalog.json 이 원본 기록과 다릅니다. pnpm labels:catalog 로 다시 만드세요.");
    process.exit(1);
  }
} else {
  writeFileSync(CATALOG, output);
  console.log(`분류 ${categories.length}개, 항목 ${categories.reduce((n, c) => n + c.entries.length, 0)}개: ${CATALOG}`);
}
