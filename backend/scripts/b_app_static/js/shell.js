"use strict";

const SHELL_SCREENS = {
  s01: {title: "nav.recent", views: ["score-summary", "score-problems", "score-history", "score-docs", "score-grid", "score-rows", "score-rule", "score-gaps"]},
  s02: {title: "nav.source", views: ["source-top", "source-values", "source-page", "source-selection"]},
  s03: {title: "nav.retest", views: ["jobs-try", "jobs-result", "jobs-connection"]},
  s04: {title: "nav.compare", views: ["compare-summary", "compare-conditions", "compare-items", "compare-values", "compare-rows", "compare-prompts"]},
  s05: {title: "nav.jobs", views: ["jobs-list", "jobs-detail"]},
  s06: {title: "nav.servers", views: ["servers-summary", "servers-rngd", "servers-runpod", "servers-models", "servers-log"]},
  s07: {title: "nav.help", views: ["help-topics", "help-glossary"]},
  s08: {title: "nav.open_guide", views: ["journey-choice", "journey-records"]},
  s09: {title: "jobs.trial.open_batch", parent: "s03", views: ["jobs-run"]},
  s10: {title: "compare.table.open", parent: "s04", views: ["jobs-compare"]}
};
const shellViews = new Map();
S.shell = {route: null, sets: [], keys: [], contextErrors: [], contextLoaded: false,
  servers: null, serverError: null, serverAt: null, polling: null, timer: null,
  started: false, ready: null, contextReady: null, contextRequest: 0, navigation: 0, pickerFocus: null};
const SHELL_SERVER_TIMEOUT_MS = 60000;

