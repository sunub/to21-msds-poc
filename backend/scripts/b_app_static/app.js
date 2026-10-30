"use strict";
// B 작업 화면 (역할 B, 개발 전용, ADR-025). 이 화면의 서버(/api/...)만 부른다. 외부 주소는 부르지 않는다.
// 글은 모두 글자 노드로 넣는다(결과 값에 어떤 글자가 들어 있어도 화면 코드가 되지 않게).

const S = {list: [], criteria: null, gaps: [], limit: 300, name: null, run: null, open: null, pick: loadPick(),
  diff: {a: null, b: null, key: null, data: null, error: null, why: new Set(), vals: new Set(), open: new Set(), prompts: {}},
  doc: {run: null, doc: null, key: null, data: null, error: null, page: null, pick: null,
    selLines: new Set(), selPaths: new Set(), open: new Set()},
  jobs: {opts: null, error: null, list: [], running: [], pollError: null, timer: null, watch: null, result: null, tried: null,
    log: null, msg: {},
    t: {model: null, doc: null, pages: null, all: false, secs: new Set([11]), edit: false, text: "", textFor: null, base: "", dry: false},
    r: {model: null, pages: null, docs: null, repeat: 2, name: "", edited: false},
    c: {picked: [], labels: {}, title: ""}},
  srv: {data: null, error: null, at: null, timer: null, started: false, busy: null, result: null}};
const LEVELS = ["필수", "중요", "일반"];
const COLORS = ["#0969da", "#8250df", "#bf3989", "#1a7f37", "#9a6700", "#57606a"];
const ROW_LABEL = {
  components: "성분 (3항)", exposure_limits: "노출기준 (8항)", physchem: "물리·화학 성질 (9항)",
  toxicity: "독성 (11항)", cmr: "발암성 등 CMR (11항)", ecotox: "생태 독성 (12항)",
  regulations: "규제 (15항)", intl_class: "국제 분류 (15항)", extras: "남는 값 extras (자리가 없는 값)",
};
// SVG 이름공간은 HTML 파서에게서 얻는다(주소 글자를 이 파일에 두지 않는다)
const SVGNS = (() => { const d = document.createElement("div"); d.innerHTML = "<svg></svg>"; return d.firstChild.namespaceURI; })();

// ── 작은 도구 ─────────────────────────────────────────

function fill(n, attrs, kids) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) {
    if (k !== null && k !== undefined && k !== false) n.append(k instanceof Node ? k : String(k));
  }
  return n;
}
const h = (tag, attrs, ...kids) => fill(document.createElement(tag), attrs, kids);
const s = (tag, attrs, ...kids) => fill(document.createElementNS(SVGNS, tag), attrs, kids);

const num = v => typeof v === "number" && isFinite(v);
const fmt1 = v => num(v) ? v.toFixed(1) : "—";
const pct = v => num(v) ? (v * 100).toFixed(1) + "%" : "—";
const when = t => t ? String(t).replace("T", " ").slice(0, 16) : "—";
const lastPart = p => p ? String(p).split("/").filter(Boolean).pop() : "—";

async function api(path) {
  const r = await fetch(path, {cache: "no-store"});
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `${r.status} ${path}`);
  return body;
}

function status(text, bad) {
  const el = document.getElementById("status");
  el.textContent = text || "";
  el.classList.toggle("bad", !!bad);
}
const fail = e => status("불러오지 못했습니다: " + e.message, true);

function card(id, title, hint, ...kids) {
  document.getElementById(id).replaceChildren(h("h2", null, title), hint ? h("p", {class: "hint"}, hint) : "", ...kids.flat().filter(k => k));
}

function loadPick() {
  try { return JSON.parse(localStorage.getItem("b_app_pick")) || []; } catch (e) { return []; }
}

// 마우스를 올리면 data-tip 글을 띄운다. SVG 도형에도 똑같이 쓴다
function setupTip() {
  const tip = document.getElementById("tip");
  document.addEventListener("mouseover", e => {
    const t = e.target.closest ? e.target.closest("[data-tip]") : null;
    tip.hidden = !t;
    if (t) tip.textContent = t.getAttribute("data-tip");
  });
  document.addEventListener("mousemove", e => {
    if (tip.hidden) return;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    const below = e.clientY + 18 + tip.offsetHeight < window.innerHeight;
    tip.style.left = x + "px";
    tip.style.top = (below ? e.clientY + 18 : e.clientY - tip.offsetHeight - 10) + "px";
  });
}

function setupTabs() {
  const buttons = document.querySelectorAll(".tabs button");
  const show = id => {
    buttons.forEach(b => b.classList.toggle("on", b.dataset.tab === id));
    document.querySelectorAll("section.tab").forEach(t => t.classList.toggle("on", t.id === "tab-" + id));
    history.replaceState(null, "", "#" + id);
    if (id === "servers" && S.srv.started) pollServers().catch(fail);   // 서버 탭을 열면 바로 다시 본다
  };
  buttons.forEach(b => b.addEventListener("click", () => show(b.dataset.tab)));
  const first = location.hash.slice(1);
  show(document.getElementById("tab-" + first) ? first : "score");
}

// ── 불러오기 ──────────────────────────────────────────

const runsShown = () => S.list.filter(r => r.kind !== "models" && !r.error);

async function loadAll() {
  status("불러오는 중… (처음에는 실행마다 채점하느라 수십 초 걸릴 수 있습니다)");
  const data = await api("/api/runs");
  S.gaps = await api("/api/silver_gaps");
  S.list = data.runs;
  S.criteria = data.criteria;
  S.limit = data.doc_time_limit;
  const keep = runsShown().some(r => r.name === S.name);
  await loadRun(keep ? S.name : data.current);
  await initDiff();
  await initDoc();
  if (S.jobs.opts) renderJobs();                     // 새 실행 목록으로 기준 실행·비교표 고르기를 다시 그린다
  const broken = S.list.filter(r => r.error).length;
  status(broken ? `읽지 못한 실행 ${broken}개 (쓰는 중일 수 있습니다)` : "");
}

async function loadRun(name) {
  S.name = name;
  S.open = null;
  S.run = name ? await api("/api/run/" + name.split("/").map(encodeURIComponent).join("/")) : null;
  renderScore();
}

function renderScore() {
  renderNow(S.run);
  renderRule();
  renderItems(S.run);
  renderHistory();
  renderDocs(S.run);
  renderGrid(S.run);
  renderRows(S.run);
}

function progressLine(r) {
  const p = (r && r.progress) || {};
  if (!p.total) return null;
  return h("p", {class: p.running ? "running" : "hint"}, `${p.total}건 중 ${p.done}건 끝${p.running ? " — 아직 도는 중입니다" : ""}`);
}

// ── 2. 지금 점수 ───────────────────────────────────────

function goalBar(label, value, goal, max, text) {
  const W = 300, x = v => Math.max(0, Math.min(1, v / max)) * W;
  return h("div", {class: "goal"}, h("span", {class: "glabel"}, label),
    s("svg", {viewBox: `0 0 ${W} 16`, width: W, height: 16, class: "bar"},
      s("rect", {x: 0, y: 2, width: W, height: 12, class: "bg"}),
      s("rect", {x: 0, y: 2, width: x(value), height: 12, class: value >= goal ? "ok" : "now"}),
      s("line", {x1: x(goal), x2: x(goal), y1: 0, y2: 16, class: "target"})),
    h("span", {class: "gtext"}, text));
}

function runLabel(r) {
  const tag = r.kind === "manual" ? "[수동] " : "";
  return `${tag}${r.name} — ${num(r.weighted) ? r.weighted.toFixed(1) + "점" : "점수 없음"}`;
}

function renderNow(r) {
  const sel = h("select", {onchange: e => loadRun(e.target.value).catch(fail)},
    runsShown().slice().reverse().map(x => h("option", {value: x.name, selected: x.name === S.name}, runLabel(x))));
  const top = h("div", {class: "pickrow"}, h("label", null, "실행 ", sel),
    h("button", {type: "button", onclick: () => loadAll().catch(fail)}, "다시 읽기"));
  if (!r) return card("now-card", "지금 점수", null, top, connLine(true), h("p", null, "점수를 낸 실행이 아직 없습니다."));
  const pass = S.criteria.pass_score;
  const mustTotal = r.must_total || S.criteria.items.filter(i => i.level === "필수").length;
  const must = r.must_passed || 0;
  const na = r.weighted_na_excluded, diff = num(na) && num(r.weighted) ? na - r.weighted : null;
  card("now-card", "지금 점수",
    "가장 최근 개발용 10건 본 실행(이름에 dev10)을 먼저 보여 줍니다. 위 상자에서 다른 실행을 고를 수 있습니다.",
    top,
    connLine(true),
    h("div", {class: "bigrow"},
      h("div", {class: "big", "data-tip": "가중 종합 점수(weighted). 항목 점수에 무게를 곱해 평균 낸 값"}, fmt1(r.weighted),
        h("small", null, "점")),
      h("div", {class: "sub"}, `필수 통과 ${r.must_passed ?? "—"}/${mustTotal}`,
        h("br"), r.passed ? h("b", {class: "okt"}, "합격 기준 넘음") : h("b", {class: "badt"}, "아직 합격 기준 아래"))),
    goalBar("점수", r.weighted || 0, pass, 100, `${fmt1(r.weighted)} / 목표 ${pass}`),
    goalBar("필수 통과", must, mustTotal, mustTotal, `${must} / ${mustTotal}`),
    h("p", {class: "na", "data-tip": "정답과 결과 양쪽에서 자료없음·해당없음·비해당·미기재 행을 빼고 같은 채점기로 다시 잰 점수.\n차이가 크면 값 없는 행 표기 때문에 깎인 점수가 많다는 뜻입니다."},
      `값 없는 행을 뺀 점수: ${fmt1(na)}점`, diff === null ? "" : ` (차이 ${diff >= 0 ? "+" : ""}${diff.toFixed(1)})`),
    progressLine(r),
    h("dl", {class: "meta"},
      h("dt", null, "모델"), h("dd", null, r.model || "—", r.model_tag ? h("small", null, ` (태그 ${r.model_tag})`) : null),
      h("dt", null, "안내문 버전"), h("dd", null, r.prompt_version || "—"),
      h("dt", null, "입력 판"), h("dd", {"data-tip": r.pages_dir || ""}, lastPart(r.pages_dir)),
      h("dt", null, "실행 이름"), h("dd", {class: "mono"}, r.name),
      h("dt", null, "시작 시각"), h("dd", null, when(r.started_at)),
      h("dt", null, "채점한 문서"), h("dd", null, `${(r.docs || []).length}건`,
        r.excluded && r.excluded.length ? h("small", null, ` (평가용·목록 밖 ${r.excluded.length}건은 뺌)`) : null,
        r.no_gold && r.no_gold.length ? h("small", null, ` (정답 없는 ${r.no_gold.length}건은 뺌)`) : null)));
}

// ── 3. 합격 기준 ───────────────────────────────────────

function renderRule() {
  const c = S.criteria, n = lv => c.items.filter(i => i.level === lv).length;
  card("rule-card", "합격 기준", null,
    h("p", {class: "rule"}, c.rule),
    h("ul", null,
      h("li", null, `필수 항목 ${n("필수")}개가 하나도 빠짐없이 각자의 목표를 넘어야 합니다. 목표는 아래 막대의 세로선입니다.`),
      h("li", null, `그리고 가중 종합 점수(weighted)가 ${c.pass_score}점 이상이어야 합니다.`),
      h("li", null, `가중 종합은 항목 점수에 무게(가중치)를 곱해 평균 낸 값입니다. 무게는 필수 ×${c.weights["필수"]}, 중요 ×${c.weights["중요"]}, 일반 ×${c.weights["일반"]}입니다.`),
      h("li", null, `항목 수는 필수 ${n("필수")}개, 중요 ${n("중요")}개, 일반 ${n("일반")}개입니다.`)),
    h("p", {class: "warn"},
      "주의: 지금 정답 자리에는 실버(Claude가 만든 정답 초안)가 들어 있습니다. 실버에도 틀린 곳이 있어서 이 점수는 실행끼리 순위를 비교하는 데만 씁니다. 합격 판정에는 쓰지 않습니다."));
}

// ── 4. 항목 23개 신호등 ────────────────────────────────

function scoreBar(score, target) {
  const W = 200, x = v => Math.max(0, Math.min(1, v)) * W;
  return s("svg", {viewBox: `0 0 ${W} 14`, width: W, height: 14, class: "bar"},
    s("rect", {x: 0, y: 2, width: W, height: 10, class: "bg"}),
    num(score) ? s("rect", {x: 0, y: 2, width: x(score), height: 10, class: score >= target ? "ok" : "no"}) : null,
    s("line", {x1: x(target), x2: x(target), y1: 0, y2: 14, class: "target"}));
}

