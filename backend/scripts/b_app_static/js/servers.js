"use strict";

// 상태 자료와 조회 타이머는 S.shell만 소유한다. 여기는 화면 조작 상태만 둔다.
// kind는 사용자가 고른 서버(rented, company)이고 step은 사용자가 옮긴 단계(choose, start)다. 나머지 단계는 서버 상태에서 정한다.
S.servers = {busy: null, proposal: null, error: null, result: null, reload: null,
  lock: null, choice: null, trigger: null, dialogReady: false, compacts: new Map(), kind: null, step: null};
const SERVERS_KINDS = ["rented", "company"];
const SERVERS_WHERE = {rented: "RunPod", company: "RNGD"};
const SERVERS_CONFIRM = {pod_create: "create", pod_delete: "delete", rngd_up: "load", rngd_down: "unload",
  tunnel_open: "tunnel_open", tunnel_close: "tunnel_close"};

function serversText(value) {
  // API가 가린 원문도 설정값·접속 주소·SSH 인자는 화면에 다시 싣지 않는다.
  return String(value ?? "").replace(/\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|BASE_URL|SSH)\s*=[^\n]*/g, T("servers.redacted"))
    .replace(/\bhttps?:[/][/][^\s)]+/gi, T("servers.redacted"))
    .replace(/\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?/g, T("servers.redacted"))
    .replace(/(?:ssh\s|\s-i\s|\s--api-key[=\s])[^\n]*/g, T("servers.redacted"))
    .replace(/\b[\w.-]+@[\w.-]+/g, T("servers.redacted"));
}
function serversFriendly(info) {
  return info ? friendlyError({message: serversText(info.message || info.fact),
    fix: serversText(info.fix || info.todo), raw: serversText(info.raw)}) : null;
}
function serversData() { return S.shell.serverError ? null : S.shell.servers; }
function serversModel(model) {
  const tag = typeof model === "object" ? model?.tag : model;
  return (serversData()?.models || []).find(item => item.tag === tag || item.model_expected === tag) || null;
}
function serversReady(model) { return model?.reachable === true && model?.match === true; }
function serversLabel(model) { return serversText(model?.label || model?.model_label || UI.context.models?.[model?.tag]
  || model?.model_expected || model?.tag || T("context.model.default_name")); }
