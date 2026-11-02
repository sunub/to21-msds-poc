"use strict";

// 자료 바꾸기(S11). 글은 UI_TEXT.swap만 읽는다. 검사는 파일을 옮기지 않고, 이 화면은 AI를 부르지 않는다.
S.swap = {view: "start", candidates: null, typed: "", check: null, busy: null, problem: null, applied: null, results: null,
  gold: null, goldProblem: null, goldChecking: false, goldCommit: null, goldNotice: null, goldReported: null};
const SWAP_SEEN = "b_app.swap.gold_seen";

function swapNote(error) {
  return friendlyError({message: error.body?.message || error.message, fix: error.body?.fix, raw: error.message});
}
function swapRender() {
  if (S.shell.route !== "s11") return;
  const views = {start: swapStart, pick: swapPick, check: swapCheckView, done: swapDone, gold: swapGold};
  const el = document.getElementById("swap-view");
  coreReplace(el, (views[S.swap.view] || swapStart)());
}
function swapTitle(key) {
  document.getElementById("title-s11").textContent = T(key);
}
function swapShow(view) {
  S.swap.view = view; S.swap.problem = null; swapRender();
  document.getElementById("title-s11").focus();
}
function swapRow(id, title, note, button, chip = null) {
  return h("div", {id, class: "swap-row"},
    h("div", null, h("strong", null, title), chip ? [" ", chip] : null, h("p", {class: "muted"}, note)), button);
}
function swapButton(label, onclick, primary = false, disabled = false) {
  return h("button", {type: "button", class: primary ? "primary" : null, onclick, disabled: disabled || null}, label);
}
function swapChip(label, good) {
  return h("span", {class: `swap-chip ${good ? "yes" : "no"}`}, label);
}
function swapSteps(current) {
  return h("ol", {class: "swap-steps", "aria-label": T("swap.steps.a11y")}, ["pick", "check", "apply"].map(step =>
    h("li", {"aria-current": step === current ? "step" : null}, T(`swap.steps.${step}`))));
}
function swapBack() {
  return swapButton(T("swap.back"), () => swapShow("start"));
}

function swapStart() {
  swapTitle("swap.start.title");
  return [h("p", {class: "muted"}, T("swap.start.lead")),
    swapRow("swap-new-docs", T("swap.start.docs_title"), T("swap.start.docs_note"),
      swapButton(T("swap.start.docs_action"), () => swapOpenPick(), true)),
    swapRow("swap-new-gold", T("swap.start.gold_title"), T("swap.start.gold_note"),
      swapButton(T("swap.start.gold_action"), () => swapOpenGold())),
    swapRow("swap-have", T("swap.start.have_title"), T("swap.start.have_note"),
      swapButton(T("swap.start.have_action"), shellOpenContext))];
}

async function swapLoadCandidates() {
  try { S.swap.candidates = await api("/api/swap/candidates"); S.swap.problem = null; }
  catch (error) { S.swap.candidates = null; S.swap.problem = error; }
}
async function swapOpenPick() {
  status("");
  await swapLoadCandidates();
  S.swap.view = "pick"; swapRender();
}
function swapPick() {
  swapTitle("swap.pick.title");
  const found = S.swap.candidates, typed = S.swap.typed;
  const input = h("input", {id: "swap-other-path", type: "text", placeholder: T("swap.pick.other_placeholder"), autocomplete: "off"});
  input.value = typed;
  const empty = found?.error ? T("swap.pick.unreadable") : T("swap.pick.empty");
  return [swapSteps("pick"), h("p", {class: "muted"}, T("swap.pick.lead")),
    S.swap.problem ? swapNote(S.swap.problem) : null,
    found?.items?.length ? h("div", {id: "swap-candidates"}, found.items.map(item =>
      swapRow(null, h("span", {class: "technical"}, item.name), T("swap.pick.meta", {count: item.docs, time: when(item.modified_at)}),
        swapButton(T("swap.pick.check"), () => swapCheck(item.path), false, S.swap.busy === "check"),
        swapChip(T(item.in_app ? "swap.pick.in_app" : "swap.pick.not_in_app"), item.in_app))))
      : h("p", {id: "swap-candidates"}, empty),
    h("div", {class: "swap-field"}, h("label", {for: "swap-other-path"}, T("swap.pick.other_label")),
      h("div", {class: "swap-actions"}, input, h("button", {id: "swap-other-check", type: "button", onclick: () => {
        const path = document.getElementById("swap-other-path").value.trim();
        S.swap.typed = path;
        if (path) swapCheck(path);
      }}, T("swap.pick.check")))),
    h("p", {class: "muted"}, T("swap.pick.other_hint")),
    S.swap.busy === "check" ? h("p", {role: "status"}, T("swap.check.checking")) : null,
    h("div", {class: "swap-actions"}, swapBack())];
}
async function swapCheck(path) {
  S.swap.busy = "check"; S.swap.problem = null; swapRender();
  try {
    S.swap.check = await post("/api/swap/check", {path});
    S.swap.view = "check";
  } catch (error) { S.swap.problem = error; S.swap.view = "pick"; }
  finally { S.swap.busy = null; swapRender(); }
}

