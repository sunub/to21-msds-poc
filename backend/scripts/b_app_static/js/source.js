"use strict";

// 같은 문제를 다시 연 안내에서도 실제 값 선택으로 근거 사건을 낼 수 있다.
on("problem_opened", () => {S.source.emitted.clear();});

// 원문과 선택 값은 메모리에만 둔다. 다른 화면에는 S.focus로 넘긴다.
S.source = {run: null, doc: null, raw: false, override: null, list: [], initialized: false,
  data: null, error: null, locked: null, loading: false, request: 0, pending: null, cacheKey: null,
  section: null, item: null, page: null, selection: null, line: {}, values: {}, sections: {},
  selectedLines: new Set(), selectedPaths: new Set(), open: new Set(), emitted: new Set(),
  filter: "all", gone: false, draw: null, scroll: {}, problemData: new Map(), problemKey: null,
  problemErrors: new Map(), problemRequest: 0, choice: 0, problemScroll: 0, problemScope: null};
const SOURCE_VIEWS = {"source-top": sourceRenderTop, "source-values": sourceRenderProblems,
  "source-page": sourceRenderPage, "source-selection": sourceRenderSelection};
for (const [id, render] of Object.entries(SOURCE_VIEWS)) {
  shellDefineView(id, {render, ...(id === "source-top" ? {load: sourceEnsure} : {})});
}
on("context_changed", async () => {
  // 전역 묶음 변경은 실행 당시 원문 묶음을 덮어쓰지 않는다. 정답지는 항상 다시 읽는다.
  if (S.source.initialized) {
    await Promise.all([sourceLoad(true), S.score.pending]);
    sourceRenderProblems();
  }
});

