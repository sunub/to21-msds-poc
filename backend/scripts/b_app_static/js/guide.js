"use strict";

// 장 위치는 승인 시안의 번호다. 선택한 실습만 이동 순서에 남긴다.
const guideOrder = ["G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G11", "G12", "G13", "G16", "G17", "G14", "G15"];
const guideScreens = {
  G02: {chapter: 1, n: 2, m: 3, example: "steps"}, G14: {chapter: 4, n: 4, m: 4, example: "defaults"},
  G16: {chapter: 4, n: 2, m: 4, example: "data"}, G17: {chapter: 4, n: 3, m: 4, example: "answers"},
  G01: {intro: true, example: "score"}, G03: {chapter: 1, n: 3, m: 3, example: "steps"},
  G04: {intro: true, example: "ready"}, G06: {intro: true, example: "source"},
  G09: {chapter: 3, n: 4, m: 7, example: "result"},
  G13: {intro: true, example: "data"}, G15: {intro: true, example: "score"},
  G05: {chapter: 2, n: 2, m: 2, example: "ready"}, G07: {chapter: 3, n: 2, m: 7, example: "source"},
  G08: {chapter: 3, n: 3, m: 7, example: "practice"}, G10: {chapter: 3, n: 5, m: 7, example: "ai"},
  G11: {chapter: 3, n: 6, m: 7, example: "result"}, G12: {chapter: 3, n: 7, m: 7, example: "result"}
};
S.guide = {open: false, screen: "G01", bootEligible: false, bootChecked: false,
  returnFocus: null, confirmFocus: null, background: [], epoch: 0, readiness: null, source: null,
  trial: null, returnScreen: null, session: null, target: null, aiChecking: false, returned: false,
  live: null, livePending: null};
const GUIDE_REQUEST_MS = 15000, GUIDE_TRIAL_MS = 600000;

function guideDefault() {return {state: "not_started", screen: null, choices: [], skipped: [], updated_at: null};}
function guideProgress() {return S.journey.progress.guide || guideDefault();}
function guideDismissed() {
  const p = guideProgress(), closed = S.journey.progress.dismissed_at;
  return p.state === "in_progress" && !!closed && (!p.updated_at || p.updated_at <= closed);
}
function guideSupported(screen) {
  if (!screen) return "G01";
  return guideOrder.includes(screen) ? screen : guideOrder.find(id => id > (screen || "G01")) || "G15";
}
function guideButton(id, key, action, primary = false) {
  return h("button", {id, type: "button", class: primary ? "primary" : "text-button",
    onclick: () => {
      emit("onboarding_action", {screen: S.guide.screen, action: id.replace(/^guide-/, "")});
      return Promise.resolve(action()).catch(fail);
    }}, T(key));
}
function guideUnchosen(choices = guideProgress().choices) {
  // 옛 진행 기록에는 선택 화면이 없었다. 그 기록의 빈 선택은 기존 순서를 잇는다.
  if (!choices.length) return [];
  return [!choices.some(c => ["score", "source"].includes(c)) && "p1",
    !choices.includes("retest") && "p2", !choices.some(c => ["retest", "ai"].includes(c)) && "p3"].filter(Boolean);
}
function guideRoute() {
  const excluded = guideUnchosen();
  return guideOrder.filter(screen => !excluded.includes({G07: "p1", G08: "p2", G09: "p2", G10: "p3", G11: "p3"}[screen]));
}
function guideAdjacent(direction = 1) {
  const at = guideOrder.indexOf(S.guide.screen), route = guideRoute();
  return (direction > 0 ? guideOrder.slice(at + 1) : guideOrder.slice(0, at).reverse()).find(screen => route.includes(screen));
}
function guideSetChoice(choice, checked) {
  const prior = guideProgress(), previousExcluded = guideUnchosen(prior.choices);
  const choices = ["score", "source", "retest", "ai"].filter(c => c === choice ? checked : prior.choices.includes(c));
  journeyChange(j => {j.progress.guide = {...prior, state: "in_progress", screen: "G02", choices,
    skipped: [...new Set([...prior.skipped.filter(p => !previousExcluded.includes(p)), ...guideUnchosen(choices)])],
    updated_at: journeyTime()};});
  emit("onboarding_action", {screen: "G02", action: `choose_${choice}`});
  guideRender(); document.getElementById(`guide-choice-${choice}`)?.focus({preventScroll: true});
}
function guideVisible(el) {
  if (!el?.isConnected) return false;
  for (let p = el; p; p = p.parentElement) {
    if (p.hidden || p.getAttribute("inert") !== null || p.getAttribute("aria-hidden") === "true") return false;
    if (p.tagName.toLowerCase() === "details" && !p.open && !p.querySelector("summary")?.contains(el)) return false;
  }
  return true;
}
function guideBackground(lock) {
  if (lock) {
    S.guide.background = [...document.body.children].filter(el => el instanceof Node &&
      !["guide-overlay", "ui-text"].includes(el.id) && el.tagName.toLowerCase() !== "script")
      .map(el => ({el, inert: el.getAttribute("inert"), hidden: el.getAttribute("aria-hidden")}));
    for (const {el} of S.guide.background) {el.setAttribute("inert", ""); el.setAttribute("aria-hidden", "true");}
  } else {
    for (const {el, inert, hidden} of S.guide.background) {
      if (inert === null) el.removeAttribute("inert"); else el.setAttribute("inert", inert);
      if (hidden === null) el.removeAttribute("aria-hidden"); else el.setAttribute("aria-hidden", hidden);
    }
    S.guide.background = [];
  }
  document.body.classList.toggle("guide-open", lock);
}
async function guideOpen({resume = false, replay = false} = {}) {
  await journeyEnsure();
  if (!S.guide.open) {S.guide.returnFocus = document.activeElement; guideBackground(true);}
  S.guide.open = true;
  S.guide.screen = resume ? guideSupported(guideProgress().screen) : "G01";
  S.guide.bootChecked = true;
  if (!S.guide.session || replay) S.guide.session = {source: null, practice: 0, trial: null};
  S.guide.livePending = guideLiveLoad();
  if (replay) {S.guide.target = null; S.guide.readiness = null; S.guide.returnScreen = null; S.guide.defaultsReturn = null;}
  if (replay) {
    // 성공·대기 작업·옛 갈래 진행을 건드리지 않는다. 직렬 PUT은 journey가 맡는다.
    journeyChange(j => {j.progress.dismissed_at = null;
      j.progress.guide = {...guideDefault(), state: "in_progress", screen: "G01", updated_at: journeyTime()};});
    emit("onboarding_replayed", {had_real: !!(S.journey.outcomes.t1.real || S.journey.outcomes.t2.real),
      had_practice: !!S.journey.outcomes.t2.practice});
  }
  if (resume && S.journey.progress.dismissed_at) journeyChange(j => {j.progress.dismissed_at = null;});
  return guideShow(S.guide.screen, {save: false});
}
function guideNext() {
  const from = S.guide.screen;
  if (guideNextDisabled()) return;
  if (from === "G15") return guideClose("completed");
  if (from === "G14") return guideApplyDefaults();
  if (from === "G05") {
    const r = S.guide.readiness;
    if (!r || [r.results, r.key].includes("checking")) return;
    if ([r.results, r.key].includes("unknown")) return guideCheckReadiness();
    if (r.key === "absent") return guideChooseKey();
  }
  if (from === "G07" && S.guide.source?.state !== "success") return guideOpenEvidence();
  if (["G08", "G11"].includes(from) && S.guide.trial?.state !== "success") {
    if (S.guide.trial?.state === "cancelled") return guidePrepareTrial().then(guideRender);
    return guideStartTrial();
  }
  if (from === "G10") return guideHandoff();
  if (from === "G06" && S.guide.readiness?.results === "absent") return guideSkipPractice("p1", "G08");
  return guideShow(guideAdjacent());
}
function guideBack() {
  const screen = guideAdjacent(-1);
  if (screen) return guideShow(screen, {save: false});
}
async function guideClose(state = "in_progress") {
  guideLeave(); S.guide.returnScreen = null; S.guide.defaultsReturn = null;
  S.guide.open = false; S.guide.bootChecked = true;
  document.getElementById("guide-overlay").hidden = true; guideBackground(false);
  journeyChange(j => {
    const prior = guideProgress();
    j.progress.guide = {...prior, state, screen: state === "completed" ? "G15" : prior.screen || "G01",
      updated_at: prior.updated_at || journeyTime()};
    j.progress.dismissed_at = journeyTime();
  });
  if (state === "completed") emit("onboarding_completed", {});
  await go("s01");
  if (!S.guide.open) (guideVisible(S.guide.returnFocus) ? S.guide.returnFocus : document.getElementById("guide-open"))?.focus();
}
function guideConfirmClose() {
  if (!S.guide.open || !document.getElementById("guide-confirm").hidden) return;
  S.guide.confirmFocus = document.activeElement;
  const frame = document.getElementById("guide-frame"); frame.setAttribute("inert", ""); frame.setAttribute("aria-hidden", "true");
  const confirm = document.getElementById("guide-confirm"); confirm.hidden = false;
  coreReplace(confirm, h("div", {class: "guide-veil", "aria-hidden": "true"}),
    h("div", {class: "guide-confirm-box", role: "dialog", "aria-modal": "true", "aria-labelledby": "guide-confirm-title"},
      h("h1", {id: "guide-confirm-title", tabindex: "-1"}, T("guide.close.title")),
      h("p", null, T("guide.close.resume")), h("p", null, T("guide.close.keep")),
      h("p", {class: "muted"}, T("guide.close.running")),
      guideButton("guide-confirm-close", "guide.close.action", () => guideClose(), true),
      guideButton("guide-continue", "guide.close.cancel", guideCancelClose)));
  document.getElementById("guide-confirm-title").focus();
}
function guideCancelClose() {
  document.getElementById("guide-confirm").hidden = true;
  const frame = document.getElementById("guide-frame"); frame.removeAttribute("inert"); frame.removeAttribute("aria-hidden");
  (guideVisible(S.guide.confirmFocus) ? S.guide.confirmFocus : document.getElementById("guide-title"))?.focus();
  guideRecordTrial();
}
function guideFocusRoot() {
  return document.getElementById(document.getElementById("guide-confirm")?.hidden === false ? "guide-confirm" : "guide-frame");
}
document.addEventListener("keydown", event => {
  if (!S.guide.open) return;
  if (event.key === "Escape") {
    event.preventDefault();
    if (document.getElementById("guide-confirm").hidden) guideConfirmClose(); else guideCancelClose();
  } else if (event.key === "Tab") {
    const root = guideFocusRoot();
    const focusable = [...root.querySelectorAll("button,a[href],input,select,textarea,summary,[tabindex]")]
      .filter(el => !el.disabled && el.getAttribute("tabindex") !== "-1" && guideVisible(el));
    const first = focusable[0], last = focusable.at(-1), current = document.activeElement;
    if (!first) {event.preventDefault(); root.querySelector("h1")?.focus();}
    else if (event.shiftKey && (current === first || !focusable.includes(current))) {event.preventDefault(); last.focus();}
    else if (!event.shiftKey && (current === last || !focusable.includes(current))) {event.preventDefault(); first.focus();}
  }
});
document.addEventListener("focusin", event => {
  if (!S.guide.open) return;
  const root = guideFocusRoot();
  if (root && !root.contains(event.target)) root.querySelector("h1")?.focus();
});