function detailList(i, r) {
  const rows = ((r && r.details) || []).filter(d => d.item === i.name);
  if (!rows.length) {
    return h("p", {class: "hint detail"}, i.level === "필수" ? "틀린 값 기록이 없습니다."
      : "틀린 값 기록이 없습니다. 채점기는 필수 항목만 틀린 값을 하나하나 남깁니다.");
  }
  const shown = rows.slice(0, 300);
  return h("div", {class: "detail"},
    rows.length > shown.length ? h("p", {class: "hint"}, `${rows.length}개 중 앞의 ${shown.length}개만 보입니다.`) : null,
    h("table", {class: "list"},
      h("thead", null, h("tr", null, h("th", null, "문서"), h("th", null, "종류"), h("th", null, "내용"))),
      h("tbody", null, shown.map(d => h("tr", null,
        h("td", {class: "mono"}, d.doc_id), h("td", {class: "k-" + d.kind}, d.kind), h("td", {class: "mono"}, d.content))))));
}

function itemRow(i, naScore, r) {
  const help = (S.criteria.items.find(c => c.name === i.name) || {}).help || "";
  const gaps = S.gaps.filter(g => i.name.startsWith(g.item));
  const scored = num(i.score), ok = scored && i.score >= i.target;
  const kinds = ["빠뜨림", "지어냄", "틀림"].map(k => h("span", {class: "k-" + k}, `${k} ${i[k] ?? 0}`));
  const row = h("div", {class: "item " + (!scored ? "none" : ok ? "pass" : "fail"),
    onclick: () => { S.open = S.open === i.name ? null : i.name; renderItems(S.run); }},
    h("span", {class: "iname", "data-tip": `${i.name}\n${help}\n잰 방법: ${i.metric} · 목표 ${pct(i.target)}`}, i.name),
    gaps.length ? h("span", {class: "gapdot", "data-tip": gaps.map(g => `실버 빈 곳: ${g.note}\n(${g.source}, ${g.since})`).join("\n\n")}, "●")
      : h("span"),
    scoreBar(i.score, i.target),
    h("span", {class: "ival"}, pct(i.score)),
    h("span", {class: "badge"}, !scored ? "점수 없음" : ok ? "통과" : "미달"),
    h("span", {class: "kinds"}, kinds),
    num(naScore) && scored && Math.abs(naScore - i.score) > 0.0005
      ? h("span", {class: "naitem", "data-tip": "값 없는 행을 뺀 점수"}, `값 없는 행 뺌 ${pct(naScore)}`) : h("span"));
  return h("div", {class: "itembox" + (S.open === i.name ? " open" : "")}, row,
    S.open === i.name ? detailList(i, r) : null);
}

function renderItems(r) {
  const items = r && r.items && r.items.length ? r.items : S.criteria.items;
  const na = Object.fromEntries(((r && r.items_na_excluded) || []).map(i => [i.name, i.score]));
  card("items-card", "항목 23개 신호등",
    "항목마다 점수 막대와 목표선(세로선)을 보여 줍니다. 초록은 통과, 빨강은 미달입니다. 이름에 마우스를 올리면 무엇을 재는지 나오고, 줄을 누르면 틀린 값 목록이 펴집니다.",
    h("p", {class: "legend"},
      h("span", {class: "k-빠뜨림"}, "빠뜨림"), " = 정답에는 있는데 결과에 없음 · ",
      h("span", {class: "k-지어냄"}, "지어냄"), " = 결과에는 있는데 정답에 없음 · ",
      h("span", {class: "k-틀림"}, "틀림"), " = 둘 다 있지만 값이 다름 · ",
      h("span", {class: "gapdot"}, "●"), " = 실버 빈 곳(정답 초안이 틀렸을 수 있음)"),
    LEVELS.map(lv => h("div", {class: "group"},
      h("h3", null, `${lv} 항목 (무게 ×${S.criteria.weights[lv]})`),
      items.filter(i => i.level === lv).map(i => itemRow(i, na[i.name], r)))));
}

// ── 5. 실행 역사 ───────────────────────────────────────

function dayOf(r) {
  if (r.started_at) return String(r.started_at).slice(5, 10);
  const m = r.name.match(/(\d{4})(\d{2})(\d{2})/);
  return m ? `${m[2]}-${m[3]}` : "";
}

function savePick(list) {
  S.pick = list;
  localStorage.setItem("b_app_pick", JSON.stringify(list));   // 탭 ②가 읽는다
  renderHistory();
  if (list.length === 2) {
    [S.diff.a, S.diff.b] = list;
    loadDiff();
  }
}

