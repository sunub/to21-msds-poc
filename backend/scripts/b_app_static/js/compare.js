"use strict";

// 점수·점수 차·바뀐 값은 API의 계산 결과만 사용한다.
S.compare = {a: null, b: null, list: [], data: null, error: null, loading: false,
  initialized: false, context: null, request: 0, pending: null, all: false, sort: "down",
  causes: new Set(), values: new Set(), limits: {}, prompts: new Map(), promptOpen: new Set()};
const COMPARE_VIEWS = {"compare-summary": compareRenderSummary, "compare-conditions": compareRenderConditions,
  "compare-items": compareRenderItems, "compare-values": compareRenderValues,
  "compare-rows": compareRenderRows, "compare-prompts": compareRenderPrompts};
for (const [id, render] of Object.entries(COMPARE_VIEWS)) {
  shellDefineView(id, {render, ...(id === "compare-summary" ? {load: compareEnsure} : {})});
}
on("context_changed", () => { if (S.compare.initialized) compareLoad(true); });

function compareText(value) { return value == null || value === "" ? T("compare.unknown") : String(value); }
function compareLabel(run) { return run?.label?.title || (typeof run?.label === "string" ? run.label : run?.name) || T("compare.unknown"); }
function compareNote(text, attrs = {}) { return h("p", attrs, text); }
function compareButton(id, key, action, attrs = {}, values = {}) {
  return h("button", {id, type: "button", onclick: action, ...attrs}, T(key, values));
}
function compareDetails(title, ...kids) { return h("details", null, h("summary", null, title), ...kids); }
function compareTable(heads, rows, attrs = {}) {
  return h("table", attrs, h("thead", null, h("tr", null, heads.map(head => h("th", {scope: "col"}, head)))),
    h("tbody", null, rows.map(row => h("tr", null, row.map(cell => h("td", null, cell))))));
}
function compareBasis() { return T("compare.basis", {key: S.compare.data?.key?.label || T("compare.conditions.key_unknown")}); }
function compareReason(run) {
  if (run?.error) return run.error;
  if (run?.comparable !== false) return "";
  return run.comparable_reason || run.reason || T(`compare.selection.reasons.${
    Object.hasOwn(UI.compare.selection.reasons, run.run_kind) ? run.run_kind : "unknown"}`);
}
function compareAllowed(run) {
  return !!run && !run.error && run.kind !== "models" && !["silver", "eval", "models"].includes(run.run_kind);
}
function comparePair() { return JSON.stringify([S.compare.a, S.compare.b]); }
function compareContext() { return JSON.stringify([S.ctx.set, S.ctx.key]); }
async function compareEnsure(args = {}) {
  const navigation = S.shell.navigation;
  if (!S.shell.contextLoaded) {
    if (S.shell.started) {
      S.compare.pending = Promise.resolve().then(async () => {
        await S.shell.ready;
        if (navigation === S.shell.navigation && S.shell.route === "s04") await compareEnsure(args);
      });
      return;
    }
    await shellLoadContext();
  }
  if (navigation !== S.shell.navigation) return;
  const explicit = Object.hasOwn(args, "a") || Object.hasOwn(args, "b");
  if (explicit) { S.compare.a = args.a || null; S.compare.b = args.b || null; }
  return compareLoad(explicit);
}
function compareLoad(force = false) {
  const D = S.compare, context = compareContext();
  if (!force && D.initialized && D.context === context) return D.pending || Promise.resolve();
  const request = ++D.request;
  D.initialized = true; D.context = context; D.loading = true; D.error = null; D.data = null;
  D.causes.clear(); D.values.clear(); D.promptOpen.clear(); D.limits = {};
  compareRenderAll();
  const valid = () => request === D.request && context === compareContext();
  const work = (async () => {
    try {
      const result = await api(ctxUrl("/api/runs"));
      if (!valid()) return;
      D.list = result.runs || [];
      // API의 시간순 목록에서 현재 실행 바로 앞의 같은 종류·묶음을 기본 짝으로 삼는다.
      if (!D.list.length) { D.a = D.b = null; return; }
      if (!D.b) {
        const eligible = run => compareAllowed(run) && run.set?.id === S.ctx.set;
        D.b = D.list.find(run => run.name === S.score?.name && eligible(run))?.name
          || D.list.find(run => run.name === result.current && eligible(run))?.name
          || D.list.filter(eligible).at(-1)?.name || null;
      }
      if (!D.a && D.b) {
        const at = D.list.findIndex(run => run.name === D.b), current = D.list[at];
        D.a = D.list.slice(0, at).filter(run => compareAllowed(run) && run.run_kind === current?.run_kind
          && run.set?.id === current?.set?.id).at(-1)?.name || null;
      }
      if (!D.a || !D.b) return;
      // 존재하지 않거나 잠긴 선택을 다른 실행으로 몰래 바꾸지 않는다.
      if (![D.a, D.b].every(name => compareAllowed(D.list.find(run => run.name === name)))) return;
      const params = new URLSearchParams({a: D.a, b: D.b});
      const data = await api(ctxUrl(`/api/diff?${params}`));
      if (valid()) D.data = data;
    } catch (error) { if (valid()) D.error = error; }
    finally { if (valid()) { D.loading = false; compareRenderAll(); } }
  })();
  D.pending = work; return work;
}
function compareRenderAll() { for (const render of Object.values(COMPARE_VIEWS)) render(); }
function compareRestore(id, render) {
  const el = document.getElementById(id), focused = el.contains(document.activeElement) ? document.activeElement.id : null;
  render(); if (focused) document.getElementById(focused)?.focus({preventScroll: true});
}
function compareClass(delta) {
  if (S.compare.data?.same_conditions !== false || !num(delta) || delta === 0) return "compare-neutral";
  return delta < 0 ? "compare-down" : "compare-up";
}
function compareSigned(delta) { return num(delta) ? `${delta < 0 ? "−" : delta > 0 ? "+" : "±"}${Math.abs(delta).toFixed(1)}` : "—"; }
function compareDirection(delta) {
  return T(`compare.criteria.${!num(delta) ? "unknown" : delta === 0 ? "same" : delta < 0 ? "decreased" : "increased"}`);
}
function compareDelta(delta) {
  return h("span", {class: compareClass(delta)}, T("compare.criteria.delta", {delta: compareSigned(delta)}),
    h("span", {class: "compare-direction"}, compareDirection(delta)));
}
function compareConditionLabel(c) { return UI.compare.conditions.labels[c.what] || c.what; }
function compareConditionValue(c, side) {
  const raw = c[side];
  // 표시 이름이 있어도 기술 태그는 조건 표에 함께 남긴다.
  if (c.what === Object.keys(UI.compare.conditions.labels)[0]) {
    const run = S.compare.list.find(run => run.name === S.compare[side]);
    return run?.model_label ? `${run.model_label} (${compareText(raw)})` : compareText(raw);
  }
  return compareText(raw);
}
function compareConditionsLead(d) {
  const changed = (d.conditions || []).filter(c => c.changed);
  const docs = d.docs || {}, odd = (docs.only_a?.length || 0) + (docs.only_b?.length || 0);
  return h("div", {class: "compare-condition-lead"},
    d.same_conditions === true ? [compareNote(T("compare.conditions.same")), compareNote(term("variation", T("compare.conditions.variation")))]
      : d.same_conditions !== false ? compareNote(T("compare.conditions.unknown")) : null,
    changed.length ? h("ul", null, changed.map(c => h("li", {class: "compare-condition-change"},
      T("compare.conditions.changed", {condition: compareConditionLabel(c)}),
      h("span", {class: "raw"}, `${compareConditionValue(c, "a")} → ${compareConditionValue(c, "b")}`)))) : null,
    d.prompt_changed_sections?.length ? compareNote(T("compare.conditions.prompt_sections", {
      sections: d.prompt_changed_sections.map(section => T("compare.items.section", {section})).join(", ")})) : null,
    odd ? [compareNote(T("compare.different.title")), compareNote(T("compare.different.counts", {
      only_a: docs.only_a?.length || 0, only_b: docs.only_b?.length || 0, common: docs.common?.length || 0})),
      compareNote(T("compare.different.no_inference"))] : null,
    (d.conditions || []).some(c => c.a == null || c.b == null) ? compareNote(T("compare.conditions.metadata_missing")) : null,
    d.same_conditions === false ? compareNote(T("compare.interpretation.causality")) : null,
    compareNote(compareBasis(), {class: "compare-basis"}));
}
function compareSelect(side) {
  const D = S.compare, groups = new Map();
  for (const run of D.list) {
    const kind = run.run_kind || "unknown";
    if (!groups.has(kind)) groups.set(kind, []);
    groups.get(kind).push(run);
  }
  const select = h("select", {id: `compare-${side}`, onchange: event => {
    D[side] = event.target.value || null; return compareLoad(true);
  }}, h("option", {value: ""}, T("compare.selection.choose")),
    [...groups].map(([kind, runs]) => h("optgroup", {"data-kind": kind, label: UI.jobs.kinds[kind] || T("score.selection.unknown")},
      runs.map(run => h("option", {value: run.name, disabled: !compareAllowed(run)}, compareLabel(run),
        compareReason(run) ? ` — ${compareReason(run)}` : "")))));
  if (D[side] && !D.list.some(run => run.name === D[side])) select.append(h("option", {value: D[side], disabled: true}, D[side]));
  select.value = D[side] || "";
  const selected = D.list.find(run => run.name === D[side]);
  return h("div", null, h("label", {for: `compare-${side}`}, T(`compare.detail.result_${side}`)), select,
    compareNote(D[side] || "", {class: "raw"}), compareReason(selected) ? compareNote(compareReason(selected)) : null);
}
function compareTarget(side) {
  const t = S.compare.data?.targets?.[side];
  return h("div", null, compareNote(t?.weighted ? T("compare.target_line", {line: compareText(t.weighted.line)}) : T("compare.unknown")),
    compareNote(typeof t?.weighted?.met === "boolean" ? T(t.weighted.met ? "score.criteria.met" : "score.criteria.below") : T("compare.unknown")),
    compareNote(t?.must ? T("compare.must_met", {met: compareText(t.must.met_count), total: compareText(t.must.total)}) : T("compare.unknown")));
}
function compareRenderSummary() {
  const D = S.compare, d = D.data;
  const w = d?.weighted || {}, biggest = d?.headline?.biggest;
  const headline = !d ? D.loading ? T("compare.loading") : D.error ? T("compare.load_failed.fact") : T("compare.headline.none")
    : d.same_conditions === true ? T("compare.same.title")
    : (d.docs?.only_a?.length || d.docs?.only_b?.length) ? T("compare.different.title")
    : !num(w.delta) ? T("compare.headline.unscored", {a: "A", b: "B"})
    : w.delta < 0 ? T("compare.headline.decreased", {gap: Math.abs(w.delta).toFixed(1)})
    : w.delta > 0 ? T("compare.swapped.title", {gap: w.delta.toFixed(1)}) : T("compare.headline.equal", {a: "A", b: "B"});
  shellConclusion("s04", headline, false);
  document.getElementById("title-s04").setAttribute("class", d ? `compare-headline ${compareClass(w.delta)}` : "");
  const host = document.getElementById("compare-summary");
  if (!d && !D.loading && !D.error && !D.list.some(compareAllowed)) {
    coreReplace(host, compareNote(T("compare.empty.next")),
      compareButton("compare-prepare", "score.empty.prepare", () => go("s03"), {class: "primary"}),
      compareButton("compare-change-set", "score.empty.change_set", () => shellOpenContext("set")));
    return;
  }
  const selection = compareDetails(T("compare.selection.expand"), h("div", {class: "two-col"}, compareSelect("a"), compareSelect("b")),
    compareButton("compare-swap", "compare.selection.swap", () => { [D.a, D.b] = [D.b, D.a]; return compareLoad(true); }),
    D.list.some(run => run.error) ? compareNote(T("compare.selection.partial", {count: D.list.filter(run => run.error).length})) : null);
  if (!d) selection.open = true;
  const retry = compareButton("compare-retry", "compare.reload", () => compareLoad(true));
  coreReplace(host,
    d ? [compareConditionsLead(d),
      h("div", {id: "compare-total-change"}, h("h2", null, T("compare.total_score")), compareDelta(w.delta)),
      biggest && num(biggest.delta) ? h("div", {id: "compare-criterion-change"},
        h("h3", null, compareItemName(biggest.name)), compareDelta(biggest.delta)) : null,
      compareTable([T("compare.detail.basis"), T("compare.result_a"), T("compare.result_b")], [
        [T("score.conditions.run_name"), ...["a", "b"].map(side => h("div", null,
          compareNote(compareLabel(D.list.find(r => r.name === D[side]))), h("small", {class: "raw"}, D[side])))],
        [term("weighted", T("compare.total_score")), T("compare.score_value", {score: fmt1(w.a)}), T("compare.score_value", {score: fmt1(w.b)})],
        [T("compare.target"), compareTarget("a"), compareTarget("b")],
        [T("compare.common_docs"), T("compare.dev_count", {count: d.docs?.common?.length || 0}), T("compare.dev_count", {count: d.docs?.common?.length || 0})]
      ]), compareNote(T("compare.recalculated")), compareSourceAction(), selection,
      compareButton("compare-build-table", "compare.table.open", () => go("s10", {a: D.a, b: D.b, runs: [D.a, D.b],
        labels: [D.a, D.b].map(name => compareLabel(D.list.find(run => run.name === name)))}).catch(fail))]
      : [selection, D.loading ? compareNote(T("compare.loading"), {role: "status"})
        : D.error ? friendlyError({message: T("compare.load_failed.fact"), fix: T("compare.load_failed.todo"), raw: D.error.message})
        : compareNote(T("compare.selection.choose_two"))], retry);
}
function compareSourceAction() {
  const d = S.compare.data, changes = Object.entries(d?.changed_values || {});
  for (const kind of ["broken", "fixed"]) {
    for (const [item, values] of changes) {
      const section = (d.items || []).find(entry => entry.name === item)?.sections?.[0];
      const value = (values[kind] || []).find(entry => entry.doc_id && (entry.section || section));
      if (value) return h("div", {class: "compare-next"},
        compareButton("compare-open-source", "compare.values.open_changed", () => compareOpenSource(value, item, kind === "fixed" ? "a" : "b"), {class: "primary"}),
        !value.path ? compareNote(T("compare.values.path_missing"), {class: "muted"}) : null);
    }
  }
  const hasValues = changes.some(([, values]) => values.broken?.length || values.fixed?.length);
  return compareNote(T(hasValues ? "compare.values.unlinked" : "compare.values.same"), {class: "muted"});
}
function compareRenderConditions() {
  const d = S.compare.data, el = document.getElementById("compare-conditions");
  if (!d) { el.replaceChildren(); return; }
  const docs = d.docs || {}, w = d.weighted_na_excluded || {};
  card("compare-conditions", T("compare.conditions.title"), compareBasis(), {collapsed: true,
    summary: T(d.same_conditions === true ? "compare.conditions.same" : "compare.interpretation.title")},
    compareTable([T("compare.detail.basis"), T("compare.result_a"), T("compare.result_b")],
      [...(d.conditions || []).map(c => [compareConditionLabel(c), h("span", {class: "raw"}, compareConditionValue(c, "a")),
        h("span", {class: "raw"}, compareConditionValue(c, "b"))]),
      [T("context.answer.label"), d.key?.label || T("compare.conditions.key_unknown"), d.key?.label || T("compare.conditions.key_unknown")],
      [T("compare.detail.nonempty_score"), T("compare.score_value", {score: fmt1(w.a)}), T("compare.score_value", {score: fmt1(w.b)})]]),
    compareDelta(w.delta),
    compareDetails(T("compare.common.scope"), ["common", "only_a", "only_b"].map(key => h("div", null,
      compareNote(T(`compare.detail.${key === "common" ? "common_count" : key}`, {count: docs[key]?.length || 0})),
      h("ul", null, (docs[key] || []).map(id => h("li", {class: "raw"}, id))))),
      compareNote(T("compare.common.values_scope"))));
}
function compareItemName(name) {
  const match = Object.keys(UI.score.item_names).sort((a, b) => b.length - a.length).find(prefix => name.startsWith(prefix));
  return h("span", null, match ? UI.score.item_names[match] : name, match ? h("small", {class: "raw"}, name) : null);
}
function compareRenderItems() {
  const D = S.compare, d = D.data, el = document.getElementById("compare-items");
  if (!d) { el.replaceChildren(); return; }
  const all = d.items || [], visible = (D.all ? all : all.filter(i => num(i.delta) && i.delta < 0)).slice();
  visible.sort((a, b) => D.sort === "name" ? a.name.localeCompare(b.name)
    : !num(a.delta) ? (num(b.delta) ? 1 : 0) : !num(b.delta) ? -1 : D.sort === "up" ? b.delta - a.delta : a.delta - b.delta);
  const select = h("select", {id: "compare-sort", onchange: event => {
    D.sort = event.target.value; compareRestore("compare-items", compareRenderItems);
  }}, ["down", "up", "name"].map(value => h("option", {value}, T(`compare.items.sort_${value}`)))); select.value = D.sort;
  const filters = h("div", {class: "compare-filters"},
    compareButton("compare-drops", "compare.items.show_drops", () => { D.all = false; compareRestore("compare-items", compareRenderItems); }, {"aria-pressed": String(!D.all)}),
    compareButton("compare-all", "compare.items.show_all", () => { D.all = true; compareRestore("compare-items", compareRenderItems); }, {"aria-pressed": String(D.all)}),
    h("div", null, h("label", {for: "compare-sort"}, T("compare.items.sort")), select));
  const rows = visible.map(item => {
    const cause = (d.causes || []).find(c => c.item === item.name);
    const id = `compare-cause-${all.indexOf(item)}`, expanded = D.causes.has(item.name);
    const body = h("div", {id: `${id}-body`, hidden: !expanded, class: "compare-cause-body"},
      compareNote(d.ui_text?.candidate || T("compare.items.candidate")),
      cause?.reasons?.length ? h("ul", null, cause.reasons.map(reason => h("li", {class: "technical"}, reason))) : compareNote(T("compare.items.no_cause")));
    const toggle = cause ? compareButton(id, "compare.items.show_causes", event => {
      const open = !D.causes.has(item.name); open ? D.causes.add(item.name) : D.causes.delete(item.name);
      body.hidden = !open; event.target.closest("button").setAttribute("aria-expanded", String(open));
    }, {"aria-expanded": String(expanded), "aria-controls": `${id}-body`}) : compareNote(T("compare.items.no_cause"));
    return h("tr", {"data-item": item.name}, h("td", null, compareItemName(item.name),
      compareNote(compareText(item.level), {class: "muted"}), compareNote(T("compare.items.sections", {
        sections: (item.sections || []).map(section => T("compare.items.section", {section})).join(", ") || "—"}))),
      h("td", null, `${fmt1(item.a)} → ${fmt1(item.b)}`), h("td", null, compareDelta(item.delta)), h("td", null, toggle, cause ? body : null));
  });
  card("compare-items", T("compare.criteria.title_count", {count: all.length}), compareBasis(), {collapsed: true, summary: T("compare.criteria.direction")},
    filters, !D.all ? compareNote(d.ui_text?.hidden || T("compare.items.hidden", {count: all.length - visible.length}), {role: "status"}) : null,
    !D.all && !visible.length ? compareNote(d.ui_text?.empty || T("compare.items.empty")) : null,
    h("table", {class: "compare-items-table"}, h("thead", null, h("tr", null,
      ["compare.items.name", "compare.criteria.direction", "compare.items.delta", "compare.items.show_causes"].map(key => h("th", {scope: "col"}, T(key))))), h("tbody", null, rows)));
}
function compareOpenSource(value, item, side) {
  const section = value.section || (S.compare.data?.items || []).find(i => i.name === item)?.sections?.[0];
  if (!section || !value.doc_id) return;
  const args = {run: S.compare[side], doc: value.doc_id, section, item, path: value.path || null,
    pick: null, kind: null, estimated: false};
  S.focus = {...S.focus, ...args}; return go("s02", args).catch(fail);
}
function compareValueList(item, kind, entries) {
  const D = S.compare, key = JSON.stringify([item, kind]), limit = D.limits[key] || 300, shown = entries.slice(0, limit);
  const block = h("div", {class: "compare-value-list"});
  const render = () => {
    const side = kind === "fixed" ? "a" : "b", section = (D.data.items || []).find(i => i.name === item)?.sections?.[0];
    block.replaceChildren(h("h3", null, T(`compare.values.${kind === "fixed" ? "correct_count" : "wrong_count"}`, {total: entries.length, shown: shown.length})),
      compareTable([T("common.document"), T("compare.values.kind"), T("compare.values.content")], shown.map(value => [
        h("span", {class: "raw"}, value.doc_id || "—"), compareText(value.kind), h("div", null,
          compareNote(compareText(value.content), {class: "technical"}),
          value.doc_id && (value.section || section) ? h("div", null,
            compareButton(null, "compare.values.open_source", () => compareOpenSource(value, item, side), {class: "text-button compare-source"}),
            !value.path ? compareNote(T("compare.values.path_missing"), {class: "muted"}) : null)
            : compareNote(T("compare.values.unlinked")))])));
    if (shown.length < entries.length) block.append(compareButton(null, "compare.values.more", () => {
      D.limits[key] = limit + 300; const next = compareValueList(item, kind, entries); block.replaceWith(next);
      next.querySelector("button")?.focus({preventScroll: true});
    }, {}, {count: Math.min(300, entries.length - shown.length)}));
  };
  render(); return block;
}
function compareRenderValues() {
  const D = S.compare, d = D.data, el = document.getElementById("compare-values");
  if (!d) { el.replaceChildren(); return; }
  const changes = Object.entries(d.changed_values || {});
  card("compare-values", T("compare.values.title"), T("compare.values.scope"), {collapsed: true, summary: T("compare.values.expand")},
    compareNote(T("compare.values.definitions")), changes.length ? changes.map(([item, value], index) => {
      const expanded = D.values.has(item), id = `compare-value-${index}`;
      const body = h("div", {id: `${id}-body`, hidden: !expanded}, compareValueList(item, "fixed", value.fixed || []), compareValueList(item, "broken", value.broken || []));
      const toggle = h("button", {id, type: "button", class: "compare-value-toggle", "aria-expanded": String(expanded), "aria-controls": `${id}-body`, onclick: () => {
        const open = !D.values.has(item); open ? D.values.add(item) : D.values.delete(item);
        body.hidden = !open; toggle.setAttribute("aria-expanded", String(open));
      }}, compareItemName(item), h("span", null, T("compare.values.fixed", {count: value.fixed?.length || 0})),
      h("span", null, T("compare.values.broken", {count: value.broken?.length || 0})));
      return h("div", {class: "compare-value-group"}, toggle, body);
    }) : compareNote(T("compare.values.same")));
}
function compareRenderRows() {
  const d = S.compare.data, el = document.getElementById("compare-rows");
  if (!d) { el.replaceChildren(); return; }
  card("compare-rows", T("compare.rows.title"), T("compare.rows.hint"), {collapsed: true, summary: compareBasis()},
    compareTable([T("compare.rows.table"), T("compare.side_a"), T("compare.side_b"), T("compare.rows.answer"), T("compare.rows.distance")],
      Object.entries(d.rows || {}).map(([key, row]) => {
        // 채점이 아닌 기존 행 수의 거리 표시. 점수와 바뀐 값은 계산하지 않는다.
        const distance = [row.a, row.b, row.gold].every(num) ? Math.abs(row.a - row.gold) - Math.abs(row.b - row.gold) : null;
        return [UI.source.table_names[key] || key, ...[row.a, row.b, row.gold].map(count => num(count) ? T("compare.rows.unit", {count}) : T("compare.unknown")),
          h("span", {class: compareClass(distance)}, T(`compare.rows.${!num(distance) ? "unknown" : distance > 0 ? "closer" : distance < 0 ? "farther" : "same"}`))];
      })));
}
function comparePromptKey(no) { return JSON.stringify([S.compare.a, S.compare.b, no]); }
function comparePromptBody(no, body) {
  const p = S.compare.prompts.get(comparePromptKey(no)), r = p?.data;
  coreReplace(body, p?.loading ? compareNote(T("compare.prompt.loading", {section: no}), {role: "status"})
    : p?.error ? [friendlyError({message: T("compare.prompt.failed"), fix: T("compare.prompt.todo"), raw: p.error.message}),
      compareButton(null, "compare.prompt.retry", () => compareFetchPrompt(no, body, true), {class: "compare-prompt-retry"})]
    : r ? [compareNote(T("compare.prompt.lines_a", {section: no, count: compareText(r.a_lines)})),
      compareNote(T("compare.prompt.lines_b", {count: compareText(r.b_lines)})),
      ["a", "b"].map((side, i) => compareNote(T("compare.prompt.form", {side: side.toUpperCase(),
        format: typeof r.rows?.[i] === "boolean" ? T(r.rows[i] ? "compare.prompt.rows" : "compare.prompt.json") : T("compare.unknown")}))),
      ["a", "b"].filter(side => r.recorded?.[side] && r.recorded[side] !== r[`${side}_hash`]).map(side =>
        h("div", {class: "compare-hash-warning"}, h("strong", null, T("compare.hash_mismatch.title")), compareNote(T("compare.hash_mismatch.todo")),
          compareNote(T("compare.prompt.hashes", {side: side.toUpperCase(), recorded: r.recorded[side], restored: compareText(r[`${side}_hash`])}), {class: "technical"}))),
      compareNote(T("compare.prompt.full_text")), r.same ? compareNote(T("compare.prompt.same"))
        : [compareNote(T("compare.prompt.legend")), h("pre", {class: "technical compare-prompt-diff"},
          String(r.diff || "").split("\n").map(line => h("span", {class: line.startsWith("+") ? "compare-diff-add" : line.startsWith("-") ? "compare-diff-remove" : null}, line + "\n")))]] : null);
}
async function compareFetchPrompt(no, body, force = false) {
  const D = S.compare, key = comparePromptKey(no), pair = comparePair(), current = D.prompts.get(key);
  if (!force && (current?.data || current?.loading)) { comparePromptBody(no, body); return current.pending; }
  const record = {loading: true}; D.prompts.set(key, record); comparePromptBody(no, body);
  record.pending = (async () => {
    try { record.data = await api(`/api/prompt_diff?${new URLSearchParams({a: D.a, b: D.b, no})}`); }
    catch (error) { record.error = error; }
    finally { record.loading = false; if (pair === comparePair()) comparePromptBody(no, body); }
  })();
  return record.pending;
}
function compareRenderPrompts() {
  const D = S.compare, el = document.getElementById("compare-prompts");
  if (!D.data) { el.replaceChildren(); return; }
  card("compare-prompts", term("prompt_version", T("compare.prompt.title")), T("compare.prompt.note"), {collapsed: true, summary: T("compare.prompt.full_text")},
    Array.from({length: 16}, (_, index) => {
      const no = index + 1, key = comparePromptKey(no), id = `compare-prompt-${no}`, open = D.promptOpen.has(key);
      const body = h("div", {id: `${id}-body`, hidden: !open});
      const toggle = compareButton(id, "compare.prompt.open", () => {
        const expanded = !D.promptOpen.has(key); expanded ? D.promptOpen.add(key) : D.promptOpen.delete(key);
        toggle.setAttribute("aria-expanded", String(expanded)); body.hidden = !expanded;
        if (expanded) return compareFetchPrompt(no, body);
      }, {"data-section": no, "aria-expanded": String(open), "aria-controls": `${id}-body`}, {section: no});
      if (open) comparePromptBody(no, body);
      return h("div", {class: "compare-prompt-section"}, toggle, body);
    }));
}