function guideChapterRow(meta) {
  if (meta.intro) return null;
  return h("div", null,
    h("div", {id: "guide-chapters", class: "guide-chapters", "aria-label": T("guide.chapter_label")},
      [1, 2, 3, 4, 5].map(k => h("span", {"data-chapter": k, "aria-current": k === meta.chapter ? "step" : null}, T(`guide.chapters.${k}`)))),
    h("div", {id: "guide-progress", class: "guide-progress", role: "img", "aria-label": T("guide.progress_label",
      {chapter: T(`guide.chapters.${meta.chapter}`), n: meta.n, m: meta.m})},
      Array.from({length: meta.m}, (_, i) => {
        const part = meta.chapter === 3 ? [null, "p1", "p2", "p2", "p3", "p3", null][i] : null;
        const skipped = part && (guideUnchosen().includes(part) || (i !== 3 && guideProgress().skipped.includes(part)));
        return h("span", {class: `${i < meta.n ? "filled" : ""}${skipped ? " guide-skipped" : ""}`, "data-skipped": skipped ? part : null},
          skipped ? T("guide.skipped") : null);
      })),
    h("p", {id: "guide-progress-text", class: "guide-progress-text"}, T("guide.progress",
      {chapter: T(`guide.chapters.${meta.chapter}`), n: meta.n, m: meta.m, k: meta.chapter})));
}
function guideExampleText(key, args) {return T(`guide.example.${key}`, args);}
function guideExampleRow(label, value) {return h("div", {class: "guide-mini-row"}, h("span", null, guideExampleText(label)), h("strong", null, value));}
function guideExampleNote(key) {return h("p", {class: "guide-after"}, guideExampleText(key));}
// 저장된 결과가 필요한 칸은 값이 없으면 빈 막대 대신 지금 상태를 글로 말한다.
function guideExampleStatus() {
  const state = S.guide.live?.state || "loading";
  if (state === "loading") return h("p", {role: "status"}, guideExampleText("loading"));
  if (state === "empty") return [h("strong", null, guideExampleText("empty")), h("p", null, guideExampleText("empty_note"))];
  return [h("strong", null, guideExampleText("failed")), h("p", null, guideExampleText("failed_note"))];
}
function guideExampleWaiting(key) {return S.guide.live?.finished ? h("p", null, guideExampleText(key)) : h("p", {role: "status"}, guideExampleText("loading"));}
function guideExampleLine(value) {
  if (!value) return null;
  const line = value.entry.v.lines?.map(id => value.data.lines.find(row => row.id === id)).find(Boolean);
  return line ? h("div", {class: "guide-mini-source"}, h("strong", null, guideExampleText("line_at", {page: line.page, line: line.no})),
    h("p", null, line.text)) : null;
}
function guideExampleValues(value) {
  const {v, only} = value.entry;
  return h("div", {class: "guide-value-pair"},
    h("div", null, h("span", null, guideExampleText("ai_value")), h("div", {class: "guide-value"}, only ? T("common.none") : jobsFocusValue(v.value, v.text))),
    h("div", null, h("span", null, guideExampleText("answer_label")), h("div", {class: "guide-value"}, only ? jobsFocusValue(v.value, v.text) : jobsFocusValue(v.silver?.value, v.silver?.text))));
}
function guideExampleChange(change) {
  return [h("p", null, T("guide.target", {doc: change.doc, section: change.section})), h("p", {class: "technical"}, change.key),
    h("div", {class: "guide-value-pair"},
      h("div", null, h("span", null, guideExampleText("old_value")), h("div", {class: "guide-value"}, change.before), h("p", {class: "muted"}, change.beforeRun)),
      h("div", null, h("span", null, guideExampleText("new_value")), h("div", {class: "guide-value"}, change.after), h("p", {class: "muted"}, change.afterRun)))];
}
function guideExampleScoreBlock(run) {
  const targets = run.targets;
  return [h("p", null, T("score.summary.scope", {model: run.model_label || run.model_tag || scoreMissing(), count: run.docs?.length ?? scoreMissing()})),
    h("div", {class: "score-number"}, fmt1(run.weighted), h("span", null, T("score.summary.denominator"))),
    h("p", {class: "score-basis muted"}, scoreBasisText(run)),
    targets ? [h("p", {class: "score-target-gap"}, T(targets.weighted.met ? "score.summary.headline_met" : "score.summary.headline_below",
      {line: targets.weighted.line, gap: fmt1(targets.weighted.line - targets.weighted.value)})),
      scoreBar(targets.weighted.value, targets.weighted.line),
      h("p", {class: "score-essential"}, T(targets.must.met ? "score.summary.must_all" : "score.summary.must_some",
        {total: targets.must.total, met: targets.must.met_count}))] : null];
}
function guideExampleProblem(run) {
  const top = run.status_text?.top_problem, loss = run.status_text?.loss_basis;
  if (!top) return null;
  return h("div", {class: "guide-mini-sub"}, h("strong", null, T("score.summary.top_problem", {item: scoreItemName(top.name)})),
    h("p", null, T("score.summary.loss_meaning", {total_loss: fmt1(loss?.loss_total), score: fmt1(run.weighted),
      item_loss: num(top.loss) ? top.loss.toFixed(2) : scoreMissing()})));
}
function guideExampleKeyLabel() {return S.shell.keys.find(key => key.id === S.ctx.key)?.label || S.ctx.key || T("common.none");}
function guideExampleSet() {return S.shell.sets.find(set => set.id === S.ctx.set);}
function guideExampleAIState() {
  const state = S.guide.aiState;
  return state ? T(`guide.ready.states.${state}`) : guideExampleText("not_checked");
}
function guideExampleTunnel() {
  const open = serversData()?.rngd?.tunnel?.open;
  return guideExampleText(open == null ? "not_checked" : open ? "tunnel_open" : "tunnel_closed");
}
function guideExampleSteps() {
  const E = guideExampleText, {run, value, change} = S.guide.live || {};
  const top = run?.status_text?.top_problem;
  return h("div", {class: "guide-mini-steps"},
    h("div", null, h("h2", null, E("step1")), h("div", null,
      run ? [h("div", {class: "score-number"}, fmt1(run.weighted), h("span", null, T("score.summary.denominator"))),
        h("strong", null, E("biggest")), h("p", null, top ? scoreItemName(top.name) : T("common.none"))] : guideExampleStatus())),
    h("div", null, h("h2", null, E("step2")), h("div", null,
      value ? [h("span", null, E("ai_value")), h("div", {class: "guide-value"}, value.entry.only ? T("common.none") : jobsFocusValue(value.entry.v.value, value.entry.v.text)), guideExampleLine(value)]
        : run ? guideExampleWaiting("no_value") : guideExampleStatus())),
    h("div", null, h("h2", null, E("step3")), h("div", null,
      change ? [h("span", null, E("old_value")), h("div", {class: "guide-value"}, change.before), h("span", null, E("new_value")), h("div", {class: "guide-value"}, change.after)]
        : run ? guideExampleWaiting("no_change") : guideExampleStatus())));
}
function guideExampleBody(kind) {
  const E = guideExampleText, live = S.guide.live || {}, {run, value, change, prompt, sample} = live, set = guideExampleSet();
  if (kind === "score") return run ? [h("div", {class: "guide-mini-content"}, guideExampleScoreBlock(run)), guideExampleProblem(run)]
    : h("div", {class: "guide-mini-content"}, guideExampleStatus());
  if (kind === "ready") return h("div", {class: "guide-mini-content"}, h("h2", null, E("ready_title")),
    guideExampleRow("saved", run ? scoreLabel(run) : live.state === "loading" ? E("loading") : E("empty")),
    guideExampleRow("key", guideExampleKeyLabel()), guideExampleRow("ai", guideExampleAIState()), guideExampleNote("offline"));
  if (kind === "source") return h("div", {class: "guide-mini-content"}, h("h2", null, E("source_title")),
    value ? [h("p", null, T("guide.target", {doc: value.doc, section: value.section})), guideExampleValues(value), guideExampleLine(value), guideExampleNote("read_line")]
      : run ? guideExampleWaiting("no_value") : guideExampleStatus());
  if (kind === "result") return h("div", {class: "guide-mini-content"}, h("h2", null, E("result_title")),
    change ? [guideExampleChange(change), guideExampleNote("result_note")] : run ? guideExampleWaiting("no_change") : guideExampleStatus());
  if (kind === "defaults") return h("div", {class: "guide-mini-content"}, h("h2", null, E("defaults_title")),
    guideExampleRow("set", set?.label || S.ctx.set || T("common.none")), guideExampleRow("key", guideExampleKeyLabel()),
    run ? h("div", {class: "score-number"}, fmt1(run.weighted), h("span", null, T("score.summary.denominator"))) : guideExampleStatus(),
    h("p", null, E("trust")));
  if (kind === "practice") return h("div", {class: "guide-mini-content"}, h("h2", null, E("practice_title")),
    value ? [guideExampleRow("document", value.doc), guideExampleRow("part", T("score.calls.section", {section: value.section})),
      h("div", {class: "guide-mini-source"}, h("strong", null, E("instruction_title")), prompt ? h("p", null, prompt) : guideExampleWaiting("no_prompt"))]
      : run ? guideExampleWaiting("no_value") : guideExampleStatus(), guideExampleNote("practice_offline"));
  if (kind === "ai") return h("div", {class: "guide-mini-content"}, h("h2", null, E("ai_title")),
    guideExampleRow("tunnel", guideExampleTunnel()), guideExampleRow("model", run?.model_label || run?.model_tag || E("not_checked")),
    guideExampleRow("model_time", E("model_duration")), guideExampleNote("guide_return"));
  if (kind === "data") {
    const docs = set?.docs || [], locked = docs.filter(doc => doc.locked).length;
    return h("div", {class: "guide-mini-content"}, h("h2", null, E("data_title")),
      guideExampleRow("set", set?.label || S.ctx.set || T("common.none")), set?.path ? h("p", {class: "technical"}, set.path) : null,
      h("p", null, E("data_counts", {open: docs.length - locked, locked})),
      sample ? h("div", {class: "guide-mini-source"}, h("strong", null, E("data_doc", {doc: sample.doc, pages: sample.pages})),
        h("p", {class: "muted"}, E("data_lines")),
        sample.lines.map(line => h("p", {class: "technical"}, `L${String(line.no).padStart(3, "0")} ${line.text}`)))
        : guideExampleWaiting("no_sample"));
  }
  if (kind === "answers") return h("div", {class: "guide-mini-content"}, h("h2", null, E("answers_title")),
    S.shell.keys.filter(key => key.usable).map(key => h("div", {class: "guide-mini-key", "data-current": String(key.id === S.ctx.key)},
      h("strong", null, key.label || key.id), h("p", {class: "technical"}, key.path),
      h("p", null, E("answers_count", {docs: key.counts?.docs ?? key.docs?.length ?? 0, locked: key.counts?.eval_locked ?? 0})))),
    value ? [h("p", null, E("answers_compare")), guideExampleValues(value)] : null);
  return null;
}
function guideExample(kind) {
  const E = guideExampleText, set = guideExampleSet();
  const content = kind === "steps" ? guideExampleSteps() : h("div", {class: "guide-mini-screen"},
    h("div", {class: "guide-mini-head"}, E("brand")),
    h("div", {class: "guide-mini-context"}, `${T("context.documents.label")}: ${set?.label || S.ctx.set || T("common.none")} · ${T("context.answer.label")}: ${guideExampleKeyLabel()}`),
    guideExampleBody(kind));
  return h("aside", {id: "guide-example", class: "guide-example", role: "img", "aria-label": E("label")},
    h("div", {class: "app-name", "aria-hidden": "true"}, E("brand")),
    h("div", {class: "guide-demo-center", "aria-hidden": "true"}, h("figure", null,
      h("figcaption", null, h("span", {class: "guide-example-badge"}, E("badge")), h("p", {class: "guide-demo-caption"}, E("caption"))), content)));
}
function guideExampleRefresh() {
  const el = document.getElementById("guide-example");
  if (S.guide.open && el) el.replaceWith(guideExample(guideScreens[S.guide.screen].example));
}
// 왼쪽 칸의 자료는 최근 결과·원문 대조와 같은 API에서 읽는다. 진행·성공 기록과 파일에는 남기지 않는다.
async function guideLiveSample(live, valid) {
  const doc = guideExampleSet()?.docs?.find(d => !d.locked && d.group !== "eval" && d.line_numbers !== false);
  if (!doc) return;
  try {
    const data = await api(ctxUrl(`/api/doc?${new URLSearchParams({doc: doc.doc_id, set: S.ctx.set})}`));
    if (valid()) live.sample = {doc: doc.doc_id, pages: data.pages?.length ?? doc.pages, lines: (data.lines || []).slice(0, 4)};
  } catch (_) {/* 없으면 글로 말한다 */}
}
function guideLiveShown(v) {return jobsFocusValue(v.value, v.text);}
async function guideLiveChange(live, pool, valid) {
  const {run, value} = live;
  const prior = pool.filter(other => other.name !== run.name && (other.docs || []).includes(value.doc)).at(-1);
  if (!prior) return;
  const data = await api(ctxUrl(`/api/doc?${new URLSearchParams({run: prior.name, doc: value.doc})}`));
  if (!valid()) return;
  const old = new Map((data.values || []).map(v => [v.key ?? v.path, v]));
  const changed = v => old.has(v.key ?? v.path) && guideLiveShown(old.get(v.key ?? v.path)) !== guideLiveShown(v);
  const rows = (value.data.values || []).filter(changed);
  // 채점하는 표의 칸을 먼저 고른다. 서술 문장과 남은 칸은 줄이 밀려 다른 내용끼리 맞붙을 수 있다.
  const clear = rows.filter(v => v.items?.length && !["narratives", "extras"].includes(v.table));
  const row = clear.find(v => v.section === value.section) || clear[0] || rows.find(v => v.items?.length) || rows[0];
  // 실행 이름 전체는 길어 회차만 보인다. 전체 이름은 최근 결과에서 볼 수 있다.
  const short = r => r.label?.parts?.at(-1) || scoreLabel(r);
  if (row) live.change = {doc: value.doc, section: row.section, key: row.key ?? row.path, before: guideLiveShown(old.get(row.key ?? row.path)), after: guideLiveShown(row),
    beforeRun: short(prior), afterRun: short(run)};
}
async function guideLivePrompt(live, valid) {
  const {run, value} = live;
  if (!run.model_tag) return;
  const data = await jobsReadPrompt(run.model_tag, value.section);
  if (valid() && data?.text) live.prompt = data.text.split("\n").filter(line => line.trim()).slice(0, 3).join(" ");
}
function guideLiveLoad() {
  const g = S.guide, context = scoreContext(), live = g.live = {state: "loading", context, finished: false};
  const valid = () => g.open && g.live === live && context === scoreContext();
  const update = () => {if (valid()) guideExampleRefresh();};
  const work = (async () => {
    const part = async task => {try {await task();} catch (_) {/* 이 칸만 글로 말한다 */} update();};
    await Promise.all([part(() => guideLiveSample(live, valid)), (async () => {
      let pool = [];
      try {
        const list = await api(ctxUrl("/api/runs"));
        if (!valid()) return;
        pool = (list.runs || []).filter(run => scoreEligible(run) && !["silver", "eval"].includes(run.run_kind));
        const chosen = pool.find(run => run.name === list.current) || pool.at(-1);
        const run = chosen ? await api(ctxUrl(scoreRunPath(chosen.name))) : null;
        if (!valid()) return;
        live.run = run?.set?.id === S.ctx.set && num(run.weighted) ? run : null;
        live.state = live.run ? "ready" : "empty";
      } catch (_) {if (valid()) live.state = "error";}
      update();
      if (!live.run || !valid()) return;
      await part(async () => {live.value = await guideFindValue(live.run, new Set(), valid) || null;});
      if (live.value && valid()) await Promise.all([part(() => guideLiveChange(live, pool, valid)), part(() => guideLivePrompt(live, valid))]);
    })()]);
    if (valid()) {live.finished = true; update();}
  })();
  g.livePending = work;
  return work;
}
function guideRender() {
  if (!S.guide.open) return;
  const keepConfirm = document.getElementById("guide-confirm")?.hidden === false;
  const confirmFocus = S.guide.confirmFocus;
  const overlay = document.getElementById("guide-overlay"), screen = S.guide.screen, meta = guideScreens[screen];
  overlay.hidden = false; overlay.setAttribute("data-screen", screen);
  overlay.setAttribute("data-variant", guideVariant());
  coreReplace(overlay, h("div", {id: "guide-frame", class: `guide-frame${meta.intro ? " guide-intro" : ""}`}, guideExample(meta.example),
    h("div", {class: `guide-column${screen === "G10" ? " guide-sheet-column" : ""}`}, h("div", {class: "guide-inner"},
      h("header", null, h("nav", {class: "guide-nav", "aria-label": T("guide.navigation")},
        screen !== "G01" ? guideButton("guide-back", "guide.back", guideBack) : null,
        ["G07", "G08", "G11"].includes(screen) && S.guide.trial?.state !== "running" ?
          guideButton("guide-skip-practice", "guide.practice_skip", () => guideSkipPractice()) : null,
        screen !== "G01" ? guideButton("guide-close", "guide.close.action", () => guideClose()) : null), guideChapterRow(meta)),
      h("div", {class: "guide-step-body"}, h("h1", {id: "guide-title", tabindex: "-1"}, guideTitle()),
        h("div", {id: "guide-notices", "aria-live": "polite"}),
        screen === "G03" ? [h("p", {class: "guide-lead"}, T("guide.screens.G03.lead")), h("h2", null, T("guide.screens.G03.terms")),
          h("ul", {class: "guide-terms"}, ["draft", "part", "limit"].map(k => h("li", null, T(`guide.screens.G03.${k}`))))] : null,
        screen === "G09" ? [h("p", {class: "guide-lead"}, T("guide.screens.G09.lead")), h("p", null, T("guide.screens.G09.example")),
          h("p", {class: "muted"}, T("guide.screens.G09.no_success"))] : null,
        guidePracticeContent(), screen === "G15" ? h("div", {id: "guide-records"}) : null),
      h("footer", {class: "guide-action"}, screen === "G01" ? guideButton("guide-skip", "guide.skip", () => guideClose("skipped")) : null,
        screen === "G14" ? guideButton("guide-keep-context", "guide.defaults.keep", () => guideShow("G15")) : null,
        screen === "G10" ? [guideButton("guide-without-ai", "guide.ai.without", () => guideSkipPractice("p3", "G13")),
          h("p", {class: "muted"}, T("guide.ai.skip_note"))] : null,
        guideButton("guide-next", guideNextKey(), guideNext, true),
        ["G02", "G14"].includes(screen) && guideNextDisabled() ? h("p", {class: "guide-disabled-note"}, T(screen === "G02" ? "guide.choices.disabled" : "guide.defaults.disabled")) : null,
        screen === "G10" ? [h("p", {class: "guide-after"}, T("guide.ai.cost_action")), h("p", {class: "muted"}, T("guide.ai.cost")), h("p", {class: "muted"}, T("guide.ai.rented_time"))] : null)))),
    h("div", {id: "guide-confirm", class: "guide-confirm", hidden: true}));
  document.getElementById("guide-next").disabled = guideNextDisabled();
  guideRefreshRecords(); document.getElementById("guide-title").focus();
  if (keepConfirm) {guideConfirmClose(); S.guide.confirmFocus = confirmFocus;}
}
function guideRefreshRecords() {
  const u = S.journeyUI;
  const notices = document.getElementById("guide-notices");
  if (notices) coreReplace(notices, u.storageNotice ? friendlyError(u.storageNotice) : null,
    u.problems ? h("div", {role: "status"}, T("journey.partial_record.title"), u.problems.map(t => h("p", null, t))) : null);
  for (const id of ["guide-records", "help-guide-records"]) {
    const target = document.getElementById(id); if (target) journeyRenderRecords(target, id);
  }
  const resume = document.getElementById("guide-resume");
  resume.hidden = !u.known || S.guide.open || !guideDismissed();
  if (!resume.hidden && !resume.querySelector("button")) coreReplace(resume, h("p", null, T("guide.resume")),
    guideButton("guide-resume-button", "guide.resume_action", () => guideOpen({resume: true})));
}
function guideSync() {
  guideRefreshRecords();
  if (!S.guide.bootEligible || S.guide.bootChecked || (!S.journeyUI.known && !S.journeyUI.storageNotice)) return;
  if (S.journeyUI.known && !S.shell.contextLoaded) return;
  S.guide.bootChecked = true;
  if (!S.journeyUI.known || S.journeyUI.problems || S.shell.navigation > 1 || S.shell.route !== "s01") return;
  const p = guideProgress();
  if (p.state === "in_progress" && !guideDismissed()) guideOpen({resume: true}).catch(fail);
  else if (!S.guide.bootHash && p.state === "not_started" && journeyPristine()) guideOpen().catch(fail);
}
// 안내 뒤의 기본 화면 주소는 새로고침에도 남는다. 다른 화면을 지정한 주소는 우선한다.
on("shell_started", ({hash}) => {S.guide.bootHash = hash; S.guide.bootEligible = !hash || hash === "#s01";});
on("journey_changed", guideSync);
on("screen_shown", guideSync);
on("guide_open", () => {guideOpen({replay: true}).catch(fail);});

