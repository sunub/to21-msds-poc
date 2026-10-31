"use strict";

// 상태 자료와 조회 타이머는 S.shell만 소유한다. 여기는 화면 조작 상태만 둔다.
S.servers = {busy: null, proposal: null, error: null, result: null, reload: null,
  lock: null, choice: null, trigger: null, dialogReady: false, compacts: new Map()};
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
function serversModelNote(model) {
  if (!model?.friendly) return null;
  const diagnosis = serversData()?.rngd?.diagnosis;
  if (model.where === "RNGD" && ["no_model", "tunnel_closed", "loading"].includes(diagnosis)) {
    const info = model.friendly;
    return h("div", {class: "server-notice"}, h("strong", null, serversText(info.message)),
      h("p", null, serversText(info.fix)), info.raw ? rawError(serversText(info.raw)) : null);
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
function serversAction(action, params, label, suffix = "", primary = false) {
  const reason = serversReason(action);
  const id = `servers-${action}${suffix ? `-${encodeURIComponent(suffix)}` : ""}`;
  return h("div", {class: "server-action"},
    h("button", {id, type: "button", class: primary ? "primary" : null, "data-server-action": action,
      disabled: !!reason, "aria-describedby": reason ? `${id}-note` : null,
      onclick: () => serversPropose(action, params, id)}, label),
    reason ? h("p", {id: `${id}-note`, class: "muted"}, reason) : null);
}
function serversButton(id, key, fn, disabled = false) {
  return h("button", {id, type: "button", disabled, onclick: fn}, T(key));
}
function serversTable(heads, rows) {
  return h("table", {class: "server-table"}, h("thead", null, h("tr", null,
    heads.map(key => h("th", {scope: "col"}, T(key))))), h("tbody", null, rows));
}
function serversProblem(error, action = null) {
  if (error?.body?.friendly) return serversFriendly(error.body.friendly);
  const prefix = error?.status === 503 ? "servers.disabled" : error?.status === 409 ? "servers.busy"
    : error?.status === 410 ? "servers.confirm.expired" : action === "pod_create" ? "servers.create_unknown" : "servers.status.failure";
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
function serversReturn() {
  return go(S.focus.returnScreen === "s09" ? "s09" : "s03");
}
function serversRenderSummary(el) {
  const data = serversData(), model = serversModel(S.focus.model);
  const connected = (data?.models || []).filter(serversReady);
  const ready = S.focus.model ? serversReady(model) : connected.length > 0;
  const states = S.focus.model ? [shellModelState(model, data)] : shellModelStates(data);
  const title = S.shell.serverError ? T("servers.failed.title") : !data ? T("servers.checking.title")
    : ready ? T("servers.ready.title", {model: serversLabel(model || connected[0])})
    : states.includes("query_failed") ? T("servers.failed.title")
    : states.filter(state => state !== "state_off").length ? states.filter(state => state !== "state_off").map(state => T(`context.model.${state}`)).join(" · ")
    : T("servers.choice.recommendation");
  const reload = S.servers.reload;
  coreReplace(el, h("h2", null, title), h("p", null, T("context.model.saved_readable")),
    S.focus.doc && S.focus.section ? h("p", null, T("servers.company.return_target", {doc: serversText(S.focus.doc), section: S.focus.section})) : null,
    ready ? h("button", {id: "servers-return", type: "button", class: "primary", onclick: serversReturn}, T("servers.ready.return_trial")) : null,
    S.shell.serverAt ? h("p", {class: "muted"}, T("servers.ready.checked_at", {time: when(S.shell.serverAt)})) : null,
    h("div", {class: "server-actions"},
      serversButton("servers-refresh", "servers.failed.retry", shellPollServers, !!S.shell.polling),
      serversButton("servers-reload-env", "servers.connection.reload", serversReloadEnv, !!S.servers.busy || !!S.servers.proposal)),
    h("div", {role: "status", "aria-live": "polite"}, S.servers.busy ? h("p", null, T("servers.status.busy")) : null),
    S.shell.serverError ? serversProblem(S.shell.serverError) : null, serversLockNote(),
    S.servers.error ? serversProblem(S.servers.error.error, S.servers.error.action) : null,
    S.servers.result ? serversResult(S.servers.result) : null,
    h("details", {id: "servers-settings"}, h("summary", null, T("servers.connection.details")),
    reload ? h("div", {class: "server-notice", role: "status"}, h("p", null, T("servers.reload.done")),
      ["names", "changed", "removed"].map(key => h("p", null, T(`servers.reload.${key}`), ": ",
        (reload[key] || []).filter(name => /^[A-Z][A-Z0-9_]*$/.test(name)).join(", ") || T("common.none"))),
      (reload.problems || []).map(serversFriendly)) : null,
    (data?.env_problems || []).map(serversFriendly),
    h("details", {id: "servers-env-details"}, h("summary", null, T("servers.env.names")),
      h("p", {class: "technical"}, "RUNPOD_API_KEY, RUNPOD_VLLM_API_KEY, RUNPOD_VLLM_BASE_URL, RNGD_BASE_URL, RNGD_API_KEY, RNGD_SSH"),
      h("p", null, T("servers.env.hidden_values")))));
}
function serversRenderModels(el) {
  const data = serversData();
  coreReplace(el, h("details", {id: "servers-model-details"}, h("summary", null, T("servers.connection.title")),
    h("h2", null, T("servers.models.title")), h("p", null, T("servers.connection.ready_condition")),
    !data ? h("p", null, T(S.shell.serverError ? "servers.failed.title" : "servers.checking.title")) :
      !data.models?.length ? h("p", null, T("servers.models.empty")) : serversTable([
        "servers.connection.expected", "servers.models.where", "servers.models.state", "servers.connection.responding", "servers.connection.address"],
      data.models.map(model => h("tr", null,
        h("td", null, h("strong", {class: "technical"}, serversLabel(model)), h("p", {class: "raw"}, serversText(model.tag))),
        h("td", null, serversText(model.where) || T("servers.models.unknown")),
        h("td", null, serversBadge(model), model.reachable === true && model.match === false ? h("p", null, T("servers.mismatch.title")) : null,
          serversModelNote(model)),
        h("td", {class: "technical"}, serversText(model.model_served) || T(model.reachable === false ? "servers.models.no_reply" : "servers.connection.unknown")),
        h("td", null, T(model.url_set ? "servers.connection.configured" : "servers.models.not_configured")))))));
}
function serversRenderComparison(el) {
  const pods = serversData()?.pods || [];
  coreReplace(el, serversTable(["common.method", "servers.compare.cost", "servers.compare.wait", "servers.compare.limits"], [
    h("tr", null, h("th", {scope: "row"}, T("servers.choice.company")), h("td", null, T("common.none")),
      h("td", null, T("servers.compare.company.wait")), h("td", null, T("servers.compare.company.limit"))),
    h("tr", null, h("th", {scope: "row"}, T("servers.choice.rented")),
      h("td", null, h("p", null, T("servers.empty.new_cost")),
        pods.length ? h("ul", null, pods.map(pod => h("li", null,
          h("span", {class: "technical"}, serversText(pod.name || pod.id)), ": ", serversMoney(pod.cost_per_hr, true)))) : T("servers.rented.unknown")),
      h("td", null, T("servers.compare.rented.wait")), h("td", null, T("servers.compare.rented.cleanup"), h("p", null, T("servers.rented.scheduler"))))]),
    h("p", {class: "muted"}, T("servers.compare.company.cost_meaning")));
}
function serversRenderRunpod(el) {
  const data = serversData(), session = data?.session;
  const active = (data?.models || []).some(model => model.where === "RunPod" && serversReady(model));
  coreReplace(el, h("details", {id: "servers-rented-details", open: active || null},
    h("summary", null, T(active ? "servers.rented.title_list" : "servers.company.alternative")),
    h("h2", null, term("runpod", T("servers.rented.title_list"))),
    h("p", null, T("servers.empty.new_cost")),
    session ? h("div", {class: "server-notice"},
      h("p", null, T(session.adopted ? "servers.session.adopted" : "servers.session.active", {pod_id: serversText(session.pod_id)})),
      h("p", null, T("servers.session.settings")),
      serversReady(serversModel(session.tag)) ? h("p", null, T("servers.ready.expected")) : h("p", null, T("servers.session.preparing")),
      (session.others || []).map(id => h("p", {class: "technical"}, T("servers.rented.other_id", {pod_id: serversText(id)})))) : null,
    data?.friendly ? serversFriendly(data.friendly) : data?.runpod_error ? serversFriendly({message: T("servers.account_failed.title"), fix: T("servers.account_failed.todo"), raw: data.runpod_error}) : null,
    !data ? h("p", null, T("servers.models.unknown")) : data.pods?.length ? serversTable([
      "servers.rented.identity", "servers.rented.ownership", "servers.rented.uptime", "servers.rented.hourly_rate", "servers.rented.total_cost", "servers.rented.confirm_delete"],
      data.pods.map(pod => h("tr", {"data-pod": pod.id},
        h("td", null, h("strong", {class: "technical"}, serversText(pod.name) || T("servers.rented.unknown")), h("p", {class: "raw"}, serversText(pod.id))),
        h("td", null, pod.owned ? T("servers.rented.owned") : T("servers.rented.delete_forbidden"),
          h("p", null, T("servers.rented.state", {state: coreCodeLabel("pod", pod.state || pod.status)})),
          coreCodeRecord(pod.state || pod.status),
          h("p", {class: "muted"}, num(pod.auto_delete_min) ? T("servers.time.auto_delete", {minutes: pod.auto_delete_min}) : T("servers.time.no_schedule"))),
        h("td", null, serversDuration(pod.uptime_s)), h("td", null, serversMoney(pod.cost_per_hr, true)), h("td", null, serversMoney(pod.cost_est)),
        h("td", null, pod.owned && pod.deletable ? serversAction("pod_delete", {pod_id: pod.id}, T("servers.rented.confirm_delete"), pod.id)
          : h("p", null, !pod.owned ? T("servers.messages.pod_not_ours") : serversText(data.why?.pod_delete || data.lock_reason || T("servers.rented.no_delete")))))))
      : h("p", null, T(data.runpod_error ? "servers.account_failed.cost_unknown" : "servers.empty.title")),
    h("p", {class: "muted"}, T("servers.rented.estimate_warning")),
    h("p", null, num(data?.volumes) ? T("servers.rented.volumes", {count: data.volumes}) : T("servers.rented.volume_unknown")),
    h("p", null, T("servers.rented.storage_cost")),
    h("p", null, T("servers.rented.scheduler")),
    serversAction("pod_create", {}, T("servers.rented.confirm_create"))));
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
      h("p", null, T("servers.diagnosis.loading.todo")), elapsed > 1500 ? h("p", null, T("servers.diagnosis.loading.late", {minutes: 25})) : null,
      serversButton("servers-read-results", "servers.creating.read_results", () => go("s01")));
  }
  const info = (data?.models || []).find(model => model.where === "RNGD" && model.friendly)?.friendly || rngd.friendly;
  return info ? serversFriendly(info) : h("p", null, T("servers.connection.unknown"));
}
function serversRenderRngd(el) {
  const data = serversData(), rngd = data?.rngd || {}, tunnel = rngd.tunnel || {}, choices = data?.rngd_choices || [];
  if (!choices.some(choice => choice.tag === S.servers.choice)) S.servers.choice = choices.find(choice => choice.tag === S.focus.model)?.tag || choices[0]?.tag || null;
  const choice = choices.find(item => item.tag === S.servers.choice);
  const select = h("select", {id: "servers-choice", disabled: !choices.length, onchange: event => {
    S.servers.choice = event.target.value; serversRender();
  }}, choices.map(item => h("option", {value: item.tag}, T("servers.connection.choice", {model: serversText(item.label || item.model), cards: item.cards}))));
  select.value = S.servers.choice || "";
  const elapsed = serversElapsed(tunnel.since);
  const comparison = h("div", {id: "servers-comparison"}); serversRenderComparison(comparison);
  const ready = S.focus.model ? serversReady(serversModel(S.focus.model)) : (data?.models || []).some(serversReady);
  const choose = h("div", {class: "server-choice"}, h("label", {for: "servers-choice"}, T("servers.connection.choose")), select,
    choice ? serversAction("rngd_up", {tag: choice.tag}, T("servers.company.confirm_load", {model: serversText(choice.label || choice.model)}), "", !ready && tunnel.open === true && rngd.diagnosis === "no_model") : null);
  coreReplace(el, h("div", {class: "server-primary"}, h("h2", null, term("rngd", T("servers.choice.company"))),
    serversDiagnosis(), !tunnel.open ? serversAction("tunnel_open", {}, T("servers.busy.open_tunnel"), "", !ready) : null,
    tunnel.open && rngd.diagnosis === "no_model" ? choose : null), comparison,
    h("details", {id: "servers-company-details"}, h("summary", null, T("servers.connection.details")),
    h("div", {class: "server-tunnel"},
      h("p", null, tunnel.port == null ? T("servers.connection.tunnel_unknown") : T(tunnel.open
        ? tunnel.owned ? "servers.connection.tunnel_owned" : "servers.connection.tunnel_external" : "servers.connection.tunnel_closed", {port: tunnel.port})),
      tunnel.open ? h("p", null, elapsed === null ? T("servers.connection.tunnel_time_unknown") : T("servers.time.since", {elapsed: serversDuration(elapsed)})) : null,
      tunnel.pid != null ? h("p", {class: "raw"}, T("servers.connection.process", {pid: tunnel.pid})) : null,
      tunnel.open ? serversAction("tunnel_close", {}, T("servers.connection.confirm_close")) : null),
    !tunnel.open || rngd.diagnosis !== "no_model" ? choose : null,
    (rngd.models || []).map(model => h("div", {class: "server-process"},
      h("p", {class: "technical"}, serversText(model.model)), h("p", {class: "raw"}, T("servers.connection.process", {pid: model.pid ?? T("servers.rented.unknown")})),
      serversAction("rngd_down", {model: model.model}, T("servers.ready.confirm_unload"), String(model.pid ?? model.model)))),
    h("details", {id: "servers-device-details"}, h("summary", null, T("servers.connection.processes")),
      h("p", null, T("servers.connection.devices", {count: 4})),
      rngd.ok && !rngd.models?.length ? h("p", null, T("servers.connection.none")) : null,
      rngd.text ? h("pre", {class: "technical"}, serversText(rngd.text)) : null,
      h("p", null, T("servers.logs.redaction")), h("p", null, T("servers.connection.ssh_meaning")), h("p", null, T("servers.connection.tunnel_meaning")))));
}
function serversRenderLog(el) {
  const rows = serversData()?.log_tail || [];
  card(el.id, T("servers.logs.summary", {limit: 10, count: rows.length}), null, {collapsed: true, summary: rows.length ? T("common.record") : T("servers.logs.empty")},
    rows.length ? h("pre", {class: "technical"}, rows.map(serversText).join("\n")) : h("p", null, T("servers.logs.empty")),
    h("p", {class: "raw"}, T("servers.logs.path")), rows.length ? h("p", null, T("servers.logs.manual_copy")) : null);
}
function serversRender() {
  const active = document.activeElement, id = active?.id;
  const expanded = new Map([...document.querySelectorAll('#screen-s06 details[id]')].map(el => [el.id, el.open]));
  if (S.shell.route === "s06") {
    serversRenderSummary(document.getElementById("servers-summary")); serversRenderModels(document.getElementById("servers-models"));
    serversRenderRngd(document.getElementById("servers-rngd")); serversRenderRunpod(document.getElementById("servers-runpod"));
    serversRenderLog(document.getElementById("servers-log"));
    for (const [id, open] of expanded) { const el = document.getElementById(id); if (el) el.open = open; }
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
function serversRenderCompact(el, {model, primary = false} = {}) {
  S.servers.compacts.set(el, {model, primary});
  const item = serversModel(model), state = serversState(item);
  coreReplace(el, h("h3", null, T("servers.connection.selected")), h("p", {class: "technical"}, serversLabel(item || {tag: model})),
    serversBadge(item), item?.reachable && item?.match === false ? h("p", null, T("servers.mismatch.title")) : null,
    S.shell.serverError ? serversProblem(S.shell.serverError) : serversModelNote(item),
    h("button", {type: "button", class: primary ? "primary" : null,
      onclick: () => go("s06", {model: item?.tag || model, returnScreen: S.shell.route === "s09" ? "s09" : "s03"})},
      T(state === "connected" ? "servers.connection.details" : "context.prepare_model")));
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
  if (!S.shell.servers && !S.shell.serverError) await shellPollServers();
  const choice = serversData()?.rngd_choices?.find(item => item.tag === args.model || item.model === args.model);
  if (choice) S.servers.choice = choice.tag;
}
on("servers_changed", () => { if (!S.shell.serverError) S.servers.lock = null; serversRender(); });
shellDefineView("servers-summary", {load: serversEnsure, render: serversRenderSummary});
shellDefineView("servers-models", {render: serversRenderModels});
shellDefineView("servers-runpod", {render: serversRenderRunpod});
shellDefineView("servers-rngd", {render: serversRenderRngd});
shellDefineView("servers-log", {render: serversRenderLog});