function swapCan(good, text) {
  return h("li", null, swapChip(T(good ? "swap.check.yes" : "swap.check.no"), good), h("span", null, text));
}
function swapFact(label, ...value) {
  return [h("dt", null, label), h("dd", null, value)];
}
function swapLockedFact(info) {
  const lines = [info.locked.eval ? h("p", null, T("swap.check.locked_eval", {count: info.locked.eval})) : null,
    ...Object.entries(info.locked.same_as).map(([doc, twin]) => h("p", null, T("swap.check.locked_same", {doc, eval_doc: twin}))),
    info.locked.unknown ? h("p", null, T("swap.check.locked_unknown", {count: info.locked.unknown})) : null].filter(Boolean);
  return lines.length ? lines : T("swap.check.locked_none");
}
function swapCheckView() {
  const info = S.swap.check;
  swapTitle(`swap.check.title.${info.verdict}`);
  const conflict = info.existing.state === "different", same = info.existing.state === "same";
  const usable = info.verdict !== "unusable";
  const openDocs = info.batch_docs + info.no_line_numbers;
  return [swapSteps("check"), h("p", {class: "technical swap-name"}, info.name),
    S.swap.problem ? swapNote(S.swap.problem) : null,
    info.verdict === "format_only" ? h("div", {class: "swap-notice"}, h("strong", null, T("swap.check.no_overlap_title")),
      h("p", null, T("swap.check.no_overlap_body")),
      info.score_alternative ? h("p", null, T("swap.check.alternative", {count: info.score_alternative.docs, set: info.score_alternative.id})) : null) : null,
    !usable ? h("div", {class: "swap-notice"}, h("p", null, T("swap.check.unusable_body"))) : null,
    conflict ? h("div", {class: "swap-notice"}, h("strong", null, T("swap.check.target_conflict_title")),
      h("p", null, T("swap.check.target_conflict"))) : null,
    usable ? h("section", {class: "swap-panel"}, h("h2", null, T("swap.check.can_title")),
      h("ul", {class: "swap-can"},
        swapCan(true, T("swap.check.batch_yes", {count: info.batch_docs})),
        swapCan(info.score_docs > 0, info.score_docs ? T("swap.check.score_yes", {count: info.score_docs}) : T("swap.check.score_no")),
        swapCan(info.try_docs > 0, info.try_docs ? T("swap.check.try_yes", {count: info.try_docs}) : T("swap.check.try_no")))) : null,
    h("section", {class: "swap-panel"}, h("h2", null, T("swap.check.facts_title")),
      h("dl", {class: "swap-facts"},
        swapFact(T("swap.check.docs_label"), T("swap.check.docs_value", {count: info.docs_total})),
        swapFact(T("swap.check.lines_label"), info.no_line_numbers
          ? T("swap.check.lines_some", {count: info.no_line_numbers})
          : T("swap.check.lines_all", {count: openDocs})),
        swapFact(T("swap.check.locked_label"), swapLockedFact(info)),
        usable ? swapFact(T("swap.check.target_label"), h("span", {class: "technical"}, info.target), h("br"),
          h("span", {class: "muted"}, conflict ? T("swap.check.target_conflict_title") : T(same ? "swap.check.target_same" : "swap.check.target_new"))) : null,
        usable ? swapFact(T("swap.check.past_label"), T("swap.check.past_value")) : null)),
    usable && !conflict ? h("p", {class: "muted"}, T(same ? "swap.check.apply_note_same" : "swap.check.apply_note_new")) : null,
    S.swap.busy === "apply" ? h("p", {role: "status"}, T(same ? "swap.check.switching" : "swap.check.applying")) : null,
    h("div", {class: "swap-actions"},
      usable && !conflict ? swapButton(T("swap.check.apply"), swapApply, true, !!S.swap.busy) : null,
      swapButton(T("swap.check.other"), () => swapOpenPick()))];
}
async function swapApply() {
  const state = S.swap, previous = S.ctx.set;
  state.busy = "apply"; state.problem = null; swapRender();
  try {
    const done = await post("/api/swap/apply", {path: state.check.path});
    await shellLoadContext();
    if (!shellApplyContext({set: done.set_id, key: S.ctx.key})) throw new Error(T("context.unavailable"));
    state.applied = {set: done.set_id, previous: previous && previous !== done.set_id ? previous : null};
    state.results = null; state.view = "done";
    status(T("swap.done.title"));
    swapLoadResults(done.set_id);
  } catch (error) { state.problem = error; }
  finally { state.busy = null; swapRender(); }
}
// 저장된 결과를 읽는 데 시간이 걸릴 수 있어 완료 화면을 먼저 보이고 뒤이어 채운다.
async function swapLoadResults(set) {
  try {
    const found = (await shellContextResults(set, S.ctx.key)).runs.length;
    if (S.swap.applied?.set === set) { S.swap.results = found; swapRender(); }
  } catch (_) { /* 결과 개수만 빠진다. 문서 묶음은 이미 바뀌었다. */ }
}
function swapConnected() {
  return (S.shell.servers?.models || []).some(model => model.reachable && model.match);
}
function swapDone() {
  swapTitle("swap.done.title");
  const applied = S.swap.applied, on = swapConnected();
  return [swapSteps("apply"), applied ? h("p", {class: "technical swap-name"}, applied.set) : null,
    h("p", {class: "muted"}, T("swap.done.changed"), S.swap.results === null ? null : [" ",
      S.swap.results ? T("swap.done.results_found", {count: S.swap.results}) : T("swap.done.results_none")]),
    swapRow(null, T(on ? "swap.done.on_title" : "swap.done.off_title"), T(on ? "swap.done.on_note" : "swap.done.off_note"),
      swapButton(T(on ? "swap.done.on_action" : "swap.done.off_action"), () => go(on ? "s09" : "s06").catch(fail), true)),
    applied?.previous ? swapRow(null, T("swap.done.undo_title"), T("swap.done.undo_note", {set: applied.previous}),
      swapButton(T("swap.done.undo"), swapUndo)) : null];
}
function swapUndo() {
  const previous = S.swap.applied?.previous;
  if (!previous || !shellApplyContext({set: previous, key: S.ctx.key})) return;
  S.swap.applied = null;
  swapShow("start");
  status(T("swap.done.undone"));
}

