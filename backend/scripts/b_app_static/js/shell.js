"use strict";

const SHELL_SCREENS = {
  s01: {title: "nav.recent", loading: "errors.loading.fact", views: ["score-summary", "score-problems", "score-history", "score-docs", "score-grid", "score-rows", "score-rule", "score-gaps"]},
  s02: {title: "nav.source", loading: "errors.loading.fact", views: ["source-top", "source-values", "source-page", "source-selection"]},
  s03: {title: "nav.retest", views: ["jobs-try", "jobs-run", "jobs-connection", "jobs-result"]},
  s04: {title: "nav.compare", loading: "errors.loading.fact", views: ["compare-summary", "compare-conditions", "compare-items", "compare-values", "compare-rows", "compare-prompts"]},
  s05: {title: "nav.jobs", loading: "steps.jobs.loading", views: ["jobs-list", "jobs-detail"]},
  s06: {title: "nav.servers", views: ["servers-flow"]},
  s07: {title: "nav.help", views: ["help-topics", "help-glossary"]},
  s10: {title: "compare.table.open", parent: "s04", views: ["jobs-compare"]},
  s11: {title: "nav.swap", views: ["swap-view"]}
};
// 옛 주소는 새 자리로 잇는다. 여러 문서 시험은 다시 시험 첫 단계의 갈래가 됐다 (ADR-039).
const SHELL_MOVED = {s09: {id: "s03", args: {trialBranch: "batch"}}};
const SHELL_NAV_GROUPS = [
  {title: "nav.group_flow", screens: ["s01", "s02", "s03", "s04"]},
  {title: "nav.group_other", screens: ["s06", "s05", "s07"]}
];
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
  return Object.hasOwn(SHELL_SCREENS, id) || Object.hasOwn(SHELL_MOVED, id) ? id : "s01";
}
// 화면마다 읽는 것이 다르다. 실행 결과를 읽지 않는 화면에 그 말을 쓰지 않는다.
function shellLoadingText(id) { return T(SHELL_SCREENS[id]?.loading || "common.legacy.loading"); }
function shellConclusion(id, text) {
  document.getElementById(`title-${id}`).textContent = text;
}
async function go(id, args = {}) {
  id = shellInitialRoute(id.startsWith("#") ? id : `#${id}`);
  const moved = SHELL_MOVED[id];
  if (moved) { id = moved.id; args = {...args, ...moved.args}; }
  S.focus = {...S.focus, ...args}; S.shell.route = id;
  status(shellLoadingText(id));
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
        if (!el.textContent.trim()) el.replaceChildren(h("p", {role: "status"}, shellLoadingText(id)));
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
function shellNavButton(id, current = false) {
  return h("button", {type: "button", "data-screen": id, onclick: () => {
    go(id).catch(fail); document.getElementById(`title-${id}`).focus();
  }}, T(SHELL_SCREENS[id].title),
  current ? h("span", {class: "nav-current", hidden: true}, T("nav.current")) : null);
}
function shellRenderHeader() {
  document.getElementById("app-heading").textContent = T("nav.app_name");
  coreReplace(document.getElementById("app-bar-side"),
    h("button", {id: "guide-open", type: "button", onclick: () => emit("guide_open", {})}, T("nav.open_guide")));
  const nav = document.getElementById("main-nav"); nav.setAttribute("aria-label", T("nav.a11y"));
  const groups = SHELL_NAV_GROUPS.map(group => h("div", {class: "nav-group", role: "group", "aria-label": T(group.title)},
    h("p", {class: "nav-group-title"}, T(group.title)),
    group.screens.map(id => h("div", null, shellNavButton(id, true),
      Object.entries(SHELL_SCREENS).filter(([, screen]) => screen.parent === id).map(([child]) =>
        h("div", {class: "subnav", "data-parent": id, hidden: true}, shellNavButton(child)))))));
  nav.replaceChildren(...groups, h("p", {class: "sidebar-note"}, T("nav.purpose")),
    h("p", {class: "sidebar-note"}, T("common.document_definition")),
    h("p", {class: "sidebar-note"}, T("common.local_only"), h("br"), T("common.tool_kind")));
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
const shellTipLines = (...lines) => lines.filter(Boolean).join("\n");
function shellRenderContext() {
  const currentSet = S.shell.sets.find(item => item.id === S.ctx.set);
  const currentKey = S.shell.keys.find(item => item.id === S.ctx.key);
  const missing = T(S.shell.contextLoaded ? "common.none" : "common.legacy.loading");
  document.getElementById("global-context").setAttribute("aria-label", T("context.a11y"));
  // 막대에는 고른 값만 둔다. 원래 폴더 이름과 정답의 신뢰 범위는 말풍선과 선택 창에서 본다.
  coreReplace(document.getElementById("context-fields"),
    h("div", {class: "context-field context-links"},
      h("button", {id: "context-change-set", class: "context-chip", type: "button", onclick: shellOpenContext,
        "data-tip": shellTipLines(T("context.documents.label"), currentSet?.label, currentSet?.id, shellScoreTip(currentSet, currentKey), T("context.change_documents"))},
      h("small", null, T("context.documents.short")), h("b", null, currentSet?.label || missing), shellScoreChip(currentSet, currentKey)),
      h("button", {id: "context-swap", class: "text-button", type: "button", onclick: () => go("s11", {swapView: "start"}).catch(fail)}, T("nav.swap"))),
    h("div", {class: "context-field"},
      h("button", {id: "context-change-key", class: "context-chip", type: "button", onclick: shellOpenContext,
        "data-tip": shellTipLines(T("context.answer.label"), currentKey?.label, UI.glossary?.[currentKey?.kind]?.meaning, T("context.answer_trust"), T("context.change_answer"))},
      h("small", null, T("context.answer.short")), h("b", null, currentKey?.label || missing)),
      h("div", {id: "context-answer-note"})),
    h("div", {id: "context-model", class: "context-field", role: "status", "aria-live": "polite"}));
  coreReplace(document.getElementById("context-errors"), S.shell.contextErrors.map(loadFailure));
  shellRenderModels();
  emit("context_rendered", {});
}
// 고른 문서 묶음에 고른 정답이 있는 문서 수. 잠긴 문서는 세지 않는다. 목록을 모르면 null이다.
function shellScoreCount(set, key) {
  if (!Array.isArray(set?.docs) || !Array.isArray(key?.docs)) return null;
  return set.docs.filter(doc => !doc.locked && key.docs.includes(doc.doc_id)).length;
}
function shellScoreChip(set, key) {
  const count = shellScoreCount(set, key);
  if (count === null) return null;
  return h("span", {id: "context-score-chip", class: `swap-chip ${count ? "yes" : "no"}`},
    T(count ? "swap.context.score_docs_short" : "swap.context.no_score_short", {count}));
}
// 막대에 다 쓰지 못하는 뜻은 말풍선에 쓴다.
function shellScoreTip(set, key) {
  const count = shellScoreCount(set, key);
  if (count === null) return null;
  return T(count ? "swap.context.score_docs" : "swap.context.no_score", {count});
}
// 빌린 서버의 요금과 자동 삭제. 닫는 단추는 AI 켜기와 비용 화면에만 둔다 (11/2 사용자 결정).
function shellRentedNote(data) {
  const session = data?.session, pod = (data?.pods || []).find(item => item.session);
  if (!session || !pod) return null;
  const where = T("context.model.rented_close_where");
  if (!session.ready) return [num(pod.minutes) ? T("context.model.rented_elapsed", {minutes: Math.round(pod.minutes)}) : null, where].filter(Boolean).join(" ");
  return [[num(pod.cost_per_hr) ? T("context.model.rented_hourly", {cost: pod.cost_per_hr}) : null,
    [num(session.idle_minutes) ? T("context.model.rented_auto_close", {idle: session.idle_minutes}) : null,
      num(pod.auto_delete_min) ? T("context.model.rented_auto_left", {minutes: pod.auto_delete_min}) : null].filter(Boolean).join(" ")]
    .filter(Boolean).join(" · "), where].filter(Boolean).join(" ");
}
// 우리 서버가 켜져 있지 않다고 확인한 경우만 참이다. 목록을 못 읽으면 요금이 없다고 단정하지 않는다.
function shellNoOwnServer(data) {
  return !!data && !data.runpod_error && !(data.pods || []).some(pod => pod.owned && pod.status === "RUNNING");
}
function shellOffNotes(data) {
  const closed = data?.last_auto_close;
  return [T("context.model.off_normal"), shellNoOwnServer(data) ? T("context.model.off_no_cost") : null,
    closed ? T(`context.model.auto_closed_${closed.kind}`, {limit: closed.limit_min}) : null,
    closed && num(closed.minutes) && num(closed.cost) ? T("context.model.auto_closed_cost", {minutes: closed.minutes, cost: closed.cost}) : null]
    .filter(Boolean).join(" ");
}
// 막대의 요금 글. 지금 쓰는 서버만 읽는다. 다른 사람 서버와 꺼진 서버의 금액은 합치지 않는다.
function shellCostText(data, error) {
  if (!data && !error) return null;
  const pod = (data?.pods || []).find(item => item.session);
  if (!pod) return T(shellNoOwnServer(data) ? "context.model.chip_no_cost" : "context.model.chip_cost_unknown");
  const parts = [num(pod.cost_per_hr) ? T("context.model.rented_hourly", {cost: pod.cost_per_hr.toFixed(2)}) : null,
    num(pod.cost_est) ? T("context.model.rented_so_far", {cost: pod.cost_est.toFixed(2)}) : null].filter(Boolean);
  return parts.length ? parts.join(" · ") : T("context.model.chip_cost_unknown");
}
function shellModelState(model, data = S.shell.servers) {
  if (!model) return "readiness_unknown";
  if (model.reachable === true && model.match === true) return "state_ready";
  if (model.reachable === true && model.match === false) return "wrong_reply";
  // 주소가 없으면 물어볼 서버가 없는 것이다. 예: 빌린 서버를 아직 켜지 않은 상태.
  if (model.url_set === false) return "state_off";
  if (model.where === "RNGD") {
    const diagnosis = data?.rngd?.diagnosis;
    if (diagnosis === "no_model" && data.rngd.ok === true) return "state_off";
    if (diagnosis === "loading") return "company_loading";
    if (diagnosis === "tunnel_closed") return "tunnel_closed";
  }
  // RunPod 프록시는 모델이 뜨기 전까지 404와 502를 돌려준다. 켜는 중인 우리 Pod의 이 응답은 실패가 아니다.
  if (model.where === "RunPod" && /^HTTP (404|502)$/.test(model.error || "") && data?.session && !data.session.ready) return "rented_loading";
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
  const label = model => model.label || model.model_label || UI.context.models?.[model.tag] || model.model_expected || model.tag || T("context.model.default_name");
  const unavailable = error?.status === 503;
  const states = shellModelStates();
  const off = !error && !!S.shell.servers && states.every(state => state === "state_off");
  // 연결된 모델이 있으면 오해만 주는 상태는 뺀다. 예: 같은 Pod를 바라보는 다른 태그의 "다른 모델 응답". 실패와 켜는 중은 남긴다.
  const details = states.filter(state => state !== "state_ready" && (off || state !== "state_off")
    && !(models.length && ["wrong_reply", "readiness_unknown"].includes(state)));
  const names = models.map(label).join(", ");
  const detailText = details.map(state => T(`context.model.${state}`)).join(" · ");
  const connected = !error && !!S.shell.servers && models.length > 0;
  const state = error ? T(unavailable ? "context.model.readiness_unknown" : "context.model.query_failed")
    : !S.shell.servers ? T("context.model.query_pending")
    : connected ? T("context.model.chip_on") : detailText;
  const onSession = (S.shell.servers?.pods || []).some(item => item.session);
  const cost = shellCostText(S.shell.servers, error);
  el.classList.toggle("error", !!error && !unavailable);
  coreReplace(el, h("button", {id: "context-model-open", class: `context-chip context-ai${connected ? " on" : ""}${onSession ? " billing" : ""}`, type: "button",
    onclick: () => go("s06").catch(fail),
    "data-tip": shellTipLines(connected ? [T("context.model.connected_count", {count: models.length, names}), detailText].filter(Boolean).join(" · ") : state,
      onSession ? T("steps.server.cost_basis") : null,
      off ? shellOffNotes(S.shell.servers) : null,
      !error ? shellRentedNote(S.shell.servers) : null,
      T("context.model.saved_readable"),
      S.shell.serverAt ? T("context.model.checked_at", {time: when(S.shell.serverAt)}) : null,
      error && !unavailable ? error.message : null,
      T("context.prepare_model"))},
  h("span", {class: "context-dot", "aria-hidden": "true"}),
  h("b", null, state),
  connected ? h("small", {class: "context-ai-name"}, [names, detailText].filter(Boolean).join(" · ")) : null,
  cost ? h("small", null, cost) : null));
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
      answers ? h("p", null, T("context.picker.modified", {time: item.updated_at ? when(item.updated_at) : T("context.unavailable")})) : null,
      answers && item.fingerprint ? h("details", null, h("summary", null, T("common.record")),
        h("p", null, T("context.picker.fingerprint")), h("code", {class: "technical"}, item.fingerprint)) : null)));
}
function shellContextCounts(set) {
  return h("ul", null, [
    num(set?.counts?.dev) ? h("li", null, T("context.picker.dev_count", {count: set.counts.dev})) : null,
    num(set?.counts?.outside) ? h("li", null, T("context.picker.outside_count", {count: set.counts.outside})) : null,
    num(set?.counts?.eval_locked) ? h("li", null, T("jobs.batch.eval_locked", {count: set.counts.eval_locked})) : null]);
}
async function shellContextResults(set, key) {
  const list = await api(`/api/runs?${new URLSearchParams({key})}`);
  if (list.key?.id && list.key.id !== key) throw new Error(T("guide.defaults.mismatch"));
  const runs = (list.runs || []).filter(run => !run.error && run.set?.id === set
    && !["silver", "eval", "models"].includes(run.run_kind)
    && (!run.key?.id || run.key.id === key));
  return {runs, current: runs.find(run => run.name === list.current) || runs.at(-1)};
}
function shellContextResultNotice(state) {
  if (num(state?.count)) return T(state.count ? "context.picker.results_found" : "context.picker.results_empty", {count: state.count});
  if (state?.error) return friendlyError({message: T("context.picker.results_failed"),
    fix: T("context.picker.results_failed_todo"), raw: state.error.message});
  return T("guide.ready.states.checking");
}
async function shellPreviewContext() {
  const node = document.getElementById("context-result-effect"), dialog = document.getElementById("context-picker");
  const set = document.getElementById("context-set").value, key = document.getElementById("context-key").value;
  const state = S.shell.pickerPreview = {};
  if (!S.shell.sets.some(item => item.usable && item.id === set)
    || !S.shell.keys.some(item => item.usable && item.id === key)) {
    coreReplace(node, T("context.unavailable")); return;
  }
  coreReplace(node, shellContextResultNotice(state));
  try {state.count = (await shellContextResults(set, key)).runs.length;}
  catch (error) {state.error = error;}
  if (S.shell.pickerPreview === state && dialog.open) coreReplace(node, shellContextResultNotice(state));
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
  document.getElementById("context-key-note").textContent = [key?.reason, T("context.picker.modified", {time: key?.updated_at ? when(key.updated_at) : T("context.unavailable")})].filter(Boolean).join(" ");
  coreReplace(document.getElementById("context-doc-keys"), h("table", null,
    h("thead", null, h("tr", null, ["common.document", "common.answer", "source.fields.source"].map(label => h("th", {scope: "col"}, T(label))))),
    h("tbody", null, docs(set).map(doc => h("tr", null, h("th", {scope: "row", class: "technical"}, doc.doc_id),
      h("td", null, T(!Array.isArray(key?.docs) ? "context.unavailable" : key.docs.includes(doc.doc_id) ? "common.present" : "common.none")),
      h("td", null, key?.docs?.includes(doc.doc_id) ? origin(key) : T("common.none")))))));
}
function shellCloseContext() {
  S.shell.pickerPreview = null;
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
    h("div", {id: "context-result-effect", role: "status", "aria-live": "polite"}),
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
    return shellPreviewContext();
  };
  document.getElementById("context-set").addEventListener("change", validate);
  document.getElementById("context-key").addEventListener("change", validate);
  validate(); dialog.showModal(); document.getElementById("context-set").focus();
}
function shellApplyContext(choice) {
  const fromGuide = typeof choice?.set === "string" && typeof choice?.key === "string";
  const set = fromGuide ? choice.set : document.getElementById("context-set").value;
  const key = fromGuide ? choice.key : document.getElementById("context-key").value;
  if (!S.shell.sets.some(item => item.usable && item.id === set) || !S.shell.keys.some(item => item.usable && item.id === key)) return;
  const changed = set !== S.ctx.set || key !== S.ctx.key;
  S.ctx = {version: 1, set, key}; coreWrite("b_app.context", S.ctx);
  const returnId = S.shell.pickerFocus?.id;
  if (!fromGuide) shellCloseContext();
  shellRenderContext();
  if (!fromGuide && returnId) document.getElementById(returnId)?.focus();
  if (changed) emit("context_changed", {...S.ctx});
  return true;
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
  emit("shell_started", {hash: location.hash});
  window.addEventListener("hashchange", () => go(shellInitialRoute(location.hash)).catch(fail));
  document.getElementById("context-picker").addEventListener("cancel", event => { event.preventDefault(); shellCloseContext(); });
  S.shell.contextReady = shellLoadContext();
  const route = go(shellInitialRoute(location.hash));
  shellPollServers().then(shellScheduleServers).catch(fail);
  S.shell.ready = Promise.all([route, S.shell.contextReady]).catch(fail);
  return S.shell.ready;
}
