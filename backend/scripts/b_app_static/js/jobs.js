"use strict";

// 폼과 지시문은 메모리에만 둔다. 시작 당시 조건은 서버의 target을 읽는다.
S.jobs = {opts: null, optionsError: null, optionsRecovered: false, pollError: null, recovered: false,
  t: {doc: null, model: null, secs: new Set([1]), all: false, base: "", dry: false, edit: false, dirty: false, text: "", textFor: null},
  r: {model: null, docs: null, repeat: 1, name: "", edited: false}, c: {picked: [], labels: {}, title: ""},
  list: [], running: [], runs: [], runsError: null, runsKey: null, timer: null, polling: null, loadingOptions: null,
  watch: null, result: null, resultStatus: null, resultLoaded: false, resultError: null, resultRequest: 0,
  observed: new Set(), emitted: new Set(), terminal: new Set(), log: null, expanded: {},
  busy: null, message: {}, confirm: null, initialized: false, defaultsApplied: false,
  dialogReady: false, confirmTrigger: null, promptRequest: 0, promptBusy: false,
  promptAttempt: null, promptError: null, promptPending: null, selected: null};
const jobsStages = [["input", "input"], ["prompt", "prompt"], ["raw_answer", "raw_answer"],
  ["parsed", "parsed"], ["converted", "to21"], ["score", "score"]];
