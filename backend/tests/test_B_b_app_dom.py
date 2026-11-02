"""점수판 조작을 작은 DOM 대역으로 검사한다. 실제 브라우저 배치 검사를 대신하지 않는다."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


import re
import runpy
from html.parser import HTMLParser

STATIC = Path(__file__).resolve().parents[1] / "scripts" / "b_app_static"
INDEX = STATIC / 'index.html'
SCRIPT_PATHS = re.findall(r'<script\s+src="/static/(js/[^" ]+\.js)"', INDEX.read_text())
SCRIPTS = [STATIC / p for p in SCRIPT_PATHS if p != 'js/boot.js']


def ui_text():
    return runpy.run_path(str(STATIC.parent / 'b_app_text.py'))['POLISH_TEXT']


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = {'tag': 'document', 'attrs': {}, 'kids': []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = {'tag': tag, 'attrs': dict(attrs), 'kids': []}
        self.stack[-1]['kids'].append(el)
        if tag not in {'meta', 'link', 'input', 'img', 'br', 'hr'}:
            self.stack.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]['tag'] == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        self.stack[-1]['kids'].append(data)


DOM = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tagName=tag; this.attrs={}; this.children=[]; this.events={};
    this.hidden=false; this.style={setProperty(k,v){this[k]=String(v);},getPropertyValue(k){return this[k]||'';}};
    this.value=''; this.checked=false; this.disabled=false; this.open=false; }
  insert(index,kids) { for (const value of kids) {
    const k=value instanceof Element?value:String(value);
    if(k instanceof Element) { if(k.parentElement===this&&this.children.indexOf(k)<index)index--; k.remove(); k.parentElement=this; }
    this.children.splice(index++,0,k);
  } }
  append(...kids) { this.insert(this.children.length,kids); }
  prepend(...kids) { this.insert(0,kids); }
  replaceChildren(...kids) { for(const k of this.children) if(k instanceof Element) k.parentElement=null; this.children=[]; this.append(...kids); }
  setAttribute(k,v) { this.attrs[k]=String(v ?? ''); if(['hidden','disabled','checked','open'].includes(k)) this[k]=true; if(k==='value') this.value=String(v); }
  removeAttribute(k) { delete this.attrs[k]; if(['hidden','disabled','checked','open'].includes(k)) this[k]=false; }
  set open(value){const next=!!value,changed=this._open!==next;this._open=next;
    if(changed&&this.tagName==='details')Promise.resolve().then(()=>this.dispatchEvent({type:'toggle'}));}
  get open(){return this._open||false;}
  getAttribute(k) { return this.attrs[k] ?? null; }
  get id(){return this.attrs.id || '';}
  get dataset(){return Object.fromEntries(Object.entries(this.attrs).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()),v]));}
  get textContent(){return this.children.map(x=>x instanceof Element?x.textContent:String(x)).join('');}
  set textContent(s){this.replaceChildren(String(s));}
  set innerHTML(s){this.replaceChildren(new Element('svg'));}
  get firstChild(){return this.children[0];}
  get childNodes(){return [...this.children];}
  get classList(){const self=this; return {contains:c=>(self.attrs.class||'').split(' ').includes(c),
    toggle(c,on){const a=new Set((self.attrs.class||'').split(' ').filter(Boolean)); if(on===undefined)on=!a.has(c); on?a.add(c):a.delete(c); self.attrs.class=[...a].join(' ');},
    add(c){this.toggle(c,true);},remove(c){this.toggle(c,false);}};}
  matches(sel){
    if(sel==='*')return true;
    const attrs=[...sel.matchAll(/\[([^=\]]+)(?:="([^"]*)")?\]/g)];
    if(attrs.some(([,k,v])=>!(k in this.attrs)||(v!==undefined&&this.attrs[k]!==v)))return false;
    sel=sel.replace(/\[[^\]]+\]/g,'');
    const id=sel.match(/#([\w-]+)/), cls=[...sel.matchAll(/\.([\w-]+)/g)],tag=sel.match(/^[\w-]+/);
    return (!id||this.id===id[1])&&cls.every(([,c])=>this.classList.contains(c))&&(!tag||this.tagName===tag[0]);
  }
  querySelectorAll(sel){const all=this.children.filter(x=>x instanceof Element).flatMap(x=>[x,...x.querySelectorAll('*')]);
    return all.filter(x=>sel.split(',').some(part=>{const bits=part.trim().split(/\s+/);if(!x.matches(bits.pop()))return false;
      let p=x.parentElement;while(bits.length){const match=bits.pop();while(p&&!p.matches(match))p=p.parentElement;if(!p)return false;p=p.parentElement;}return true;}));}
  querySelector(sel){return this.querySelectorAll(sel)[0]||null;}
  closest(sel){return sel.split(',').some(s=>this.matches(s.trim()))?this:this.parentElement?.closest(sel)||null;}
  contains(el){return el===this||this.querySelectorAll('*').includes(el);}
  remove(){if(this.parentElement){this.parentElement.children=this.parentElement.children.filter(x=>x!==this);this.parentElement=null;}}
  before(...kids){const p=this.parentElement;if(p)p.insert(p.children.indexOf(this),kids);}
  after(...kids){const p=this.parentElement;if(p)p.insert(p.children.indexOf(this)+1,kids);}
  replaceWith(...kids){const p=this.parentElement;if(p){const index=p.children.indexOf(this);this.remove();p.insert(index,kids);}}
  get isConnected(){return this===document||!!this.parentElement?.isConnected;}
  addEventListener(k,fn){(this.events[k]||=[]).push(fn);}
  dispatchEvent(e){e.target ||= this;e.preventDefault ||= ()=>{e.defaultPrevented=true;};let result;
    for(const fn of this.events[e.type]||[])result=fn(e);if(e.bubbles&&this.parentElement)this.parentElement.dispatchEvent(e);return result;}
  click(){if(!this.disabled)return this.dispatchEvent({type:'click',bubbles:true});}
  focus(){document.activeElement=this;this.dispatchEvent({type:'focusin',bubbles:true});}
  showModal(){this.open=true;}
  close(){this.open=false;this.dispatchEvent({type:'close'});}
  getBoundingClientRect(){return {left:20,top:20,right:100,bottom:40};}
  get offsetWidth(){return 220;}
  get offsetHeight(){return 60;}
}
const document=new Element('document');
document.createElement=tag=>new Element(tag);
document.createElementNS=(_,tag)=>new Element(tag);
document.getElementById=id=>document.querySelector('#'+id);
const store=new Map();
const localStorage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)};
const location={hash:''};
const history={replaceState:(_,__,url)=>{location.hash=url;},pushState:(_,__,url)=>{location.hash=url;}};
let now=0, timerId=0;
const timers=new Map();
function clockTick(ms){now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();if(t.repeat)timers.set(id,{...t,at:now+t.repeat});}}
const timeout=(fn,ms=0)=>{const id=++timerId;timers.set(id,{fn,at:now+ms});return id;};
const interval=(fn,ms)=>{const id=timeout(fn,ms);timers.get(id).repeat=ms;return id;};
const win=new Element('window');win.innerWidth=1440;win.innerHeight=900;
const context=vm.createContext({Node:Element,document,localStorage,store,location,history,window:win,console,assert,
  URLSearchParams,AbortController,CSS:{escape:s=>s},setTimeout:timeout,clearTimeout:id=>timers.delete(id),setInterval:interval,clearInterval:id=>timers.delete(id),clockTick,timers,
  fetch:async()=>{throw new Error('Unexpected network call');}});
function hydrate(node,parent){if(typeof node==='string'){parent.append(node);return;}const el=new Element(node.tag);
  for(const [k,v] of Object.entries(node.attrs))el.setAttribute(k,v);parent.append(el);for(const c of node.kids)hydrate(c,el);}
"""