// 기능 호출은 기존 화면과 공유하고, 이 층은 준비·표시·취소 수명만 관리한다.
async function guideRequest(work) {
  let timer;
  try { return await Promise.race([work, new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(T("guide.recovery.timeout"))), GUIDE_REQUEST_MS);
  })]); } finally { clearTimeout(timer); }
}
function guideCurrent(epoch, screen = S.guide.screen) { return S.guide.open && S.guide.epoch === epoch && S.guide.screen === screen; }
function guideLeave() {
  S.guide.epoch++;
  if (S.guide.trial) {S.guide.trial.active = false; clearTimeout(S.guide.trial.timer); clearTimeout(S.guide.trial.deadline);}
}
async function guideShow(screen, {save = true} = {}) {
  guideLeave(); const g = S.guide, epoch = g.epoch;
  g.screen = guideSupported(screen); g.trial = null; g.aiChecking = false;
  if (g.screen !== "G14") g.defaultsReturn = null;
  if (g.screen === "G07") g.source = {state: "loading", started: Date.now(), skipped: new Set(), emitted: new Set()};
  if (g.screen === "G14") g.defaults = {loading: true, choices: [], selected: null};
  guideRender();
  if (save) journeyChange(j => {j.progress.guide = {...guideProgress(), state: "in_progress", screen: g.screen, updated_at: journeyTime()};});
  emit("onboarding_step_viewed", {screen: g.screen});
  if (g.screen === "G05") await guideCheckReadiness();
  if (guideCurrent(epoch, "G14")) await guideLoadDefaults();
  if (guideCurrent(epoch, "G07")) await guideLoadValue();
  if (guideCurrent(epoch) && ["G08", "G10", "G11"].includes(g.screen)) {
    if (g.screen !== "G08") {
      await guideCheckAI();
      if (!guideCurrent(epoch)) return;
      const resolved = guideAIReady() ? "G11" : "G10";
      if (g.screen !== resolved) {g.screen = resolved; emit("onboarding_step_viewed", {screen: resolved});}
      if (save) journeyChange(j => {j.progress.guide = {...guideProgress(), screen: g.screen, updated_at: journeyTime()};});
    }
    if (guideCurrent(epoch) && ["G08", "G11"].includes(g.screen)) await guidePrepareTrial();
  }
  if (guideCurrent(epoch)) guideRender();
}
async function guideCheckReadiness() {
  const g = S.guide, epoch = g.epoch, context = scoreContext();
  const r = g.readiness = {results: "checking", key: "checking", ai: "checking", run: null, error: null};
  guideRender();
  const valid = () => guideCurrent(epoch, "G05") && context === scoreContext() && g.readiness === r;
  const update = () => {if (valid()) guideRender();};
  await Promise.all([
    (async () => {
      try {
        const list = await guideRequest(api(ctxUrl("/api/runs")));
        const pool = (list.runs || []).filter(run => scoreEligible(run) && !["silver", "eval"].includes(run.run_kind));
        const current = pool.find(run => run.name === list.current) || pool.at(-1);
        const run = current ? await guideRequest(api(ctxUrl(scoreRunPath(current.name)))) : null;
        if (!valid()) return;
        r.run = run?.set?.id === S.ctx.set ? run : null; r.results = r.run ? "present" : "absent";
      } catch (error) {if (valid()) {r.results = "unknown"; r.error = error;}}
      update();
    })(),
    (async () => {
      try {
        const data = await guideRequest(api("/api/keys"));
        if (!valid()) return;
        r.keyInfo = (data.keys || []).find(key => key.id === S.ctx.key && key.usable);
        r.key = r.keyInfo ? "present" : "absent";
      } catch (error) {if (valid()) {r.key = "unknown"; r.error = error;}}
      update();
    })(),
    (async () => {
      await guideCheckAI(); if (!valid()) return;
      r.ai = g.aiState; update();
    })()
  ]);
}
function guideAIReady() {return S.guide.aiState === "present";}
async function guideCheckAI() {
  const g = S.guide, epoch = g.epoch; g.aiChecking = true; g.aiState = "checking"; guideRender();
  try {
    await guideRequest(Promise.all([shellPollServers(), jobsLoadOptions()]));
    if (!guideCurrent(epoch)) return;
    const model = (S.jobs.opts?.models || []).find(m => jobsReady(m.tag) && serversReady(serversModel(m.tag)));
    g.model = model?.tag || S.jobs.t.model;
    g.aiState = S.shell.serverError || S.jobs.optionsError ? "unknown" : model ? "present"
      : shellModelStates().every(state => state === "state_off") ? "absent" : "unknown";
  } catch (_) {if (guideCurrent(epoch)) g.aiState = "unknown";}
  finally {if (guideCurrent(epoch)) {g.aiChecking = false; guideRender();}}
}
async function guideRecheckAI() {
  const epoch = S.guide.epoch; await guideCheckAI();
  if (guideCurrent(epoch) && guideAIReady()) return guideShow("G11");
}
async function guideFindValue(run, skipped, valid) {
  const top = run?.status_text?.top_problem;
  const docs = top?.section ? scoreProblemDocs(top).filter(doc => !sourceLock(doc) && (!run.docs || run.docs.includes(doc))) : [];
  for (const doc of docs) {
    const data = await guideRequest(api(ctxUrl(`/api/doc?${new URLSearchParams({run: run.name, doc})}`)));
    if (!valid()) return null;
    const scope = {run: run.name, doc, section: top.section, item: top.name};
    const entries = sourceProblems(data, scope).filter(entry => !skipped.has(`${doc}:${entry.v.path}`));
    const entry = sourceChooseProblem(entries, "wrong", data) || sourceChooseProblem(entries, "missing", data);
    if (entry) return {...scope, data, entry};
  }
  return null;
}
async function guideLoadValue() {
  const g = S.guide, epoch = g.epoch, context = scoreContext(), state = g.source;
  state.state = "loading"; state.error = null; guideRender();
  try {
    // 준비 조회를 거치지 않은 새로고침에서도 API로 대상 실행을 다시 찾는다.
    let run = g.readiness?.run;
    if (!run) {
      const data = await guideRequest(api(ctxUrl("/api/runs")));
      const pool = (data.runs || []).filter(r => scoreEligible(r) && !["silver", "eval"].includes(r.run_kind));
      const chosen = pool.find(r => r.name === data.current) || pool.at(-1);
      run = chosen ? await guideRequest(api(ctxUrl(scoreRunPath(chosen.name)))) : null;
    }
    const valid = () => guideCurrent(epoch, "G07") && context === scoreContext();
    const found = await guideFindValue(run, state.skipped, valid);
    if (!valid()) return;
    if (found) {
      const {data, entry, ...scope} = found;
      Object.assign(state, scope, {data, entry, state: "waiting", line: Object.fromEntries(data.lines.map(line => [line.id, line])),
        selectedLines: new Set(), page: null});
      g.target = {...scope, model: run.model_tag}; guideRender(); return;
    }
    if (guideCurrent(epoch)) {state.state = "empty"; guidePracticeResult(state, "p1", "real", "failed"); guideRender();}
  } catch (error) {if (guideCurrent(epoch)) {state.state = "error"; state.error = error; guidePracticeResult(state, "p1", "real", "failed"); guideRender();}}
}
async function guideOpenEvidence() {
  const g = S.guide, state = g.source;
  if (!state || state.state === "loading") return;
  if (state.state === "error") return guideLoadValue();
  if (state.state === "estimated" || state.state === "empty") {
    if (state.entry) state.skipped.add(`${state.doc}:${state.entry.v.path}`);
    return guideLoadValue();
  }
  const entry = state.entry;
  if (!entry || entry.only || !sourceHasEvidence(entry.v, state.data) || entry.kind !== "wrong" || entry.v.silver?.same !== false) {
    state.state = "estimated"; guidePracticeResult(state, "p1", "real", "failed"); guideRender(); return;
  }
  state.selectedLines = new Set(entry.v.lines.filter(id => state.line[id]));
  state.page = entry.v.lines.map(id => state.line[id]).find(line => line && state.data.pages.includes(line.page))?.page;
  state.state = "shown"; guideRender();
  emit("problem_opened", {...g.target, origin: "guide"});
  if (sourceEvidence(entry.v, state, document.getElementById("guide-source-lines"), guideVisible(document.getElementById("guide-source-lines")))) {
    state.state = "success"; g.session.source = journeyTime(); guidePracticeResult(state, "p1", "real", "success"); guideRender();
  }
}
async function guidePrepareTrial() {
  const g = S.guide, epoch = g.epoch;
  try {
    await guideRequest(jobsLoadOptions()); if (!guideCurrent(epoch)) return;
    if (S.jobs.optionsError) throw S.jobs.optionsError;
    const docs = jobsDocs().filter(d => jobsAllowed(d, "try") && d.group !== "eval" && !d.locked && !sourceLock(d.doc_id));
    const doc = docs.find(d => d.doc_id === g.target?.doc) || docs[0];
    const section = g.target?.doc === doc?.doc_id ? g.target.section : 1;
    const model = g.screen === "G08" ? jobsDefaultModel(g.target?.doc === doc?.doc_id ? g.target.model : g.readiness?.run?.model_tag)
      : g.model || S.jobs.t.model;
    g.trial = {active: true, state: doc && model && S.ctx.key ? "waiting" : "unavailable", doc: doc?.doc_id, section, model,
      base: g.target?.doc === doc?.doc_id ? g.target.run : null, dry: g.screen === "G08", epoch};
    // 새로고침은 저장된 작업을 읽기만 한다. 전송은 항상 단추에서 시작한다.
    const pending = S.journey.pending;
    if (pending?.job && pending.mode === (g.trial.dry ? "practice" : "real")) {
      const data = await guideRequest(api("/api/jobs")); if (!guideCurrent(epoch)) return;
      const job = (data.jobs || []).find(job => job.id === pending.job && job.target?.set === S.ctx.set &&
        job.target?.kind === "try" && !job.target.all && job.target.sections?.length === 1 && docs.some(d => d.doc_id === job.target.doc));
      if (job) {
        Object.assign(g.trial, {id: job.id, doc: job.target.doc, section: job.target.sections[0], model: job.target.model,
          base: job.target.base_run, started: Date.now(), state: "running"});
        S.jobs.observed.add(job.id); guideTrialDeadline(g.trial); await guidePollTrial();
      }
    }
  } catch (error) {
    if (guideCurrent(epoch)) g.trial = {active: true, state: "unavailable", error, epoch};
  }
}
function guideTrialCurrent(t) {return t && t === S.guide.trial && t.active && guideCurrent(t.epoch) && ["G08", "G11"].includes(S.guide.screen);}
function guideTrialDeadline(t) {
  clearTimeout(t.deadline);
  t.deadline = setTimeout(() => {
    if (!guideTrialCurrent(t)) return;
    t.request = (t.request || 0) + 1; t.polling = null; clearTimeout(t.timer);
    t.expired = true; t.state = "recovery"; t.error = new Error(T("guide.recovery.timeout")); guideUpdatePractice();
    guidePracticeResult(t, t.dry ? "p2" : "p3", t.dry ? "practice" : "real", "timeout");
  }, GUIDE_TRIAL_MS);
}
async function guideStartTrial() {
  const g = S.guide, t = g.trial;
  if (!t || !guideTrialCurrent(t) || ["running", "sending"].includes(t.state)) return;
  if (t.state === "unavailable") {await guidePrepareTrial(); guideRender(); return;}
  if (t.state === "recovery" && t.id) return guidePollTrial();
  if (!t.dry && !guideAIReady()) return guideShow("G10");
  const doc = jobsDocs().find(d => d.doc_id === t.doc);
  if (!jobsAllowed(doc, "try") || doc.group === "eval" || doc.locked || sourceLock(t.doc)) return;
  t.state = "sending"; t.started = Date.now(); t.error = null; t.epoch = g.epoch;
  t.id = null; t.failureKind = null; t.expired = false; t.response = null; t.result = null; t.event = null;
  t.reported = null;
  guideTrialDeadline(t); guideRender();
  const body = jobsTryBody({doc: t.doc, model: t.model, secs: new Set([t.section]), all: false, edit: false, base: t.base, dry: t.dry});
  try {
    const data = await guideRequest(jobsSubmitTry(body, {accept: () => guideTrialCurrent(t) && t.state === "sending"}));
    if (!data || !guideTrialCurrent(t)) return;
    t.id = data.id; t.state = "running"; guideUpdatePractice(); await guidePollTrial();
  } catch (error) {
    if (guideTrialCurrent(t)) {t.state = "recovery"; t.error = error; clearTimeout(t.deadline);
      guidePracticeResult(t, t.dry ? "p2" : "p3", t.dry ? "practice" : "real", "unconfirmed"); guideUpdatePractice();}
  }
}
async function guidePollTrial() {
  const t = S.guide.trial;
  if (!guideTrialCurrent(t) || !t.id || ["success", "cancelled", "failed"].includes(t.state)) return;
  if (t.polling) return t.polling;
  clearTimeout(t.timer);
  const request = t.request = (t.request || 0) + 1;
  const valid = () => guideTrialCurrent(t) && request === t.request && !S.jobs.terminal.has(t.id);
  const work = (async () => {
    try {
      const data = await guideRequest(api("/api/jobs")); if (!valid()) return;
      const job = (data.jobs || []).find(j => j.id === t.id); t.job = job; t.error = null;
      if (!job) {t.state = "recovery"; return;}
      if (["failed", "stopped"].includes(job.status) || (job.status === "done" && job.returncode !== 0)) {
        t.state = "failed"; t.failureKind = "job"; return;
      }
      if (job.status !== "done") {
        if (t.expired || Date.now() - t.started >= GUIDE_TRIAL_MS) {t.state = "recovery"; t.error = new Error(T("guide.recovery.timeout"));}
        else t.state = "running";
        return;
      }
      const response = await guideRequest(jobsReadResult(t.id)); if (!valid()) return;
      t.response = response; t.result = response.status === 200 ? response.data : null;
      if (response.status !== 200 || !t.result) {t.state = "recovery"; return;}
      if (t.dry && !t.prompt) {
        const prompt = await guideRequest(jobsReadPrompt(t.model, t.section)); if (!valid()) return;
        t.prompt = prompt.text;
      }
      const event = jobsResultEvent(job, t.result, response.status);
      const sameTarget = job.target?.doc === t.doc && job.target?.model === t.model && job.target?.set === S.ctx.set &&
        job.target?.sections?.length === 1 && String(job.target.sections[0]) === String(t.section);
      t.state = sameTarget && event && event.mode === (t.dry ? "practice" : "real") && (t.dry || event.section_ok) ? "shown" : "failed";
      t.event = t.state === "shown" ? event : null;
    } catch (error) {if (valid()) {t.state = "recovery"; t.error = error;}}
    finally {
      if (valid()) {
        guideUpdatePractice(); guideRecordTrial();
        if (["failed", "recovery"].includes(t.state)) guidePracticeResult(t, t.dry ? "p2" : "p3",
          t.dry ? "practice" : "real", t.state === "failed" ? "failed" : t.expired ? "timeout" : "unconfirmed");
        if (t.state === "running") t.timer = setTimeout(() => {if (t.state === "running") guidePollTrial().catch(fail);}, 2000);
        else clearTimeout(t.deadline);
      }
    }
  })();
  t.polling = work;
  try {await work;} finally {if (t.polling === work) t.polling = null;}
}
function guideRecordTrial() {
  const g = S.guide, t = g.trial, summary = document.getElementById("guide-result-summary");
  if (!guideTrialCurrent(t) || t.state !== "shown" || !t.event || !guideVisible(summary)) return;
  t.state = "success"; S.jobs.emitted.add(t.id);
  if (t.dry) g.session.practice++; else g.session.trial = journeyTime();
  emit("try_result_viewed", t.event); guidePracticeResult(t, t.dry ? "p2" : "p3", t.dry ? "practice" : "real", "success"); guideUpdatePractice();
}
function guidePracticeResult(attempt, scenario, source, outcome) {
  if (attempt?.reported === outcome) return;
  if (attempt) attempt.reported = outcome;
  const elapsed = Date.now() - (attempt?.started ?? Date.now());
  emit("practice_result", {scenario, source, outcome, latency_ms: Number.isFinite(elapsed) ? Math.max(0, Math.round(elapsed)) : 0});
}
function guideCancelPractice() {
  const t = S.guide.trial; if (!t?.dry) return;
  t.active = false; clearTimeout(t.timer); clearTimeout(t.deadline); t.state = "cancelled";
  guidePracticeResult(t, "p2", "practice", "cancelled");
  if (t.id) {S.jobs.terminal.add(t.id); emit("attempt_cancelled", {job: t.id});}
  else if (S.journey.pending?.mode === "practice") journeyChange(j => {j.pending = null;});
  guideRender();
}
function guideSkipPractice(part, next) {
  part ||= {G07: "p1", G08: "p2", G11: "p3"}[S.guide.screen];
  next ||= guideAdjacent();
  if (!guideRoute().includes(next)) next = guideOrder.slice(guideOrder.indexOf(next) + 1).find(screen => guideRoute().includes(screen));
  journeyChange(j => {j.progress.guide = {...guideProgress(), skipped: [...new Set([...guideProgress().skipped, part])]};});
  guidePracticeResult(null, part, "skipped", "skipped");
  return guideShow(next);
}
async function guideHandoff() {
  const g = S.guide;
  g.returnScreen = g.screen; guideLeave();
  await journeyChange(j => {j.progress.guide = {...guideProgress(), state: "in_progress", screen: g.screen, updated_at: journeyTime()};});
  g.open = false; document.getElementById("guide-overlay").hidden = true; guideBackground(false);
  await go("s06", {model: g.model || S.jobs.t.model});
}
async function guideReturn() {
  if (!S.guide.returnScreen) return;
  const screen = S.guide.returnScreen; S.guide.returnScreen = null; S.guide.returned = true;
  await guideOpen({resume: true});
  if (S.guide.screen !== screen && screen === "G05") await guideShow(screen, {save: false});
}
async function guideChooseKey() {
  S.guide.defaultsReturn = "G05";
  return guideShow("G14");
}
on("guide_return", () => {guideReturn().catch(fail);});
on("attempt_cancelled", ({job}) => {
  const t = S.guide.trial; if (!t || t.id !== job) return;
  t.active = false; t.state = "cancelled"; clearTimeout(t.timer); clearTimeout(t.deadline); S.jobs.terminal.add(job);
  if (S.guide.open) guideUpdatePractice();
});
on("context_changed", () => {
  S.guide.target = null; S.guide.readiness = null;
  if (S.guide.open) guideLiveLoad();
  if (S.guide.open && !S.guide.applyingDefaults) guideShow("G05").catch(fail);
});

