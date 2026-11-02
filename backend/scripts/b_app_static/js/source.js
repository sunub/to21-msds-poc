"use strict";

// 같은 문제를 다시 연 안내에서도 실제 값 선택으로 근거 사건을 낼 수 있다.
on("problem_opened", () => {S.source.emitted.clear();});

const SOURCE_ROW_BATCH = 60, SOURCE_NEAR_LINES = 2, SOURCE_KINDS = ["wrong", "made", "missing"], SOURCE_TOP_CRITERIA = 5;
// 원문과 선택 값은 메모리에만 둔다. 다른 화면에는 S.focus로 넘긴다.
// step은 표시 상태일 뿐 고른 값을 지우지 않는다: choose(문제 고르기), compare(원문과 맞춰 보기), send(다시 시험으로 보내기).
S.source = {step: null, run: null, doc: null, docAll: true, raw: false, override: null, list: [], added: [], initialized: false,
  data: null, error: null, locked: null, loading: false, request: 0, pending: null, cacheKey: null, scopeKey: null,
  section: null, item: null, page: null, selection: null, rowId: null, line: {}, values: {}, only: {}, sections: {},
  selectedLines: new Set(), selectedPaths: new Set(), emitted: new Set(),
  filter: "all", gone: false, draw: null, scroll: {}, problemData: new Map(), problemKey: null,
  problemErrors: new Map(), problemRequest: 0, choice: 0, problemScroll: 0, rowStart: 0, rowLimit: SOURCE_ROW_BATCH,
  allLines: false, allCriteria: false, runData: null, runFor: null, runError: null, runRequest: 0};
const SOURCE_VIEWS = {"source-top": sourceRenderTop, "source-values": sourceRenderProblems,
  "source-page": sourceRenderPage, "source-selection": sourceRenderSelection};
