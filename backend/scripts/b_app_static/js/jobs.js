"use strict";

// 폼과 지시문은 메모리에만 둔다. 시작 당시 조건은 서버의 target을 읽는다.
// step은 표시 상태일 뿐 입력을 지우지 않는다: target, model, prompt, job(작업 상태에 따라 시험 또는 결과). batch는 '여러 문서' 갈래다.
S.jobs = {step: null, batch: false, runWatch: null, sendError: null, runError: null, timings: {},
  opts: null, optionsError: null, optionsRecovered: false, pollError: null, recovered: false,
  t: {doc: null, model: null, secs: new Set([1]), all: false, base: "", dry: false, edit: false, dirty: false, text: "", textFor: null},
  r: {model: null, docs: null, repeat: 1, name: "", edited: false}, c: {picked: [], labels: {}, title: ""},
  list: [], running: [], runs: [], runsError: null, runsKey: null, timer: null, polling: null, loadingOptions: null,
  watch: null, result: null, resultStatus: null, resultLoaded: false, resultError: null, resultRequest: 0,
  observed: new Set(), emitted: new Set(), terminal: new Set(), log: null, expanded: {}, change: null,
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
// 원문에서 고른 값이 지금 대상의 값인가.
function jobsPickedValue() {
  const f = S.focus, t = S.jobs.t;
  return !!f.path && !t.all && f.doc === t.doc && t.secs.has(Number(f.section));
}
// 들어올 때 여는 단계. 고른 값이 없거나 원문과 묶음이 다르면 ①, AI가 꺼져 있으면 ②, 켜져 있으면 ③이다.
function jobsEntryStep() {
  const doc = jobsDocs().find(d => d.doc_id === S.jobs.t.doc);
  const sameSet = !S.focus.source_set || S.focus.source_set === S.ctx.set;
  return stepsFirstOpen([{id: "target", done: jobsPickedValue() && jobsAllowed(doc, "try") && sameSet},
    {id: "model", done: jobsReady(S.jobs.t.model)}, {id: "prompt", done: false}]);
}
function jobsEnterStep(args, {trialBranch, trialStep, cameBack}) {
  const J = S.jobs, running = J.step === "job" && jobsWatched()?.status === "running";
  // 도는 시험을 덮지 않는다. 옛 주소로 들어와도 ④를 그대로 보인다.
  if (trialBranch && !running) { J.batch = trialBranch === "batch"; J.step = "target"; }
  else if (trialStep) J.step = trialStep;
  else if (args.job) return;
  else if (J.step === null || ((args.doc || args.section || args.path) && !running)) { J.batch = false; J.step = jobsEntryStep(); }
  // 서버에서 돌아왔을 때 고른 AI가 응답하면 ②를 지난다. 다른 AI만 켜졌다면 머문다.
  else if (cameBack && J.step === "model" && jobsReady(jobsForm().model)) J.step = "prompt";
}
async function jobsEnsure(args = {}) {
  const J = S.jobs, incoming = Object.keys(args).length ? args : !J.initialized ? S.focus : {};
  // 단계 지시는 이번 이동에만 쓴다. S.focus에 남으면 다음 이동에 다시 적용된다.
  const {trialBranch, trialStep, ...focus} = S.focus;
  const cameBack = S.shell.route === "s03" && !!focus.returnScreen;
  if (cameBack) delete focus.returnScreen;
  S.focus = focus;
  if (args.journeyPrepare) {
    J.defaultsApplied = true; J.t.doc = args.doc || null;
    J.t.secs = new Set(args.section ? [Number(args.section)] : []); J.t.all = false; J.batch = false;
    J.t.edit = false; J.t.dirty = false; J.t.text = ""; J.t.textFor = null; J.promptAttempt = null;
  }
  if (Object.hasOwn(args, "practice")) J.t.dry = args.practice;
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
  if (!J.opts || args.journeyPrepare || args.journeyCheck || cameBack) await jobsLoadOptions();
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
  if (S.shell.route === "s03") jobsEnterStep(args, {trialBranch, trialStep, cameBack});
  if (args.resumePending && J.list.some(job => job.id === args.job && job.kind === "try")) J.observed.add(args.job);
  if (args.job) await jobsWatch(args.job, false);
}
function jobsFormStatus() {
  const J = S.jobs;
  return J.optionsError ? loadFailure(J.optionsError.message)
    : J.optionsRecovered ? jobsNote(T("jobs.record.options_recovered"), {role: "status"}) : null;
}
// ── 다시 시험의 단계: 무엇을 → 어느 AI로 → 무엇을 시킬지 → 시험 → 결과 (ADR-039) ──
function jobsForm() { return S.jobs.batch ? S.jobs.r : S.jobs.t; }
function jobsWatched() {
  const J = S.jobs, id = J.batch ? J.runWatch : J.watch;
  return J.list.find(job => job.id === id) || null;
}
function jobsRunning() { return jobsWatched()?.status === "running"; }
function jobsFinished() {
  const J = S.jobs, job = jobsWatched();
  if (J.batch) return job?.status === "done";
  return !!J.watch && !["running", "failed", "stopped"].includes(job?.status) && J.resultLoaded && J.resultStatus === 200 && !!J.result;
}
// 다음 단계로 못 가는 이유. 없으면 빈 글이다.
function jobsTargetReason() {
  const J = S.jobs, t = J.t, r = J.r;
  if (J.batch) return !r.docs?.size || !r.name.trim() || !Number.isInteger(r.repeat) || r.repeat < 1 || r.repeat > 10 ? T("jobs.form.invalid_run") : "";
  const doc = jobsDocs().find(d => d.doc_id === t.doc);
  if (!doc) return T("jobs.form.no_doc");
  if (!jobsAllowed(doc, "try")) return doc.run_reason?.try || T("jobs.no_runnable.todo");
  return !t.all && !t.secs.size ? T("jobs.form.no_sections") : "";
}
function jobsStep() {
  const J = S.jobs, at = J.step || "target";
  if (at === "job") return jobsFinished() ? "result" : "running";
  // 대상이 사라지면 ①에서 고친다. 다른 문서로 몰래 바꾸지 않는다.
  return at !== "target" && jobsTargetReason() ? "target" : at;
}
function jobsGoStep(id) {
  S.jobs.step = ["running", "result"].includes(id) ? "job" : id;
  jobsRenderSteps();
  document.getElementById("title-s03").focus({preventScroll: true});
}
function jobsRenderSteps() { jobsRenderTry(); jobsRenderRun(); jobsRenderConnection(); jobsRenderResult(); }
function jobsChooseBranch(kind) {
  const J = S.jobs;
  J.batch = kind === "batch";
  if (!J.batch) { J.t.all = kind === "document"; jobsRemember(); }
  jobsRenderSteps();
  document.getElementById(`jobs-branch-${kind}`)?.focus({preventScroll: true});
}
function jobsTargetText() {
  const J = S.jobs, t = J.t;
  if (J.batch) return T("jobs.form.count", {count: J.r.docs?.size || 0, repeats: J.r.repeat});
  return t.doc ? `${t.doc} · ${t.all ? T("jobs.form.all") : [...t.secs].map(section => T("jobs.form.section", {section})).join(", ")}` : T("jobs.form.no_doc");
}
function jobsResultSeconds(r) {
  const rows = Object.values(r?.results || {});
  return r?.run?.seconds ?? (rows.length === 1 ? rows[0].seconds : null);
}
// 같은 조건의 지난 시험 시간. 이 화면에서 끝까지 본 실제 시험만 기억한다.
function jobsTimingKey({doc, sections, all, model, set, custom_prompt}) {
  return JSON.stringify([doc, all ? null : [...(sections || [])].map(Number).sort((a, b) => a - b), !!all, model, set, !!custom_prompt]);
}
function jobsCurrentTiming() {
  const t = S.jobs.t;
  return S.jobs.timings[jobsTimingKey({doc: t.doc, sections: [...t.secs], all: t.all, model: t.model, set: S.ctx.set, custom_prompt: jobsSingle() && t.edit})];
}
function jobsStepList(current) {
  const J = S.jobs, order = ["target", "model", "prompt", "running", "result"], at = order.indexOf(current);
  const form = jobsForm(), valid = !jobsTargetReason(), running = jobsRunning(), seconds = J.batch ? null : jobsResultSeconds(J.result);
  const summary = {target: jobsTargetText(), model: form.model ? jobsModelLabel(form.model) : "",
    prompt: T(!J.batch && jobsSingle() && J.t.edit ? "steps.trial.prompt_used_edited" : "steps.trial.prompt_used_default"),
    running: num(seconds) ? T("steps.trial.took", {seconds: Math.round(seconds)}) : ""};
  const reachable = {target: !running, model: valid && !running, prompt: valid && !running && jobsReady(form.model), running, result: jobsFinished()};
  return order.map((id, index) => ({id, label: T(`steps.trial.${id}`), done: index < at, summary: index < at ? summary[id] : "",
    reachable: reachable[id], buttonId: `jobs-step-${id}`}));
}
function jobsResultHead() {
  const J = S.jobs, r = J.result, job = jobsWatched();
  if (J.batch) return [T("steps.trial.batch_done_title"), ""];
  if (job?.target && !jobsResultMatches(job, r)) return [T("jobs.target_mismatch.fact"), ""];
  if (!r.run && !r.results) return [T("steps.trial.practice_title"), ""];
  if (r.results && !Object.values(r.results).every(v => v.ok === true)) return [T("steps.trial.parse_title"), ""];
  const before = r.score?.before?.weighted, after = r.score?.after?.weighted;
  if (!num(before) || !num(after)) return [T("jobs.result.plain_done"), ""];
  // 한 부분 시험은 그 부분만 바꿔 계산한 점수다. 문서 전체를 새로 시험한 것으로 읽히지 않게 한다.
  const prefix = r.run ? "steps.trial.score" : "steps.trial.partial_score";
  return [T(`${prefix}_${after > before ? "up" : after < before ? "down" : "same"}`, {before: fmt1(before), after: fmt1(after)}), T("steps.trial.result_say")];
}
function jobsHead(step) {
  const J = S.jobs, form = jobsForm(), job = jobsWatched();
  if (step === "result") return jobsResultHead();
  if (step === "running") {
    if (job?.status === "failed") return [T("steps.trial.failed_title"), ""];
    if (job?.status === "stopped") return [T("jobs.stopped.fact"), ""];
    if (J.batch) return [T("steps.trial.batch_running_title"), T("jobs.running.leave_screen")];
    if (J.resultError) return [T("common.legacy.load_error.message"), ""];
    if (J.resultLoaded && !J.result && J.resultStatus === 204) return [T("jobs.result_missing.fact"), ""];
    if (job && job.status !== "running") return [T("jobs.result.pending"), ""];
    const t = job?.target || {};
    const what = t.all ? T("jobs.form.all") : (t.sections || []).map(section => T("jobs.form.section", {section})).join(", ");
    return [T("steps.trial.running_title", {target: what || jobsTargetText()}), T("jobs.running.leave_screen")];
  }
  if (J.optionsError) return [T("common.legacy.load_error.message"), ""];
  if (!J.opts) return [T("common.legacy.loading"), ""];
  if (step === "target") return [T("steps.trial.target_title"), T(J.batch ? "jobs.batch.title" : jobsPickedValue() ? "steps.trial.target_filled" : "steps.trial.target_say")];
  if (step === "prompt") return J.batch ? [T("steps.trial.batch_prompt_title"), ""] : [T("steps.trial.prompt_title"), T("steps.trial.prompt_say")];
  if (!form.model) return [T("jobs.form.no_models"), ""];
  const made = !J.batch && J.runs.find(run => run.name === J.t.base)?.model_tag === form.model;
  return jobsReady(form.model) ? [T("steps.trial.model_on_title", {model: jobsModelLabel(form.model)}), made ? T("steps.trial.model_on_say") : ""]
    : [T("steps.trial.model_off_title"), T("steps.trial.model_off_say")];
}
function jobsSendReason(real) {
  const J = S.jobs, t = J.t;
  if (J.optionsError) return T("common.legacy.load_error.message");
  const target = jobsTargetReason();
  if (target) return target;
  if (!t.model) return T("jobs.form.no_models");
  return real && !jobsReady(t.model) ? T("jobs.actions.run_unavailable") : "";
}
function jobsOpenServers() {
  const form = jobsForm();
  // 고른 AI를 켜러 가는 길에 다른 AI가 켜져도 고른 값을 바꾸지 않는다.
  if (!S.jobs.batch) form.modelPicked = true;
  return go("s06", {model: form.model, returnScreen: "s03"}).catch(fail);
}
function jobsActions(step) {
  const J = S.jobs, form = jobsForm(), ready = jobsReady(form.model), job = jobsWatched();
  const records = {label: T("jobs.running.open_jobs"), onClick: () => go("s05").catch(fail), attrs: {id: "jobs-open-records"}};
  const practice = J.batch ? null : {label: T("steps.trial.practice"), onClick: () => jobsStartTry({practice: true}),
    disabled: !!J.busy || !!jobsSendReason(false), attrs: {id: "jobs-practice", "data-guide": "s03-practice"}};
  const back = to => ({label: T("steps.back"), onClick: () => jobsGoStep(to), attrs: {id: "jobs-back"}});
  if (step === "target") {
    const reason = J.opts ? jobsTargetReason() : T("common.legacy.loading");
    return {note: J.batch || reason ? "" : T("steps.trial.batch_hint"),
      primary: {label: T("steps.next", {name: T("steps.trial.model")}), onClick: () => jobsGoStep("model"), disabled: !!reason, reason, attrs: {id: "jobs-next"}}};
  }
  if (step === "model") return {back: back("target"), note: ready ? "" : T("steps.trial.off_note"), secondary: practice,
    primary: ready ? {label: T("steps.next", {name: T("steps.trial.prompt")}), onClick: () => jobsGoStep("prompt"), attrs: {id: "jobs-next"}}
      : {label: T("steps.trial.prepare"), onClick: jobsOpenServers, disabled: !form.model, attrs: {id: "jobs-prepare"}}};
  if (step === "prompt") {
    if (J.batch) return {back: back("model"), primary: {label: T("jobs.batch.start"), onClick: jobsStartRun, disabled: !ready || !!J.busy || !J.r.docs?.size,
      reason: ready ? "" : T("jobs.actions.run_unavailable"), attrs: {id: "jobs-run-start"}}};
    const reason = jobsSendReason(true), seconds = jobsCurrentTiming();
    return {back: back("model"), secondary: practice,
      note: [J.t.model ? T("steps.trial.send_note", {target: jobsTargetText(), model: jobsModelLabel(J.t.model)}) : "",
        num(seconds) ? T("steps.trial.previous_time", {seconds: Math.round(seconds)}) : ""].filter(Boolean).join(" "),
      primary: {label: T(J.busy === "try" ? "jobs.form.sending" : "jobs.actions.send"), onClick: () => jobsStartTry({practice: false}), disabled: !!J.busy || !!reason, reason,
        attrs: {id: "jobs-send", "data-guide": "s03-send"}}};
  }
  if (step === "running") {
    if (!job || job.status === "running") return {secondary: records,
      back: job?.stoppable ? {label: T("jobs.running.stop"), disabled: !!J.busy, attrs: {id: "jobs-try-stop"},
        onClick: () => { J.confirm = {kind: "stop", id: job.id}; jobsOpenConfirm("jobs-try-stop"); }} : null,
      primary: {label: T("steps.trial.see_result"), disabled: true, reason: T("steps.trial.result_later"), attrs: {id: "jobs-see-result"}}};
    return {secondary: records, primary: {label: T("jobs.stopped.return_target"), onClick: () => jobsGoStep("prompt"), attrs: {id: "jobs-return-target"}}};
  }
  if (J.batch) return {back: back("target"), secondary: records,
    primary: {label: T("steps.trial.open_recent"), onClick: () => go("s01").catch(fail), attrs: {id: "jobs-open-recent"}}};
  const r = J.result;
  if (!r.run && !r.results) return {primary: {label: T("steps.trial.after_practice"), onClick: () => jobsGoStep(ready ? "prompt" : "model"), attrs: {id: "jobs-after-practice"}}};
  const again = {label: T("steps.trial.edit_again"), onClick: () => jobsGoStep("prompt"), attrs: {id: "jobs-edit-again"}};
  if (r.run) return {secondary: again, primary: r.saved ? {label: T("jobs.done.open_source"), attrs: {id: "jobs-whole-source"},
    onClick: () => go("s02", {run: r.saved.replace(/^.*?runs\//, ""), doc: r.plan?.doc_id, section: 1}).catch(fail)} : null};
  return {secondary: again, primary: job?.target ? {label: T("jobs.done.open_source"), attrs: {id: "jobs-result-source"},
    onClick: () => go("s02", {run: job.target.base_run || S.focus.run, doc: job.target.doc, section: job.target.sections?.[0] || 1, path: S.focus.path, line: S.focus.line}).catch(fail)} : null};
}
function jobsRenderFrame() {
  const step = jobsStep(), active = document.activeElement, activeId = active?.id, [title, say] = jobsHead(step);
  shellConclusion("s03", title);
  document.getElementById("jobs-step-say").textContent = say;
  stepsRenderBar(document.getElementById("jobs-step-bar"), {steps: jobsStepList(step), current: step, onGo: jobsGoStep});
  coreReplace(document.getElementById("jobs-details"), h("p", {class: "server-details-link"},
    h("button", {id: "jobs-details-open", type: "button", class: "text-button", onclick: jobsOpenDetails}, T("steps.details.open")), " ",
    T(step === "result" && jobsPractice(jobsWatched()) ? "steps.trial.details_hint_practice" : "steps.trial.details_hint")));
  stepsRenderActions(document.getElementById("jobs-actions"), jobsActions(step));
  if (activeId && !active.isConnected) document.getElementById(activeId)?.focus({preventScroll: true});
  if (S.drawer.screen === "s03") jobsRenderDrawer(document.querySelector("#details-drawer .drawer-body"));
}
function jobsModelNote(m) {
  const J = S.jobs, on = jobsReady(m.tag), where = serversModel(m.tag)?.where, pod = serversSessionPod(), quote = serversData()?.create_quote;
  const made = !J.batch && J.runs.find(run => run.name === J.t.base)?.model_tag === m.tag ? T("steps.trial.made_base") : null;
  const note = where === "RNGD" ? T(on ? "steps.trial.on_company" : "steps.trial.off_company")
    : where === "RunPod" && on && num(pod?.cost_per_hr) ? T("steps.trial.on_rented", {hourly: pod.cost_per_hr.toFixed(2)})
    : where === "RunPod" && !on && quote?.tag === m.tag && num(quote.cost_per_hr) ? T("steps.trial.off_rented", {hourly: quote.cost_per_hr.toFixed(2)})
    : on ? T("steps.trial.on_note") : null;
  return [made, note].filter(Boolean).join(" ");
}
function jobsModelState(m) {
  if (jobsReady(m.tag)) return T("steps.trial.state_on");
  const item = serversModel(m.tag);
  const state = item || S.shell.serverError ? serversState(item) : m.connected === false ? "state_off" : "readiness_unknown";
  return state === "state_off" ? T("steps.trial.state_off") : state === "connected" ? T("servers.models.connected") : T(`context.model.${state}`);
}
function jobsPickModel(form, kind, tag) {
  form.model = tag;
  if (kind === "try") { form.modelPicked = true; jobsRemember(); }
  else if (!form.edited) form.name = jobsSuggestName();
  jobsRenderSteps();
}
function jobsModelChoices(form, kind) {
  const id = kind === "try" ? "jobs-model" : "jobs-run-model";
  // AI 켜기 화면에서 다루는 모델만 고른다 (11/2 G4 사용자 결정). 이미 고른 모델은 몰래 바꾸지 않으려고 남긴다.
  const models = (S.jobs.opts?.models || []).filter(m => !jobsDraftModel(m) || m.tag === form.model)
    .sort((a, b) => Number(jobsDraftModel(a)) - Number(jobsDraftModel(b)));
  return h("fieldset", {id, class: "step-choices", "data-guide": kind === "try" ? "s03-model" : null, onchange: e => jobsPickModel(form, kind, e.target.value)},
    h("legend", null, T("jobs.form.model")),
    models.length ? models.map(m => {
      const on = form.model === m.tag, note = jobsModelNote(m);
      return h("label", {class: `step-choice${on ? " on" : ""}`},
        h("input", {id: `${id}-${m.tag}`, type: "radio", name: id, value: m.tag, checked: on, disabled: kind === "run" && m.connected !== true}),
        h("span", {class: "step-choice-body"}, h("b", null, jobsModelLabel(m.tag)), note ? h("small", null, note) : null),
        h("span", {class: `step-choice-state${jobsReady(m.tag) ? " on" : ""}`}, jobsModelState(m)));
    }) : jobsNote(T("jobs.form.no_models")));
}
function jobsRenderFocus() {
  const f = S.focus, valid = jobsPickedValue();
  const key = valid ? {wrong: "pair", missing: "missing", made: "made"}[f.kind] : null;
  const parsed = String(f.line || "").match(/^p(\d+):L(\d+)$/);
  const parts = String(f.path || "").replace(/\[\d+\]/g, "").split(".");
  const field = parts.slice().reverse().find(part => UI.source.field_names[part]) || parts.at(-1);
  const table = parts.find(part => UI.source.table_names[part]);
  // 고른 값이 없으면 강조할 것이 없다. 한 줄로만 말한다.
  if (!key) return h("p", {id: "jobs-focus", class: "muted"}, T("jobs.focus.none", {key_value: "", ai_value: ""}));
  return h("div", {id: "jobs-focus", class: "job-focus"}, h("h3", null, T("jobs.focus.title")),
    key ? jobsNote([UI.source.table_names[table], sourceFieldName({field, table}, null)].filter(Boolean).join(" · ")) : null,
    jobsNote(T(`jobs.focus.${key || "none"}`, {key_value: jobsFocusValue(f.expected, f.expected_text), ai_value: jobsFocusValue(f.actual, f.actual_text)})),
    // 줄 표시(p1:L29)는 기록 값이다. 화면에는 쪽과 줄로 쓰고 기록 값은 서랍에 둔다.
    key && parsed ? jobsNote(f.line_text ? T(`jobs.focus.${f.estimated ? "line_estimated" : "line"}`,
      {page: parsed[1], line_no: parsed[2], line_text: f.line_text}) : T(`jobs.form.${f.estimated ? "focus_estimated" : "focus_line"}`, {page: parsed[1], line_no: parsed[2]})) : null);
}
function jobsSetName(id) { return S.shell.sets.find(set => set.id === id)?.label || id; }
function jobsSetNotice() {
  return S.focus.source_set && S.focus.source_set !== S.ctx.set ? h("div", {class: "job-notice"}, jobsNote(T("jobs.set_mismatch.title")),
    jobsNote(T("jobs.form.source_set", {set: jobsSetName(S.focus.source_set)})), jobsNote(T("jobs.form.next_set", {set: jobsSetName(S.ctx.set)}))) : null;
}
// ① 무엇을: 세 갈래. 갈래를 바꿔도 다른 갈래의 초안은 지우지 않는다.
function jobsStageTarget() {
  const J = S.jobs, t = J.t, branch = J.batch ? "batch" : t.all ? "document" : "part";
  const seg = h("div", {class: "step-seg", role: "group", "aria-label": T("steps.trial.scope.a11y")}, ["part", "document", "batch"].map(kind =>
    h("button", {id: `jobs-branch-${kind}`, type: "button", class: kind === branch ? "on" : null, "aria-pressed": String(kind === branch), onclick: () => jobsChooseBranch(kind)},
      T(`steps.trial.scope.${kind}`))));
  if (J.batch) return [seg];
  const docs = jobsDocs();
  // 고를 수 있는 문서를 먼저 둔다. 평가용 문서는 한 줄로 줄인다(열 수 없고 번호순으로 맨 앞에 와서 개발 문서를 가린다).
  const closed = docs.filter(d => !jobsAllowed(d, "try") && d.group !== "eval"), evals = docs.filter(d => !jobsAllowed(d, "try") && d.group === "eval");
  const closedReason = d => d.run_reason?.try || T("jobs.no_runnable.todo");
  const select = h("select", {"data-guide": "s03-target", onchange: e => { t.doc = e.target.value; jobsRemember(); jobsRenderSteps(); }},
    h("option", {value: ""}, T("jobs.form.no_doc")), [...docs.filter(d => jobsAllowed(d, "try")), ...closed].map(d => h("option", {value: d.doc_id, disabled: !jobsAllowed(d, "try")},
      d.doc_id, d.run_reason?.try ? ` — ${d.run_reason.try}` : ""))); select.value = t.doc || "";
  const base = h("select", {onchange: e => {
    t.base = e.target.value; t.model = jobsDefaultModel(J.runs.find(run => run.name === t.base)?.model_tag);
    t.modelPicked = !!t.base; jobsRemember(); jobsRenderSteps();
  }},
    h("option", {value: ""}, T("jobs.form.base_auto")),
    J.runs.filter(r => !["eval", "silver", "models"].includes(r.run_kind) && [...(r.docs || []), ...(r.no_gold || [])].includes(t.doc))
      .map(r => h("option", {value: r.name}, jobsRunLabel(r))));
  if (t.base && ![...base.querySelectorAll("option")].some(option => option.value === t.base)) base.append(h("option", {value: t.base}, t.base));
  base.value = t.base;
  return [seg, jobsSetNotice(),
    h("div", {class: "step-card"}, h("div", {class: "job-form-grid"},
      jobsField("jobs-doc", T("jobs.form.doc"), T("jobs.fields.doc"), select),
      jobsField("jobs-base", term("base_run", T("jobs.scope.base_run")), T("jobs.fields.base_run"), base)),
      t.all ? jobsNote(T("jobs.form.all")) : h("fieldset", null, h("legend", null, T("jobs.scope.label")),
        h("div", {class: "job-sections"}, Array.from({length: 16}, (_, i) => i + 1).map(n => h("label", null,
          h("input", {id: `jobs-section-${n}`, type: "checkbox", checked: t.secs.has(n), onchange: e => {
            e.target.checked ? t.secs.add(n) : t.secs.delete(n); jobsRemember(); jobsRenderSteps();
          }}), sourceLabel(n))))),
      t.all ? null : jobsNote(T("jobs.fields.scope"), {class: "muted"})),
    docs.some(d => jobsAllowed(d, "try")) ? null : jobsNote(T("jobs.no_runnable.fact")),
    h("ul", {class: "muted"}, evals.length ? h("li", null, T("jobs.batch.eval_locked", {count: evals.length})) : null,
      [...new Set(closed.map(closedReason))].map(reason => h("li", null, closed.filter(d => closedReason(d) === reason).map(d => d.doc_id).join(", "), " — ", reason))),
    t.all ? null : jobsRenderFocus()];
}
// ② 어느 AI로: 고르는 칸은 접지 않는다. 켜는 길은 jobs-connection과 행동 줄에 있다.
function jobsStageModel() {
  const J = S.jobs, form = jobsForm();
  return [jobsModelChoices(form, J.batch ? "run" : "try"),
    !J.batch && form.model ? jobsModelDifference(form.model, J.runs.find(run => run.name === J.t.base)?.model_tag) : null,
    jobsNote(J.opts.try_hint?.note || T("jobs.try_hint.off"), {role: "status"}),
    jobsButton("jobs-options-reload", "jobs.form.reload", jobsPoll, !!J.loadingOptions),
    J.batch ? null : jobsNote(term("practice", T("steps.trial.practice_button_note")), {class: "muted"}),
    J.batch ? null : serversFlat(J.message.try) || null];
}
// ③ 무엇을 시킬지: 한 부분만 고쳐 쓸 수 있다. 늦게 온 기본 글은 고친 글을 덮지 못한다(jobsLoadPrompt).
function jobsStagePrompt() {
  const J = S.jobs, t = J.t, one = jobsSingle();
  if (!one) return [jobsSetNotice(), h("div", {class: "step-card"}, jobsNote(T("jobs.multiple.no_edit")), jobsNote(T("jobs.multiple.default_prompt"))),
    jobsNote(term("practice", T("steps.trial.practice_button_note")), {class: "muted"}), serversFlat(J.message.try) || null];
  const choice = (id, on, key) => h("label", {class: `step-choice${on ? " on" : ""}`},
    h("input", {id, type: "radio", name: "jobs-prompt-mode", checked: on, onchange: e => {
      t.edit = id === "jobs-edit" ? e.target.checked : !e.target.checked; jobsRenderTry();
    }}),
    h("span", {class: "step-choice-body"}, h("b", null, T(`steps.trial.${key}`)), h("small", null, T(`steps.trial.${key}_note`))));
  const textarea = h("textarea", {rows: 8, class: "job-prompt technical", spellcheck: "false",
    oninput: e => { t.text = e.target.value; t.edit = true; t.dirty = true; t.revision = (t.revision || 0) + 1;
      const edit = document.getElementById("jobs-edit"), plain = document.getElementById("jobs-edit-default");
      if (edit) edit.checked = true;
      edit?.closest(".step-choice")?.classList.add("on"); plain?.closest(".step-choice")?.classList.remove("on"); }});
  textarea.value = t.text;
  const field = jobsField("jobs-prompt", term("prompt", T("jobs.form.prompt")), T("jobs.prompt.hint"), textarea);
  textarea.setAttribute("aria-describedby", "jobs-prompt-help jobs-prompt-status");
  return [jobsSetNotice(),
    h("div", {class: "step-choices"}, choice("jobs-edit-default", !t.edit, "prompt_default"), choice("jobs-edit", t.edit, "prompt_edit")),
    field,
    h("div", {id: "jobs-prompt-status", role: J.promptError ? "alert" : "status"},
      J.promptBusy ? jobsNote(T("jobs.form.prompt_loading")) : J.promptError ? serversFlat(loadFailure(J.promptError.message)) : null),
    jobsButton("jobs-load-prompt", "jobs.form.load_prompt", jobsLoadPrompt, !t.model || J.promptBusy),
    t.textFor && t.textFor !== `${t.model}|${[...t.secs][0]}` ? jobsNote(T("jobs.prompt.review_foreign"), {class: "warning"}) : null,
    jobsNote(T("jobs.prompt.retest_hint"), {class: "muted"}),
    jobsNote(term("practice", T("steps.trial.practice_button_note")), {class: "muted"}), serversFlat(J.message.try) || null];
}
function jobsRenderTry() {
  const J = S.jobs, t = J.t, el = document.getElementById("jobs-try");
  if (!J.opts) {
    el.hidden = false;
    coreReplace(el, serversFlat(jobsFormStatus()) || jobsNote(T("common.legacy.loading"), {role: "status"}));
    jobsRenderFrame(); return;
  }
  const active = document.activeElement?.id, step = jobsStep();
  const body = step === "target" ? jobsStageTarget() : step === "model" ? jobsStageModel() : step === "prompt" && !J.batch ? jobsStagePrompt() : null;
  el.hidden = !body;
  coreReplace(el, body ? [serversFlat(jobsFormStatus()), body] : []);
  if (active) document.getElementById(active)?.focus({preventScroll: true});
  jobsRenderFrame();
  const allowed = jobsAllowed(jobsDocs().find(d => d.doc_id === t.doc), "try"), one = jobsSingle();
  emit("trial_form_shown", {valid: !J.optionsError && allowed && one, connected: jobsReady(t.model),
    signature: JSON.stringify([t.doc, [...t.secs], t.all, t.model, S.ctx.set, S.ctx.key])});
  if (S.shell.route === "s03" && allowed && one && t.model && !t.edit && !t.dirty && J.promptAttempt !== jobsPromptKey()) {
    J.promptPending = jobsLoadPrompt({automatic: true});
  }
}
function jobsConnectionActions(tag) {
  const data = serversData(), model = serversModel(tag), out = [];
  const choice = data?.rngd_choices?.find(item => item.tag === tag);
  if (choice) {
    if (data.rngd?.tunnel?.open === false) out.push(serversAction("tunnel_open", {}, T("servers.busy.open_tunnel"), "jobs"));
    out.push(serversAction("rngd_up", {tag: choice.tag}, T("servers.company.confirm_load", {model: choice.label || choice.model}), "jobs"));
    for (const loaded of data.rngd?.models || []) out.push(serversAction("rngd_down", {model: loaded.model}, T("servers.ready.confirm_unload"), `jobs-${loaded.pid}`));
  } else if (model?.where === "RunPod") {
    out.push(jobsNote(T("servers.empty.new_cost")), serversAction("pod_create", {}, T("servers.rented.confirm_create"), "jobs"));
  }
  return out;
}
function jobsRenderConnection() {
  const el = document.getElementById("jobs-connection"), tag = jobsForm().model;
  const show = jobsStep() === "model" && !jobsReady(tag) && !!S.jobs.opts;
  el.hidden = !show;
  if (!show) { S.servers.compacts.delete(el); coreReplace(el); return; }
  serversRenderCompact(el, {model: tag, inStep: true, extra: () => jobsConnectionActions(tag)});
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
// 단추가 연습인지 실제 시험인지 정한다. 체크박스로 주 단추의 뜻을 바꾸지 않는다. 인자가 없으면 안내가 정한 값(t.dry)을 쓴다.
async function jobsStartTry(mode = {}) {
  const J = S.jobs, t = J.t;
  if (!J.busy && typeof mode.practice === "boolean") t.dry = mode.practice;
  if (J.busy || J.optionsError || !jobsAllowed(jobsDocs().find(d => d.doc_id === t.doc), "try") || !t.model || (!t.dry && !jobsReady(t.model))) return;
  const one = jobsSingle();
  const problem = !S.ctx.set || !S.ctx.key ? "missing_context" : !t.all && !t.secs.size ? "no_sections"
    : one && t.edit && !t.text.trim() ? "prompt_empty"
    : one && t.edit && t.textFor && t.textFor !== `${t.model}|${[...t.secs][0]}` ? "prompt_foreign" : null;
  if (problem) { J.message.try = jobsNote(T(`jobs.form.${problem}`), {role: "alert"}); jobsRenderTry(); return; }
  const body = jobsTryBody(t);
  J.busy = "try"; J.message.try = null; J.sendError = null; jobsRemember(); jobsRenderTry();
  try {
    const data = await jobsSubmitTry(body);
    J.watch = data.id; J.result = null; J.resultStatus = null; J.resultLoaded = false; J.resultError = null; J.resultRequest++;
    J.step = "job";
    jobsRenderSteps();
    if (S.shell.route === "s03") {
      const result = document.getElementById("jobs-result"), context = document.getElementById("global-context");
      result.style.scrollMarginTop = `${context?.offsetHeight || 0}px`;
      result.setAttribute("tabindex", "-1"); result.focus({preventScroll: true}); result.scrollIntoView?.({block: "start"});
    }
    await jobsPoll();
  } catch (error) { J.sendError = error; J.message.try = jobsRequestError(error); }
  finally {
    J.busy = null; jobsRenderTry(); jobsRenderResult();
  }
}

function jobsTargetHead(job) {
  const t = job?.target;
  if (!t) return [jobsNote(T("jobs.record.unknown")), jobsNote(T("jobs.legacy.no_target"))];
  const head = t.kind === "try" ? `${t.doc || T("common.none")} · ${t.all ? T("jobs.form.all") : (t.sections || []).map(section => T("jobs.form.section", {section})).join(", ")}`
    : t.kind === "run" ? (t.docs || []).join(", ") : t.title || T("common.none");
  return [jobsNote(head, {class: "technical"}), t.model ? jobsNote(jobsModel(t.model)?.label || t.model, {class: "technical"}) : null];
}
function jobsTargetConditions(job) {
  const t = job.target;
  return [t.set ? jobsNote(`${T("jobs.running.set")}: ${t.set}`, {class: "technical"}) : null,
      t.pages_dir ? jobsNote(`${T("jobs.detail.pages")}: ${t.pages_dir}`, {class: "technical"}) : null,
      t.kind === "try" ? jobsNote(T("jobs.result.key", {label: t.key?.label || T("jobs.result.key_unknown")})) : null,
      t.key?.fingerprint ? jobsNote(`${T("jobs.detail.key_hash")} ${t.key.fingerprint}`, {class: "technical"}) : null,
      t.base_run ? jobsNote(`${T("jobs.detail.base_run")} ${t.base_run}`, {class: "technical"}) : null,
      t.kind === "try" ? jobsNote(T(jobsPractice(job) ? "jobs.trial.practice_meaning" : "jobs.running.real_trial")) : null,
      t.custom_prompt ? jobsNote(T("jobs.selected.prompt")) : null,
      t.repeat ? jobsNote(T("jobs.form.count", {count: t.docs?.length || 0, repeats: t.repeat})) : null,
      [...(t.run_names || []), ...(t.runs || [])].map(name => jobsNote(name, {class: "technical"}))];
}
function jobsTarget(job) {
  if (!job?.target) return h("div", null, jobsTargetHead(job));
  return h("div", {class: "job-target"}, jobsTargetHead(job), jobsDetails(`jobs-target-${job.id}`, T("jobs.record.conditions"), jobsTargetConditions(job)));
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
// 결과 기록은 서랍에 평평하게 둔다.
function jobsStage(index, ...body) {
  const [title, help] = jobsStages[index];
  return h("div", {id: `jobs-stage-${S.jobs.watch}-${index}`, class: "drawer-section"}, h("h3", null, T(`jobs.detail.${title}`)),
    h("p", {class: "job-stage-help"}, T(`jobs.stages.${help}`)), body);
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
  if (r.run) return h("div", {role: "status"}, jobsNote(T("jobs.whole_done.kind")),
    jobsNote(T("jobs.result.whole_stats", {ok: r.run.sections_ok, failed: r.run.sections_failed, retries: r.run.reextracted, seconds: fmt1(r.run.seconds)})), jobsScore(r, job));
  if (r.results) {
    const rows = Object.values(r.results), ok = rows.length > 0 && rows.every(v => v.ok === true);
    return h("div", {role: "status"}, jobsNote(T(ok ? "jobs.result.plain_done" : "jobs.parse_failed.fact")),
      !ok ? jobsNote(T("steps.trial.parse_todo")) : null, jobsScore(r, job));
  }
  return h("div", {role: "status"}, jobsNote(T(jobsPractice(job) ? "jobs.practice_done.title" : "jobs.result.practice_unconfirmed")),
    jobsNote(T("jobs.practice_done.no_success")), jobsNote(T("steps.trial.practice_omitted")));
}
// 결과를 본 뒤에도 켜진 서버가 있으면 알린다. 요금은 위쪽 막대와 같은 값이다. 지금 쓰는 서버만 읽는다.
function jobsServerNote() {
  const data = serversData(), pod = serversSessionPod();
  const company = !pod && (data?.models || []).some(model => model.where === "RNGD" && serversReady(model));
  if (!pod && !company) return null;
  return h("div", {class: "job-notice job-server-note"},
    h("p", null, T(pod ? "steps.trial.server_on" : "steps.trial.company_on"), pod ? ` ${shellCostText(data, null)}` : ""),
    h("button", {id: "jobs-server-open", type: "button", onclick: () => go("s06").catch(fail)}, T("steps.trial.close_server")));
}
function jobsBatchBody(step) {
  const job = jobsWatched();
  return [job ? h("div", {class: "job-target"}, jobsTargetHead(job)) : jobsNote(T("jobs.form.sent"), {role: "status"}),
    job ? jobsStatus(job) : null, job ? serversFlat(jobsFailure(job)) : null, jobsWarnings(job?.warnings), job ? jobsProgress(job) : null,
    step === "result" ? jobsServerNote() : null];
}
function jobsRenderTryResult(el) {
  const J = S.jobs, job = J.list.find(j => j.id === J.watch);
  const head = [job ? h("div", {class: "job-target"}, jobsTargetHead(job)) : null, job ? jobsStatus(job) : null,
    job ? serversFlat(jobsFailure(job)) : null, jobsWarnings(job?.warnings)];
  if (job?.status === "stopped") { coreReplace(el, head, jobsNote(T("jobs.stopped.fact")), jobsNote(T("jobs.stopped.late_reply"))); return; }
  if (J.resultError) { coreReplace(el, head, serversFlat(loadFailure(J.resultError.message)), jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return; }
  if (!J.resultLoaded) {
    const seconds = num(job?.started) ? Math.max(0, Math.round(Date.now() / 1000 - job.started)) : null;
    coreReplace(el, head, job && job.status !== "running" ? jobsNote(T("jobs.result.pending"), {role: "status"})
      : h("div", {class: "step-card"}, serversProgress([["done", T("steps.trial.sent")], ["now", T("steps.trial.pending")]]),
        num(seconds) ? jobsNote(T("steps.trial.elapsed", {seconds}), {class: "muted", role: "status"}) : null));
    return;
  }
  const r = J.result;
  if (J.resultStatus !== 200 && J.resultStatus !== 204) {
    coreReplace(el, head, jobsNote(T("jobs.result.pending"), {role: "status"}),
      jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return;
  }
  // 실패한 작업에 결과 파일이 없는 것은 당연하다. 실패 안내만 보인다.
  if (!r && job?.status === "failed") { coreReplace(el, head); return; }
  if (!r) {
    coreReplace(el, head, jobsNote(h("strong", null, T("jobs.result_missing.fact"))), jobsNote(T("jobs.result_missing.todo", {status_code: 204})),
      jobsButton("jobs-result-log", "jobs.result_missing.open_log", () => jobsOpenLog(J.watch)), jobsButton("jobs-result-retry", "jobs.result.retry", () => jobsLoadResult(J.watch))); return;
  }
  const mismatch = job?.target && !jobsResultMatches(job, r), seconds = jobsResultSeconds(r);
  if (job?.target && !jobsPractice(job) && num(seconds)) J.timings[jobsTimingKey(job.target)] = seconds;
  // 대상과 끝남은 단계 표시와 제목에 이미 있다. 연습은 연습이라고 남긴다. 켜진 서버 글은 첫 화면 안에 오도록 고른 값보다 앞에 둔다.
  coreReplace(el, jobsPractice(job) ? head : [job ? serversFlat(jobsFailure(job)) : null, jobsWarnings(job?.warnings)],
    mismatch ? serversFlat(friendlyError({message: T("jobs.target_mismatch.fact"), fix: T("jobs.target_mismatch.todo")})) : null,
    jobsResultSummary(r, job), jobsServerNote(),
    r.results && jobsPickedValue() && S.focus.kind ? [jobsRenderFocus(), jobsRenderChange(job)] : null);
  if (job && !mismatch) jobsEmitResult(job, r);
}
// ── 고른 값의 전후 (STEPS.md A7). 저장한 결과가 있을 때만 읽는다. 점수와 판정은 서버가 정한 값을 그대로 쓴다. ──
// 행 번호는 문서마다 달라 같은 행의 표시가 아니다. 표의 행은 짝 정답 행으로, 짝 없는 AI 행은 제목으로, 표가 아닌 값은 경로로 찾는다.
function jobsSameCell(before, after, path, only) {
  const from = sourceRowOf(path, only, before), cell = from?.cells.find(item => item.path === path && (item.side === "silver_only") === only);
  if (!cell) return null;
  const rows = sourceRows(after);
  const to = from.row == null && from.gold_row == null ? rows.find(row => row.row == null && row.gold_row == null && row.cells.some(item => item.path === path))
    : from.gold_row != null ? rows.find(row => row.table === from.table && row.gold_row === from.gold_row)
    : rows.find(row => row.table === from.table && row.gold_row == null && row.title === from.title);
  return {cell, to: to?.cells.find(item => item.field === cell.field) || null, found: !!to};
}
function jobsChangeText(data, cell) {
  const v = cell && cell.side !== "silver_only" ? data.values.find(value => value.path === cell.path) : null;
  return v?.text ?? T("steps.trial.change_none");
}
async function jobsLoadChange(job, r) {
  const J = S.jobs, f = S.focus, t = job?.target;
  J.change = null;
  // 점수를 계산한 시험만 결과 문서를 남긴다(try_section.save_manual_run). 같은 문서·부분·기준 결과일 때만 비교한다.
  if (!r?.results || !r.score || !r.saved || !f.path || !f.run || !t || t.doc !== f.doc || !(t.sections || []).includes(Number(f.section)) || (t.base_run && t.base_run !== f.run)) return;
  const run = r.saved.replace(/^.*?runs\//, ""), id = job.id, path = f.path;
  const read = name => api(`/api/doc?${new URLSearchParams({run: name, doc: f.doc, ...(t.key?.id ? {key: t.key.id} : {})})}`);
  J.change = {job: id, path, state: "loading"};
  jobsRenderResult();
  let next = {job: id, path, state: "none"};
  try {
    const [before, after] = await Promise.all([read(f.run), read(run)]);
    const same = jobsSameCell(before, after, path, f.kind === "missing");
    if (same) next = {job: id, path, state: "ready", run, doc: f.doc, section: f.section, found: same.found, field: same.cell.field,
      before: {text: jobsChangeText(before, same.cell), kind: same.cell.kind},
      after: same.to ? {text: jobsChangeText(after, same.to), kind: same.to.kind, path: same.to.path, side: same.to.side} : null};
  } catch (_) { /* 읽지 못하면 비교할 결과가 없다고 말한다 */ }
  if (J.change?.job === id && J.change.path === path) J.change = next;
}
function jobsRenderChange(job) {
  const c = S.jobs.change;
  if (c?.job !== job?.id || c?.path !== S.focus.path || c.state === "none") return jobsNote(T("steps.trial.change_unavailable"), {class: "muted"});
  if (c.state === "loading") return jobsNote(T("steps.trial.change_loading"), {class: "muted", role: "status"});
  const same = c.after && c.after.text === c.before.text && c.after.kind === c.before.kind;
  return h("div", {id: "jobs-change", class: "job-notice"}, h("h3", null, T("steps.trial.change_title")),
    !c.after ? jobsNote(T("steps.trial.change_gone")) : same ? jobsNote(T("steps.trial.change_same")) : [
      jobsNote(T("steps.trial.change_value", {before: c.before.text, after: c.after.text})),
      jobsNote(T("steps.trial.change_kind", {before: T(`source.kinds.${c.before.kind}`), after: T(`source.kinds.${c.after.kind}`)}))],
    c.after ? h("button", {id: "jobs-change-source", type: "button", onclick: () => go("s02", {run: c.run, doc: c.doc, section: Number(c.section), path: c.after.path,
      kind: c.after.kind, estimated: c.after.side === "silver_only"}).catch(fail)}, T("steps.trial.change_open")) : null);
}
function jobsRenderResult() {
  const J = S.jobs, el = document.getElementById("jobs-result"), step = jobsStep(), show = step === "running" || step === "result";
  el.setAttribute("data-guide", "s03-result-summary");
  el.hidden = !show;
  if (!show) coreReplace(el);
  else if (J.batch) coreReplace(el, jobsBatchBody(step));
  else jobsRenderTryResult(el);
  jobsRenderFrame();
}
// ── 자세히 서랍: 고른 값의 기록, 입력 폴더, 잠긴 문서, 지시문 보관, 시험 기록, 오류 기록 ──
function jobsDrawerLocks() {
  const J = S.jobs, kind = J.batch ? "run" : "try", locked = jobsDocs().filter(d => !jobsAllowed(d, kind));
  if (!locked.length) return null;
  const evaluation = locked.filter(d => d.group === "eval"), reasons = new Map();
  for (const doc of locked) {
    const reason = doc.run_reason?.[kind] || T("context.unavailable");
    if (!reasons.has(reason)) reasons.set(reason, []);
    reasons.get(reason).push(doc.doc_id);
  }
  return h("div", {id: `jobs-${kind}-locked`, class: "drawer-section"},
    h("h3", null, evaluation.length ? T("jobs.batch.eval_locked", {count: evaluation.length}) : T("jobs.batch.runnable")),
    [...reasons].map(([reason, ids]) => [jobsNote(reason), jobsNote(ids.join(", "), {class: "technical"})]));
}
function jobsDrawerStages() {
  const J = S.jobs, r = J.result, job = jobsWatched();
  if (J.batch || !J.watch || !r) return null;
  const p = r.plan || {}, secs = Object.entries(p.sections || {});
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
  if (r.run) {
    parts.push(jobsStage(2, jobsNote(T("jobs.result.whole_stats", {ok: r.run.sections_ok, failed: r.run.sections_failed, retries: r.run.reextracted, seconds: fmt1(r.run.seconds)})),
      jobsNote(T("jobs.whole_done.raw_path")), jobsNote(r.saved ? `${r.saved}/raw/` : T("common.none"), {class: "technical"})),
      jobsStage(3, jobsPre(r.summary || {})), jobsStage(4, jobsNote(T("jobs.whole_done.no_journey_success"))));
  } else if (r.results) {
    const rows = Object.entries(r.results);
    parts.push(jobsStage(2, rows.map(([no, v]) => h("div", null, h("h4", null, T("jobs.result.section", {section: no})),
      jobsNote(T("jobs.result.raw_meta", {mode: coreCodeLabel("mode", v.mode), reason: coreCodeLabel("finish", v.finish_reason), seconds: fmt1(v.seconds)})),
      coreCodeRecord(v.mode, v.finish_reason), jobsPre(v.raw_text || T("jobs.result.no_answer"))))),
      jobsStage(3, rows.map(([no, v]) => h("div", null, h("h4", null, T("jobs.result.section", {section: no})),
        jobsNote(T(v.ok ? "jobs.result.ok" : "jobs.result.bad")), jobsNote(T("jobs.result.parse_meta", {discarded: v.dropped_rows, retries: v.reextracted ? 1 : 0, attempts: v.attempts})),
        jobsNote(T("jobs.detail.tokens", {input_tokens: v.usage?.prompt_tokens, output_tokens: v.usage?.completion_tokens})),
        jobsWarnings(v.errors), jobsWarnings(v.check_problems), jobsPre(v.parsed)))),
      jobsStage(4, h("ul", null, Object.entries(r.fields || {}).map(([no, fields]) => h("li", null, T("jobs.result.section", {section: no}),
        h("ul", null, Object.entries(fields || {}).map(([name, count]) => h("li", null,
          T("jobs.result.fields_count", {name: UI.source?.rows?.[name] || name, count: jobsValue(count)})))))))));
  }
  if (r.saved) parts.push(jobsNote(`${T("jobs.completion.path")} ${r.saved}`, {class: "technical"}));
  if (job?.target && !jobsResultMatches(job, r)) parts.push(jobsNote(T("jobs.target_mismatch.todo")));
  return parts;
}
function jobsDrawerRaw() {
  const J = S.jobs, job = jobsWatched(), failure = error => error?.body?.error || error?.message;
  const raws = [failure(J.optionsError), failure(J.promptError), failure(J.resultError), failure(J.sendError), failure(J.runError),
    job?.error?.raw, failure(S.shell.serverError) && serversText(failure(S.shell.serverError)), serversText(serversModel(jobsForm().model)?.friendly?.raw)];
  const unique = [...new Set(raws.filter(Boolean).map(String))];
  const exit = job?.status === "failed" ? T(num(job.returncode) ? "jobs.legacy.exit_code" : "jobs.record.exit_missing", {count: job.returncode}) : null;
  return unique.length || exit ? serversDrawerSection(T("common.raw_error_title"), exit ? jobsNote(exit) : null, unique.map(raw => jobsPre(raw))) : null;
}
function jobsRenderDrawer(body) {
  const J = S.jobs, job = jobsWatched();
  coreReplace(body,
    jobsPickedValue() ? serversDrawerSection(T("jobs.focus.title"), coreCodeRecord(S.focus.path)) : null,
    serversDrawerSection(T("jobs.scope.sets"), jobsNote(T("jobs.fields.pages")), jobsNote(jobsSet()?.label || S.ctx.set || T("common.none"))),
    jobsDrawerLocks(),
    J.batch ? serversDrawerSection(T("jobs.batch.details"), ["kind", "repeat_range", "keep_awake", "confirm", "outside_policy"].map(key => jobsNote(T(`jobs.batch.${key}`))))
      : serversDrawerSection(T("steps.trial.prompt_origin_title"), ["origin", "memory_only", "delete_temp", "hash_only"].map(key => jobsNote(T(`jobs.prompt.${key}`)))),
    job ? serversDrawerSection(T("steps.trial.conditions_title"), jobsNote(job.id, {class: "technical"}), job.target ? jobsTargetConditions(job) : jobsTargetHead(job)) : null,
    jobsDrawerStages(), jobsDrawerRaw());
  drawerFlatten(body);
}
function jobsOpenDetails() {
  drawerOpen({title: T("steps.trial.details_title"), trigger: document.getElementById("jobs-details-open"), render: jobsRenderDrawer});
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
  if (J.watch !== id || request !== J.resultRequest) return;
  jobsRenderResult();
  if (J.result) {
    await jobsLoadChange(J.list.find(job => job.id === id), J.result);
    if (J.watch === id && request === J.resultRequest) jobsRenderResult();
  }
}
async function jobsWatch(id, navigate = true) {
  const J = S.jobs;
  J.selected = id; J.batch = false; J.step = "job";
  if (J.watch !== id) { J.watch = id; J.result = null; J.resultStatus = null; J.resultLoaded = false; J.resultError = null; J.resultRequest++; }
  if (navigate && S.shell.route !== "s03") await go("s03");
  if (J.list.find(j => j.id === id)?.status !== "running") await jobsLoadResult(id);
  jobsRenderSteps();
}

// ‘여러 문서’ 갈래의 입력. ①에서 문서와 반복과 이름을 고르고 ③에서 조건을 확인한다. 잠긴 문서 전체 목록은 서랍에 있다.
function jobsRunForm() {
  const J = S.jobs, r = J.r;
  const refill = () => { if (!r.edited) r.name = jobsSuggestName(); jobsRenderRun(); };
  const docs = jobsDocs(), allowed = docs.filter(d => jobsAllowed(d, "run")), locked = docs.filter(d => !jobsAllowed(d, "run"));
  const evaluation = locked.filter(d => d.group === "eval"), closed = locked.filter(d => d.group !== "eval");
  const checkbox = d => h("label", null,
    h("input", {id: `jobs-run-doc-${d.doc_id}`, type: "checkbox", checked: r.docs?.has(d.doc_id), disabled: !jobsAllowed(d, "run"),
      onchange: e => { e.target.checked ? r.docs.add(d.doc_id) : r.docs.delete(d.doc_id); refill(); }}), d.doc_id);
  const count = () => T("jobs.form.count", {count: r.docs?.size || 0, repeats: r.repeat});
  return [jobsNote(jobsSet()?.label || S.ctx.set || T("common.none")),
    h("fieldset", null, h("legend", null, T("jobs.batch.select_docs")),
      h("div", {class: "job-actions"}, jobsButton("jobs-select-all", "jobs.form.select_all", () => { r.docs = new Set(allowed.map(d => d.doc_id)); refill(); }),
        jobsButton("jobs-select-none", "jobs.form.select_none", () => { r.docs.clear(); refill(); })),
      h("div", {class: "job-docs"}, allowed.map(d => h("div", null, checkbox(d), d.run_reason?.run ? jobsNote(d.run_reason.run) : null))),
      jobsNote(count(), {id: "jobs-run-count", role: "status"})),
    evaluation.length ? jobsNote(T("jobs.batch.eval_locked", {count: evaluation.length}), {class: "muted"}) : null,
    closed.length ? h("div", {class: "job-docs"}, closed.map(d => h("div", null, checkbox(d), jobsNote(d.run_reason?.run || T("context.unavailable"), {class: "muted"})))) : null,
    h("div", {class: "job-form-grid"}, jobsField("jobs-repeat", T("jobs.batch.repeats"), T("jobs.fields.repeat"),
      h("input", {type: "number", min: 1, max: 10, value: r.repeat, oninput: e => {
        r.repeat = Number(e.target.value);
        document.getElementById("jobs-run-count").textContent = count();
        jobsRenderFrame();
      }})),
      jobsField("jobs-run-name", T("jobs.form.run_name"), T("jobs.fields.run_name"), h("input", {type: "text", class: "technical", value: r.name,
        oninput: e => { r.name = e.target.value; r.edited = true; jobsRenderFrame(); }}))),
    jobsButton("jobs-suggest", "jobs.form.suggest", () => { r.edited = false; refill(); })];
}
function jobsRunReview() {
  const J = S.jobs, r = J.r;
  return [serversFlat(jobsFormStatus()),
    h("div", {class: "step-card"}, jobsNote(T("jobs.form.count", {count: r.docs?.size || 0, repeats: r.repeat}), {id: "jobs-run-count", role: "status"}),
      jobsNote([...(r.docs || [])].join(", "), {class: "technical"}),
      r.model ? jobsNote(jobsModelLabel(r.model)) : null,
      jobsNote(`${T("jobs.form.run_name")}: ${r.name}`, {class: "technical"})),
    jobsNote(T("jobs.multiple.default_prompt")),
    serversFlat(J.message.run) || null,
    J.confirm?.kind === "run" ? jobsNote(J.confirm.summary, {class: "technical"}) : null];
}
function jobsRenderRun() {
  const J = S.jobs, el = document.getElementById("jobs-run"), step = jobsStep();
  const show = J.batch && !!J.opts && ["target", "prompt"].includes(step), active = document.activeElement?.id;
  el.hidden = !show;
  coreReplace(el, !show ? [] : step === "target" ? jobsRunForm() : jobsRunReview());
  if (show && active) document.getElementById(active)?.focus({preventScroll: true});
  jobsRenderFrame();
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
  J.busy = "run"; J.message.run = null; J.runError = null; jobsRenderRun();
  try {
    const data = await post("/api/jobs/run", body); J.confirm = null;
    J.runWatch = data?.id || null;
    if (J.runWatch) J.step = "job";
    await jobsPoll();
  } catch (error) {
    if (error.status === 409 && error.body?.needs_confirm && !body.confirm) J.confirm = {kind: "run", body, summary: error.body.summary};
    else { J.confirm = null; J.runError = error; J.message.run = jobsRequestError(error); }
  } finally { J.busy = null; jobsRenderSteps(); if (J.confirm?.kind === "run") jobsOpenConfirm("jobs-run-start"); }
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
shellDefineView("jobs-run", {render: jobsRenderRun});
shellDefineView("jobs-connection", {render: jobsRenderConnection});
shellDefineView("jobs-result", {render: jobsRenderResult});
shellDefineView("jobs-compare", {load: jobsEnsure, render: jobsRenderCompare});
shellDefineView("jobs-list", {load: jobsEnsure, render: jobsRenderList});
shellDefineView("jobs-detail", {render: jobsRenderDetail});
on("servers_changed", async () => {
  if (!S.jobs.initialized) return;
  if (await jobsLoadOptions()) { jobsRenderTry(); jobsRenderRun(); }
  jobsRenderConnection(); jobsRenderResult();
});
on("context_changed", async () => {
  if (!S.jobs.initialized) return;
  jobsReconcile(); await jobsLoadRuns(); jobsRenderSteps(); jobsRenderCompare();
});
