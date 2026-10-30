"""점수판 조작을 작은 DOM 대역으로 검사한다. 실제 브라우저 배치 검사를 대신하지 않는다."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "scripts" / "b_app_static" / "app.js"
DOM = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tagName = tag; this.attrs = {}; this.children = []; this.events = {}; this.hidden = false; }
  append(...kids) { this.children.push(...kids); }
  replaceChildren(...kids) { this.children = []; this.append(...kids); }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'hidden') this.hidden = true; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  get dataset() { return Object.fromEntries(Object.entries(this.attrs).filter(([k]) => k.startsWith('data-')).map(([k,v]) => [k.slice(5),v])); }
  get textContent() { return this.children.map(x => x instanceof Element ? x.textContent : String(x)).join(''); }
  set textContent(s) { this.children = [s]; }
  set innerHTML(s) { this.children = [new Element('svg')]; }
  get firstChild() { return this.children[0]; }
  get classList() {
    const self = this;
    return { contains(c) { return (self.attrs.class || '').split(' ').includes(c); },
      toggle(c, on) { const a = new Set((self.attrs.class || '').split(' ').filter(Boolean));
        if (on === undefined) on = !a.has(c); on ? a.add(c) : a.delete(c); self.attrs.class = [...a].join(' '); },
      add(c) { this.toggle(c, true); }, remove(c) { this.toggle(c, false); } };
  }
  querySelectorAll(selector) {
    const all = this.children.filter(x => x instanceof Element).flatMap(x => [x, ...x.querySelectorAll('*')]);
    if (selector === '*') return all;
    if (selector.startsWith('.')) return all.filter(x => x.classList.contains(selector.slice(1)));
    if (selector.startsWith('#')) return all.filter(x => x.attrs.id === selector.slice(1));
    return all.filter(x => x.tagName === selector);
  }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
  addEventListener(k, fn) { this.events[k] = fn; }
  click() { return this.events.click?.({target:this}); }
  focus() { document.activeElement = this; }
}
const elements = new Map();
const store = new Map();
const localStorage = { getItem: k => store.get(k) ?? null, setItem: (k,v) => store.set(k,v) };
const document = {
  createElement: tag => new Element(tag), createElementNS: (_,tag) => new Element(tag),
  getElementById: id => { if (!elements.has(id)) elements.set(id, new Element('div')); return elements.get(id); },
  querySelector: s => s.includes('data-tab="doc"') ? docTab : null,
};
const docTab = new Element('button');
const context = vm.createContext({Node: Element, document, localStorage, console, assert, location: {}, history: {},
  CSS: {escape: s => s}, setTimeout, clearTimeout});
"""