function guideVariant() {
  const g = S.guide, screen = g.screen, state = g.trial?.state;
  if (screen === "G05") {
    if ([g.readiness?.results, g.readiness?.key].includes("unknown")) return "G05-failed";
    if (g.readiness?.results === "absent") return "G05-empty";
  }
  if (screen === "G07") {
    if (g.source?.state === "success") return "G07-success";
    if (g.source?.state === "estimated") return "G07-estimated";
  }
  if (screen === "G08" && state === "success") return "G08-done";
  if (screen === "G10" && g.returned) return "G10-returned";
  if (screen === "G11") {
    if (["sending", "running"].includes(state)) return "G11-running";
    if (state === "success") return "G11-result";
    if (state === "failed") return "G11-failed";
  }
  if (screen === "G12" && !g.session?.trial) return g.session?.source ? "G12-source-only" : "G12-no-success";
  return screen;
}
function guideTitle() {
  const variant = guideVariant(), screen = S.guide.screen;
  if (screen === "G11" && S.guide.trial?.failureKind === "job") return T("guide.recovery.fact");
  const keys = {"G05-empty": "ready.empty", "G05-failed": "ready.failed", "G07-success": "source.success",
    "G07-estimated": "source.estimated", "G08-done": "practice.done", "G11-running": "trial.running",
    "G11-result": "trial.done", "G11-failed": "trial.failed", "G12-source-only": "records.not_yet", "G12-no-success": "records.not_yet"};
  return T(keys[variant] ? `guide.${keys[variant]}` : `guide.screens.${screen}.title`);
}
function guideNextKey() {
  const g = S.guide, screen = g.screen, state = g.trial?.state;
  if (screen === "G05") {
    if ([g.readiness?.results, g.readiness?.key].includes("unknown")) return "guide.ready.retry";
    if (g.readiness?.key === "absent") return "guide.ready.choose_key";
    if (g.readiness?.results === "absent") return "guide.ready.continue_practice";
  }
  if (screen === "G07") return g.source?.state === "success" ? "guide.next" : g.source?.state === "error" ? "guide.ready.retry"
    : ["estimated", "empty"].includes(g.source?.state) ? "guide.source.another" : "guide.source.open";
  if (["G08", "G11"].includes(screen)) return state === "success" ? "guide.next" : ["sending", "running"].includes(state)
    ? "guide.trial.busy" : ["recovery", "unavailable"].includes(state) ? "guide.ready.retry" : state === "failed"
    ? "guide.trial.retry" : screen === "G08" ? "guide.practice.send" : "guide.trial.send";
  return `guide.screens.${screen}.next`;
}
function guideNextDisabled() {
  const g = S.guide;
  if (g.screen === "G02") return !guideProgress().choices.length;
  if (g.screen === "G14") return !g.defaults?.selected?.usable;
  if (g.screen === "G05") return !g.readiness || [g.readiness.results, g.readiness.key].includes("checking");
  if (g.screen === "G07") return !g.source || g.source.state === "loading";
  if (["G08", "G11"].includes(g.screen)) return !g.trial || ["running", "sending"].includes(g.trial.state) || g.aiChecking;
  return g.screen === "G10" && g.aiChecking;
}
function guideUpdatePractice() {
  if (!S.guide.open) return;
  const content = document.getElementById("guide-content"), active = document.activeElement?.id;
  if (content) content.replaceWith(guidePracticeContent());
  document.getElementById("guide-title").textContent = guideTitle();
  document.getElementById("guide-overlay").setAttribute("data-variant", guideVariant());
  const next = document.getElementById("guide-next"); next.textContent = T(guideNextKey()); next.disabled = guideNextDisabled();
  const skip = document.getElementById("guide-skip-practice");
  if (skip) skip.hidden = ["sending", "running"].includes(S.guide.trial?.state);
  if (active && !document.activeElement?.isConnected) document.getElementById(active)?.focus({preventScroll: true});
}
function guideBefore(kind) {
  return h("div", {class: "guide-before"}, h("strong", null, T("guide.before")),
    h("p", null, T(`guide.${kind}.uses`)), h("p", null, T(`guide.${kind}.record`)));
}
function guideError(fact, todo, error) {return friendlyError({message: T(fact), fix: T(todo), raw: error?.message});}
function guidePracticeContent() {
  const screen = S.guide.screen;
  return h("div", {id: "guide-content"}, screen === "G05" ? guideReadinessContent() : screen === "G07" ? guideSourceContent()
    : ["G08", "G11"].includes(screen) ? guideTrialContent() : screen === "G10" ? guideAIContent()
    : screen === "G12" ? guideRecordsContent() : screen === "G02" ? guideChoicesContent() : screen === "G14" ? guideDefaultsContent()
    : screen === "G16" ? guideDataContent("source") : screen === "G17" ? guideDataContent("answers") : null);
}
function guideReadinessContent() {
  const r = S.guide.readiness || {}, failed = [r.results, r.key].includes("unknown");
  return h("div", null,
    h("p", {class: "guide-lead"}, T(r.results === "absent" ? "guide.ready.empty_lead" : "guide.ready.lead")),
    h("div", {class: "guide-ready-list", "aria-live": "polite"}, ["results", "key", "ai"].map(name => {
      const state = r[name] || "checking";
      return h("div", {id: `guide-ready-${name}`, class: "guide-ready-row", "data-state": state},
        h("div", null, h("strong", null, T(`guide.ready.${name}`)), h("span", null, T(`guide.ready.states.${state}`))),
        name === "results" && r.run ? h("p", null, scoreLabel(r.run)) : null,
        name === "key" && r.keyInfo ? h("p", null, r.keyInfo.label || r.keyInfo.id) : null);
    })),
    h("p", {class: "guide-after"}, T("guide.ready.ai_optional")),
    failed ? guideError("guide.ready.request_failed", "guide.ready.retry_todo", r.error) : null,
    guideButton("guide-ai-open", "guide.ready.open_ai", guideHandoff));
}
function guideSourceContent() {
  const state = S.guide.source, v = state?.entry?.v;
  return h("div", null, h("p", {class: "guide-lead"}, T("guide.source.lead")),
    h("div", {id: "guide-practice", class: "guide-practice"}, guideBefore("source"),
      v ? [h("h2", null, scoreItemName(state.item)),
        h("p", null, T(state.section === 8 ? "guide.source.exposure_meaning" : "guide.source.criterion_meaning")),
        h("p", {class: "raw"}, T("guide.target", {doc: state.doc, section: state.section})),
        h("p", null, T(state.entry.only ? "source.kinds.missing" : "source.kinds.wrong")),
        h("div", {class: "guide-value-pair"}, h("div", null, h("span", null, T("guide.source.ai_value")),
          h("div", {class: "guide-value raw-value"}, state.entry.only ? T("common.none") : jobsFocusValue(v.value, v.text))),
        h("div", null, h("span", null, T("guide.source.key_value")),
          h("div", {class: "guide-value raw-value"}, jobsFocusValue(state.entry.only ? v.value : v.silver?.value, state.entry.only ? v.text : v.silver?.text))))] : null,
      state?.state === "loading" ? h("p", {role: "status"}, T("guide.ready.states.checking")) : null,
      state?.state === "error" ? guideError("guide.source.request_failed", "guide.source.retry_todo", state.error) : null,
      state?.state === "empty" ? h("p", null, T("guide.source.empty")) : null,
      state?.state === "estimated" ? h("div", {class: "guide-inplace"}, h("strong", null, T("guide.source.estimated_only")),
        h("p", null, T("guide.source.no_actual")), h("p", null, T("guide.source.not_recorded"))) : null,
      ["shown", "success"].includes(state?.state) ? h("div", {id: "guide-source-lines", class: "guide-inplace guide-evidence"},
        [...state.selectedLines].map(id => state.line[id]).filter(line => line.page === state.page).map(line =>
          h("div", {"data-line": line.id, "aria-pressed": "true"}, h("strong", null, T("guide.source.line", {page: line.page, line_no: line.no || line.id.split("L").at(-1)})),
            h("p", {class: "source-text"}, line.text))), h("p", null, T("guide.source.actual"))) : null,
      state?.state === "waiting" ? h("p", {class: "guide-inplace"}, T("guide.source.waiting")) : null),
    h("p", {class: "guide-after"}, T("guide.source.key_caution")));
}
function guideAIContent() {
  const g = S.guide;
  return h("div", null, h("p", {class: "guide-lead"}, T("guide.ai.lead")),
    h("p", {role: "status"}, T(g.aiChecking ? "guide.ready.states.checking" : g.aiState === "unknown" ? "guide.ready.states.unknown"
      : g.returned ? "guide.ai.still_off" : "guide.ai.off")),
    serversData()?.rngd?.diagnosis === "no_model" ? h("p", null, T("guide.ai.tunnel_open")) : null,
    S.shell.serverAt ? h("p", {class: "muted"}, T("guide.ai.checked", {time: when(S.shell.serverAt)})) : null,
    g.returned ? h("p", null, T("guide.ai.return_not_success")) : null,
    guideButton("guide-ai-recheck", "guide.ready.retry", guideRecheckAI));
}
function guideTrialContent() {
  const t = S.guide.trial, dry = S.guide.screen === "G08", kind = dry ? "practice" : "trial";
  const running = ["running", "sending"].includes(t?.state), done = ["shown", "success"].includes(t?.state);
  return h("div", null, dry ? h("p", {class: "guide-lead"}, T("guide.practice.lead")) : null,
    h("div", {id: "guide-practice", class: "guide-practice"}, guideBefore(kind),
      t?.doc ? h("p", {class: "raw"}, T("guide.target", {doc: t.doc, section: t.section})) : null,
      t?.model ? [h("p", null, T("servers.connection.selected"), ": ", jobsModelLabel(t.model)),
        jobsModelDifference(t.model, S.guide.target?.run === t.base ? S.guide.target.model
          : S.jobs.runs.find(run => run.name === t.base)?.model_tag)] : null,
      !t ? h("p", {role: "status"}, T("guide.ready.states.checking")) : null,
      t?.state === "waiting" ? h("p", {class: "guide-inplace"}, T(`guide.${kind}.waiting`)) : null,
      t?.state === "unavailable" ? guideError("guide.recovery.no_target", "guide.recovery.target_todo", t.error) : null,
      running ? h("div", {role: "status", "aria-live": "polite"}, h("p", null, T("guide.trial.waiting_answer")),
        h("p", null, T("guide.trial.elapsed", {seconds: Math.max(0, Math.floor((Date.now() - t.started) / 1000))})),
        h("ol", {class: "guide-stages"}, ["input", "answer", "parse", "summary"].map((name, i) => h("li", null,
          T(`guide.trial.stages.${name}`), " — ", T(i === 0 && t.id ? "guide.trial.complete" : i <= 1 ? "guide.trial.progress" : "guide.trial.wait")))),
        h("p", null, T(dry ? "guide.practice.no_real" : "guide.trial.not_yet")),
        dry ? guideButton("guide-cancel-practice", "guide.practice.cancel", guideCancelPractice) : h("p", null, T("guide.trial.cannot_stop"))) : null,
      t?.state === "failed" ? [guideError(t.failureKind === "job" ? "guide.recovery.fact" : "guide.trial.failed_fact", "guide.trial.failed_todo", t.error),
        h("p", null, T("guide.trial.not_recorded"))] : null,
      t?.state === "cancelled" ? [h("p", null, T("guide.recovery.cancelled")),
        guideButton("guide-reprepare", "guide.ready.retry", async () => {await guidePrepareTrial(); guideRender();})] : null,
      t?.state === "recovery" ? [guideError("guide.recovery.fact", "guide.recovery.todo", t.error),
        t.response?.status ? h("p", null, T("jobs.result_missing.todo", {status_code: t.response.status})) : null,
        guideButton("guide-result-retry", "jobs.result.retry", guidePollTrial)] : null,
      done ? h("div", {id: "guide-result-summary", class: "guide-inplace", role: "status"},
        h("strong", null, T(`guide.${kind}.done`)), jobsResultSummary(t.result, t.job),
        dry ? h("details", {id: "guide-plan-details"}, h("summary", null, T("guide.practice.sent_details")),
          guidePlan(t.result.plan, t.prompt)) : h("details", null, h("summary", null, T("guide.trial.proof")),
          h("p", null, T("guide.trial.proof_text", {section: t.section, status: t.response.status})),
          jobsPre(t.result.results?.[String(t.section)]?.parsed))) : null));
}
function guidePlan(plan, prompt) {
  return h("div", null, h("h2", null, T("guide.practice.prompt")),
    h("details", null, h("summary", null, T("guide.practice.prompt_open")), jobsPre(prompt)),
    h("ul", null, Object.values(plan?.sections || {}).map(section => h("li", {class: "raw"}, section.prompt_hash || T("common.none")))),
    h("h2", null, T("guide.practice.input")), h("ul", null, Object.entries(plan?.sections || {}).map(([no, v]) => h("li", null,
      T("jobs.result.input_rows", {section: no, format: T(v.rows ? "jobs.result.format_rows" : "jobs.result.format_json"),
        count: v.lines, preamble: v.preamble_lines, first: v.first, last: v.last, pages: (v.pages || []).join(", "),
        images: (v.images || []).join(", ") || T("common.none"), method: coreCodeLabel("split", v.method)})))));
}
function guideDataContent(kind) {
  const D = key => T(`guide.data.${kind}.${key}`), adds = kind === "source" ? ["add1", "add2", "add3", "add4"] : ["add1", "add2", "add3"];
  return h("div", null, h("p", {class: "guide-lead"}, D("lead")),
    kind === "source" ? [h("p", null, D("example")), h("p", null, D("set"))] : [h("h2", null, D("kinds_title")), h("ul", {class: "guide-terms"}, h("li", null, D("gold")), h("li", null, D("silver")))],
    h("h2", null, D("change_title")), h("p", null, D("change")),
    h("h2", null, D("receive_title")), h("p", null, D("receive")),
    h("h2", null, D("add_title")), h("ol", {class: "guide-steps"}, adds.map(key => h("li", null, D(key)))),
    h("p", {class: "guide-after"}, D("caution")));
}
function guideRecordsContent() {
  const record = S.guide.session || {};
  const rows = ["source", "practice", "trial"].map(kind => {
    const value = !record[kind] ? T("guide.records.none") : kind === "practice"
      ? T("guide.records.count", {count: record.practice}) : when(record[kind]);
    return h("div", {class: "guide-ready-row"}, h("div", null,
      h("strong", null, T(`guide.records.${kind}`)), h("span", null, value)));
  });
  return h("div", null, h("p", {class: "guide-lead"}, T(record.trial ? "guide.records.lead" : record.source ? "guide.records.source_only" : "guide.records.practice_only")),
    h("div", {id: "guide-session-records", class: "guide-ready-list"}, rows),
    h("p", {class: "guide-after"}, T("guide.records.separate")));
}