function renderHistory() {
  const runs = runsShown().filter(r => r.kind === "run" && num(r.weighted));
  const hint = "점 하나가 본 실행 하나입니다. 왼쪽이 먼저 돌린 실행입니다. 수동 시험(runs/manual)은 문서 수가 달라 뺐습니다. 점을 두 개 차례로 누르면 탭 ②(두 실행 비교)에 넘길 두 실행으로 고릅니다.";
  if (!runs.length) return card("history-card", "실행 역사", hint, h("p", null, "점수를 낸 본 실행이 없습니다."));
  const W = 900, H = 240, L = 44, R = 16, T = 14, B = 34, pass = S.criteria.pass_score;
  const lo = Math.max(0, Math.floor((Math.min(...runs.map(r => r.weighted)) - 5) / 10) * 10), hi = 100;
  const x = i => L + (runs.length === 1 ? (W - L - R) / 2 : i * (W - L - R) / (runs.length - 1));
  const y = v => T + (hi - v) / (hi - lo) * (H - T - B);
  const tags = [...new Set(runs.map(r => r.model_tag || "?"))];
  const color = t => COLORS[tags.indexOf(t || "?") % COLORS.length];
  const g = s("svg", {viewBox: `0 0 ${W} ${H}`, class: "chart"});
  for (let v = lo; v <= hi; v += 10) {
    g.append(s("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), class: "grid"}),
      s("text", {x: L - 6, y: y(v) + 4, class: "ax", "text-anchor": "end"}, v));
  }
  g.append(s("line", {x1: L, x2: W - R, y1: y(pass), y2: y(pass), class: "goalline"}),
    s("text", {x: W - R, y: y(pass) - 4, class: "ax", "text-anchor": "end"}, `합격선 ${pass}점`));
  let prev = "", lastX = -Infinity;
  runs.forEach((r, i) => {
    const d = dayOf(r);
    if (d !== prev && x(i) - lastX > 44) {          // 날짜가 바뀐 첫 실행 아래에만. 글자가 겹치면 건너뛴다
      g.append(s("text", {x: x(i), y: H - 12, class: "ax", "text-anchor": "middle"}, d));
      lastX = x(i);
    }
    prev = d;
  });
  runs.forEach((r, i) => {
    const picked = S.pick.indexOf(r.name);
    const tip = `${r.name}\n모델: ${r.model_tag || "—"}\n안내문 버전: ${r.prompt_version || "—"}\n입력 판: ${lastPart(r.pages_dir)}\n가중 종합: ${fmt1(r.weighted)}점 · 필수 ${r.must_passed}/${r.must_total}`;
    const toggle = () => savePick(picked >= 0 ? S.pick.filter(n => n !== r.name) : [...S.pick, r.name].slice(-2));
    g.append(s("circle", {cx: x(i), cy: y(r.weighted), r: r.name === S.name ? 8 : 5.5, fill: color(r.model_tag),
      class: "pt" + (picked >= 0 ? " picked" : ""), "data-tip": tip, onclick: toggle}));
    if (picked >= 0) g.append(s("text", {x: x(i), y: y(r.weighted) - 12, class: "picknum", "text-anchor": "middle"}, picked ? "②" : "①"));
  });
  const legend = h("p", {class: "legend"}, tags.map(t => h("span", {class: "sw"}, h("i", {style: `background:${color(t)}`}), t)),
    h("span", {class: "sw"}, "큰 점 = 지금 점수 카드의 실행"));
  const picks = S.pick.length
    ? h("p", {class: "picks"}, "고른 실행: ", S.pick.map((n, k) => h("span", {class: "mono"}, `${k ? "②" : "①"} ${n} `)),
      h("button", {type: "button", onclick: () => savePick([])}, "고른 것 지우기"),
      S.pick.length === 2 ? " → 탭 ②에서 ①을 A(전), ②를 B(후)로 비교합니다." : " → 하나 더 고르세요.")
    : h("p", {class: "picks"}, "아직 고른 실행이 없습니다.");
  card("history-card", "실행 역사", hint, h("div", {class: "scroll"}, g), legend, picks);
}

// ── 6. 문서별 ──────────────────────────────────────────

function renderDocs(r) {
  const docs = Object.keys((r && r.per_doc) || {});
  const hint = `문서마다 가중 종합 점수와 걸린 시간(초)입니다. 목표는 PDF 하나를 ${S.limit}초(5분) 안에 끝내는 것입니다. 빨간 시간 막대는 ${S.limit}초를 넘은 문서입니다.`;
  if (!docs.length) return card("docs-card", "문서별 점수와 시간", hint, progressLine(r), h("p", null, "채점한 문서가 없습니다."));
  const W = 900, rowH = 26, top = 26, L = 100, sw = 330, tx = 520, tw = 320;
  const maxSec = Math.max(S.limit * 1.1, ...docs.map(d => r.per_doc[d].seconds || 0));
  const xs = v => tx + v / maxSec * tw;
  const g = s("svg", {viewBox: `0 0 ${W} ${top + docs.length * rowH + 8}`, class: "chart"},
    s("text", {x: L, y: 14, class: "ax"}, "가중 종합 (0~100점)"),
    s("text", {x: tx, y: 14, class: "ax"}, "걸린 시간 (초)"));
  docs.forEach((d, i) => {
    const p = r.per_doc[d], yy = top + i * rowH;
    const failed = (p.failed_must || []).length ? "\n필수 미달: " + p.failed_must.join(", ") : "\n필수 항목 모두 통과";
    g.append(s("text", {x: 4, y: yy + 13, class: "lab"}, d),
      s("rect", {x: L, y: yy + 2, width: sw, height: 14, class: "bg"}),
      s("rect", {x: L, y: yy + 2, width: (p.weighted || 0) / 100 * sw, height: 14, class: "now",
        "data-tip": `${d}: ${fmt1(p.weighted)}점${failed}`}),
      s("text", {x: L + sw + 6, y: yy + 13, class: "lab"}, fmt1(p.weighted)));
    if (num(p.seconds)) {
      g.append(s("rect", {x: tx, y: yy + 2, width: xs(p.seconds) - tx, height: 14,
        class: p.seconds > S.limit ? "no" : "time", "data-tip": `${d}: ${p.seconds.toFixed(0)}초`}),
        s("text", {x: xs(p.seconds) + 6, y: yy + 13, class: "lab"}, `${p.seconds.toFixed(0)}초`));
    } else {
      g.append(s("text", {x: tx, y: yy + 13, class: "lab"}, "시간 기록 없음"));
    }
  });
  g.append(s("line", {x1: xs(S.limit), x2: xs(S.limit), y1: top - 6, y2: top + docs.length * rowH, class: "goalline"}),
    s("text", {x: xs(S.limit) + 4, y: 14, class: "ax"}, `${S.limit}초`));
  card("docs-card", "문서별 점수와 시간", hint, progressLine(r), h("div", {class: "scroll"}, g));
}

// ── 7. 호출 격자 ───────────────────────────────────────

function gridCell(doc, mi, no, c) {
  const where = `${doc}${mi ? ` (${mi + 1}번째 MSDS)` : ""} ${no}항`;
  if (!c) return h("td", {class: "c-none", "data-tip": `${where}: 기록 없음`});
  const kind = c.limit_kind;
  const cls = !c.ok ? "c-fail" : kind ? "c-limit" : c.reextracted ? "c-re" : "c-ok";
  const text = kind || (!c.ok ? "✕" : c.reextracted ? "재" : "");
  const tip = [where, c.ok ? "성공" : "실패", `시도 ${c.attempts ?? "?"}번 · ${fmt1(c.seconds)}초`,
    c.mode ? `방식 ${c.mode}` : null, c.reextracted ? "검사에 걸려 한 번 더 뽑음(재추출)" : null,
    kind ? `출력 한도에 걸린 요청이 있음: ${kind}` : null].filter(Boolean).join("\n");
  return h("td", {class: cls, "data-tip": tip}, text);
}

function renderGrid(r) {
  const rows = [];
  for (const [doc, cells] of Object.entries((r && r.grid) || {})) {
    const byM = {};
    for (const [k, v] of Object.entries(cells)) {
      const m = k.match(/^m(\d+):(\d+)$/);
      const mi = m ? +m[1] : 0, no = m ? +m[2] : +k;
      (byM[mi] = byM[mi] || {})[no] = v;
    }
    Object.keys(byM).map(Number).sort((a, b) => a - b).forEach(mi => rows.push([doc, mi, byM[mi]]));
  }
  const hint = "줄은 문서, 칸은 법정 항목 1~16항입니다. 칸 하나가 모델 호출 하나입니다. 마우스를 올리면 시간과 시도 수가 나옵니다.";
  if (!rows.length) return card("grid-card", "호출 격자", hint, h("p", null, "호출 기록(checks)이 없습니다."));
  const nos = Array.from({length: 16}, (_, i) => i + 1);
  const legend = h("p", {class: "legend"},
    h("span", {class: "sw c-ok"}, "성공"), h("span", {class: "sw c-re"}, "재 = 재추출 뒤 성공"),
    h("span", {class: "sw c-limit"}, "출력 한도에 걸림 (공백폭주·반복·긴출력)"), h("span", {class: "sw c-fail"}, "✕ = 실패"));
  const table = h("table", {class: "grid"},
    h("thead", null, h("tr", null, h("th", null, "문서"), nos.map(n => h("th", null, `${n}항`)))),
    h("tbody", null, rows.map(([doc, mi, cells]) => h("tr", null,
      h("th", {class: "mono"}, mi ? `${doc} (${mi + 1})` : doc), nos.map(n => gridCell(doc, mi, n, cells[n]))))));
  card("grid-card", "호출 격자", hint, legend, h("div", {class: "scroll"}, table));
}

// ── 8. 표 행 수 ────────────────────────────────────────

function renderRows(r) {
  const rows = (r && r.rows) || {};
  const keys = Object.keys(ROW_LABEL).filter(k => rows[k]);
  const hint = "표마다 결과 행 수(파랑)와 정답 행 수(회색)입니다. 결과가 짧으면 행을 빠뜨린 것이고, extras가 길면 자리가 없는 칸에 값을 많이 보낸 것입니다.";
  if (!keys.length) return card("rows-card", "표 행 수", hint, h("p", null, "채점한 문서가 없습니다."));
  const W = 900, rowH = 34, L = 230, bw = 520;
  const max = Math.max(1, ...keys.map(k => Math.max(rows[k].pred, rows[k].gold)));
  const g = s("svg", {viewBox: `0 0 ${W} ${keys.length * rowH + 6}`, class: "chart"});
  keys.forEach((k, i) => {
    const {pred, gold} = rows[k], yy = i * rowH + 4;
    const ratio = gold ? ` (${Math.round(pred / gold * 100)}%)` : "";
    g.append(s("text", {x: 4, y: yy + 17, class: "lab"}, ROW_LABEL[k]),
      s("rect", {x: L, y: yy, width: pred / max * bw, height: 12, class: "now", "data-tip": `${ROW_LABEL[k]} 결과 ${pred}행`}),
      s("rect", {x: L, y: yy + 14, width: gold / max * bw, height: 12, class: "goldbar", "data-tip": `${ROW_LABEL[k]} 정답 ${gold}행`}),
      s("text", {x: L + bw + 10, y: yy + 17, class: "lab"}, `결과 ${pred} / 정답 ${gold}${ratio}`));
  });
  card("rows-card", "표 행 수", hint, h("div", {class: "scroll"}, g));
}

// ── 탭 ② 두 실행 비교 ─────────────────────────────────

const query = obj => Object.entries(obj).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
const signed = v => num(v) ? (v > 0 ? "+" : v < 0 ? "−" : "±") + Math.abs(v).toFixed(1) : "—";
const trend = v => num(v) && v > 0 ? "up" : num(v) && v < 0 ? "down" : null;

// 처음 열 때: 탭 ①에서 고른 두 점, 없으면 B = 지금 점수 카드의 실행, A = 그보다 먼저 돌린 본 실행
async function initDiff() {
  const D = S.diff, runs = runsShown(), names = runs.map(r => r.name);
  if (!D.a && !D.b && S.pick.length === 2 && S.pick.every(n => names.includes(n))) [D.a, D.b] = S.pick;
  if (!names.includes(D.b)) D.b = S.name;
  if (!names.includes(D.a)) {
    const before = runs.filter(r => r.kind === "run" && num(r.weighted) && names.indexOf(r.name) < names.indexOf(D.b));
    D.a = before.length ? before[before.length - 1].name : null;
  }
  await loadDiff();
}

async function loadDiff() {
  const D = S.diff, key = `${D.a}|${D.b}`;
  Object.assign(D, {key, data: null, error: null});
  [D.why, D.vals, D.open].forEach(x => x.clear());
  renderDiff();
  if (!D.a || !D.b) return;
  try {
    const data = await api("/api/diff?" + query({a: D.a, b: D.b}));
    if (D.key === key) D.data = data;
  } catch (e) {
    if (D.key === key) D.error = e.message;
  }
  if (D.key === key) renderDiff();
}

function renderDiff() {
  renderDiffTop();
  renderDiffItems();
  renderDiffValues();
  renderDiffRows();
}

function diffSelect(which) {
  const D = S.diff;
  return h("select", {onchange: e => { D[which] = e.target.value || null; loadDiff(); }},
    h("option", {value: "", selected: !D[which]}, "— 실행을 고르세요 —"),
    runsShown().slice().reverse().map(x => h("option", {value: x.name, selected: x.name === D[which]}, runLabel(x))));
}

function changeLine(label, w, tip) {
  return h("div", {class: "chgrow", "data-tip": tip}, h("span", {class: "glabel"}, label),
    h("b", null, `${fmt1(w.a)} → ${fmt1(w.b)}`), h("span", {class: trend(w.delta)}, `(${signed(w.delta)})`));
}

function renderDiffTop() {
  const D = S.diff, d = D.data;
  const hint = "A에는 먼저 돌린 실행, B에는 나중 실행을 고르면 차이가 'B − A'로 나옵니다. 탭 ①의 실행 역사에서 점 두 개를 고르면 여기에 채워집니다.";
  const pick = h("div", {class: "pickcol"},
    h("label", null, "A (전) ", diffSelect("a")), h("label", null, "B (후) ", diffSelect("b")),
    h("button", {type: "button", onclick: () => { [D.a, D.b] = [D.b, D.a]; loadDiff(); }}, "A ↔ B 바꾸기"));
  if (D.error) return card("diff-top-card", "고른 두 실행", hint, pick, h("p", {class: "badt"}, "비교하지 못했습니다: " + D.error));
  if (!d) {
    return card("diff-top-card", "고른 두 실행", hint, pick,
      h("p", {class: "hint"}, D.a && D.b ? "비교하는 중… (처음에는 두 실행을 채점하느라 몇 초 걸립니다)" : "A와 B를 둘 다 고르세요."));
  }
  const show = (c, v) => v === null || v === undefined ? "—" : c.what === "입력 판" ? lastPart(v) : String(v);
  const cond = h("table", {class: "list cond"},
    h("thead", null, h("tr", null, h("th", null, "조건"), h("th", null, "A"), h("th", null, "B"))),
    h("tbody", null, d.conditions.map(c => h("tr", {class: c.changed ? "chg" : null},
      h("td", null, c.what), h("td", {class: "mono"}, show(c, c.a)), h("td", {class: "mono"}, show(c, c.b))))));
  const nos = d.prompt_changed_sections;
  const docs = d.docs, odd = docs.only_a.length || docs.only_b.length;
  card("diff-top-card", "고른 두 실행", hint, pick,
    h("p", {class: "hint"}, "노란 줄은 두 실행에서 다른 조건입니다."), cond,
    h("p", null, "안내문 글이 다른 항(실행 기록의 해시 기준): ", h("b", null, nos.length ? nos.map(n => `${n}항`).join(", ") : "없음")),
    changeLine("가중 종합", d.weighted, "항목 점수에 무게를 곱해 평균 낸 점수(weighted)"),
    changeLine("값 없는 행을 뺀 점수", d.weighted_na_excluded,
      "정답과 결과 양쪽에서 자료없음·해당없음·비해당·미기재 행을 빼고 같은 채점기로 다시 잰 점수"),
    odd ? h("p", {class: "warn"}, `주의: 두 실행이 채점한 문서가 다릅니다. A에만 ${docs.only_a.length}건, B에만 ${docs.only_b.length}건입니다. 항목 점수는 서로 다른 문서 묶음의 평균이라 차이를 그대로 믿기 어렵습니다. 바뀐 값과 원인은 둘 다 채점한 ${docs.common.length}건만 봅니다.`) : null);
}

function deltaBar(v) {
  const W = 160, mid = W / 2, len = num(v) ? Math.min(mid, Math.abs(v) / 50 * mid) : 0;
  return s("svg", {viewBox: `0 0 ${W} 14`, width: W, height: 14, class: "bar"},
    s("rect", {x: 0, y: 2, width: W, height: 10, class: "bg"}),
    num(v) && v !== 0 ? s("rect", {x: v < 0 ? mid - len : mid, y: 2, width: Math.max(len, 1), height: 10, class: v < 0 ? "no" : "ok"}) : null,
    s("line", {x1: mid, x2: mid, y1: 0, y2: 14, class: "target"}));
}

const diffClass = l => l.startsWith("---") || l.startsWith("+++") ? "dfile" : l.startsWith("@@") ? "dhunk"
  : l.startsWith("+") ? "dadd" : l.startsWith("-") ? "ddel" : null;

function togglePrompt(item, no) {
  const D = S.diff, k = `${item}|${no}`, pk = `${D.a}|${D.b}|${no}`;
  D.open.has(k) ? D.open.delete(k) : D.open.add(k);
  if (D.open.has(k) && (!D.prompts[pk] || D.prompts[pk].error)) {
    D.prompts[pk] = {loading: true};
    api("/api/prompt_diff?" + query({a: D.a, b: D.b, no}))
      .then(r => { D.prompts[pk] = {data: r}; }, e => { D.prompts[pk] = {error: e.message}; })
      .then(renderDiffItems);
  }
  renderDiffItems();
}

function promptView(no) {
  const D = S.diff, p = D.prompts[`${D.a}|${D.b}|${no}`] || {}, r = p.data;
  if (p.loading) return h("p", {class: "hint"}, `${no}항 안내문을 두 실행의 커밋에서 다시 만드는 중… (몇 초 걸립니다)`);
  if (p.error) return h("p", {class: "badt"}, `${no}항 안내문 차이를 만들지 못했습니다: ${p.error}`);
  if (!r) return null;
  const form = x => x ? "행 형식" : "JSON";
  const notes = ["a", "b"].filter(w => r.recorded[w] && r.recorded[w] !== r[w + "_hash"]).map(w => h("p", {class: "warn"},
    `주의: ${w.toUpperCase()} 실행이 기록한 해시(${r.recorded[w]})와 다시 만든 글의 해시(${r[w + "_hash"]})가 다릅니다. 그 실행은 커밋되지 않은 안내문으로 돌았을 수 있습니다.`));
  const head = h("p", {class: "hint"},
    `${no}항 안내문: A ${r.a_lines}줄(${form(r.rows[0])}), B ${r.b_lines}줄(${form(r.rows[1])}). 빨간 줄은 A에만, 초록 줄은 B에만 있습니다. 글은 화면에만 보이고 저장하지 않습니다.`);
  if (r.same) return h("div", null, head, notes, h("p", null, "두 글이 같습니다."));
  return h("div", null, head, notes, h("pre", {class: "diff"}, r.diff.split("\n").map(l => h("span", {class: diffClass(l)}, l))));
}

function renderDiffItems() {
  const D = S.diff, d = D.data;
  const hint = "항목마다 A 점수, B 점수, 차이(B − A)입니다. 막대는 가운데가 0이고 빨강은 내려간 것, 초록은 오른 것입니다(±50점이면 끝까지). 2점 넘게 내려간 항목에는 '왜?' 단추가 있고, 그 값을 만드는 항의 안내문이 바뀌었으면 '안내문 차이 보기' 단추가 있습니다.";
  if (!d) return card("diff-items-card", "항목 23개 점수 차", hint, h("p", {class: "hint"}, "두 실행을 고르면 나옵니다."));
  const causes = Object.fromEntries(d.causes.map(c => [c.item, c.reasons]));
  const changed = new Set(d.prompt_changed_sections);
  const help = n => (S.criteria.items.find(c => c.name === n) || {}).help || "";
  const rows = d.items.map(i => {
    const why = causes[i.name], nos = (i.sections || []).filter(n => changed.has(n));
    const row = h("tr", null,
      h("td", {"data-tip": `${i.name}\n${help(i.name)}\n값을 만드는 항: ${(i.sections || []).join("·")}항`}, i.name, h("small", null, ` ${i.level}`)),
      h("td", {class: "num"}, fmt1(i.a)), h("td", {class: "num"}, fmt1(i.b)),
      h("td", null, deltaBar(i.delta), " ", h("span", {class: trend(i.delta)}, signed(i.delta))),
      h("td", null,
        why ? h("button", {type: "button", onclick: () => { D.why.has(i.name) ? D.why.delete(i.name) : D.why.add(i.name); renderDiffItems(); }},
          D.why.has(i.name) ? "왜? 접기" : "왜?") : null,
        nos.map(n => h("button", {type: "button", onclick: () => togglePrompt(i.name, n)},
          `${D.open.has(`${i.name}|${n}`) ? "접기" : "안내문 차이 보기"} (${n}항)`))));
    const more = [];
    if (why && D.why.has(i.name)) {
      more.push(h("tr", {class: "sub"}, h("td", {colspan: 5}, why.length
        ? h("ul", {class: "why"}, why.map(t => h("li", null, t))) : h("p", {class: "hint"}, "수치로 뒷받침되는 원인 후보를 찾지 못했습니다."))));
    }
    nos.filter(n => D.open.has(`${i.name}|${n}`)).forEach(n => more.push(h("tr", {class: "sub"}, h("td", {colspan: 5}, promptView(n)))));
    return [row, more];
  });
  card("diff-items-card", "항목 23개 점수 차", hint, h("div", {class: "scroll"}, h("table", {class: "list ditems"},
    h("thead", null, h("tr", null, h("th", null, "항목"), h("th", null, "A"), h("th", null, "B"), h("th", null, "차이 (B − A)"), h("th", null, ""))),
    h("tbody", null, rows))));
}

function valueTable(title, list) {
  if (!list.length) return h("p", {class: "hint"}, `${title}: 없음`);
  const shown = list.slice(0, 300);
  return h("div", null, h("h3", null, `${title} ${list.length}개${list.length > shown.length ? ` (앞의 ${shown.length}개만 보임)` : ""}`),
    h("table", {class: "list"},
      h("thead", null, h("tr", null, h("th", null, "문서"), h("th", null, "종류"), h("th", null, "내용"))),
      h("tbody", null, shown.map(x => h("tr", null,
        h("td", {class: "mono"}, x.doc_id), h("td", {class: "k-" + x.kind}, x.kind), h("td", {class: "mono"}, x.content))))));
}

function renderDiffValues() {
  const D = S.diff, d = D.data;
  const hint = "채점기가 남긴 틀린 값(필수 항목만)을 두 실행 사이에서 견줍니다. 두 실행 모두 채점한 문서만 봅니다. '새로 맞춘 것'은 A에서 틀렸는데 B에서 사라진 값, '새로 틀린 것'은 B에서 새로 생긴 틀린 값입니다. 줄을 누르면 펴집니다.";
  if (!d) return card("diff-values-card", "바뀐 값", hint, h("p", {class: "hint"}, "두 실행을 고르면 나옵니다."));
  const names = Object.keys(d.changed_values);
  if (!names.length) return card("diff-values-card", "바뀐 값", hint, h("p", null, "두 실행의 틀린 값 목록이 같습니다."));
  card("diff-values-card", "바뀐 값", hint, names.map(n => {
    const c = d.changed_values[n], open = D.vals.has(n);
    return h("div", {class: "itembox" + (open ? " open" : "")},
      h("div", {class: "vrow", onclick: () => { open ? D.vals.delete(n) : D.vals.add(n); renderDiffValues(); }},
        h("span", {class: "iname"}, n), h("span", {class: "okt"}, `새로 맞춘 것 ${c.fixed.length}개`),
        h("span", {class: "badt"}, `새로 틀린 것 ${c.broken.length}개`)),
      open ? h("div", {class: "detail"}, valueTable("새로 맞춘 것", c.fixed), valueTable("새로 틀린 것", c.broken)) : null);
  }));
}

function renderDiffRows() {
  const d = S.diff.data;
  const hint = "표마다 A 결과 행 수, B 결과 행 수, 정답 행 수입니다. B가 A보다 정답에 가까워지면 초록, 멀어지면 빨강입니다.";
  if (!d) return card("diff-rows-card", "표 행 수", hint, h("p", {class: "hint"}, "두 실행을 고르면 나옵니다."));
  const keys = Object.keys(ROW_LABEL).filter(k => d.rows[k]);
  const far = r => num(r.gold) && num(r.a) && num(r.b) ? Math.abs(r.a - r.gold) - Math.abs(r.b - r.gold) : null;
  card("diff-rows-card", "표 행 수", hint, h("table", {class: "list rowsdiff"},
    h("thead", null, h("tr", null, h("th", null, "표"), h("th", null, "A"), h("th", null, "B"), h("th", null, "정답"))),
    h("tbody", null, keys.map(k => {
      const r = d.rows[k];
      return h("tr", null, h("td", null, ROW_LABEL[k]), h("td", {class: "num"}, r.a ?? "—"),
        h("td", {class: "num " + (trend(far(r)) || "")}, r.b ?? "—"), h("td", {class: "num"}, r.gold ?? "—"));
    }))));
}

// ── 탭 ③ 원문 대조 ─────────────────────────────────────

const SECTION_NAME = {1: "제품·회사 정보", 2: "유해성·위험성", 3: "구성성분", 4: "응급조치", 5: "폭발·화재 시 대처",
  6: "누출 사고 시 대처", 7: "취급·저장", 8: "노출방지·개인보호구", 9: "물리화학적 특성", 10: "안정성·반응성",
  11: "독성", 12: "환경 영향", 13: "폐기", 14: "운송", 15: "법적 규제", 16: "그 밖의 참고사항"};
const TABLE_NAME = {
  meta: "관리정보", product: "제품", companies: "회사", hazard: "유해성", "hazard.classes": "유해성 분류",
  "hazard.pictograms": "그림문자", "hazard.h_statements": "H 코드", "hazard.p_statements": "P 코드",
  "hazard.other_hazards": "기타 유해성", composition: "조성", components: "성분", narratives: "서술 문장",
  exposure_limits: "노출기준", physchem: "물리·화학 성질", toxicity: "독성", cmr: "발암성 등 CMR", ecotox: "생태 독성",
  transport: "운송", regulations: "규제", dangerous_goods: "위험물", waste: "폐기물", intl_class: "국제 분류",
  extras: "남는 값 extras",
};
const pad3 = n => String(n).padStart(3, "0");
const tipOf = v => v !== null && typeof v === "object" ? JSON.stringify(v, null, 1) : null;

// 고른 실행의 개발용 문서(채점한 문서 + 정답 없는 문서). 평가용은 서버가 목록에서 이미 뺐다
function docsOf(name) {
  const r = S.list.find(x => x.name === name);
  return r ? [...(r.docs || []), ...(r.no_gold || [])].sort() : [];
}

async function initDoc() {
  const D = S.doc;
  if (!runsShown().some(r => r.name === D.run)) D.run = S.name;
  if (!docsOf(D.run).includes(D.doc)) D.doc = docsOf(D.run)[0] || null;
  await loadDoc();
}

async function loadDoc() {
  const D = S.doc, key = `${D.run}|${D.doc}`;
  Object.assign(D, {key, data: null, error: null, page: null, pick: null});
  [D.selLines, D.selPaths, D.open].forEach(x => x.clear());
  renderDoc();
  if (!D.run || !D.doc) return;
  try {
    const data = await api("/api/doc?" + query({run: D.run, doc: D.doc}));
    if (D.key === key) prepDoc(data);
  } catch (e) {
    if (D.key === key) D.error = e.message;
  }
  if (D.key === key) renderDoc();
}

function prepDoc(d) {
  const D = S.doc;
  D.data = d;
  D.page = d.pages.length ? d.pages[0] : null;
  D.line = Object.fromEntries(d.lines.map(l => [l.id, l]));
  D.value = Object.fromEntries(d.values.map(v => [v.path, v]));
  const pos = Object.fromEntries(d.lines.map((l, i) => [l.id, i]));
  D.sec = {};                                        // 줄 → 그 줄이 든 항 (항 구간 띠)
  for (const [no, sp] of Object.entries(d.sections)) {
    if (!(sp.start in pos) || !(sp.end in pos)) continue;
    for (let i = pos[sp.start]; i <= pos[sp.end]; i++) D.sec[d.lines[i].id] = +no;
  }
  // 항 → 표 → 행 → 칸. 실버에만 있는 행은 같은 표 끝에 실버 행 번호로 붙인다
  const secs = new Map();
  const add = (v, only) => {
    const sk = v.section ?? "?";
    if (!secs.has(sk)) secs.set(sk, new Map());
    const tables = secs.get(sk);
    if (!tables.has(v.table)) tables.set(v.table, new Map());
    // 실버에만 있는 칸도 짝 행이 결과에 있으면(pair_row) 그 결과 행 아래에 둔다
    const row = only && v.pair_row !== null && v.pair_row !== undefined ? "r" + v.pair_row : (only ? "s" : "r") + (v.row ?? "");
    const rows = tables.get(v.table), rk = row;
    if (!rows.has(rk)) rows.set(rk, []);
    rows.get(rk).push({v, only});
  };
  d.values.forEach(v => add(v, false));
  d.silver_only.forEach(v => add(v, true));
  const order = k => k === "?" ? 99 : +k;
  D.groups = [...secs.entries()].sort((a, b) => order(a[0]) - order(b[0]));
}

function renderDoc() {
  renderDocTop();
  renderDocMain();
}

function renderDocTop() {
  const D = S.doc, d = D.data;
  const hint = "실행과 문서를 고르면 아래에 쪽 그림·쪽 글자(왼쪽), 결과 값과 실버 값(오른쪽)이 나옵니다. 개발용 문서만 고를 수 있습니다.";
  const docs = docsOf(D.run);
  const runSel = h("select", {onchange: e => { D.run = e.target.value; D.doc = docsOf(D.run)[0] || null; loadDoc(); }},
    runsShown().slice().reverse().map(x => h("option", {value: x.name, selected: x.name === D.run}, runLabel(x))));
  const docSel = h("select", {onchange: e => { D.doc = e.target.value; loadDoc(); }},
    docs.length ? docs.map(x => h("option", {value: x, selected: x === D.doc}, x))
      : h("option", {value: ""}, "— 이 실행에는 결과가 있는 개발용 문서가 없습니다 —"));
  const pick = h("div", {class: "pickcol"}, h("label", null, "실행 ", runSel), h("label", null, "문서 ", docSel));
  if (D.error) return card("doc-top-card", "실행과 문서", hint, pick, h("p", {class: "badt"}, "불러오지 못했습니다: " + D.error));
  if (!d) return card("doc-top-card", "실행과 문서", hint, pick, h("p", {class: "hint"}, D.doc ? "불러오는 중…" : "문서를 고르세요."));
  const pageSel = h("select", {id: "doc-page", onchange: e => showPage(+e.target.value)},
    d.pages.map(p => h("option", {value: p, selected: p === D.page}, `${p}쪽`)));
  const secBtns = Array.from({length: 16}, (_, i) => i + 1).map(no => {
    const sp = d.sections[no];
    return h("button", {type: "button", class: "secbtn", disabled: !sp, onclick: () => goSection(no),
      "data-tip": sp ? `${no}항 ${SECTION_NAME[no]}\n구간 ${sp.start} ~ ${sp.end}\n누르면 왼쪽 줄 목록이 이 항의 첫 줄로 갑니다.`
        : `${no}항 ${SECTION_NAME[no]}: 제목을 찾지 못해 구간이 없습니다`}, no);
  });
  const same = d.values.filter(v => v.silver.same).length;
  card("doc-top-card", "실행과 문서", hint, pick,
    h("div", {class: "pickcol"}, h("label", null, "쪽 ", pageSel), h("span", null, "항 ", secBtns)),
    h("p", {class: "hint"}, `결과 값 ${d.values.length}개 · 실버와 같음 ${same}개 · 다름 ${d.values.length - same}개 · 실버에만 ${d.silver_only.length}개`,
      d.has_gold ? "" : " (이 문서는 실버가 없습니다)"),
    d.warnings.map(w => h("p", {class: "warn"}, "주의: " + w)));
}

function renderDocMain() {
  const D = S.doc, d = D.data;
  const hint = "값을 누르면 근거 줄과 쪽 그림의 그 자리가 노랗게 켜집니다. 줄을 누르면 그 줄을 근거로 쓴 값이 켜집니다. 근거 줄은 결과 파일의 원문 조각(evidence)을 같은 쪽 줄과 맞춰 찾습니다. 그림 위 자리는 쪽 좌표 파일(pNNN.json)의 칸 글자와 줄 글자를 맞춰 찾고, 못 맞춘 줄은 글자만 켭니다.";
  if (!d) return card("doc-main-card", "원문 · 결과 · 실버", hint, h("p", {class: "hint"}, "실행과 문서를 고르면 나옵니다."));
  const legend = h("p", {class: "legend"},
    h("span", {class: "sw lg-same"}, "회색 = 실버와 같음"), h("span", {class: "sw lg-diff"}, "주황 = 실버와 다르거나 실버에 없음"),
    h("span", {class: "sw lg-only"}, "빨강 테두리 = 실버에만 있음(결과가 빠뜨림)"), h("span", {class: "sw lg-hl"}, "노랑 = 고른 값·줄"),
    h("span", {class: "sw"}, "줄 왼쪽 띠 = 항 구간"));
  card("doc-main-card", "원문 · 결과 · 실버", hint, legend, h("p", {class: "selnote", id: "doc-sel"}),
    h("div", {class: "dgrid"}, h("div", {class: "dleft", id: "doc-left"}), h("div", {class: "dright", id: "doc-right"})));
  renderDocLeft();
  renderDocRight();
  noteSel();
}

// 고른 줄을 쪽 그림 위 사각형으로 그리고, 그림 상자를 첫 사각형으로 옮긴다
function drawBoxes(img, svg) {
  const D = S.doc;
  if (!img.naturalWidth) return;
  svg.setAttribute("viewBox", `0 0 ${img.naturalWidth} ${img.naturalHeight}`);
  const lines = [...D.selLines].map(id => D.line[id]).filter(l => l && l.page === D.page && l.bbox);
  svg.replaceChildren(...lines.map(({bbox: [x0, y0, x1, y1]}) =>
    s("rect", {x: x0 - 6, y: y0 - 6, width: x1 - x0 + 12, height: y1 - y0 + 12, rx: 4, class: "box"})));
  const box = img.closest(".pagebox");
  if (lines.length && box) box.scrollTop = lines[0].bbox[1] / img.naturalHeight * img.clientHeight - box.clientHeight / 3;
}

function renderDocLeft() {
  const D = S.doc, d = D.data, el = document.getElementById("doc-left");
  if (!el || !d) return;
  const sel = document.getElementById("doc-page");
  if (sel) sel.value = D.page;
  const img = h("img", {src: `/pages/${encodeURIComponent(d.doc_id)}/p${pad3(D.page)}.png`, alt: `${D.page}쪽 그림`});
  const svg = s("svg", {class: "boxes"});
  const wrap = h("div", {class: "pagewrap"}, img, svg);
  img.addEventListener("load", () => drawBoxes(img, svg));
  img.addEventListener("error", () => wrap.replaceChildren(h("p", {class: "hint"}, `${D.page}쪽 그림 파일이 없습니다.`)));
  D.draw = () => drawBoxes(img, svg);
  let prev = null;
  const lines = d.lines.filter(l => l.page === D.page).map(l => {
    const no = D.sec[l.id], first = no && no !== prev, used = (d.line_index[l.id] || []).length;
    prev = no;
    return h("div", {class: `ln${no ? " band b" + (no % 2) : ""}${D.selLines.has(l.id) ? " hl" : ""}`, "data-id": l.id,
      onclick: () => pickLine(l.id)},
      h("span", {class: "lsec", "data-tip": no ? `${no}항 ${SECTION_NAME[no]} 구간` : null}, first ? `${no}항` : ""),
      h("span", {class: "lno mono"}, `L${pad3(l.no)}`), h("span", {class: "ltx"}, l.text),
      used ? h("span", {class: "luse", "data-tip": "이 줄을 근거로 쓴 결과 값 수"}, `값 ${used}`) : h("span"));
  });
  el.replaceChildren(h("div", {class: "pagebox"}, wrap), h("div", {class: "linebox", id: "doc-lines"}, lines));
}

function renderDocRight() {
  const D = S.doc, el = document.getElementById("doc-right");
  if (!el || !D.data) return;
  if (!D.groups.length) return el.replaceChildren(h("p", {class: "hint"}, "결과 값이 없습니다."));
  el.replaceChildren(...D.groups.map(([sec, tables]) => {
    const k = `s${sec}`, all = [...tables.values()].flatMap(rows => [...rows.values()].flat());
    const only = all.filter(x => x.only).length, diff = all.filter(x => !x.only && !x.v.silver.same).length;
    return h("details", {class: "dsec", open: D.open.has(k), ontoggle: e => setOpen(k, e.target.open)},
      h("summary", null, sec === "?" ? "항을 모르는 값" : `${sec}항 ${SECTION_NAME[sec] || ""}`,
        h("small", null, ` 값 ${all.length - only} · 다름 ${diff} · 실버에만 ${only}`)),
      [...tables.entries()].map(([t, rows]) => tableBlock(sec, t, rows)));
  }));
}

function setOpen(k, open) {
  open ? S.doc.open.add(k) : S.doc.open.delete(k);
}

function tableBlock(sec, t, rows) {
  const D = S.doc, k = `s${sec}|${t}`, n = [...rows.values()].flat().length;
  return h("details", {class: "dtab", open: D.open.has(k), ontoggle: e => setOpen(k, e.target.open)},
    h("summary", null, TABLE_NAME[t] || t, h("small", {class: "mono"}, ` ${t} · ${n}칸`)),
    h("table", {class: "list vals"},
      h("thead", null, h("tr", null, h("th", null, "칸"), h("th", null, "결과 값 (근거 줄)"), h("th", null, "실버 값"))),
      h("tbody", null, [...rows.entries()].map(([rk, xs]) => [rowHead(rk), xs.map(valueRow)]))));
}

function rowHead(rk) {
  if (rk === "r") return null;                       // 객체 칸(행 번호 없음)
  if (rk === "s") return h("tr", {class: "rhead"}, h("td", {colspan: 3}, "실버에만 있는 칸"));
  const n = +rk.slice(1) + 1;
  return h("tr", {class: "rhead"}, h("td", {colspan: 3}, rk[0] === "s" ? `실버 ${n}번째 행에만 있는 칸` : `${n}번째 행`));
}

function valueRow({v, only}) {
  const D = S.doc, field = h("td", {class: "mono fld"}, v.field || "(행 전체)");
  if (only) return h("tr", null, field, h("td", {class: "hint"}, "—"), h("td", {class: "sv only", "data-tip": tipOf(v.value)}, v.text));
  const sv = v.silver;
  return h("tr", null, field,
    h("td", {class: "pv" + (D.selPaths.has(v.path) ? " hl" : ""), "data-path": v.path, "data-tip": tipOf(v.value),
      onclick: () => pickValue(v.path)},
      v.text, h("small", {class: "lref mono"}, v.lines.length ? v.lines.join(" ") : "근거 줄 못 찾음")),
    h("td", {class: "sv " + (sv.same ? "same" : "diff"), "data-tip": sv.value === null ? "실버에 이 값이 없습니다" : tipOf(sv.value)},
      sv.value === null ? "—" : sv.text));
}

// 고른 것 표시: 다시 그리지 않고 글자 줄·값 칸의 켜짐만 바꾼다(스크롤 자리를 지킨다)
function markLines() {
  const D = S.doc;
  document.querySelectorAll("#doc-lines .ln").forEach(n => n.classList.toggle("hl", D.selLines.has(n.dataset.id)));
  if (D.draw) D.draw();
}

function markValues() {
  document.querySelectorAll("#doc-right .pv").forEach(n => n.classList.toggle("hl", S.doc.selPaths.has(n.dataset.path)));
}

function noteSel() {
  const D = S.doc, el = document.getElementById("doc-sel");
  if (!el) return;
  if (!D.pick) return el.replaceChildren("값이나 줄을 눌러 보세요.");
  if (D.pick.line) {
    const n = D.selPaths.size;
    return el.replaceChildren(`고른 줄 ${D.pick.line}: `, n ? `이 줄을 근거로 쓴 결과 값 ${n}개가 오른쪽에 켜졌습니다.` : "이 줄을 근거로 쓴 결과 값이 없습니다.");
  }
  const v = D.value[D.pick.value], noBox = v.lines.filter(id => D.line[id] && !D.line[id].bbox);
  el.replaceChildren(`고른 값 ${v.path.replace(/^msds\[0\]\./, "")}: `,
    v.lines.length ? `근거 줄 ${v.lines.join(", ")}` : "근거 줄을 찾지 못했습니다(실행이 다른 쪽 글자로 돌았거나 원문 조각이 없습니다).",
    noBox.length ? ` · 그림 위 자리를 못 찾은 줄 ${noBox.join(", ")}은 글자만 켭니다.` : "");
}

function scrollInto(box, el, start) {
  if (box && el) box.scrollTop += el.getBoundingClientRect().top - box.getBoundingClientRect().top - (start ? 4 : box.clientHeight / 2);
}

const lineEl = id => document.querySelector(`#doc-lines .ln[data-id="${CSS.escape(id)}"]`);

function showPage(p) {
  if (p === S.doc.page) return markLines();
  S.doc.page = p;
  renderDocLeft();
}

function goSection(no) {
  const D = S.doc, sp = D.data.sections[no];
  showPage(D.line[sp.start].page);
  scrollInto(document.getElementById("doc-lines"), lineEl(sp.start), true);
}

function pickValue(path) {
  const D = S.doc, v = D.value[path];
  D.pick = {value: path};
  D.selPaths = new Set([path]);
  D.selLines = new Set(v.lines);
  const first = v.lines.map(id => D.line[id]).find(Boolean);
  if (first) showPage(first.page);
  markLines();
  markValues();
  noteSel();
  if (first) scrollInto(document.getElementById("doc-lines"), lineEl(first.id));
}

function pickLine(id) {
  const D = S.doc, paths = D.data.line_index[id] || [];
  D.pick = {line: id};
  D.selLines = new Set([id]);
  D.selPaths = new Set(paths);
  let opened = false;
  for (const p of paths) {
    const v = D.value[p], sk = `s${v.section ?? "?"}`;
    for (const k of [sk, `${sk}|${v.table}`]) if (!D.open.has(k)) { D.open.add(k); opened = true; }
  }
  markLines();
  opened ? renderDocRight() : markValues();
  noteSel();
  scrollInto(document.getElementById("doc-right"), document.querySelector("#doc-right .pv.hl"));
}

// ── 탭 ④ 작업 ─────────────────────────────────────────
// 시험(try_section.py)·본 실행(run_sections.py)·비교표(compare_models.py)를 띄우고 진행을 본다. 고쳐 쓴 안내문은 이 화면의
// 메모리에만 있고 보낼 때 서버가 저장소 밖 임시 파일로 넘긴 뒤 지운다 (D-47).

const JOB_KIND = {try: "시험", run: "본 실행", compare: "비교표"};
const JOB_STATUS = {running: "돌아감", done: "끝남", failed: "실패", stopped: "멈춤", unknown: "모름"};
const JOB_TIP = {unknown: "앱을 다시 켜기 전에 시작한 작업이라 결과를 모릅니다. 로그나 실행 폴더를 보세요.\n아직 돌고 있으면 아래에 '다른 터미널에서'로 따로 보입니다."};
const range16 = () => Array.from({length: 16}, (_, i) => i + 1);
const field = (label, ...kids) => h("div", {class: "jfield"}, h("span", {class: "jlab"}, label), ...kids);
const fromRuns = p => { const s = String(p || ""), i = s.lastIndexOf("/runs/"); return i >= 0 ? s.slice(i + 1) : s; };
const clock = t => {
  const d = new Date(t * 1000), p = n => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
    cache: "no-store"});
  return {status: r.status, data: await r.json().catch(() => ({}))};
}