def run_js(body, *, text=None):
    node = shutil.which('node')
    if not node:
        pytest.skip('DOM 대역 검사에는 설치된 Node가 필요합니다')
    page = _Page()
    page.feed(INDEX.read_text())
    program = DOM + '\n' + ''.join('hydrate(' + json.dumps(k) + ', document);\n' for k in page.root['kids'])
    program += 'document.body=document.querySelector("body");\n'
    program += 'document.getElementById("ui-text").textContent=' + json.dumps(json.dumps(ui_text() if text is None else text)) + ';\n'
    for path in SCRIPTS:
        program += 'vm.runInContext(' + json.dumps(path.read_text()) + ',context,{filename:' + json.dumps(path.name) + '});\n'
    program += 'vm.runInContext(' + json.dumps('(async()=>{' + body + '})()') + ',context).then(()=>console.log("DOM_TEST_DONE"),e=>{console.error(e);process.exitCode=1;});'
    result = subprocess.run([node, '-'], input=program, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'DOM_TEST_DONE' in result.stdout, 'DOM test did not finish its awaited assertions'


def test_scripts_exist_and_boot_is_last():
    assert SCRIPTS
    assert all(p.is_file() for p in SCRIPTS)
    assert SCRIPT_PATHS[-1] == 'js/boot.js'
    assert (STATIC / 'js/boot.js').read_text().strip() == 'start();'


def test_script_top_level_names_are_unique():
    seen = {}
    for path in sorted((STATIC / 'js').glob('*.js')):
        for name in re.findall(r'^(?:(?:async\s+)?function|const|let|class)\s+(\w+)', path.read_text(), re.M):
            assert name not in seen, (name, path, seen.get(name))
            seen[name] = path.name


# 주석과 문자열을 한 번에 훑는다. 따옴표를 담은 정규식 리터럴은 쓰지 않는다.
JS_TOKENS = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')


def test_static_rules_no_modules_korean_strings_external_addresses_or_motion():
    html = INDEX.read_text()
    assert not re.search(r'type\s*=\s*[\'\"]module', html)
    assert not re.search('[가-힣]', re.sub(r'<title>.*?</title>', '', html, flags=re.S))
    for path in [INDEX, STATIC / 'app.css', *sorted((STATIC / 'js').glob('*.js'))]:
        source = path.read_text()
        assert not re.search(r'https?://', source), path
        if path.suffix == '.js':
            assert not re.search(r'^\s*(import|export)\b', source, re.M), path
            for token in JS_TOKENS.findall(source):
                if not token.startswith(('/', '/*')):
                    assert not re.search('[가-힣]', token), (path, token)
    css = (STATIC / 'app.css').read_text()
    assert 'word-break: keep-all' in css
    assert not re.search(r'break-all|@keyframes|backdrop-filter|\banimation\s*:|\btransition\s*:', css)


def test_all_scripts_load_without_boot():
    run_js('assert.equal(typeof start,"function"); assert.ok(S.focus);')