function sourceRunDocs(run = S.source.run) {
  const record = S.source.list.find(item => item.name === run);
  return [...new Set([...(record?.docs || []), ...(record?.no_gold || [])])];
}
function sourceSet() {
  return S.shell.sets.find(item => item.id === (S.source.override || S.source.data?.set?.id || S.ctx.set));
}
function sourceLock(doc) {
  const entries = S.shell.sets.flatMap(set => set.docs || []).filter(item => item.doc_id === doc);
  // 문서가 여러 판에 있더라도 평가용이라는 사실을 우선한다.
  return entries.find(item => item.group === "eval") || entries.find(item => item.locked);
}
function sourceDocs() {
  return S.source.raw ? (sourceSet()?.docs || []).filter(item => !item.locked && item.group !== "eval").map(item => item.doc_id)
    : sourceRunDocs().filter(id => !sourceLock(id));
}
function sourceLabel(no) {
  return no == null ? T("source.labels.unknown_section") : T("source.labels.section_name", {
    section: no, name: UI.source.section_names[no] || T("source.labels.unknown_section")});
}
function sourceButton(id, text, action, attrs = {}) {
  return h("button", {id, type: "button", onclick: action, ...attrs}, text);
}
function sourceDetails(title, ...kids) {
  return h("details", null, h("summary", null, title), ...kids);
}
function sourceSelect(id, label, options, selected, action) {
  const select = h("select", {id, onchange: event => action(event.target.value)}, options.map(item =>
    h("option", {value: item.id, disabled: item.disabled, selected: item.id === selected}, item.label)));
  select.value = selected ?? "";
  return h("div", null, h("label", {for: id}, label), select);
}
function sourceResetSelection() {
  Object.assign(S.source, {selection: null, page: null, gone: false, filter: "all", scroll: {}});
  S.source.selectedLines.clear(); S.source.selectedPaths.clear(); S.source.open.clear();
}
async function sourceEnsure(args = {}) {
  const D = S.source, navigation = S.shell.navigation;
  if (!S.shell.contextLoaded) {
    await (S.shell.contextReady || shellLoadContext());
  }
  if (navigation !== S.shell.navigation) return;
  if (S.score?.list?.length || D.usingScoreList) { D.list = S.score.list; D.usingScoreList = true; }
  else if (!D.initialized) {
    D.loading = true; D.error = null; sourceRenderTop();
    try {
      const result = await api(ctxUrl("/api/runs"));
      if (navigation !== S.shell.navigation) return;
      D.list = result.runs || []; D.run = result.current || null;
    } catch (error) {
      if (navigation === S.shell.navigation) { D.error = error; D.data = null; }
      return;
    } finally { D.loading = false; sourceRenderTop(); }
  }
  const incoming = Object.keys(args).length ? args : !D.initialized ? S.focus : {};
  const explicitRun = Object.hasOwn(incoming, "run");
  const run = explicitRun ? incoming.run : D.initialized ? D.run : S.score?.name || D.run;
  const changedRun = run !== D.run;
  if (changedRun || !D.initialized) D.override = null;
  D.run = run; D.raw = explicitRun ? !run : D.raw;
  if (D.raw && Object.hasOwn(incoming, "set")) D.override = incoming.set;
  if (!D.raw && !D.list.some(item => item.name === D.run)) D.run = D.list.at(-1)?.name || null;
  if (Object.hasOwn(incoming, "doc")) D.doc = incoming.doc;
  else if (changedRun || !sourceDocs().includes(D.doc)) D.doc = sourceDocs()[0] || null;
  if (Object.keys(incoming).length) {
    D.section = incoming.section ?? null; D.item = incoming.item ?? null;
  }
  D.initialized = true;
  const loading = sourceLoad(false), request = D.request, choice = D.choice, key = S.ctx.key;
  const valid = () => navigation === S.shell.navigation && request === D.request && choice === D.choice && key === S.ctx.key && D.data;
  await loading;
  if (!valid()) return;
  await sourceLoadProblems();
  if (!valid()) return;
  if (Object.hasOwn(incoming, "path") && incoming.path) {
    const only = incoming.kind === "missing" || incoming.estimated === true;
    const v = only ? D.data.silver_only.find(x => x.path === incoming.path) : D.values[incoming.path];
    if (v) sourcePick(v, only ? "silver_only" : "result", false);
    else { sourceResetSelection(); D.gone = true; sourceGoSection(D.section); }
  } else if (incoming.pick) {
    const entries = sourceProblems();
    const found = sourceChooseProblem(entries, incoming.pick);
    if (found) sourcePick(found.v, found.only ? "silver_only" : "result", false);
    else { sourceResetSelection(); sourceGoSection(D.section); }
  } else if (incoming.section != null) sourceGoSection(D.section);
}
function sourceHasEvidence(v, data = S.source.data) {
  return (v.lines || []).some(id => data?.lines.some(line => line.id === id && data.pages.includes(line.page)));
}
function sourceChooseProblem(entries, pick = "mismatch", data = S.source.data) {
  const kinds = pick === "mismatch" ? ["wrong", "made", "missing"] : [pick];
  return kinds.map(kind => entries.find(entry => entry.kind === kind && !entry.only && sourceHasEvidence(entry.v, data))
    || entries.find(entry => entry.kind === kind)).find(Boolean);
}
function sourceProblemDocs() {
  const D = S.source, top = S.score?.run?.name === D.run ? S.score.run.status_text?.top_problem : null;
  if (D.item && top?.name === D.item) D.problemScope = {run: D.run, item: D.item, docs: top.docs?.map(doc => doc.doc_id) || []};
  const docs = D.item && D.problemScope?.run === D.run && D.problemScope.item === D.item ? D.problemScope.docs : [D.doc];
  return [...new Set(docs)].filter(doc => doc && sourceRunDocs().includes(doc) && !sourceLock(doc));
}
function sourceDocUrl(doc) {
  const params = new URLSearchParams({doc});
  if (S.source.run) params.set("run", S.source.run);
  if (S.source.override) params.set("set", S.source.override);
  return ctxUrl(`/api/doc?${params}`);
}
async function sourceLoadProblems(force = false) {
  const D = S.source, docs = sourceProblemDocs();
  const key = JSON.stringify([D.run, D.override, S.ctx.key, D.item, D.section, docs]);
  if (!force && D.problemKey === key) { sourceRenderProblems(); return; }
  D.problemKey = key; D.problemData.clear(); D.problemErrors.clear();
  const request = ++D.problemRequest;
  if (!D.data || !D.run || !D.item) { sourceRenderProblems(); return; }
  if (docs.includes(D.doc)) D.problemData.set(D.doc, D.data);
  const others = docs.filter(doc => doc !== D.doc);
  const results = await Promise.allSettled(others.map(sourceDocUrl).map(path => api(path)));
  if (request !== D.problemRequest || key !== D.problemKey) return;
  results.forEach((result, i) => {
    if (result.status === "fulfilled") D.problemData.set(others[i], result.value);
    else D.problemErrors.set(others[i], result.reason);
  });
  sourceRenderProblems();
}
function sourceLoad(force = false) {
  const D = S.source, cacheKey = JSON.stringify([D.run, D.doc, D.override, S.ctx.key]);
  if (!force && D.cacheKey === cacheKey) return D.pending || Promise.resolve();
  const priorDoc = D.data?.doc_id, priorRun = D.loadedRun, priorSelection = D.selection, priorPage = D.page;
  const keep = priorDoc === D.doc && priorRun === D.run;
  const request = ++D.request, key = S.ctx.key;
  // 정답·묶음 변경이나 새 문서 요청 뒤에는 앞 요청의 목록을 덮어쓰지 않는다.
  ++D.problemRequest; D.problemKey = null; D.problemData.clear(); D.problemErrors.clear();
  D.cacheKey = cacheKey; D.data = null; D.error = null; D.locked = sourceLock(D.doc); D.draw = null;
  if (!keep) sourceResetSelection();
  D.absent = !!D.doc && !sourceDocs().includes(D.doc);
  D.loading = !!D.doc && !D.locked && !D.absent;
  sourceRenderAll();
  const work = (async () => {
    if (!D.doc || D.locked || D.absent) return;
    try {
      const data = await api(sourceDocUrl(D.doc));
      if (request !== D.request || key !== S.ctx.key) return;
      sourcePrepare(data); D.loadedRun = D.run;
      if (keep) {
        if (data.pages.includes(priorPage)) D.page = priorPage;
        if (priorSelection?.path) {
          const v = priorSelection.side === "silver_only" ? data.silver_only.find(x => x.path === priorSelection.path) : D.values[priorSelection.path];
          if (v) sourceSelectValue(v, priorSelection.side);
          else { sourceResetSelection(); D.gone = true; }
        }
      }
    } catch (error) { if (request === D.request) D.error = error; }
    finally {
      if (request === D.request) { D.loading = false; sourceRenderAll(); }
    }
    if (request === D.request && D.data) await sourceLoadProblems();
  })();
  D.pending = work; return work;
}
function sourcePrepare(data) {
  const D = S.source; D.data = data;
  D.line = Object.fromEntries(data.lines.map(line => [line.id, line]));
  D.values = Object.fromEntries(data.values.map(value => [value.path, value]));
  D.page = data.pages[0] ?? null; D.sections = {};
  const positions = Object.fromEntries(data.lines.map((line, i) => [line.id, i]));
  for (const [section, span] of Object.entries(data.sections)) {
    if (!(span.start in positions) || !(span.end in positions)) continue;
    for (let i = positions[span.start]; i <= positions[span.end]; i++) D.sections[data.lines[i].id] = +section;
  }
}
function sourceRenderAll() { for (const render of Object.values(SOURCE_VIEWS)) render(); }
function sourceChangeTarget(kind, value) {
  const D = S.source;
  if (kind === "run") { D.run = value || null; D.raw = !value; D.override = D.raw ? S.ctx.set : null; D.doc = sourceDocs()[0] || null; }
  if (kind === "doc") D.doc = value;
  if (kind === "set") D.override = value || null;
  sourceResetSelection();
  if (kind === "run") { D.section = null; D.item = null; }
  return sourceLoad(true);
}
async function sourceReload() {
  if (!S.source.initialized) { await sourceEnsure(); sourceRenderAll(); }
  else await sourceLoad(true);
}
function sourceRaw() {
  const D = S.source;
  D.raw = true; D.run = null; D.override = S.ctx.set;
  D.doc = sourceDocs()[0] || null; D.section = null; D.item = null; sourceResetSelection();
  return sourceLoad(true);
}
function sourceRenderTop() {
  const D = S.source, d = D.data, el = document.getElementById("source-top");
  el.setAttribute("aria-busy", String(D.loading));
  const controls = sourceDetails(T("source.selection.expand"),
    h("div", {class: "source-controls"},
      sourceSelect("source-run-select", T("source.labels.run"), [
        {id: "", label: T("source.selection.raw")},
        ...D.list.filter(item => !item.error).map(item => ({id: item.name, label: item.label?.title || item.name}))
      ], D.run, value => sourceChangeTarget("run", value)),
      sourceSelect("source-doc-select", T("source.labels.doc"), sourceDocs().map(id => ({id, label: id})), D.doc,
        value => sourceChangeTarget("doc", value)),
      sourceSelect("source-section-choice", T("source.labels.section"), [
        {id: "", label: T("source.labels.choose_scope")},
        ...Array.from({length: 16}, (_, i) => ({id: String(i + 1), label: sourceLabel(i + 1)}))
      ], String(D.section ?? ""), value => sourceChooseSection(value ? +value : null)),
      sourceSelect("source-set-select", T("source.selection.source_set"), [
        {id: "", label: T("source.labels.return_set")},
        ...S.shell.sets.map(set => ({id: set.id, label: set.label, disabled: !set.usable}))
      ], D.override, value => sourceChangeTarget("set", value))),
    sourceButton("source-raw-open", T("source.selection.raw"), sourceRaw),
    sourceDetails(T("source.selection.eval_reason"), S.shell.sets.map(set => h("div", null,
      h("p", null, set.label, set.reason ? ` — ${set.reason}` : ""),
      h("p", null, T("source.locked.counts", {dev: set.counts?.dev ?? 0, locked: set.counts?.eval_locked ?? 0, outside: set.counts?.outside ?? 0})),
      (set.docs || []).filter(doc => doc.locked).map(doc => h("p", {class: "raw"}, doc.doc_id, " — ", doc.reason))))));
  const basis = d ? h("div", {class: "source-basis"},
    h("p", null, T("source.selection.source_set"), ": ", h("strong", null, d.set?.label || T("context.unavailable"))),
    h("p", null, UI.source.origin[d.set?.source] || T("context.unavailable"), d.set?.note ? ` — ${d.set.note}` : ""),
    h("p", null, T("source.selection.next_set"), ": ", S.shell.sets.find(set => set.id === S.ctx.set)?.label || T("context.unavailable")),
    h("p", null, T("source.labels.answer"), ": ", shellKeyLabel(d.key)),
    shellKeyMismatch(d.key) ? h("p", {class: "answer-mismatch"}, shellKeyMismatch(d.key)) : null) : null;
  let state = null;
  if (D.loading) state = h("p", {role: "status"}, T("source.loading"));
  else if (D.locked) state = h("div", {class: "source-state", role: "status"},
    h("strong", null, T("source.locked.title")), h("p", null, D.locked.reason), h("p", null, T("errors.eval_locked.todo")));
  else if (D.error?.status === 404 || D.absent || (!D.doc && !D.error)) state = h("p", {class: "source-state"}, T(D.doc || D.run ? "source.empty.document" : "source.empty.runs"));
  else if (D.error) state = friendlyError({message: T("source.load_failed.fact"), fix: T("source.load_failed.todo"), raw: D.error.message});
  const legend = d ? h("div", {class: "source-legend"}, (d.legend || []).map(entry => h("span", {class: "source-legend-entry"},
    h("span", {class: "source-chip", "aria-hidden": "true", style: `background:${entry.color}`}), entry.label))) : null;
  const failed = !!D.error || !!D.locked || D.absent;
  shellConclusion("s02", T(D.loading ? "source.loading" : D.locked ? "source.locked.title" : D.error?.status === 404 || D.absent
    ? "source.empty.document" : D.error ? "source.load_failed.fact" : "source.title"), !failed && !D.loading);
  controls.open = !D.section || D.open.has("controls");
  controls.addEventListener("toggle", () => { if (controls.isConnected) sourceOpen("controls", controls.open); });
  coreReplace(controls, controls.querySelector("summary"), ...Array.from(controls.children).slice(1),
    h("p", {class: "technical"}, D.run || T("source.raw.title"), D.doc ? ` / ${D.doc}` : ""), basis,
    sourceButton("source-reload", T("source.reload"), sourceReload),
    d ? h("p", null, d.ui_text?.howto || T("source.doc.howto")) : null, legend,
    d?.warnings?.map(warning => h("p", {class: "source-warning page-text"}, warning)),
    d && D.run && !d.has_gold ? h("p", null, T("source.empty.answer")) : null);
  coreReplace(el, state, !D.section ? h("p", null, T("source.labels.choose_scope")) : null, controls);
}
function sourceKind(v, only = false, data = S.source.data) {
  if (only) return "missing";
  if (!data?.has_gold) return "uncompared";
  return v.silver?.same === true ? "same" : v.silver?.value == null ? "made" : "wrong";
}
function sourceProblems(d = S.source.data, D = S.source) {
  if (!d || !D.run || !d.has_gold) return [];
  return [...d.values.map(v => ({v, only: false, kind: sourceKind(v, false, d)})),
    ...d.silver_only.map(v => ({v, only: true, kind: "missing"}))]
    .filter(({v, kind}) => kind !== "same" && (!D.item || (v.items || []).includes(D.item))
      && (D.section == null || v.section === +D.section));
}
function sourceRenderProblems() {
  document.getElementById("source-values").setAttribute("data-guide", "s02-diff-values");
  const D = S.source, el = document.getElementById("source-values");
  const previous = document.getElementById("source-problem-list");
  if (previous) D.problemScroll = previous.scrollTop || 0;
  if (!D.data || (!D.section && !D.item)) { el.replaceChildren(); return; }
  const docs = sourceProblemDocs();
  const groups = docs.map(doc => ({doc, data: doc === D.doc ? D.data : D.problemData.get(doc)}));
  const entries = groups.flatMap(({doc, data}) => data ? sourceProblems(data).map(entry => ({...entry, doc, data})) : []);
  const top = S.score?.run?.name === D.run ? S.score.run.status_text?.top_problem : null;
  const counts = top?.name === D.item ? top.counts : null;
  coreReplace(el, h("h2", null, T("source.problem_count", {count: docs.length})),
    D.item ? h("p", {class: "issue-meta"}, T("source.labels.criterion", {item: D.item})) : null,
    D.section === 8 ? h("p", {class: "muted"}, term("exposure"), " — ", term("concentration_unit", T("source.unit_first_use"))) : null,
    h("div", {class: "source-filters"}, ["all", "missing", "made", "wrong"].map(kind =>
      sourceButton(`source-filter-${kind}`, kind === "all" ? T("source.filter.all_values")
        : num(counts?.[UI.score.cause_keys[kind]]) ? T(`source.filter.${kind}`, {count: counts[UI.score.cause_keys[kind]]})
        : `${T(`source.kinds.${kind}`)} · ${T("common.legacy.cell_labels.c_none")}`,
        () => { D.filter = kind; sourceRenderProblems(); document.getElementById(`source-filter-${kind}`).focus(); }, {"aria-pressed": String(D.filter === kind)}))),
    h("div", {id: "source-problem-list"}, groups.map(({doc, data}) => {
      const filtered = entries.filter(entry => entry.doc === doc && (D.filter === "all" || entry.kind === D.filter));
      if (!filtered.length && !D.problemErrors.has(doc)) return null;
      return h("section", {"data-problem-doc": doc}, h("h3", {class: "source-document"}, doc),
        D.problemErrors.has(doc) ? friendlyError({message: T("source.load_failed.fact"), fix: T("source.load_failed.todo"), raw: D.problemErrors.get(doc).message}) : null,
        filtered.map(({v, only, kind}) => {
          const selected = D.doc === doc && D.selection?.path === v.path && (D.selection.side === "silver_only") === only;
          return sourceButton(null, [h("span", {class: "issue-meta"}, sourceFieldName(v, data)),
        h("strong", {class: "big-value"}, T(`source.kinds.${kind}`), " · ", v.text || T("common.none")),
        h("span", {class: "source-selected-label"}, selected ? T("source.labels.selected") : "")],
        () => sourcePickProblem(doc, v, only),
        {class: "source-problem", "data-problem-path": v.path, "aria-pressed": String(selected)});
        }));
    })),
    !entries.some(entry => D.filter === "all" || entry.kind === D.filter) ? h("p", null, T("source.empty.problems")) : null);
  document.getElementById("source-problem-list").scrollTop = D.problemScroll;
}
function sourceFieldName(v, data = S.source.data) {
  return data?.ui_text?.value_field_labels?.[v.field] || UI.source.field_names[v.field]
    || UI.source.fields[v.field] || UI.source.table_names[v.table] || T("source.labels.field");
}
async function sourcePickProblem(doc, v, only) {
  const D = S.source, filter = D.filter, key = S.ctx.key, choice = ++D.choice;
  if (doc !== D.doc) {
    D.doc = doc;
    const loading = sourceLoad(), request = D.request;
    await loading;
    if (D.doc !== doc || !D.data || request !== D.request || key !== S.ctx.key || choice !== D.choice) return;
    D.filter = filter;
  }
  const current = only ? D.data.silver_only.find(value => value.path === v.path) : D.values[v.path];
  if (current) sourcePick(current, only ? "silver_only" : "result");
}
function sourceTip(v, side) {
  return S.source.data.ui_text?.value_tips?.[side]?.[v.path]?.join("\n") || null;
}
function sourceValueButton(v, side) {
  const only = side === "silver_only", silver = side === "silver", kind = sourceKind(v, only);
  const state = kind === "same" ? "same" : kind === "missing" ? "missing" : "different";
  return sourceButton(null, [h("span", {class: "big-value"}, (silver ? v.silver?.text : v.text) ?? T("common.none")),
    h("small", {class: "source-cell-state"}, kind === "uncompared" ? T("source.kinds.uncompared") : T(`source.legend.${state}`))],
    () => sourcePick(v, side), {class: `source-value source-${kind}`, "data-source-path": v.path, "data-side": side,
      "data-tip": sourceTip(v, side), "aria-pressed": "false"});
}
function sourceStructure() {
  const D = S.source, d = D.data, groups = new Map();
  for (const [only, values] of [[false, d.values], [true, d.silver_only]]) {
    for (const v of values) {
      const section = v.section ?? "?";
      if (!groups.has(section)) groups.set(section, new Map());
      const tables = groups.get(section);
      if (!tables.has(v.table)) tables.set(v.table, new Map());
      const row = only && v.pair_row != null ? `r${v.pair_row}` : `${only ? "s" : "r"}${v.row ?? ""}`;
      const rows = tables.get(v.table);
      if (!rows.has(row)) rows.set(row, []);
      rows.get(row).push({v, only});
    }
  }
  const sections = [...groups].sort(([a], [b]) => (a === "?" ? 99 : +a) - (b === "?" ? 99 : +b)).map(([section, tables]) => {
    const body = [...tables].map(([table, rows]) => sourceTable(section, table, rows));
    return h("details", {"data-source-section": section, open: D.open.has(`s${section}`),
      ontoggle: event => sourceOpen(`s${section}`, event.target.open)},
      h("summary", null, sourceLabel(section === "?" ? null : section),
        h("small", {class: "source-section-summary"}, d.ui_text?.sections?.[section] || "")), body);
  });
  const detail = sourceDetails(T("source.structure.expand"), sections);
  detail.open = D.open.has("structure"); detail.addEventListener("toggle", event => sourceOpen("structure", event.target.open));
  return detail;
}
function sourceTable(section, table, rows) {
  const D = S.source;
  const body = [...rows].flatMap(([row, entries]) => {
    const heading = row.length > 1 ? h("tr", null, h("th", {colspan: 3, scope: "rowgroup"},
      T(row[0] === "s" ? "source.labels.only_row" : "source.labels.row", {row: +row.slice(1) + 1}))) : null;
    return [heading, ...entries.map(({v, only}) => h("tr", null,
      h("th", {scope: "row", class: "technical"}, sourceFieldName(v),
        h("small", {class: "raw"}, v.field || "", " · ", v.path)),
      h("td", null, only ? T("common.none") : sourceValueButton(v, "result")),
      h("td", null, sourceValueButton(v, only ? "silver_only" : "silver"))))];
  });
  return h("details", {open: D.open.has(`s${section}|${table}`),
    ontoggle: event => sourceOpen(`s${section}|${table}`, event.target.open)},
    h("summary", null, UI.source.table_names[table] || table, h("span", {class: "raw"}, ` (${table}) `),
      T("source.labels.cells", {count: [...rows.values()].flat().length})),
    h("table", null, h("thead", null, h("tr", null,
      ["field", "result", "answer"].map(key => h("th", {scope: "col"}, T(`source.labels.${key}`))))),
      h("tbody", null, body)));
}

