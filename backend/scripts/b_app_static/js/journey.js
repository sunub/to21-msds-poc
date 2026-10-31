"use strict";

// 저장 자료와 화면의 대상·준비 상태를 분리한다. 서버로 보내는 것은 S.journey뿐이다.
function journeyDefault() {
  return {version: 2, progress: {active: null, dismissed_at: null,
    t1: {state: "not_started", step: 0, updated_at: null}, t2: {state: "not_started", step: 0, updated_at: null}},
  outcomes: {t1: {real: null}, t2: {real: null, practice: null}}, pending: null, migrated_from: null};
}
S.journey = journeyDefault();
S.journeyUI = {started: false, read: null, readSeq: 0, known: false, revision: 0, dirty: false, unsaved: false, writing: null,
  storageNotice: null, problems: null, target: null, phase: 1, blocked: null, notice: null,
  run: null, runsLoading: false, runsLoaded: false, runsError: null, runsSeq: 0,
  pendingJob: null, pendingError: null, seen: new Set(), optionsRevision: 0, modelAfter: 0,
  trialReady: false, modelReady: false, trialSignature: null, bandReason: null};
const journeyClone = value => JSON.parse(JSON.stringify(value));
const journeyTime = () => new Date().toISOString();
function journeyProgressDefault(p) {
  return p.active === null && p.dismissed_at === null && ["t1", "t2"].every(t =>
    p[t].state === "not_started" && p[t].step === 0 && p[t].updated_at === null);
}
function journeyPristine() {
  return journeyProgressDefault(S.journey.progress) && !S.journey.pending &&
    !S.journey.outcomes.t1.real && !S.journey.outcomes.t2.real && !S.journey.outcomes.t2.practice;
}
function journeyNotice(error, op) {
  const u = S.journeyUI;
  if (!u.storageNotice) {
    u.storageNotice = {message: T("journey.save_failed.title"),
      fix: error.status === 400 ? (error.body?.message || error.body?.error || error.message) : T("journey.save_failed.todo")};
    emit("journey_storage_unavailable", {op});
  }
}
function journeyProblems(problems) {
  if (problems?.length && !S.journeyUI.problems) S.journeyUI.problems = problems.map(p => p.message).filter(Boolean);
}
function journeyMergeOutcomes(remote) {
  for (const track of ["t1", "t2"]) for (const kind of Object.keys(S.journey.outcomes[track])) {
    const a = S.journey.outcomes[track][kind], b = remote.outcomes?.[track]?.[kind];
    if (!b) continue;
    if (!a) S.journey.outcomes[track][kind] = journeyClone(b);
    else S.journey.outcomes[track][kind] = {...(a.last_at >= b.last_at ? a : b),
      first_at: a.first_at < b.first_at ? a.first_at : b.first_at,
      last_at: a.last_at > b.last_at ? a.last_at : b.last_at, count: Math.max(a.count, b.count)};
  }
  if (remote.migrated_from === 1) S.journey.migrated_from = 1;
}
function journeyChange(change) {
  change(S.journey); S.journeyUI.revision++; S.journeyUI.readSeq++; S.journeyUI.dirty = true; S.journeyUI.unsaved = true;
  journeyRender(); return journeySave();
}
function journeySave() {
  const u = S.journeyUI;
  if (u.writing) return u.writing;
  u.writing = (async () => {
    while (u.dirty) {
      u.dirty = false;
      const revision = u.revision, snapshot = journeyClone(S.journey);
      try {
        const response = await api("/api/journey", {method: "PUT", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({journey: snapshot})});
        if (revision === u.revision) {S.journey = response.journey; u.unsaved = false;}
        else journeyMergeOutcomes(response.journey);
        journeyProblems(response.problems);
      } catch (error) { journeyNotice(error, "write"); }
      journeyRender();
    }
  })().finally(() => { u.writing = null; });
  return u.writing;
}
function journeyMigrate() {
  if (S.journey.migrated_from !== null) return;
  let old;
  try { old = JSON.parse(localStorage.getItem("b_app.journey")); } catch (_) { return; }
  if (old?.version !== 1 || !Number.isInteger(old.last_step) || old.last_step < 0 || old.last_step > 3 ||
      typeof old.dismissed !== "boolean" || typeof old.completed !== "boolean" ||
      !(old.first_success_at === null || (typeof old.first_success_at === "string" && Number.isFinite(Date.parse(old.first_success_at)))) ||
      !(old.completed ? old.last_step === 3 && old.first_success_at !== null : old.last_step < 3 && old.first_success_at === null)) return;
  journeyChange(j => {
    const now = journeyTime(), original = journeyProgressDefault(j.progress);
    if (old.completed) {
      const at = new Date(old.first_success_at).toISOString();
      journeyMergeOutcomes({outcomes: {t1: {real: {first_at: at, last_at: at, count: 1}}}});
      if (original) j.progress.t1 = {state: "completed", step: 3, updated_at: at};
    } else if (original && old.last_step > 0) {
      j.progress.t1 = {state: "in_progress", step: old.last_step, updated_at: now}; j.progress.active = "t1";
    }
    if (original && old.dismissed) { j.progress.dismissed_at = now; j.progress.active = null; }
    j.migrated_from = 1;
  });
  emit("journey_migrated", {from: 1});
}
function journeyEnsure() {
  if (S.journeyUI.started) return S.journeyUI.read || Promise.resolve();
  S.journeyUI.started = true; return journeyLoad();
}
async function journeyLoad() {
  const u = S.journeyUI;
  // 아직 보내지 못한 변경을 GET으로 덮지 않는다.
  if (u.writing) await u.writing;
  const request = ++u.readSeq;
  u.read = (async () => {
    try {
      const response = await api("/api/journey");
      if (request !== u.readSeq) return;
      if (u.unsaved) journeyMergeOutcomes(response.journey);
      else S.journey = response.journey;
      u.known = true;
      journeyProblems(response.problems); journeyMigrate();
      await journeyCheckPending();
    } catch (error) { if (request === u.readSeq) journeyNotice(error, "read"); }
    journeyRender();
  })();
  return u.read;
}
async function journeyCheckPending() {
  const u = S.journeyUI, pending = S.journey.pending;
  if (!pending) { u.pendingJob = null; return; }
  if (!pending.job) {
    u.notice = "journey.pending.unknown"; journeyChange(j => {j.pending = null;}); return;
  }
  try {
    const data = await api("/api/jobs");
    if (S.journey.pending?.job !== pending.job) return;
    u.pendingJob = (data.jobs || []).find(job => job.id === pending.job) || null; u.pendingError = null;
    if (!u.pendingJob) { u.notice = "journey.pending.not_found"; journeyChange(j => {j.pending = null;}); }
  } catch (error) { u.pendingError = error.message; }
}
async function journeyLoadRuns() {
  const u = S.journeyUI, request = ++u.runsSeq, key = S.ctx.key, set = S.ctx.set;
  u.runsLoading = true; u.runsError = null; u.run = null; journeyRender();
  try {
    const list = await api(ctxUrl("/api/runs"));
    const runs = (list.runs || []).filter(r => !r.error && r.set?.id === set && r.run_kind !== "silver");
    const current = runs.find(r => r.name === list.current) || runs.at(-1);
    const run = current ? await api(ctxUrl("/api/run/" + current.name.split("/").map(encodeURIComponent).join("/"))) : null;
    if (request !== u.runsSeq || key !== S.ctx.key || set !== S.ctx.set) return;
    u.run = run; u.runsLoaded = true;
  } catch (error) { if (request === u.runsSeq) u.runsError = error.message; }
  finally { if (request === u.runsSeq) {u.runsLoading = false; journeyRender();} }
}
function journeyConfirm(track, step) {
  const p = S.journey.progress[track];
  if (S.journey.progress.active !== track || p.state !== "in_progress" || p.step >= step) return;
  journeyChange(j => {j.progress[track].step = step; j.progress[track].updated_at = journeyTime();});
  emit("onboarding_step_confirmed", {track, step});
}
function journeyRecord(track, kind, job = null) {
  const previous = S.journey.outcomes[track][kind], id = `${track}:${kind}:${job}`;
  if (track === "t2" && (!job || previous?.last_job === job || S.journeyUI.seen.has(id))) return false;
  if (track === "t2") S.journeyUI.seen.add(id);
  const now = journeyTime();
  journeyChange(j => {j.outcomes[track][kind] = {first_at: previous?.first_at || now, last_at: now,
    count: (previous?.count || 0) + 1, ...(track === "t2" ? {last_job: job} : {})};});
  emit(kind === "practice" ? "practice_recorded" : "first_success_recorded",
    {track, first: !previous, in_guide: S.journey.progress.active === track});
  return true;
}
function journeyComplete(track) {
  if (S.journey.progress.active !== track) return;
  journeyChange(j => {j.progress[track] = {state: "completed", step: track === "t1" ? 3 : 4, updated_at: journeyTime()};
    if (track === "t2") j.pending = null;});
  emit("onboarding_track_completed", {track});
}
function journeyDetach(reason) {
  if (!S.journey.pending) return;
  emit("attempt_detached", {mode: S.journey.pending.mode, why: reason});
  S.journey.pending = null; S.journeyUI.pendingJob = null;
}
function journeyDismiss() {
  journeyChange(j => {j.progress.dismissed_at = journeyTime(); j.progress.active = null;});
  S.journeyUI.blocked = null; journeyRender(); emit("onboarding_dismissed", {where: S.shell.route || "band"});
}
function journeySkip() {
  const track = S.journey.progress.active;
  journeyChange(j => {if (track) {j.progress[track].state = "skipped"; j.progress[track].updated_at = journeyTime();}
    j.progress.active = null; journeyDetach("skip");});
  S.journeyUI.notice = "journey.skipped.title"; journeyRender(); emit("onboarding_track_skipped", {track});
}
on("help_replay", () => {journeyReplay().catch(fail);});
function journeyReplay() {
  journeyChange(j => {j.progress = journeyDefault().progress; journeyDetach("replay");});
  const u = S.journeyUI; u.target = null; u.blocked = null; u.notice = null; u.phase = 1;
  emit("onboarding_replayed", {had_real: !!(S.journey.outcomes.t1.real || S.journey.outcomes.t2.real), had_practice: !!S.journey.outcomes.t2.practice});
  return go("s08", {entry: "help_replay"});
}
function journeyMarkTarget() {
  document.querySelectorAll(".journey-target").forEach(el => el.classList.remove("journey-target"));
  document.querySelectorAll(".journey-target-label").forEach(el => el.remove());
  const u = S.journeyUI;
  if (!S.journey.progress.active || S.shell.route !== u.anchorScreen || !u.anchor) return null;
  const target = document.querySelector(`[data-guide="${u.anchor}"]`);
  if (!target) return null;
  target.classList.add("journey-target"); target.setAttribute("tabindex", "-1");
  target.parentElement.append(h("span", {class: "journey-target-label"}, T("journey.steps.target")));
  return target;
}
async function journeyGo(screen, anchor, args = {}) {
  await go(screen, args);
  if (S.shell.route !== screen) return;
  S.journeyUI.anchor = anchor; S.journeyUI.anchorScreen = screen;
  const target = journeyMarkTarget() || document.querySelector(`[data-guide="${anchor}"]`);
  if (!target) {S.journeyUI.blocked = "anchor"; journeyRender(); return;}
  for (let p = target.parentElement; p; p = p.parentElement) if (p.tagName.toLowerCase() === "details") p.open = true;
  target.setAttribute("tabindex", "-1"); target.focus();
  S.journeyUI.blocked = null; journeyRender();
}
async function journeyStart(track, practice = false) {
  await journeyEnsure();
  const u = S.journeyUI, old = S.journey.progress[track], resumed = old.state === "in_progress";
  if (track === "t1") {
    await journeyLoadRuns();
    if (!u.run || !num(u.run.weighted) || !S.shell.keys.some(k => k.id === S.ctx.key && k.usable)) return;
  }
  const missing = resumed && (track === "t1" ? !u.target : !S.jobs.t.doc);
  u.phase = resumed && !missing ? Math.min(old.step + 1, track === "t1" ? 3 : 4) : 1;
  u.blocked = null; u.notice = missing ? (track === "t1" ? "journey.start.resume" : "journey.resume.reselect") : null;
  journeyChange(j => {j.progress.active = track; j.progress.dismissed_at = null;
    j.progress[track] = {state: "in_progress", step: resumed && !missing ? old.step : 0, updated_at: journeyTime()};});
  emit("onboarding_track_started", {track, resumed, from_step: S.journey.progress[track].step});
  if (track === "t1") return u.phase === 3 && u.target ? journeyGo("s02", "s02-diff-values", {...u.target, pick: "mismatch"})
    : journeyGo("s01", u.phase === 2 ? "s01-top-problem" : "s01-score");
  const t = u.target;
  return journeyGo("s03", "s03-target", {journeyPrepare: !resumed || missing, practice,
    ...(t ? {doc: t.doc, section: t.section, base_run: t.run} : {})});
}
async function journeyNext() {
  const u = S.journeyUI, track = S.journey.progress.active, p = S.journey.progress[track];
  if (!p) return;
  if (track === "t1") {
    if (u.phase === 1 && p.step >= 1) {u.phase = 2; return journeyGo("s01", "s01-top-problem");}
    const t = u.target;
    if (!t) return;
    if (u.phase === 2) emit("problem_opened", t);
    return journeyGo("s02", "s02-diff-values", {...t, pick: "mismatch"});
  }
  if (u.phase === 1 && u.trialReady) {
    u.phase = 2; u.modelAfter = u.optionsRevision + 1;
    return journeyGo("s03", "s03-model", {journeyCheck: true});
  }
  if (u.phase === 2 && u.modelReady) {u.phase = 3; return journeyGo("s03", "s03-send", {practice: false});}
  if (S.journey.pending?.job) return journeyOpenPending();
  return journeyGo("s03", "s03-send");
}
function journeyOpenPending() {
  const id = S.journey.pending?.job;
  if (!id) return go("s05");
  return journeyGo("s03", "s03-result-summary", {job: id, resumePending: true});
}
function journeyButton(id, key, action, disabled = false) {
  return h("button", {id, type: "button", disabled, onclick: () => Promise.resolve(action()).catch(fail)}, T(key));
}
function journeyParagraph(key, values) {return h("p", null, T(key, values));}
function journeyRenderBand() {
  const u = S.journeyUI, j = S.journey, el = document.getElementById("journey-band");
  if (!el) return;
  let reason = null, content = [];
  if (u.known && j.pending?.job) {
    reason = "pending_result";
    const state = u.pendingJob?.status;
    content = [state === "failed" && u.pendingJob.error ? friendlyError(u.pendingJob.error)
      : journeyParagraph(state === "done" ? "journey.pending.title" : state === "running" ? "journey.band.running"
        : state === "stopped" ? "jobs.stopped.fact" : "journey.pending.unknown"),
      u.pendingError ? loadFailure(u.pendingError) : null,
      journeyButton("journey-open-pending", u.pendingJob?.status === "done" ? "journey.pending.open_result" : "nav.open_jobs",
        () => u.pendingJob?.status === "done" ? journeyOpenPending() : go("s05"))];
  } else if (u.known && j.progress.active && j.progress[j.progress.active].state === "in_progress") {
    const track = j.progress.active, total = track === "t1" ? 3 : 4;
    reason = "resume";
    content = [journeyParagraph("journey.band.resume", {track: track.slice(1), total, step: Math.min(j.progress[track].step + 1, total)}),
      journeyButton("journey-resume", "journey.resume.action", () => journeyStart(track))];
  } else if (u.known && journeyPristine()) {
    reason = "first_visit";
    content = [h("h2", null, T("journey.band.title")), journeyParagraph("journey.band.read"), journeyParagraph("journey.band.trial"),
      journeyButton("journey-open", "journey.band.open", () => go("s08", {entry: "band"})), journeyParagraph("journey.band.closed")];
  }
  el.hidden = !reason; coreReplace(el, content, reason ? journeyButton("journey-band-dismiss", "journey.start.dismiss", journeyDismiss) : null);
  if (reason && reason !== u.bandReason && S.shell.route === "s01") {u.bandReason = reason; emit("onboarding_band_shown", {reason});}
}
function journeyRenderRecords() {
  const j = S.journey;
  const cell = o => o ? T("journey.history.first_count", {time: new Date(o.first_at).toLocaleString(), count: o.count}) : T("journey.history.none");
  coreReplace(document.getElementById("journey-records"), h("h2", null, T("journey.history.title")),
    h("table", null, h("thead", null, h("tr", null, ["journey.track", "journey.history.real_success", "journey.practice", "common.action"].map(k => h("th", {scope: "col"}, T(k))))),
      h("tbody", null, ["t1", "t2"].map(track => h("tr", null,
        h("th", {scope: "row"}, T(track === "t1" ? "journey.history.read_track" : "journey.history.trial_track")),
        h("td", null, cell(j.outcomes[track].real)), h("td", null, track === "t2" ? cell(j.outcomes.t2.practice) : T("common.none")),
        h("td", null, journeyButton(`journey-record-${track}`, j.outcomes[track].real ? "journey.replay.start" : j.progress[track].state === "in_progress" ? "journey.resume.action" : track === "t1" ? "journey.choice.start_read" : "journey.choice.start_trial", () => journeyStart(track))))))),
    journeyParagraph("journey.history.replay_progress"), journeyParagraph("journey.history.keep_outcomes"), journeyParagraph("journey.replay.keep_job"),
    journeyButton("journey-replay", "journey.start.replay", journeyReplay), journeyButton("journey-dismiss", "journey.start.dismiss", journeyDismiss));
}
function journeyConnection(place) {
  const u = S.journeyUI; u.connections ||= {};
  const el = u.connections[place] ||= h("div", {class: "journey-connection"});
  serversRenderCompact(el, {model: S.jobs.t.model}); return el;
}
function journeyRenderChoice() {
  const u = S.journeyUI, key = S.shell.keys.find(k => k.id === S.ctx.key), ready = u.run && num(u.run.weighted) && key?.usable;
  const note = u.runsError ? loadFailure(u.runsError) : journeyParagraph(u.runsLoading || !u.runsLoaded ? "journey.start.loading"
    : !u.run ? "journey.start.empty" : !num(u.run.weighted) ? "journey.start.unscored" : "journey.choice.read_ready");
  const connection = journeyConnection("choice");
  coreReplace(document.getElementById("journey-choice"), h("h2", null, T("journey.choice.title")),
    h("div", {class: "journey-choices"},
      h("div", {class: "journey-choice"}, h("h3", null, T("journey.choice.read_title")), journeyParagraph("journey.choice.read_action"),
        journeyParagraph("journey.choice.read_success"), journeyParagraph("journey.steps.count", {count: Object.keys(UI.journey.tracks.t1.steps).length}), note,
        key?.usable === false ? friendlyError({message: T("journey.read.key_unusable"), fix: key.reason || T("journey.read.key_todo")}) : null,
        journeyButton("journey-start-t1", "journey.choice.start_read", () => journeyStart("t1"), !ready || u.runsLoading),
        journeyButton("journey-runs-retry", "score.partial.reload", journeyLoadRuns)),
      h("div", {class: "journey-choice"}, h("h3", null, T("journey.choice.trial_title")), journeyParagraph("journey.choice.trial_action"),
        journeyParagraph("journey.choice.trial_success"), journeyParagraph("journey.steps.count", {count: Object.keys(UI.journey.tracks.t2.steps).length}), connection,
        journeyButton("journey-start-t2", "journey.choice.start_trial", () => journeyStart("t2")),
        journeyParagraph("journey.choice.practice"), journeyParagraph("journey.history.keep_outcomes"),
        journeyButton("journey-practice", "jobs.actions.preview", () => journeyStart("t2", true)))),
    journeyButton("journey-skip-all", "journey.choice.skip", () => {journeyDismiss(); return go("s01");}));
}
function journeyRenderStrip() {
  const j = S.journey, u = S.journeyUI, track = j.progress.active, el = document.getElementById("journey-strip");
  const p = track ? j.progress[track] : null;
  el.hidden = !track && !u.notice;
  if (!track) {coreReplace(el, u.notice ? journeyParagraph(u.notice) : null, u.notice ? journeyParagraph("journey.pending.todo") : null); return;}
  const total = Object.keys(UI.journey.tracks[track].steps).length, phase = Math.min(u.phase, total);
  const complete = p.state === "completed" && !!j.outcomes[track].real;
  let instruction = UI.journey.tracks[track].steps[String(phase)];
  const children = [h("strong", null, T("journey.steps.position", {track: track.slice(1), total, step: phase})),
    h("p", null, complete ? T(track === "t1" ? "journey.read.completed" : "journey.trial.completed") : instruction),
    h("ol", {class: "journey-steps"}, Object.values(UI.journey.tracks[track].steps).map((text, i) => h("li", {"aria-current": !complete && i + 1 === phase ? "step" : null},
      text, " — ", i < p.step ? T("journey.steps.done") : i + 1 === phase ? T("journey.start.current") : T("journey.history.none"))))];
  if (u.notice) children.push(journeyParagraph(u.notice));
  if (u.blocked === "anchor") children.push(friendlyError({message: T("journey.target_missing.title"), fix: T("journey.target_missing.todo")}));
  if (u.blocked === "parse") children.push(friendlyError({message: T("journey.trial.parse_failed"), fix: T("journey.trial.parse_todo")}),
    journeyButton("journey-retry-result", "jobs.result.retry", () => journeyGo("s03", "s03-result-summary", {job: u.failedJob})));
  if (u.blocked === "same" || u.blocked === "other") children.push(journeyParagraph(`journey.read.${u.blocked}`));
  if (!complete && track === "t1") {
    if (phase === 1) children.push(journeyParagraph("journey.read.two_targets"));
    if (phase > 1 && !u.target) children.push(journeyParagraph(u.run?.status_text?.top_problem ? "journey.unlinked.reason" : "journey.start.no_problem"),
      journeyButton("journey-items", "journey.unlinked.open_items", () => journeyGo("s01", "s01-top-problem")));
    if (phase === 3 && u.blocked === "line") children.push(journeyParagraph("journey.start.no_line"));
    children.push(journeyButton("journey-next", phase === 1 ? "journey.read.next_problem" : "score.summary.open_source", journeyNext,
      phase === 1 ? p.step < 1 : !u.target));
  } else if (!complete) {
    if (phase === 1 && !u.trialReady) children.push(journeyParagraph("journey.trial.single_only"));
    if (phase === 2) {
      const connection = journeyConnection("strip"); children.push(connection,
        journeyParagraph("journey.trial.fresh_reply"), journeyButton("journey-model-refresh", "jobs.form.reload", () => journeyGo("s03", "s03-model", {journeyCheck: true})),
        journeyButton("journey-practice-step", "jobs.actions.preview", () => journeyGo("s03", "s03-practice", {practice: true})));
    }
    if (j.outcomes.t2.practice) children.push(journeyParagraph("journey.history.first_count", {time: T("journey.practice"), count: j.outcomes.t2.practice.count}), journeyParagraph("journey.trial.practice_stay"));
    children.push(journeyButton("journey-next", phase === 1 ? "journey.trial.next_model" : phase === 2 ? "journey.trial.continue_ready" : phase === 3 ? "nav.retest" : "journey.pending.open_result",
      journeyNext, phase === 1 ? !u.trialReady : phase === 2 ? !u.modelReady : false));
  } else children.push(journeyButton("journey-done-next", track === "t1" ? "journey.choice.start_trial" : "journey.skipped.open_recent", () => track === "t1" ? journeyStart("t2") : go("s01")));
  children.push(journeyParagraph(track === "t1" ? "journey.choice.read_success" : "journey.choice.trial_success"),
    journeyParagraph(track === "t1" ? "journey.steps.skip_read" : "journey.steps.skip_trial"),
    h("div", {class: "journey-actions"}, journeyButton("journey-skip", "journey.skip", journeySkip),
      journeyButton("journey-close-strip", "journey.start.dismiss", journeyDismiss), journeyButton("journey-back", "journey.target_missing.back", () => go("s08"))));
  coreReplace(el, children);
}
function journeyRender() {
  const active = document.activeElement?.id;
  journeyRenderBand(); journeyRenderChoice(); journeyRenderRecords(); journeyRenderStrip();
  const u = S.journeyUI;
  coreReplace(document.getElementById("journey-notices"),
    u.storageNotice ? h("div", {"data-notice": "storage"}, friendlyError(u.storageNotice), journeyParagraph("journey.save_failed.continue")) : null,
    u.problems ? h("div", {"data-notice": "problems", role: "status"}, journeyParagraph("journey.partial_record.title"),
      u.problems.map(text => h("p", null, text)), journeyParagraph("journey.partial_record.todo")) : null);
  if (active && document.activeElement?.isConnected === false) document.getElementById(active)?.focus({preventScroll: true});
  journeyMarkTarget();
}
on("shell_started", () => {journeyEnsure();});
on("screen_shown", ({screen, args}) => {
  const u = S.journeyUI;
  if (screen === "s08") emit("onboarding_opened", {entry: args.entry || "top_link"});
  if (screen === "s02" && u.target && S.source.run === u.target.run && S.source.doc === u.target.doc &&
      S.source.section === u.target.section && S.source.item === u.target.item && S.source.data?.lines?.length) {
    journeyConfirm("t1", 2); if (S.journey.progress.active === "t1") u.phase = 3;
    const linked = S.source.data.values.some(v => v.section === u.target.section && v.items?.includes(u.target.item) &&
      v.silver?.same === false && v.lines?.some(id => S.source.line[id]));
    if (!linked) u.blocked = "line";
  }
  journeyRender();
});
on("score_summary_shown", e => {
  const u = S.journeyUI;
  if (S.shell.route !== "s01" || e.run !== S.score.run?.name || e.key !== S.ctx.key || !num(e.weighted)) return;
  u.run = S.score.run;
  const top = u.run.status_text?.top_problem;
  u.target = top?.section && top.docs?.[0]?.doc_id ? {run: e.run, doc: top.docs[0].doc_id, section: top.section, item: top.name} : null;
  u.fromProblem = false; journeyConfirm("t1", 1); journeyRender();
});
on("problem_opened", e => {
  if (e.item !== S.score.run?.status_text?.top_problem?.name) return;
  S.journeyUI.target = {...e}; S.journeyUI.fromProblem = true;
  S.journeyUI.readAttempt = (S.journeyUI.readAttempt || 0) + 1;
});
on("evidence_line_shown", e => {
  const u = S.journeyUI, t = u.target;
  if (!t || !u.fromProblem) return;
  if (["run", "doc", "section", "item"].some(k => e[k] !== t[k])) {u.blocked = "other"; journeyRender(); return;}
  if (e.mismatch !== true) {u.blocked = "same"; journeyRender(); return;}
  const id = JSON.stringify([u.readAttempt, e.run, e.doc, S.ctx.key, e.path]);
  if (u.seen.has(id)) return;
  u.seen.add(id); u.blocked = null; u.phase = 3; journeyRecord("t1", "real"); journeyComplete("t1"); journeyRender();
});
on("try_result_viewed", e => {
  if (!e.job || !["real", "practice"].includes(e.mode)) return;
  const u = S.journeyUI, attached = S.journey.pending?.job === e.job;
  if (e.mode === "real" && e.section_ok !== true) {u.blocked = "parse"; u.failedJob = e.job; journeyRender(); return;}
  const recorded = journeyRecord("t2", e.mode === "practice" ? "practice" : "real", e.job);
  if (!recorded) return;
  u.blocked = null;
  if (e.mode === "real" && attached) {u.phase = 4; journeyComplete("t2");}
  if (attached && S.journey.pending) journeyChange(j => {j.pending = null;});
  journeyRender();
});
on("trial_options_checked", () => {S.journeyUI.optionsRevision++;});
on("trial_form_shown", e => {
  const u = S.journeyUI;
  u.trialReady = e.valid; u.modelReady = e.connected && u.optionsRevision >= u.modelAfter;
  if (S.journey.progress.active !== "t2") return;
  if (u.trialSignature && u.trialSignature !== e.signature && S.journey.pending) {
    journeyChange(() => journeyDetach("target_changed")); u.notice = "journey.detached.title";
  }
  u.trialSignature = e.signature;
  if (u.phase === 1 && e.valid) journeyConfirm("t2", 1);
  if (u.phase === 2 && e.valid && u.modelReady) journeyConfirm("t2", 2);
  journeyRender();
});
on("attempt_started", e => {
  if (S.journey.progress.active !== "t2" || !e.single) return;
  S.journeyUI.blocked = null;
  journeyChange(j => {j.pending = {attempt: e.attempt, job: null, mode: e.mode, started_at: journeyTime()};});
});
on("attempt_accepted", e => {
  if (S.journey.pending?.attempt !== e.attempt) return;
  journeyChange(j => {j.pending.job = e.job;});
});
on("trial_jobs_changed", ({jobs}) => {
  const pending = S.journey.pending;
  if (!pending?.job) return;
  S.journeyUI.pendingJob = jobs.find(job => job.id === pending.job) || null;
  const job = S.journeyUI.pendingJob;
  if (job && pending.mode === "real" && job.dry_run === false && ["running", "done"].includes(job.status)) {
    journeyConfirm("t2", 3); S.journeyUI.phase = 4;
  }
  if (job?.status === "stopped") journeyChange(j => {j.pending = null;});
  journeyRender();
});
on("attempt_cancelled", e => {if (S.journey.pending?.job === e.job) journeyChange(j => {j.pending = null;});});
on("context_changed", () => {
  const u = S.journeyUI; u.target = null; u.fromProblem = false; u.runsSeq++; u.runsLoaded = false; u.run = null;
  if (S.journey.progress.active) journeyChange(j => {const t = j.progress.active; j.progress[t].step = 0; j.progress[t].state = "in_progress"; journeyDetach("context_changed");});
  u.phase = 1; if (S.shell.route === "s08") journeyLoadRuns(); journeyRender();
});
on("servers_changed", journeyRender);
document.addEventListener("visibilitychange", () => {if (document.visibilityState === "visible") journeyLoad();});
shellDefineView("journey-choice", {load: async args => {
  await journeyEnsure();
  if (!S.shell.contextLoaded && S.shell.started) {
    Promise.resolve().then(async () => {await S.shell.ready; await journeyLoadRuns();}); return;
  }
  await journeyLoadRuns();
}, render: journeyRenderChoice});
shellDefineView("journey-records", {render: journeyRenderRecords});
