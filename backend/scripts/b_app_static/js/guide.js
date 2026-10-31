"use strict";

// 미구현 실습·선택은 순서표에서 제외한다. 장 위치는 승인 시안의 번호다.
const guideOrder = ["G01", "G03", "G04", "G06", "G09", "G13", "G15"];
const guideScreens = {
  G01: {intro: true, example: "score"}, G03: {chapter: 1, n: 3, m: 3, example: "steps"},
  G04: {intro: true, example: "ready"}, G06: {intro: true, example: "source"},
  G09: {chapter: 3, n: 4, m: 7, example: "result"},
  G13: {intro: true, example: "defaults"}, G15: {intro: true, example: "score"}
};
S.guide = {open: false, screen: "G01", bootEligible: false, bootChecked: false,
  returnFocus: null, confirmFocus: null, background: []};

function guideDefault() {return {state: "not_started", screen: null, choices: [], skipped: [], updated_at: null};}
function guideProgress() {return S.journey.progress.guide || guideDefault();}
function guideSupported(screen) {
  if (!screen) return "G01";
  return guideOrder.includes(screen) ? screen : guideOrder.find(id => id > (screen || "G01")) || "G15";
}
function guideButton(id, key, action, primary = false) {
  return h("button", {id, type: "button", class: primary ? "primary" : "text-button",
    onclick: () => Promise.resolve(action()).catch(fail)}, T(key));
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
  if (replay) {
    // 성공·대기 작업·옛 갈래 진행을 건드리지 않는다. 직렬 PUT은 journey가 맡는다.
    journeyChange(j => {j.progress.guide = {...guideDefault(), state: "in_progress", screen: "G01", updated_at: journeyTime()};});
    emit("onboarding_replayed", {had_real: !!(S.journey.outcomes.t1.real || S.journey.outcomes.t2.real),
      had_practice: !!S.journey.outcomes.t2.practice});
  }
  guideRender(); emit("onboarding_step_viewed", {screen: S.guide.screen});
}
function guideNext() {
  const from = S.guide.screen;
  emit("onboarding_action", {screen: from, action: "next"});
  if (from === "G15") return guideClose("completed");
  S.guide.screen = guideOrder[guideOrder.indexOf(from) + 1];
  const saved = journeyChange(j => {j.progress.guide = {...guideProgress(), state: "in_progress",
    screen: S.guide.screen, updated_at: journeyTime()};});
  guideRender(); emit("onboarding_step_viewed", {screen: S.guide.screen});
  return saved;
}
function guideBack() {
  const index = guideOrder.indexOf(S.guide.screen);
  if (index <= 0) return;
  S.guide.screen = guideOrder[index - 1]; guideRender();
  emit("onboarding_action", {screen: S.guide.screen, action: "back"});
}
async function guideClose(state = "in_progress") {
  S.guide.open = false; S.guide.bootChecked = true;
  document.getElementById("guide-overlay").hidden = true; guideBackground(false);
  journeyChange(j => {
    const prior = guideProgress();
    j.progress.guide = {...prior, state, screen: state === "completed" ? "G15" : prior.screen || "G01",
      updated_at: prior.updated_at || journeyTime()};
    j.progress.dismissed_at = journeyTime();
  });
  emit(state === "completed" ? "onboarding_completed" : "onboarding_action", {screen: S.guide.screen, action: state});
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
      Array.from({length: meta.m}, (_, i) => h("span", {class: i < meta.n ? "filled" : null}))),
    h("p", {id: "guide-progress-text", class: "guide-progress-text"}, T("guide.progress",
      {chapter: T(`guide.chapters.${meta.chapter}`), n: meta.n, m: meta.m, k: meta.chapter})));
}
function guideExampleText(key, values = {}) {return T(`guide.example.${key}`, {...UI.guide.example.values, ...values});}
function guideExampleRow(label, value) {return h("div", {class: "guide-mini-row"}, h("span", null, guideExampleText(label)), h("strong", null, guideExampleText(value)));}
function guideExampleScore() {
  return h("div", {class: "guide-mini-content"}, h("h2", null, guideExampleText("score_title")),
    h("div", {class: "guide-mini-score"}, guideExampleText("score"), h("span", null, guideExampleText("score_unit"))),
    h("p", null, guideExampleText("gap")),
    h("div", {class: "guide-scale", "aria-hidden": "true"}, h("span", {style: `width:${UI.guide.example.values.score}%`}),
      h("i", {style: `left:${UI.guide.example.values.target}%`})),
    h("p", {class: "guide-scale-label"}, guideExampleText("target")),
    S.guide.screen === "G01" ? h("p", null, guideExampleText("essential_definition")) : null,
    h("p", null, guideExampleText("essential")));
}
function guideExamplePair(result = false) {
  return h("div", {class: "guide-value-pair"}, [false, true].map(answer => h("div", null,
    h("span", null, guideExampleText(result ? (answer ? "new_value" : "old_value") : (answer ? "answer_label" : "ai_value"))),
    h("div", {class: "guide-value"}, guideExampleText(answer ? "answer" : "prediction"),
      h("span", {class: "guide-unit"}, guideExampleText("unit"))))));
}
function guideExample(kind) {
  const E = guideExampleText;
  let content;
  if (kind === "steps") content = h("div", {class: "guide-mini-steps"},
    h("div", null, h("h2", null, E("step1")), h("div", null, h("strong", null, E("biggest")),
      h("p", {class: "guide-value"}, E("score"), h("span", {class: "guide-unit"}, E("points"))), h("p", null, E("view_limit")))),
    h("div", null, h("h2", null, E("step2")), h("div", null, h("strong", null, E("doc")),
      h("div", {class: "guide-mini-source"}, E("line"), h("p", null, E("short_source"))))),
    h("div", null, h("h2", null, E("step3")), h("div", null, h("strong", null, E("section")),
      h("p", {class: "guide-value"}, E("answer"), h("span", {class: "guide-unit"}, E("unit"))), h("p", null, E("new_answer")))));
  else {
    let body;
    if (kind === "score") body = [guideExampleScore(), h("div", {class: "guide-mini-sub"}, h("strong", null, E("problem")),
      h("p", null, E(S.guide.screen === "G01" ? "limit_definition" : "limit_short")),
      S.guide.screen === "G01" ? h("p", null, E("exposure")) : null, h("p", null, E("loss")))];
    if (kind === "ready") body = h("div", {class: "guide-mini-content"}, h("h2", null, E("ready_title")),
      guideExampleRow("saved", "present"), guideExampleRow("key", "present"), guideExampleRow("ai", "absent"), h("p", {class: "guide-after"}, E("offline")));
    if (kind === "source" || kind === "result") body = h("div", {class: "guide-mini-content"}, h("h2", null, E(kind === "source" ? "source_title" : "result_title")),
      h("p", null, E(kind === "source" ? "source_target" : "result_target")), guideExamplePair(kind === "result"),
      h("div", {class: "guide-mini-source"}, h("strong", null, E("line")), h("p", null, E("source"))),
      h("p", {class: "guide-after"}, E(kind === "source" ? "read_line" : "result_note")));
    if (kind === "defaults") body = h("div", {class: "guide-mini-content"}, h("h2", null, E("defaults_title")),
      guideExampleRow("set", "set_name"), guideExampleRow("key", "answer_name"),
      h("div", {class: "guide-mini-score"}, E("score"), h("span", null, E("score_unit"))), h("p", null, E("trust")));
    content = h("div", {class: "guide-mini-screen"}, h("div", {class: "guide-mini-head"}, E("brand")),
      h("div", {class: "guide-mini-context"}, E(S.guide.screen === "G01" ? "context_first" : "context"),
        S.guide.screen === "G01" ? h("p", null, E("draft_definition")) : null), body);
  }
  return h("aside", {id: "guide-example", class: "guide-example", "aria-label": E("label")}, h("div", {class: "app-name"}, E("brand")),
    h("div", {class: "guide-demo-center"}, h("figure", null, h("figcaption", null, h("span", {class: "guide-example-badge"}, E("badge"))), content,
      S.guide.screen === "G15" ? h("div", {class: "guide-demo-record"}, h("h2", null, E("records.title")),
        h("ul", null, ["source", "practice", "trial"].map(k => h("li", null,
          h("strong", null, E(`records.${k}_label`)), h("span", null, E(`records.${k}`)))))) : null,
      kind === "defaults" ? h("p", {class: "guide-demo-caption"}, E("set_definition")) : null)));
}
function guideRender() {
  if (!S.guide.open) return;
  const overlay = document.getElementById("guide-overlay"), screen = S.guide.screen, meta = guideScreens[screen];
  overlay.hidden = false; overlay.setAttribute("data-screen", screen);
  coreReplace(overlay, h("div", {id: "guide-frame", class: `guide-frame${meta.intro ? " guide-intro" : ""}`}, guideExample(meta.example),
    h("div", {class: "guide-column"}, h("div", {class: "guide-inner"},
      h("header", null, h("nav", {class: "guide-nav", "aria-label": T("guide.navigation")},
        screen !== "G01" ? guideButton("guide-back", "guide.back", guideBack) : null,
        screen !== "G01" ? guideButton("guide-close", "guide.close.action", () => guideClose()) : null), guideChapterRow(meta)),
      h("div", {class: "guide-step-body"}, h("h1", {id: "guide-title", tabindex: "-1"}, T(`guide.screens.${screen}.title`)),
        h("div", {id: "guide-notices", "aria-live": "polite"}),
        screen === "G03" ? [h("p", {class: "guide-lead"}, T("guide.screens.G03.lead")), h("h2", null, T("guide.screens.G03.terms")),
          h("ul", {class: "guide-terms"}, ["draft", "part", "limit"].map(k => h("li", null, T(`guide.screens.G03.${k}`))))] : null,
        screen === "G09" ? [h("p", {class: "guide-lead"}, T("guide.screens.G09.lead")), h("p", null, T("guide.screens.G09.example")),
          h("p", {class: "muted"}, T("guide.screens.G09.no_success"))] : null,
        screen === "G15" ? h("div", {id: "guide-records"}) : null),
      h("footer", {class: "guide-action"}, screen === "G01" ? guideButton("guide-skip", "guide.skip", () => guideClose("skipped")) : null,
        guideButton("guide-next", `guide.screens.${screen}.next`, guideNext, true))))),
    h("div", {id: "guide-confirm", class: "guide-confirm", hidden: true}));
  guideRefreshRecords(); document.getElementById("guide-title").focus();
}
function guideRefreshRecords() {
  const u = S.journeyUI;
  const notices = document.getElementById("guide-notices");
  if (notices) coreReplace(notices, u.storageNotice ? friendlyError(u.storageNotice) : null,
    u.problems ? h("div", {role: "status"}, T("journey.partial_record.title"), u.problems.map(t => h("p", null, t))) : null);
  for (const id of ["guide-records", "help-guide-records"]) {
    const target = document.getElementById(id); if (target) journeyRenderRecords(target, id);
  }
  const resume = document.getElementById("guide-resume"), progress = guideProgress();
  resume.hidden = !u.known || progress.state !== "in_progress";
  if (!resume.hidden && !resume.querySelector("button")) coreReplace(resume, h("p", null, T("guide.resume")),
    guideButton("guide-resume-button", "guide.resume_action", () => guideOpen({resume: true})));
}
function guideSync() {
  guideRefreshRecords();
  if (!S.guide.bootEligible || S.guide.bootChecked || (!S.journeyUI.known && !S.journeyUI.storageNotice)) return;
  S.guide.bootChecked = true;
  if (!S.journeyUI.known || S.journeyUI.problems || S.shell.navigation > 1 || S.shell.route !== "s01") return;
  const p = guideProgress(), closed = S.journey.progress.dismissed_at;
  if (p.state === "in_progress" && (!closed || p.updated_at > closed)) guideOpen({resume: true}).catch(fail);
  else if (p.state === "not_started" && journeyPristine()) guideOpen().catch(fail);
}
on("shell_started", ({hash}) => {S.guide.bootEligible = !hash;});
on("journey_changed", guideSync);
on("screen_shown", guideSync);
on("guide_open", () => {guideOpen({replay: true}).catch(fail);});