function sourceOpen(key, open) { open ? S.source.open.add(key) : S.source.open.delete(key); }
function sourceSelectValue(v, side) {
  const D = S.source, only = side === "silver_only";
  D.selection = {path: v.path, side}; D.section = v.section ?? D.section;
  D.selectedPaths = new Set(only ? [] : [v.path]);
  D.selectedLines = new Set((v.lines || []).filter(id => D.line[id]));
  const first = (v.lines || []).map(id => D.line[id]).find(line => line && D.data.pages.includes(line.page));
  if (first) D.page = first.page;
  D.gone = false;
}
function sourceSelected() {
  const D = S.source;
  return D.selection?.side === "silver_only" ? D.data?.silver_only.find(v => v.path === D.selection.path)
    : D.values[D.selection?.path];
}
function sourcePick(v, side = "result", user = true) {
  const D = S.source, oldPage = D.page;
  if (user) ++D.choice;
  sourceSelectValue(v, side);
  if (oldPage !== D.page) sourceRenderPage();
  sourceRenderTop(); sourceRenderSelection(); sourceRenderProblems(); sourceMark(); sourceRemember();
  sourceScrollLine([...D.selectedLines].find(id => D.line[id].page === D.page));
  if (user) {
    const problem = [...document.querySelectorAll("[data-problem-path]")].find(button =>
      button.dataset.problemPath === v.path && button.closest("[data-problem-doc]")?.dataset.problemDoc === D.doc &&
      button.getAttribute("aria-pressed") === "true");
    // 목록 선택 뒤 숨겨진 상세 표의 단추로 초점을 보내지 않는다.
    const button = problem || sourceValueElement(v.path, side);
    let visible = true;
    for (let parent = button?.parentElement; parent; parent = parent.parentElement) {
      if (parent.hidden || (parent.tagName?.toLowerCase() === "details" && !parent.open)) visible = false;
    }
    if (visible) button?.focus({preventScroll: true});
    if (side !== "silver_only") sourceEvidence(v);
  }
}
function sourceValueElement(path, side = "result") {
  return [...document.querySelectorAll("[data-source-path]")].find(el => el.dataset.sourcePath === path && el.dataset.side === side);
}
function sourceMark() {
  const D = S.source, estimated = D.selection?.side === "silver_only";
  document.querySelectorAll("#source-page [data-line]").forEach(el => {
    const selected = D.selectedLines.has(el.dataset.line);
    el.setAttribute("aria-pressed", String(selected)); el.classList.toggle("source-highlight", selected);
    el.classList.toggle("source-estimated", selected && estimated);
    const flag = el.querySelector(".source-line-state");
    if (flag) flag.textContent = selected ? T(estimated ? "source.missing.evidence_title" : "source.labels.selected") : "";
  });
  document.querySelectorAll("[data-source-path]").forEach(el => {
    const selected = D.selection?.side === "silver_only" ? el.dataset.side === "silver_only" && el.dataset.sourcePath === D.selection.path
      : el.dataset.side !== "silver_only" && D.selectedPaths.has(el.dataset.sourcePath);
    el.setAttribute("aria-pressed", String(selected)); el.classList.toggle("source-highlight", selected);
  });
  if (D.draw) D.draw();
}
function sourceEvidence(v, D = S.source, root = document.getElementById("source-page"),
    visible = S.shell.route === "s02" && !document.getElementById("screen-s02").hidden && !S.guide?.open) {
  if (!visible || !root?.isConnected || !D.data?.values.includes(v)) return false;
  const line = (v.lines || []).find(id => D.selectedLines.has(id) && D.line[id]?.page === D.page &&
    [...root.querySelectorAll("[data-line]")].some(el => el.dataset.line === id && el.isConnected && el.getAttribute("aria-pressed") === "true"));
  if (!line) return false;
  const eventKey = JSON.stringify([D.run, D.doc, D.data.set?.id, S.ctx.key, v.path]);
  if (D.emitted.has(eventKey)) return;
  D.emitted.add(eventKey);
  emit("evidence_line_shown", {run: D.run, doc: D.doc, section: v.section, path: v.path,
    line, mismatch: v.silver?.same === false, item: (v.items || []).includes(D.item) ? D.item : null});
  return true;
}
function sourceRemember() {
  const D = S.source, v = sourceSelected(), only = D.selection?.side === "silver_only";
  S.focus = {...S.focus, run: D.run, doc: D.doc, section: D.section, item: D.item,
    path: v?.path ?? null, kind: v ? sourceKind(v, only) : null,
    expected: v ? (only ? v.value : v.silver?.value) ?? null : null,
    actual: v && !only ? v.value ?? null : null, page: D.page,
    expected_text: v ? (only ? v.text : v.silver?.text) ?? null : null,
    actual_text: v && !only ? v.text ?? null : null,
    line: [...D.selectedLines].find(id => D.line[id]?.page === D.page) || null,
    lines: [...D.selectedLines], estimated: !!only, source_set: D.data?.set?.id || null,
    key: S.ctx.key, pick: null, scroll: {...D.scroll}};
}
function sourceRetest() { sourceRemember(); return go("s03", {...S.focus}).catch(fail); }
function sourceRenderSelection() {
  const D = S.source, d = D.data, el = document.getElementById("source-selection");
  document.getElementById("source-details")?.remove();
  if (!d) { el.replaceChildren(); return; }
  const v = sourceSelected(), only = D.selection?.side === "silver_only";
  const lines = v ? (v.lines || []).map(id => D.line[id]).filter(line => line && d.pages.includes(line.page)) : [];
  const content = v ? h("div", {class: "source-comparison"},
    h("div", {"data-guide": "s02-evidence"}, h("h2", null, T(only ? "source.missing.evidence_title" : "source.evidence.title")),
      lines.length ? lines.map(line => h("div", {class: `selected-line source-evidence${only ? " source-estimated" : ""}`},
        h("p", null, T(only ? "source.missing.location" : "source.evidence.location", {page: line.page, line_no: line.no})), h("p", null, line.text)))
        : h("p", null, T(only ? "source.doc.no_guess" : "source.unlinked.title")),
      lines.length ? h("p", null, T(only ? "source.doc.guess" : "source.evidence.recorded")) : null,
      !lines.length ? h("p", null, T("source.unlinked.no_fallback")) : null,
      lines.some(line => !line.bbox) ? h("p", null, T("source.page.no_coordinates")) : null),
    h("div", null, h("h2", null, T("source.labels.result")),
      h("p", {class: "big-value"}, only ? T("common.none") : v.text ?? T("common.none")),
      h("p", null, T(`source.comparison.${sourceKind(v, only)}`)),
      h("p", null, T("source.labels.answer"), ": ", h("span", {class: "big-value"}, (only ? v.text : v.silver?.text) ?? T("common.none"))),
      h("p", null, T("source.value.draft_warning")))) : h("p", null, T("source.labels.choose"));
  const raw = v ? h("details", {class: "source-raw"}, h("summary", null, T("source.labels.raw_value")),
    h("p", {class: "technical"}, v.path), h("pre", {class: "technical"}, JSON.stringify(D.selection.side === "silver" ? v.silver?.value : v.value, null, 2) ?? T("common.none"))) : null;
  const coverage = d.silver_lines;
  coreReplace(el,
    D.gone ? h("p", {role: "status"}, T("source.value_gone.title"), " ", T("source.value_gone.returned", {section: D.section})) : null,
    content, raw,
    D.selection?.line ? h("p", null, D.selection.line, " — ", T("source.labels.line_values", {count: D.selectedPaths.size})) : null,
    v && !lines.length ? sourceButton("source-read-section", T("source.unlinked.read_section"), () => {
      sourceGoSection(D.section);
      document.getElementById("source-page").scrollIntoView?.({block: "start"});
      document.getElementById("source-page-select")?.focus({preventScroll: true});
    }, {class: "primary", disabled: !D.section}) : null,
    v && !lines.length && D.section ? h("p", null, T("source.unlinked.todo", {section: D.section})) : null,
    sourceButton("source-retest", T("source.retest.open"), sourceRetest, {class: v && !lines.length ? null : "primary", disabled: !D.doc || !D.section}),
    D.section ? h("p", null, T("source.retest.target", {doc: D.doc, section: D.section})) : null);
  document.getElementById("source-page").after(h("div", {id: "source-details"}, sourceStructure(),
    sourceDetails(T("source.structure.doc_comparison"), h("p", null, T("source.doc.counts", {
      total: d.values.length, different: d.has_gold ? d.values.filter(v => !v.silver?.same).length : T("context.unavailable"), missing: d.silver_only.length})),
      h("p", null, T("source.labels.matched_count", {count: d.has_gold ? d.values.filter(v => v.silver?.same).length : T("context.unavailable")}))),
    coverage ? sourceDetails(T("source.estimation.expand"),
      h("p", null, T("source.estimation.coverage", {total: coverage.total, matched: coverage.found})),
      coverage.basis === "text_match" ? h("p", null, T("source.estimation.method")) : null,
      h("p", null, T("source.estimation.count_meaning")), h("p", null, T("source.estimation.verify"))) : null));
  sourceMark();
}
function sourceScrollLine(id) {
  const line = [...document.querySelectorAll("#source-page [data-line]")].find(el => el.dataset.line === id);
  const box = document.getElementById("source-lines");
  if (line && box) {
    box.scrollTop = (box.scrollTop || 0) + line.getBoundingClientRect().top - box.getBoundingClientRect().top - (box.clientHeight || 0) / 3;
    S.source.scroll[S.source.page] = box.scrollTop;
    line.scrollIntoView?.({block: "nearest"});
  }
}
function sourceGoSection(section) {
  const D = S.source; D.section = section == null ? null : +section;
  const span = D.data?.sections?.[section];
  const first = D.line[span?.start];
  if (first && D.data.pages.includes(first.page)) D.page = first.page;
  sourceRenderTop(); sourceRenderPage(); sourceRenderSelection(); sourceRenderProblems();
  if (first) sourceScrollLine(first.id);
}
function sourceChooseSection(section) {
  const D = S.source, page = D.page;
  ++D.choice;
  sourceResetSelection(); D.page = page; D.item = null;
  sourceGoSection(section); sourceRemember();
}
function sourcePage(page) {
  const D = S.source;
  if (!D.data.pages.includes(page)) return;
  D.page = page; sourceRenderPage(); sourceRemember();
}
function sourcePickLine(id) {
  const D = S.source, paths = (D.data.line_index[id] || []).filter(path => D.values[path]);
  if (!D.line[id]) return;
  D.selection = {line: id}; D.selectedLines = new Set([id]); D.selectedPaths = new Set(paths);
  D.section = D.sections[id] ?? D.section;
  sourceRenderSelection(); sourceRenderProblems(); sourceMark();
  sourceRemember();
  for (const path of paths) sourceEvidence(D.values[path]);
}
function sourceDrawBoxes(img, svg) {
  const D = S.source;
  if (!img.naturalWidth || !img.naturalHeight) return;
  svg.setAttribute("viewBox", `0 0 ${img.naturalWidth} ${img.naturalHeight}`);
  const lines = [...D.selectedLines].map(id => D.line[id]).filter(line => line?.page === D.page &&
    Array.isArray(line.bbox) && line.bbox.length === 4 && line.bbox.every(Number.isFinite));
  svg.replaceChildren(...lines.map(({bbox: [x0, y0, x1, y1]}) => s("rect", {
    x: x0, y: y0, width: Math.max(0, x1 - x0), height: Math.max(0, y1 - y0),
    class: D.selection?.side === "silver_only" ? "source-box source-estimated" : "source-box"})));
}
function sourceRenderPage() {
  document.getElementById("source-page").setAttribute("data-guide", "s02-lines");
  const D = S.source, d = D.data, el = document.getElementById("source-page");
  if (!d) { el.replaceChildren(); return; }
  const page = D.page, hasPage = d.pages.includes(page), span = d.sections[D.section];
  const img = hasPage && d.image_base ? h("img", {src: `${d.image_base}p${String(page).padStart(3, "0")}.png${d.image_query || ""}`,
    alt: T("source.labels.image_alt", {page})}) : null;
  const svg = s("svg", {class: "source-boxes", "aria-hidden": "true"});
  const wrap = h("div", {class: "source-page-wrap"}, img, img ? svg : h("p", null, T("source.page.no_image")));
  if (img) {
    img.addEventListener("load", () => sourceDrawBoxes(img, svg));
    img.addEventListener("error", () => { wrap.replaceChildren(h("p", null, T("source.page.no_image"))); });
  }
  D.draw = img ? () => sourceDrawBoxes(img, svg) : null;
  const pageLines = hasPage ? d.lines.filter(line => line.page === page) : [];
  const list = h("div", {id: "source-lines", class: "source-lines"}, pageLines.length ? pageLines.map(line =>
    sourceButton(null, [h("span", {class: "source-band"}, D.sections[line.id] ? sourceLabel(D.sections[line.id]) : ""),
      h("span", {class: "raw"}, line.id), h("span", {class: "page-text"}, line.text),
      h("small", null, T("source.labels.line_values", {count: (d.line_index[line.id] || []).length})),
      h("span", {class: "source-line-state"})], () => sourcePickLine(line.id),
      {class: "source-line", "data-line": line.id, "aria-pressed": "false"})) : h("p", null, T("source.empty.lines")));
  list.scrollTop = D.scroll[page] || 0;
  list.addEventListener("scroll", () => { D.scroll[page] = list.scrollTop; });
  coreReplace(el, h("h2", null, T("source.page.expand")),
    h("div", {class: "source-controls"},
      sourceSelect("source-page-select", T("source.labels.page"), d.pages.map(p => ({id: String(p), label: T("source.labels.page_name", {page: p})})), String(page ?? ""), value => sourcePage(+value)),
      sourceSelect("source-section-select", T("source.labels.section"), Array.from({length: 16}, (_, i) => ({id: String(i + 1), label: sourceLabel(i + 1)})), String(D.section ?? ""), value => sourceChooseSection(+value))),
    D.section ? h("p", {class: "technical"}, span ? T("source.labels.range", {start: span.start, end: span.end}) : T("source.section_unknown.title", {section: D.section})) : null,
    hasPage ? h("div", {class: "source-page-grid"}, wrap, list) : h("p", {class: "source-state"}, T("source.empty.pages")));
  sourceMark();
}