async function initJobs() {
  if (!S.jobs.opts) await loadOptions();
  renderJobs();
  await pollJobs();
}

// 모델(연결 여부)·개발용 문서·쪽 폴더·추천 실행 이름. 처음 고를 모델은 연결된 항목별 추출 모델(행 형식 항이 있는 태그)
async function loadOptions() {
  const J = S.jobs;
  try {
    J.opts = await api("/api/options");
    J.error = null;
  } catch (e) {
    J.error = e.message;
    return;
  }
  const o = J.opts, usable = m => !o.status_checked || m.connected;
  const extract = m => m.rows_sections.length > 0;   // 실버용 태그(gpt·claude)보다 항목별 추출 모델을 먼저
  const pick = o.models.find(m => usable(m) && extract(m)) || o.models.find(usable) || o.models.find(extract) || o.models[0];
  for (const f of [J.t, J.r]) {
    if (!o.models.some(m => m.tag === f.model && usable(m))) f.model = pick ? pick.tag : null;
    if (!o.pages_dirs.some(p => p.value === f.pages)) f.pages = o.default_pages_dir;
  }
  if (!o.docs.some(d => d.doc_id === J.t.doc)) J.t.doc = o.docs.length ? o.docs[0].doc_id : null;
  if (!J.r.docs) J.r.docs = new Set(o.docs.map(d => d.doc_id));
  if (!J.r.edited) J.r.name = suggestName();
}