function shellDefineView(viewId, handlers) {
  if (!Object.values(SHELL_SCREENS).some(screen => screen.views.includes(viewId))) throw new Error(`Unknown view: ${viewId}`);
  shellViews.set(viewId, handlers);
}
function shellInitialRoute(hash) {
  const id = String(hash || "").replace(/^#/, "");
  return Object.hasOwn(SHELL_SCREENS, id) ? id : "s01";
}
function shellConclusion(id, text, normal = true) {
  const title = document.getElementById(`title-${id}`);
  title.textContent = text;
  const existing = document.getElementById(`flow-${id}`);
  if (!normal) { existing?.remove(); return; }
  if (existing) return;
  const current = ["s01", "s02", "s03"].indexOf(id);
  title.before(h("ol", {id: `flow-${id}`, class: "score-flow", "aria-label": T("score.flow.a11y")},
    ["result", "cause", "retest"].map((step, i) => h("li", {"aria-current": i === current ? "step" : null}, T(`score.flow.${step}`)))));
}
async function go(id, args = {}) {
  id = shellInitialRoute(id.startsWith("#") ? id : `#${id}`);
  S.focus = {...S.focus, ...args}; S.shell.route = id;
  status(T("errors.loading.fact"));
  if (S.shell.timer !== null) shellScheduleServers();
  const navigation = ++S.shell.navigation;
  history.replaceState(null, "", `#${id}`);
  for (const [screenId, screen] of Object.entries(SHELL_SCREENS)) {
    const el = document.getElementById(`screen-${screenId}`);
    el.hidden = screenId !== id;
    document.getElementById(`title-${screenId}`).textContent = T(screen.title);
  }
  document.querySelectorAll("[data-screen]").forEach(button => {
    const own = button.dataset.screen === id;
    const parent = button.dataset.screen === SHELL_SCREENS[id].parent;
    if (own || parent) button.setAttribute("aria-current", own ? "page" : "true");
    else button.removeAttribute("aria-current");
    const marker = button.querySelector(".nav-current");
    if (marker) marker.hidden = !(own || parent);
  });
  document.querySelectorAll("[data-parent]").forEach(el => {
    el.hidden = el.dataset.parent !== id && el.dataset.parent !== SHELL_SCREENS[id].parent;
  });
  for (const viewId of SHELL_SCREENS[id].views) {
    const view = shellViews.get(viewId);
    if (!view) continue;
    const el = document.getElementById(viewId);
    try {
      if (view.load) {
        if (!el.textContent.trim()) el.replaceChildren(h("p", {role: "status"}, T("errors.loading.fact")));
        await view.load(args);
      }
      if (navigation !== S.shell.navigation) return;
      if (view.render) view.render(el, args);
    } catch (error) {
      if (navigation === S.shell.navigation) el.replaceChildren(loadFailure(error.message));
    }
  }
  if (navigation === S.shell.navigation) {
    status(T("common.screen_shown", {screen: T(SHELL_SCREENS[id].title)}));
    emit("screen_shown", {screen: id, args});
  }
}
function ctxUrl(path) {
  const [base, query = ""] = path.split("?");
  if (!S.ctx.key || !(base === "/api/runs" || base.startsWith("/api/run/") ||
      ["/api/diff", "/api/silver_gaps", "/api/doc"].includes(base))) return path;
  const params = new URLSearchParams(query); params.set("key", S.ctx.key);
  return `${base}?${params}`;
}
function shellNavButton(id, key = SHELL_SCREENS[id].title, current = false) {
  return h("button", {type: "button", "data-screen": id, onclick: () => {
    go(id).catch(fail); document.getElementById(`title-${id}`).focus();
  }}, T(key), current ? h("span", {class: "nav-current", hidden: true}, T("nav.current")) : null);
}
function shellRenderHeader() {
  document.getElementById("app-heading").replaceChildren(
    h("div", null, h("div", {class: "app-name"}, T("nav.app_name")),
      h("p", {class: "app-purpose"}, T("nav.purpose")),
      h("p", {class: "definition"}, T("common.document_definition"))),
    h("div", {class: "head-side"}, shellNavButton("s08"), shellNavButton("s05", "nav.open_jobs")));
  const nav = document.getElementById("main-nav"); nav.setAttribute("aria-label", T("nav.a11y"));
  const entries = ["s01", "s02", "s03", "s04", "s05", "s06", "s07"].map(id =>
    h("div", null, shellNavButton(id, SHELL_SCREENS[id].title, true),
      Object.entries(SHELL_SCREENS).filter(([, screen]) => screen.parent === id).map(([child]) =>
        h("div", {class: "subnav", "data-parent": id, hidden: true}, shellNavButton(child)))));
  nav.replaceChildren(...entries, h("p", {class: "sidebar-note"}, T("common.local_only"), h("br"), T("common.tool_kind")));
}
function shellChosen(items, saved, fallback) {
  return items.find(item => item.id === saved && item.usable)?.id
    ?? items.find(item => item.id === fallback && item.usable)?.id ?? null;
}
function shellKeyLabel(key) {
  return key?.label || S.shell.keys.find(item => key?.id && item.id === key.id)?.label || T("score.basis.fallback");
}
function shellKeyMismatch(key) {
  return key?.id && S.ctx.key && key.id !== S.ctx.key ? T("context.answer_mismatch", {
    result_key: shellKeyLabel(key), selected_key: shellKeyLabel({id: S.ctx.key})
  }) : null;
}
async function shellLoadContext() {
  const request = ++S.shell.contextRequest;
  const results = await Promise.allSettled([api("/api/sets"), api("/api/keys")]);
  if (request !== S.shell.contextRequest) return;
  const saved = S.shell.contextLoaded ? S.ctx : coreRead("b_app.context", {});
  const valid = saved?.version === 1 ? saved : {};
  S.shell.contextErrors = results.filter(result => result.status === "rejected").map(result => result.reason.message);
  const sets = results[0].status === "fulfilled" ? results[0].value : {};
  const keys = results[1].status === "fulfilled" ? results[1].value : {};
  S.shell.sets = sets.sets || []; S.shell.keys = keys.keys || [];
  S.ctx = {version: 1, set: shellChosen(S.shell.sets, valid.set, sets.default), key: shellChosen(S.shell.keys, valid.key, keys.default)};
  S.shell.contextLoaded = true; shellRenderContext();
}
function shellRenderContext() {
  const currentSet = S.shell.sets.find(item => item.id === S.ctx.set);
  const currentKey = S.shell.keys.find(item => item.id === S.ctx.key);
  const missing = T(S.shell.contextLoaded ? "common.none" : "common.legacy.loading");
  const el = document.getElementById("global-context"); el.setAttribute("aria-label", T("context.a11y"));
  coreReplace(el, 
    h("div", {class: "context-field"}, h("span", {class: "context-label"}, T("context.documents.label")),
      h("strong", null, currentSet?.label || missing),
      h("button", {id: "context-change-set", class: "text-button", type: "button", onclick: shellOpenContext}, T("context.change_documents")),
      h("p", {class: "raw"}, currentSet?.id || "")),
    h("div", {class: "context-field"}, h("span", {class: "context-label"}, T("context.answer.label")),
      h("strong", null, ["gold", "silver"].includes(currentKey?.kind)
        ? term(currentKey.kind, currentKey.label) : currentKey?.label || missing),
      h("button", {id: "context-change-key", class: "text-button", type: "button", onclick: shellOpenContext}, T("context.change_answer")),
      h("p", null, T("context.answer_trust"))),
    h("div", {id: "context-model", class: "context-field", role: "status", "aria-live": "polite"}),
    S.shell.contextErrors.length ? h("div", {class: "context-errors"}, S.shell.contextErrors.map(loadFailure)) : null);
  shellRenderModels();
}
function shellModelState(model, data = S.shell.servers) {
  if (!model) return "readiness_unknown";
  if (model.reachable === true && model.match === true) return "state_ready";
  if (model.reachable === true && model.match === false) return "wrong_reply";
  if (model.where === "RNGD" && model.url_set !== false) {
    const diagnosis = data?.rngd?.diagnosis;
    if (diagnosis === "no_model" && data.rngd.ok === true) return "state_off";
    if (diagnosis === "loading") return "company_loading";
    if (diagnosis === "tunnel_closed") return "tunnel_closed";
  }
  if (model.error) return "query_failed";
  // 모델 목록 API가 빈 목록으로 응답한 경우만 꺼짐으로 확인한다.
  if (model.reachable === true && !model.model_served) return "state_off";
  return "readiness_unknown";
}
function shellModelStates(data = S.shell.servers) {
  const states = [...new Set((data?.models || []).map(model => shellModelState(model, data)))];
  return states.length ? states : ["readiness_unknown"];
}
function shellRenderModels() {
  const el = document.getElementById("context-model");
  if (!el) return;
  const error = S.shell.serverError;
  const models = (S.shell.servers?.models || []).filter(model => model.reachable && model.match);
  const label = model => model.label || model.model_label || model.model_expected || model.tag || T("context.model.default_name");
  const unavailable = error?.status === 503;
  const states = shellModelStates();
  const off = !error && !!S.shell.servers && states.every(state => state === "state_off");
  const details = states.filter(state => state !== "state_ready" && (off || state !== "state_off"));
  const summary = [models.length ? T("context.model.connected_count", {count: models.length, names: models.map(label).join(", ")}) : null,
    ...details.map(state => T(`context.model.${state}`))].filter(Boolean).join(" · ");
  const state = error ? T(unavailable ? "context.model.readiness_unknown" : "context.model.query_failed")
    : !S.shell.servers ? T("context.model.query_pending")
    : summary;
  el.classList.toggle("error", !!error && !unavailable);
  coreReplace(el, h("span", {class: "context-label"}, T("context.model.current_label", {model: T("context.model.default_name")})),
    h("strong", null, state),
    h("button", {class: "text-button", type: "button", onclick: () => go("s06").catch(fail)}, T("context.prepare_model")),
    off ? h("p", null, T("context.model.off_normal")) : null,
    h("p", null, T("context.model.saved_readable")),
    S.shell.serverAt ? h("p", {class: "muted"}, T("context.model.checked_at", {time: when(S.shell.serverAt)})) : null,
    error && !unavailable ? rawError(error.message) : null);
  shellMeasureHeader();
}
function shellMeasureHeader() {
  const context = document.getElementById("global-context");
  if (context) document.body.style.setProperty("--sticky-offset", `${Math.ceil(context.getBoundingClientRect().height || context.offsetHeight) + 16}px`);
}
async function shellPollServers() {
  if (S.shell.polling) return S.shell.polling;
  S.shell.polling = (async () => {
    const controller = new AbortController(); let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => { reject(new Error(T("servers.failed.no_reply"))); controller.abort(); }, SHELL_SERVER_TIMEOUT_MS);
    });
    try { S.shell.servers = await Promise.race([api("/api/servers", {signal: controller.signal}), timeout]); S.shell.serverError = null; }
    catch (error) { S.shell.servers = null; S.shell.serverError = error; }
    finally { clearTimeout(timer); S.shell.serverAt = new Date().toISOString(); shellRenderModels(); }
  })();
  try { await S.shell.polling; } finally { S.shell.polling = null; emit("servers_changed", {data: S.shell.servers, error: S.shell.serverError}); }
}
function shellScheduleServers() {
  clearTimeout(S.shell.timer);
  S.shell.timer = setTimeout(async () => {
    try { await shellPollServers(); } finally { shellScheduleServers(); }
  }, S.shell.route === "s06" ? 10000 : 60000);
}
function shellContextChoice(id, label, items, selected, answers = false) {
  const select = h("select", {id, disabled: !items.some(item => item.usable)},
    items.map(item => h("option", {value: item.id, disabled: !item.usable}, item.label,
      !item.usable && item.reason ? ` — ${item.reason}` : "")));
  select.value = selected || "";
  return h("div", null, h("label", {for: id}, label), select, h("p", {id: `${id}-note`, class: "muted"}));
}
function shellContextCandidates(items, answers = false) {
  return h("ul", {class: "context-candidates"}, items.map(item => h("li", null,
      h("strong", null, item.label), h("span", {class: "raw"}, ` (${item.id})`),
      h("p", null, item.reason || T("context.picker.usable")),
      !answers && item.counts ? shellContextCounts(item) : null,
      answers ? h("p", null, T("context.picker.modified", {time: item.updated_at || T("context.unavailable")})) : null,
      answers && item.fingerprint ? h("details", null, h("summary", null, T("common.record")),
        h("p", null, T("context.picker.fingerprint")), h("code", {class: "technical"}, item.fingerprint)) : null)));
}
function shellContextCounts(set) {
  return h("ul", null, [
    num(set?.counts?.dev) ? h("li", null, T("context.picker.dev_count", {count: set.counts.dev})) : null,
    num(set?.counts?.outside) ? h("li", null, T("context.picker.outside_count", {count: set.counts.outside})) : null,
    num(set?.counts?.eval_locked) ? h("li", null, T("jobs.batch.eval_locked", {count: set.counts.eval_locked})) : null]);
}
function shellContextComparison() {
  const set = S.shell.sets.find(item => item.id === document.getElementById("context-set").value);
  const key = S.shell.keys.find(item => item.id === document.getElementById("context-key").value);
  const currentSet = S.shell.sets.find(item => item.id === S.ctx.set), currentKey = S.shell.keys.find(item => item.id === S.ctx.key);
  const choice = item => h("div", null, item?.label || T("context.unavailable"), h("span", {class: "raw"}, item?.id || ""));
  const docs = value => value?.docs?.filter(doc => !doc.locked) || [];
  const coverage = (pack, answer) => Array.isArray(pack?.docs) && Array.isArray(answer?.docs)
    ? T("context.picker.coverage", {found: docs(pack).filter(doc => answer.docs.includes(doc.doc_id)).length, total: docs(pack).length})
    : T("context.unavailable");
  const origin = answer => T(answer?.kind === "silver" ? "context.picker.draft_origin" : answer?.kind === "gold" ? "context.picker.gold_origin" : "context.unavailable");
  const rows = [
    [T("context.documents.label"), h("div", null, choice(currentSet), shellContextCounts(currentSet)), h("div", null, choice(set), shellContextCounts(set))],
    [T("common.answer"), choice(currentKey), choice(key)],
    [T("context.picker.coverage_label"), coverage(currentSet, currentKey), coverage(set, key)],
    [T("source.fields.source"), origin(currentKey), origin(key)]];
  coreReplace(document.getElementById("context-comparison"), h("thead", null, h("tr", null,
    ["common.selection", "common.current", "common.candidate"].map(label => h("th", {scope: "col"}, T(label))))),
    h("tbody", null, rows.map(([label, current, candidate]) => h("tr", null, h("th", {scope: "row"}, label), h("td", null, current), h("td", null, candidate)))));
  document.getElementById("context-set-note").textContent = set?.reason || T(set?.usable ? "context.picker.usable" : "context.unavailable");
  document.getElementById("context-key-note").textContent = [key?.reason, T("context.picker.modified", {time: key?.updated_at || T("context.unavailable")})].filter(Boolean).join(" ");
  coreReplace(document.getElementById("context-doc-keys"), h("table", null,
    h("thead", null, h("tr", null, ["common.document", "common.answer", "source.fields.source"].map(label => h("th", {scope: "col"}, T(label))))),
    h("tbody", null, docs(set).map(doc => h("tr", null, h("th", {scope: "row", class: "technical"}, doc.doc_id),
      h("td", null, T(!Array.isArray(key?.docs) ? "context.unavailable" : key.docs.includes(doc.doc_id) ? "common.present" : "common.none")),
      h("td", null, key?.docs?.includes(doc.doc_id) ? origin(key) : T("common.none")))))));
}
function shellCloseContext() {
  document.getElementById("context-picker").close();
  S.shell.pickerFocus?.focus();
}
function shellOpenContext() {
  const dialog = document.getElementById("context-picker");
  S.shell.pickerFocus = document.activeElement;
  const apply = h("button", {id: "context-apply", type: "button", class: "primary", onclick: shellApplyContext}, T("context.picker.apply"));
  dialog.replaceChildren(h("h2", {id: "context-picker-title"}, T("context.picker.title")),
    h("div", {id: "context-picker-body"}, h("table", {id: "context-comparison"}),
    h("div", {class: "two-col"},
      shellContextChoice("context-set", T("context.documents.label"), S.shell.sets, S.ctx.set),
      shellContextChoice("context-key", T("context.answer.label"), S.shell.keys, S.ctx.key, true)),
    h("h3", null, T("context.picker.effects")),
    h("ul", null, ["effect_set", "effect_key", "no_model_call", "running_context"].map(key => h("li", null, T(`context.picker.${key}`)))),
    h("details", {id: "context-candidates"}, h("summary", null, T("context.picker.alternatives")),
      h("div", {class: "two-col"}, shellContextCandidates(S.shell.sets), shellContextCandidates(S.shell.keys, true))),
    h("details", {id: "context-doc-details"}, h("summary", null, T("context.picker.doc_keys")), h("div", {id: "context-doc-keys"}))),
    h("div", {class: "dialog-actions"}, apply,
      h("button", {id: "context-cancel", type: "button", onclick: shellCloseContext}, T("context.picker.cancel"))));
  const validate = () => {
    apply.disabled = !S.shell.sets.some(item => item.usable && item.id === document.getElementById("context-set").value)
      || !S.shell.keys.some(item => item.usable && item.id === document.getElementById("context-key").value);
    shellContextComparison();
  };
  document.getElementById("context-set").addEventListener("change", validate);
  document.getElementById("context-key").addEventListener("change", validate);
  validate(); dialog.showModal(); document.getElementById("context-set").focus();
}
function shellApplyContext() {
  const set = document.getElementById("context-set").value;
  const key = document.getElementById("context-key").value;
  if (!S.shell.sets.some(item => item.usable && item.id === set) || !S.shell.keys.some(item => item.usable && item.id === key)) return;
  const changed = set !== S.ctx.set || key !== S.ctx.key;
  S.ctx = {version: 1, set, key}; coreWrite("b_app.context", S.ctx);
  const returnId = S.shell.pickerFocus?.id;
  shellCloseContext(); shellRenderContext();
  if (returnId) document.getElementById(returnId)?.focus();
  if (changed) emit("context_changed", {...S.ctx});
}
async function start() {
  if (S.shell.started) return S.shell.ready;
  S.shell.started = true;
  shellRenderHeader(); shellRenderContext(); setupTip();
  window.addEventListener("resize", shellMeasureHeader);
  if (typeof ResizeObserver !== "undefined") {
    S.shell.headerObserver = new ResizeObserver(shellMeasureHeader);
    S.shell.headerObserver.observe(document.getElementById("global-context"));
  }
  emit("shell_started", {});
  window.addEventListener("hashchange", () => go(shellInitialRoute(location.hash)).catch(fail));
  document.getElementById("context-picker").addEventListener("cancel", event => { event.preventDefault(); shellCloseContext(); });
  S.shell.contextReady = shellLoadContext();
  const route = go(shellInitialRoute(location.hash));
  shellPollServers().then(shellScheduleServers).catch(fail);
  S.shell.ready = Promise.all([route, S.shell.contextReady]).catch(fail);
  return S.shell.ready;
}
