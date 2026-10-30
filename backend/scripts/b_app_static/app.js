"use strict";
// B 작업 화면 (역할 B, 개발 전용, ADR-025). 이 화면의 서버(/api/...)만 부른다. 외부 주소는 부르지 않는다.
// 글은 모두 글자 노드로 넣는다(결과 값에 어떤 글자가 들어 있어도 화면 코드가 되지 않게).

const S = {list: [], criteria: null, gaps: [], limit: 300, name: null, run: null, open: null, pick: loadPick(),
  diff: {a: null, b: null, key: null, data: null, error: null, why: new Set(), vals: new Set(), open: new Set(), prompts: {}}};
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
  if (!r) return card("now-card", "지금 점수", null, top, h("p", null, "점수를 낸 실행이 아직 없습니다."));
  const pass = S.criteria.pass_score;
  const mustTotal = r.must_total || S.criteria.items.filter(i => i.level === "필수").length;
  const must = r.must_passed || 0;
  const na = r.weighted_na_excluded, diff = num(na) && num(r.weighted) ? na - r.weighted : null;
  card("now-card", "지금 점수",
    "가장 최근 개발용 10건 본 실행(이름에 dev10)을 먼저 보여 줍니다. 위 상자에서 다른 실행을 고를 수 있습니다.",
    top,
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

// ── 시작 ───────────────────────────────────────────────

setupTabs();
setupTip();
loadAll().catch(fail);
