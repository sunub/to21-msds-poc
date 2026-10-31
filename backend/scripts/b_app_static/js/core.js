"use strict";

const UI = (() => {
  try { return JSON.parse(document.getElementById("ui-text")?.textContent || "{}"); }
  catch (_) { return {}; }
})();
const S = {ctx: {version: 1, set: null, key: null}, focus: {}, cards: loadCards(), glossary: []};
const SVGNS = (() => {
  const el = document.createElement("div"); el.innerHTML = "<svg></svg>";
  return el.firstChild.namespaceURI;
})();
const coreListeners = new Map();
let coreTipReady = false;

function coreRead(key, fallback = null) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch (_) { return fallback; }
}
function coreWrite(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch (_) { return false; }
}
function loadCards() {
  const saved = coreRead("b_app.cards", {});
  return saved && typeof saved === "object" && !Array.isArray(saved)
    ? Object.fromEntries(Object.entries(saved).filter(([, value]) => typeof value === "boolean")) : {};
}
function T(key, values = {}) {
  const value = key.split(".").reduce((item, part) => item?.[part], UI);
  if (typeof value !== "string") return `⟦${key}⟧`;
  return value.replace(/\{([^{}]+)\}/g, (_, name) => String(values[name] ?? "—"));
}
function fill(el, attrs, kids) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of kids.flat(Infinity)) {
    if (child !== null && child !== undefined && child !== false) el.append(child instanceof Node ? child : String(child));
  }
  if (["button", "summary"].includes(el.tagName.toLowerCase())) {
    const tips = [];
    el.querySelectorAll("[data-tip]").forEach(child => {
      tips.push(child.getAttribute("data-tip")); child.setAttribute("tabindex", "-1");
    });
    if (tips.length && !el.getAttribute("data-tip")) el.setAttribute("data-tip", tips.join("\n"));
  }
  if (el.getAttribute("data-tip")) {
    if (!el.getAttribute("tabindex") && !["button", "summary"].includes(el.tagName.toLowerCase())) el.setAttribute("tabindex", "0");
    el.setAttribute("aria-describedby", "tip");
  }
  if (el.tagName.toLowerCase() === "details") {
    const sync = () => el.querySelector("summary")?.setAttribute("aria-expanded", String(el.open));
    el.addEventListener("toggle", sync);
    sync();
  }
  return el;
}
const h = (tag, attrs, ...kids) => fill(document.createElement(tag), attrs, kids);
const s = (tag, attrs, ...kids) => fill(document.createElementNS(SVGNS, tag), attrs, kids);
function coreReplace(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter(child => child !== null && child !== undefined && child !== false));
}
const num = value => typeof value === "number" && Number.isFinite(value);
const fmt1 = value => num(value) ? value.toFixed(1) : "—";
const pct = value => num(value) ? `${(value * 100).toFixed(1)}%` : "—";
const when = value => value ? String(value).replace("T", " ").slice(0, 19) : "—";