function jobsButton(id, key, action, disabled = false, primary = false) {
  return h("button", {id, type: "button", disabled, class: primary ? "primary" : null, onclick: action}, T(key));
}
function jobsNote(text, attrs = {}) { return h("p", attrs, text); }
function jobsValue(value) {
  if (value == null) return T("common.none");
  if (typeof value === "boolean") return T(value ? "source.value.true" : "source.value.false");
  return typeof value === "object" ? JSON.stringify(value, null, 1) : String(value);
}
function jobsFocusValue(value, text) {
  if (value == null) return T("common.none");
  if (typeof value?.raw === "string" && value.raw.trim()) return value.raw;
  if (typeof text === "string" && text.trim()) return text;
  if (Array.isArray(value)) return value.map(item => jobsFocusValue(item)).join(", ");
  if (typeof value === "object") return value.value != null
    ? [jobsFocusValue(value.value), value.unit].filter(part => part != null && part !== "").join(" ") : T("context.unavailable");
  return jobsValue(value);
}
function jobsPre(value) { return h("pre", {class: "job-log technical"}, value == null ? T("common.none") : jobsValue(value)); }
function jobsDetails(id, title, ...kids) {
  const open = S.jobs.expanded[id] ?? (S.cards[id] === false);
  const d = h("details", {id, open: open || null, ontoggle: e => {
    S.jobs.expanded[id] = e.target.open; S.cards[id] = !e.target.open; coreWrite("b_app.cards", S.cards);
  }},
    h("summary", null, title), h("div", {class: "job-details"}, kids));
  return d;
}
function jobsField(id, label, help, control) {
  control.setAttribute("id", id);
  if (help) control.setAttribute("aria-describedby", `${id}-help`);
  return h("div", {class: "job-field"}, h("label", {for: id}, label), control,
    help ? h("small", {id: `${id}-help`, class: "muted"}, help) : null);
}
function jobsRunLabel(run) { return run.label?.title || (typeof run.label === "string" ? run.label : run.name); }
function jobsSet() { return S.jobs.opts?.sets?.find(set => set.id === S.ctx.set); }
function jobsDocs() { return jobsSet()?.usable === false ? [] : jobsSet()?.docs || []; }
function jobsAllowed(doc, kind) { return doc?.runnable?.[kind] === true; }
function jobsModel(tag) { return S.jobs.opts?.models?.find(model => model.tag === tag); }
function jobsModelLabel(tag) { return UI.context.models?.[tag] || serversLabel(jobsModel(tag) || serversModel(tag) || {tag}); }
function jobsDraftModel(model) { return model.watched === false || ["gpt", "claude"].includes(model.tag); }
function jobsDefaultModel(previous) {
  const models = S.jobs.opts?.models || [];
  return (models.find(model => model.tag === previous) || models.find(model => model.watched === true)
    || models.find(model => model.watched == null && !jobsDraftModel(model)))?.tag || null;
}
function jobsModelDifference(tag, previous) {
  return previous && tag !== previous ? jobsNote(T("jobs.focus.model_difference", {model: jobsModelLabel(previous)})) : null;
}
function jobsReady(tag) { return !S.jobs.optionsError && jobsModel(tag)?.connected === true; }
function jobsSingle() { return !S.jobs.t.all && S.jobs.t.secs.size === 1; }
function jobsPractice(job) { return job?.dry_run === true || job?.target?.dry_run === true; }
function jobsRemember() {
  const t = S.jobs.t;
  const changed = S.focus.doc !== t.doc || Number(S.focus.section) !== [...t.secs][0];
  S.focus = {...S.focus, doc: t.doc, section: [...t.secs][0] || null, model: t.model, base_run: t.base || null,
    ...(changed ? {path: null, kind: null, expected: null, actual: null, expected_text: null, actual_text: null, line: null, lines: []} : {})};
}
function jobsSuggestName() {
  const J = S.jobs, page = J.opts?.pages_dirs?.find(item => item.id === S.ctx.set)?.value;
  const docs = jobsDocs().filter(doc => jobsAllowed(doc, "run"));
  const all = docs.length > 0 && docs.every(doc => J.r.docs?.has(doc.doc_id));
  return J.opts?.run_names?.[J.r.model]?.[page]?.[all ? "dev10" : "probe"] || "";
}
function jobsReconcile() {
  const J = S.jobs, models = J.opts?.models || [];
  if (!jobsModel(J.t.model)) J.t.model = jobsDefaultModel(J.runs.find(run => run.name === J.t.base)?.model_tag);
  const pick = models.find(m => !jobsDraftModel(m) && m.connected === true) || jobsModel(jobsDefaultModel());
  // 직접 고르지 않았다면 연결된 모델로 옮긴다. 예: 화면을 연 뒤에 Pod가 준비된 경우. 특정 실행을 다시 시험할 때는 그 실행의 모델을 지킨다.
  if (!J.t.modelPicked && !J.t.base && !jobsReady(J.t.model) && pick?.connected === true) {
    J.t.model = pick.tag;
    if (S.focus.model) S.focus = {...S.focus, model: pick.tag};
  }
  if (!jobsModel(J.r.model) || (!jobsReady(J.r.model) && pick?.connected === true)) J.r.model = pick?.tag || null;
  const docs = jobsDocs();
  if (!J.defaultsApplied && !J.t.doc) J.t.doc = docs.find(d => jobsAllowed(d, "try"))?.doc_id || null;
  if (jobsSet()) J.defaultsApplied = true;
  if (!docs.some(d => d.doc_id === J.t.doc)) J.t.doc = null;
  const allowed = docs.filter(d => jobsAllowed(d, "run")).map(d => d.doc_id);
  J.r.docs = J.r.docs === null ? new Set(allowed) : new Set([...J.r.docs].filter(id => allowed.includes(id)));
  if (!models.some(m => m.connected === true) && !J.t.dry) { J.t.dry = true; J.t.dryForced = true; }
  if (!J.r.edited) J.r.name = jobsSuggestName();
}
async function jobsLoadOptions() {
  const J = S.jobs;
  if (J.loadingOptions) return J.loadingOptions;
  J.loadingOptions = (async () => {
    const before = JSON.stringify(J.opts), hadError = !!J.optionsError;
    try { J.opts = await api("/api/options"); J.optionsError = null; J.optionsRecovered = hadError; jobsReconcile(); emit("trial_options_checked", {}); }
    catch (error) { J.optionsError = error; J.optionsRecovered = false; }
    return hadError !== !!J.optionsError || before !== JSON.stringify(J.opts);
  })();
  try { return await J.loadingOptions; } finally { J.loadingOptions = null; }
}
async function jobsLoadRuns() {
  const J = S.jobs, key = S.ctx.key;
  try {
    const data = await api(ctxUrl("/api/runs"));
    if (key !== S.ctx.key) return;
    J.runs = data.runs || []; J.runsError = null; J.runsKey = key;
  } catch (error) { if (key === S.ctx.key) J.runsError = error; }
}
async function jobsEnsure(args = {}) {
  const J = S.jobs, incoming = Object.keys(args).length ? args : !J.initialized ? S.focus : {};
  if (args.journeyPrepare) {
    J.defaultsApplied = true; J.t.doc = args.doc || null;
    J.t.secs = new Set(args.section ? [Number(args.section)] : []); J.t.all = false;
    J.t.edit = false; J.t.dirty = false; J.t.text = ""; J.t.textFor = null; J.promptAttempt = null;
    J.expanded["jobs-scope"] = true;
  }
  if (Object.hasOwn(args, "practice")) { J.t.dry = args.practice; J.t.dryForced = false; }
  if ((args.doc || args.section) && !Object.hasOwn(args, "path")) {
    S.focus = {...S.focus, path: null, kind: null, expected: null, actual: null, expected_text: null, actual_text: null, line: null, lines: [], source_set: null};
  }
  if (incoming.doc) J.t.doc = incoming.doc;
  if (Number.isInteger(Number(incoming.section)) && Number(incoming.section) >= 1 && Number(incoming.section) <= 16) {
    J.t.secs = new Set([Number(incoming.section)]); J.t.all = false;
  }
  if (incoming.base_run || incoming.run) J.t.base = incoming.base_run || incoming.run;
  if (incoming.model) J.t.model = incoming.model;
  J.initialized = true;
  if (!J.opts || args.journeyPrepare || args.journeyCheck) await jobsLoadOptions();
  if (J.runsKey !== S.ctx.key || J.runsKey === null) await jobsLoadRuns();
  if (!jobsModel(incoming.model) && (incoming.base_run || incoming.run || !jobsModel(J.t.model))) {
    J.t.model = jobsDefaultModel(J.runs.find(run => run.name === J.t.base)?.model_tag);
  }
  if (Array.isArray(args.runs)) {
    J.c.picked = [...new Set(args.runs)].filter(name => J.runs.some(run => run.name === name && jobsCompareAllowed(run)));
    for (const name of J.c.picked) {
      const label = args.labels?.[args.runs.indexOf(name)];
      J.c.labels[name] = typeof label === "string" ? label : jobsRunLabel(J.runs.find(run => run.name === name));
    }
  }
  if (!J.timer) await jobsPoll();
  jobsRemember();
  if (args.resumePending && J.list.some(job => job.id === args.job && job.kind === "try")) J.observed.add(args.job);
  if (args.job) await jobsWatch(args.job, false);
}
function jobsFormStatus() {
  const J = S.jobs;
  return J.optionsError ? loadFailure(J.optionsError.message)
    : J.optionsRecovered ? jobsNote(T("jobs.record.options_recovered"), {role: "status"}) : null;
}
function jobsModelSelect(form, kind) {
  const select = h("select", {onchange: e => {
    form.model = e.target.value;
    if (kind === "try") { form.modelPicked = true; jobsRemember(); jobsRenderTry(); jobsRenderConnection(); }
    else { if (!form.edited) form.name = jobsSuggestName(); jobsRenderRun(); }
  }}, [...(S.jobs.opts?.models || [])].sort((a, b) => Number(jobsDraftModel(a)) - Number(jobsDraftModel(b)))
    .map(m => h("option", {value: m.tag, disabled: kind === "run" && m.connected !== true},
      jobsDraftModel(m) ? jobsModelLabel(m.tag) : m.option_label || jobsModelLabel(m.tag))));
  select.value = form.model || "";
  return select;
}
function jobsRenderFocus() {
  const f = S.focus, valid = f.doc === S.jobs.t.doc && S.jobs.t.secs.has(Number(f.section)) && f.path;
  const key = valid ? {wrong: "pair", missing: "missing", made: "made"}[f.kind] : null;
  const parsed = String(f.line || "").match(/^p(\d+):L(\d+)$/);
  const parts = String(f.path || "").replace(/\[\d+\]/g, "").split(".");
  const field = parts.slice().reverse().find(part => UI.source.field_names[part]) || parts.at(-1);
  const table = parts.find(part => UI.source.table_names[part]);
  return h("div", {id: "jobs-focus", class: "job-focus"}, h("h3", null, T("jobs.focus.title")),
    key ? jobsNote([UI.source.table_names[table], sourceFieldName({field, table}, null)].filter(Boolean).join(" · ")) : null,
    jobsNote(T(`jobs.focus.${key || "none"}`, {key_value: jobsFocusValue(f.expected, f.expected_text), ai_value: jobsFocusValue(f.actual, f.actual_text)})),
    key ? coreCodeRecord(f.path) : null,
    key && f.line ? jobsNote(f.line_text && parsed ? T(`jobs.focus.${f.estimated ? "line_estimated" : "line"}`,
      {page: parsed[1], line_no: parsed[2], line_text: f.line_text}) : T(`jobs.form.${f.estimated ? "focus_estimated" : "focus_line"}`, {line: f.line})) : null);
}
function jobsRenderTry() {
  const J = S.jobs, t = J.t, el = document.getElementById("jobs-try");
  shellConclusion("s03", T(J.optionsError ? "common.legacy.load_error.message" : !J.opts ? "common.legacy.loading"
    : jobsReady(t.model) ? "jobs.trial.title" : "jobs.off.title"), !!J.opts && !J.optionsError);
  if (!J.opts) { coreReplace(el, jobsFormStatus() || jobsNote(T("common.legacy.loading"), {role: "status"})); return; }
  const active = document.activeElement?.id;
  const docs = jobsDocs(), allowed = jobsAllowed(docs.find(d => d.doc_id === t.doc), "try"), one = jobsSingle();
  // 고를 수 있는 문서를 먼저 둔다. 평가용 문서는 한 줄로 접는다(열 수 없고 번호순으로 맨 앞에 와서 개발 문서를 가린다).
  const closed = docs.filter(d => !jobsAllowed(d, "try") && d.group !== "eval"), evals = docs.filter(d => !jobsAllowed(d, "try") && d.group === "eval");
  const closedReason = d => d.run_reason?.try || T("jobs.no_runnable.todo");
  const select = h("select", {onchange: e => { t.doc = e.target.value; jobsRemember(); jobsRenderTry(); }},
    h("option", {value: ""}, T("jobs.form.no_doc")), [...docs.filter(d => jobsAllowed(d, "try")), ...closed].map(d => h("option", {value: d.doc_id, disabled: !jobsAllowed(d, "try")},
      d.doc_id, d.run_reason?.try ? ` — ${d.run_reason.try}` : ""))); select.value = t.doc || "";
  const base = h("select", {onchange: e => {
    t.base = e.target.value; t.model = jobsDefaultModel(J.runs.find(run => run.name === t.base)?.model_tag);
    t.modelPicked = !!t.base; jobsRemember(); jobsRenderTry(); jobsRenderConnection();
  }},
    h("option", {value: ""}, T("jobs.form.base_auto")),
    J.runs.filter(r => !["eval", "silver", "models"].includes(r.run_kind) && [...(r.docs || []), ...(r.no_gold || [])].includes(t.doc))
      .map(r => h("option", {value: r.name}, jobsRunLabel(r))));
  if (t.base && ![...base.querySelectorAll("option")].some(option => option.value === t.base)) base.append(h("option", {value: t.base}, t.base));
  base.value = t.base;
  const textarea = h("textarea", {rows: 5, class: "job-prompt technical", spellcheck: "false", disabled: !one,
    oninput: e => { t.text = e.target.value; t.edit = true; t.dirty = true; t.revision = (t.revision || 0) + 1;
      const check = document.getElementById("jobs-edit"); if (check) check.checked = true; }});
  textarea.value = t.text;
  const ready = jobsReady(t.model), busy = J.busy === "try";
  // AI가 없어 켠 연습은 AI가 연결되면 푼다. 직접 켠 연습은 그대로 둔다.
  if (!ready && !t.dry) { t.dry = true; t.dryForced = true; }
  if (ready && t.dryForced) { t.dry = false; t.dryForced = false; }
  const controls = h("div", {class: "job-form-grid"},
    jobsField("jobs-model", T("jobs.form.model"), T("jobs.fields.model"), jobsModelSelect(t, "try")),
    jobsField("jobs-doc", T("jobs.form.doc"), T("jobs.fields.doc"), select));
  const scope = jobsDetails("jobs-scope", T("jobs.scope.expand"), controls,
    h("ul", {class: "muted"}, evals.length ? h("li", null, T("jobs.batch.eval_locked", {count: evals.length})) : null,
      [...new Set(closed.map(closedReason))].map(reason => h("li", null, closed.filter(d => closedReason(d) === reason).map(d => d.doc_id).join(", "), " — ", reason))),
    jobsNote(T("jobs.fields.pages")), jobsNote(jobsSet()?.label || S.ctx.set || T("common.none")),
    h("fieldset", null, h("legend", null, T("jobs.scope.label")),
      h("label", null, h("input", {type: "checkbox", checked: t.all, onchange: e => { t.all = e.target.checked; jobsRemember(); jobsRenderTry(); }}), T("jobs.form.all")),
      h("div", {class: "job-sections"}, Array.from({length: 16}, (_, i) => i + 1).map(n => h("label", null,
        h("input", {type: "checkbox", checked: t.secs.has(n), disabled: t.all, onchange: e => {
          e.target.checked ? t.secs.add(n) : t.secs.delete(n); jobsRemember(); jobsRenderTry();
        }}), T("jobs.form.section", {section: n}))))), jobsNote(T("jobs.fields.scope")),
    jobsField("jobs-base", term("base_run", T("jobs.scope.base_run")), T("jobs.fields.base_run"), base));
  if (!t.doc) { scope.open = true; J.expanded["jobs-scope"] = true; }
  coreReplace(el, jobsFormStatus(), jobsNote(t.doc ? `${t.doc} · ${t.all ? T("jobs.form.all") : [...t.secs].map(section => T("jobs.form.section", {section})).join(", ")}`
    : T(docs.some(d => jobsAllowed(d, "try")) ? "jobs.form.no_doc" : "jobs.no_runnable.fact"), {class: "fixed-target"}),
    t.model ? [jobsNote(T("servers.connection.selected") + ": " + jobsModelLabel(t.model)),
      jobsModelDifference(t.model, J.runs.find(run => run.name === t.base)?.model_tag)] : null,
    jobsRenderFocus(), jobsField("jobs-prompt", term("prompt", T("jobs.form.prompt")), T("jobs.prompt.hint"), textarea),
    h("div", {id: "jobs-prompt-status", role: J.promptError ? "alert" : "status"},
      J.promptBusy ? jobsNote(T("jobs.form.prompt_loading")) : J.promptError ? loadFailure(J.promptError.message) : null),
    jobsNote(T("jobs.prompt.retest_hint")),
    h("div", {class: "job-actions"}, h("label", null, h("input", {id: "jobs-edit", type: "checkbox", checked: t.edit && one, disabled: !one,
      onchange: e => { t.edit = e.target.checked; jobsRenderTry(); }}), T("jobs.prompt.edit")),
      jobsButton("jobs-load-prompt", "jobs.form.load_prompt", jobsLoadPrompt, !one || !t.model || J.promptBusy)),
    !one ? jobsNote(T("jobs.multiple.no_edit")) : null,
    t.textFor && t.textFor !== `${t.model}|${[...t.secs][0]}` ? jobsNote(T("jobs.prompt.review_foreign"), {class: "warning"}) : null,
    jobsDetails("jobs-prompt-origin", T("jobs.prompt.details"), ["origin", "memory_only", "delete_temp", "hash_only"].map(key => jobsNote(T(`jobs.prompt.${key}`)))),
    S.focus.source_set && S.focus.source_set !== S.ctx.set ? h("div", {class: "job-notice"}, jobsNote(T("jobs.set_mismatch.title")),
      jobsNote(T("jobs.form.source_set", {set: S.focus.source_set})), jobsNote(T("jobs.form.next_set", {set: S.ctx.set}))) : null,
    jobsNote(J.opts.try_hint?.note || T("jobs.try_hint.off"), {role: "status"}),
    document.getElementById("jobs-connection"),
    jobsButton("jobs-options-reload", "jobs.form.reload", jobsPoll, !!J.loadingOptions),
    h("div", {class: "job-actions"}, jobsButton("jobs-send", busy ? "jobs.form.sending" : t.dry ? "jobs.actions.preview" : "jobs.actions.send", jobsStartTry,
      !!J.busy || !!J.optionsError || !allowed || !t.model || (!t.all && !t.secs.size) || (!t.dry && !ready), ready)),
    h("label", {hidden: !ready}, h("input", {id: "jobs-dry", type: "checkbox", checked: t.dry, disabled: !(J.opts.models || []).some(m => m.connected === true),
      onchange: e => { t.dry = e.target.checked; t.dryForced = false; jobsRenderTry(); }}), T("jobs.fields.dry_run")),
    jobsNote(term("practice", T("jobs.trial.practice_meaning")), {class: "muted"}), J.message.try || null, scope,
    jobsDetails("jobs-next", T("jobs.trial.next_options"),
      jobsButton("jobs-open-guide", "jobs.trial.start_guide", () => go("s08", {branch: "try"})),
      jobsButton("jobs-open-batch", "jobs.trial.open_batch", () => go("s09"))));
  if (active) document.getElementById(active)?.focus({preventScroll: true});
  document.getElementById("jobs-doc").setAttribute("data-guide", "s03-target");
  document.getElementById("jobs-model").setAttribute("data-guide", "s03-model");
  document.getElementById("jobs-send").setAttribute("data-guide", "s03-send");
  document.getElementById("jobs-dry").setAttribute("data-guide", "s03-practice");
  textarea.setAttribute("aria-describedby", "jobs-prompt-help jobs-prompt-status");
  jobsRenderConnection();
  emit("trial_form_shown", {valid: !J.optionsError && allowed && one, connected: ready,
    signature: JSON.stringify([t.doc, [...t.secs], t.all, t.model, S.ctx.set, S.ctx.key])});
  if (S.shell.route === "s03" && allowed && one && t.model && !t.edit && !t.dirty && J.promptAttempt !== jobsPromptKey()) {
    J.promptPending = jobsLoadPrompt({automatic: true});
  }
}
function jobsRenderConnection() {
  const el = document.getElementById("jobs-connection");
  const ready = jobsReady(S.jobs.t.model);
  el.hidden = ready;
  if (ready) return;
  serversRenderCompact(el, {model: S.jobs.t.model, primary: true});
  const data = serversData(), model = serversModel(S.jobs.t.model);
  const choice = data?.rngd_choices?.find(item => item.tag === S.jobs.t.model);
  if (choice) {
    if (data.rngd?.tunnel?.open === false) el.append(serversAction("tunnel_open", {}, T("servers.busy.open_tunnel"), "jobs"));
    el.append(serversAction("rngd_up", {tag: choice.tag}, T("servers.company.confirm_load", {model: choice.label || choice.model}), "jobs"));
    for (const loaded of data.rngd?.models || []) el.append(serversAction("rngd_down", {model: loaded.model}, T("servers.ready.confirm_unload"), `jobs-${loaded.pid}`));
  } else if (model?.where === "RunPod") {
    el.append(jobsNote(T("servers.empty.new_cost")), serversAction("pod_create", {}, T("servers.rented.confirm_create"), "jobs"));
  }
}
function jobsPromptKey() {
  const t = S.jobs.t;
  return JSON.stringify([S.ctx.set, t.doc, t.model, [...t.secs], t.all]);
}
function jobsReadPrompt(model, section) {
  return api(`/api/prompt?${new URLSearchParams({model, no: section})}`);
}
async function jobsLoadPrompt({automatic = false} = {}) {
  const J = S.jobs, t = J.t;
  const key = jobsPromptKey();
  if (!jobsSingle() || !t.model || (J.promptBusy && J.promptAttempt === key) || (automatic && (t.edit || t.dirty))) return;
  const request = ++J.promptRequest, origin = `${t.model}|${[...t.secs][0]}`, draft = t.text, revision = t.revision || 0;
  J.promptAttempt = key; J.promptBusy = true; J.promptError = null; jobsRenderTry();
  try {
    const data = await jobsReadPrompt(t.model, [...t.secs][0]);
    if (request !== J.promptRequest || key !== jobsPromptKey() || draft !== t.text || revision !== (t.revision || 0) || (automatic && (t.edit || t.dirty))) return;
    t.text = data.text || ""; t.textFor = origin; t.dirty = false;
  } catch (error) { if (request === J.promptRequest && key === jobsPromptKey()) J.promptError = error; }
  finally { if (request === J.promptRequest) { J.promptBusy = false; jobsRenderTry(); } }
}
function jobsRequestError(error) {
  return error.body?.message ? friendlyError({...error.body, raw: error.body.error})
    : friendlyError({message: T("jobs.send_unknown.fact"), fix: T("jobs.send_unknown.todo"), raw: error.message});
}
function jobsTryBody(t, context = S.ctx) {
  const one = !t.all && t.secs.size === 1;
  return {model: t.model, doc: t.doc, sections: t.all ? null : [...t.secs].sort((a,b) => a-b), all: t.all,
    set: context.set, key: context.key, system_text: one && t.edit ? t.text : null, base_run: t.base || null, dry_run: t.dry};
}
async function jobsSubmitTry(body, {accept = () => true} = {}) {
  const attempt = "try_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
  emit("attempt_started", {attempt, single: !body.all && body.sections?.length === 1, mode: body.dry_run ? "practice" : "real"});
  const data = await post("/api/jobs/try", body);
  if (!accept()) return null;
  if (!data?.id) throw new Error(T("jobs.send_unknown.fact"));
  S.jobs.observed.add(data.id); emit("attempt_accepted", {attempt, job: data.id});
  return data;
}
function jobsReadResult(id, options = {}) {
  return api(`/api/jobs/${encodeURIComponent(id)}/result`, {...options, withStatus: true});
}
async function jobsStartTry() {
  const J = S.jobs, t = J.t;
  if (J.busy || J.optionsError || !jobsAllowed(jobsDocs().find(d => d.doc_id === t.doc), "try") || !t.model || (!t.dry && !jobsReady(t.model))) return;
  const one = jobsSingle();
  const problem = !S.ctx.set || !S.ctx.key ? "missing_context" : !t.all && !t.secs.size ? "no_sections"
    : one && t.edit && !t.text.trim() ? "prompt_empty"
    : one && t.edit && t.textFor && t.textFor !== `${t.model}|${[...t.secs][0]}` ? "prompt_foreign" : null;
  if (problem) { J.message.try = jobsNote(T(`jobs.form.${problem}`), {role: "alert"}); jobsRenderTry(); return; }
  const body = jobsTryBody(t);
  J.busy = "try"; J.message.try = null; jobsRemember(); jobsRenderTry();
  try {
    const data = await jobsSubmitTry(body);
    J.watch = data.id; J.result = null; J.resultStatus = null; J.resultLoaded = false; J.resultError = null; J.resultRequest++;
    J.message.try = jobsNote(T("jobs.form.sent"), {role: "status"});
    jobsRenderResult();
    if (S.shell.route === "s03") {
      const result = document.getElementById("jobs-result"), context = document.getElementById("global-context");
      result.style.scrollMarginTop = `${context?.offsetHeight || 0}px`;
      result.setAttribute("tabindex", "-1"); result.focus({preventScroll: true}); result.scrollIntoView?.({block: "start"});
    }
    await jobsPoll();
  } catch (error) { J.message.try = jobsRequestError(error); }
  finally {
    J.busy = null; jobsRenderTry(); jobsRenderResult();
  }
}