function suggestName() {
  const o = S.jobs.opts, R = S.jobs.r;
  const all = o.docs.length > 0 && o.docs.every(d => R.docs.has(d.doc_id));
  return (((o.run_names[R.model] || {})[R.pages] || {})[all ? "dev10" : "probe"]) || "";
}

function renderJobs() {
  renderJobTry();
  renderJobRun();
  renderJobCompare();
  renderJobResult();
  renderJobList();
}

function modelSelect(f, anyModel, after) {
  const o = S.jobs.opts, off = m => o.status_checked && !m.connected;
  return h("select", {onchange: e => { f.model = e.target.value; after(); }},
    o.models.map(m => h("option", {value: m.tag, selected: m.tag === f.model, disabled: off(m) && !anyModel},
      m.tag + (off(m) ? " — 연결 안 됨" : ""))));
}

function pagesSelect(f, after) {
  return h("select", {onchange: e => { f.pages = e.target.value; after(); }},
    S.jobs.opts.pages_dirs.map(p => h("option", {value: p.value, selected: p.value === f.pages}, p.name)));
}

function connNote() {
  const o = S.jobs.opts;
  const tip = o.models.map(m => `${m.tag}: ${m.connected ? "연결됨" : m.connected === false ? "연결 안 됨 (" + m.error + ")" : "확인 안 함"}`).join("\n");
  return h("span", {class: "hint", "data-tip": tip},
    o.status_checked ? `연결된 모델 ${o.models.filter(m => m.connected).length}개 ` : "모델 서버 연결은 확인하지 않았습니다 ",
    h("button", {type: "button", onclick: () => loadOptions().then(renderJobs).catch(fail)}, "연결 다시 보기"));
}

function jobMsg(key) {
  const m = S.jobs.msg[key];
  return m ? h("p", {class: m.ok ? "okt" : "badt"}, m.text) : null;
}

const loadingCard = (id, title, hint) => card(id, title, hint, h("p", {class: S.jobs.error ? "badt" : "hint"},
  S.jobs.error ? "고를 거리를 불러오지 못했습니다: " + S.jobs.error : "불러오는 중… (모델 서버 연결을 확인하느라 몇 초 걸릴 수 있습니다)"));

// ── 시험하기 ─────────────────────────────────────────

