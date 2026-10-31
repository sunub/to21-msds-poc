"use strict";

// 폼과 지시문은 메모리에만 둔다. 시작 당시 조건은 서버의 target을 읽는다.
S.jobs = {opts: null, optionsError: null, optionsRecovered: false, pollError: null, recovered: false,
  t: {doc: null, model: null, secs: new Set([1]), all: false, base: "", dry: false, edit: false, text: "", textFor: null},
  r: {model: null, docs: null, repeat: 1, name: "", edited: false}, c: {picked: [], labels: {}, title: ""},
  list: [], running: [], runs: [], runsError: null, runsKey: null, timer: null, polling: null, loadingOptions: null,
  watch: null, result: null, resultLoaded: false, resultError: null, resultRequest: 0,
  observed: new Set(), emitted: new Set(), terminal: new Set(), log: null, expanded: {},
  busy: null, message: {}, confirm: null, initialized: false, defaultsApplied: false,
  dialogReady: false, confirmTrigger: null, promptRequest: 0, promptBusy: false};
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
  control.setAttribute("id", id); control.setAttribute("aria-describedby", `${id}-help`);
  return h("div", {class: "job-field"}, h("label", {for: id}, label), control,
    help ? h("small", {id: `${id}-help`, class: "muted"}, help) : null);
}
function jobsSet() { return S.jobs.opts?.sets?.find(set => set.id === S.ctx.set); }
function jobsDocs() { return jobsSet()?.usable === false ? [] : jobsSet()?.docs || []; }
function jobsAllowed(doc, kind) { return doc?.runnable?.[kind] === true; }
function jobsModel(tag) { return S.jobs.opts?.models?.find(model => model.tag === tag); }
function jobsReady(tag) { return !S.jobs.optionsError && jobsModel(tag)?.connected === true; }
function jobsSingle() { return !S.jobs.t.all && S.jobs.t.secs.size === 1; }
function jobsPractice(job) { return job?.dry_run === true || job?.target?.dry_run === true; }
function jobsRemember() {
  const t = S.jobs.t;
  const changed = S.focus.doc !== t.doc || Number(S.focus.section) !== [...t.secs][0];
  S.focus = {...S.focus, doc: t.doc, section: [...t.secs][0] || null, model: t.model, base_run: t.base || null,
    ...(changed ? {path: null, kind: null, expected: null, actual: null, line: null, lines: []} : {})};
}
function jobsSuggestName() {
  const J = S.jobs, page = J.opts?.pages_dirs?.find(item => item.id === S.ctx.set)?.value;
  const docs = jobsDocs().filter(doc => jobsAllowed(doc, "run"));
  const all = docs.length > 0 && docs.every(doc => J.r.docs?.has(doc.doc_id));
  return J.opts?.run_names?.[J.r.model]?.[page]?.[all ? "dev10" : "probe"] || "";
}
function jobsReconcile() {
  const J = S.jobs, models = J.opts?.models || [], pick = models.find(m => m.connected === true) || models[0];
  for (const form of [J.t, J.r]) if (!jobsModel(form.model) || (!jobsReady(form.model) && pick?.connected === true)) form.model = pick?.tag || null;
  const docs = jobsDocs();
  if (!J.defaultsApplied && !J.t.doc) J.t.doc = docs.find(d => jobsAllowed(d, "try"))?.doc_id || null;
  if (jobsSet()) J.defaultsApplied = true;
  if (!docs.some(d => d.doc_id === J.t.doc)) J.t.doc = null;
  const allowed = docs.filter(d => jobsAllowed(d, "run")).map(d => d.doc_id);
  J.r.docs = J.r.docs === null ? new Set(allowed) : new Set([...J.r.docs].filter(id => allowed.includes(id)));
  if (!models.some(m => m.connected === true)) J.t.dry = true;
  if (!J.r.edited) J.r.name = jobsSuggestName();
}
async function jobsLoadOptions() {
  const J = S.jobs;
  if (J.loadingOptions) return J.loadingOptions;
  J.loadingOptions = (async () => {
    const before = JSON.stringify(J.opts), hadError = !!J.optionsError;
    try { J.opts = await api("/api/options"); J.optionsError = null; J.optionsRecovered = hadError; jobsReconcile(); }
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
  if ((args.doc || args.section) && !Object.hasOwn(args, "path")) {
    S.focus = {...S.focus, path: null, kind: null, expected: null, actual: null, line: null, lines: [], source_set: null};
  }
  if (incoming.doc) J.t.doc = incoming.doc;
  if (Number.isInteger(Number(incoming.section)) && Number(incoming.section) >= 1 && Number(incoming.section) <= 16) {
    J.t.secs = new Set([Number(incoming.section)]); J.t.all = false;
  }
  if (incoming.base_run || incoming.run) J.t.base = incoming.base_run || incoming.run;
  if (incoming.model) J.t.model = incoming.model;
  J.initialized = true;
  if (!J.opts) await jobsLoadOptions();
  if (J.runsKey !== S.ctx.key || J.runsKey === null) await jobsLoadRuns();
  if (!J.timer) await jobsPoll();
  jobsRemember();
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
    if (kind === "try") { jobsRemember(); jobsRenderTry(); jobsRenderConnection(); }
    else { if (!form.edited) form.name = jobsSuggestName(); jobsRenderRun(); }
  }}, (S.jobs.opts?.models || []).map(m => h("option", {value: m.tag, disabled: kind === "run" && m.connected !== true}, m.option_label || m.label || m.tag)));
  select.value = form.model || "";
  return select;
}
function jobsRenderFocus() {
  const f = S.focus, valid = f.doc === S.jobs.t.doc && S.jobs.t.secs.has(Number(f.section)) && f.path;
  const key = valid ? {wrong: "pair", missing: "missing", made: "made"}[f.kind] : null;
  const parsed = String(f.line || "").match(/^p(\d+):L(\d+)$/);
  return h("div", {id: "jobs-focus", class: "job-focus"}, h("h3", null, T("jobs.focus.title")),
    jobsNote(T(`jobs.focus.${key || "none"}`, {key_value: jobsValue(f.expected), ai_value: jobsValue(f.actual)})),
    key ? jobsNote(f.path, {class: "technical"}) : null,
    key && f.line ? jobsNote(f.line_text && parsed ? T(`jobs.focus.${f.estimated ? "line_estimated" : "line"}`,
      {page: parsed[1], line_no: parsed[2], line_text: f.line_text}) : T(`jobs.form.${f.estimated ? "focus_estimated" : "focus_line"}`, {line: f.line})) : null);
}
function jobsRenderTry() {
  const J = S.jobs, t = J.t, el = document.getElementById("jobs-try");
  if (!J.opts) { coreReplace(el, jobsFormStatus() || jobsNote(T("common.legacy.loading"), {role: "status"})); return; }
  const active = document.activeElement?.id;
  const docs = jobsDocs(), allowed = jobsAllowed(docs.find(d => d.doc_id === t.doc), "try"), one = jobsSingle();
  const select = h("select", {onchange: e => { t.doc = e.target.value; jobsRemember(); jobsRenderTry(); }},
    h("option", {value: ""}, T("jobs.form.no_doc")), docs.map(d => h("option", {value: d.doc_id, disabled: !jobsAllowed(d, "try")},
      d.doc_id, d.run_reason?.try ? ` — ${d.run_reason.try}` : ""))); select.value = t.doc || "";
  const base = h("select", {onchange: e => { t.base = e.target.value; jobsRemember(); }},
    h("option", {value: ""}, T("jobs.form.base_auto")),
    J.runs.filter(r => !["eval", "silver", "models"].includes(r.run_kind) && [...(r.docs || []), ...(r.no_gold || [])].includes(t.doc))
      .map(r => h("option", {value: r.name}, r.label || r.name)));
  if (t.base && !base.querySelectorAll("option").some(option => option.value === t.base)) base.append(h("option", {value: t.base}, t.base));
  base.value = t.base;
  const textarea = h("textarea", {rows: 5, class: "job-prompt technical", spellcheck: "false", disabled: !one,
    oninput: e => { t.text = e.target.value; t.edit = true; const check = document.getElementById("jobs-edit"); if (check) check.checked = true; }});
  textarea.value = t.text;
  const ready = jobsReady(t.model), busy = J.busy === "try";
  const controls = h("div", {class: "job-form-grid"},
    jobsField("jobs-model", T("jobs.form.model"), T("jobs.fields.model"), jobsModelSelect(t, "try")),
    jobsField("jobs-doc", T("jobs.form.doc"), T("jobs.fields.doc"), select));
  const scope = jobsDetails("jobs-scope", T("jobs.scope.expand"), controls,
    h("ul", {class: "muted"}, docs.filter(d => !jobsAllowed(d, "try")).map(d => h("li", null, d.doc_id, " — ", d.run_reason?.try || T("jobs.no_runnable.todo")))),
    jobsNote(T("jobs.fields.pages")), jobsNote(jobsSet()?.label || S.ctx.set || T("common.none")),
    h("fieldset", null, h("legend", null, T("jobs.scope.label")),
      h("label", null, h("input", {type: "checkbox", checked: t.all, onchange: e => { t.all = e.target.checked; jobsRenderTry(); }}), T("jobs.form.all")),
      h("div", {class: "job-sections"}, Array.from({length: 16}, (_, i) => i + 1).map(n => h("label", null,
        h("input", {type: "checkbox", checked: t.secs.has(n), disabled: t.all, onchange: e => {
          e.target.checked ? t.secs.add(n) : t.secs.delete(n); jobsRemember(); jobsRenderTry();
        }}), T("jobs.form.section", {section: n}))))), jobsNote(T("jobs.fields.scope")),
    jobsField("jobs-base", T("jobs.scope.base_run"), T("jobs.fields.base_run"), base));
  if (!t.doc) { scope.open = true; J.expanded["jobs-scope"] = true; }
  coreReplace(el, jobsFormStatus(), jobsNote(t.doc ? `${t.doc} · ${t.all ? T("jobs.form.all") : [...t.secs].map(section => T("jobs.form.section", {section})).join(", ")}`
    : T(docs.some(d => jobsAllowed(d, "try")) ? "jobs.form.no_doc" : "jobs.no_runnable.fact"), {class: "fixed-target"}),
    jobsRenderFocus(), jobsField("jobs-prompt", T("jobs.form.prompt"), T("jobs.prompt.hint"), textarea),
    jobsNote(T("jobs.prompt.retest_hint")),
    h("div", {class: "job-actions"}, h("label", null, h("input", {id: "jobs-edit", type: "checkbox", checked: t.edit && one, disabled: !one,
      onchange: e => { t.edit = e.target.checked; jobsRenderTry(); }}), T("jobs.prompt.edit")),
      jobsButton("jobs-load-prompt", "jobs.form.load_prompt", jobsLoadPrompt, !one || !t.model || J.promptBusy)),
    !one ? jobsNote(T("jobs.multiple.no_edit")) : null,
    t.textFor && t.textFor !== `${t.model}|${[...t.secs][0]}` ? jobsNote(T("jobs.prompt.review_foreign"), {class: "warning"}) : null,
    J.promptBusy ? jobsNote(T("jobs.form.prompt_loading"), {role: "status"}) : null,
    jobsDetails("jobs-prompt-origin", T("jobs.prompt.details"), ["origin", "memory_only", "delete_temp", "hash_only"].map(key => jobsNote(T(`jobs.prompt.${key}`)))),
    S.focus.source_set && S.focus.source_set !== S.ctx.set ? h("div", {class: "job-notice"}, jobsNote(T("jobs.set_mismatch.title")),
      jobsNote(T("jobs.form.source_set", {set: S.focus.source_set})), jobsNote(T("jobs.form.next_set", {set: S.ctx.set}))) : null,
    jobsNote(J.opts.try_hint?.note || T("jobs.try_hint.off"), {role: "status"}),
    jobsButton("jobs-options-reload", "jobs.form.reload", jobsPoll, !!J.loadingOptions),
    h("div", {class: "job-actions"}, jobsButton("jobs-send", busy ? "jobs.form.sending" : t.dry ? "jobs.actions.preview" : "jobs.actions.send", jobsStartTry,
      !!J.busy || !!J.optionsError || !allowed || !t.model || (!t.all && !t.secs.size) || (!t.dry && !ready), true)),
    h("label", null, h("input", {id: "jobs-dry", type: "checkbox", checked: t.dry, disabled: !(J.opts.models || []).some(m => m.connected === true),
      onchange: e => { t.dry = e.target.checked; jobsRenderTry(); }}), T("jobs.actions.preview")),
    jobsNote(T("jobs.trial.practice_meaning"), {class: "muted"}), J.message.try || null, scope,
    jobsDetails("jobs-next", T("jobs.trial.next_options"),
      jobsButton("jobs-open-guide", "jobs.trial.start_guide", () => go("s08", {branch: "try"})),
      jobsButton("jobs-open-batch", "jobs.trial.open_batch", () => go("s09"))));
  if (active) document.getElementById(active)?.focus({preventScroll: true});
}
function jobsRenderConnection() {
  const el = document.getElementById("jobs-connection");
  const ready = jobsReady(S.jobs.t.model);
  el.hidden = ready;
  if (ready) return;
  serversRenderCompact(el, {model: S.jobs.t.model});
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
async function jobsLoadPrompt() {
  const J = S.jobs, t = J.t;
  if (!jobsSingle() || !t.model || J.promptBusy) return;
  const request = ++J.promptRequest, origin = `${t.model}|${[...t.secs][0]}`, draft = t.text;
  J.promptBusy = true; J.message.try = null; jobsRenderTry();
  try {
    const data = await api(`/api/prompt?${new URLSearchParams({model: t.model, no: [...t.secs][0]})}`);
    if (request !== J.promptRequest || !jobsSingle() || origin !== `${t.model}|${[...t.secs][0]}` || draft !== t.text) return;
    t.text = data.text || ""; t.textFor = origin;
  } catch (error) { J.message.try = loadFailure(error.message); }
  finally { J.promptBusy = false; jobsRenderTry(); }
}
function jobsRequestError(error) {
  return error.body?.message ? friendlyError({...error.body, raw: error.body.error})
    : friendlyError({message: T("jobs.send_unknown.fact"), fix: T("jobs.send_unknown.todo"), raw: error.message});
}
async function jobsStartTry() {
  const J = S.jobs, t = J.t;
  if (J.busy || J.optionsError || !jobsAllowed(jobsDocs().find(d => d.doc_id === t.doc), "try") || !t.model || (!t.dry && !jobsReady(t.model))) return;
  const one = jobsSingle();
  const problem = !S.ctx.set || !S.ctx.key ? "missing_context" : !t.all && !t.secs.size ? "no_sections"
    : one && t.edit && !t.text.trim() ? "prompt_empty"
    : one && t.edit && t.textFor && t.textFor !== `${t.model}|${[...t.secs][0]}` ? "prompt_foreign" : null;
  if (problem) { J.message.try = jobsNote(T(`jobs.form.${problem}`), {role: "alert"}); jobsRenderTry(); return; }
  const body = {model: t.model, doc: t.doc, sections: t.all ? null : [...t.secs].sort((a,b) => a-b), all: t.all,
    set: S.ctx.set, key: S.ctx.key, system_text: one && t.edit ? t.text : null, base_run: t.base || null, dry_run: t.dry};
  J.busy = "try"; J.message.try = null; jobsRemember(); jobsRenderTry();
  try {
    const data = await post("/api/jobs/try", body);
    if (!data?.id) throw new Error(T("jobs.send_unknown.fact"));
    J.watch = data.id; J.result = null; J.resultLoaded = false; J.resultRequest++;
    J.message.try = jobsNote(T("jobs.form.sent"), {role: "status"}); await jobsPoll();
  } catch (error) { J.message.try = jobsRequestError(error); }
  finally { J.busy = null; jobsRenderTry(); jobsRenderResult(); }
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
function jobsFailure(job) {
  if (job.status !== "failed") return null;
  const error = job.error;
  return h("div", {class: "error-note", role: "alert"},
    jobsNote(h("strong", null, (typeof error === "string" ? error : error?.message || error?.fact) || T("errors.job.other.message"))),
    error?.fix ? jobsNote(error.fix) : null, jobsNote(T("errors.job.no_line.fix")),
    jobsButton(`jobs-error-log-${job.id}`, "jobs.result_missing.open_log", () => jobsOpenLog(job.id)),
    jobsDetails(`jobs-error-raw-${job.id}`, T("common.raw_error"),
      jobsNote(num(job.returncode) ? T("jobs.legacy.exit_code", {count: job.returncode}) : T("jobs.record.exit_missing")),
      jobsPre(error?.raw || "")));
}
function jobsStatus(job) {
  const known = Object.hasOwn(UI.jobs.status, job.status) ? job.status : "unknown";
  return h("span", {class: known === "failed" ? "error" : known === "done" ? "positive" : "muted",
    "data-tip": known === "unknown" ? T("jobs.record.unknown_tip") : null}, T(`jobs.status.${known}`));
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
function jobsEmitResult(job, result) {
  const J = S.jobs;
  if (S.shell.route !== "s03" || document.getElementById("screen-s03").hidden || !J.observed.has(job.id) ||
      J.emitted.has(job.id) || J.terminal.has(job.id) || job.status !== "done" || job.returncode !== 0 ||
      !jobsResultMatches(job, result) || job.target?.all || job.target?.kind !== "try") return;
  const practice = jobsPractice(job);
  if (!practice && !result.results) return;
  J.emitted.add(job.id);
  emit("try_result_viewed", {job: job.id, mode: practice ? "practice" : "real",
    section_ok: practice ? null : job.target.sections.every(no => result.results[String(no)]?.ok === true)});
}
function jobsRenderResult() {
  const J = S.jobs, el = document.getElementById("jobs-result"), job = J.list.find(j => j.id === J.watch);
  if (!J.watch) { coreReplace(el, jobsNote(T("jobs.form.waiting"), {class: "muted"})); return; }
  const head = [h("h2", null, T("jobs.completion.title")), jobsNote(J.watch, {class: "technical"}), job ? jobsStatus(job) : null,
    job ? jobsTarget(job) : null, job ? jobsFailure(job) : null, jobsWarnings(job?.warnings)];
  if (job?.status === "stopped") { coreReplace(el, head, jobsNote(T("jobs.stopped.fact")), jobsNote(T("jobs.stopped.late_reply"))); return; }
  if (J.resultError) { coreReplace(el, head, loadFailure(J.resultError.message), jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return; }
  if (!J.resultLoaded) { coreReplace(el, head, jobsNote(T("jobs.result.pending"), {role: "status"})); return; }
  const r = J.result;
  if (!r) {
    coreReplace(el, head, jobsNote(h("strong", null, T("jobs.result_missing.fact"))), jobsNote(T("jobs.result_missing.todo", {status_code: 204})),
      jobsButton("jobs-result-log", "jobs.result_missing.open_log", () => jobsOpenLog(J.watch)), jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return;
  }
  const p = r.plan || {}, secs = Object.entries(p.sections || {}), mismatch = job?.target && !jobsResultMatches(job, r);
  const parts = [jobsStage(0,
    jobsNote(T("jobs.result.input_meta", {pages: p.pages_dir, method: p.sections_method, count: p.msds_count})),
    jobsNote([p.doc_id, p.model_tag, p.model].filter(Boolean).join(" · "), {class: "technical"}),
    h("ul", null, secs.map(([no, v]) => h("li", {class: "technical"}, T("jobs.result.input_rows", {section: no,
      format: T(v.rows ? "jobs.result.format_rows" : "jobs.result.format_json"), count: v.lines, preamble: v.preamble_lines,
      first: v.first, last: v.last, pages: (v.pages || []).join(", "), images: (v.images || []).join(", ") || T("common.none"), method: v.method})))), jobsWarnings(p.warnings)),
    jobsStage(1, jobsNote(T("jobs.detail.no_full_text")), h("ul", null, secs.map(([no, v]) => h("li", null,
      T("jobs.result.section", {section: no}), " — ", h("code", {class: "technical"}, v.prompt_hash || T("common.none")),
      v.system_override ? jobsNote(T("jobs.detail.prompt_edited", {section: no})) : null))))];
  let summary;
  if (r.run) {
    summary = jobsNote(T("jobs.whole_done.kind"));
    const stats = T("jobs.result.whole_stats", {ok: r.run.sections_ok, failed: r.run.sections_failed, retries: r.run.reextracted, seconds: fmt1(r.run.seconds)});
    parts.push(jobsStage(2, jobsNote(stats), jobsNote(T("jobs.whole_done.raw_path")), jobsNote(r.saved ? `${r.saved}/raw/` : T("common.none"), {class: "technical"})),
      jobsStage(3, jobsPre(r.summary || {})), jobsStage(4, jobsNote(T("jobs.whole_done.no_journey_success")),
        r.saved ? jobsButton("jobs-whole-source", "jobs.done.open_source", () => go("s02", {run: r.saved.replace(/^.*?runs\//, ""), doc: p.doc_id, section: 1})) : null),
      jobsStage(5, jobsScore(r, job)));
  } else if (r.results) {
    const rows = Object.entries(r.results), ok = rows.length > 0 && rows.every(([, v]) => v.ok === true);
    summary = h("div", {role: "status"}, jobsNote(T(ok ? "jobs.result.plain_done" : "jobs.parse_failed.fact")),
      !ok ? jobsNote(T("jobs.parse_failed.todo", {stage: 4})) : null, jobsScore(r, job));
    parts.push(jobsStage(2, rows.map(([no, v]) => h("div", null, h("h3", null, T("jobs.result.section", {section: no})),
      jobsNote(T("jobs.result.raw_meta", {mode: v.mode, reason: v.finish_reason, seconds: fmt1(v.seconds)})), jobsPre(v.raw_text || T("jobs.result.no_answer"))))),
      jobsStage(3, rows.map(([no, v]) => h("div", null, h("h3", null, T("jobs.result.section", {section: no})),
        jobsNote(T(v.ok ? "jobs.result.ok" : "jobs.result.bad")), jobsNote(T("jobs.result.parse_meta", {discarded: v.dropped_rows, retries: v.reextracted ? 1 : 0, attempts: v.attempts})),
        jobsNote(T("jobs.detail.tokens", {input_tokens: v.usage?.prompt_tokens, output_tokens: v.usage?.completion_tokens})),
        jobsWarnings(v.errors), jobsWarnings(v.check_problems), jobsPre(v.parsed)))),
      jobsStage(4, h("ul", null, Object.entries(r.fields || {}).map(([no, fields]) => h("li", null, T("jobs.result.section", {section: no}),
        h("ul", null, Object.entries(fields || {}).map(([name, count]) => h("li", null,
          T("jobs.result.fields_count", {name: UI.source?.rows?.[name] || name, count: jobsValue(count)})))))))),
      jobsStage(5, jobsScore(r, job)));
  } else {
    summary = h("div", {role: "status"}, jobsNote(T(jobsPractice(job) ? "jobs.practice_done.title" : "jobs.result.practice_unconfirmed")),
      jobsNote(T("jobs.practice_done.no_success")), jobsNote(T("jobs.practice_done.omitted_stages", {first_stage: 3, last_stage: 6})));
  }
  coreReplace(el, head, mismatch ? friendlyError({message: T("jobs.target_mismatch.fact"), fix: T("jobs.target_mismatch.todo")}) : null,
    summary, parts, r.saved ? jobsNote(`${T("jobs.completion.path")} ${r.saved}`, {class: "technical"}) : null,
    job?.target ? jobsButton("jobs-result-source", "jobs.done.open_source", () => go("s02", {run: job.target.base_run || S.focus.run, doc: job.target.doc,
      section: job.target.sections?.[0] || 1, path: S.focus.path, line: S.focus.line})) : null);
  if (job && !mismatch) jobsEmitResult(job, r);
}
async function jobsLoadResult(id) {
  const J = S.jobs, request = ++J.resultRequest;
  try {
    const data = await api(`/api/jobs/${encodeURIComponent(id)}/result`);
    if (J.watch !== id || request !== J.resultRequest) return;
    J.result = data; J.resultLoaded = true; J.resultError = null;
  } catch (error) { if (J.watch === id && request === J.resultRequest) J.resultError = error; }
  if (J.watch === id && request === J.resultRequest) jobsRenderResult();
}
async function jobsWatch(id, navigate = true) {
  const J = S.jobs;
  if (J.watch !== id) { J.watch = id; J.result = null; J.resultLoaded = false; J.resultError = null; J.resultRequest++; }
  if (navigate && S.shell.route !== "s03") await go("s03");
  if (J.list.find(j => j.id === id)?.status !== "running") await jobsLoadResult(id);
  jobsRenderResult();
}

function jobsRenderRun() {
  const J = S.jobs, r = J.r, el = document.getElementById("jobs-run");
  if (!J.opts) { coreReplace(el, jobsFormStatus() || jobsNote(T("common.legacy.loading"))); return; }
  const refill = () => { if (!r.edited) r.name = jobsSuggestName(); jobsRenderRun(); };
  const docs = jobsDocs(), ready = jobsReady(r.model);
  coreReplace(el, h("h2", null, T("jobs.batch.title")), jobsFormStatus(),
    jobsField("jobs-run-model", T("jobs.form.model"), T("jobs.fields.model"), jobsModelSelect(r, "run")),
    jobsNote(jobsSet()?.label || S.ctx.set || T("common.none")),
    h("fieldset", null, h("legend", null, T("jobs.batch.select_docs")),
      h("div", {class: "job-actions"}, jobsButton("jobs-select-all", "jobs.form.select_all", () => { r.docs = new Set(docs.filter(d => jobsAllowed(d, "run")).map(d => d.doc_id)); refill(); }),
        jobsButton("jobs-select-none", "jobs.form.select_none", () => { r.docs.clear(); refill(); })),
      h("div", {class: "job-docs"}, docs.map(d => h("label", null,
        h("input", {id: `jobs-run-doc-${d.doc_id}`, type: "checkbox", checked: r.docs?.has(d.doc_id), disabled: !jobsAllowed(d, "run"),
          onchange: e => { e.target.checked ? r.docs.add(d.doc_id) : r.docs.delete(d.doc_id); refill(); }}), d.doc_id,
        d.run_reason?.run ? h("small", {class: "muted"}, ` — ${d.run_reason.run}`) : null)))),
    h("div", {class: "job-form-grid"}, jobsField("jobs-repeat", T("jobs.batch.repeats"), T("jobs.fields.repeat"),
      h("input", {type: "number", min: 1, max: 10, value: r.repeat, oninput: e => { r.repeat = Number(e.target.value); }})),
      jobsField("jobs-run-name", T("jobs.form.run_name"), T("jobs.fields.run_name"), h("input", {type: "text", class: "technical", value: r.name,
        oninput: e => { r.name = e.target.value; r.edited = true; }}))),
    jobsButton("jobs-suggest", "jobs.form.suggest", () => { r.edited = false; refill(); }),
    jobsNote(T("jobs.form.count", {count: r.docs?.size || 0, repeats: r.repeat})),
    jobsButton("jobs-run-start", "jobs.batch.start", jobsStartRun, !ready || !!J.busy || !r.docs?.size, true),
    !ready ? jobsNote(T("jobs.actions.run_unavailable")) : null, J.message.run || null,
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
function jobsRenderCompare() {
  const J = S.jobs, c = J.c, el = document.getElementById("jobs-compare");
  coreReplace(el, h("h2", null, T("compare.table.title")), jobsNote(T("compare.table.column_order")), jobsNote(T("jobs.compare.key_default")),
    J.runsError ? loadFailure(J.runsError.message) : null,
    jobsButton("jobs-reload-runs", "compare.table.reload", async () => { await jobsLoadRuns(); jobsRenderCompare(); }),
    jobsNote(T("jobs.fields.compare_label")),
    h("div", {class: "job-compare-rows"}, J.runs.length ? J.runs.map(run => {
      const picked = c.picked.includes(run.name), allowed = jobsCompareAllowed(run);
      return h("div", {class: "job-compare-row"}, h("label", null,
        h("input", {id: `jobs-compare-pick-${run.name}`, type: "checkbox", checked: picked, disabled: !allowed, onchange: e => {
          c.picked = e.target.checked ? [...new Set([...c.picked, run.name])] : c.picked.filter(name => name !== run.name); jobsRenderCompare();
        }}), run.label || run.name, h("small", {class: "technical"}, run.name)),
        jobsDetails(`jobs-compare-conditions-${run.name}`, T("jobs.selected.context"),
          jobsNote(run.set?.label || run.set?.id || T("jobs.record.unknown")),
          jobsNote(T("jobs.result.key", {label: run.key?.label || T("jobs.result.key_unknown")})),
          jobsNote(run.model_label || run.model_tag || T("common.none"), {class: "technical"}),
          jobsNote(`${T("score.conditions.prompt")}: ${run.prompt_version || T("jobs.record.unknown")}`, {class: "technical"}),
          jobsNote(UI.jobs.kinds[run.run_kind] || T("jobs.record.unknown")),
          jobsNote(T("score.conditions.score_counts", {total: (run.docs || []).length + (run.no_gold || []).length + (run.excluded || []).length,
            scored: (run.docs || []).length, missing: (run.no_gold || []).length, excluded: (run.excluded || []).length}))),
        !allowed ? jobsNote(T("jobs.compare.unavailable")) : null,
        picked ? jobsField(`jobs-compare-label-${run.name}`, `${c.picked.indexOf(run.name) + 1}. ${T("jobs.compare.label")}`, T("compare.table.default_name"),
          h("input", {type: "text", value: c.labels[run.name] || "", oninput: e => { c.labels[run.name] = e.target.value; }})) : null);
    }) : jobsNote(T("jobs.compare.empty"))),
    jobsField("jobs-compare-title", T("compare.table.caption"), null, h("input", {type: "text", value: c.title, oninput: e => { c.title = e.target.value; }})),
    jobsNote(T("jobs.compare.count", {count: c.picked.length})),
    jobsButton("jobs-compare-start", "compare.table.create_ordered", jobsStartCompare, !!J.busy || !c.picked.length, true), J.message.compare || null,
    jobsButton("jobs-compare-records", "compare.table.open_job", () => go("s05")));
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
function jobsRenderList() {
  const J = S.jobs, el = document.getElementById("jobs-list");
  coreReplace(el, h("h2", null, T("jobs.list.title")),
    J.pollError ? loadFailure(J.pollError.message) : J.recovered ? jobsNote(T("jobs.record.recovered"), {role: "status"}) : null,
    jobsButton("jobs-reload", "jobs.record.reload", jobsPoll),
    h("table", {class: "job-table"}, h("thead", null, h("tr", null, ["kind", "name", "started", "progress"].map(key => h("th", {scope: "col"}, T(`jobs.record.${key}`))))),
      h("tbody", null, J.list.map(job => h("tr", {class: job.id === J.watch || job.id === J.log?.id ? "job-selected" : null},
        h("td", null, T(Object.hasOwn(UI.jobs.kind, job.kind) ? `jobs.kind.${job.kind}` : "jobs.status.unknown"), jobsStatus(job)),
        h("td", null, jobsTarget(job), jobsNote(job.label || "", {class: "raw"}), jobsFailure(job), jobsWarnings(job.warnings)),
        h("td", null, when(job.started ? new Date(job.started * 1000).toISOString() : null)),
        h("td", null, jobsProgress(job), jobsButton(`jobs-log-${job.id}`, "jobs.result_missing.open_log", () => jobsOpenLog(job.id)),
          job.kind === "try" ? jobsButton(`jobs-watch-${job.id}`, "jobs.list.open_trial", () => jobsWatch(job.id)) : null,
          job.stoppable ? jobsButton(`jobs-stop-${job.id}`, "jobs.record.stop", () => { J.confirm = {kind: "stop", id: job.id}; jobsOpenConfirm(`jobs-stop-${job.id}`); }) : null))),
        J.running.filter(item => !item.mine).map(item => h("tr", {"data-external": true},
          h("td", null, T("jobs.list.external")), h("td", null, jobsNote(item.run_name || item.doc || T("jobs.list.target_unknown"), {class: "technical"}),
            jobsNote(item.model || "", {class: "technical"})), h("td", null, T("jobs.external.running")),
          h("td", null, T("jobs.external.unstoppable"), jobsNote(T("jobs.record.pid", {pid: item.pid}))))))),
    !J.list.length && !J.running.some(item => !item.mine) ? jobsNote(T("jobs.record.empty")) : null);
}
function jobsRenderDetail() {
  const J = S.jobs, el = document.getElementById("jobs-detail"), log = J.log;
  const job = J.list.find(j => j.id === log?.id);
  coreReplace(el, log ? h("div", null, h("h2", null, T("jobs.selected.title")), job ? jobsTarget(job) : null,
    jobsButton("jobs-close-log", "jobs.record.close_log", () => { J.log = null; jobsRenderDetail(); }),
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
  S.jobs.log = {id, text: "", scroll: 0, bottom: true};
  if (S.shell.route !== "s05") await go("s05");
  await jobsRefreshLog(); jobsRenderDetail();
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
    if (data.stopped) J.terminal.add(job.id);
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