function swapDate(value) {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? `${date.getMonth() + 1}/${date.getDate()}` : T("common.none");
}
function swapGoldQuery(fetchRemote) {
  const query = new URLSearchParams(), seen = coreRead(SWAP_SEEN, null);
  if (fetchRemote) query.set("fetch", "1");
  if (typeof seen === "string" && seen) query.set("since", seen);
  const text = query.toString();
  return `/api/swap/gold${text ? `?${text}` : ""}`;
}
function swapChangedCount(changed) {
  return (changed?.dev?.length || 0) + (changed?.eval || 0);
}
function swapRememberGold(gold, acknowledge) {
  const state = S.swap, sha = gold.commit?.sha;
  state.goldCommit = gold.commit || null;
  const changed = swapChangedCount(gold.changed);
  if (!sha) return false;
  if (!coreRead(SWAP_SEEN, null) || acknowledge) {
    coreWrite(SWAP_SEEN, sha); state.goldNotice = null;
  } else if (changed) state.goldNotice = changed;
  return changed > 0;
}
async function swapRereadScores() {
  await shellLoadContext();
  emit("context_changed", {...S.ctx});
}
async function swapLoadGold() {
  const state = S.swap;
  state.goldChecking = true; state.goldProblem = null; swapRender();
  try {
    const gold = await api(swapGoldQuery(true));
    const changed = swapRememberGold(gold, true);
    state.gold = gold;
    if (changed) state.goldReported = gold.changed;
    shellRenderContext();
    if (changed) await swapRereadScores();
  } catch (error) { state.goldProblem = error; }
  finally { state.goldChecking = false; swapRender(); }
}
async function swapOpenGold() {
  status("");
  S.swap.view = "gold"; swapRender();
  await swapLoadGold();
}
function swapGoldBehind(gold) {
  return gold.behind.dev.length + gold.behind.eval > 0;
}
function swapGoldRemote(gold) {
  if (gold.fetched === false) return h("p", {id: "swap-gold-remote", class: "swap-notice"}, T("swap.gold.offline"));
  if (swapGoldBehind(gold)) return h("div", {id: "swap-gold-remote", class: "swap-notice"},
    h("strong", null, T("swap.gold.behind_title", {dev: gold.behind.dev.length, eval_docs: gold.behind.eval})),
    h("p", null, T("swap.gold.behind_body")),
    gold.branch !== "main" ? h("p", null, T("swap.gold.branch_note", {branch: gold.branch})) : null,
    h("pre", {class: "technical"}, gold.pull));
  return gold.fetched ? h("p", {id: "swap-gold-remote"}, T("swap.gold.latest")) : null;
}
function swapGold() {
  swapTitle("swap.gold.title");
  const state = S.swap, gold = state.gold;
  const selected = S.shell.keys.find(key => key.id === S.ctx.key);
  const mainGold = S.shell.keys.find(key => key.id === "gold" && key.usable);
  const reported = state.goldReported;
  return [h("p", {class: "muted"}, T("swap.gold.lead")),
    reported && swapChangedCount(reported) ? h("div", {class: "swap-notice"},
      h("strong", null, T("swap.gold.changed_title", {dev: reported.dev.length, eval_docs: reported.eval})),
      reported.dev.length ? h("p", null, T("swap.gold.changed_docs", {docs: reported.dev.join(", ")})) : null) : null,
    state.goldProblem ? swapNote(state.goldProblem) : null,
    state.goldChecking ? h("p", {role: "status"}, T("swap.gold.checking")) : null,
    gold ? h("section", {class: "swap-panel"}, h("h2", null, T("swap.gold.now_title")),
      h("dl", {class: "swap-facts"},
        swapFact(T("swap.gold.name_label"), T("swap.gold.name_value"), " ", h("span", {class: "technical"}, gold.path)),
        swapFact(T("swap.gold.commit_label"), gold.commit
          ? [when(gold.commit.at), " ", h("span", {class: "technical"}, gold.commit.sha)] : T("swap.gold.commit_none")),
        swapFact(T("swap.gold.docs_label"), T("swap.gold.docs_value", {count: gold.docs})),
        swapFact(T("swap.gold.eval_label"), T("swap.gold.eval_value", {count: gold.eval_docs})),
        swapFact(T("swap.gold.selected_label"), selected?.label || T("common.none")))) : null,
    gold && S.ctx.key !== "gold" ? h("div", {class: "swap-notice"}, h("p", null, T("swap.gold.other_selected")),
      mainGold ? swapButton(T("swap.gold.use_gold"), swapUseGold) : null) : null,
    gold ? swapGoldRemote(gold) : null,
    h("p", null, T("swap.gold.after")),
    h("div", {class: "swap-actions"}, swapButton(T("swap.gold.recheck"), swapLoadGold, true, state.goldChecking),
      swapButton(T("swap.gold.open_scores"), () => go("s01").catch(fail)), swapBack())];
}
function swapUseGold() {
  if (shellApplyContext({set: S.ctx.set, key: "gold"})) swapRender();
}