function renderJobTry() {
  const J = S.jobs, o = J.opts, T = J.t;
  const hint = "항 하나·여러 개·문서 전체를 모델에 다시 보내 봅니다. 결과는 기준 실행의 다른 항 답에 끼워 채점합니다. 기록은 runs/manual/에 남습니다.";
  if (!o) return loadingCard("jobs-try-card", "시험하기", hint);
  const one = !T.all && T.secs.size === 1, no = one ? [...T.secs][0] : null;
  if (!one) T.edit = false;
  const radio = (name, on, text, set, attrs) => h("label", {class: "chk", ...(attrs || {})},
    h("input", {type: "radio", name, checked: on, disabled: (attrs || {}).disabled, onchange: () => { set(); renderJobTry(); }}), text);
  const boxes = range16().map(n => h("label", {class: "chk"}, h("input", {type: "checkbox", checked: T.secs.has(n), disabled: T.all,
    onchange: e => { e.target.checked ? T.secs.add(n) : T.secs.delete(n); renderJobTry(); }}), n));
  const bases = runsShown().filter(r => r.model_tag === T.model && [...(r.docs || []), ...(r.no_gold || [])].includes(T.doc)).reverse();
  if (T.base && !bases.some(r => r.name === T.base)) T.base = "";
  const editor = T.edit ? h("div", {class: "jedit"},
    h("p", {class: "warn"}, "고쳐 쓴 글은 저장되지 않습니다. 화면을 새로 고치면 사라집니다. 보낸 뒤 임시 파일은 지우고, 기록에는 글의 해시만 남습니다."),
    h("button", {type: "button", onclick: () => loadPrompt(no).catch(e => { J.msg.try = {text: e.message}; renderJobTry(); })},
      `${no}항의 지금 안내문 불러오기`),
    T.textFor && T.textFor !== `${T.model}|${no}` ? h("span", {class: "hint"}, " 글상자의 글은 다른 모델이나 항에서 불러온 것입니다.") : null,
    h("textarea", {class: "jtext", rows: 14, spellcheck: "false", oninput: e => { T.text = e.target.value; }}, T.text)) : null;
  card("jobs-try-card", "시험하기", hint,
    field("모델", modelSelect(T, T.dry, renderJobTry)),
    field("문서", h("select", {onchange: e => { T.doc = e.target.value; renderJobTry(); }},
      o.docs.map(d => h("option", {value: d.doc_id, selected: d.doc_id === T.doc}, d.doc_id)))),
    field("쪽 폴더", pagesSelect(T, renderJobTry)),
    field("범위", radio("tscope", !T.all, "항 고르기", () => { T.all = false; }),
      radio("tscope", T.all, "문서 전체(16개 항)", () => { T.all = true; })),
    h("div", {class: "boxes"}, boxes),
    field("안내문", radio("tprompt", !T.edit, "코드가 만든 것", () => { T.edit = false; }),
      radio("tprompt", T.edit, "고쳐 쓰기", () => { T.edit = true; },
        {disabled: !one, "data-tip": one ? null : "항을 하나만 고르면 쓸 수 있습니다"})),
    editor,
    field("기준 실행", h("select", {onchange: e => { T.base = e.target.value; }, "data-tip": "새 항 답을 끼워 넣을 실행. 그 실행의 점수가 '전', 끼운 뒤 점수가 '후'입니다"},
      h("option", {value: "", selected: !T.base}, "자동 (같은 모델의 가장 최근 dev10 실행)"),
      bases.map(r => h("option", {value: r.name, selected: r.name === T.base}, runLabel(r))))),
    h("label", {class: "chk", "data-tip": "서버를 부르지 않고 ① 보낸 입력과 ② 안내문만 봅니다. 연결 안 된 모델도 고를 수 있습니다"},
      h("input", {type: "checkbox", checked: T.dry, onchange: e => { T.dry = e.target.checked; renderJobTry(); }}), "dry-run (서버 없이 입력·안내문만)"),
    h("div", {class: "pickrow"},
      h("button", {type: "button", class: "primary", onclick: () => startTry().catch(e => { J.msg.try = {text: e.message}; renderJobTry(); })},
        T.dry ? "입력·안내문 보기" : "돌리기"), connNote()),
    jobMsg("try"));
}

async function loadPrompt(no) {
  const T = S.jobs.t;
  const d = await api("/api/prompt?" + query({model: T.model, no}));
  T.text = d.text;
  T.textFor = `${T.model}|${no}`;
  renderJobTry();
}

async function startTry() {
  const J = S.jobs, T = J.t, o = J.opts, m = o.models.find(x => x.tag === T.model);
  if (!T.dry && o.status_checked && !(m && m.connected)) throw new Error("연결된 모델을 고르세요. dry-run은 연결 없이 됩니다.");
  if (T.edit && !T.text.trim()) throw new Error("고쳐 쓴 안내문이 비었습니다. '지금 안내문 불러오기'로 채운 뒤 고치세요.");
  const {status, data} = await post("/api/jobs/try", {model: T.model, doc: T.doc, all: T.all,
    sections: T.all ? null : [...T.secs].sort((a, b) => a - b), pages_dir: T.pages,
    system_text: T.edit ? T.text : null, base_run: T.base || null, dry_run: T.dry});
  if (status !== 200) throw new Error(data.error || `요청 실패 (${status})`);
  J.msg.try = null;
  Object.assign(J, {watch: data.id, result: null, tried: null});
  renderJobTry();
  await pollJobs();
  document.getElementById("jobs-result-card").scrollIntoView({behavior: "smooth", block: "start"});
}

// ── 시험 결과: 단계 6개를 접고 펼친다 ─────────────────

function renderJobResult() {
  const J = S.jobs, id = J.watch;
  const hint = "시험하기에서 돌린 결과를 단계별로 접어 둡니다. 제목을 누르면 펼칩니다. 작업 목록의 '결과'로 지난 시험도 볼 수 있습니다.";
  if (!id) return card("jobs-result-card", "시험 결과", hint, h("p", {class: "hint"}, "아직 고른 시험이 없습니다."));
  const job = J.list.find(j => j.id === id);
  const head = h("p", null, h("b", null, job ? job.label : id), " — ", job ? jobStatus(job) : "…");
  if (!J.result) {
    const why = !job || job.status === "running" ? "끝나면 여기에 나옵니다." : "로그에 결과 JSON이 없습니다. 아래 작업 목록에서 로그를 보세요.";
    return card("jobs-result-card", "시험 결과", hint, head, h("p", {class: "hint"}, why));
  }
  card("jobs-result-card", "시험 결과", hint, head, tryStages(J.result));
}

function stage(title, open, ...kids) {
  return h("details", {class: "stage", open: open || null}, h("summary", null, title), h("div", {class: "stagebody"}, ...kids));
}

function tryStages(R) {
  const p = R.plan || {}, secs = Object.values(p.sections || {});
  const out = [
    stage("① 보낸 입력", false,
      h("p", null, `${p.doc_id} · ${p.model_tag} (${p.model}) · 쪽 글자 ${p.pages_dir} · 항목 분할 ${p.sections_method} · MSDS ${p.msds_count}건(첫 건만)`),
      h("table", {class: "list"},
        h("thead", null, h("tr", null, ["항", "형식", "보낸 줄(머리)", "항 구간", "분할", "쪽", "이미지"].map(x => h("th", null, x)))),
        h("tbody", null, secs.map(s => h("tr", null, h("td", null, `${s.section}항`), h("td", null, s.rows ? "행 형식" : "JSON"),
          h("td", {class: "num"}, `${s.lines} (${s.preamble_lines})`), h("td", {class: "mono"}, `${s.first} ~ ${s.last}`),
          h("td", null, s.method), h("td", null, (s.pages || []).join(", ")), h("td", null, (s.images || []).join(", ") || "없음"))))),
      (p.warnings || []).map(w => h("p", {class: "warn"}, "주의: " + w))),
    stage("② 안내문", false,
      h("p", {class: "hint"}, "안내문 글은 기록하지 않습니다. 실행 기록과 같은 규칙의 해시(sha256 앞 12자리)만 보입니다. 글은 위 '고쳐 쓰기 → 불러오기'로 봅니다."),
      h("ul", null, secs.map(s => h("li", null, `${s.section}항 해시 `, h("span", {class: "mono"}, s.prompt_hash),
        s.system_override ? h("b", null, " (고쳐 쓴 안내문)") : ""))))];
  if (R.run) {                                       // 문서 전체 (--all)
    const run = R.run;
    out.push(stage("③~⑤ 문서 전체 실행", true,
      h("p", null, `성공 ${run.sections_ok}항 · 실패 ${run.sections_failed}항 · 재추출 ${run.reextracted}항 · ${fmt1(run.seconds)}초`),
      h("p", {class: "hint"}, "문서 전체는 실행기로 돌려서 항별 원문 답은 기록 폴더의 raw/에 있습니다. 탭 ①·③에서 그 기록([수동])을 고르면 값과 줄을 봅니다.")));
    out.push(stage("⑥ 점수 전 → 후", true, scoreView(R.score, (R.summary || {}).weighted, R.base_run, null)));
  } else if (!R.results) {
    out.push(h("p", {class: "hint"}, "dry-run이라 서버를 부르지 않았습니다. ③~⑥은 없습니다."));
  } else {
    const res = Object.values(R.results);
    out.push(stage("③ 모델 원문 답", false, res.map(r => h("details", {class: "dtab"},
      h("summary", null, `${r.section}항 · 방식 ${r.mode || "—"} · 끝난 이유 ${r.finish_reason || "—"} · ${fmt1(r.seconds)}초`),
      h("pre", {class: "log"}, r.raw_text || "(응답 없음)")))));
    out.push(stage("④ 읽은 결과", false, res.map(r => h("div", {class: "secres"},
      h("p", null, h("b", {class: r.ok ? "okt" : "badt"}, `${r.section}항 ${r.ok ? "성공" : "실패"}`),
        ` · 버린 줄 ${r.dropped_rows} · ${r.reextracted ? "재추출 결과" : "첫 시도"} · 시도 ${r.attempts}회`,
        ` · 입력 ${(r.usage || {}).prompt_tokens ?? "—"} / 출력 ${(r.usage || {}).completion_tokens ?? "—"} 토큰`),
      (r.errors || []).map(e => h("p", {class: "badt"}, "오류: " + e)),
      (r.check_problems || []).map(e => h("p", {class: "warn"}, "줄 번호 검사: " + e)),
      r.parsed ? h("details", {class: "dtab"}, h("summary", null, "읽은 값 (JSON)"), h("pre", {class: "log"}, JSON.stringify(r.parsed, null, 1))) : null))));
    out.push(stage("⑤ 펼친 TO21 칸", false,
      h("p", {class: "hint"}, "표는 행 수, 객체는 값이 있는 칸 수입니다. 서술·extras는 그 항의 것만 셉니다."),
      h("ul", null, Object.entries(R.fields || {}).map(([no, f]) => h("li", null, `${no}항: `,
        Object.entries(f).map(([k, n]) => `${ROW_LABEL[k] || k} ${n}`).join(", ") || "없음")))));
    out.push(stage("⑥ 점수 전 → 후", true, scoreView(R.score, null, R.base_run, R.score_skipped)));
  }
  if (R.saved) out.push(h("p", {class: "hint"}, "기록: ", h("span", {class: "mono"}, fromRuns(R.saved))));
  return out;
}

function scoreView(sc, weighted, base, skipped) {
  if (!sc) {
    return [num(weighted) ? h("p", null, `가중 종합 ${fmt1(weighted)}점`) : null,
      h("p", {class: "hint"}, "점수 전 → 후는 건너뛰었습니다: " + (skipped || "기준 실행이나 정답이 없습니다"))];
  }
  const d = sc.after.weighted - sc.before.weighted;
  return [h("div", {class: "chgrow"}, h("span", {class: "glabel"}, "가중 종합"),
      h("b", null, `${fmt1(sc.before.weighted)} → ${fmt1(sc.after.weighted)}`), h("span", {class: trend(d)}, `(${signed(d)})`)),
    base ? h("p", {class: "hint"}, "기준 실행: ", h("span", {class: "mono"}, fromRuns(base))) : null,
    sc.changed.length
      ? h("table", {class: "list cond"}, h("thead", null, h("tr", null, h("th", null, "바뀐 항목"), h("th", null, "전"), h("th", null, "후"))),
        h("tbody", null, sc.changed.map(c => h("tr", null, h("td", null, c.name), h("td", {class: "num"}, pct(c.before)),
          h("td", {class: "num " + (trend((c.after ?? 0) - (c.before ?? 0)) || "")}, pct(c.after))))))
      : h("p", null, "바뀐 항목 없음"),
    (sc.warnings || []).map(w => h("p", {class: "warn"}, "주의: " + w))];
}

async function loadResult(id) {
  const r = await fetch(`/api/jobs/${encodeURIComponent(id)}/result`, {cache: "no-store"});
  const data = r.status === 200 ? await r.json().catch(() => null) : null;
  if (S.jobs.watch !== id) return;
  Object.assign(S.jobs, {result: data, tried: id});
  renderJobResult();
}

function watchTry(id) {
  Object.assign(S.jobs, {watch: id, result: null, tried: null});
  renderJobResult();
  loadResult(id).catch(fail);
  document.getElementById("jobs-result-card").scrollIntoView({behavior: "smooth", block: "start"});
}

// ── 본 실행 ───────────────────────────────────────────