function serversState(model) {
  if (S.shell.serverError) return S.shell.serverError.status === 503 ? "readiness_unknown" : "query_failed";
  return serversReady(model) ? "connected" : shellModelState(model, serversData());
}
function serversBadge(model) {
  const state = serversState(model);
  return h("strong", {class: `server-state ${state === "connected" ? "server-ready" : "muted"}`},
    T(state === "connected" ? "servers.models.connected" : `context.model.${state}`));
}
// quiet: 다른 AI가 이미 응답 중이면 예상된 꺼짐의 할 일을 보이지 않는다.
function serversModelNote(model, quiet = false) {
  if (!model?.friendly) return null;
  const diagnosis = serversData()?.rngd?.diagnosis;
  if (model.where === "RNGD" && ["no_model", "tunnel_closed", "loading"].includes(diagnosis)) {
    const info = model.friendly;
    return h("div", {class: "server-notice"}, h("strong", null, serversText(info.message)),
      quiet ? null : h("p", null, serversText(info.fix)), info.raw ? rawError(serversText(info.raw)) : null);
  }
  return serversFriendly(model.friendly);
}
function serversDuration(seconds) {
  if (!num(seconds) || seconds < 0) return T("servers.rented.unknown");
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? T("servers.time.hours_minutes", {hours: Math.floor(minutes / 60), minutes: minutes % 60})
    : T("servers.time.minutes", {minutes});
}
function serversElapsed(since) {
  const time = typeof since === "string" && since ? Date.parse(since) : NaN;
  return Number.isFinite(time) ? Math.max(0, (Date.now() - time) / 1000) : null;
}
function serversMoney(value, hourly = false) {
  return num(value) && value >= 0 ? hourly ? T("servers.rented.hourly", {cost: value.toFixed(2)}) : `$${value.toFixed(2)}` : T("servers.rented.unknown");
}
function serversCreateCost(proposal) {
  // 현재 API는 요금을 summary의 한 문장으로만 준다. 한 개의 완전한 요금만 읽는다.
  const prefix = UI.servers.confirm.create.action.split("{cost_per_hour}")[0];
  const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = [...String(proposal?.summary || "").matchAll(new RegExp(`${escaped}([0-9]+(?:\\.[0-9]+)?)\\.(?=\\s|$)`, "g"))];
  return matches.length === 1 && Number.isFinite(Number(matches[0][1])) ? matches[0][1] : null;
}
function serversReason(action, confirming = false) {
  const data = serversData();
  if (!data) return T("servers.status.unavailable");
  if (S.servers.busy) return T("servers.status.busy");
  if (S.servers.proposal && !confirming) return T("servers.confirm.once");
  if ((data.locked || S.servers.lock) && action !== "tunnel_open") return serversText(S.servers.lock?.lock_reason || data.lock_reason || T("servers.controls.busy"));
  if (action === "rngd_up" && data.rngd?.diagnosis === "loading") return T("servers.connection.loading_locked");
  if (action === "rngd_up" && data.rngd?.models?.length) return T("servers.connection.replace_locked");
  return data.can?.[action] === true ? "" : serversText(data.why?.[action] || T("servers.status.unavailable"));
}
function serversActionId(action, suffix) { return `servers-${action}${suffix ? `-${encodeURIComponent(suffix)}` : ""}`; }
function serversAction(action, params, label, suffix = "", primary = false) {
  const reason = serversReason(action), id = serversActionId(action, suffix);
  return h("div", {class: "server-action"},
    h("button", {id, type: "button", class: primary ? "primary" : null, "data-server-action": action,
      disabled: !!reason, "aria-describedby": reason ? `${id}-note` : null,
      onclick: () => serversPropose(action, params, id)}, label),
    reason ? h("p", {id: `${id}-note`, class: "muted"}, reason) : null);
}
function serversButton(id, key, fn, disabled = false) {
  return h("button", {id, type: "button", disabled, onclick: fn}, T(key));
}
function serversProblem(error, action = null) {
  if (error?.body?.friendly) return serversFriendly(error.body.friendly);
  // 상태를 읽지 못한 것은 서버를 바꾸다 실패한 것이 아니다.
  const prefix = error?.status === 503 ? "servers.disabled" : error?.status === 409 ? "servers.busy"
    : error?.status === 410 ? "servers.confirm.expired" : action === "pod_create" ? "servers.create_unknown"
    : action === "status" ? "servers.failed" : "servers.status.failure";
  const message = T(`${prefix}.${["servers.busy", "servers.create_unknown"].includes(prefix) ? "title" : "fact"}`);
  const fix = prefix === "servers.busy" ? T("servers.controls.busy") : T(`${prefix}.todo`);
  return serversFriendly({message, fix, raw: error?.body?.error || error?.message || ""});
}
function serversLockNote() {
  const data = serversData();
  if (!data?.locked && !S.servers.lock) return null;
  const jobs = S.servers.lock?.running || data.running_jobs || [];
  return h("div", {class: "server-notice", role: "status"}, h("strong", null, T("servers.busy.title")),
    h("p", null, serversText(S.servers.lock?.lock_reason || data.lock_reason)),
    h("ul", null, jobs.map(job => h("li", {class: "technical"}, serversText(job.label || job.name || job.id || job.kind)))),
    h("p", null, T("servers.busy.allow_tunnel")), serversButton("servers-open-jobs", "servers.busy.open_job", () => go("s05")));
}
function serversDiagnosis() {
  const data = serversData(), rngd = data?.rngd || {}, key = rngd.diagnosis;
  if (["ok", "no_model", "tunnel_closed"].includes(key)) {
    const prefix = `servers.diagnosis.${key === "ok" ? "ready" : key}`;
    return h("div", {class: "server-notice"}, h("strong", null, T(`${prefix}.fact`)), h("p", null, T(`${prefix}.todo`)));
  }
  if (key === "loading") {
    const elapsed = serversElapsed(rngd.loading_since);
    return h("div", {class: "server-notice", role: "status"},
      h("strong", null, elapsed === null ? T("servers.diagnosis.loading.unknown") : T("servers.diagnosis.loading.elapsed", {minutes: Math.floor(elapsed / 60)})),
      h("p", null, T("servers.diagnosis.loading.todo")), elapsed > 1500 ? h("p", null, T("servers.diagnosis.loading.late", {minutes: 25})) : null);
  }
  return serversKindProblem("company") || h("p", null, T("servers.connection.unknown"));
}
function serversReturn() { return go("s03"); }
// ── 단계 흐름: 서버 고르기 → 켜기 → 준비 기다리기 → 쓰고 나서 끄기 (ADR-039) ──
function serversTargetTag() { return serversModel(S.focus.model)?.tag ?? S.focus.model ?? null; }
// 켤 수 있는 서버는 API 값으로 정한다. 회사 서버는 rngd_choices, 빌린 서버는 create_quote다.
function serversCanStart(kind, tag) {
  const data = serversData();
  return kind === "company" ? !!data?.rngd_choices?.some(choice => choice.tag === tag) : data?.create_quote?.tag === tag;
}
// off는 꺼짐, wait는 켜는 중, stop은 응답 중이라 끄는 일만 남은 상태다. 고른 AI가 있으면 다른 AI의 응답은 준비 완료가 아니다.
function serversKindState(kind) {
  const data = serversData();
  if (!data) return "off";
  const target = serversModel(S.focus.model), where = SERVERS_WHERE[kind];
  const replies = target?.where === where ? serversReady(target)
    : (data.models || []).some(model => model.where === where && serversReady(model));
  if (replies) return "stop";
  return (kind === "rented" ? data.session : data.rngd?.diagnosis === "loading") ? "wait" : "off";
}
function serversKind() {
  if (S.servers.kind) return S.servers.kind;
  const live = kind => serversKindState(kind) !== "off";
  if (S.focus.model) {
    const target = serversModel(S.focus.model);
    return SERVERS_KINDS.find(kind => target?.where === SERVERS_WHERE[kind] && live(kind)) || null;
  }
  return SERVERS_KINDS.find(kind => serversKindState(kind) === "stop") || SERVERS_KINDS.find(live) || null;
}
function serversStep() {
  if (!serversData() || S.servers.step === "choose") return "choose";
  const kind = serversKind(), state = kind ? serversKindState(kind) : "off";
  if (state !== "off") return state;
  return kind && S.servers.step === "start" ? "start" : "choose";
}
function serversKindModel(kind) {
  const data = serversData(), target = serversModel(S.focus.model), where = SERVERS_WHERE[kind];
  if (target?.where === where) return target;
  const mine = (data?.models || []).filter(model => model.where === where);
  return mine.find(serversReady) || mine.find(model => kind === "rented" ? model.tag === data?.session?.tag
    : model.model_expected === data?.rngd?.models?.[0]?.model) || mine[0] || null;
}
function serversSessionPod() { return (serversData()?.pods || []).find(pod => pod.session) || null; }
function serversCompanyStart() {
  const data = serversData(), rngd = data?.rngd || {}, tunnel = rngd.tunnel || {}, choices = data?.rngd_choices || [];
  if (!choices.some(choice => choice.tag === S.servers.choice)) S.servers.choice = choices.find(choice => choice.tag === S.focus.model)?.tag || choices[0]?.tag || null;
  return {choices, choice: choices.find(item => item.tag === S.servers.choice),
    needsTunnel: tunnel.open === false && tunnel.port != null, loaded: rngd.models || []};
}
function serversStepList(current) {
  const order = ["choose", "start", "wait", "stop"], at = order.indexOf(current);
  const kind = serversKind(), state = kind ? serversKindState(kind) : "off";
  const seconds = serversData()?.session?.ready_seconds;
  const summary = {choose: kind ? T(`steps.server.${kind}_name`) : "", start: kind ? T(`steps.server.start_done_${kind}`) : "",
    wait: kind === "rented" && num(seconds) ? T("steps.server.prepared_short", {elapsed: serversDuration(seconds)}) : ""};
  return order.map((id, index) => ({id, label: T(`steps.server.${id}`), done: index < at, summary: summary[id], buttonId: `servers-step-${id}`,
    reachable: id === "choose" || (id === "start" ? !!S.servers.kind && state === "off" : state === id)}));
}
// 단계 이동은 표시만 바꾼다. 서버에 아무것도 보내지 않는다.
function serversMove(step, kind) {
  S.servers.step = step; S.servers.kind = kind;
  serversRender(); document.getElementById("title-s06").focus({preventScroll: true});
}
function serversGo(id) {
  serversMove(["choose", "start"].includes(id) ? id : null, id === "choose" ? null : S.servers.kind);
}
function serversChoose(kind) {
  S.servers.error = null; S.servers.result = null; S.servers.reload = null;
  serversMove("start", kind);
}
function serversChooseSay() {
  if (!S.focus.model) return T("servers.choice.recommendation");
  const tag = serversTargetTag(), fits = SERVERS_KINDS.filter(kind => serversCanStart(kind, tag));
  return [T("steps.server.choose_target", {model: serversLabel(serversModel(tag) || {tag})}),
    fits.length === 1 ? T("steps.server.only_on", {server: T(`steps.server.${fits[0]}_name`)}) : fits.length ? null : T("steps.server.no_server")]
    .filter(Boolean).join(" ");
}
function serversHead(step, kind) {
  if (S.shell.serverError) return [T("servers.failed.title"), T("servers.failed.stale")];
  if (!serversData()) return [T("servers.checking.title"), T("servers.checking.wait")];
  if (step === "choose") return [T("steps.server.choose_title"), serversChooseSay()];
  if (step === "start" && kind === "rented") return [T("steps.server.start_rented_title"), T("steps.server.start_rented_say")];
  if (step === "start") {
    const company = serversCompanyStart();
    return [T(company.needsTunnel ? "steps.server.start_company_tunnel_title" : company.loaded.length ? "steps.server.start_company_other_title" : "steps.server.start_company_pick_title"), T("steps.server.start_company_say")];
  }
  const model = serversLabel(serversKindModel(kind));
  if (step === "wait") return [T("steps.server.wait_title", {model}), T("steps.server.wait_say")];
  return [T("servers.ready.title", {model}), T(kind === "rented" ? "steps.server.stop_say_rented" : "servers.ready.company_cost")];
}
function serversFacts(rows) {
  return h("dl", {class: "server-facts"}, rows.filter(Boolean).map(([label, value]) => [h("dt", null, label), h("dd", null, value)]));
}
function serversStat(label, value) {
  return h("div", {class: "server-stat"}, h("small", null, label), h("b", null, value));
}
function serversProgress(rows) {
  return h("ol", {class: "server-progress"}, rows.map(([state, text]) =>
    // 숫자를 쓰지 않는다. 위쪽 단계 표시와 겹쳐 보인다.
    h("li", {class: state}, h("span", {class: "step-no"}, state === "done" ? "✓" : ""), h("span", null, text))));
}
function serversStepAction(action, params, label, suffix = "") {
  const reason = serversReason(action), id = serversActionId(action, suffix);
  return {label, disabled: !!reason, reason, onClick: () => serversPropose(action, params, id), attrs: {id, "data-server-action": action}};
}
// 단계 안에서는 사실과 할 일만 보인다. 원래 오류는 서랍의 오류 기록에 모은다.
function serversFlat(node) {
  node?.querySelectorAll("details").forEach(folded => folded.remove());
  return node;
}
function serversQuoteModel(quote) { return serversLabel(serversModel(quote.tag) || {tag: quote.tag}); }
function serversKindProblem(kind) {
  const data = serversData();
  if (kind === "rented") return data.friendly ? serversFlat(serversFriendly(data.friendly))
    : data.runpod_error ? serversFlat(serversFriendly({message: T("servers.account_failed.title"), fix: T("servers.account_failed.todo")})) : null;
  if (["ok", "no_model", "tunnel_closed", "loading"].includes(data.rngd?.diagnosis)) return null;
  const info = (data.models || []).find(model => model.where === "RNGD" && model.friendly)?.friendly || data.rngd?.friendly;
  return info ? serversFlat(serversFriendly(info)) : null;
}
function serversCard(kind, primary) {
  const data = serversData(), rented = kind === "rented", quote = data.create_quote;
  const fit = S.focus.model ? serversCanStart(kind, serversTargetTag()) : null;
  const models = rented ? (quote ? [serversQuoteModel(quote)] : []) : (data.rngd_choices || []).map(choice => serversText(choice.label || choice.model));
  return h("section", {class: `server-card step-card${fit ? " fit" : ""}`, "data-server-kind": kind},
    h("h2", null, term(rented ? "runpod" : "rngd", T(`steps.server.${kind}_name`))),
    fit === null ? null : h("p", {class: fit ? "server-fit" : "muted"}, T(`steps.server.${fit ? "matches" : "mismatch"}`)),
    serversFacts([
      [T("steps.server.fact_models"), models.join(", ") || T("servers.rented.unknown")],
      [T("steps.server.fact_cost"), !rented ? T("steps.server.company_cost")
        : num(quote?.cost_per_hr) ? T("context.model.rented_hourly", {cost: quote.cost_per_hr.toFixed(2)}) : T("servers.rented.unknown")],
      [T("servers.compare.wait"), T(`servers.compare.${kind}.wait`)],
      [T("servers.compare.limits"), T(rented ? "servers.compare.rented.cleanup" : "servers.compare.company.limit")]]),
    rented ? null : h("p", {class: "muted"}, T("servers.compare.company.cost_meaning")),
    serversKindProblem(kind),
    h("button", {id: `servers-use-${kind}`, type: "button", class: primary ? "primary" : null, onclick: () => serversChoose(kind)}, T(fit === false ? "steps.server.use_other_ai" : `steps.server.use_${kind}`)));
}
function serversStageChoose() {
  if (!serversData()) return null;
  // 고른 AI가 없으면 추가 임대료 없는 회사 서버를 권한다. 고른 AI를 켤 서버가 없으면 아무것도 권하지 않는다.
  const fit = S.focus.model ? SERVERS_KINDS.find(kind => serversCanStart(kind, serversTargetTag())) : "company";
  return h("div", {class: "server-cards"}, (fit === "rented" ? ["rented", "company"] : ["company", "rented"]).map(kind => serversCard(kind, kind === fit)));
}
function serversStageStartRented() {
  const data = serversData(), quote = data.create_quote;
  return [h("div", {class: "server-stats"},
    serversStat(T("steps.server.stat_hourly"), serversMoney(quote?.cost_per_hr)),
    num(quote?.max_cost) ? serversStat(T("steps.server.stat_forgot", {hours: quote.max_hours}), serversMoney(quote.max_cost)) : null),
  h("div", {class: "step-card"}, serversFacts([
    [T("steps.server.fact_target_model"), quote ? serversQuoteModel(quote) : T("servers.rented.unknown")],
    [T("steps.server.fact_auto_delete"), T("servers.rented.scheduler")],
    [T("steps.server.fact_storage"), [num(data.volumes) ? T("servers.rented.volumes", {count: data.volumes}) : T("servers.rented.volume_unknown"), " ", T("servers.rented.storage_cost")]],
    quote ? [T("steps.server.fact_basis"), [serversText(quote.basis), " ", T("steps.server.forgot_note", {hours: quote.max_hours})]] : null,
    S.focus.doc && S.focus.section ? [T("steps.server.fact_return"), T("steps.server.return_value", {doc: serversText(S.focus.doc), section: S.focus.section})] : null]))];
}
function serversStageStartCompany() {
  const {choices, needsTunnel, loaded} = serversCompanyStart();
  const select = h("select", {id: "servers-choice", disabled: !choices.length, onchange: event => {
    S.servers.choice = event.target.value; serversRender();
  }}, choices.map(item => h("option", {value: item.tag}, T("servers.connection.choice", {model: serversText(item.label || item.model), cards: item.cards}))));
  select.value = S.servers.choice || "";
  return [h("div", {class: "step-card"}, serversProgress(needsTunnel
    ? [["now", T("steps.server.tunnel_line")], ["next", T("steps.server.pick_line")]]
    : [["done", T("servers.company.connected")], ["now", T(loaded.length ? "steps.server.start_company_other_title" : "steps.server.pick_line")]])),
  needsTunnel ? h("div", {class: "server-notice"}, h("strong", null, T("servers.diagnosis.tunnel_closed.fact")), h("p", null, T("servers.diagnosis.tunnel_closed.todo")))
    : loaded.length ? h("div", {class: "server-notice"}, h("strong", null, T("servers.mismatch.title")), h("p", null, T("servers.mismatch.limit")))
    : serversDiagnosis(),
  !needsTunnel && choices.length ? h("div", {class: "step-card server-choice"}, h("label", {for: "servers-choice"}, T("servers.connection.choose")), select) : null];
}
function serversStageWait(kind) {
  const data = serversData(), rented = kind === "rented", pod = serversSessionPod(), model = serversKindModel(kind);
  const seen = rented ? pod?.status === "RUNNING" : !!data.rngd?.models?.length;
  return [h("div", {class: "step-card"}, serversProgress([
    [seen ? "done" : "now", T(`steps.server.wait_${rented ? "server" : "process"}${seen ? "" : "_unseen"}`)],
    [seen ? "now" : "next", T("steps.server.wait_reply")],
    ["next", T("steps.server.wait_match")]])),
  model?.reachable === true && model?.match === false ? h("div", {class: "server-notice"}, h("strong", null, T("servers.mismatch.title"))) : null,
  rented ? [serversKindProblem("rented"), num(pod?.uptime_s) ? h("p", null, T("steps.server.wait_on_for", {elapsed: serversDuration(pod.uptime_s)})) : null,
    h("p", null, T("servers.session.preparing")),
    num(pod?.auto_delete_min) ? h("p", {class: "muted"}, T("steps.server.wait_auto", {minutes: pod.auto_delete_min})) : null]
    : serversDiagnosis()];
}
function serversStageStop(kind) {
  const data = serversData(), rngd = data.rngd || {};
  if (kind === "company") {
    const loaded = rngd.models || [];
    return [serversDiagnosis(),
      h("div", {class: "step-card"}, serversFacts([[T("steps.server.fact_cost"), T("steps.server.company_cost")],
        num(loaded[0]?.elapsed_s) ? [T("steps.server.stat_uptime"), serversDuration(loaded[0].elapsed_s)] : null])),
      h("p", {class: "muted"}, T("steps.server.preparation_unknown")),
      h("p", null, T("steps.server.stop_company_note")),
      h("div", {class: "server-actions"}, loaded.map(item => serversAction("rngd_down", {model: item.model}, T("servers.ready.confirm_unload"), `step-${item.pid ?? item.model}`)),
        rngd.tunnel?.open ? serversAction("tunnel_close", {}, T("servers.connection.confirm_close"), "step") : null)];
  }
  const pod = serversSessionPod(), seconds = data.session?.ready_seconds, others = data.session?.others?.length;
  return [h("div", {class: "server-stats"},
    serversStat(T("steps.server.stat_hourly"), serversMoney(pod?.cost_per_hr)),
    serversStat(T("steps.server.stat_uptime"), serversDuration(pod?.uptime_s)),
    serversStat(T("steps.server.stat_total"), serversMoney(pod?.cost_est)),
    serversStat(T("steps.server.stat_auto"), num(pod?.auto_delete_min) ? serversDuration(pod.auto_delete_min * 60) : T("steps.server.auto_unknown"))),
  h("p", {class: "muted"}, T("steps.server.cost_basis"), " ",
    num(seconds) ? T("steps.server.prepared_time", {elapsed: serversDuration(seconds)}) : T("steps.server.preparation_unknown")),
  others ? h("div", {class: "server-notice"}, h("p", null, T("steps.server.others_running", {count: others}))) : null,
  // 목록을 못 읽으면 주인을 모른다. 남의 서버라고 말하지 않는다.
  data.runpod_error ? serversKindProblem("rented")
    : !pod?.owned ? h("div", {class: "server-notice"}, h("p", null, T("servers.messages.pod_not_ours")))
    : !pod.deletable ? h("div", {class: "server-notice"}, h("p", null, serversText(data.why?.pod_delete || data.lock_reason || T("servers.rented.no_delete"))))
    : h("div", {class: "server-notice server-delete"}, h("p", null, T("steps.server.delete_note")),
      serversAction("pod_delete", {pod_id: pod.id}, T("steps.server.delete_action"), pod.id))];
}
function serversStartActions(kind) {
  if (kind === "rented") return {primary: serversStepAction("pod_create", {}, T("servers.rented.confirm_create"))};
  const {choice, needsTunnel, loaded} = serversCompanyStart();
  if (needsTunnel) return {primary: serversStepAction("tunnel_open", {}, T("servers.busy.open_tunnel"))};
  const downs = loaded.map(item => serversStepAction("rngd_down", {model: item.model}, T("servers.mismatch.unload"), `step-${item.pid ?? item.model}`));
  const up = choice ? serversStepAction("rngd_up", {tag: choice.tag}, T("servers.company.confirm_load", {model: serversText(choice.label || choice.model)})) : null;
  // 다른 모델이 켜져 있으면 끄는 일이 먼저다. 다음 행동 자리에 그 일을 둔다.
  if (downs.length) return {note: T("steps.server.start_company_note"), secondary: [up, ...downs.slice(0, -1)].filter(Boolean), primary: downs.at(-1)};
  return {note: T("steps.server.start_company_note"), primary: up};
}
function serversBack(key, onClick) { return {label: T(key), onClick, attrs: {id: "servers-back"}}; }
function serversActions(step, kind) {
  const data = serversData();
  const target = S.focus.doc && S.focus.section ? T("servers.company.return_target", {doc: serversText(S.focus.doc), section: S.focus.section}) : "";
  const checked = S.shell.serverAt ? T("servers.ready.checked_at", {time: when(S.shell.serverAt)}) : "";
  if (step === "start") return {...serversStartActions(kind), back: serversBack("steps.server.back_choose", () => serversGo("choose"))};
  if (step === "wait") {
    const pod = serversSessionPod(), loaded = data.rngd?.models?.[0];
    return {note: [target, checked].filter(Boolean).join(" "),
      back: kind === "company" ? (loaded ? serversStepAction("rngd_down", {model: loaded.model}, T("steps.server.cancel_company"), `step-${loaded.pid ?? loaded.model}`) : null)
        : pod?.owned && pod.deletable ? serversStepAction("pod_delete", {pod_id: pod.id}, T("steps.server.cancel_rented"), pod.id) : null,
      // 준비되면 저절로 ④로 넘어간다. 그래서 주 행동은 기다리는 동안 할 일이다.
      secondary: {label: T("servers.failed.retry"), onClick: shellPollServers, disabled: !!S.shell.polling, attrs: {id: "servers-refresh"}},
      primary: {label: T("servers.creating.read_results"), onClick: () => go("s01"), attrs: {id: "servers-read-results"}}};
  }
  if (step === "stop") return {note: [target, checked].filter(Boolean).join(" "),
    primary: {label: T("servers.ready.return_trial"), onClick: serversReturn, attrs: {id: "servers-return"}}};
  return {note: T("context.model.saved_readable"), back: S.focus.returnScreen ? serversBack("servers.ready.return_trial", serversReturn) : null,
    primary: S.shell.serverError ? {label: T("servers.failed.retry"), onClick: shellPollServers, disabled: !!S.shell.polling, attrs: {id: "servers-refresh"}} : null};
}
function serversNotices(step, kind) {
  const data = serversData(), primary = step === "start" ? serversStartActions(kind).primary : null;
  const blocked = primary && data?.can?.[primary.attrs["data-server-action"]] === false;
  const other = ["choose", "start"].includes(step) ? SERVERS_KINDS.find(item => item !== S.servers.kind && serversKindState(item) !== "off") : null;
  return [S.guide?.returnScreen ? h("div", {class: "server-notice"}, h("p", null, T("guide.ai.return_note")),
    h("button", {id: "servers-guide-return", type: "button", "data-guide": "s06-return", onclick: () => emit("guide_return", {})}, T("guide.ai.return"))) : null,
  h("div", {role: "status", "aria-live": "polite"}, S.servers.busy ? h("p", null, T("servers.status.busy")) : null),
  S.shell.serverError ? serversFlat(serversProblem(S.shell.serverError, "status")) : null, serversLockNote(),
  S.servers.error ? serversFlat(serversProblem(S.servers.error.error, S.servers.error.action)) : null,
  S.servers.result ? serversResult(S.servers.result) : null,
  S.servers.reload ? h("div", {class: "server-notice", role: "status"}, h("p", null, T("servers.reload.done"))) : null,
  (data?.env_problems || []).map(info => serversFlat(serversFriendly(info))),
  S.shell.serverError || S.servers.error || data?.env_problems?.length || blocked ? h("div", {class: "server-actions"},
    step === "wait" || (step === "choose" && S.shell.serverError) ? null : serversButton("servers-refresh", "servers.failed.retry", shellPollServers, !!S.shell.polling),
    serversButton("servers-reload-env", "servers.connection.reload", serversReloadEnv, !!S.servers.busy || !!S.servers.proposal)) : null,
  other ? h("div", {class: "server-notice"}, h("p", null, T("steps.server.other_on", {model: serversLabel(serversKindModel(other))})),
    h("button", {id: "servers-see-live", type: "button", onclick: () => serversMove(null, other)}, T("steps.server.other_on_open"))) : null];
}
function serversRenderFlow(el) {
  const step = serversStep(), kind = serversKind(), [title, say] = serversHead(step, kind);
  shellConclusion("s06", title);
  coreReplace(document.getElementById("servers-step-say"), say, step === "stop" ? [" ", term("stop_order", T("steps.server.stop_order"))] : null);
  stepsRenderBar(document.getElementById("servers-step-bar"), {steps: serversStepList(step), current: step, onGo: serversGo});
  const stage = !serversData() ? null : step === "choose" ? serversStageChoose() : step === "wait" ? serversStageWait(kind)
    : step === "stop" ? serversStageStop(kind) : kind === "rented" ? serversStageStartRented() : serversStageStartCompany();
  const actions = h("div", {id: "servers-actions"});
  coreReplace(el, h("div", {class: "step-screen"}, serversNotices(step, kind), stage,
    h("p", {class: "server-details-link"}, h("button", {id: "servers-details-open", type: "button", class: "text-button", onclick: serversOpenDetails}, T("steps.details.open")), " ", T("steps.server.details_hint")),
    actions));
  stepsRenderActions(actions, serversActions(step, kind));
}
// ── 자세히 서랍: 서버 목록, 모델별 연결, 회사 서버 연결, 설정, 서버 기록, 오류 기록 ──
function serversDrawerSection(title, ...kids) {
  return h("div", {class: "drawer-section"}, h("h3", null, title), kids);
}
function serversDrawerPods() {
  const data = serversData(), session = data?.session;
  return serversDrawerSection(T("servers.rented.title_list"),
    h("p", null, T("servers.empty.new_cost")),
    session ? [h("p", null, T(session.adopted ? "servers.session.adopted" : "servers.session.active", {pod_id: serversText(session.pod_id)})),
      h("p", null, T("servers.session.settings")),
      h("p", null, T(serversReady(serversModel(session.tag)) ? "servers.ready.expected" : "servers.session.preparing")),
      (session.others || []).map(id => h("p", {class: "technical"}, T("servers.rented.other_id", {pod_id: serversText(id)})))] : null,
    data && serversKindProblem("rented"),
    !data ? h("p", null, T("servers.models.unknown")) : data.pods?.length ? data.pods.map(pod => {
      const state = pod.state || pod.status;
      return h("div", {class: "server-row", "data-pod": pod.id},
        h("p", null, h("strong", {class: "technical"}, serversText(pod.name) || T("servers.rented.unknown")), " ", h("span", {class: "raw"}, serversText(pod.id))),
        h("p", null, T(pod.owned ? "servers.rented.owned" : "servers.rented.delete_forbidden")),
        h("p", null, T("servers.rented.state", {state: coreCodeLabel("pod", state)})),
        h("p", {class: "raw", "data-code-record": "pod"}, T("common.code_record_title"), ": ", serversText(state) || T("common.none")),
        h("p", {class: "muted"}, num(pod.auto_delete_min) ? T("servers.time.auto_delete", {minutes: pod.auto_delete_min}) : T("servers.time.no_schedule")),
        serversFacts([[T("servers.rented.uptime"), serversDuration(pod.uptime_s)],
          state && state !== "RUNNING" ? null : [T("servers.rented.hourly_rate"), serversMoney(pod.cost_per_hr, true)], [T("servers.rented.total_cost"), serversMoney(pod.cost_est)]]),
        pod.owned && pod.deletable ? serversAction("pod_delete", {pod_id: pod.id}, T("servers.rented.confirm_delete"), `drawer-${pod.id}`)
          : h("p", null, !pod.owned ? T("servers.messages.pod_not_ours") : serversText(data.why?.pod_delete || data.lock_reason || T("servers.rented.no_delete"))));
    }) : h("p", null, T(data.runpod_error ? "servers.account_failed.cost_unknown" : "servers.empty.title")),
    h("p", {class: "muted"}, T("servers.rented.estimate_warning")),
    h("p", null, num(data?.volumes) ? T("servers.rented.volumes", {count: data.volumes}) : T("servers.rented.volume_unknown")),
    h("p", null, T("servers.rented.storage_cost")),
    h("p", null, T("servers.rented.scheduler")));
}
function serversDrawerModels() {
  const data = serversData(), quiet = (data?.models || []).some(serversReady);
  return serversDrawerSection(T("servers.connection.title"), h("p", null, T("servers.connection.ready_condition")),
    h("div", {id: "servers-model-list"}, !data ? h("p", null, T(S.shell.serverError ? "servers.failed.title" : "servers.checking.title"))
      : !data.models?.length ? h("p", null, T("servers.models.empty")) : data.models.map(model => h("div", {class: "server-row"},
        h("p", null, h("strong", {class: "technical"}, serversLabel(model)), " ", h("span", {class: "raw"}, serversText(model.tag))),
        serversBadge(model), model.reachable === true && model.match === false ? h("p", null, T("servers.mismatch.title")) : null,
        serversFlat(serversModelNote(model, quiet)),
        serversFacts([[T("servers.connection.expected"), serversText(model.model_expected) || T("servers.models.unknown")],
          [T("servers.models.where"), serversText(model.where) || T("servers.models.unknown")],
          [T("servers.connection.responding"), serversText(model.model_served) || T(model.reachable === false ? "servers.models.no_reply" : "servers.connection.unknown")],
          [T("servers.connection.address"), T(model.url_set ? "servers.connection.configured" : "servers.models.not_configured")]])))));
}
function serversDrawerCompany() {
  const rngd = serversData()?.rngd || {}, tunnel = rngd.tunnel || {}, elapsed = serversElapsed(tunnel.since);
  return serversDrawerSection(T("steps.server.connection"),
    h("p", null, tunnel.port == null ? T("servers.connection.tunnel_unknown") : T(tunnel.open
      ? tunnel.owned ? "servers.connection.tunnel_owned" : "servers.connection.tunnel_external" : "servers.connection.tunnel_closed", {port: tunnel.port})),
    tunnel.open ? h("p", null, elapsed === null ? T("servers.connection.tunnel_time_unknown") : T("servers.time.since", {elapsed: serversDuration(elapsed)})) : null,
    tunnel.pid != null ? h("p", {class: "raw"}, T("servers.connection.process", {pid: tunnel.pid})) : null,
    tunnel.open ? serversAction("tunnel_close", {}, T("servers.connection.confirm_close"), "drawer") : null,
    (rngd.models || []).map(model => h("div", {class: "server-row"},
      h("p", {class: "technical"}, serversText(model.model)), h("p", {class: "raw"}, T("servers.connection.process", {pid: model.pid ?? T("servers.rented.unknown")})),
      serversAction("rngd_down", {model: model.model}, T("servers.ready.confirm_unload"), `drawer-${model.pid ?? model.model}`))),
    h("p", null, T("servers.connection.devices", {count: 4})),
    rngd.ok && !rngd.models?.length ? h("p", null, T("servers.connection.none")) : null,
    rngd.text ? h("pre", {class: "technical"}, serversText(rngd.text)) : null,
    h("p", null, T("servers.logs.redaction")), h("p", null, T("servers.connection.ssh_meaning")), h("p", null, T("servers.connection.tunnel_meaning")));
}
function serversDrawerSettings() {
  const reload = S.servers.reload;
  return serversDrawerSection(T("steps.server.settings"),
    S.shell.serverAt ? h("p", {class: "muted"}, T("servers.ready.checked_at", {time: when(S.shell.serverAt)})) : null,
    serversButton("servers-reload-env-drawer", "servers.connection.reload", serversReloadEnv, !!S.servers.busy || !!S.servers.proposal),
    reload ? [h("p", null, T("servers.reload.done")),
      ["names", "changed", "removed"].map(key => h("p", null, T(`servers.reload.${key}`), ": ",
        (reload[key] || []).filter(name => /^[A-Z][A-Z0-9_]*$/.test(name)).join(", ") || T("common.none"))),
      (reload.problems || []).map(info => serversFlat(serversFriendly(info)))] : null,
    (serversData()?.env_problems || []).map(info => serversFlat(serversFriendly(info))),
    h("p", null, h("strong", null, T("servers.env.names"))),
    h("p", {class: "technical"}, "RUNPOD_API_KEY, RUNPOD_VLLM_API_KEY, RUNPOD_VLLM_BASE_URL, RNGD_BASE_URL, RNGD_API_KEY, RNGD_SSH"),
    h("p", null, T("servers.env.hidden_values")));
}
function serversDrawerLog() {
  const rows = serversData()?.log_tail || [];
  return serversDrawerSection(T("servers.logs.summary", {limit: 10, count: rows.length}),
    rows.length ? h("pre", {class: "technical"}, rows.map(serversText).join("\n")) : h("p", null, T("servers.logs.empty")),
    h("p", {class: "raw"}, T("servers.logs.path")), rows.length ? h("p", null, T("servers.logs.manual_copy")) : null);
}
function serversDrawerRaw() {
  const data = serversData(), failure = error => error?.body?.friendly?.raw || error?.body?.error || error?.message;
  const raws = [failure(S.shell.serverError), failure(S.servers.error?.error), data?.friendly?.raw, data?.runpod_error, data?.rngd?.friendly?.raw,
    ...(data?.models || []).map(model => model.friendly?.raw), ...(data?.env_problems || []).map(info => info.raw)];
  const unique = [...new Set(raws.filter(Boolean).map(serversText))];
  return unique.length ? serversDrawerSection(T("common.raw_error_title"), unique.map(raw => h("pre", {class: "technical"}, raw))) : null;
}
function serversRenderDrawer(body) {
  coreReplace(body, serversDrawerPods(), serversDrawerModels(), serversDrawerCompany(), serversDrawerSettings(), serversDrawerLog(), serversDrawerRaw());
  drawerFlatten(body);
}
function serversOpenDetails() {
  drawerOpen({title: T("steps.server.details_title"), trigger: document.getElementById("servers-details-open"), render: serversRenderDrawer});
}
function serversRender() {
  const active = document.activeElement, id = active?.id;
  if (S.shell.route === "s06") {
    serversRenderFlow(document.getElementById("servers-flow"));
    if (S.drawer.screen === "s06") serversRenderDrawer(document.querySelector("#details-drawer .drawer-body"));
  }
  if (S.servers.proposal && !S.servers.busy) serversUpdateConfirm();
  for (const [el, options] of S.servers.compacts) {
    if (!el.isConnected) S.servers.compacts.delete(el); else serversRenderCompact(el, options);
  }
  if (id && !active.isConnected && !document.getElementById("action-confirm").open) document.getElementById(id)?.focus({preventScroll: true});
}
function serversConfirmReason(proposal) {
  if (proposal.invalid) return proposal.invalid;
  const reason = serversReason(proposal.action, true);
  if (reason) return reason;
  if (proposal.action === "pod_create" && serversCreateCost(proposal) === null) return T("servers.confirm.create.cost_unknown");
  if (proposal.action === "pod_delete" && !serversData()?.pods?.some(pod => pod.id === proposal.params.pod_id && pod.owned && pod.deletable)) return T("servers.rented.no_delete");
  return "";
}
function serversUpdateConfirm() {
  const proposal = S.servers.proposal, button = document.getElementById("servers-confirm");
  if (!button || !proposal) return;
  const reason = serversConfirmReason(proposal);
  if (reason) proposal.invalid = reason;
  button.disabled = !!reason || proposal.expiresAt === null;
  const note = document.getElementById("servers-confirm-blocked");
  if (note) note.textContent = reason;
}
// inStep: 단계 화면 안에서 쓴다. 주 행동은 행동 줄에 있고 접힘이 없다. extra는 다시 그려도 남는 제자리 행동이다.
function serversRenderCompact(el, {model, primary = false, inStep = false, extra = null} = {}) {
  S.servers.compacts.set(el, {model, primary, inStep, extra});
  const item = serversModel(model), state = serversState(item);
  coreReplace(el, h("h3", null, T("servers.connection.selected")), h("p", {class: "technical"}, serversLabel(item || {tag: model})),
    serversBadge(item), item?.reachable && item?.match === false ? h("p", null, T("servers.mismatch.title")) : null,
    S.shell.serverError ? serversProblem(S.shell.serverError) : serversModelNote(item),
    inStep ? null : h("button", {type: "button", class: primary ? "primary" : null,
      onclick: () => go("s06", {model: item?.tag || model, returnScreen: "s03"})},
      T(state === "connected" ? "servers.connection.details" : "context.prepare_model")),
    extra?.());
  if (inStep) serversFlat(el);
}
function serversCatch(error, action) {
  S.servers.error = {error, action};
  if (error.status === 409) S.servers.lock = error.body || {};
  if (error.status === 503) { S.shell.servers = null; S.shell.serverError = error; shellRenderModels(); }
}
async function serversPropose(action, params = {}, trigger = null) {
  if (serversReason(action)) return;
  S.servers.busy = action; S.servers.error = null; S.servers.result = null; S.servers.trigger = trigger;
  serversRender();
  try {
    const data = await post("/api/servers/propose", {action, params});
    if (!data?.token || data.action !== action) throw new Error(T("servers.status.failure.fact"));
    S.servers.proposal = {...data, params, expiresAt: num(data.expires_in) ? Date.now() + data.expires_in * 1000 : null, used: false};
    serversOpenDialog();
  } catch (error) { serversCatch(error, action); }
  finally { S.servers.busy = null; serversRender(); }
}
function serversOpenDialog() {
  const proposal = S.servers.proposal, dialog = document.getElementById("action-confirm");
  const prefix = `servers.confirm.${SERVERS_CONFIRM[proposal.action]}`;
  const model = serversData()?.rngd_choices?.find(item => item.tag === proposal.params.tag);
  const values = {server: serversText(proposal.params.pod_id), model: serversText(model?.label || proposal.params.model || T("context.model.default_name")),
    cost_per_hour: serversCreateCost(proposal)};
  dialog.setAttribute("aria-labelledby", "servers-confirm-title");
  dialog.setAttribute("aria-describedby", "servers-confirm-summary");
  coreReplace(dialog, h("h2", {id: "servers-confirm-title"}, T(`${prefix}.title`, values)),
    h("h3", null, T("servers.confirm.summary")), h("p", {id: "servers-confirm-summary", class: "technical"}, serversText(proposal.summary)),
    proposal.action === "pod_create" && values.cost_per_hour !== null ? h("p", null, T("steps.server.confirm_create", values)) : null,
    proposal.warning ? h("div", null, h("strong", null, T("servers.confirm.warning")), h("p", {class: "technical"}, serversText(proposal.warning))) : null,
    h("p", null, T("servers.confirm.once")), h("p", null, proposal.expiresAt === null ? T("servers.confirm.no_expiry")
      : T("servers.confirm.expires", {time: when(new Date(proposal.expiresAt).toISOString())})),
    h("p", null, T("servers.confirm.recheck")),
    h("p", {id: "servers-confirm-blocked", role: "status"}),
    h("div", {class: "dialog-actions"}, serversButton("servers-cancel", "servers.confirm.cancel", serversCloseDialog),
      h("button", {id: "servers-confirm", class: "primary", type: "button", disabled: proposal.expiresAt === null,
        onclick: () => serversExecute(proposal)}, proposal.action === "pod_create" && values.cost_per_hour === null
          ? T("servers.rented.confirm_create") : T(`${prefix}.action`, values))));
  if (!S.servers.dialogReady) {
    S.servers.dialogReady = true;
    dialog.addEventListener("cancel", event => { if (S.servers.proposal) { event.preventDefault(); serversCloseDialog(); } });
    dialog.addEventListener("keydown", event => {
      if (!S.servers.proposal) return;
      if (event.key === "Escape") { event.preventDefault(); serversCloseDialog(); }
      if (event.key === "Tab") {
        const buttons = [...dialog.querySelectorAll("button")].filter(button => !button.disabled);
        const first = buttons[0], last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
  }
  if (!dialog.open) dialog.showModal();
  document.getElementById("servers-cancel").focus();
}
function serversCloseDialog() {
  S.servers.proposal = null;
  const dialog = document.getElementById("action-confirm");
  if (dialog.open) dialog.close();
  serversRender(); document.getElementById(S.servers.trigger)?.focus({preventScroll: true});
}
async function serversExecute(proposal) {
  if (proposal.used || S.servers.proposal !== proposal || S.servers.busy) return;
  if (serversConfirmReason(proposal)) { serversUpdateConfirm(); return; }
  if (proposal.expiresAt === null || Date.now() >= proposal.expiresAt) {
    serversCloseDialog(); serversCatch(Object.assign(new Error(T("servers.confirm.expired.fact")), {status: 410}), proposal.action); serversRender(); return;
  }
  proposal.used = true; serversCloseDialog(); S.servers.busy = proposal.action; S.servers.error = null; serversRender();
  try {
    const data = await post("/api/servers/execute", {token: proposal.token});
    S.servers.result = {action: proposal.action, ...data};
    if (data?.ok !== true) throw Object.assign(new Error(data?.error || T("servers.status.failure.fact")), {body: data});
    if (proposal.action === "pod_create") S.servers.step = null;
    if (["pod_delete", "rngd_down"].includes(proposal.action) && S.servers.step !== "start") S.servers.kind = null;
  } catch (error) { serversCatch(error, proposal.action); }
  finally { S.servers.busy = null; await serversRefreshAfterChange(); serversRender(); }
}
function serversResult(data) {
  const result = data.result || {}, action = data.action, lines = [];
  if (action === "pod_create") {
    lines.push(T("servers.result.created", {pod_id: serversText(result.pod_id)}));
    lines.push(T(result.watchdog ? "servers.result.watchdog" : "servers.result.no_watchdog"));
  } else if (action === "pod_delete") {
    lines.push(T(result.gone ? "servers.result.deleted" : "servers.result.deleting", {pod_id: serversText(result.pod_id), count: result.remaining?.length ?? 0}));
    if (result.remaining?.length) lines.push(T("servers.result.remaining", {ids: result.remaining.map(item => serversText(item.id || item)).join(", ")}));
  } else if (action === "rngd_up") {
    lines.push(result.started ? T("servers.result.started") : T("servers.status.failure.fact"));
    if (result.error) lines.push(serversText(result.error));
  } else if (action === "rngd_down") {
    lines.push(T("servers.result.stopped", {pids: result.killed?.join(", ") || T("common.none")}));
    if (result.remaining?.length) lines.push(T("servers.result.process_remaining", {pids: result.remaining.join(", ")}));
  } else lines.push(T(`servers.result.${action}`));
  return h("div", {class: "server-notice", role: "status"}, h("strong", null, T(data.ok ? "servers.result.done" : "servers.status.failure.fact")),
    lines.map(line => h("p", {class: "technical"}, line)), data.log_line ? h("p", {class: "raw"}, T("servers.result.log", {line: serversText(data.log_line)})) : null);
}
async function serversReloadEnv() {
  if (S.servers.busy || S.servers.proposal) return;
  S.servers.busy = "reload_env"; S.servers.error = null; S.servers.reload = null; serversRender();
  try {
    const data = await post("/api/servers/reload_env", {});
    if (data?.ok !== true) throw Object.assign(new Error(data?.error || T("servers.status.failure.fact")), {body: data});
    S.servers.reload = data;
  } catch (error) { serversCatch(error, "reload_env"); }
  finally { S.servers.busy = null; await serversRefreshAfterChange(); serversRender(); }
}
async function serversRefreshAfterChange() {
  if (S.shell.polling) await S.shell.polling;
  await shellPollServers();
}
async function serversEnsure(args = {}) {
  // 시험에서 다른 AI를 들고 오면 전에 고른 서버를 잊는다. 메뉴로 다시 들어오면 지금 상태의 단계로 연다.
  if (args.model) { S.servers.kind = null; S.servers.step = null; }
  else if (S.servers.step === "choose") S.servers.step = null;
  if (!S.shell.servers && !S.shell.serverError) await shellPollServers();
  const choice = serversData()?.rngd_choices?.find(item => item.tag === args.model || item.model === args.model);
  if (choice) S.servers.choice = choice.tag;
}
on("servers_changed", () => { if (!S.shell.serverError) S.servers.lock = null; serversRender(); });
shellDefineView("servers-flow", {load: serversEnsure, render: serversRenderFlow});