def run_js(body):
    node = shutil.which("node")
    if not node:
        pytest.skip("DOM 대역 검사에는 설치된 Node가 필요합니다")
    source = APP_JS.read_text(encoding="utf-8").removesuffix("start();\n")
    program = DOM + "\nvm.runInContext(" + json.dumps(source) + ", context);\n"
    program += "vm.runInContext(" + json.dumps("(async () => {" + body + "})()") + ", context).catch(e => { console.error(e); process.exitCode = 1; });"
    result = subprocess.run([node, "-e", program], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_connection_banner_renders_server_copy_and_reserves_red_for_errors():
    run_js(r"""
      S.run={model:'fake-model',connection_notes:{}};
      for (const [state,level] of [['hint','hint'],['ok','ok'],['error','error'],['loading','hint']]) {
        S.run.connection_notes[state]={advanced_off:{text:'받은 '+state,level},advanced_on:{text:'고급 '+state,level}};
      }
      S.srv.data={models:[]};
      let note=connLine(true);
      assert.equal(note.getAttribute('id'),'conn-now');
      assert.equal(note.classList.contains('connwarn'),false);
      assert.equal(note.textContent,'받은 hint');
      S.srv.data.models=[{model_expected:'fake-model',reachable:true,match:true}];
      assert.equal(connLine(true).textContent,'받은 ok');
      S.srv.error='x';
      assert.equal(connLine(true).textContent,'받은 error');
      assert.equal(connLine(true).classList.contains('connwarn'),true);
      S.srv.error=null; S.srv.data=null;
      assert.equal(connLine(true).textContent,'받은 loading');
      assert.equal(connLine(true).classList.contains('connwarn'),false);
      document.getElementById('advanced').checked=true;
      assert.equal(connLine(true).textContent,'고급 loading');
    """)


def test_score_status_card_and_filter_preserve_all_values():
    run_js(r"""
      S.criteria = {items: [], weights: {'필수':3,'중요':2,'일반':1}};
      S.name = 'fake-run';
      S.run = {name:S.name, status_text:{headline:'서버의 요약',verdict:'fail',next_action:'서버의 할 일',
        top_drops:[{name:'8항 노출기준',section:8,sentence:'서버의 원인'}]},
        items:[{name:'8항 노출기준',level:'필수',score:.4,target:.95,pass:false},
          {name:'14항 운송',level:'필수',score:1,target:.95,pass:true}]};
      renderStatus(S.run);
      const statusCard = document.getElementById('status-card');
      assert.match(statusCard.textContent, /서버의 요약/);
      assert.match(statusCard.textContent, /서버의 원인/);
      assert.match(statusCard.textContent, /다음에 할 일: 서버의 할 일/);
      assert.equal(statusCard.querySelectorAll('button').length, 1);
      let navigation;
      openScoreSource = async (r,d) => { navigation = [r.name,d.section]; };
      await statusCard.querySelector('button').click();
      assert.deepEqual(navigation, ['fake-run',8]);
      renderItems(S.run);
      const card = document.getElementById('items-card');
      assert.equal(card.querySelectorAll('.itembox').length,1);
      assert.match(card.textContent, /통과한 항목 1개 숨김/);
      card.querySelectorAll('button').find(b => b.textContent === '모두 보기').click();
      assert.equal(card.querySelectorAll('.itembox').length,2);
      card.querySelectorAll('button').find(b => b.textContent.includes('미달만 보기')).click();
      assert.equal(card.querySelectorAll('.itembox').length,1);
    """)


def test_score_collapsed_cards_keep_content_state_and_work_without_storage():
    run_js(r"""
      card('history-card','실행 역사','기존 안내',{collapsed:true,summary:'서버 요약'},h('p',null,'기존 그래프'));
      let el = document.getElementById('history-card');
      let toggle = el.querySelector('.card-toggle');
      assert.equal(toggle.getAttribute('aria-expanded'),'false');
      assert.equal(el.querySelector('.card-body').hidden,true);
      assert.match(el.textContent,/기존 안내/);
      assert.match(el.textContent,/기존 그래프/);
      toggle.click();
      assert.equal(el.querySelector('.card-body').hidden,false);
      assert.equal(JSON.parse(localStorage.getItem('b_app.cards'))['history-card'],false);
      card('history-card','실행 역사',null,{collapsed:true,summary:'갱신'},h('p',null,'새 그래프'));
      assert.equal(el.querySelector('.card-body').hidden,false);
      // 페이지를 다시 열 때 읽는 경로와 저장 실패도 검사한다.
      S.cards = loadCards();
      localStorage.setItem = () => { throw new Error('storage blocked'); };
      el.querySelector('.card-toggle').click();
      assert.equal(el.querySelector('.card-body').hidden,true);
      card('history-card','실행 역사',null,{collapsed:true,summary:'갱신'},h('p',null,'다음 그래프'));
      assert.equal(el.querySelector('.card-body').hidden,true);
      localStorage.getItem = () => '[]';
      assert.equal(Object.keys(loadCards()).length,0);
      localStorage.getItem = () => '{';
      assert.equal(Object.keys(loadCards()).length,0);
      localStorage.getItem = () => { throw new Error('storage blocked'); };
      assert.equal(Object.keys(loadCards()).length,0);
    """)


def test_score_source_jump_selects_run_and_section_after_document_load():
    run_js(r"""
      let selected, tabClicked = false;
      const tab = document.querySelector('.tabs button[data-tab="doc"]');
      tab.addEventListener('click', () => { tabClicked = true; });
      S.list = [{name:'fake-run',docs:['T21-X01','T21-X02']}];
      loadDoc = async () => { S.doc.data={sections:{8:{start:'p1:L1'}}}; S.doc.line={'p1:L1':{page:1}}; };
      renderDocRight = () => {};
      goSection = n => { selected = n; };
      await openScoreSource({name:'fake-run',details:[]},{name:'8항 노출기준',section:8});
      assert.equal(tabClicked,true);
      assert.equal(document.activeElement,tab);
      assert.equal(S.doc.run,'fake-run');
      assert.equal(S.doc.doc,'T21-X01');
      assert.equal(selected,8);
      assert.equal(S.doc.open.has('s8'),true);
    """)


def test_score_loading_displays_count_before_scoring_finishes():
    run_js(r"""
      let release;
      const scoring = new Promise(resolve => { release = resolve; });
      api = async path => {
        if (path === '/api/runs?count=1') return {count:7};
        if (path === '/api/runs') return scoring;
        if (path === '/api/silver_gaps') return [];
        throw new Error(path);
      };
      loadRun = async () => { renderStatus(null); };
      initDiff = async () => {};
      initDoc = async () => {};
      const loading = loadAll();
      await new Promise(resolve => setTimeout(resolve,0));
      assert.match(document.getElementById('status-card').textContent,/실행 7개를 채점하는 중/);
      release({runs:[],criteria:{},doc_time_limit:300,current:null});
      await loading;
      assert.doesNotMatch(document.getElementById('status-card').textContent,/채점하는 중/);
    """)