function renderJobRun() {
  const J = S.jobs, o = J.opts, R = J.r;
  const hint = "개발용 문서를 run_sections.py로 n회 돌립니다. 실행 이름 끝에 _r1, _r2…가 붙습니다. Mac이 잠들어 멈추지 않게 caffeinate로 감쌉니다.";
  if (!o) return loadingCard("jobs-run-card", "본 실행", hint);
  const refill = () => { if (!R.edited) R.name = suggestName(); renderJobRun(); };
  const boxes = o.docs.map(d => h("label", {class: "chk"}, h("input", {type: "checkbox", checked: R.docs.has(d.doc_id),
    onchange: e => { e.target.checked ? R.docs.add(d.doc_id) : R.docs.delete(d.doc_id); refill(); }}), d.doc_id));
  card("jobs-run-card", "본 실행", hint,
    field("모델", modelSelect(R, false, refill)),
    field("쪽 폴더", pagesSelect(R, refill)),
    field("문서", `${R.docs.size}/${o.docs.length}건`,
      h("button", {type: "button", onclick: () => { R.docs = new Set(o.docs.map(d => d.doc_id)); refill(); }}, "모두"),
      h("button", {type: "button", onclick: () => { R.docs.clear(); refill(); }}, "없음")),
    h("div", {class: "boxes"}, boxes),
    field("반복", h("input", {type: "number", min: 1, max: 10, value: R.repeat, class: "jnum",
      oninput: e => { R.repeat = Math.round(+e.target.value); }}), "회"),
    field("실행 이름", h("input", {type: "text", class: "jname mono", value: R.name,
      oninput: e => { R.name = e.target.value; R.edited = true; }}),
      h("button", {type: "button", "data-tip": "날짜_sections_모델 태그_안내문 버전_입력판_용도.\n개발용 10건을 모두 고르면 dev10, 아니면 probe. 같은 이름이 있으면 _2를 붙입니다.",
        onclick: () => { R.edited = false; refill(); }}, "추천 이름")),
    h("p", {class: "hint"}, "이름에 dev10이 든 실행은 점수판이 먼저 보여 주고, 시험하기의 '자동' 기준 실행이 됩니다."),
    h("div", {class: "pickrow"},
      h("button", {type: "button", class: "primary", onclick: () => startRun().catch(e => { J.msg.run = {text: e.message}; renderJobRun(); })}, "시작"),
      connNote()),
    jobMsg("run"));
}

async function startRun() {
  const J = S.jobs, R = J.r, o = J.opts, m = o.models.find(x => x.tag === R.model);
  if (o.status_checked && !(m && m.connected)) throw new Error("연결된 모델을 고르세요.");
  const body = {model: R.model, docs: o.docs.map(d => d.doc_id).filter(d => R.docs.has(d)), pages_dir: R.pages,
    run_name: R.name.trim(), repeat: R.repeat};
  if (!body.docs.length) throw new Error("문서를 하나 이상 고르세요.");
  let {status, data} = await post("/api/jobs/run", body);
  if (status === 409 && data.needs_confirm) {           // 서버가 요약을 돌려주면 확인 창을 띄우고 한 번 더 보낸다
    if (!window.confirm(data.summary + "\n\n이대로 시작할까요?")) return;
    ({status, data} = await post("/api/jobs/run", {...body, confirm: true}));
  }
  if (status !== 200) throw new Error(data.error || `요청 실패 (${status})`);
  J.msg.run = {ok: true, text: `시작했습니다: ${body.run_name}_r1${body.repeat > 1 ? ` ~ _r${body.repeat}` : ""}. 진행은 아래 작업 목록에 나옵니다.`};
  renderJobRun();
  await pollJobs();
}

// ── 비교표 ───────────────────────────────────────────

function renderJobCompare() {
  const J = S.jobs, C = J.c;
  const hint = "실행 여러 개를 정답 자리(실버)와 채점해 비교표 compare.md를 만듭니다. 고른 순서대로 들어갑니다. 라벨을 비우면 실행 이름이 쓰입니다.";
  const rows = runsShown().slice().reverse().map(r => {
    const on = C.picked.includes(r.name);
    return h("div", {class: "cmprow"},
      h("label", {class: "chk", "data-tip": runLabel(r)}, h("input", {type: "checkbox", checked: on, onchange: e => {
        if (e.target.checked) C.picked.push(r.name); else C.picked.splice(C.picked.indexOf(r.name), 1);
        renderJobCompare();
      }}), h("span", {class: "mono"}, r.name)),
      on ? h("span", null, h("small", null, `${C.picked.indexOf(r.name) + 1}번 `),
        h("input", {type: "text", class: "jlabel", placeholder: "라벨", value: C.labels[r.name] || "",
          oninput: e => { C.labels[r.name] = e.target.value; }})) : null);
  });
  card("jobs-compare-card", "비교표", hint,
    h("div", {class: "cmplist"}, rows.length ? rows : h("p", {class: "hint"}, "실행 목록을 불러오는 중이거나 실행이 없습니다.")),
    h("p", {class: "hint"}, `고른 실행 ${C.picked.length}개. 목록은 점수판의 '다시 읽기'를 누르면 새로 읽습니다.`),
    field("제목", h("input", {type: "text", class: "jname", value: C.title, placeholder: "예: rows_s7_v9_vs_s6",
      oninput: e => { C.title = e.target.value; }})),
    h("div", {class: "pickrow"}, h("button", {type: "button", class: "primary",
      onclick: () => startCompare().catch(e => { J.msg.cmp = {text: e.message}; renderJobCompare(); })}, "만들기")),
    jobMsg("cmp"));
}

async function startCompare() {
  const J = S.jobs, C = J.c;
  if (!C.picked.length) throw new Error("실행을 하나 이상 고르세요.");
  const labels = C.picked.map(n => (C.labels[n] || "").trim() || null);
  const {status, data} = await post("/api/jobs/compare", {title: C.title.trim(), runs: C.picked,
    labels: labels.some(Boolean) ? labels : null});
  if (status !== 200) throw new Error(data.error || `요청 실패 (${status})`);
  J.msg.cmp = {ok: true, text: "만들기 시작했습니다. 끝나면 작업 목록의 진행 칸에 compare.md 경로가 나옵니다."};
  renderJobCompare();
  await pollJobs();
}

// ── 작업 목록 ─────────────────────────────────────────

function jobStatus(j) {
  const st = j.status;
  return h("span", {class: "st-" + st, "data-tip": JOB_TIP[st] || null},
    (JOB_STATUS[st] || st) + (st === "failed" && j.returncode !== null ? ` (종료 코드 ${j.returncode})` : ""));
}

function progressText(j) {
  if (j.kind === "run" && j.progress) return j.progress.map((p, i) => `r${i + 1}: ${p.total}건 중 ${p.done}건`).join(" · ");
  if (j.kind === "compare" && j.output) return h("span", {class: "mono"}, j.output);
  return "";
}

function renderJobList() {
  const J = S.jobs;
  const hint = "이 화면에서 띄운 작업과, 다른 터미널·지난 앱에서 돌고 있는 run_sections.py·try_section.py를 보여 줍니다. 로그는 runs/manual/jobs/에 남습니다.";
  const outside = J.running.filter(r => !r.mine);
  const mark = j => j.id === J.watch || (J.log && J.log.id === j.id);
  const rows = J.list.map(j => h("tr", {class: mark(j) ? "chg" : null},
    h("td", null, JOB_KIND[j.kind] || j.kind), h("td", {"data-tip": j.command}, j.label), h("td", null, clock(j.started)),
    h("td", null, jobStatus(j)), h("td", null, progressText(j)),
    h("td", null,
      h("button", {type: "button", onclick: () => openLog(j.id).catch(fail)}, "로그"),
      j.kind === "try" ? h("button", {type: "button", onclick: () => watchTry(j.id)}, "결과") : null,
      j.stoppable ? h("button", {type: "button", class: "danger", onclick: () => stopJob(j).catch(fail)}, "멈추기") : null)));
  const ext = outside.map(r => h("tr", {class: "outside"},
    h("td", null, JOB_KIND[r.kind] || r.kind), h("td", null, [r.run_name, r.doc, r.model].filter(Boolean).join(" · ") || "—"),
    h("td", null, "—"), h("td", null, h("span", {class: "st-running"}, "돌아감 — 다른 터미널에서")), h("td", null, ""),
    h("td", {class: "mono"}, `pid ${r.pid}`)));
  const empty = !rows.length && !ext.length ? h("tr", null, h("td", {colspan: 6, class: "hint"}, "아직 작업이 없습니다.")) : null;
  card("jobs-list-card", "작업 목록", hint,
    J.pollError ? h("p", {class: "badt"}, "작업 목록을 읽지 못했습니다: " + J.pollError) : null,
    h("table", {class: "list jobs"},
      h("thead", null, h("tr", null, ["종류", "내용", "시작", "상태", "진행", ""].map(x => h("th", null, x)))),
      h("tbody", null, rows, ext, empty)),
    J.log ? h("div", {class: "logbox"},
      h("div", {class: "pickrow"}, h("b", null, "로그"), h("span", {class: "mono"}, J.log.id),
        h("button", {type: "button", onclick: () => { J.log = null; renderJobList(); }}, "닫기")),
      h("pre", {class: "log", id: "job-log", onscroll: e => {
        const el = e.target;
        Object.assign(J.log, {scroll: el.scrollTop, bottom: el.scrollTop + el.clientHeight >= el.scrollHeight - 4});
      }}, J.log.text || "(아직 비어 있음)")) : null);
  const el = document.getElementById("job-log");    // 다시 그려도 읽던 자리를 지킨다. 맨 아래였으면 새 줄을 따라간다
  if (el) el.scrollTop = J.log.bottom ? el.scrollHeight : J.log.scroll;
}

async function refreshLog() {
  const L = S.jobs.log;
  const d = await api(`/api/jobs/${encodeURIComponent(L.id)}/log?lines=400`);
  if (S.jobs.log === L) L.text = d.text;
}

async function openLog(id) {
  S.jobs.log = {id, text: "", scroll: 0, bottom: true, final: false};
  await refreshLog();
  renderJobList();
}

async function stopJob(j) {
  if (!window.confirm(`이 작업을 멈출까요?\n${j.label}\n\n돌던 문서의 결과는 남지 않을 수 있습니다.`)) return;
  const {data} = await post(`/api/jobs/${encodeURIComponent(j.id)}/stop`, {});
  status(data.stopped ? "작업을 멈췄습니다." : "멈출 작업이 없습니다(이미 끝났을 수 있습니다).");
  await pollJobs();
}

// 도는 작업이 있으면 3초마다, 없으면 15초마다 다시 읽는다
async function pollJobs() {
  const J = S.jobs;
  clearTimeout(J.timer);
  try {
    const d = await api("/api/jobs");
    Object.assign(J, {list: d.jobs, running: d.running, pollError: null});
  } catch (e) {
    J.pollError = e.message;
  }
  const w = J.watch && J.list.find(j => j.id === J.watch);
  if (w && w.status !== "running" && J.tried !== w.id) await loadResult(w.id).catch(fail);
  else if (J.watch && !J.result) renderJobResult();
  const lj = J.log && J.list.find(j => j.id === J.log.id);
  if (lj && !J.log.final) {
    await refreshLog().catch(fail);
    if (J.log) J.log.final = lj.status !== "running";
  }
  renderJobList();
  const busy = J.list.some(j => j.status === "running") || J.running.length > 0;
  J.timer = setTimeout(() => pollJobs().catch(fail), busy ? 3000 : 15000);
}

// ── 탭 ⑤ 서버 ─────────────────────────────────────────
// 모델 서버 연결, RunPod Pod, RNGD 모델을 보여 주고 바꾼다. 바꾸는 단추는 모두 두 단계다: 요약과 확인 토큰을 받고
// (/api/servers/propose) → 창에서 '확인'을 눌러야 실행한다(/api/servers/execute). 서버는 키를 보내지 않는다.

const SRV_LOG = "runs/manual/server_log.md";
const connected = () => ((S.srv.data && S.srv.data.models) || []).filter(m => m.reachable && m.match);
const stamp = d => d ? d.toTimeString().slice(0, 8) : "—";

// 지금 연결된 모델 한 줄. small이면 탭 ① 점수 카드용이고, 보고 있는 실행의 모델이 연결돼 있지 않으면 눈에 띄게 한다
function connLine(small) {
  const V = S.srv, list = connected();
  const attrs = small ? {id: "conn-now", class: "connline"} : {class: "connbig"};
  if (!V.data) return h("p", attrs, V.error ? "모델 서버 연결을 보지 못했습니다: " + V.error : "모델 서버 연결을 확인하는 중…");
  const text = list.length
    ? "지금 연결된 모델: " + list.map(m => `${m.model_expected} (${m.where}, 태그 ${m.tag})`).join(" · ")
    : "연결된 모델 없음";
  const r = small ? S.run : null;
  const off = r && r.model && !list.some(m => m.model_expected === r.model);
  if (off) attrs.class += " connwarn";
  return h("p", attrs, text, off ? ` — 이 실행의 모델(${r.model})은 지금 연결돼 있지 않습니다` : "",
    small ? h("small", null, " (서버 탭에서 바꿉니다)") : "");
}

