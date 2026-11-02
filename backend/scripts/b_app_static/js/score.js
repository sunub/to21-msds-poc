"use strict";

// 점수와 손실은 API 값이다. 화면은 순서를 유지하고 표시 자리수만 바꾼다.
S.score = {run: null, list: [], criteria: null, gaps: [], key: null, limit: null,
  name: null, context: null, loading: false, count: null, error: null, gapError: null,
  request: 0, pending: null, initial: null, below: false, expanded: new Set(),
  pick: (() => {const saved = coreRead("b_app.pick", []); return Array.isArray(saved) ? saved.filter(x => typeof x === "string").slice(-2) : [];})()};
const SCORE_VIEWS = {
  "score-summary": scoreRenderSummary, "score-problems": scoreRenderProblems,
  "score-history": scoreRenderHistory, "score-docs": scoreRenderDocs,
  "score-grid": scoreRenderGrid, "score-rows": scoreRenderRows,
  "score-rule": scoreRenderRule, "score-gaps": scoreRenderGaps
};
for (const [id, render] of Object.entries(SCORE_VIEWS)) {
  shellDefineView(id, {render, ...(id === "score-summary" ? {load: scoreEnsure} : {})});
}
on("context_changed", () => { scoreLoad(true); });

function scoreContext() { return JSON.stringify([S.ctx.set, S.ctx.key]); }
async function scoreEnsure() {
  if (!S.shell.contextLoaded) {
    await (S.shell.contextReady || shellLoadContext());
  }
  return scoreLoad();
}
function scoreEligible(run) { return S.ctx.set !== null && !run.error && run.set?.id === S.ctx.set; }
function scoreRunPath(name) { return "/api/run/" + name.split("/").map(encodeURIComponent).join("/"); }
function scoreLoad(force = false, selected = null) {
  const state = S.score, context = scoreContext();
  if (!force && state.context === context) return state.pending || Promise.resolve();
  const keep = selected || state.name;
  const request = ++state.request, key = S.ctx.key, set = S.ctx.set;
  const url = path => {
    const [base, query = ""] = path.split("?"); const params = new URLSearchParams(query);
    if (key) params.set("key", key);
    return base + (params.size ? `?${params}` : "");
  };
  state.context = context; state.run = null; state.loading = true; state.count = null;
  state.error = null; state.gapError = null; state.gaps = []; state.criteria = null;
  state.list = []; state.key = null;
  scoreRenderAll();
  const valid = () => request === state.request && context === scoreContext();
  const work = (async () => {
    try {
      const count = await api(url("/api/runs?count=1"));
      if (!valid()) return;
      state.count = count.count; scoreRenderSummary();
      const [list, criteria, gaps] = await Promise.allSettled([
        api(url("/api/runs")), api("/api/criteria"), api(url("/api/silver_gaps"))
      ]);
      if (!valid()) return;
      if (list.status === "rejected") throw list.reason;
      const data = list.value;
      state.list = data.runs || []; state.key = data.key; state.limit = data.doc_time_limit;
      state.criteria = criteria.status === "fulfilled" ? criteria.value : data.criteria;
      state.gaps = gaps.status === "fulfilled" ? (gaps.value.gaps || []) : [];
      state.gapError = gaps.status === "rejected" ? gaps.reason.message : null;
      const pool = state.list.filter(scoreEligible);
      // API의 current가 우선이다. 다른 묶음이면 API의 시각 순 목록에서 같은 묶음의 마지막 기록만 고른다.
      state.name = pool.find(r => r.name === keep)?.name || pool.find(r => r.name === data.current)?.name
        || pool.filter(r => r.run_kind !== "silver").at(-1)?.name || pool.at(-1)?.name || null;
      if (state.name) {
        const result = await api(url(scoreRunPath(state.name)));
        if (!valid()) return;
        // 응답까지 사이에 입력 기록이나 선택 기준이 달라진 경우 이전 점수를 노출하지 않는다.
        if (result.set?.id === set) state.run = result;
      }
    } catch (error) { if (valid()) state.error = error.message; }
    finally {
      if (valid()) { state.loading = false; scoreRenderAll(); }
    }
  })();
  state.pending = work;
  return work;
}
function scoreRenderAll() { for (const render of Object.values(SCORE_VIEWS)) render(); }
function scoreItemKey(name) {
  return Object.keys(UI.score.item_names).sort((a, b) => b.length - a.length)
    .find(key => name.startsWith(key.replace(/\)$/, "")));
}
function scoreItemName(name) { return UI.score.item_names[scoreItemKey(name)] || name; }
function scoreLabel(run) { return run.label?.title || run.name; }
function scoreMissing() { return T("context.unavailable"); }
function scoreBasis(run = S.score.run, count = run?.docs?.length) {
  return h("p", {class: "score-basis muted"}, scoreBasisText(run, count),
    shellKeyMismatch(run?.key) ? h("span", {class: "answer-mismatch"}, " ", shellKeyMismatch(run.key)) : null);
}
function scoreBasisText(run = S.score.run, count = run?.docs?.length) {
  return T("score.basis.label", {
    key: shellKeyLabel(run?.key), count: count ?? scoreMissing()
  });
}
function scoreButton(id, key, action, attrs = {}) {
  return h("button", {type: "button", id, onclick: action, ...attrs}, T(key));
}
function scoreTable(headings, rows) {
  return h("div", {class: "score-table-wrap"}, h("table", null,
    h("thead", null, h("tr", null, headings.map(text => h("th", {scope: "col"}, text)))),
    h("tbody", null, rows.map(row => h("tr", null, row.map(value => h("td", null, value)))))));
}
function scoreNote(text) { return h("p", {class: "muted"}, text || scoreMissing()); }
function scoreDetails(title, ...children) {
  return h("details", null, h("summary", null, title), h("div", {class: "score-detail-body"}, children));
}
function scoreSection(id, title, hint, summary, ...children) {
  if (!S.score.run || S.score.loading || S.score.error) { document.getElementById(id).replaceChildren(); return; }
  card(id, title, hint, {collapsed: true, summary: summary || T("common.legacy.cell_labels.c_none")}, ...children);
}
function scoreBar(value, target, max = 100) {
  const x = n => num(n) && max > 0 ? Math.max(0, Math.min(1, n / max)) * 300 : 0;
  return s("svg", {viewBox: "0 0 300 18", class: "score-bar", "aria-hidden": "true"},
    s("rect", {x: 0, y: 5, width: 300, height: 8, class: "score-track"}),
    num(value) ? s("rect", {x: 0, y: 5, width: x(value), height: 8, class: "score-fill"}) : null,
    num(target) ? s("line", {x1: x(target), x2: x(target), y1: 0, y2: 18, class: "score-target"}) : null);
}
function scoreCounts(row, links = false) {
  if (!row.counts) return h("span", {class: "score-unrecorded"}, T("common.legacy.cell_labels.c_none"));
  const picks = {missing: "missing", wrong: "mismatch", made: "made"};
  return h("span", {class: "score-counts"}, ["missing", "made", "wrong"].map(kind => {
    const count = row.counts[UI.score.cause_keys[kind]];
    const text = num(count) ? T(`score.problem.counts.${kind}`, {count}) : T("common.legacy.cell_labels.c_none");
    return h("span", {class: "score-count"}, links && num(count) && count > 0
      ? h("button", {type: "button", class: "text-button", disabled: !row.docs?.[0]?.doc_id || !row.section,
        onclick: () => scoreOpenSource(row, picks[kind])}, text) : text);
  }));
}
function scoreProblemDocs(row, pick = "mismatch") {
  const kinds = pick === "mismatch" ? ["wrong", "made"] : [pick === "missing" ? "missing" : "made"];
  // API의 손실 순서를 유지하며 실제로 문제 값이 있는 문서를 먼저 고른다.
  return [...new Set([...kinds.flatMap(kind => (row.docs || []).filter(doc => doc.counts?.[UI.score.cause_keys[kind]] > 0)),
    ...(row.docs || [])].map(doc => doc.doc_id).filter(Boolean))];
}
function scoreProblemDoc(row, pick = "mismatch") { return scoreProblemDocs(row, pick)[0]; }
function scoreOpenSource(row, pick = "mismatch", doc = scoreProblemDoc(row, pick)) {
  if (!doc || !row.section || !S.score.run) return;
  const args = {run: S.score.run.name, doc, section: row.section, item: row.name, pick};
  S.focus = {...S.focus, ...args};
  emit("problem_opened", args);
  return go("s02", args).catch(fail);
}
function scoreSelect() {
  const groups = new Map();
  for (const run of S.score.list) {
    if (run.error) continue;
    const kind = run.run_kind || "unknown";
    if (!groups.has(kind)) groups.set(kind, []);
    groups.get(kind).push(run);
  }
  const select = h("select", {id: "score-run-select", onchange: event => scoreLoad(true, event.target.value)},
    [...groups].map(([kind, runs]) => h("optgroup", {"data-kind": kind,
      label: UI.jobs.kinds[kind] || T("score.selection.unknown")}, runs.map(run => h("option", {
        value: run.name, selected: run.name === S.score.name, disabled: !scoreEligible(run)
      }, scoreLabel(run), run.comparable === false ? ` — ${T("score.selection.not_comparable")}` : "",
      !scoreEligible(run) ? ` — ${T("score.selection.other_set")}` : "")))));
  select.value = S.score.name || "";
  return h("div", {class: "score-picker"}, h("div", null,
    h("label", {for: "score-run-select"}, T("score.history.select_record")), select),
    scoreButton("score-reload", "score.partial.reload", () => scoreLoad(true)));
}
function scoreConditions(run) {
  const progress = run.progress;
  const top = run.status_text?.top_problem;
  const facts = [
    [T("score.conditions.run_name"), scoreLabel(run)],
    [T("score.conditions.raw_name"), h("code", {class: "raw"}, run.name)],
    [T("common.model"), h("span", null, run.model_label || run.model_tag || scoreMissing(),
      h("span", {class: "raw"}, [run.model_tag, run.model].filter(Boolean).join(" / ")))],
    [term("prompt_version", T("score.conditions.prompt")), h("span", {class: "raw"}, run.prompt_version || scoreMissing())],
    [T("score.conditions.pages"), h("span", {class: "raw"}, run.pages_dir || scoreMissing())],
    [T("score.history.started"), when(run.started_at)],
    [T("score.conditions.kind"), UI.jobs.kinds[run.run_kind] || run.run_kind || scoreMissing()],
    [T("score.conditions.score_scope"), T("score.conditions.score_counts", {
      total: (run.docs || []).length + (run.no_gold || []).length + (run.excluded || []).length,
      scored: (run.docs || []).length, missing: (run.no_gold || []).length, excluded: (run.excluded || []).length})]
  ];
  return scoreDetails(T("score.conditions.expand"),
    scoreNote(run.status_text?.headline), scoreNote(run.status_text?.next_action),
    progress ? scoreNote(T("score.conditions.progress", progress) + (progress.running ? ` — ${T("score.conditions.running")}` : "")) : null,
    scoreTable([T("common.record"), T("score.conditions.value")], facts),
    top?.section && top.docs?.[0]?.doc_id ? scoreButton("score-retest", "score.actions.retest", () => {
      const args = {run: run.name, base_run: run.name, doc: top.docs[0].doc_id, section: top.section, item: top.name};
      S.focus = {...S.focus, ...args}; return go("s03", args).catch(fail);
    }) : null);
}
function scoreRenderSummary() {
  const el = document.getElementById("score-summary"), state = S.score, run = state.run;
  el.setAttribute("aria-busy", String(state.loading || !state.context));
  if (state.loading || !state.context) {
    shellConclusion("s01", T("errors.loading.fact"));
    el.replaceChildren(h("p", {role: "status"}, num(state.count) ? T("score.loading.scoring", {count: state.count}) : T("errors.loading.fact")));
    return;
  }
  if (state.error) {
    shellConclusion("s01", T("score.load_failed.fact"));
    el.replaceChildren(friendlyError({message: T("score.load_failed.fact"), fix: T("score.load_failed.todo"), raw: state.error}),
      scoreButton("score-reload", "score.partial.reload", () => scoreLoad(true)));
    return;
  }
  const broken = state.list.filter(row => row.error);
  const warning = broken.length ? h("div", {class: "score-partial", role: "status"},
    h("p", null, T("score.partial.title", {total: state.list.length, failed: broken.length})),
    scoreNote(T("score.partial.todo")), scoreDetails(T("common.raw_error"),
      broken.map(row => h("p", {class: "technical"}, row.name, ": ", row.error)))) : null;
  if (!run) {
    shellConclusion("s01", T("score.empty.title"));
    coreReplace(el, warning, h("div", {class: "score-empty"},
      h("h2", null, T("score.empty.state")), scoreNote(T("score.empty.no_mixing")),
      scoreButton("score-prepare", "score.empty.prepare", () => go("s03").catch(fail), {class: "primary"}),
      scoreButton("score-change-set", "score.empty.change_set", shellOpenContext)));
    return;
  }
  if (!num(run.weighted)) {
    shellConclusion("s01", T("score.summary.unscored"));
    coreReplace(el, warning, scoreSelect(),
      scoreNote(T("score.summary.unscored_todo")), scoreBasis(run), scoreConditions(run)); return;
  }
  const targets = run.targets, top = run.status_text?.top_problem, loss = run.status_text?.loss_basis;
  const missingCount = top?.counts?.[UI.score.cause_keys.missing];
  const kind = ["wrong", "made", "missing"].find(k => top?.counts?.[UI.score.cause_keys[k]] > 0);
  const count = kind ? top.counts[UI.score.cause_keys[kind]] : null;
  const hint = !kind ? T("score.problem.evidence_unrecorded") : kind === "wrong"
    ? num(missingCount) ? T("score.problem.evidence_hint", {count: missingCount}) : T("score.problem.wrong_hint")
    : T(`score.problem.${kind}_hint`);
  shellConclusion("s01", !top ? T("score.no_problem.title") : targets?.weighted
    ? targets.weighted.met ? T("score.summary.headline_met", {line: targets.weighted.line})
      : T("score.summary.headline_model", {model: run.model_label || run.model_tag || scoreMissing()})
    : T("score.summary.value", {score: fmt1(run.weighted)}));
  const main = h("div", {class: "score-overview"},
    h("div", {class: "score-block", "data-guide": "s01-score"},
      h("p", null, T("score.summary.scope", {model: run.model_label || run.model_tag || scoreMissing(), count: run.docs?.length ?? scoreMissing()})),
      h("div", {class: "score-number"}, term("weighted", fmt1(run.weighted)), h("span", null, T("score.summary.denominator"))),
      scoreBasis(run),
      targets ? h("div", null,
        h("p", {class: "score-target-gap"}, T(targets.weighted.met ? "score.summary.headline_met" : "score.summary.headline_below",
          {line: targets.weighted.line, gap: fmt1(targets.weighted.line - targets.weighted.value)})),
        scoreBar(targets.weighted.value, targets.weighted.line),
        h("p", null, T("score.summary.target_line", {line: targets.weighted.line})),
        h("p", {class: "score-essential"}, T(targets.must.met ? "score.summary.must_all" : "score.summary.must_some",
          {total: targets.must.total, met: targets.must.met_count}))) : scoreNote(scoreMissing())),
    h("div", {class: "score-loss-block", "data-guide": "s01-top-problem"},
      top ? [h("h2", null, term(top.section === 8 ? "exposure" : "item", T("score.summary.top_problem", {item: scoreItemName(top.name)}))),
        top.section === 8 ? h("p", {class: "small"}, term("concentration_unit")) : null,
        scoreNote([top.section ? T("score.calls.section", {section: top.section}) : null, top.name].filter(Boolean).join(" · ")),
        h("p", {class: "small"}, T("score.summary.loss_meaning", {total_loss: fmt1(loss?.loss_total),
          score: fmt1(run.weighted), item_loss: num(top.loss) ? top.loss.toFixed(2) : scoreMissing()})),
        scoreCounts(top, true)] : [h("h2", null, T("score.no_problem.title")), scoreNote(T("score.no_problem.no_fallback"))]));
  coreReplace(el, warning, main,
    top ? h("div", {class: "score-next", "data-guide": "s01-open-source"},
      h("button", {id: "score-open-source", type: "button", onclick: () => scoreOpenSource(top),
        class: "primary", disabled: !top.docs?.[0]?.doc_id || !top.section},
        kind ? T(`score.problem.open_${kind}`, {count}) : T("score.summary.open_source")),
      scoreNote(hint),
      !top.docs?.[0]?.doc_id || !top.section ? scoreNote(T("score.summary.unlinked")) : null)
      : scoreButton("score-open-items", "score.no_problem.open_items", () => {
        if (S.cards["score-problems"] !== false) document.querySelector("#score-problems .card-toggle")?.click();
        document.querySelector("#score-problems .card-toggle")?.focus();
      }),
    scoreDetails(T("score.history.select_record"), scoreSelect()), scoreConditions(run));
  if (S.shell.route === "s01") emit("score_summary_shown", {run: run.name, key: run.key?.id, weighted: run.weighted});
}
function scoreProblemDetail(row, run) {
  const details = (run.details || []).filter(d => d.item === row.name);
  const na = (run.items_na_excluded || []).find(i => i.name === row.name);
  const criterion = S.score.criteria?.items?.find(i => i.name === row.name);
  const block = h("div", {class: "score-problem-detail"});
  let shown = Math.min(300, details.length);
  const render = () => {
    const more = scoreButton(null, "score.problem.show_more", () => {shown = Math.min(shown + 300, details.length); render();});
    coreReplace(block, scoreBasis(run), scoreNote(criterion?.help),
      scoreNote(T("score.criteria.method") + ": " + (UI.score.item_methods[scoreItemKey(row.name)] || criterion?.metric || scoreMissing())),
      scoreNote(T("score.criteria.weight", row)),
      na && num(na.score) ? scoreNote(T("score.problem.nonempty_score", {score: (na.score * 100).toFixed(1)})) : null,
      row.cause ? scoreNote(T("score.problem.cause", {cause: row.cause})) : null,
      !details.length ? scoreNote(T(row.counts ? "score.problem.empty" : "score.problem.unrecorded")) : [
        scoreNote(T("score.problem.shown", {total: details.length, shown})),
        scoreTable([T("common.document"), T("score.problem.kind"), T("score.problem.record")], details.slice(0, shown).map(d => [
          h("button", {type: "button", class: "text-button technical", disabled: !row.section,
            onclick: () => scoreOpenSource(row, "mismatch", d.doc_id)}, d.doc_id), d.kind, h("span", {class: "technical"}, d.content)])),
        shown < details.length ? more : null],
      S.score.gaps.filter(g => row.name.startsWith(g.item)).map(scoreGap));
  };
  render(); return block;
}
function scoreRenderProblems() {
  const run = S.score.run, losses = run?.status_text?.losses || [];
  const below = losses.filter(row => row.below_target), visible = S.score.below ? below : losses;
  const rows = visible.map((row, i) => {
    const body = scoreProblemDetail(row, run); body.setAttribute("id", `score-item-detail-${i}`);
    body.hidden = !S.score.expanded.has(row.name);
    const button = h("button", {type: "button", class: "score-item-toggle", "data-item": row.name,
      "data-tip": scoreBasisText(run),
      "aria-expanded": String(!body.hidden), "aria-controls": body.id, onclick: () => {
        body.hidden = !body.hidden; button.setAttribute("aria-expanded", String(!body.hidden));
        body.hidden ? S.score.expanded.delete(row.name) : S.score.expanded.add(row.name);
      }},
      h("span", {class: "score-item-name"}, scoreItemName(row.name), h("span", {class: "raw"}, row.name)),
      h("span", null, scoreBar(row.score, row.target), T("score.criteria.score", {score: fmt1(row.score), target: fmt1(row.target)})),
      h("span", {class: row.below_target ? "score-below" : "score-met"}, T(row.below_target ? "score.criteria.below" : "score.criteria.met")),
      h("span", null, T("score.criteria.loss"), " ", T("score.value_points", {score: num(row.loss) ? row.loss.toFixed(2) : scoreMissing()})), scoreCounts(row));
    return h("div", {class: "score-item"}, button, body);
  });
  scoreSection("score-problems", T("score.criteria.expand"), T("score.criteria.hint"),
    T("score.criteria.below_count", {count: below.length}), scoreBasis(run),
    h("div", {class: "score-filters"},
      h("button", {id: "score-filter-below", type: "button", "aria-pressed": String(S.score.below), onclick: () => {
        S.score.below = true; scoreRenderProblems(); document.getElementById("score-filter-below").focus();
      }}, T("score.criteria.filter_below", {count: below.length})),
      scoreButton("score-filter-all", "score.criteria.show_all", () => {
        S.score.below = false; scoreRenderProblems(); document.getElementById("score-filter-all").focus();
      }, {"aria-pressed": String(!S.score.below)}),
      S.score.below ? scoreNote(T("score.criteria.hidden", {count: losses.length - visible.length})) : null),
    scoreDetails(T("score.problem.scope"), ["missing_meaning", "made_meaning", "wrong_meaning", "unrecorded", "checked_empty", "answer_warning"].map(k => scoreNote(T(`score.problem.${k}`)))), rows);
}
function scoreHistoryRuns() {
  return S.score.list.filter(r => r.kind === "run" && r.run_kind !== "silver" && !r.error && num(r.weighted));
}
function scoreSavePick(names) {
  S.score.pick = names; coreWrite("b_app.pick", names);
  document.querySelectorAll("[data-score-pick]").forEach(button => {
    const i = names.indexOf(button.dataset.run); button.setAttribute("aria-pressed", String(i >= 0));
    if (button.dataset.scorePick === "table") button.textContent = i < 0 ? T("common.record") : T("score.history.selected", {order: i ? "B" : "A"});
  });
  const chosen = document.getElementById("score-history-selected");
  if (chosen) chosen.replaceChildren(...names.map((name, i) => h("p", {class: "raw"}, `${i ? "B" : "A"}: ${name}`)));
  const compare = document.getElementById("score-compare-picks"); if (compare) compare.disabled = names.length !== 2;
}
function scoreHistoryPick(run, chart = false) {
  const label = T("score.history.point", {run: scoreLabel(run), score: fmt1(run.weighted),
    model: run.model_label || run.model_tag || scoreMissing(), time: when(run.started_at)}) + " · "
    + scoreBasisText({...run, key: S.score.key});
  return h("button", {type: "button", class: chart ? "score-history-point" : "score-history-choice",
    "data-run": run.name, "data-score-pick": chart ? "chart" : "table", "aria-label": label,
    "data-tip": label, "aria-pressed": String(S.score.pick.includes(run.name)), onclick: () => {
      const picked = S.score.pick.includes(run.name);
      scoreSavePick(picked ? S.score.pick.filter(n => n !== run.name) : [...S.score.pick, run.name].slice(-2));
    }}, chart ? h("span", {class: "score-history-dot"}) : T("common.record"));
}
function scoreRenderHistory() {
  const run = S.score.run, runs = scoreHistoryRuns(), width = 900, height = 260;
  const y = n => 220 - n * 1.9, x = i => 52 + (runs.length > 1 ? i / (runs.length - 1) : .5) * 796;
  const chart = s("svg", {class: "score-history-chart", viewBox: `0 0 ${width} ${height}`,
    role: "group", "aria-label": T("score.history.title")});
  for (const value of [0, 25, 50, 75, 100]) {
    chart.append(s("line", {x1: 40, x2: 860, y1: y(value), y2: y(value), class: "score-grid-line"}),
      s("text", {x: 34, y: y(value) + 4, "text-anchor": "end", class: "score-axis"}, value));
  }
  const line = run?.targets?.weighted?.line;
  if (num(line)) chart.append(s("line", {x1: 40, x2: 860, y1: y(line), y2: y(line), class: "score-target"}));
  runs.forEach((r, i) => {
    chart.append(s("foreignObject", {x: x(i) - 22, y: y(r.weighted) - 22, width: 44, height: 44}, scoreHistoryPick(r, true)));
    if (i === 0 || i === runs.length - 1 || (runs.length < 12)) chart.append(s("text", {
      x: x(i), y: 252, "text-anchor": "middle", class: "score-axis"}, when(r.started_at).split(" ").slice(1, 3).join(" ")));
  });
  const records = runs.map(r => [scoreHistoryPick(r), h("span", null, scoreLabel(r), scoreNote(r.set?.label),
    r.name === S.score.name ? scoreNote(T("score.history.current_record")) : null),
    h("span", null, fmt1(r.weighted), scoreBasis({...r, key: S.score.key})),
    h("span", {class: "raw"}, r.model_label || r.model_tag || scoreMissing()), when(r.started_at)]);
  scoreSection("score-history", T("score.history.title"), T("score.history.hint"), run?.card_summaries?.history,
    scoreNote(T("score.history.scope")), scoreBasis(run),
    scoreNote(T("score.history.exclude_answer")), scoreNote(T("score.history.answer_records")),
    num(line) ? scoreNote(T("score.summary.target_line", {line})) : null,
    scoreNote(T("score.history.plotted", {count: runs.length})), chart,
    scoreTable([T("common.record"), T("score.conditions.run_name"), T("score.history.score", {maximum: 100}), T("common.model"), T("score.history.started")], records),
    scoreNote(T("score.history.selection_order")), h("div", {id: "score-history-selected"}),
    h("div", {class: "score-actions"}, scoreButton("score-clear-picks", "score.history.clear", () => scoreSavePick([])),
      scoreButton("score-compare-picks", "score.history.compare", () => go("s04", {a: S.score.pick[0], b: S.score.pick[1]}).catch(fail))));
  if (!S.score.loading && !S.score.error && S.score.run) scoreSavePick(S.score.pick.filter(name => runs.some(r => r.name === name)));
}
function scoreRenderDocs() {
  const run = S.score.run, limit = S.score.limit;
  const rows = Object.entries(run?.per_doc || {}).map(([doc, data]) => [h("span", {class: "raw"}, doc),
    h("span", null, fmt1(data.weighted), scoreBar(data.weighted, run?.targets?.weighted?.line), scoreBasis(run, 1)),
    h("span", {class: "technical"}, (data.failed_must || []).map(scoreItemName).join(", ") || T("common.none")),
    num(data.seconds) ? T("score.documents.seconds", {seconds: fmt1(data.seconds)}) : T("score.documents.time_unknown"),
    !num(data.seconds) || !num(limit) ? T("score.documents.time_unknown") : data.seconds > limit
      ? h("span", {class: "score-below"}, T("common.legacy.time_over")) : T("score.documents.within_time", {minutes: limit / 60})]);
  scoreSection("score-docs", T("score.documents.title"), T("score.documents.hint"), run?.card_summaries?.docs,
    scoreNote(T("score.documents.time_target", {seconds: limit ?? scoreMissing()})),
    scoreTable([T("common.document"), T("score.history.score", {maximum: 100}), T("score.documents.must_below"),
      T("score.documents.duration"), T("score.documents.time_state")], rows));
}
function scoreCall(no, cell) {
  const state = !cell ? "c_none" : !cell.ok ? "c_fail" : cell.limit_kind ? "c_limit" : cell.reextracted ? "c_re" : "c_ok";
  return h("details", {class: `score-call ${state}`}, h("summary", null,
    h("span", null, T("score.calls.section", {section: no})), h("span", null, T(`common.legacy.cell_labels.${state}`))),
    h("div", null, cell ? [
      scoreNote(T("score.calls.attempt_info", {count: cell.attempts ?? scoreMissing(), seconds: fmt1(cell.seconds)})),
      scoreNote(T("score.calls.mode", {mode: coreCodeLabel("mode", cell.mode)})),
      cell.reextracted ? scoreNote(T("score.calls.reextract_meaning")) : null,
      cell.limit_kind ? scoreNote(T("score.calls.limit_reason", {reason: coreCodeLabel("limit", cell.limit_kind)})) : scoreNote(T("score.calls.not_limited")),
      coreCodeRecord(cell.mode, cell.limit_kind)
    ] : scoreNote(T("score.calls.unknown"))));
}
function scoreRenderGrid() {
  const run = S.score.run, groups = [];
  for (const [doc, cells] of Object.entries(run?.grid || {})) {
    const msds = new Map();
    for (const [key, cell] of Object.entries(cells)) {
      const match = key.match(/^m(\d+):(\d+)$/), mi = match ? +match[1] : 0, no = match ? +match[2] : +key;
      if (!msds.has(mi)) msds.set(mi, {}); msds.get(mi)[no] = cell;
    }
    for (const [mi, entries] of [...msds].sort(([a], [b]) => a - b)) groups.push(h("div", null,
      h("h3", {class: "technical"}, T("score.calls.scope", {doc, number: mi + 1})),
      h("div", {class: "score-calls"}, Array.from({length: 16}, (_, i) => scoreCall(i + 1, entries[i + 1])))));
  }
  scoreSection("score-grid", T("score.calls.legend"), T("score.calls.multiple_msds"), run?.card_summaries?.grid,
    h("ul", null, ["c_ok", "c_re", "c_limit", "c_fail", "c_none"].map(k => h("li", null, T(`common.legacy.cell_labels.${k}`)))),
    groups.length ? groups : scoreNote(T("common.legacy.cell_labels.c_none")));
}
function scoreRenderRows() {
  const run = S.score.run;
  scoreSection("score-rows", T("score.rows.title"), T("score.rows.hint"), run?.card_summaries?.rows,
    scoreBasis(run), scoreNote(T("score.rows.meaning")), scoreTable([
      T("score.rows.kind"), T("score.rows.prediction"), T("context.answer.label"), T("score.rows.ratio")],
    Object.entries(run?.rows || {}).map(([key, row]) => [key === "extras" ? term("extras", UI.score.tables[key]) : UI.score.tables[key] || key, row.pred ?? scoreMissing(), row.gold ?? scoreMissing(),
      num(row.pred) && num(row.gold) && row.gold > 0 ? `${Math.round(row.pred / row.gold * 100)}%` : T("score.rows.not_applicable")])));
}
function scoreRenderRule() {
  const run = S.score.run, criteria = S.score.criteria;
  const na = run?.weighted_na_excluded;
  scoreSection("score-rule", T("score.calculation.title"), T("score.calculation.weighted"),
    T("score.conditions.nonempty_score", {score: fmt1(na)}),
    scoreBasis(run), scoreNote(T("context.answer_trust")),
    scoreNote(T("score.conditions.nonempty_meaning")), scoreNote(T("score.conditions.keep_components")),
    num(na) && num(run?.weighted) ? scoreNote(T("score.conditions.nonempty_difference", {gap: fmt1(na - run.weighted)})) : null,
    scoreNote(T("score.calculation.loss_formula")),
    scoreNote(T("score.calculation.weight_basis", {weight: run?.status_text?.loss_basis?.weight_total ?? scoreMissing()})),
    scoreNote(T("score.calculation.total_loss", {loss: fmt1(run?.status_text?.loss_basis?.loss_total)})),
    h("h3", null, T("score.calculation.scorer_counts")),
    scoreNote(T("score.calculation.scorer_counts_hint")),
    scoreTable([T("common.record"), ...["missing", "made", "wrong"].map(kind => T(`source.kinds.${kind}`))],
      (run?.status_text?.losses || []).map(row => [scoreItemName(row.name),
        ...["missing", "made", "wrong"].map(kind => row.scorer_counts?.[UI.score.cause_keys[kind]] ?? T("common.legacy.cell_labels.c_none"))])),
    Object.entries(criteria?.weights || {}).map(([level, weight]) => scoreNote(T("score.calculation.weight", {
      level, weight, count: criteria.items?.filter(i => i.level === level).length || 0}))),
    scoreTable([T("common.record"), T("score.criteria.method"), T("score.criteria.loss")],
      (criteria?.items || []).map(item => [h("span", null, scoreItemName(item.name), h("span", {class: "raw"}, item.name)),
        h("span", null, UI.score.item_methods[scoreItemKey(item.name)] || item.help || scoreMissing(), h("span", {class: "raw"}, item.metric)),
        h("span", null, T("score.summary.target_line", {line: num(item.target) ? fmt1(item.target * 100) : scoreMissing()}),
          scoreNote(T("score.criteria.weight", {level: item.level, weight: criteria.weights?.[item.level] ?? scoreMissing()})))])));
}
function scoreGap(gap) {
  return h("div", {class: "score-gap"}, h("p", null, gap.item, ": ", gap.note),
    scoreNote(T("score.gaps.source", {source: gap.source || scoreMissing()})), scoreNote(T("score.problem.found_at", {time: gap.since || scoreMissing()})));
}
function scoreRenderGaps() {
  scoreSection("score-gaps", T("score.gaps.title"), null, T("score.gaps.count", {count: S.score.gaps.length}),
    scoreBasis(), S.score.gapError ? loadFailure(S.score.gapError)
      : S.score.gaps.length ? S.score.gaps.map(scoreGap) : scoreNote(T("score.gaps.none")));
}
