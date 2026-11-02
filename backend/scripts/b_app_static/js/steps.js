"use strict";

// 단계 화면의 공통 틀: 단계 표시, 맨 아래 행동 줄, 자세히 서랍 (ADR-039).
S.drawer = {trigger: null, triggerId: null, screen: null};

// steps: [{id, label, done, summary, reachable, buttonId}]. reachable을 주지 않으면 끝난 단계만 누를 수 있다. 다시 그려도 초점을 찾으려면 buttonId를 준다.
function stepsRenderBar(el, {steps, current, onGo}) {
  coreReplace(el, h("ol", {class: "steps", "aria-label": T("steps.a11y")}, steps.map((step, index) => {
    const now = step.id === current;
    const body = [h("span", {class: "step-no"}, step.done && !now ? "✓" : String(index + 1)),
      h("span", {class: "step-words"}, h("b", null, step.label), h("small", null, now ? T("steps.current") : step.summary))];
    if (now) return h("li", {class: "step now", "aria-current": "step"}, body);
    if (step.reachable ?? step.done) {
      return h("li", null, h("button", {id: step.buttonId, class: `step ${step.done ? "done" : "open"}`, type: "button", onclick: () => onGo(step.id)}, body));
    }
    return h("li", {class: "step", "aria-disabled": "true"}, body);
  })));
}
function stepsFirstOpen(steps) {
  return steps.find(step => !step.done)?.id ?? steps.at(-1)?.id ?? null;
}
// 각 행동: {label, onClick, disabled, reason, attrs}. attrs는 단추에 그대로 붙는다. 다음 행동(primary)은 언제나 줄의 마지막 칸이다.
function stepsRenderActions(el, {note, back, secondary, primary}) {
  const others = [secondary].flat().filter(Boolean);
  const backs = [back].flat().filter(Boolean);
  const reasons = [...backs, ...others, primary].filter(action => action?.disabled && action.reason).map(action => action.reason);
  const button = (action, kind = null) => h("button", {type: "button", class: kind, disabled: !!action.disabled, onclick: action.onClick, ...action.attrs}, action.label);
  coreReplace(el, h("div", {class: "step-actions", role: "group", "aria-label": T("steps.actions_a11y")},
    backs.map(action => button(action)),
    h("p", {class: "step-actions-say"}, [note, ...reasons].filter(Boolean).join(" ")),
    others.map(action => button(action)),
    primary ? button(primary, "primary") : null));
}
// 서랍 안에서는 접지 않는다. 공용 함수(rawError, coreCodeRecord)가 만든 접힘도 제목과 본문으로 편다.
function drawerFlatten(root) {
  for (const folded of root.querySelectorAll("details")) {
    // 펼칠 것이 없으므로 "펼치기"가 든 제목 대신 납작한 제목을 쓴다.
    const flat = folded.getAttribute("data-flat-title");
    folded.replaceWith(h("div", {class: "drawer-section"}, [...folded.childNodes].map(node =>
      node.tagName?.toLowerCase() === "summary" ? h("h3", null, flat || [...node.childNodes]) : node)));
  }
}
// render(body)는 열 때만 불린다. 큰 표를 미리 만들지 않기 위해서다.
function drawerOpen({title, render, trigger = document.activeElement}) {
  const dialog = document.getElementById("details-drawer");
  const close = h("button", {class: "drawer-close", type: "button", onclick: drawerClose}, T("steps.details.close"));
  const body = h("div", {class: "drawer-body"});
  S.drawer = {trigger, triggerId: trigger?.id || null, screen: S.shell.route};
  coreReplace(dialog, h("div", {class: "drawer-head"}, h("h2", {id: "details-drawer-title"}, title), close), body);
  render(body);
  drawerFlatten(body);
  if (!dialog.open) dialog.showModal();
  close.focus();
}
function drawerClose() {
  const dialog = document.getElementById("details-drawer");
  if (!dialog.open) return;
  const {trigger, triggerId} = S.drawer;
  dialog.close();
  coreReplace(dialog);
  S.drawer = {trigger: null, triggerId: null, screen: null};
  // 화면이 다시 그려져 연 단추가 바뀌었으면 같은 id의 새 단추로 돌아간다.
  (trigger?.isConnected ? trigger : triggerId ? document.getElementById(triggerId) : null)?.focus();
}
document.getElementById("details-drawer").addEventListener("cancel", event => { event.preventDefault(); drawerClose(); });
on("screen_shown", ({screen}) => { if (S.drawer.screen && S.drawer.screen !== screen) drawerClose(); });