for (const [id, render] of Object.entries(SOURCE_VIEWS)) {
  shellDefineView(id, {render, ...(id === "source-top" ? {load: sourceEnsure} : {})});
}
on("context_changed", async () => {
  // 전역 묶음 변경은 실행 당시 원문 묶음을 덮어쓰지 않는다. 정답지는 항상 다시 읽는다.
  if (S.source.initialized) {
    S.source.runFor = null;
    await Promise.all([sourceLoad(true), S.score.pending]);
    await sourceLoadRun();
    await sourceLoadProblems();
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
function sourceSelect(id, label, options, selected, action) {
  const select = h("select", {id, onchange: event => action(event.target.value)}, options.map(item =>
    h("option", {value: item.id, disabled: item.disabled, selected: item.id === selected}, item.label)));
  select.value = selected ?? "";
  return h("div", null, h("label", {for: id}, label), select);
}
function sourceResetSelection() {
  Object.assign(S.source, {selection: null, rowId: null, page: null, gone: false, filter: "all", scroll: {}, rowStart: 0, rowLimit: SOURCE_ROW_BATCH});
  S.source.selectedLines.clear(); S.source.selectedPaths.clear();
}
async function sourceEnsure(args = {}) {
  const D = S.source, navigation = S.shell.navigation;
  // 이번 이동에만 쓰는 지시다. S.focus에 남으면 다음 이동에 다시 적용된다.
  const {sourceDocOnly, ...focus} = S.focus;
  S.focus = focus;
  if (!S.shell.contextLoaded) {
    await (S.shell.contextReady || shellLoadContext());
  }
  if (navigation !== S.shell.navigation) return;
  if (S.score?.list?.length || D.usingScoreList) {
    D.list = [...S.score.list, ...D.added.filter(item => !S.score.list.some(known => known.name === item.name))];
    D.usingScoreList = true;
  }
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
  // 방금 끝난 시험의 결과는 처음 읽은 목록에 없다.
  if (explicitRun && run && !D.list.some(item => item.name === run)) {
    try {
      const result = await api(ctxUrl("/api/runs"));
      if (navigation !== S.shell.navigation) return;
      const fresh = (result.runs || []).filter(item => !D.list.some(known => known.name === item.name));
      D.added = [...D.added, ...fresh]; D.list = [...D.list, ...fresh];
    } catch (_) { /* 찾지 못하면 아래에서 있는 결과로 돌아간다 */ }
  }
  const changedRun = run !== D.run;
  if (changedRun || !D.initialized) D.override = null;
  D.run = run; D.raw = explicitRun ? !run : D.raw;
  if (D.raw && Object.hasOwn(incoming, "set")) D.override = incoming.set;
  if (!D.raw && !D.list.some(item => item.name === D.run)) D.run = D.list.at(-1)?.name || null;
  if (Object.hasOwn(incoming, "doc")) D.doc = incoming.doc;
  else if (changedRun || !sourceDocs().includes(D.doc)) D.doc = sourceDocs()[0] || null;
  if (Object.keys(incoming).length) {
    D.section = incoming.section ?? null; D.item = incoming.item ?? null;
    if (D.item) D.docAll = !sourceDocOnly;
    else if (Object.hasOwn(incoming, "doc")) D.docAll = false;
  }
  // 다시 시험할 수 있는 부분을 알아 둔다. 기다리지 않는다.
  if (!S.jobs.opts && !S.jobs.loadingOptions) jobsLoadOptions().then(() => { if (S.shell.route === "s02") sourceRenderFrame(); });
  // 고른 문제를 들고 오면 ②에서 시작한다. 메뉴로 처음 들어오면 ①이다. 그 뒤로는 있던 자리를 연다.
  const pointed = ["section", "path", "pick"].some(name => args[name] != null);
  D.step = Object.keys(args).length ? (pointed ? "compare" : "choose") : D.step || "choose";
  D.initialized = true;
  const running = sourceLoadRun();
  const loading = sourceLoad(false), request = D.request, choice = D.choice, key = S.ctx.key;
  const valid = () => navigation === S.shell.navigation && request === D.request && choice === D.choice && key === S.ctx.key && D.data;
  if (D.item) await running;
  await loading;
  if (!valid()) return;
  await sourceLoadProblems();
  if (!valid()) return;
  if (Object.hasOwn(incoming, "path") && incoming.path) {
    const only = incoming.kind === "missing" || incoming.estimated === true;
    const v = only ? D.only[incoming.path] : D.values[incoming.path];
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
// 실행 API의 값을 읽기만 한다. 점수와 건수를 화면에서 다시 세지 않는다.
function sourceRunData() {
  const D = S.source;
  return S.score?.run?.name === D.run ? S.score.run : D.runFor === D.run ? D.runData : null;
}
function sourceCriteria() {
  const text = sourceRunData()?.status_text;
  return text?.losses || (text?.top_problem ? [text.top_problem] : []);
}
function sourceCriterion(item = S.source.item) { return sourceCriteria().find(row => row.name === item) || null; }
function sourceCriterionDocs(item = S.source.item) {
  const run = sourceRunData(), top = run?.status_text?.top_problem;
  return run?.problem_rows?.[item]?.docs || (top?.name === item ? top.docs : null) || [];
}
function sourceProblemDocs() {
  // 문서를 옮겨도 목록 순서는 그대로다. 이전·다음 행이 같은 순서를 따른다.
  const D = S.source, docs = D.item && D.docAll ? sourceCriterionDocs().map(doc => doc.doc_id) : [];
  return [...new Set(docs.includes(D.doc) ? docs : [D.doc, ...docs])].filter(doc => doc && sourceRunDocs().includes(doc) && !sourceLock(doc));
}
async function sourceLoadRun() {
  const D = S.source, run = D.run;
  if (!run || S.score?.run?.name === run || (D.runFor === run && !D.runError)) return;
  const request = ++D.runRequest;
  D.runFor = null; D.runData = null; D.runError = null;
  try {
    const data = await api(ctxUrl(scoreRunPath(run)));
    if (request !== D.runRequest) return;
    D.runData = data; D.runFor = run;
  } catch (error) { if (request === D.runRequest) D.runError = error; }
  if (request === D.runRequest) { sourceRenderTop(); await sourceLoadProblems(); }
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
  if (D.problemKey !== key) { D.rowStart = 0; D.rowLimit = SOURCE_ROW_BATCH; }
  D.problemKey = key; D.problemErrors.clear();
  const request = ++D.problemRequest;
  if (!D.data || !D.run) { sourceRenderProblems(); return; }
  // 이미 읽은 문서는 다시 받지 않는다. 다음 행이 다른 문서여도 바로 열린다.
  const others = docs.filter(doc => doc !== D.doc && (force || !D.problemData.has(doc)));
  sourceRenderProblems();
  const results = await Promise.allSettled(others.map(sourceDocUrl).map(path => api(path)));
  if (request !== D.problemRequest || key !== D.problemKey) return;
  results.forEach((result, i) => {
    if (result.status === "fulfilled") D.problemData.set(others[i], result.value);
    else D.problemErrors.set(others[i], result.reason);
  });
  sourceRenderProblems(); sourceRenderFrame();
}
function sourceLoad(force = false) {
  const D = S.source, cacheKey = JSON.stringify([D.run, D.doc, D.override, S.ctx.key]);
  if (!force && D.cacheKey === cacheKey) return D.pending || Promise.resolve();
  const priorDoc = D.data?.doc_id, priorRun = D.loadedRun, priorSelection = D.selection, priorPage = D.page, priorRow = D.rowId;
  const keep = priorDoc === D.doc && priorRun === D.run;
  const scopeKey = JSON.stringify([D.run, D.override, S.ctx.key]);
  const request = ++D.request, key = S.ctx.key;
  // 정답·묶음 변경이나 새로 읽기 뒤에는 앞 요청의 목록을 덮어쓰지 않는다. 같은 실행의 다른 문서로 옮길 때만 읽은 문서를 다시 쓴다.
  ++D.problemRequest; D.problemKey = null; D.problemErrors.clear();
  if (force || D.scopeKey !== scopeKey) D.problemData.clear();
  else if (D.data) D.problemData.set(priorDoc, D.data);
  D.scopeKey = scopeKey;
  const known = D.problemData.get(D.doc);
  D.cacheKey = cacheKey; D.data = null; D.error = null; D.locked = sourceLock(D.doc); D.draw = null;
  if (!keep) sourceResetSelection();
  D.absent = !!D.doc && !sourceDocs().includes(D.doc);
  D.loading = !!D.doc && !D.locked && !D.absent;
  sourceRenderAll();
  const work = (async () => {
    if (!D.doc || D.locked || D.absent) return;
    try {
      const data = known || await api(sourceDocUrl(D.doc));
      if (request !== D.request || key !== S.ctx.key) return;
      sourcePrepare(data); D.loadedRun = D.run;
      if (keep) {
        D.rowId = priorRow;
        if (data.pages.includes(priorPage)) D.page = priorPage;
        if (priorSelection?.path) {
          const v = priorSelection.side === "silver_only" ? D.only[priorSelection.path] : D.values[priorSelection.path];
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
  D.only = Object.fromEntries(data.silver_only.map(value => [value.path, value]));
  D.page = data.pages[0] ?? null; D.sections = {};
  const positions = Object.fromEntries(data.lines.map((line, i) => [line.id, i]));
  for (const [section, span] of Object.entries(data.sections)) {
    if (!(span.start in positions) || !(span.end in positions)) continue;
    for (let i = positions[span.start]; i <= positions[span.end]; i++) D.sections[data.lines[i].id] = +section;
  }
}
function sourceRenderAll() { for (const render of Object.values(SOURCE_VIEWS)) render(); sourceRenderFrame(); }
function sourceChangeTarget(kind, value) {
  const D = S.source;
  if (kind === "doc" && !value) {
    D.docAll = true; sourceRenderTop();
    return sourceLoadProblems();
  }
  if (kind === "run") { D.run = value || null; D.raw = !value; D.override = D.raw ? S.ctx.set : null; D.doc = sourceDocs()[0] || null; D.docAll = true; }
  if (kind === "doc") { D.doc = value; D.docAll = false; }
  if (kind === "set") D.override = value || null;
  sourceResetSelection();
  if (kind === "run") { D.section = null; D.item = null; sourceLoadRun(); }
  return sourceLoad(true);
}
async function sourceReload() {
  if (!S.source.initialized) { await sourceEnsure(); sourceRenderAll(); }
  else await sourceLoad(true);
}
function sourceRaw() {
  const D = S.source;
  D.raw = true; D.run = null; D.override = S.ctx.set; D.docAll = false;
  D.doc = sourceDocs()[0] || null; D.section = null; D.item = null; sourceResetSelection();
  return sourceLoad(true);
}
// ── 단계 틀: 문제 고르기 → 원문과 맞춰 보기 → 다시 시험으로 보내기 (ADR-039) ──
// 읽는 중에는 가던 단계를 지킨다. 읽지 못하면 고르는 단계에서 이유를 보인다.
function sourceStep() { return S.source.data || S.source.loading ? S.source.step || "choose" : "choose"; }
function sourceHasTarget() {
  const D = S.source;
  return !!D.data && (!!D.selection || D.section != null || !!D.item || sourceVisibleRows().length > 0);
}
function sourceGoStep(id) {
  const D = S.source;
  D.step = id;
  // 고른 행이 없으면 목록의 첫 행을 연다. 사용자가 고른 값이 아니므로 근거 사건을 내지 않는다.
  const first = id === "compare" && !D.selection && !D.rowId ? sourceVisibleRows()[0] : null;
  if (id === "send") sourceRemember();
  if (first) sourceOpenRow(first, false);
  else if (id === "compare" && !D.selection && D.section != null) sourceGoSection(D.section);
  else sourceRenderAll();
  if (id === "send" && !S.jobs.opts) jobsLoadOptions().then(() => { if (sourceStep() === "send") sourceRenderTop(); });
  document.getElementById("title-s02").focus({preventScroll: true});
}
function sourceScopeText() {
  const D = S.source;
  return D.item ? scoreItemName(D.item) : D.section != null ? sourceLabel(D.section) : D.doc || "";
}
function sourceStepList(current) {
  const D = S.source, order = ["choose", "compare", "send"], at = order.indexOf(current);
  const count = sourceRowEntries().length, retest = !!D.doc && D.section != null;
  const summary = {choose: T(count ? "steps.source.choose_summary" : "steps.source.choose_summary_plain", {what: sourceScopeText(), count}),
    compare: sourceCurrentRow()?.title || T("steps.source.compare_hint"),
    send: retest ? T("steps.source.send_summary", {doc: D.doc, section: D.section}) : T("steps.source.send_hint")};
  const reachable = {choose: true, compare: !!D.data && sourceHasTarget(), send: !!D.data && retest};
  return order.map((id, index) => ({id, label: T(`steps.source.${id}`), done: index < at, summary: summary[id],
    reachable: reachable[id], buttonId: `source-step-${id}`}));
}
function sourceHead(step) {
  const D = S.source;
  if (D.loading) return [T("source.loading"), ""];
  if (D.locked) return [T("source.locked.title"), ""];
  if (D.error?.status === 404 || D.absent) return [T("source.empty.document"), ""];
  if (D.error) return [T("source.load_failed.fact"), ""];
  if (step === "send") return [T("steps.source.send_title"), T("steps.source.send_say")];
  if (step === "compare") return [T("source.title"), ""];
  return [T("steps.source.choose_title"), `${T("steps.source.choose_say")} ${T("steps.source.row_meaning")}`];
}
function sourceSelectedLines(v = sourceSelected()) {
  const D = S.source;
  return v ? (v.lines || []).map(id => D.line[id]).filter(line => line && D.data.pages.includes(line.page)) : [];
}
function sourceActions(step) {
  const D = S.source, off = D.section != null && !jobsSectionOpen(D.section), target = !D.doc || D.section == null || off;
  const reason = T(off ? "steps.source.not_extracted" : "source.labels.choose_scope");
  // 항목 표가 있으면 표의 첫 단추가 주 행동이다. 표가 없을 때만 이 단추가 주 행동이다.
  if (step === "choose") {
    const next = {label: T("steps.next", {name: T("steps.source.compare")}), onClick: () => sourceGoStep("compare"),
      disabled: !sourceHasTarget(), reason, attrs: {id: "source-next"}};
    return D.run && sourceCriteria().some(row => sourceCriterionValues(row).loss > 1e-9) ? {secondary: next} : {primary: next};
  }
  if (step === "send") return {back: {label: T("steps.back"), onClick: () => sourceGoStep("compare"), attrs: {id: "source-back"}},
    primary: {label: T("steps.source.send"), onClick: sourceRetest, disabled: target, reason, attrs: {id: "source-retest"}}};
  const v = sourceSelected(), rows = sourceVisibleRows(), at = rows.findIndex(row => sourceIsCurrentRow(row));
  const move = (id, key, offset) => ({label: T(`steps.source.${key}`), disabled: !rows[at < 0 ? 0 : at + offset], attrs: {id},
    onClick: () => sourceOpenRow(rows[at < 0 ? 0 : at + offset])});
  const retest = {label: T("source.retest.open"), onClick: sourceRetest, disabled: target, reason, attrs: {id: "source-retest"}};
  const read = {label: T("source.unlinked.read_section"), disabled: !D.section, attrs: {id: "source-read-section"}, onClick: () => {
    sourceGoSection(D.section);
    document.getElementById("source-page-select")?.focus({preventScroll: true});
  }};
  const unlinked = !!v && !sourceSelectedLines(v).length;
  return {back: D.run ? [move("source-prev-row", "previous_row", -1), move("source-next-row", "next_row", 1)] : null,
    note: T("steps.source.compare_note"),
    secondary: unlinked ? retest : null, primary: unlinked ? read : retest};
}
function sourceRenderFrame(step = sourceStep()) {
  const D = S.source, active = document.activeElement, activeId = active?.id, [title, say] = sourceHead(step);
  document.getElementById("screen-s02").setAttribute("data-step", step);
  shellConclusion("s02", title);
  document.getElementById("source-step-say").textContent = say;
  stepsRenderBar(document.getElementById("source-step-bar"), {steps: sourceStepList(step), current: step, onGo: sourceGoStep});
  coreReplace(document.getElementById("source-details"), step === "compare" && D.data ? [] : h("p", {class: "server-details-link"}, sourceDetailsButton(), " ", T("steps.source.details_hint")));
  stepsRenderActions(document.getElementById("source-actions"), sourceActions(step));
  if (activeId && !active.isConnected) document.getElementById(activeId)?.focus({preventScroll: true});
}
function sourceDetailsButton() {
  return h("button", {id: "source-details-open", type: "button", class: "text-button", onclick: sourceOpenDetails}, T("steps.details.open"));
}
function sourceStateNote() {
  const D = S.source;
  if (D.loading) return h("p", {role: "status"}, T("source.loading"));
  if (D.locked) return h("div", {class: "source-state", role: "status"},
    h("strong", null, T("source.locked.title")), h("p", null, D.locked.reason), h("p", null, T("errors.eval_locked.todo")));
  if (D.error?.status === 404 || D.absent || (!D.doc && !D.error)) return h("p", {class: "source-state"}, T(D.doc || D.run ? "source.empty.document" : "source.empty.runs"));
  if (D.error) return serversFlat(friendlyError({message: T("source.load_failed.fact"), fix: T("source.load_failed.todo"), raw: D.error.message}));
  return null;
}
// ① 문제 고르기: 고르는 칸을 접지 않는다. 손실 표는 API의 순서와 값을 그대로 쓴다.
function sourceCriterionValues(row) {
  const D = S.source, rows = sourceRunData()?.problem_rows?.[row.name];
  const own = D.docAll ? null : sourceCriterionDocs(row.name).find(doc => doc.doc_id === D.doc);
  return D.docAll ? {loss: row.loss, counts: row.counts, rows: rows?.row_count} : {loss: own?.loss, counts: own?.counts, rows: own?.row_count};
}
function sourceCriteriaTable() {
  const D = S.source, list = sourceCriteria().filter(row => sourceCriterionValues(row).loss > 1e-9);
  if (!list.length) return null;
  // 문서를 고르면 그 문서의 깎인 점수를 보이므로 그 순서로 놓는다. 전체일 때는 API 순서 그대로다.
  if (!D.docAll) list.sort((a, b) => sourceCriterionValues(b).loss - sourceCriterionValues(a).loss);
  const shown = D.allCriteria ? list : list.slice(0, SOURCE_TOP_CRITERIA);
  const unknown = T("context.unavailable");
  const cellCount = counts => counts ? Object.values(counts).reduce((sum, count) => sum + (num(count) ? count : 0), 0) : null;
  return [h("table", {class: "source-criteria"},
    h("thead", null, h("tr", null, ["col_item", "col_loss", "col_rows", "col_cells"].map(key => h("th", {scope: "col"}, T(`steps.source.${key}`))), h("th", {scope: "col"}, T("steps.source.col_open")))),
    h("tbody", null, shown.map(row => {
      const values = sourceCriterionValues(row), cells = cellCount(values.counts);
      return h("tr", {class: D.item === row.name ? "source-criterion-on" : null},
        h("td", null, h("button", {type: "button", class: "text-button source-criterion-name", disabled: !row.section, onclick: () => sourceOpenCriterion(row)}, scoreItemName(row.name)),
          D.docAll && row.rank === 1 ? h("span", {class: "source-top-tag"}, T("guide.example.biggest")) : null,
          row.section ? h("small", null, sourceLabel(row.section)) : null),
        h("td", null, T("steps.source.loss", {points: fmt1(values.loss)})),
        h("td", null, num(values.rows) ? T("compare.rows.unit", {count: values.rows}) : unknown),
        h("td", null, num(cells) ? T("source.labels.cells", {count: cells}) : unknown),
        h("td", null, h("button", {type: "button", class: `source-open-criterion${row === shown[0] ? " primary" : ""}`, disabled: !row.section, onclick: () => sourceOpenCriterion(row)}, T("steps.source.open"))));
    }))),
    list.length > SOURCE_TOP_CRITERIA ? h("button", {id: "source-all-criteria", type: "button", class: "text-button", onclick: () => { D.allCriteria = !D.allCriteria; sourceRenderTop(); }},
      T(D.allCriteria ? "steps.source.top_criteria" : "steps.source.all_criteria", {count: list.length})) : null];
}
function sourceOpenCriterion(row) {
  const D = S.source, docs = sourceCriterionDocs(row.name);
  const doc = D.docAll ? scoreProblemDoc({docs}) || D.doc : D.doc;
  return go("s02", {run: D.run, doc, section: row.section, item: row.name, pick: "mismatch", sourceDocOnly: !D.docAll}).catch(fail);
}
function sourceStageChoose() {
  const D = S.source, d = D.data, docs = sourceDocs();
  const controls = h("div", {class: "source-controls"},
    sourceSelect("source-run-select", T("source.labels.run"), [
      {id: "", label: T("source.selection.raw")},
      ...D.list.filter(item => !item.error).map(item => ({id: item.name, label: item.label?.title || item.name}))
    ], D.run, value => sourceChangeTarget("run", value)),
    sourceSelect("source-doc-select", T("source.labels.doc"), [
      ...(D.run && docs.length > 1 ? [{id: "", label: T("steps.source.all_docs", {count: docs.length})}] : []),
      ...docs.map(id => ({id, label: id}))], D.run && docs.length > 1 && D.docAll ? "" : D.doc, value => sourceChangeTarget("doc", value)),
    sourceSelect("source-section-choice", T("source.labels.section"), [
      {id: "", label: T("steps.source.choose_section")},
      ...Array.from({length: 16}, (_, i) => ({id: String(i + 1), label: sourceLabel(i + 1)}))
    ], String(D.section ?? ""), value => sourceChooseSection(value ? +value : null)),
    sourceSelect("source-set-select", T("source.selection.source_set"), [
      {id: "", label: T("source.labels.return_set")},
      ...S.shell.sets.map(set => ({id: set.id, label: set.label, disabled: !set.usable}))
    ], D.override, value => sourceChangeTarget("set", value)));
  const basis = d ? h("div", {class: "source-basis"},
    h("p", null, T("source.selection.source_set"), ": ", h("strong", null, d.set?.label || T("context.unavailable")),
      " — ", UI.source.origin[d.set?.source] || T("context.unavailable"), d.set?.note ? ` — ${d.set.note}` : ""),
    h("p", null, T("source.selection.next_set"), ": ", S.shell.sets.find(set => set.id === S.ctx.set)?.label || T("context.unavailable")),
    h("p", null, T("source.labels.answer"), ": ", shellKeyLabel(d.key)),
    shellKeyMismatch(d.key) ? h("p", {class: "answer-mismatch"}, shellKeyMismatch(d.key)) : null) : null;
  const table = D.run ? sourceCriteriaTable() : null;
  return [sourceStateNote(), D.raw ? h("p", null, T("source.raw.title")) : null, controls, basis,
    d?.warnings?.map(warning => h("p", {class: "source-warning page-text"}, warning)),
    d && D.run && !d.has_gold ? h("p", null, T("source.empty.answer")) : null,
    !table && !D.section ? h("p", null, T("source.labels.choose_scope")) : null, table,
    D.runError ? h("p", {class: "muted"}, T("steps.source.run_failed")) : null,
    h("p", {class: "source-links"}, sourceButton("source-raw-open", T("source.selection.raw"), sourceRaw, {class: "text-button"}), " ",
      sourceButton("source-reload", T("source.reload"), sourceReload, {class: "text-button"}))];
}
// ③ 다시 시험으로 보내기: 넘길 것을 읽어 본다. 시험을 시작하지 않는다.
function sourceStageSend() {
  const D = S.source, v = sourceSelected(), only = D.selection?.side === "silver_only", lines = sourceSelectedLines(v);
  const run = D.list.find(item => item.name === D.run);
  const fact = (label, ...value) => h("div", null, h("dt", null, label), h("dd", {class: "big-value"}, value));
  const openable = S.jobs.opts ? jobsDocs().find(doc => doc.doc_id === D.doc) : null;
  return [jobsSetNotice(), h("div", {class: "step-card"}, h("dl", {class: "source-send"},
    fact(T("source.labels.doc"), D.doc), fact(T("source.labels.section"), sourceLabel(D.section)),
    D.run ? fact(T("source.labels.run"), run?.label?.title || D.run) : null,
    v ? fact(T("source.labels.field"), sourceFieldName(v)) : null,
    v ? fact(T("source.labels.result"), only ? T("common.none") : sourceValueText(v, v.text)) : null,
    v ? fact(T("source.labels.answer"), sourceValueText(v, only ? v.text : v.silver?.text)) : null,
    v ? fact(T(only ? "source.missing.evidence_title" : "steps.source.evidence_title"), lines.length
      ? lines.map(line => h("span", {class: "page-text"}, T(only ? "source.missing.location" : "source.evidence.location", {page: line.page, line_no: line.no})))
      : T(only ? "source.doc.no_guess" : "source.unlinked.title")) : h("p", null, T("steps.source.send_no_value")))),
    openable && !jobsAllowed(openable, "try") ? h("p", {role: "status"}, openable.run_reason?.try || T("jobs.no_runnable.todo")) : null,
    D.section != null ? h("p", null, T("source.retest.target", {doc: D.doc, section: D.section})) : null];
}
function sourceRenderTop() {
  const D = S.source, el = document.getElementById("source-top"), step = sourceStep();
  el.setAttribute("aria-busy", String(D.loading));
  el.hidden = step === "compare" && !!D.data;
  coreReplace(el, step === "choose" ? sourceStageChoose() : !D.data ? sourceStateNote() : step === "send" ? sourceStageSend() : []);
  sourceRenderFrame(step);
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
// ── 행 묶음: 판정은 API가 정한 칸의 kind를 그대로 쓴다 ──
function sourceRows(data = S.source.data) { return data?.row_groups || []; }
function sourceRowOf(path, only, data = S.source.data) {
  // 두 목록의 번호는 서로 다른 문서의 번호라 경로만으로 찾으면 안 된다.
  return sourceRows(data).find(group => group.cells.some(cell => cell.path === path && (cell.side === "silver_only") === only)) || null;
}
function sourceCurrentRow() { return sourceRows().find(group => group.id === S.source.rowId) || null; }
function sourceIsCurrentRow(entry) { return entry.doc === S.source.doc && entry.group.id === S.source.rowId; }
function sourceCellInScope(cell) {
  const D = S.source;
  return SOURCE_KINDS.includes(cell.kind) && (!D.item || (cell.items || []).includes(D.item)) && (D.section == null || cell.section === +D.section);
}
function sourceRowEntries() {
  const D = S.source;
  if (!D.data || !D.run) return [];
  return sourceProblemDocs().flatMap(doc => {
    const data = doc === D.doc ? D.data : D.problemData.get(doc);
    return data?.has_gold ? sourceRows(data).flatMap(group => {
      const cells = group.cells.filter(sourceCellInScope);
      return cells.length ? [{doc, data, group, cells}] : [];
    }) : [];
  });
}
// 화면에 보이는 순서의 행. 줄이나 서랍에서 고른 행은 문제가 없어도 목록에 남긴다.
function sourceVisibleRows() {
  const D = S.source, rows = sourceRowEntries(), current = sourceCurrentRow();
  const shown = D.filter === "all" ? rows : rows.filter(row => row.cells.some(cell => cell.kind === D.filter));
  return current && D.filter === "all" && !rows.some(sourceIsCurrentRow) ? [{doc: D.doc, data: D.data, group: current, cells: []}, ...shown] : shown;
}
function sourceRowSummary(entry) {
  const parts = SOURCE_KINDS.map(kind => [kind, entry.cells.filter(cell => cell.kind === kind).length]).filter(([, count]) => count);
  return parts.length ? parts.map(([kind, count]) => T("steps.source.row_kind", {kind: T(`source.kinds.${kind}`), count})).join(" · ") : T("source.kinds.same");
}
function sourceFilterCounts() {
  const D = S.source;
  return D.docAll ? sourceCriterion()?.counts : sourceCriterionDocs().find(doc => doc.doc_id === D.doc)?.counts;
}
// 뜻은 말풍선에 있다. 안내 도움말과 같은 용어 사전 글이다.
function sourceKindLegend() {
  const terms = {wrong: "wrong", made: "invented", missing: "missing"};
  return Object.keys(terms).map((kind, i) => [i ? " · " : "", term(terms[kind], T(`source.kinds.${kind}`)), ": ", T(`steps.source.kind_notes.${kind}`)]);
}
function sourceRenderProblems() {
  const el = document.getElementById("source-values"), D = S.source;
  el.setAttribute("data-guide", "s02-diff-values");
  const previous = document.getElementById("source-problem-list");
  if (previous && previous.offsetParent !== null) D.problemScroll = previous.scrollTop || 0;
  // 행 목록은 ②에만 있다. ①은 시안대로 항목 표 하나다.
  el.hidden = !D.data || !D.run || sourceStep() !== "compare";
  if (el.hidden) { el.replaceChildren(); return; }
  const docs = sourceProblemDocs(), rows = sourceVisibleRows(), counts = sourceFilterCounts();
  // 고른 행은 언제나 그린다. 목록이 길면 고른 행이 든 묶음만 그려 단추 수를 줄인다.
  const at = rows.findIndex(sourceIsCurrentRow);
  if (at >= 0 && (at < D.rowStart || at >= D.rowStart + D.rowLimit)) { D.rowStart = Math.floor(at / SOURCE_ROW_BATCH) * SOURCE_ROW_BATCH; D.rowLimit = SOURCE_ROW_BATCH; }
  if (D.rowStart >= rows.length) D.rowStart = 0;
  const drawn = rows.slice(D.rowStart, D.rowStart + D.rowLimit), after = rows.length - D.rowStart - drawn.length;
  const button = entry => {
    const on = sourceIsCurrentRow(entry);
    return sourceButton(null, [h("b", {class: "big-value"}, entry.group.title),
      h("small", null, sourceRowSummary(entry), on ? ` · ${T("source.labels.selected")}` : "")],
      () => sourceOpenRow(entry), {class: "source-problem", "data-row-id": entry.group.id, "aria-pressed": String(on)});
  };
  coreReplace(el, h("div", {class: "source-rows-head"}, h("h2", null, docs.length === 1 ? T("steps.source.list_title_one", {doc: docs[0]}) : T("steps.source.list_title", {count: docs.length})),
      D.item ? h("p", {class: "issue-meta"}, T("source.labels.criterion", {item: D.item})) : null),
    h("div", {class: "source-filters", role: "group", "aria-label": T("steps.source.filter_a11y")}, ["all", ...SOURCE_KINDS].map(kind =>
      sourceButton(`source-filter-${kind}`, kind === "all" ? T("source.filter.all_values")
        : num(counts?.[UI.score.cause_keys[kind]]) ? T(`source.filter.${kind}`, {count: counts[UI.score.cause_keys[kind]]})
        : T(`source.kinds.${kind}`),
        () => { D.filter = kind; D.rowStart = 0; D.rowLimit = SOURCE_ROW_BATCH; sourceRenderProblems(); sourceRenderFrame(); document.getElementById(`source-filter-${kind}`).focus(); }, {"aria-pressed": String(D.filter === kind)}))),
    h("p", {class: "source-kinds"}, sourceKindLegend()),
    h("div", {id: "source-problem-list"}, D.rowStart > 0 ? sourceButton("source-rows-before", T("steps.source.earlier_rows", {count: D.rowStart}), () => {
      const open = Math.min(SOURCE_ROW_BATCH, D.rowStart);
      D.rowStart -= open; D.rowLimit += open; sourceRenderProblems();
      (document.getElementById("source-rows-before") || document.getElementById("source-problem-list"))?.focus({preventScroll: true});
    }, {class: "text-button"}) : null, docs.map(doc => {
      const own = drawn.filter(entry => entry.doc === doc), all = rows.filter(entry => entry.doc === doc).length;
      if (!own.length && !D.problemErrors.has(doc)) return null;
      return h("section", {"data-problem-doc": doc}, h("h3", {class: "source-document"}, T("steps.source.doc_rows", {doc, count: all})),
        D.problemErrors.has(doc) ? h("p", {role: "status"}, T("steps.source.partial")) : null, own.map(button));
    }),
    after > 0 ? sourceButton("source-rows-more", T("steps.source.more_rows", {count: after}), () => {
      D.rowLimit += SOURCE_ROW_BATCH; sourceRenderProblems();
      document.getElementById("source-rows-more")?.focus({preventScroll: true});
    }, {class: "text-button"}) : null),
    !rows.length ? h("p", null, T(D.data.has_gold ? "source.empty.problems" : "source.empty.answer")) : null);
  // 화면에 붙기 전에 넣은 스크롤 위치는 브라우저가 버린다.
  const list = document.getElementById("source-problem-list");
  list.scrollTop = D.problemScroll;
  sourceRevealRow(list);
}
// 고른 행이 목록 바깥에 있을 때만 목록 안에서 움직인다. 창은 움직이지 않는다.
function sourceRevealRow(list) {
  const row = list.querySelector('[aria-pressed="true"]');
  if (!row) return;
  const box = row.getBoundingClientRect(), area = list.getBoundingClientRect();
  if (box.top < area.top || box.bottom > area.bottom) {
    list.scrollTop = (list.scrollTop || 0) + box.top - area.top - (list.clientHeight || 0) / 3;
    S.source.problemScroll = list.scrollTop;
  }
}
// 칸 이름. 줄 번호는 떼고 찾는다. 예: statements[1], contacts[0].type
function sourceFieldKey(v) { return (v.field || "").replace(/\[\d+\]/g, ""); }
function sourceFieldName(v, data = S.source.data) {
  const key = sourceFieldKey(v);
  const named = key.split(".").reduce((item, part) => item?.[part], UI.source.field_names);
  return UI.source.value_titles[v.table]?.[key] || data?.ui_text?.value_field_labels?.[key] || (typeof named === "string" ? named : null)
    || UI.source.fields[key] || UI.source.table_names[v.table] || T("source.labels.field");
}
// 코드 값은 쉬운 이름과 함께 보인다. 이름표에 없는 값은 원래 표기 그대로다.
function sourceValueText(v, text) {
  if (text == null) return T("common.none");
  const key = sourceFieldKey(v), name = key === "comp_ref" && text === "MIX" ? T("source.rows.mix") : UI.source.row_parts[key]?.[text];
  if (!name) return text;
  return name.includes(text) ? name : T("source.labels.code_value", {name, code: text});
}
async function sourcePickProblem(doc, v, only, user = true) {
  const D = S.source, filter = D.filter, key = S.ctx.key, choice = user ? ++D.choice : D.choice;
  if (doc !== D.doc) {
    D.doc = doc;
    const loading = sourceLoad(), request = D.request;
    await loading;
    if (D.doc !== doc || !D.data || request !== D.request || key !== S.ctx.key || choice !== D.choice) return;
    D.filter = filter;
  }
  const current = only ? D.only[v.path] : D.values[v.path];
  if (current) sourcePick(current, only ? "silver_only" : "result", user, "row");
}
// 행을 열면 그 행에서 먼저 볼 칸을 고른다: 지금 범위의 문제 칸, 근거 줄이 있는 칸, 틀림·만듦·못 뽑음 순서.
function sourceOpenRow({doc, data, group, cells}, user = true) {
  const from = cells.length ? cells : group.cells;
  const entries = from.map(cell => ({v: (cell.side === "silver_only" ? data.silver_only : data.values).find(v => v.path === cell.path),
    only: cell.side === "silver_only", kind: cell.kind})).filter(entry => entry.v);
  const found = sourceChooseProblem(entries, "mismatch", data) || entries[0];
  return found ? sourcePickProblem(doc, found.v, found.only, user) : null;
}
function sourceTip(v, side) {
  return S.source.data.ui_text?.value_tips?.[side]?.[v.path]?.join("\n") || null;
}
function sourceValueButton(v, side) {
  const only = side === "silver_only", silver = side === "silver";
  return sourceButton(null, h("span", {class: "big-value"}, sourceValueText(v, silver ? v.silver?.text : v.text)),
    // 서랍의 표에서 고르면 서랍을 닫고 그 행을 연다.
    () => { drawerClose(); sourcePick(v, side); }, {class: `source-value source-${sourceKind(v, only)}`, "data-source-path": v.path, "data-side": side,
      "data-tip": sourceTip(v, side), "aria-pressed": "false"});
}
// 문서 전체 표. 단추가 많아 서랍에서 표 열기를 누른 뒤에만 만든다. 서랍 안에서는 접지 않는다.
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
  return [...groups].sort(([a], [b]) => (a === "?" ? 99 : +a) - (b === "?" ? 99 : +b)).map(([section, tables]) =>
    h("div", {"data-source-section": section, class: "drawer-section"}, h("h3", null, sourceLabel(section === "?" ? null : section),
      h("small", {class: "source-section-summary"}, d.ui_text?.sections?.[section] || "")),
      [...tables].map(([table, rows]) => sourceTable(table, rows))));
}
function sourceTable(table, rows) {
  const body = [...rows].flatMap(([row, entries]) => {
    const heading = row.length > 1 ? h("tr", null, h("th", {colspan: 3, scope: "rowgroup"},
      T(row[0] === "s" ? "source.labels.only_row" : "source.labels.row", {row: +row.slice(1) + 1}))) : null;
    return [heading, ...entries.map(({v, only}) => h("tr", null,
      h("th", {scope: "row", class: "technical"}, sourceFieldName(v),
        h("small", {class: "raw"}, v.field || "", " · ", v.path)),
      h("td", null, only ? T("common.none") : sourceValueButton(v, "result")),
      h("td", null, sourceValueButton(v, only ? "silver_only" : "silver"))))];
  });
  return [h("h4", null, UI.source.table_names[table] || table, h("span", {class: "raw"}, ` (${table}) `),
      T("source.labels.cells", {count: [...rows.values()].flat().length})),
    h("table", null, h("thead", null, h("tr", null,
      ["field", "result", "answer"].map(key => h("th", {scope: "col"}, T(`source.labels.${key}`))))),
      h("tbody", null, body))];
}

function sourceSelectValue(v, side) {
  const D = S.source, only = side === "silver_only";
  D.selection = {path: v.path, side}; D.section = v.section ?? D.section;
  const row = sourceRowOf(v.path, only);
  D.rowId = row?.id ?? null;
  // 다른 입구가 고른 행을 필터가 가리지 않게 한다.
  if (row && D.filter !== "all" && !row.cells.some(cell => cell.kind === D.filter)) D.filter = "all";
  D.selectedPaths = new Set(only ? [] : [v.path]);
  D.selectedLines = new Set((v.lines || []).filter(id => D.line[id]));
  const first = (v.lines || []).map(id => D.line[id]).find(line => line && D.data.pages.includes(line.page));
  if (first) D.page = first.page;
  D.gone = false;
}
function sourceSelected() {
  const D = S.source;
  if (!D.data) return null;
  return D.selection?.side === "silver_only" ? D.only[D.selection.path] : D.values[D.selection?.path];
}
function sourcePick(v, side = "result", user = true, from = "cell") {
  const D = S.source, oldPage = D.page, drawn = !!document.getElementById("source-lines");
  if (user) ++D.choice;
  sourceSelectValue(v, side); D.step = "compare";
  sourceRenderTop(); sourceRenderProblems(); sourceRenderSelection();
  // 같은 쪽이면 그림을 다시 받지 않는다.
  if (!drawn || oldPage !== D.page) sourceRenderPage(); else sourceRenderLines();
  sourceRenderFrame(); sourceRemember();
  sourceScrollLine([...D.selectedLines].find(id => D.line[id].page === D.page));
  if (user) {
    const row = document.getElementById("source-problem-list")?.querySelector('[aria-pressed="true"]');
    (from === "row" && row ? row : sourceValueElement(v.path, side))?.focus({preventScroll: true});
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
// ② 위쪽: 한 행의 칸들. 높이는 CSS의 격자 줄이 정해 값이 있는 줄과 없는 줄에서 같다.
function sourceRowTable(group) {
  const D = S.source;
  return h("table", {class: "source-row-table"},
    h("thead", null, h("tr", null, ["field", "result", "answer"].map(key => h("th", {scope: "col"}, T(`source.labels.${key}`))),
      h("th", {scope: "col"}, T("steps.source.col_result")))),
    // 문제가 있는 칸을 먼저 보인다. 같은 칸은 아래에 둔다.
    h("tbody", null, [...group.cells].sort((a, b) => SOURCE_KINDS.includes(b.kind) - SOURCE_KINDS.includes(a.kind)).map(cell => {
      const only = cell.side === "silver_only", v = only ? D.only[cell.path] : D.values[cell.path];
      return v ? h("tr", {class: "source-cell-row"}, h("th", {scope: "row"}, sourceFieldName(v)),
        h("td", null, only ? T("common.none") : sourceValueButton(v, "result")),
        h("td", null, sourceValueButton(v, only ? "silver_only" : "silver")),
        h("td", {class: `source-${cell.kind}`}, h("span", {class: "source-cell-state"}, T(`source.kinds.${cell.kind}`)))) : null;
    })));
}
function sourceValueNote(v, only) {
  const D = S.source, lines = sourceSelectedLines(v);
  const unit = D.section === 8 ? h("p", {class: "muted"}, term("exposure"), " — ", term("concentration_unit", T("source.unit_first_use"))) : null;
  if (!v) return h("div", {class: "source-value-note", "data-guide": "s02-evidence"}, sourceCurrentRow() && !D.selection ? h("p", null, T("source.labels.choose")) : null,
    D.selection?.line ? h("p", null, D.selection.line, " — ", T("source.labels.line_values", {count: D.selectedPaths.size})) : null, unit);
  return h("div", {class: "source-value-note", "data-guide": "s02-evidence"},
    h("h3", null, T(only ? "source.missing.evidence_title" : "steps.source.evidence_title")),
    lines.map(line => h("div", {class: `selected-line source-evidence${only ? " source-estimated" : ""}`},
      h("p", null, T(only ? "source.missing.location" : "source.evidence.location", {page: line.page, line_no: line.no})), h("p", null, line.text))),
    h("p", null, T(lines.length ? (only ? "source.doc.guess" : "source.evidence.recorded") : only ? "source.doc.no_guess" : "source.unlinked.title")),
    !lines.length ? h("p", null, T("source.unlinked.no_fallback")) : null,
    !lines.length && D.section ? h("p", null, T("source.unlinked.todo", {section: D.section})) : null,
    lines.some(line => !line.bbox) ? h("p", null, T("source.page.no_coordinates")) : null,
    h("p", null, T(`source.comparison.${sourceKind(v, only)}`), " ", T("source.value.draft_warning")), unit);
}
// 표가 길어도 근거 위치는 머리에 늘 보인다. 추정 줄은 추정이라고 쓴다.
function sourceEvidenceWhere(v, only) {
  const lines = sourceSelectedLines(v);
  if (!lines.length) return T(only ? "source.doc.no_guess" : "source.unlinked.title");
  const where = lines.map(line => T(only ? "source.missing.location" : "source.evidence.location", {page: line.page, line_no: line.no})).join(", ");
  const mark = lines.some(line => !line.bbox) ? ` ${T("source.page.no_coordinates")}` : "";
  return `${T(only ? "source.missing.evidence_title" : "steps.source.evidence_title")}: ${where}.${mark}`;
}
function sourceRenderSelection() {
  const D = S.source, d = D.data, el = document.getElementById("source-selection"), show = sourceStep() === "compare" && !!d;
  el.hidden = !show;
  if (!show) { el.replaceChildren(); return; }
  const group = sourceCurrentRow(), v = sourceSelected(), only = D.selection?.side === "silver_only";
  const rows = sourceVisibleRows(), at = rows.findIndex(sourceIsCurrentRow);
  const problems = group ? group.cells.filter(cell => SOURCE_KINDS.includes(cell.kind)).length : 0;
  // 다른 행을 열면 맨 위부터 보인다. 같은 행의 다른 칸을 고를 때는 보던 자리를 지킨다.
  if (D.shownRow !== D.rowId) { D.shownRow = D.rowId; el.scrollTop = 0; }
  coreReplace(el, h("div", {class: "source-row-head"},
      h("h2", {class: "big-value"}, group?.title ? termText(group.title) : T(D.run ? "source.labels.choose" : "source.raw.title")),
      group ? h("small", null, T("steps.source.row_summary", {doc: D.doc, section: group.section ?? T("context.unavailable"), total: group.cells.length, problems}),
        at >= 0 ? ` · ${T("steps.source.row_position", {total: rows.length, index: at + 1})}` : "") : null,
      sourceDetailsButton()),
    v ? h("p", {class: "source-row-evidence"}, sourceEvidenceWhere(v, only)) : null,
    d.warnings?.map(warning => h("p", {class: "source-warning page-text"}, warning)),
    shellKeyMismatch(d.key) ? h("p", {class: "answer-mismatch"}, shellKeyMismatch(d.key)) : null,
    d.set?.note ? h("p", {class: "source-warning"}, d.set.note) : null,
    D.gone ? h("p", {role: "status"}, T("source.value_gone.title"), " ", T("source.value_gone.returned", {section: D.section})) : null,
    group ? sourceRowTable(group) : null, sourceValueNote(v, only),
    (d.legend || []).length ? h("div", {class: "source-legend"}, d.legend.map(entry => h("span", {class: "source-legend-entry"},
      // 세 상태는 글자로 구분하고 색 칸은 선택 표시 하나다 (PR #123).
      entry.color ? h("span", {class: "source-chip", "aria-hidden": "true", style: `background:${entry.color}`}) : null, entry.label))) : null);
  sourceMark();
  sourceRevealCell(el);
}
// 낮은 창에서는 표가 비교 영역보다 길다. 고른 칸이 영역 밖이면 영역 안에서만 움직인다. 창은 움직이지 않는다.
function sourceRevealCell(panel) {
  const cell = panel.querySelector('.source-value[aria-pressed="true"]')?.closest("tr");
  if (!cell) return;
  const box = cell.getBoundingClientRect(), area = panel.getBoundingClientRect();
  if (box.top < area.top || box.bottom > area.bottom) panel.scrollTop = (panel.scrollTop || 0) + box.top - area.top - (panel.clientHeight || 0) / 3;
}
// ── 자세히 서랍: 열 때만 그린다. 전체 표는 서랍 안의 단추를 누른 뒤에 만든다 ──
function sourceOpenDetails() {
  drawerOpen({title: T("steps.source.details_title"), trigger: document.getElementById("source-details-open"), render: sourceRenderDrawer});
}
function sourceRenderDrawer(body) {
  const D = S.source, d = D.data, v = d ? sourceSelected() : null, coverage = d?.silver_lines;
  const items = v?.items || [];
  const raw = D.error?.message;
  const table = h("div", {id: "source-structure", tabindex: "-1"}, h("button", {id: "source-structure-open", type: "button", onclick: () => {
    coreReplace(table, sourceStructure());
    table.focus();
  }}, T("steps.source.doc_table_open")));
  const span = D.section != null ? d?.sections?.[D.section] : null;
  // 쉬운 요약을 먼저 쓰고 프로그램용 기록은 맨 끝에 둔다.
  coreReplace(body,
    d ? serversDrawerSection(T("source.structure.doc_comparison"), h("p", null, T("source.doc.counts", {
      total: d.values.length, different: d.has_gold ? d.values.filter(value => !value.silver?.same).length : T("context.unavailable"), missing: d.silver_only.length})),
      h("p", null, T("source.labels.matched_count", {count: d.has_gold ? d.values.filter(value => value.silver?.same).length : T("context.unavailable")})), table) : null,
    coverage ? serversDrawerSection(T("source.estimation.expand"),
      h("p", null, T("source.estimation.coverage", {total: coverage.total, matched: coverage.found})),
      coverage.basis === "text_match" ? h("p", null, T("source.estimation.method")) : null,
      h("p", null, T("source.estimation.count_meaning")), h("p", null, T("source.estimation.verify"))) : null,
    d ? serversDrawerSection(T("steps.source.howto_title"), h("p", null, d.ui_text?.howto || T("source.doc.howto"))) : null,
    v ? serversDrawerSection(T("steps.source.scope_title"), h("p", null, items.length ? T("steps.source.scope_items", {items: items.map(scoreItemName).join(", ")}) : T("steps.source.scope_none")),
      h("p", null, T("steps.source.scope_note"))) : null,
    serversDrawerSection(T("source.selection.eval_reason"), S.shell.sets.map(set => h("div", null,
      h("p", null, set.label, set.reason ? ` — ${set.reason}` : ""),
      h("p", null, T("source.locked.counts", {dev: set.counts?.dev ?? 0, locked: set.counts?.eval_locked ?? 0, outside: set.counts?.outside ?? 0})),
      (set.docs || []).filter(doc => doc.locked).map(doc => h("p", {class: "raw"}, doc.doc_id, " — ", doc.reason))))),
    v ? serversDrawerSection(T("steps.source.raw_value_title"), h("div", {class: "source-raw"}, h("p", {class: "technical"}, v.path),
      h("pre", {class: "technical"}, JSON.stringify(D.selection.side === "silver" ? v.silver?.value : v.value, null, 2) ?? T("common.none")))) : null,
    serversDrawerSection(T("steps.source.target_title"), h("p", {class: "technical"}, D.run || T("source.raw.title"), D.doc ? ` / ${D.doc}` : ""),
      span ? h("p", {class: "technical"}, T("source.labels.range", {start: span.start, end: span.end})) : null),
    raw ? serversDrawerSection(T("common.raw_error_title"), h("pre", {class: "technical"}, raw)) : null,
    [...D.problemErrors].map(([doc, error]) => serversDrawerSection(T("common.raw_error_title"), h("p", {class: "technical"}, doc), h("pre", {class: "technical"}, error.message))));
}
function sourceScrollLine(id) {
  const line = [...document.querySelectorAll("#source-page [data-line]")].find(el => el.dataset.line === id);
  const box = document.getElementById("source-lines");
  if (line && box) {
    box.scrollTop = (box.scrollTop || 0) + line.getBoundingClientRect().top - box.getBoundingClientRect().top - (box.clientHeight || 0) / 3;
    S.source.scroll[S.source.page] = box.scrollTop;
  }
}
function sourceGoSection(section) {
  const D = S.source; D.section = section == null ? null : +section;
  const span = D.data?.sections?.[section];
  const first = D.line[span?.start];
  if (first && D.data.pages.includes(first.page)) D.page = first.page;
  sourceRenderAll();
  if (first) sourceScrollLine(first.id);
}
function sourceChooseSection(section) {
  const D = S.source, page = D.page;
  ++D.choice;
  sourceResetSelection(); D.page = page; D.item = null;
  sourceGoSection(section); sourceRemember(); sourceLoadProblems();
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
  // 그 줄을 근거로 쓴 값의 행을 연다. 근거로 쓴 값이 없으면 보던 행에 머문다.
  const row = sourceCurrentRow()?.cells.some(cell => paths.includes(cell.path) && cell.side === "result") ? null : paths[0] ? sourceRowOf(paths[0], false) : null;
  if (row) {
    D.rowId = row.id;
    if (D.filter !== "all" && !row.cells.some(cell => cell.kind === D.filter)) D.filter = "all";
  }
  sourceRenderSelection(); sourceRenderProblems(); sourceRenderLines(); sourceRenderFrame();
  sourceScrollLine(id);
  document.querySelector(`#source-lines [data-line="${id}"]`)?.focus({preventScroll: true});
  sourceRemember();
  for (const path of paths) sourceEvidence(D.values[path]);
}
function sourceDrawBoxes(img, svg) {
  const D = S.source;
  // 다시 그리면 그림이 새로 만들어진다. 버려진 그림의 load가 늦게 돌면 새 그림 칸의 위치를 되돌린다.
  if (!img.isConnected || !img.naturalWidth || !img.naturalHeight) return;
  svg.setAttribute("viewBox", `0 0 ${img.naturalWidth} ${img.naturalHeight}`);
  const lines = [...D.selectedLines].map(id => D.line[id]).filter(line => line?.page === D.page &&
    Array.isArray(line.bbox) && line.bbox.length === 4 && line.bbox.every(Number.isFinite));
  svg.replaceChildren(...lines.map(({bbox: [x0, y0, x1, y1]}) => s("rect", {
    x: x0, y: y0, width: Math.max(0, x1 - x0), height: Math.max(0, y1 - y0),
    class: D.selection?.side === "silver_only" ? "source-box source-estimated" : "source-box"})));
  // 그림 칸 안에서만 움직여 표시한 줄을 보인다.
  const box = document.getElementById("source-image");
  if (box && lines[0]) box.scrollTop = lines[0].bbox[1] * (img.clientWidth || 0) / img.naturalWidth - (box.clientHeight || 0) / 3;
}
// 기본은 연결 값이 있는 줄과 고른 줄 주변이다(D3). 원문만 볼 때는 고를 값이 없어 쪽 전체다.
function sourcePageLines(page) {
  const D = S.source, d = D.data, all = d.lines.filter(line => line.page === page);
  if (D.allLines || !D.run) return all;
  const near = new Set();
  all.forEach((line, index) => {
    if (D.selectedLines.has(line.id)) all.slice(Math.max(0, index - SOURCE_NEAR_LINES), index + SOURCE_NEAR_LINES + 1).forEach(item => near.add(item.id));
  });
  return all.filter(line => near.has(line.id) || (d.line_index[line.id] || []).length);
}
function sourceRenderLines() {
  const D = S.source, d = D.data, list = document.getElementById("source-lines"), page = D.page;
  if (!list) return;
  const whole = d.lines.some(line => line.page === page), lines = whole ? sourcePageLines(page) : [];
  let band = null;
  coreReplace(list, lines.length ? lines.map(line => {
    const count = (d.line_index[line.id] || []).length, section = D.sections[line.id];
    const head = section && section !== band ? h("span", {class: "source-band"}, sourceLabel(section)) : null;
    band = section ?? band;
    return sourceButton(null, [head, h("span", {class: "raw"}, line.no), h("span", {class: "page-text"}, line.text),
      count ? h("small", null, T("source.labels.line_values", {count})) : null,
      h("span", {class: "source-line-state"})], () => sourcePickLine(line.id),
      {class: "source-line", "data-line": line.id, "aria-pressed": "false"});
  }) : h("p", null, T(whole ? "steps.source.no_linked_lines" : "source.empty.lines")));
  const picked = lines.find(line => D.selectedLines.has(line.id));
  document.getElementById("source-lines-title").textContent = picked
    ? T("steps.source.lines_near", {page, line: picked.no}) : T("steps.source.lines_title", {page});
  // 화면에 붙기 전에 넣은 스크롤 위치는 브라우저가 버린다.
  list.scrollTop = D.scroll[page] || 0;
  sourceMark();
}
function sourceRenderPage() {
  const D = S.source, d = D.data, el = document.getElementById("source-page"), show = sourceStep() === "compare" && !!d;
  el.setAttribute("data-guide", "s02-lines");
  el.hidden = !show;
  if (!show) { D.draw = null; el.replaceChildren(); return; }
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
  const list = h("div", {id: "source-lines", class: "source-lines"});
  list.addEventListener("scroll", () => { D.scroll[page] = list.scrollTop; });
  const toggle = D.run ? sourceButton("source-lines-toggle", T(D.allLines ? "steps.source.near_lines" : "steps.source.all_lines"), () => {
    D.allLines = !D.allLines; sourceRenderPage();
    sourceScrollLine([...D.selectedLines].find(id => D.line[id]?.page === D.page));
    document.getElementById("source-lines-toggle")?.focus({preventScroll: true});
  }, {class: "text-button"}) : null;
  const pickers = h("div", {class: "source-page-pickers"},
    sourceSelect("source-page-select", T("source.labels.page"), d.pages.map(p => ({id: String(p), label: T("source.labels.page_name", {page: p})})), String(page ?? ""), value => sourcePage(+value)),
    sourceSelect("source-section-select", T("source.labels.section"), Array.from({length: 16}, (_, i) => ({id: String(i + 1), label: sourceLabel(i + 1)})), String(D.section ?? ""), value => sourceChooseSection(+value)));
  // 부분을 찾지 못했을 때만 본문에 알린다. 줄 구간은 기록이라 서랍에 둔다.
  const range = D.section && !span ? h("p", {class: "technical"}, T("source.section_unknown.title", {section: D.section})) : null;
  coreReplace(el, hasPage ? h("div", {class: "source-page-grid"},
    h("section", {class: "source-panel"}, h("div", {class: "source-panel-head"}, h("h3", null, T("steps.source.image_title", {page})), pickers), range, h("div", {id: "source-image", class: "source-image"}, wrap)),
    h("section", {class: "source-panel"}, h("div", {class: "source-panel-head"}, h("h3", {id: "source-lines-title"}), toggle), list))
    : [pickers, range, h("p", {class: "source-state"}, T("source.empty.pages"))]);
  sourceRenderLines();
}