function guideChoicesContent() {
  return h("div", null, h("p", {class: "guide-lead"}, T("guide.choices.lead")),
    h("p", null, T("guide.choices.skip")),
    h("fieldset", {class: "guide-choice-list"}, h("legend", null, T("guide.choices.legend")),
      ["score", "source", "retest", "ai"].map(choice => {
        const checked = guideProgress().choices.includes(choice);
        return h("label", {class: "guide-choice-card", "data-selected": String(checked)},
          h("input", {id: `guide-choice-${choice}`, type: "checkbox", checked,
            onchange: event => guideSetChoice(choice, event.target.checked)}),
          h("span", null, h("strong", null, T(`guide.choices.${choice}.title`)),
            h("span", {class: "guide-choice-note"}, T(`guide.choices.${choice}.note`)),
            checked ? h("span", {class: "guide-choice-selected"}, T("guide.choices.selected")) : null));
      })));
}
async function guideLoadDefaults() {
  const g = S.guide, epoch = g.epoch, state = g.defaults;
  try {
    const [sets, keys] = await guideRequest(Promise.all([api("/api/sets"), api("/api/keys")]));
    if (!guideCurrent(epoch, "G14") || g.defaults !== state) return;
    S.shell.sets = sets.sets || []; S.shell.keys = keys.keys || [];
    state.choices = S.shell.sets.flatMap(set => S.shell.keys.map(key => {
      const known = Array.isArray(set.docs) && Array.isArray(key.docs);
      const covered = known && set.docs.some(doc => !doc.locked && doc.group !== "eval" && key.docs.includes(doc.doc_id));
      const reasons = [!set.usable ? set.reason || T("context.unavailable") : null,
        !key.usable ? key.reason || T("context.unavailable") : null,
        set.usable && key.usable && !covered ? T(known ? "guide.defaults.no_answers" : "context.unavailable") : null].filter(Boolean);
      return {set, key, usable: !!(set.usable && key.usable && covered), reason: reasons.join(" · ")};
    }));
    state.choices.sort((a, b) => Number(b.set.id === S.ctx.set && b.key.id === S.ctx.key) - Number(a.set.id === S.ctx.set && a.key.id === S.ctx.key));
  } catch (error) {if (guideCurrent(epoch, "G14")) state.error = error;}
  finally {if (guideCurrent(epoch, "G14")) {state.loading = false; guideRender();}}
}
async function guidePreviewDefaults(choice) {
  if (!choice.usable) return;
  const g = S.guide, epoch = g.epoch, state = g.defaults;
  const request = state.request = (state.request || 0) + 1;
  const valid = () => guideCurrent(epoch, "G14") && g.defaults === state && state.request === request;
  state.selected = choice; state.preview = {loading: true};
  emit("onboarding_action", {screen: "G14", action: "choose_defaults"});
  guideRender(); document.getElementById(`guide-default-${state.choices.indexOf(choice)}`)?.focus({preventScroll: true});
  const url = path => `${path}?${new URLSearchParams({key: choice.key.id})}`;
  try {
    const list = await guideRequest(shellContextResults(choice.set.id, choice.key.id));
    if (!valid()) return;
    const run = list.current;
    state.preview.count = list.runs.length;
    const result = run ? await guideRequest(api(url(scoreRunPath(run.name)))) : null;
    if (!valid()) return;
    if (result && (result.set?.id !== choice.set.id || result.key?.id !== choice.key.id)) throw new Error(T("guide.defaults.mismatch"));
    state.preview = {run: result, count: list.runs.length};
  } catch (error) {if (valid()) state.preview = {count: state.preview.count, error};}
  finally {if (valid()) guideUpdatePractice();}
}
async function guideApplyDefaults() {
  const g = S.guide, choice = g.defaults?.selected;
  if (!choice?.usable) return;
  const next = g.defaultsReturn || "G15";
  g.applyingDefaults = true;
  try {
    if (!shellApplyContext({set: choice.set.id, key: choice.key.id})) return;
    g.defaultsReturn = null;
  } finally {g.applyingDefaults = false;}
  return guideShow(next);
}
function guideDefaultsPreview() {
  const preview = S.guide.defaults?.preview;
  return h("div", {class: "guide-choice-preview", role: "status", "aria-live": "polite"},
    !preview?.error || num(preview?.count) ? h("div", {class: "context-result-effect"}, shellContextResultNotice(preview)) : null,
    preview?.loading ? null : preview?.error
      ? guideError("guide.defaults.failed", "guide.defaults.failed_todo", preview.error)
      : !preview?.run || !num(preview.run.weighted)
        ? h("div", null, h("strong", null, T("guide.defaults.empty")), h("p", null, T("guide.defaults.empty_note")))
        : h("div", null, h("p", null, T("guide.defaults.preview")), h("div", {class: "guide-value"},
          preview.run.weighted.toFixed(1), h("span", {class: "guide-unit"}, T("guide.example.score_unit"))),
          h("p", null, shellKeyLabel(preview.run.key)), h("p", null, T("guide.example.trust"))));
}
function guideDefaultsContent() {
  const state = S.guide.defaults;
  const current = state?.choices.find(choice => choice.set.id === S.ctx.set && choice.key.id === S.ctx.key);
  const alternatives = state?.choices.filter(choice => choice !== current) || [];
  const unavailable = alternatives.filter(choice => !choice.usable);
  const renderChoice = (choice, compact = false) => {
    const selected = choice === state.selected, isCurrent = choice === current;
    return h(compact ? "li" : "div", {class: compact ? "guide-unavailable-choice" : "guide-choice-card", "data-selected": String(selected)},
      h("label", null, h("input", {id: `guide-default-${state.choices.indexOf(choice)}`, type: "radio", name: "guide-default", checked: selected,
        "data-set": choice.set.id, "data-key": choice.key.id, disabled: !choice.usable,
        onchange: () => guidePreviewDefaults(choice)}),
        h("span", null, h("strong", null, isCurrent ? T("guide.defaults.current") : choice.key.label || choice.key.id),
          isCurrent ? h("span", {class: "guide-choice-note"}, `${choice.set.label || choice.set.id} · ${choice.key.label || choice.key.id}`) : null,
          !choice.usable ? h("span", {class: "guide-choice-note"}, choice.reason) : null,
          selected ? h("span", {class: "guide-choice-selected"}, T("guide.choices.selected")) : null)),
      selected ? guideDefaultsPreview() : null);
  };
  const groups = (choices, compact = false) => [...new Set(choices.map(choice => choice.set.id))].map(id => {
    const group = choices.filter(choice => choice.set.id === id), set = group[0].set;
    return h("div", {class: "guide-default-group", role: "group", "aria-label": set.label || set.id}, h("h3", null, set.label || set.id),
      compact ? h("ul", null, group.map(choice => renderChoice(choice, true))) : group.map(choice => renderChoice(choice)));
  });
  return h("div", null, h("p", {class: "guide-lead"}, T("guide.defaults.lead")),
    h("p", null, T("guide.defaults.definition")),
    state?.loading ? h("p", {role: "status"}, T("guide.ready.states.checking")) : null,
    state?.error ? h("div", null, guideError("guide.defaults.load_failed", "guide.defaults.load_todo", state.error),
      guideButton("guide-defaults-retry", "guide.ready.retry", () => guideShow("G14"))) : null,
    state && !state.loading && !state.error ? h("fieldset", {class: "guide-choice-list"},
      h("legend", null, T("guide.defaults.legend")),
      current ? renderChoice(current) : null, groups(alternatives.filter(choice => choice.usable)),
      unavailable.length ? h("details", {id: "guide-unavailable", open: !!state.unavailableOpen,
        ontoggle: event => {state.unavailableOpen = event.target.open;}},
        h("summary", null, T("guide.defaults.unavailable", {count: unavailable.length})), groups(unavailable, true)) : null,
      !state.choices.length ? h("p", null, T("context.unavailable")) : null) : null);
}