function jobsTarget(job) {
  const t = job?.target;
  if (!t) return h("div", null, jobsNote(T("jobs.record.unknown")), jobsNote(T("jobs.legacy.no_target")));
  const head = t.kind === "try" ? `${t.doc || T("common.none")} · ${t.all ? T("jobs.form.all") : (t.sections || []).map(section => T("jobs.form.section", {section})).join(", ")}`
    : t.kind === "run" ? (t.docs || []).join(", ") : t.title || T("common.none");
  return h("div", {class: "job-target"}, jobsNote(head, {class: "technical"}),
    t.model ? jobsNote(jobsModel(t.model)?.label || t.model, {class: "technical"}) : null,
    jobsDetails(`jobs-target-${job.id}`, T("jobs.record.conditions"),
      t.set ? jobsNote(`${T("jobs.running.set")}: ${t.set}`, {class: "technical"}) : null,
      t.pages_dir ? jobsNote(`${T("jobs.detail.pages")}: ${t.pages_dir}`, {class: "technical"}) : null,
      t.kind === "try" ? jobsNote(T("jobs.result.key", {label: t.key?.label || T("jobs.result.key_unknown")})) : null,
      t.key?.fingerprint ? jobsNote(`${T("jobs.detail.key_hash")} ${t.key.fingerprint}`, {class: "technical"}) : null,
      t.base_run ? jobsNote(`${T("jobs.detail.base_run")} ${t.base_run}`, {class: "technical"}) : null,
      t.kind === "try" ? jobsNote(T(jobsPractice(job) ? "jobs.trial.practice_meaning" : "jobs.running.real_trial")) : null,
      t.custom_prompt ? jobsNote(T("jobs.selected.prompt")) : null,
      t.repeat ? jobsNote(T("jobs.form.count", {count: t.docs?.length || 0, repeats: t.repeat})) : null,
      [...(t.run_names || []), ...(t.runs || [])].map(name => jobsNote(name, {class: "technical"}))));
}
function jobsWarnings(warnings) {
  return (warnings || []).map(w => h("div", {class: "job-warning", role: "status"},
    jobsNote(typeof w === "string" ? w : w.message || w.fact || T("common.none")),
    typeof w === "object" && (w.fix || w.todo) ? jobsNote(w.fix || w.todo) : null));
}
function jobsFailure(job, openLog = true) {
  if (job.status !== "failed") return null;
  const error = job.error;
  return h("div", {class: "error-note", role: "alert"},
    jobsNote(h("strong", null, (typeof error === "string" ? error : error?.message || error?.fact) || T("errors.job.other.message"))),
    error?.fix ? jobsNote(error.fix) : null, jobsNote(T("errors.job.no_line.fix")),
    openLog ? jobsButton(`jobs-error-log-${job.id}`, "jobs.result_missing.open_log", () => jobsOpenLog(job.id)) : null,
    jobsDetails(`jobs-error-raw-${job.id}`, T("common.raw_error"),
      jobsNote(num(job.returncode) ? T("jobs.legacy.exit_code", {count: job.returncode}) : T("jobs.record.exit_missing")),
      jobsPre(error?.raw || "")));
}
function jobsStatus(job) {
  const known = Object.hasOwn(UI.jobs.status, job.status) ? job.status : "unknown";
  return h("span", {class: known === "failed" ? "error" : known === "done" && !jobsPractice(job) ? "positive" : "muted",
    "data-job-status": job.status, "data-tip": known === "unknown" ? T("jobs.record.unknown_tip") : null},
    T(known === "done" && jobsPractice(job) ? "jobs.practice_done.state" : `jobs.status.${known}`));
}
function jobsStage(index, ...body) {
  const [title, help] = jobsStages[index];
  return jobsDetails(`jobs-stage-${S.jobs.watch}-${index}`, h("span", null, T(`jobs.detail.${title}`),
    h("small", {class: "job-stage-help"}, T(`jobs.stages.${help}`))), body);
}
function jobsScore(result, job) {
  const sc = result.score, label = job?.target?.key?.label || T("jobs.result.key_unknown");
  const blocks = [jobsNote(T("jobs.result.key", {label}))];
  if (sc) {
    blocks.push(jobsNote(result.run ? `${T("jobs.result.before")} ${T("jobs.result.weighted", {score: fmt1(sc.before?.weighted)})} → ${T("jobs.result.after")} ${T("jobs.result.weighted", {score: fmt1(sc.after?.weighted)})}`
      : T("jobs.result.partial_score", {before: fmt1(sc.before?.weighted), after: fmt1(sc.after?.weighted)})),
      result.run ? jobsNote(T("jobs.whole_done.kind")) : jobsNote(T("jobs.result.partial_meaning", {section: (job?.target?.sections || []).join(", ")})),
      sc.changed?.length ? h("table", {class: "job-table"}, h("thead", null, h("tr", null,
        ["changed", "before", "after"].map(key => h("th", {scope: "col"}, T(`jobs.result.${key}`))))),
        h("tbody", null, sc.changed.map(c => h("tr", null, h("th", {scope: "row"}, c.name), h("td", null, pct(c.before)), h("td", null, pct(c.after))))))
        : jobsNote(T("jobs.result.unchanged")), jobsWarnings(sc.warnings));
  } else {
    blocks.push(jobsNote(T("jobs.score_skipped.fact")), result.score_skipped ? jobsNote(result.score_skipped) : null,
      num(result.summary?.weighted) ? jobsNote(T("jobs.result.weighted", {score: fmt1(result.summary.weighted)})) : null);
  }
  if (result.base_run) blocks.push(jobsNote(`${T("jobs.detail.base_run")} ${result.base_run}`, {class: "technical"}));
  return blocks;
}
function jobsResultMatches(job, result) {
  const t = job?.target, p = result?.plan;
  if (!t || !p || t.doc !== p.doc_id || t.model !== p.model_tag) return false;
  if (t.all) return true;
  const expected = (t.sections || []).map(String).sort(), planned = Object.keys(p.sections || {}).sort();
  return expected.length > 0 && JSON.stringify(expected) === JSON.stringify(planned);
}
function jobsResultEvent(job, result, responseStatus, J = S.jobs) {
  if (!job || responseStatus !== 200 || !J.observed.has(job.id) ||
      J.emitted.has(job.id) || J.terminal.has(job.id) || job.status !== "done" || job.returncode !== 0 ||
      !jobsResultMatches(job, result) || job.target?.all || job.target?.kind !== "try") return null;
  const practice = jobsPractice(job);
  if (job.target.sections?.length !== 1 || (!practice && (job.dry_run !== false || job.target.dry_run !== false || !result.results))) return null;
  return {job: job.id, mode: practice ? "practice" : "real",
    section_ok: practice ? null : job.target.sections.every(no => result.results[String(no)]?.ok === true)};
}
function jobsEmitResult(job, result) {
  if (S.shell.route !== "s03" || document.getElementById("screen-s03").hidden || S.guide?.open) return;
  const event = jobsResultEvent(job, result, S.jobs.resultStatus);
  if (!event) return;
  S.jobs.emitted.add(job.id); emit("try_result_viewed", event);
}
function jobsResultSummary(r, job) {
  if (r.run) return jobsNote(T("jobs.whole_done.kind"));
  if (r.results) {
    const rows = Object.values(r.results), ok = rows.length > 0 && rows.every(v => v.ok === true);
    return h("div", {role: "status"}, jobsNote(T(ok ? "jobs.result.plain_done" : "jobs.parse_failed.fact")),
      !ok ? jobsNote(T("jobs.parse_failed.todo", {stage: 4})) : null, jobsScore(r, job));
  }
  return h("div", {role: "status"}, jobsNote(T(jobsPractice(job) ? "jobs.practice_done.title" : "jobs.result.practice_unconfirmed")),
    jobsNote(T("jobs.practice_done.no_success")), jobsNote(T("jobs.practice_done.omitted_stages", {first_stage: 3, last_stage: 6})));
}
function jobsRenderResult() {
  document.getElementById("jobs-result").setAttribute("data-guide", "s03-result-summary");
  const J = S.jobs, el = document.getElementById("jobs-result"), job = J.list.find(j => j.id === J.watch);
  if (!J.watch) { coreReplace(el, jobsNote(T("jobs.form.waiting"), {class: "muted"})); return; }
  const head = [h("h2", null, T("jobs.completion.title")), jobsNote(J.watch, {class: "technical"}), job ? jobsStatus(job) : null,
    job ? jobsTarget(job) : null, job ? jobsFailure(job) : null, jobsWarnings(job?.warnings)];
  if (job?.status === "stopped") { coreReplace(el, head, jobsNote(T("jobs.stopped.fact")), jobsNote(T("jobs.stopped.late_reply"))); return; }
  if (J.resultError) { coreReplace(el, head, loadFailure(J.resultError.message), jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return; }
  if (!J.resultLoaded) { coreReplace(el, head, jobsNote(T("jobs.result.pending"), {role: "status"})); return; }
  const r = J.result;
  if (J.resultStatus !== 200 && J.resultStatus !== 204) {
    coreReplace(el, head, jobsNote(T("jobs.result.pending"), {role: "status"}),
      jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return;
  }
  if (!r) {
    coreReplace(el, head, jobsNote(h("strong", null, T("jobs.result_missing.fact"))), jobsNote(T("jobs.result_missing.todo", {status_code: 204})),
      jobsButton("jobs-result-log", "jobs.result_missing.open_log", () => jobsOpenLog(J.watch)), jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return;
  }
  const p = r.plan || {}, secs = Object.entries(p.sections || {}), mismatch = job?.target && !jobsResultMatches(job, r);
  const parts = [jobsStage(0,
    jobsNote(T("jobs.result.input_meta", {pages: p.pages_dir, method: coreCodeLabel("split", p.sections_method), count: p.msds_count})),
    coreCodeRecord(p.sections_method),
    jobsNote([p.doc_id, p.model_tag, p.model].filter(Boolean).join(" · "), {class: "technical"}),
    h("ul", null, secs.map(([no, v]) => h("li", {class: "technical"}, T("jobs.result.input_rows", {section: no,
      format: T(v.rows ? "jobs.result.format_rows" : "jobs.result.format_json"), count: v.lines, preamble: v.preamble_lines,
      first: v.first, last: v.last, pages: (v.pages || []).join(", "), images: (v.images || []).join(", ") || T("common.none"), method: coreCodeLabel("split", v.method)}),
      coreCodeRecord(v.method)))), jobsWarnings(p.warnings)),
    jobsStage(1, jobsNote(T("jobs.detail.no_full_text")), h("ul", null, secs.map(([no, v]) => h("li", null,
      T("jobs.result.section", {section: no}), " — ", h("code", {class: "technical"}, v.prompt_hash || T("common.none")),
      v.system_override ? jobsNote(T("jobs.detail.prompt_edited", {section: no})) : null))))];
  const summary = jobsResultSummary(r, job);
  if (r.run) {
    const stats = T("jobs.result.whole_stats", {ok: r.run.sections_ok, failed: r.run.sections_failed, retries: r.run.reextracted, seconds: fmt1(r.run.seconds)});
    parts.push(jobsStage(2, jobsNote(stats), jobsNote(T("jobs.whole_done.raw_path")), jobsNote(r.saved ? `${r.saved}/raw/` : T("common.none"), {class: "technical"})),
      jobsStage(3, jobsPre(r.summary || {})), jobsStage(4, jobsNote(T("jobs.whole_done.no_journey_success")),
        r.saved ? jobsButton("jobs-whole-source", "jobs.done.open_source", () => go("s02", {run: r.saved.replace(/^.*?runs\//, ""), doc: p.doc_id, section: 1})) : null),
      jobsStage(5, jobsScore(r, job)));
  } else if (r.results) {
    const rows = Object.entries(r.results);
    parts.push(jobsStage(2, rows.map(([no, v]) => h("div", null, h("h3", null, T("jobs.result.section", {section: no})),
      jobsNote(T("jobs.result.raw_meta", {mode: coreCodeLabel("mode", v.mode), reason: coreCodeLabel("finish", v.finish_reason), seconds: fmt1(v.seconds)})),
      coreCodeRecord(v.mode, v.finish_reason), jobsPre(v.raw_text || T("jobs.result.no_answer"))))),
      jobsStage(3, rows.map(([no, v]) => h("div", null, h("h3", null, T("jobs.result.section", {section: no})),
        jobsNote(T(v.ok ? "jobs.result.ok" : "jobs.result.bad")), jobsNote(T("jobs.result.parse_meta", {discarded: v.dropped_rows, retries: v.reextracted ? 1 : 0, attempts: v.attempts})),
        jobsNote(T("jobs.detail.tokens", {input_tokens: v.usage?.prompt_tokens, output_tokens: v.usage?.completion_tokens})),
        jobsWarnings(v.errors), jobsWarnings(v.check_problems), jobsPre(v.parsed)))),
      jobsStage(4, h("ul", null, Object.entries(r.fields || {}).map(([no, fields]) => h("li", null, T("jobs.result.section", {section: no}),
        h("ul", null, Object.entries(fields || {}).map(([name, count]) => h("li", null,
          T("jobs.result.fields_count", {name: UI.source?.rows?.[name] || name, count: jobsValue(count)})))))))),
      jobsStage(5, jobsScore(r, job)));
  }
  coreReplace(el, head, mismatch ? friendlyError({message: T("jobs.target_mismatch.fact"), fix: T("jobs.target_mismatch.todo")}) : null,
    summary, parts, r.saved ? jobsNote(`${T("jobs.completion.path")} ${r.saved}`, {class: "technical"}) : null,
    job?.target ? jobsButton("jobs-result-source", "jobs.done.open_source", () => go("s02", {run: job.target.base_run || S.focus.run, doc: job.target.doc,
      section: job.target.sections?.[0] || 1, path: S.focus.path, line: S.focus.line})) : null);
  if (job && !mismatch) jobsEmitResult(job, r);
}
async function jobsLoadResult(id) {
  const J = S.jobs, request = ++J.resultRequest;
  J.result = null; J.resultStatus = null; J.resultError = null;
  try {
    const response = await jobsReadResult(id);
    if (J.watch !== id || request !== J.resultRequest) return;
    J.resultStatus = response.status;
    J.result = response.status === 200 ? response.data : null; J.resultLoaded = true; J.resultError = null;
  } catch (error) { if (J.watch === id && request === J.resultRequest) J.resultError = error; }
  if (J.watch === id && request === J.resultRequest) jobsRenderResult();
}
async function jobsWatch(id, navigate = true) {
  const J = S.jobs;
  J.selected = id;
  if (J.watch !== id) { J.watch = id; J.result = null; J.resultStatus = null; J.resultLoaded = false; J.resultError = null; J.resultRequest++; }
  if (navigate && S.shell.route !== "s03") await go("s03");
  if (J.list.find(j => j.id === id)?.status !== "running") await jobsLoadResult(id);
  jobsRenderResult();
}

function jobsRenderRun() {
  const J = S.jobs, r = J.r, el = document.getElementById("jobs-run");
  if (!J.opts) { coreReplace(el, jobsFormStatus() || jobsNote(T("common.legacy.loading"))); return; }
  const refill = () => { if (!r.edited) r.name = jobsSuggestName(); jobsRenderRun(); };
  const docs = jobsDocs(), ready = jobsReady(r.model);
  const allowed = docs.filter(d => jobsAllowed(d, "run"));
  const locked = docs.filter(d => !jobsAllowed(d, "run"));
  const evaluation = locked.filter(d => d.group === "eval");
  const reasons = new Map();
  for (const doc of locked) {
    const reason = doc.run_reason?.run || T("context.unavailable");
    if (!reasons.has(reason)) reasons.set(reason, []);
    reasons.get(reason).push(doc);
  }
  const checkbox = d => h("label", null,
    h("input", {id: `jobs-run-doc-${d.doc_id}`, type: "checkbox", checked: r.docs?.has(d.doc_id), disabled: !jobsAllowed(d, "run"),
      onchange: e => { e.target.checked ? r.docs.add(d.doc_id) : r.docs.delete(d.doc_id); refill(); }}), d.doc_id);
  coreReplace(el, h("h2", null, T("jobs.batch.title")), jobsFormStatus(),
    jobsField("jobs-run-model", T("jobs.form.model"), T("jobs.fields.model"), jobsModelSelect(r, "run")),
    jobsNote(jobsSet()?.label || S.ctx.set || T("common.none")),
    h("fieldset", null, h("legend", null, T("jobs.batch.select_docs")),
      h("div", {class: "job-actions"}, jobsButton("jobs-select-all", "jobs.form.select_all", () => { r.docs = new Set(docs.filter(d => jobsAllowed(d, "run")).map(d => d.doc_id)); refill(); }),
        jobsButton("jobs-select-none", "jobs.form.select_none", () => { r.docs.clear(); refill(); })),
      h("div", {class: "job-docs"}, allowed.map(d => h("div", null, checkbox(d), d.run_reason?.run ? jobsNote(d.run_reason.run) : null))),
      jobsNote(T("jobs.form.count", {count: r.docs?.size || 0, repeats: r.repeat}), {id: "jobs-run-count", role: "status"})),
    locked.length ? jobsDetails("jobs-run-locked", evaluation.length ? T("jobs.batch.eval_locked", {count: evaluation.length}) : T("jobs.batch.runnable"),
      [...reasons].map(([reason, group]) => h("div", null, jobsNote(reason), h("div", {class: "job-docs"}, group.map(checkbox))))) : null,
    h("div", {class: "job-form-grid"}, jobsField("jobs-repeat", T("jobs.batch.repeats"), T("jobs.fields.repeat"),
      h("input", {type: "number", min: 1, max: 10, value: r.repeat, oninput: e => {
        r.repeat = Number(e.target.value);
        document.getElementById("jobs-run-count").textContent = T("jobs.form.count", {count: r.docs?.size || 0, repeats: r.repeat});
      }})),
      jobsField("jobs-run-name", T("jobs.form.run_name"), T("jobs.fields.run_name"), h("input", {type: "text", class: "technical", value: r.name,
        oninput: e => { r.name = e.target.value; r.edited = true; }}))),
    jobsButton("jobs-suggest", "jobs.form.suggest", () => { r.edited = false; refill(); }),
    !ready ? h("div", {class: "job-actions"}, jobsNote(T("jobs.actions.run_unavailable")),
      jobsButton("jobs-run-prepare", "context.prepare_model", () => go("s06", {model: r.model, returnScreen: "s09"}), false, true)) : null,
    jobsButton("jobs-run-start", "jobs.batch.start", jobsStartRun, !ready || !!J.busy || !r.docs?.size, ready),
    J.message.run || null,
    J.confirm?.kind === "run" ? jobsNote(J.confirm.summary, {class: "technical"}) : null,
    jobsDetails("jobs-run-conditions", T("jobs.batch.details"), ["kind", "repeat_range", "keep_awake", "confirm", "outside_policy"].map(k => jobsNote(T(`jobs.batch.${k}`)))),
    jobsButton("jobs-run-records", "jobs.running.open_jobs", () => go("s05")));
}
async function jobsStartRun(confirmed = false) {
  const J = S.jobs, r = J.r;
  if (J.busy) return;
  // 확인은 보낸 조건의 사본에만 적용한다. 화면 전역 기준을 바꿔도 다른 대상을 보내지 않는다.
  const pending = J.confirm?.kind === "run" ? J.confirm : null;
  if (confirmed === true && !pending) return;
  const body = confirmed === true && pending ? {...pending.body, confirm: true}
    : {model: r.model, docs: jobsDocs().filter(d => jobsAllowed(d, "run") && r.docs.has(d.doc_id)).map(d => d.doc_id), set: S.ctx.set, run_name: r.name.trim(), repeat: r.repeat};
  if (!jobsReady(body.model) || !body.set || !body.docs.length || !body.run_name || !Number.isInteger(body.repeat) || body.repeat < 1 || body.repeat > 10) {
    J.message.run = jobsNote(T("jobs.form.invalid_run"), {role: "alert"}); jobsRenderRun(); return;
  }
  if (body.confirm) jobsCloseConfirm();
  J.busy = "run"; J.message.run = null; jobsRenderRun();
  try {
    await post("/api/jobs/run", body); J.confirm = null;
    J.message.run = jobsNote(T("jobs.form.sent"), {role: "status"}); await jobsPoll();
  } catch (error) {
    if (error.status === 409 && error.body?.needs_confirm && !body.confirm) J.confirm = {kind: "run", body, summary: error.body.summary};
    else { J.confirm = null; J.message.run = jobsRequestError(error); }
  } finally { J.busy = null; jobsRenderRun(); if (J.confirm?.kind === "run") jobsOpenConfirm("jobs-run-start"); }
}
function jobsCompareAllowed(run) { return !run.error && !["eval", "silver", "models"].includes(run.run_kind) && run.kind !== "models"; }
function jobsCompareConditions(run) {
  return jobsDetails(`jobs-compare-conditions-${run.name}`, T("jobs.selected.context"),
    jobsNote(run.set?.label || run.set?.id || T("jobs.record.unknown")),
    jobsNote(T("jobs.result.key", {label: run.key?.label || T("jobs.result.key_unknown")})),
    jobsNote(run.model_label || run.model_tag || T("common.none"), {class: "technical"}),
    jobsNote(`${T("score.conditions.prompt")}: ${run.prompt_version || T("jobs.record.unknown")}`, {class: "technical"}),
    jobsNote(UI.jobs.kinds[run.run_kind] || T("jobs.record.unknown")),
    jobsNote(T("score.conditions.score_counts", {total: (run.docs || []).length + (run.no_gold || []).length + (run.excluded || []).length,
      scored: (run.docs || []).length, missing: (run.no_gold || []).length, excluded: (run.excluded || []).length})));
}
function jobsCompareMove(name, offset) {
  const picked = S.jobs.c.picked, from = picked.indexOf(name), to = from + offset;
  if (from < 0 || to < 0 || to >= picked.length) return;
  [picked[from], picked[to]] = [picked[to], picked[from]];
  jobsRenderCompare(); document.getElementById(`jobs-compare-${offset < 0 ? "up" : "down"}-${name}`)?.focus({preventScroll: true});
}
function jobsRenderCompare() {
  const J = S.jobs, c = J.c, el = document.getElementById("jobs-compare");
  // 목록에서 사라졌거나 잠긴 결과를 조용히 전송하지 않는다.
  c.picked = c.picked.filter(name => J.runs.some(run => run.name === name && jobsCompareAllowed(run)));
  const picked = c.picked.map(name => J.runs.find(run => run.name === name));
  const candidates = jobsDetails("jobs-compare-candidates", T("compare.builder.selection_output"),
    jobsButton("jobs-reload-runs", "compare.table.reload", async () => { await jobsLoadRuns(); jobsRenderCompare(); }),
    J.runs.length ? h("div", {class: "job-compare-rows"}, J.runs.map(run => {
      const selected = c.picked.includes(run.name), allowed = jobsCompareAllowed(run);
      return h("div", {class: "job-compare-row"}, h("label", null,
        h("input", {id: `jobs-compare-pick-${run.name}`, type: "checkbox", checked: selected, disabled: !allowed, onchange: e => {
          c.picked = e.target.checked ? [...new Set([...c.picked, run.name])] : c.picked.filter(name => name !== run.name); jobsRenderCompare();
        }}), jobsRunLabel(run), h("small", {class: "technical"}, run.name)),
        !selected ? jobsCompareConditions(run) : null,
        !allowed ? jobsNote(T("jobs.compare.unavailable")) : null);
    })) : jobsNote(T("jobs.compare.empty")));
  coreReplace(el, h("h2", null, T("compare.builder.title")), jobsNote(T("compare.table.column_order")),
    J.runsError ? loadFailure(J.runsError.message) : null,
    h("table", {id: "jobs-compare-order", class: "job-table"}, h("thead", null, h("tr", null,
      ["compare.swapped.order", "score.conditions.run_name", "compare.builder.display_name", "compare.builder.conditions"].map(key => h("th", {scope: "col"}, T(key))))),
      h("tbody", null, picked.map((run, index) => h("tr", {"data-run": run.name},
        h("td", null, String(index + 1), picked.length > 2 ? h("div", {class: "job-actions"},
          jobsButton(`jobs-compare-up-${run.name}`, "compare.builder.move_up", () => jobsCompareMove(run.name, -1), index === 0),
          jobsButton(`jobs-compare-down-${run.name}`, "compare.builder.move_down", () => jobsCompareMove(run.name, 1), index === picked.length - 1)) : null),
        h("th", {scope: "row"}, jobsRunLabel(run), h("small", {class: "raw"}, run.name)),
        h("td", null, jobsField(`jobs-compare-label-${run.name}`, `${index + 1}. ${T("compare.builder.display_name")}`, T("compare.table.default_name"),
          h("input", {type: "text", value: c.labels[run.name] || "", oninput: e => { c.labels[run.name] = e.target.value; }}))),
        h("td", null, jobsCompareConditions(run)))))),
    !picked.length ? jobsNote(T("compare.builder.selected_count", {count: 0})) : null,
    h("div", {class: "job-actions"}, jobsButton("jobs-compare-swap", "compare.builder.swap", () => {
      [c.picked[0], c.picked[1]] = [c.picked[1], c.picked[0]]; jobsRenderCompare(); document.getElementById("jobs-compare-swap").focus({preventScroll: true});
    }, c.picked.length !== 2)),
    jobsField("jobs-compare-title", T("compare.table.caption"), null, h("input", {type: "text", value: c.title, oninput: e => { c.title = e.target.value; }})),
    jobsNote(T("jobs.compare.key_default")), jobsNote(T("jobs.compare.count", {count: c.picked.length})),
    jobsButton("jobs-compare-start", "compare.table.create_ordered", jobsStartCompare, !!J.busy || !c.picked.length, true), J.message.compare || null,
    candidates, jobsButton("jobs-compare-records", "compare.table.open_job", () => go("s05")));
}
async function jobsStartCompare() {
  const J = S.jobs, c = J.c;
  if (J.busy) return;
  const runs = c.picked.filter(name => J.runs.some(r => r.name === name && jobsCompareAllowed(r)));
  if (!runs.length || !c.title.trim()) { J.message.compare = jobsNote(T("jobs.compare.need_title"), {role: "alert"}); jobsRenderCompare(); return; }
  const labels = runs.map(name => (c.labels[name] || "").trim() || null);
  J.busy = "compare"; jobsRenderCompare();
  try { await post("/api/jobs/compare", {title: c.title.trim(), runs, labels: labels.some(Boolean) ? labels : null});
    J.message.compare = jobsNote(T("jobs.form.sent"), {role: "status"}); await jobsPoll();
  } catch (error) { J.message.compare = jobsRequestError(error); }
  finally { J.busy = null; jobsRenderCompare(); }
}
function jobsProgress(job) {
  return h("div", null, (job.progress || []).map(p => jobsNote(T("jobs.record.round", p), {class: "technical"})),
    job.output ? jobsNote(job.output, {class: "technical"}) : null);
}
function jobsTargetSummary(job) {
  const t = job.target;
  if (!t) return T("jobs.record.unknown");
  if (t.kind === "try") return `${t.doc || T("common.none")} · ${t.all ? T("jobs.form.all") : (t.sections || []).map(section => T("jobs.form.section", {section})).join(", ")}`;
  if (t.kind === "run") return (t.docs || []).join(", ");
  return t.title || T("jobs.list.selected_runs", {count: (t.runs || []).length});
}
function jobsRenderList() {
  const J = S.jobs, el = document.getElementById("jobs-list");
  coreReplace(el, h("h2", null, T("jobs.list.title")),
    J.pollError ? loadFailure(J.pollError.message) : J.recovered ? jobsNote(T("jobs.record.recovered"), {role: "status"}) : null,
    jobsButton("jobs-reload", "jobs.record.reload", jobsPoll),
    h("table", {class: "job-table"}, h("thead", null, h("tr", null, ["kind", "name", "started", "progress"].map(key => h("th", {scope: "col"}, T(`jobs.record.${key}`))))),
      h("tbody", null, J.list.map(job => h("tr", {class: job.id === (J.log?.id || J.selected || J.watch) ? "job-selected" : null},
        h("td", null, T(Object.hasOwn(UI.jobs.kind, job.kind) ? `jobs.kind.${job.kind}` : "jobs.status.unknown")),
        h("td", null, jobsNote(jobsTargetSummary(job)), job.status === "failed" ? jobsNote(
          (typeof job.error === "string" ? job.error : job.error?.message || job.error?.fact) || T("errors.job.other.message"), {class: "job-error-summary"}) : null),
        h("td", null, when(job.started ? new Date(job.started * 1000).toISOString() : null)),
        h("td", null, jobsStatus(job), h("div", {class: "job-actions"},
          jobsButton(`jobs-log-${job.id}`, "jobs.result_missing.open_log", () => jobsOpenLog(job.id)),
          job.kind === "try" ? jobsButton(`jobs-watch-${job.id}`, "jobs.list.open_trial", () => jobsWatch(job.id)) : null,
          job.stoppable ? jobsButton(`jobs-stop-${job.id}`, "jobs.record.stop", () => { J.confirm = {kind: "stop", id: job.id}; jobsOpenConfirm(`jobs-stop-${job.id}`); }) : null)))),
        J.running.filter(item => !item.mine).map(item => h("tr", {"data-external": true},
          h("td", null, T("jobs.list.external")), h("td", null, jobsNote(item.run_name || item.doc || T("jobs.list.target_unknown"), {class: "technical"}),
            jobsNote(item.model || "", {class: "technical"})), h("td", null, T("jobs.external.running")),
          h("td", null, T("jobs.external.unstoppable"), jobsNote(T("jobs.record.pid", {pid: item.pid}))))))),
    !J.list.length && !J.running.some(item => !item.mine) ? jobsNote(T("jobs.record.empty")) : null);
}
function jobsRenderDetail() {
  const J = S.jobs, el = document.getElementById("jobs-detail"), log = J.log;
  const job = J.list.find(j => j.id === log?.id);
  coreReplace(el, log ? h("div", null, h("h2", null, T("jobs.selected.title")), job ? jobsTarget(job) : null, job ? jobsStatus(job) : null,
    job ? jobsFailure(job, false) : null, jobsWarnings(job?.warnings), job ? jobsProgress(job) : null,
    job ? jobsNote(job.label || "", {class: "raw"}) : null,
    jobsButton("jobs-close-log", "jobs.record.close_log", () => { J.log = null; jobsRenderDetail(); jobsRenderList(); }),
    log.error ? loadFailure(log.error.message) : null,
    h("pre", {id: "jobs-log", class: "job-log technical", tabindex: "0", onscroll: e => {
      log.scroll = e.target.scrollTop; log.bottom = e.target.scrollTop + e.target.clientHeight >= e.target.scrollHeight - 4;
    }}, log.text || T("jobs.record.log_empty")),
    job ? jobsDetails(`jobs-log-meta-${job.id}`, T("jobs.legacy.log"), jobsNote(job.command || "", {class: "technical"}),
      jobsNote(job.log || "", {class: "technical"}), jobsNote(num(job.returncode) ? T("jobs.legacy.exit_code", {count: job.returncode}) : T("jobs.record.exit_missing"))) : null) : null,
J.message.stop || null);
  const pre = document.getElementById("jobs-log"); if (pre) pre.scrollTop = log.bottom ? pre.scrollHeight : log.scroll;
}
async function jobsRefreshLog() {
  const log = S.jobs.log; if (!log) return;
  try { const data = await api(`/api/jobs/${encodeURIComponent(log.id)}/log?lines=400`);
    if (S.jobs.log === log) { log.text = data.text; log.error = null; }
  } catch (error) { if (S.jobs.log === log) log.error = error; }
}
async function jobsOpenLog(id) {
  S.jobs.selected = id; S.jobs.log = {id, text: "", scroll: 0, bottom: true};
  if (S.shell.route !== "s05") await go("s05");
  await jobsRefreshLog(); jobsRenderList(); jobsRenderDetail();
}
function jobsOpenConfirm(trigger) {
  const J = S.jobs, c = J.confirm, dialog = document.getElementById("action-confirm");
  if (!c) return;
  J.confirmTrigger = trigger;
  const stop = c.kind === "stop" ? J.list.find(job => job.id === c.id) : null;
  dialog.setAttribute("aria-labelledby", "jobs-confirm-title");
  dialog.setAttribute("aria-describedby", "jobs-confirm-summary");
  coreReplace(dialog, h("h2", {id: "jobs-confirm-title"}, T(stop ? "jobs.record.confirm_stop" : "servers.confirm.summary")),
    h("div", {id: "jobs-confirm-summary"}, stop ? jobsTarget(stop) : jobsNote(c.summary, {class: "technical"})),
    stop ? jobsNote(T("jobs.confirm.stop.loss")) : null,
    h("div", {class: "dialog-actions"}, jobsButton("jobs-confirm-cancel", "servers.confirm.cancel", jobsCloseConfirm),
      jobsButton(stop ? "jobs-stop-confirm" : "jobs-run-confirm", stop ? "jobs.record.confirm_action" : "servers.confirm.batch.action",
        stop ? () => jobsStop(stop) : () => jobsStartRun(true), !!J.busy, true)));
  if (!J.dialogReady) {
    J.dialogReady = true;
    dialog.addEventListener("cancel", event => { if (J.confirm) { event.preventDefault(); jobsCloseConfirm(); } });
    dialog.addEventListener("keydown", event => {
      if (!J.confirm) return;
      if (event.key === "Escape") { event.preventDefault(); jobsCloseConfirm(); }
      if (event.key === "Tab") {
        const buttons = [...dialog.querySelectorAll("button")].filter(button => !button.disabled);
        const first = buttons[0], last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
  }
  if (!dialog.open) dialog.showModal();
  document.getElementById("jobs-confirm-cancel").focus();
}
function jobsCloseConfirm() {
  const J = S.jobs, trigger = J.confirmTrigger;
  J.confirm = null;
  const dialog = document.getElementById("action-confirm"); if (dialog.open) dialog.close();
  jobsRenderRun(); jobsRenderDetail(); document.getElementById(trigger)?.focus({preventScroll: true});
}
async function jobsStop(job) {
  const J = S.jobs;
  if (J.busy || !job.stoppable || J.confirm?.id !== job.id) return;
  jobsCloseConfirm(); J.busy = "stop"; jobsRenderDetail();
  try { const data = await post(`/api/jobs/${encodeURIComponent(job.id)}/stop`, {});
    if (data.stopped) {J.terminal.add(job.id); emit("attempt_cancelled", {job: job.id});}
    J.message.stop = jobsNote(T(data.stopped ? "jobs.record.stopped" : "jobs.record.not_stopped"), {role: "status"});
    J.confirm = null; await jobsPoll();
  } catch (error) { J.message.stop = jobsRequestError(error); }
  finally { J.busy = null; jobsRenderDetail(); }
}
async function jobsPoll() {
  const J = S.jobs;
  if (J.polling) return J.polling;
  clearTimeout(J.timer); J.timer = null;
  J.polling = (async () => {
    if (await jobsLoadOptions()) { jobsRenderTry(); jobsRenderRun(); jobsRenderConnection(); }
    try {
      const data = await api("/api/jobs"); J.recovered = !!J.pollError; J.pollError = null;
      J.list = data.jobs || []; J.running = data.running || [];
      emit("trial_jobs_changed", {jobs: J.list});
      for (const job of J.list) {
        if (job.kind === "try" && job.status === "running") J.observed.add(job.id);
        if (["failed", "stopped"].includes(job.status)) J.terminal.add(job.id);
      }
    } catch (error) { J.pollError = error; J.recovered = false; }
    const watched = J.list.find(j => j.id === J.watch);
    if (!J.pollError && watched && watched.status !== "running" && !J.resultLoaded) await jobsLoadResult(watched.id);
    if (J.log) await jobsRefreshLog();
    jobsRenderList(); jobsRenderDetail(); jobsRenderResult();
  })();
  try { await J.polling; } finally {
    J.polling = null; J.timer = setTimeout(() => jobsPoll().catch(fail), 10000);
  }
}
shellDefineView("jobs-try", {load: jobsEnsure, render: jobsRenderTry});
shellDefineView("jobs-result", {render: jobsRenderResult});
shellDefineView("jobs-connection", {render: jobsRenderConnection});
shellDefineView("jobs-run", {load: jobsEnsure, render: jobsRenderRun});
shellDefineView("jobs-compare", {load: jobsEnsure, render: jobsRenderCompare});
shellDefineView("jobs-list", {load: jobsEnsure, render: jobsRenderList});
shellDefineView("jobs-detail", {render: jobsRenderDetail});
on("servers_changed", async () => {
  if (!S.jobs.initialized) return;
  if (await jobsLoadOptions()) { jobsRenderTry(); jobsRenderRun(); }
  jobsRenderConnection();
});
on("context_changed", async () => {
  if (!S.jobs.initialized) return;
  jobsReconcile(); await jobsLoadRuns(); jobsRenderTry(); jobsRenderRun(); jobsRenderCompare();
});