function renderConnNow() {
  const el = document.getElementById("conn-now");
  if (el) el.replaceWith(connLine(true));
}

function renderServers() {
  renderSrvTop();
  renderSrvModels();
  renderSrvRunpod();
  renderSrvRngd();
  renderSrvLog();
}

// 실행 중이면 잠근다. 다른 서버 동작이 진행 중일 때도 잠근다
function srvBtn(label, action, params, cls) {
  const d = S.srv.data, locked = !d || d.locked || !!S.srv.busy;
  return h("button", {type: "button", class: cls || null, disabled: locked,
    "data-tip": d && d.locked ? "잠김: " + d.lock_reason : null,
    onclick: () => srvPropose(action, params, label).catch(fail)}, label);
}

function lockNote() {
  const d = S.srv.data;
  return d && d.locked ? h("p", {class: "warn"}, `잠김: ${d.lock_reason}. 실행이 끝나면 단추가 풀립니다. 돌고 있는 실행이 서버를 쓰고 있어, 지금 바꾸면 연결 오류로 실패합니다.`) : null;
}

function renderSrvTop() {
  const V = S.srv, d = V.data, R = V.result, sess = d && d.session;
  card("srv-top-card", "지금 연결된 모델", "모델 서버의 /v1/models에 물어 기대한 모델이 답하면 '연결'로 봅니다. 이 탭을 보는 동안 10초마다 다시 묻습니다.",
    connLine(false),
    lockNote(),
    V.busy ? h("p", {class: "running"}, `진행 중: ${V.busy}… (Pod 지우기·RNGD 내리기는 확인까지 5초쯤 걸립니다)`) : null,
    R ? h("div", {class: R.ok ? "srvres ok" : "srvres bad"}, h("b", null, R.text), R.detail ? h("div", null, R.detail) : null,
      R.line ? h("div", {class: "mono"}, "기록: " + R.line) : null) : null,
    sess ? h("p", null, h("b", null, `이 앱이 만든 Pod: ${sess.pod_id} `), sess.ready ? h("span", {class: "okt"}, "준비됨") : h("span", {class: "running"}, "준비 중 — 모델을 받는 중"),
      h("br"), h("small", null, "작업 탭에서 띄우는 실행·시험은 이 Pod의 주소와 키를 받습니다. 키는 이 앱의 메모리에만 있어 앱을 끄면 이 Pod를 쓸 수 없습니다. 4시간 자동 삭제 감시는 앱을 꺼도 돕니다.")) : null,
    h("div", {class: "pickrow"}, h("small", null, `마지막으로 본 시각 ${stamp(V.at)}`),
      h("button", {type: "button", onclick: () => pollServers().catch(fail)}, "지금 다시 보기")));
}

function renderSrvModels() {
  const d = S.srv.data;
  if (!d) return card("srv-models-card", "모델별 연결", null, h("p", {class: "hint"}, "불러오는 중…"));
  const yes = (v, ok, no) => v === true ? h("span", {class: "okt"}, ok) : v === false ? h("span", {class: "badt"}, no) : h("span", {class: "hint"}, "—");
  card("srv-models-card", "모델별 연결", "configs/models.yaml의 항목별 추출 태그만 봅니다(실버용 태그는 보지 않습니다). 주소와 키는 .env에서 읽습니다. 앱이 Pod를 만들었으면 RunPod 태그는 그 Pod를 봅니다.",
    h("table", {class: "list"},
      h("thead", null, h("tr", null, ["태그", "기대 모델", "서버", "주소 설정", "응답", "서버가 말한 모델", "일치"].map(x => h("th", null, x)))),
      h("tbody", null, d.models.map(m => h("tr", null,
        h("td", {class: "mono"}, m.tag), h("td", {class: "mono"}, m.model_expected), h("td", null, m.where),
        h("td", null, m.url_set ? "있음" : h("span", {class: "hint"}, "없음 (.env)")),
        h("td", null, m.url_set ? yes(m.reachable, "응답함", "응답 없음" + (m.error ? ` (${m.error})` : "")) : h("span", {class: "hint"}, "—")),
        h("td", {class: "mono"}, m.model_served || "—"),
        h("td", null, yes(m.match, "일치", "다름")))))));
}

function renderSrvRunpod() {
  const d = S.srv.data;
  const hint = "RunPod 계정의 Pod 목록입니다. 켜져 있는 동안 시간당 요금이 붙습니다. 이 도구가 만든 Pod는 이름이 to21-b-로 시작합니다.";
  if (!d) return card("srv-runpod-card", "RunPod", hint, h("p", {class: "hint"}, "불러오는 중…"));
  const money = v => num(v) ? "$" + v.toFixed(2) : "—";
  const rows = d.pods.map(p => h("tr", {class: p.ours ? null : "notours"},
    h("td", {class: "mono"}, p.id),
    h("td", null, p.name || "—", p.ours ? null : h("small", {"data-tip": "다른 사람이 쓰는 Pod일 수 있습니다. 지우기 전에 확인하세요."}, " (이 도구가 만든 것이 아님)")),
    h("td", null, p.state ? h("span", {class: p.state === "준비됨" ? "okt" : "running"}, p.state) : (p.status || "—"),
      num(p.auto_delete_min) ? h("small", null, ` · 자동 삭제까지 ${p.auto_delete_min}분`) : null),
    h("td", {class: "num"}, money(p.cost_per_hr)), h("td", {class: "num"}, num(p.minutes) ? Math.round(p.minutes) + "분" : "—"),
    h("td", {class: "num"}, money(p.est_cost)),
    h("td", null, srvBtn("지우기", "pod_delete", {pod_id: p.id}, "danger"))));
  card("srv-runpod-card", "RunPod", hint,
    d.runpod_error ? h("p", {class: "badt"}, "RunPod을 보지 못했습니다: " + d.runpod_error) : null,
    h("table", {class: "list"},
      h("thead", null, h("tr", null, ["Pod", "이름", "상태", "시간당", "켜진 시간", "추정 비용", ""].map(x => h("th", null, x)))),
      h("tbody", null, rows.length ? rows : h("tr", null, h("td", {colspan: 7, class: "hint"}, d.runpod_error ? "—" : "켜진 Pod가 없습니다.")))),
    h("p", {class: "hint"}, num(d.volumes) ? `네트워크 볼륨 ${d.volumes}개${d.volumes ? " — 볼륨도 쓰지 않는 동안 요금이 붙습니다" : ""}` : "네트워크 볼륨 수를 보지 못했습니다"),
    h("div", {class: "srvbtns"}, srvBtn("Pod 만들기(Qwen3.6)", "pod_create", {}, "primary")));
}

function renderSrvRngd() {
  const d = S.srv.data;
  const hint = "사내 RNGD 장비(카드 4장)의 furiosa-llm 서버입니다. 카드가 4장뿐이라 모델을 번갈아 띄웁니다. 아래 글은 furiosa-smi ps 출력이고 --api-key 값은 ***로 가립니다.";
  if (!d) return card("srv-rngd-card", "RNGD", hint, h("p", {class: "hint"}, "불러오는 중…"));
  const g = d.rngd || {};
  card("srv-rngd-card", "RNGD", hint,
    g.ok ? null : h("p", {class: "badt"}, "RNGD를 보지 못했습니다: " + (g.error || "알 수 없음"),
      g.error === "RNGD_SSH 없음" ? h("small", null, " (.env의 RNGD_SSH에 ssh 접속 인자를 넣고 앱을 다시 켜세요)") : null),
    g.ok ? h("div", null, h("b", null, "떠 있는 모델"),
      g.models.length ? h("ul", null, g.models.map(m => h("li", null, h("span", {class: "mono"}, `${m.model} (pid ${m.pid}) `),
        srvBtn("내리기", "rngd_down", {model: m.model}, "danger")))) : h("p", {class: "hint"}, "떠 있는 모델이 없습니다.")) : null,
    h("div", {class: "srvbtns"}, (d.rngd_choices || []).map(c => srvBtn(`${c.label} 올리기(${c.cards}장)`, "rngd_up", {tag: c.tag}))),
    g.ok && g.text ? h("details", null, h("summary", null, "furiosa-smi ps 글 보기"), h("pre", {class: "log"}, g.text)) : null);
}

function renderSrvLog() {
  const d = S.srv.data, rows = (d && d.log_tail) || [];
  card("srv-log-card", "서버 기록", `Pod 만들기·지우기와 RNGD 올리기·내리기를 ${SRV_LOG}에 한 줄씩 남깁니다. 키는 남기지 않습니다. 마지막 10줄입니다.`,
    rows.length ? h("pre", {class: "log"}, rows.join("\n")) : h("p", {class: "hint"}, "아직 기록이 없습니다."),
    h("p", {class: "warn"}, "이 줄을 docs/plan/RunPod_사용기록.md에 옮기세요. 앱은 docs/ 아래에 쓰지 않습니다(하네스가 지키는 폴더)."));
}

// 1단계: 요약과 확인 토큰을 받아 창을 띄운다
async function srvPropose(action, params, label) {
  const V = S.srv;
  V.busy = label + " 요약 받는 중";
  renderServers();
  try {
    const {status, data} = await post("/api/servers/propose", {action, params});
    if (status !== 200) {
      V.result = {ok: false, text: `${label}: ${data.error || "요청 실패 (" + status + ")"}`, detail: data.lock_reason ? "잠김: " + data.lock_reason : null};
      return;
    }
    openSrvDialog({label, ...data});
  } finally {
    V.busy = null;
    renderServers();
  }
}

// 창의 '확인'은 이 창의 토큰(P)만 쓴다. 그만두기·Esc로 닫으면 토큰은 쓰이지 않고 10분 뒤 버려진다
function openSrvDialog(P) {
  const dlg = document.getElementById("srv-dialog");
  dlg.replaceChildren(...[
    h("h2", null, P.label),
    h("p", null, P.summary),
    P.warning ? h("p", {class: "warn"}, "주의: " + P.warning) : null,
    h("p", {class: "hint"}, `'확인'을 누르면 바로 실행합니다. 이 확인은 ${Math.round(P.expires_in / 60)}분 동안만 쓸 수 있고, 한 번 쓰면 끝납니다.`),
    h("div", {class: "pickrow"},
      h("button", {type: "button", onclick: closeSrvDialog}, "그만두기"),
      h("button", {type: "button", class: "confirm", onclick: () => srvExecute(P).catch(fail)}, "확인"))].filter(Boolean));
  if (!dlg.open) dlg.showModal();
}

function closeSrvDialog() {
  const dlg = document.getElementById("srv-dialog");
  if (dlg.open) dlg.close();
}

function srvDetail(action, r) {
  if (!r) return null;
  if (action === "pod_create") return `Pod ${r.pod_id}를 만들었습니다. 모델이 뜨면 RunPod 표의 상태가 '준비됨'으로 바뀝니다. `
    + (r.watchdog ? "4시간 뒤 자동으로 지웁니다." : "자동 삭제 감시를 띄우지 못했습니다. 다 쓰면 직접 지우세요.");
  if (action === "pod_delete") return r.gone ? `Pod ${r.pod_id}를 지웠습니다. 남은 Pod ${r.remaining.length}개.`
    : `지운 뒤에도 목록에 ${r.pod_id}가 남아 있습니다. 잠시 뒤 다시 보세요.`;
  if (action === "rngd_up") return r.started ? "프로세스가 떴습니다. 모델을 읽는 데 15~25분 걸립니다. 모델별 연결 표의 '응답'이 초록이 되면 씁니다."
    : "올리지 못했습니다: " + (r.error || "프로세스를 찾지 못함");
  if (action === "rngd_down") return `멈춘 pid ${r.killed.join(", ") || "없음"}` + (r.remaining.length ? ` · 아직 남은 pid ${r.remaining.join(", ")}` : "");
  return null;
}

// 2단계: 확인 토큰으로 실행한다
async function srvExecute(P) {
  const V = S.srv;
  closeSrvDialog();
  V.busy = P.label;
  renderServers();
  try {
    const {status, data} = await post("/api/servers/execute", {token: P.token});
    V.result = {ok: status === 200 && data.ok, line: data.log_line || null,
      text: `${P.label}: ` + (status === 200 && data.ok ? "끝났습니다." : (data.error || (status === 200 ? "확인하지 못했습니다." : `요청 실패 (${status})`))),
      detail: srvDetail(P.action, data.result) || (data.lock_reason ? "잠김: " + data.lock_reason : null)};
  } finally {
    V.busy = null;
    await pollServers();
  }
}

// 서버 탭을 보는 동안 10초마다, 아니면 60초마다 다시 본다(탭 ① 점수 카드의 한 줄도 같이 고친다)
async function pollServers() {
  const V = S.srv;
  clearTimeout(V.timer);
  V.started = true;
  try {
    V.data = await api("/api/servers");
    V.error = null;
    V.at = new Date();
  } catch (e) {
    V.error = e.message;
  }
  renderServers();
  renderConnNow();
  const on = document.getElementById("tab-servers").classList.contains("on");
  V.timer = setTimeout(() => pollServers().catch(fail), on ? 10000 : 60000);
}

// ── 시작 ───────────────────────────────────────────────

setupTabs();
setupTip();
loadAll().catch(fail);
initJobs().catch(e => { S.jobs.error = e.message; renderJobs(); });
renderServers();
pollServers().catch(fail);