// 윗줄의 정답 칸. 켤 때와 다시 그릴 때 부른다. 켤 때는 네트워크를 부르지 않는다.
function swapRenderContextNote() {
  const el = document.getElementById("context-answer-note");
  if (!el) return;
  const state = S.swap, current = S.shell.keys.find(key => key.id === S.ctx.key);
  const note = current?.id === "gold" && state.goldCommit ? T("swap.context.gold_note",
    {date: swapDate(state.goldCommit.at), count: current.docs?.length ?? 0}) : null;
  coreReplace(el, note ? h("small", {class: "context-note", "data-tip": note}, note) : null);
  // 좁은 창에서는 막대에서 날짜 글이 빠지므로 정답 칩의 말풍선에도 둔다.
  const chip = document.getElementById("context-change-key");
  if (chip) {
    if (chip.getAttribute("data-tip-base") == null) chip.setAttribute("data-tip-base", chip.getAttribute("data-tip") || "");
    chip.setAttribute("data-tip", [chip.getAttribute("data-tip-base"), note].filter(Boolean).join("\n"));
  }
  // 새 정답 알림은 점수를 바꾸는 일이라 막대 아래 줄에 다 보인다. 알림이 있을 때만 줄이 생긴다.
  coreReplace(document.getElementById("context-gold-notice"),
    state.goldNotice ? h("p", {class: "swap-gold-changed"}, T("swap.context.gold_changed", {count: state.goldNotice}), " ",
      h("button", {id: "context-gold-open", class: "text-button", type: "button",
        onclick: () => go("s11", {swapView: "gold"}).catch(fail)}, T("swap.context.gold_changed_open"))) : null);
}
async function swapWatchGold() {
  try {
    const gold = await api(swapGoldQuery(false));
    const changed = swapRememberGold(gold, false);
    await S.shell.contextReady;
    if (changed && coreRead(SWAP_SEEN, null) !== gold.commit?.sha) await swapRereadScores();
    swapRenderContextNote();
  } catch (_) { /* 정답 상태를 못 읽어도 다른 화면은 그대로 쓴다. S11을 열면 이유를 보인다. */ }
}
on("context_rendered", swapRenderContextNote);
on("shell_started", swapWatchGold);
shellDefineView("swap-view", {
  load: async (args = {}) => {
    if (args.swapView) S.swap.view = args.swapView;
    if (S.swap.view === "pick") await swapLoadCandidates();
  },
  render: () => {
    swapRender();
    if (S.swap.view === "gold" && !S.swap.goldChecking) swapLoadGold().catch(fail);
  }
});