function term(word, shown = null) {
  const copy = UI.glossary?.[word];
  // 첫 화면에서도 설명을 읽을 수 있다. 도움말 API와 같은 승인 문구를 HTML이 공급한다.
  const entry = S.glossary.find(item => item.term === word || item.also?.includes(word))
    || (copy ? {term: copy.term, short: copy.meaning} : null);
  return entry ? h("abbr", {class: "term", "data-term": entry.term,
    "data-tip": [entry.short, entry.example].filter(Boolean).join("\n")}, shown ?? (copy ? copy.term : word))
    : h("span", null, shown ?? word);
}
function on(event, handler) {
  if (!coreListeners.has(event)) coreListeners.set(event, new Set());
  coreListeners.get(event).add(handler);
  return () => coreListeners.get(event)?.delete(handler);
}
function emit(event, payload) {
  for (const handler of coreListeners.get(event) || []) handler(payload);
}
async function api(path, options = {}) {
  const {withStatus = false, ...request} = options;
  const response = await fetch(path, {cache: "no-store", ...request});
  const body = response.status === 204 ? null : await response.json().catch(error => {
    if (withStatus && response.ok) throw error;
    return {};
  });
  if (!response.ok) {
    const error = new Error(body?.error || `${response.status} ${path}`);
    error.status = response.status; error.body = body; throw error;
  }
  return withStatus ? {status: response.status, data: body} : body;
}
async function post(path, body) {
  return api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
}
function status(text, bad = false) {
  const el = document.getElementById("status");
  el.textContent = text || ""; el.classList.toggle("error", bad);
}
function errorCopy(text) {
  return String(text || "").split("`").map((part, i) => i % 2 ? h("code", {class: "technical"}, part) : part);
}
function rawError(raw) {
  return h("details", null, h("summary", null, T("common.raw_error")), h("pre", {class: "technical"}, raw || ""));
}
function friendlyError(info) {
  if (!info) return null;
  const fix = info.fix || info.todo || T("common.legacy.request_error.fix");
  const prefix = T("common.todo", {action: ""});
  return h("div", {class: "error-note", role: "alert"},
    h("p", null, h("strong", null, errorCopy(info.message || info.fact))),
    h("p", null, errorCopy(fix.startsWith(prefix) ? fix : T("common.todo", {action: fix}))), rawError(info.raw));
}
function loadFailure(raw) {
  return friendlyError({message: T("common.legacy.load_error.message"), fix: T("common.legacy.load_error.fix"), raw});
}
function fail(error) {
  document.getElementById("status").replaceChildren(loadFailure(error.message));
}
function card(id, title, hint, ...kids) {
  const el = document.getElementById(id);
  const focused = document.activeElement;
  const hadFocus = el.contains(focused) && focused?.classList.contains("card-toggle");
  const first = kids[0];
  const options = first && !(first instanceof Node) && typeof first === "object" && "collapsed" in first ? kids.shift() : null;
  const content = [hint ? h("p", {class: "muted"}, hint) : null, ...kids];
  if (!options) { coreReplace(el, h("h2", null, title), content); return el; }
  const body = h("div", {id: `${id}-body`, class: "card-body"}, content);
  const toggle = h("summary", {class: "card-toggle", "aria-controls": `${id}-body`});
  const details = h("details", {class: "card"}, toggle, body);
  const setCollapsed = collapsed => {
    S.cards[id] = collapsed; body.hidden = collapsed; details.open = !collapsed;
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.replaceChildren(h("span", {class: "card-title"}, title),
      h("span", {class: "card-summary"}, options.summary || T("common.none")),
      h("span", {class: "card-action"}, T(collapsed ? "common.expand" : "common.collapse")));
  };
  setCollapsed(typeof S.cards[id] === "boolean" ? S.cards[id] : options.collapsed);
  toggle.addEventListener("click", event => {
    event.preventDefault(); setCollapsed(!S.cards[id]); coreWrite("b_app.cards", S.cards);
  });
  el.replaceChildren(details);
  if (hadFocus) toggle.focus({preventScroll: true});
  return el;
}
function setupTip() {
  if (coreTipReady) return;
  coreTipReady = true;
  const tip = document.getElementById("tip");
  let hovered = null, focused = null, dismissed = null, hideTimer = null;
  const target = el => el?.closest?.("[data-tip]");
  const show = el => {
    if (!el || !el.isConnected || el === dismissed) { tip.hidden = true; return; }
    tip.textContent = el.getAttribute("data-tip"); tip.hidden = false;
    const rect = el.getBoundingClientRect();
    tip.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - tip.offsetWidth - 8)) + "px";
    tip.style.top = Math.max(8, rect.bottom + tip.offsetHeight + 8 < window.innerHeight
      ? rect.bottom + 8 : rect.top - tip.offsetHeight - 10) + "px";
  };
  document.addEventListener("mouseover", event => {
    clearTimeout(hideTimer);
    if (tip.contains(event.target)) return;
    const next = target(event.target);
    if (next !== hovered) dismissed = null;
    hovered = next; show(focused || hovered);
  });
  document.addEventListener("mouseout", event => {
    if (tip.contains(event.relatedTarget)) return;
    hovered = target(event.relatedTarget); clearTimeout(hideTimer);
    if (focused || hovered) show(focused || hovered);
    else hideTimer = setTimeout(() => show(null), 150);
  });
  document.addEventListener("focusin", event => { focused = target(event.target); dismissed = null; show(focused || hovered); });
  document.addEventListener("focusout", event => { focused = target(event.relatedTarget); show(focused || hovered); });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") { dismissed = focused || hovered; tip.hidden = true; }
  });
  window.addEventListener("blur", () => { clearTimeout(hideTimer); focused = hovered = null; tip.hidden = true; });
  window.addEventListener("resize", () => show(focused || hovered));
  document.addEventListener("scroll", () => show(focused || hovered), true);
}
