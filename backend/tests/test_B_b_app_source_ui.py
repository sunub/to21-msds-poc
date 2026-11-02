"""S02 원문 보기. 직접 만든 자료와 API 대역만 사용한다."""
import json
import runpy
from pathlib import Path

import pytest

from test_B_b_app_dom import run_js


# /api/doc의 row_groups(b_app_doc.row_groups)와 같은 모양을 값 목록에서 만든다. 시험이 값을 바꾼 뒤에도 맞도록 요청 때 만든다.
ROW_GROUPS = r"""
const rowGroupsOf=d=>{
 const kindOf=(v,side)=>side==='silver_only'?'missing':!d.has_gold?'uncompared':v.silver?.same===true?'same':v.silver?.value==null?'made':'wrong';
 const groups=new Map();
 for(const [side,cells] of [['result',d.values],['silver_only',d.silver_only]])for(const v of cells){
  const own=side==='result'?v.row:v.pair_row;
  const key=v.row==null?side+':'+v.path:own==null?'gold:'+v.table+':'+v.row:'result:'+v.table+':'+own;
  if(!groups.has(key))groups.set(key,{id:key,table:v.table,table_label:'Fake table',section:v.section,row:v.row==null?null:own??null,
   gold_row:v.row==null?null:own==null?v.row:v.silver?.value==null?null:own,paired:v.row==null||!d.has_gold?null:own!=null,
   title:'Fake row '+(v.row??v.path),cells:[],counts:{wrong:0,made:0,missing:0}});
  const g=groups.get(key),kind=kindOf(v,side);
  g.cells.push({path:v.path,side,field:v.field,section:v.section,kind,items:v.items});
  if(kind in g.counts)g.counts[kind]++;
 }
 return [...groups.values()];
};
"""


def fixture():
    bt = runpy.run_path(str(Path(__file__).parents[1] / 'scripts/b_app_text.py'))
    def value(name, *, same=False, made=False, section=8, items=None, lines=None):
        return dict(path=f'msds[0].exposure_limits[{name}].q', field='q', table='exposure_limits',
                    row=name, section=section, value={'value': 8, 'unit': 'fake-unit', 'approx': False}, text='8 fake-unit',
                    lines=['p2:L3'] if lines is None else lines, items=['Fake criterion'] if items is None else items,
                    silver={'same': same, 'value': None if made else {'value': 5, 'unit': 'fake-unit'},
                            'text': None if made else '5 fake-unit'})
    view = dict(doc_id='T21-X01', pages=[1, 2], lines=[
        dict(id='p1:L1', page=1, no=1, text='Fake heading', bbox=None),
        dict(id='p2:L3', page=2, no=3, text='<em>Fake evidence</em>', bbox=[10, 20, 80, 40]),
        dict(id='p2:L4', page=2, no=4, text='Fake estimated evidence', bbox=None)],
        sections={'8': {'start': 'p2:L3', 'end': 'p2:L4', 'method': 'title'}},
        values=[value(0, made=True), value(1), value(2, same=True), value(3, items=['Other criterion']),
                value(4, lines=['p9:L999'])],
        silver_only=[dict(path='msds[0].exposure_limits[5].q', section=8, table='exposure_limits', row=5,
                          field='q', value={'value': 2, 'unit': 'fake-unit'}, text='2 fake-unit', pair_row=None,
                          items=['Fake criterion'], lines=['p2:L4'])],
        line_index={'p2:L3': [f'msds[0].exposure_limits[{i}].q' for i in range(4)]},
        has_gold=True, silver_lines={'basis': 'text_match', 'found': 4, 'total': 6}, warnings=['Fake warning'],
        set={'id': 'prev/fake', 'label': 'Recorded fake input', 'source': 'moved', 'note': 'Fake moved input note'},
        image_base='/fake-image-contract/T21-X01/', image_query='?set=prev%2Ffake',
        key={'id': 'gold/fake', 'label': 'Reviewed fake answers'})
    view['legend'] = bt['doc_legend']()
    view['ui_text'] = bt['doc_ui_text'](view)
    return ROW_GROUPS + "const view=" + json.dumps(view) + r""";
S.shell.contextLoaded=true; S.ctx={version:1,set:'next/fake',key:'gold/fake'};
const runs=[{name:'older',docs:['T21-X04'],no_gold:[]},
 {name:'current',label:{title:'Current fake result'},docs:['T21-X01','T21-X02'],no_gold:['T21-X03']}];
S.score.name='current';S.score.list=runs;S.score.run=runs[1];
S.shell.sets=[{id:'prev/fake',label:'Recorded fake input',usable:true,counts:{dev:4,eval_locked:1,outside:0},
 docs:['T21-X01','T21-X02','T21-X03','T21-X04'].map(doc_id=>({doc_id,group:'dev',locked:false,reason:null}))
 .concat([{doc_id:'T21-X99',group:'eval',locked:true,reason:'Fake evaluation lock'}])},
 {id:'next/fake',label:'Next fake input',usable:true,counts:{dev:0,eval_locked:0,outside:1},
 docs:[{doc_id:'RAW-X01',group:'outside',locked:false,reason:null}]}];
const calls=[];
api=async path=>{calls.push(path);const [base,q]=path.split('?');const p=new URLSearchParams(q);
 if(base==='/api/runs')return {runs,current:'older'};
 if(base==='/api/doc')return {...view,doc_id:p.get('doc'),row_groups:rowGroupsOf(view)};
 if(base.startsWith('/api/run/'))return runs.find(r=>r.name===decodeURIComponent(base.slice('/api/run/'.length)));
 throw new Error('Unexpected '+path);};
const el=id=>document.getElementById(id);
const screen=()=>el('screen-s02').textContent;
// 값 단추는 그 값의 행을 볼 때만 있다. 없으면 그 행을 먼저 연다. 고르지는 않는다.
const pick=(n,side='result')=>{
 const path='msds[0].exposure_limits['+n+'].q',only=side==='silver_only';
 const found=()=>Array.from(document.querySelectorAll("[data-source-path]")).find(e=>e.dataset.sourcePath===path&&e.dataset.side===side)||null;
 if(!found()&&S.source.data&&sourceRowOf(path,only)){S.source.rowId=sourceRowOf(path,only).id;S.source.step='compare';sourceRenderAll();}
 return found();
};
const flush=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const openDrawer=()=>{drawerClose();el('source-details-open').click();return document.querySelector('#details-drawer .drawer-body');};
const change=async(id,value)=>{const e=el(id);e.value=value;await e.dispatchEvent({type:'change'});};
"""


def test_source_first_open_current_run_then_preserves_manual_document_value_and_page():
    run_js(fixture() + r"""
await go('s02');assert.equal(S.source.run,'current');assert.equal(S.source.doc,'T21-X01');
await change('source-doc-select','T21-X02');pick(1).click();
S.score.name='older';S.score.run=runs[0];await go('s03');await go('s02');
assert.equal(S.source.run,'current');assert.equal(S.source.doc,'T21-X02');assert.equal(S.source.page,2);
assert.equal(pick(1).getAttribute('aria-pressed'),'true');
sourceGoStep('choose');await change('source-run-select','older');assert.equal(S.source.doc,'T21-X04');
assert.equal(S.source.selection,null);
""")


def test_source_key_default_input_and_response_metadata_image_contract():
    run_js(fixture() + r"""
await go('s02',{run:'current',section:8});
const request=new URLSearchParams(calls.find(x=>x.startsWith('/api/doc?')).split('?')[1]);
assert.equal(request.get('key'),'gold/fake');assert.equal(request.has('set'),false);
assert.equal(el('source-page').querySelector('img').getAttribute('src'),view.image_base+'p002.png'+view.image_query);
assert.ok(el('source-page').querySelector('img').getAttribute('alt').includes('2'));
sourceGoStep('choose');
assert.ok(screen().includes(view.set.label));assert.ok(screen().includes(view.set.note));
assert.ok(screen().includes(T('source.origin.moved')));
await change('source-set-select','prev/fake');assert.ok(calls.at(-1).includes('set=prev%2Ffake'));
""")


def test_source_value_tips_and_raw_json_are_safe_on_all_three_sides():
    run_js(fixture() + r"""
view.values[1].value.text='<em>not markup</em>';view.values[1].text='<em>not markup</em>';
await go('s02',{section:8});
for(const [n,side,v] of [[1,'result',view.values[1].value],[1,'silver',view.values[1].silver.value],[5,'silver_only',view.silver_only[0].value]]){
 const b=pick(n,side);assert.equal(b.tagName,'button');
 assert.ok(b.getAttribute('data-tip').includes(T('source.fields.value')+':'));
 b.click();assert.equal(el('source-selection').querySelector('details'),null);
 const body=openDrawer(),raw=body.querySelector('.source-raw');
 assert.ok(body.textContent.includes(T('steps.source.raw_value_title')));
 assert.deepEqual(JSON.parse(raw.querySelector('pre').textContent),v);
 assert.equal(el('screen-s02').querySelector('em'),null);drawerClose();
}
""")


def test_source_legend_section_summaries_and_visible_comparison_states():
    run_js(fixture() + r"""
await go('s02',{section:8});
// 색으로 구분하는 것은 선택 표시뿐이다. 값의 세 상태는 글자로 구분하므로 색 칸을 그리지 않는다.
const chips=el('source-selection').querySelectorAll('.source-chip');assert.equal(chips.length,1);
assert.ok(chips[0].getAttribute('style').includes(view.legend.find(x=>x.key==='picked').color));
view.legend.forEach(x=>assert.ok(el('source-selection').textContent.includes(x.label)));
for(const key of ['same','different','missing'])assert.ok(el('source-selection').textContent.includes(T('source.legend.'+key)));
// P1-04: 항 선택은 원문만 이동하고 상세는 사용자가 연다.
assert.equal(document.querySelector('[data-source-section="8"]'),null);
const body=openDrawer();assert.ok(body.textContent.includes(view.ui_text.howto));
el('source-structure-open').click();assert.ok(body.textContent.includes(view.ui_text.sections['8']));
""")


def test_source_line_buttons_image_failure_and_empty_page_are_not_blank():
    run_js(fixture() + r"""
await go('s02',{section:8});const line=el('source-page').querySelector('[data-line="p2:L3"]');
assert.equal(line.tagName,'button');line.click();
assert.equal(line.getAttribute('aria-pressed'),'true');assert.ok(line.classList.contains('source-highlight'));
assert.equal(pick(1).getAttribute('aria-pressed'),'true');
const img=el('source-page').querySelector('img');img.dispatchEvent({type:'error'});
assert.ok(el('source-page').textContent.includes(T('source.page.no_image')));
assert.ok(el('source-page').textContent.includes('<em>Fake evidence</em>'));
view.lines=[];view.pages=[];await sourceLoad(true);
assert.ok(screen().includes(T('source.empty.pages')));assert.equal(el('source-page').querySelector('img'),null);
""")


def test_source_evidence_event_only_after_rendered_highlight_and_once():
    run_js(fixture() + r"""
const events=[];on('evidence_line_shown',event=>{
 const line=el('source-page').querySelector('[data-line="'+event.line+'"]');
 assert.ok(line.isConnected);assert.equal(line.getAttribute('aria-pressed'),'true');
 assert.equal(el('screen-s02').hidden,false);events.push(event);});
await go('s02',{section:8,item:'Fake criterion'});
pick(4).click();assert.equal(events.length,0);
pick(5,'silver_only').click();assert.equal(events.length,0);
pick(1).click();pick(1).click();assert.equal(events.length,1);
assert.deepEqual(events[0],{run:'current',doc:'T21-X01',section:8,path:view.values[1].path,
 line:'p2:L3',mismatch:true,item:'Fake criterion'});
el('screen-s02').hidden=true;pick(0).click();assert.equal(events.length,1);
""")


def test_source_no_event_for_nonexistent_page_or_detached_highlight():
    run_js(fixture() + r"""
view.pages=[1];const events=[];on('evidence_line_shown',e=>events.push(e));
await go('s02');pick(1).click();assert.equal(events.length,0);
""")


def test_source_item_problem_filters_counts_and_wrong_first():
    run_js(fixture() + r"""
// F07: 칸 단위 집계는 실행 API가 제공하며 화면은 다시 세지 않는다.
S.score.run={...runs[1],status_text:{top_problem:{name:'Fake criterion',counts_basis:'field',
 counts:{'빠뜨림':1,'틀림':2,'지어냄':1},docs:[{doc_id:'T21-X01'}]}}};
await go('s02',{run:'current',doc:'T21-X01',section:8,item:'Fake criterion',pick:'mismatch'});
assert.equal(S.source.selection.path,view.values[1].path);
assert.equal(el('source-filter-all').textContent,T('source.filter.all_values'));
for(const [kind,count] of [['wrong',2],['made',1],['missing',1]]){
 assert.equal(el('source-filter-'+kind).textContent,T('source.filter.'+kind,{count}));
 el('source-filter-'+kind).click();
 assert.equal(el('source-problem-list').querySelectorAll('button').length,count);
}
assert.ok(!el('source-problem-list').textContent.includes(view.values[3].path));
""")


@pytest.mark.parametrize('remove,expected', [([1, 4], 0), ([0, 1, 4], 5)])
def test_source_mismatch_falls_back_to_made_then_missing(remove, expected):
    run_js(fixture() + 'view.values=view.values.filter(v=>!' + json.dumps(remove) + '.includes(v.row));' + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
""" + f"assert.equal(S.source.selection.path,'msds[0].exposure_limits[{expected}].q');")


def test_source_estimated_lines_have_distinct_text_style_and_no_guess_state():
    run_js(fixture() + r"""
await go('s02');pick(5,'silver_only').click();
const line=el('source-page').querySelector('[data-line="p2:L4"]');
assert.ok(line.classList.contains('source-estimated'));assert.ok(line.textContent.includes(T('source.missing.evidence_title')));
assert.ok(el('source-selection').textContent.includes(T('source.doc.guess')));
assert.ok(openDrawer().textContent.includes(T('source.estimation.coverage',{total:6,matched:4})));drawerClose();
view.silver_only[0].lines=[];await sourceLoad(true);pick(5,'silver_only').click();
assert.ok(el('source-selection').textContent.includes(T('source.doc.no_guess')));
assert.equal(el('source-page').querySelectorAll('.source-highlight').length,0);
""")


def test_source_locked_document_is_never_requested_and_404_is_absent_not_protected():
    run_js(fixture() + r"""
await go('s02',{run:'current',doc:'T21-X99'});
assert.ok(!calls.some(x=>x.startsWith('/api/doc?')));
assert.ok(screen().includes('Fake evaluation lock'));assert.ok(screen().includes(T('source.locked.title')));
const lockedText=screen();api=async()=>{const e=new Error('missing');e.status=404;throw e;};
await go('s02',{run:'current',doc:'T21-X01'});
assert.ok(screen().includes(T('source.empty.document')));assert.ok(screen()!==lockedText);
assert.equal(el('source-page').querySelector('img'),null);
""")


def test_source_loading_failure_retry_no_stale_values_and_raw_text():
    run_js(fixture() + r"""
await go('s02');const base=api;let release;
api=()=>new Promise(resolve=>release=resolve);const pending=sourceLoad(true);await flush();
assert.ok(screen().includes(T('source.loading')));assert.equal(pick(1),null);
release({...view});await pending;
api=async()=>{throw new Error('<b>fake error</b>');};await sourceLoad(true);
const err=el('source-top').querySelector('.error-note');assert.ok(err);
assert.ok(err.textContent.includes(T('source.load_failed.fact')));
assert.ok(err.textContent.includes(T('source.load_failed.todo')));
assert.equal(err.querySelector('details'),null);assert.ok(!err.textContent.includes('fake error'));
openDrawer();assert.equal(Array.from(document.querySelectorAll('#details-drawer pre')).at(-1).textContent,'<b>fake error</b>');drawerClose();
api=base;await el('source-reload').click();assert.ok(pick(1));assert.ok(!/null|undefined|⟦/.test(screen()));
""")


def test_source_latest_document_and_key_win_races_and_key_reload_keeps_manual_choice():
    run_js(fixture() + r"""
await go('s02',{section:8});pick(1).click();sourceGoStep('choose');const base=api;let release;
api=path=>path.includes('doc=T21-X02')?new Promise(resolve=>release=resolve):base(path);
const old=change('source-doc-select','T21-X02');await flush();
await change('source-doc-select','T21-X03');release({...view,doc_id:'T21-X02'});await old;
assert.equal(S.source.data.doc_id,'T21-X03');
pick(1).click();S.ctx.key='gold/new';emit('context_changed');await S.source.pending;
assert.ok(calls.at(-1).includes('key=gold%2Fnew'));assert.equal(S.source.doc,'T21-X03');
assert.equal(S.source.selection.path,view.values[1].path);
""")


def test_source_retest_focus_preserves_chosen_value_location_and_estimation():
    run_js(fixture() + r"""
await go('s02',{section:8,item:'Fake criterion'});pick(5,'silver_only').click();
await el('source-retest').click();assert.equal(S.shell.route,'s03');
for(const [k,v] of Object.entries({run:'current',doc:'T21-X01',section:8,item:'Fake criterion',
 path:view.silver_only[0].path,kind:'missing',page:2,line:'p2:L4',estimated:true,source_set:'prev/fake'}))assert.equal(S.focus[k],v,k);
assert.deepEqual(S.focus.expected,view.silver_only[0].value);assert.equal(S.focus.actual,null);
await go('s02');assert.equal(S.source.selection.path,view.silver_only[0].path);
""")


def test_source_raw_mode_uses_set_docs_and_no_run_or_false_problem_counts():
    run_js(fixture() + r"""
await go('s02');await el('source-raw-open').click();
assert.equal(S.source.run,null);assert.equal(S.source.doc,'RAW-X01');
const p=new URLSearchParams(calls.at(-1).split('?')[1]);assert.equal(p.has('run'),false);
assert.equal(p.get('set'),'next/fake');assert.ok(screen().includes(T('source.raw.title')));
""")


def test_source_no_gold_no_matching_problem_unknown_section_and_deleted_path():
    run_js(fixture() + r"""
view.has_gold=false;view.silver_only=[];await go('s02',{item:'Fake criterion',pick:'mismatch'});
assert.equal(S.source.selection,null);assert.ok(screen().includes(T('source.empty.answer')));
view.has_gold=true;await sourceLoad(true);await go('s02',{item:'Absent criterion',section:12,pick:'mismatch'});
assert.equal(S.source.selection,null);assert.ok(screen().includes(T('source.empty.problems')));
await go('s02',{section:12,path:'gone',item:null});
assert.ok(screen().includes(T('source.value_gone.title')));
assert.ok(screen().includes(T('source.section_unknown.title',{section:12})));
""")


def test_source_actual_score_button_reaches_source_and_selects_criterion():
    run_js(fixture() + r"""
await scoreOpenSource({name:'Fake criterion',section:8,docs:[{doc_id:'T21-X02'}]});
assert.equal(S.shell.route,'s02');assert.equal(S.source.doc,'T21-X02');
assert.equal(S.source.selection.path,view.values[1].path);assert.equal(S.source.page,2);
""")


def test_source_start_hash_waits_for_context_before_any_doc_request():
    run_js(fixture() + r"""
S.shell.contextLoaded=false;S.ctx={version:1,set:null,key:null};location.hash='#s02';
const sets=S.shell.sets,base=api;let release;
api=path=>{
 if(path==='/api/sets')return new Promise(resolve=>release=resolve);
 if(path==='/api/keys')return Promise.resolve({default:'gold/fake',keys:[{id:'gold/fake',label:'Fake key',usable:true}]});
 if(path==='/api/servers')return Promise.resolve({models:[]});return base(path);};
const starting=start();await flush();assert.ok(!calls.some(x=>x.startsWith('/api/doc?')));
release({default:'prev/fake',sets});await starting;await flush();await S.source.pending;
assert.ok(calls.some(x=>x.includes('/api/doc?')&&x.includes('key=gold%2Ffake')));
assert.ok(!/null|undefined|⟦/.test(screen()));
""")


def test_source_stale_navigation_does_not_apply_old_pick_to_new_doc():
    run_js(fixture() + r"""
const base=api;let release;api=path=>path.includes('doc=T21-X01')?new Promise(resolve=>release=resolve):base(path);
const old=go('s02',{run:'current',doc:'T21-X01',path:view.values[0].path});await flush();
await go('s02',{run:'current',doc:'T21-X02',path:view.values[1].path});
release({...view});await old;
assert.equal(S.source.doc,'T21-X02');assert.equal(S.source.selection.path,view.values[1].path);
""")


def test_source_removed_run_and_unknown_document_are_not_requested():
    run_js(fixture() + r"""
await go('s02');S.score.list=[];S.score.name=null;S.score.run=null;
await go('s02');assert.equal(S.source.doc,null);assert.equal(S.source.data,null);
S.score.list=runs;S.score.name='current';calls.length=0;
await go('s02',{run:'current',doc:'T21-X98'});assert.ok(!calls.some(x=>x.startsWith('/api/doc?')));
assert.ok(screen().includes(T('source.empty.document')));
""")


def test_source_bbox_uses_natural_image_coordinates_and_line_first_event():
    run_js(fixture() + r"""
const events=[];on('evidence_line_shown',x=>events.push(x));await go('s02',{section:8,item:'Fake criterion'});
pick(1).click();const img=el('source-page').querySelector('img');img.naturalWidth=800;img.naturalHeight=1200;
img.dispatchEvent({type:'load'});const svg=el('source-page').querySelector('svg');
assert.equal(svg.getAttribute('viewBox'),'0 0 800 1200');const rect=svg.querySelector('rect');
for(const [key,value] of Object.entries({x:'10',y:'20',width:'70',height:'20'}))assert.equal(rect.getAttribute(key),value);
el('source-page').querySelector('[data-line="p2:L3"]').click();
assert.equal(events.filter(x=>x.path===view.values[1].path).length,1);
assert.ok(events.some(x=>x.path===view.values[2].path&&x.mismatch===false));
assert.ok(!events.some(x=>x.path===view.silver_only[0].path));
""")


def test_source_new_doc_keeps_item_filter_but_manual_choice_survives_menu_reentry():
    run_js(fixture() + r"""
await go('s02',{item:'Fake criterion',section:8,pick:'mismatch'});pick(0).click();
await go('s03');await go('s02');assert.equal(S.source.selection.path,view.values[0].path);
sourceGoStep('choose');await change('source-doc-select','T21-X02');assert.equal(S.source.item,'Fake criterion');
assert.equal(S.source.section,8);assert.equal(S.source.selection,null);
""")


def test_source_unrelated_value_does_not_claim_the_requested_criterion():
    run_js(fixture() + r"""
const events=[];on('evidence_line_shown',e=>events.push(e));
await go('s02',{item:'Fake criterion',section:8});pick(3).click();
assert.equal(events.length,1);assert.equal(events[0].item,null);
""")


def test_source_page_change_and_line_selection_survive_reload_and_return():
    run_js(fixture() + r"""
await go('s02',{section:8});el('source-page').querySelector('[data-line="p2:L3"]').click();
await sourceLoad(true);assert.equal(S.source.page,2);
assert.equal(el('source-page').querySelector('[data-line="p2:L3"]').getAttribute('aria-pressed'),'true');
await change('source-page-select','1');await go('s03');await go('s02');assert.equal(S.source.page,1);
""")


def test_source_raw_run_selection_uses_global_docs_and_request_scope():
    run_js(fixture() + r"""
await go('s02');await change('source-run-select','');
assert.equal(S.source.doc,'RAW-X01');
const p=new URLSearchParams(calls.at(-1).split('?')[1]);assert.equal(p.has('run'),false);
assert.equal(p.get('set'),'next/fake');
""")


def test_source_initial_run_list_failure_is_recoverable_without_unhandled_rejection():
    run_js(fixture() + r"""
S.score.list=[];S.score.name=null;S.score.run=null;const base=api;
api=async()=>{throw new Error('Fake list read failure');};await go('s02');
assert.ok(el('source-top').querySelector('.error-note'));
assert.ok(openDrawer().textContent.includes('Fake list read failure'));drawerClose();
api=base;await el('source-reload').click();assert.ok(S.source.data);
""")


# 대역 DOM은 화면 배치를 계산하지 않는다. 실제 브라우저처럼 붙지 않은 요소의 scrollTop은 버리고,
# 고정 막대·비교 카드·원문 줄의 위치를 정해 둔다.
_LAYOUT = r"""
const proto=Node.prototype;
Object.defineProperty(proto,'scrollTop',{configurable:true,get(){return this._scrollTop||0;},set(v){if(this.isConnected)this._scrollTop=v;}});
Object.defineProperty(proto,'clientHeight',{configurable:true,get(){return 300;}});
const baseRect=proto.getBoundingClientRect;
let panelRect={top:524,bottom:973};
proto.getBoundingClientRect=function(){
  if(this.dataset?.line){const b=this.parentElement,t=100+b.children.indexOf(this)*400-(b.scrollTop||0);return {top:t,bottom:t+100,left:0,right:10};}
  if(this.id==='source-lines')return {top:100,bottom:400,left:0,right:10};
  if(this.id==='source-selection')return {left:0,right:10,...panelRect};
  if(this.id==='global-context')return {top:0,bottom:145,left:0,right:10};
  return baseRect.call(this);
};
const scrolled=[];
proto.scrollIntoView=function(options){scrolled.push({target:this.id||this.dataset?.line||'element',block:options?.block});};
const landing={run:'current',doc:'T21-X01',section:8,item:'Fake criterion',pick:'mismatch'};
"""


def test_source_line_list_stays_on_the_picked_line_after_the_screen_renders():
    run_js(fixture() + _LAYOUT + r"""
view.values[1].lines=['p2:L4'];
await go('s02',landing);await flush();
assert.equal(S.source.selection.path,'msds[0].exposure_limits[1].q');
// 고른 줄이 목록 바깥에 있으면 안 된다. 다시 그려도 목록을 맨 위로 되돌리지 않는다.
assert.equal(el('source-lines').scrollTop,300);
assert.equal(S.source.scroll[2],300);
""")


def test_source_line_list_restores_the_saved_position_when_it_is_drawn_again():
    run_js(fixture() + _LAYOUT + r"""
await go('s02',{run:'current',doc:'T21-X01',section:8});await flush();
S.source.scroll[S.source.page]=120;
sourceRenderPage();
assert.equal(el('source-lines').scrollTop,120);
""")


def test_source_opening_a_problem_or_picking_a_value_does_not_move_the_window():
    # PR #123: 창을 움직이면 비교 카드가 고정 막대에 가린다. 이제 페이지가 스크롤하지 않으므로 움직일 일이 없다.
    run_js(fixture() + _LAYOUT + r"""
await go('s02',landing);await flush();assert.deepEqual(scrolled,[]);
pick(1).click();assert.deepEqual(scrolled,[]);
pick(5,'silver_only').click();assert.deepEqual(scrolled,[]);
assert.equal(el('source-actions').querySelector('#source-retest').disabled,false);
""")


def test_source_opening_without_a_problem_or_picking_a_line_does_not_move_the_page():
    run_js(fixture() + _LAYOUT + r"""
await go('s02',{run:'current',doc:'T21-X01',section:8});await flush();
assert.deepEqual(scrolled,[]);
await change('source-page-select','2');
document.querySelector('[data-line="p2:L3"]').click();
assert.deepEqual(scrolled,[]);
""")


def test_source_comparison_card_leaves_room_for_the_fixed_bar():
    # 옛 scroll-margin 계약의 뜻: 막대 아래 고정 작업 영역 안에 있어 가리지 않는다.
    import re
    css = (Path(__file__).parents[1] / 'scripts/b_app_static/app.css').read_text()
    assert re.search(r'\.work:has\(> #screen-s02:not\(\[hidden\]\)\)\s*\{[^}]*overflow:\s*hidden', css)
    assert re.search(r'#source-stage\s*\{[^}]*flex:\s*1[^}]*min-height:\s*0', css)


# ── 3단계: 문제 고르기 → 원문과 맞춰 보기 → 다시 시험으로 보내기 (ADR-039) ──
STEPS = r"""
const stepNow=()=>el('source-step-bar').querySelector('[aria-current="step"]').textContent;
const atStep=key=>assert.ok(stepNow().includes(T('steps.source.'+key)),stepNow());
const rowButton=id=>el('source-problem-list').querySelector('[data-row-id="'+id+'"]');
const row=n=>'result:exposure_limits:'+n;
const folds=()=>el('screen-s02').querySelectorAll('details').length;
const top={name:'Fake criterion',section:8,loss:3.5,level:'필수',rank:1,counts_basis:'field',counts:{'빠뜨림':1,'틀림':2,'지어냄':1}};
const docRows=[{doc_id:'T21-X01',loss:2.5,score:40,counts:{'빠뜨림':1,'틀림':1,'지어냄':1},row_count:3},
 {doc_id:'T21-X02',loss:1,score:70,counts:{'빠뜨림':0,'틀림':1,'지어냄':0},row_count:1}];
const scored={...runs[1],status_text:{top_problem:{...top,docs:docRows},losses:[top,
 {name:'Other criterion',section:8,loss:1.25,level:'권장',rank:2,counts_basis:'field',counts:{'빠뜨림':0,'틀림':1,'지어냄':0}},
 {name:'Clean criterion',section:2,loss:0,level:'권장',rank:3,counts_basis:'field',counts:{'빠뜨림':0,'틀림':0,'지어냄':0}}]},
 problem_rows:{'Fake criterion':{row_count:4,docs:docRows},
  'Other criterion':{row_count:1,docs:[{doc_id:'T21-X01',loss:1.25,score:80,counts:{'빠뜨림':0,'틀림':1,'지어냄':0},row_count:1}]},
  'Clean criterion':{row_count:0,docs:[]}}};
S.score.run=scored;
"""


def test_big_button_from_recent_results_starts_at_compare_and_menu_starts_at_choose():
    run_js(fixture() + STEPS + r"""
await go('s02');atStep('choose');assert.equal(el('source-selection').hidden,true);assert.equal(el('source-page').hidden,true);
await scoreOpenSource({...top,docs:docRows});atStep('compare');
assert.equal(S.source.selection.path,view.values[1].path);
assert.equal(el('source-selection').hidden,false);assert.equal(el('source-page').hidden,false);assert.equal(el('source-top').hidden,true);
// 돌아오면 같은 행과 칸과 쪽을 연다.
await go('s03');await go('s02');atStep('compare');assert.equal(S.source.selection.path,view.values[1].path);
""")


def test_compare_left_list_is_rows_with_a_title_and_kind_counts_and_a_click_opens_the_row():
    run_js(fixture() + STEPS + r"""
await go('s02',{doc:'T21-X01',section:8});atStep('compare');
// 칸이 아니라 행이다: 같은 행의 칸 둘은 단추 하나다.
view.values.push({...view.values[1],path:'msds[0].exposure_limits[1].extra',field:'extra'});await sourceLoad(true);
const button=rowButton(row(1));assert.ok(button);
assert.ok(button.textContent.includes('Fake row 1'));
assert.ok(button.textContent.includes(T('source.kinds.wrong')));
assert.ok(button.textContent.includes(T('steps.source.row_kind',{kind:T('source.kinds.wrong'),count:2})));
assert.equal(el('source-problem-list').querySelectorAll('[data-row-id="'+row(1)+'"]').length,1);
await button.click();await flush();atStep('compare');
assert.equal(sourceCurrentRow().id,row(1));
""")


def test_choose_table_shows_api_loss_rows_and_cells_in_api_order():
    run_js(fixture() + STEPS + r"""
await go('s02');
const table=el('source-top').querySelector('table');assert.ok(table);
const rows=table.querySelector('tbody').querySelectorAll('tr');
assert.equal(rows.length,2);// 깎은 점수가 없는 기준은 맨 앞 표에 넣지 않는다.
assert.ok(rows[0].textContent.includes(T('guide.example.biggest')));
assert.ok(rows[0].textContent.includes(T('steps.source.loss',{points:'3.5'})));
assert.ok(rows[0].textContent.includes(T('compare.rows.unit',{count:4})));
assert.ok(rows[0].textContent.includes(T('source.labels.cells',{count:4})));
assert.ok(rows[1].textContent.includes(T('steps.source.loss',{points:'1.3'})));
assert.ok(!rows[1].textContent.includes(T('guide.example.biggest')));
""")


def test_choose_table_uses_document_values_when_a_document_is_chosen():
    run_js(fixture() + STEPS + r"""
await go('s02');assert.equal(el('source-doc-select').value,'');
await change('source-doc-select','T21-X02');
const rows=el('source-top').querySelector('tbody').querySelectorAll('tr');
assert.equal(rows.length,1);
assert.ok(rows[0].textContent.includes(T('steps.source.loss',{points:'1.0'})));
assert.ok(rows[0].textContent.includes(T('compare.rows.unit',{count:1})));
assert.ok(rows[0].textContent.includes(T('source.labels.cells',{count:1})));
await change('source-doc-select','');
assert.equal(el('source-top').querySelector('tbody').querySelectorAll('tr').length,2);
""")


def test_choose_table_opens_a_criterion_that_is_not_the_top_problem_across_its_documents():
    run_js(fixture() + STEPS + r"""
await go('s02');
const buttons=el('source-top').querySelector('tbody').querySelectorAll('tr')[1].querySelectorAll('button');
// 이름도 단추도 그 항목의 2단계로 간다. 목록에는 그 항목의 행만 있다.
await buttons[0].click();await flush();atStep('compare');assert.equal(S.source.item,'Other criterion');
assert.ok(rowButton(row(3)));assert.equal(rowButton(row(1)),null);
assert.equal(S.source.selection.path,view.values[3].path);
sourceGoStep('choose');
const open=el('source-top').querySelector('tbody').querySelectorAll('tr')[1].querySelector('.source-open-criterion');
await open.click();await flush();atStep('compare');assert.equal(S.source.item,'Other criterion');assert.equal(S.source.selection.path,view.values[3].path);
""")


def test_run_that_is_not_the_score_run_reads_its_own_table():
    run_js(fixture() + STEPS + r"""
S.score.run=runs[0];S.score.name='older';
await go('s02',{run:'current'});
assert.ok(calls.some(p=>p.startsWith('/api/run/current')));
""")


def test_compare_has_cells_of_one_row_image_and_lines_together():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});atStep('compare');
const panel=el('source-selection');
assert.ok(panel.querySelector('h2').textContent.includes('Fake row 1'));
assert.ok(pick(1).isConnected);assert.ok(pick(1,'silver').isConnected);
assert.ok(panel.textContent.includes('8 fake-unit'));assert.ok(panel.textContent.includes('5 fake-unit'));
assert.ok(panel.textContent.includes(T('source.kinds.wrong')));
assert.ok(el('source-page').querySelector('img'));assert.ok(el('source-page').querySelector('[data-line="p2:L3"]'));
assert.equal(el('source-page').querySelector('[data-line="p2:L3"]').getAttribute('aria-pressed'),'true');
assert.equal(pick(1).getAttribute('aria-pressed'),'true');
""")


def test_changing_the_cell_moves_the_image_box_and_the_line_to_the_same_line():
    run_js(fixture() + STEPS + r"""
view.lines[2].bbox=[1,2,3,4];
view.values.push({...view.values[1],path:'msds[0].exposure_limits[1].other',field:'other',lines:['p2:L4'],silver:{same:false,value:1,text:'1'}});
view.line_index['p2:L4']=['msds[0].exposure_limits[1].other'];
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const img=el('source-page').querySelector('img');img.naturalWidth=800;img.naturalHeight=1200;img.dispatchEvent({type:'load'});
assert.equal(el('source-page').querySelector('rect').getAttribute('y'),'20');
const other=Array.from(document.querySelectorAll('[data-source-path]')).find(e=>e.dataset.sourcePath.endsWith('.other')&&e.dataset.side==='result');
other.click();
// 같은 쪽이면 그림을 다시 받지 않는다.
assert.equal(el('source-page').querySelector('img'),img);
assert.equal(el('source-page').querySelector('rect').getAttribute('y'),'2');
assert.equal(el('source-page').querySelector('[data-line="p2:L4"]').getAttribute('aria-pressed'),'true');
assert.equal(el('source-page').querySelector('[data-line="p2:L3"]').getAttribute('aria-pressed'),'false');
assert.equal(sourceCurrentRow().id,row(1));
""")


def test_row_table_uses_plain_field_names_and_keeps_paths_in_the_drawer():
    run_js(fixture() + STEPS + r"""
view.ui_text.value_field_labels={q:'Fake numeric label'};
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const text=el('source-selection').textContent;
assert.ok(text.includes('Fake numeric label'));assert.doesNotMatch(text,/msds\[0\]/);
assert.ok(openDrawer().textContent.includes(view.values[1].path));
""")


_LIST_LAYOUT = r"""
const proto=Node.prototype;
Object.defineProperty(proto,'scrollTop',{configurable:true,get(){return this._scrollTop||0;},set(v){if(this.isConnected)this._scrollTop=v;}});
Object.defineProperty(proto,'clientHeight',{configurable:true,get(){return 300;}});
const baseRect=proto.getBoundingClientRect;
const offset=node=>{const all=Array.from(node.closest('#source-problem-list').querySelectorAll('[data-row-id]'));return all.indexOf(node);};
proto.getBoundingClientRect=function(){
 if(this.dataset?.rowId){const t=100+offset(this)*200-(this.closest('#source-problem-list').scrollTop||0);return {top:t,bottom:t+100,left:0,right:10};}
 if(this.id==='source-problem-list')return {top:100,bottom:400,left:0,right:10};
 if(this.dataset?.line){const b=this.parentElement,t=100+b.children.indexOf(this)*400-(b.scrollTop||0);return {top:t,bottom:t+100,left:0,right:10};}
 if(this.id==='source-lines')return {top:100,bottom:400,left:0,right:10};
 return baseRect.call(this);
};
const scrolled=[];proto.scrollIntoView=function(){scrolled.push(this.id||'element');};
"""


@pytest.mark.parametrize('kind,path_row,side,filler', [('wrong', 1, 'result', 'null'), ('made', 0, 'result', '1'), ('missing', 5, 'silver_only', '1')])
def test_every_entry_shows_the_picked_row_inside_the_list_and_the_line_inside_the_lines(kind, path_row, side, filler):
    # 앞쪽에 다른 종류의 행을 많이 두어 고른 행이 처음에는 목록 바깥에 있게 한다.
    run_js(fixture() + STEPS + _LIST_LAYOUT + f"const filler={filler};" + r"""
for(let i=20;i<32;i++)view.values.unshift({...view.values[2],row:i,path:'msds[0].exposure_limits['+i+'].q',silver:{same:false,value:filler,text:filler},lines:['p2:L3']});
""" + f"""
await go('s02',{{run:'current',doc:'T21-X01',section:8,item:'Fake criterion',pick:{kind!r}}});await flush();
assert.equal(S.source.selection.side,{side!r});assert.equal(S.source.selection.path,'msds[0].exposure_limits[{path_row}].q');
""" + r"""
const list=el('source-problem-list'),button=list.querySelector('[aria-pressed="true"]');assert.ok(button);
const box=button.getBoundingClientRect(),area=list.getBoundingClientRect();
assert.ok(box.top>=area.top&&box.bottom<=area.bottom,JSON.stringify([box,area]));
const line=el('source-page').querySelector('[data-line][aria-pressed="true"]');assert.ok(line);
const lb=line.getBoundingClientRect(),la=el('source-lines').getBoundingClientRect();
assert.ok(lb.top>=la.top&&lb.bottom<=la.bottom,JSON.stringify([lb,la]));
assert.deepEqual(scrolled,[]);
""")


def test_picked_row_beyond_the_first_batch_of_the_list_is_still_drawn():
    run_js(fixture() + STEPS + r"""
for(let i=100;i<400;i++)view.values.unshift({...view.values[2],row:i,path:'msds[0].exposure_limits['+i+'].q',silver:{same:false,value:1,text:'1'},lines:['p2:L3']});
await go('s02',{section:8,item:'Fake criterion',path:view.silver_only[0].path,kind:'missing'});
assert.ok(el('source-problem-list').querySelector('[aria-pressed="true"]'));
// 고른 행이 맨 끝 묶음에 있어 앞쪽 행을 여는 단추가 있다. 뒤쪽 행을 여는 단추는 아래 시험이 본다.
assert.ok(el('source-rows-before'));
""")


def test_long_list_draws_only_the_batch_around_the_picked_row_and_can_widen_both_ways():
    # 실제 가장 큰 문서의 11번 부분 260행에서 맨 끝 행을 열면 단추가 321개였다. 기준은 200개 이하다.
    run_js(fixture() + STEPS + r"""
for(let i=100;i<400;i++)view.values.unshift({...view.values[2],row:i,path:'msds[0].exposure_limits['+i+'].q',silver:{same:false,value:1,text:'1'},lines:['p2:L3']});
await go('s02',{section:8,item:'Fake criterion',path:'msds[0].exposure_limits[250].q',kind:'wrong'});
const drawn=()=>el('source-problem-list').querySelectorAll('.source-problem').length;
assert.ok(el('source-problem-list').querySelector('[aria-pressed="true"]'));
assert.equal(drawn(),60);assert.ok(el('screen-s02').querySelectorAll('button').length<=200);
const before=el('source-rows-before').textContent,more=el('source-rows-more').textContent;
assert.ok(before.includes('120'),before);
el('source-rows-before').click();assert.equal(drawn(),120);
assert.ok(el('source-rows-before').textContent.includes('60'));assert.equal(el('source-rows-more').textContent,more);
el('source-rows-more').click();assert.equal(drawn(),180);
assert.ok(el('source-problem-list').querySelector('[aria-pressed="true"]'));
// 필터를 바꾸면 앞에서부터 다시 그린다
el('source-filter-made').click();assert.equal(el('source-rows-before'),null);
""")


def test_filter_that_hides_the_picked_row_returns_to_all_when_another_entry_picks_it():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
el('source-filter-wrong').click();assert.equal(S.source.filter,'wrong');
await go('s02',{section:8,item:'Fake criterion',pick:'missing'});
assert.equal(S.source.filter,'all');assert.ok(el('source-problem-list').querySelector('[aria-pressed="true"]'));
""")


def test_picking_a_line_without_values_keeps_the_comparison_area_as_it_is():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
S.source.allLines=true;sourceRenderPage();
const rowBefore=sourceCurrentRow().id;
el('source-page').querySelector('[data-line="p2:L4"]').click();
assert.equal(sourceCurrentRow().id,rowBefore);
const panel=el('source-selection');
assert.ok(panel.querySelector('h2').textContent.includes('Fake row 1'));assert.ok(panel.querySelector('table'));
assert.equal(pick(1).getAttribute('aria-pressed'),'false');
""")


def test_picking_a_line_opens_the_row_of_its_first_value():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',path:view.silver_only[0].path,kind:'missing'});
assert.equal(sourceCurrentRow().id,'gold:exposure_limits:5');
el('source-page').querySelector('[data-line="p2:L3"]').click();
assert.equal(sourceCurrentRow().id,row(0));
assert.ok(el('source-problem-list').querySelector('[aria-pressed="true"]'));
""")


def _css_rules():
    import re
    css = (Path(__file__).parents[1] / 'scripts/b_app_static/app.css').read_text()
    return {sel.strip(): body for sels, body in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', css, flags=re.S))
            for sel in sels.split(',')}


def test_css_keeps_the_page_still_and_gives_the_comparison_area_a_fixed_track():
    rules = _css_rules()
    # 페이지 전체가 아니라 칸마다 안쪽으로 스크롤한다.
    assert 'height: 100vh' in rules['body:has(#screen-s02:not([hidden]))']
    assert 'overflow-y: auto' in rules['#source-problem-list']
    assert 'overflow-y: auto' in rules['.source-lines']
    assert 'max-height' not in rules['.source-lines']
    assert 'overflow' in rules['.source-image']
    # 내용과 상관없이 높이가 같도록 줄 높이를 내용이 아니라 비율로 정한다(줄을 눌러도 페이지가 당겨지지 않는다).
    assert 'grid-template-rows: minmax(0, 2fr) minmax(0, 3fr)' in rules['#screen-s02[data-step="compare"] #source-stage']
    assert 'overflow-y: auto' in rules['#source-selection']
    assert 'min-height: 0' in rules['#source-selection']


def test_source_code_never_moves_the_window():
    source = (Path(__file__).parents[1] / 'scripts/b_app_static/js/source.js').read_text()
    assert 'scrollIntoView' not in source
    assert 'sourceRevealSelection' not in source


def test_estimated_line_says_so_and_is_not_a_success():
    run_js(fixture() + STEPS + r"""
const events=[];on('evidence_line_shown',e=>events.push(e));
await go('s02',{section:8,item:'Fake criterion',pick:'missing'});
pick(5,'silver_only').click();
assert.ok(el('source-selection').textContent.includes(T('source.missing.evidence_title')));
const line=el('source-page').querySelector('[data-line="p2:L4"]');
assert.ok(line.classList.contains('source-estimated'));assert.ok(line.textContent.includes(T('source.missing.evidence_title')));
assert.equal(events.length,0);
""")


def test_structure_is_drawn_only_after_the_drawer_is_opened_and_buttons_stay_within_the_limit():
    run_js(fixture() + STEPS + r"""
for(let i=100;i<1100;i++)view.values.push({...view.values[1],row:i,path:'msds[0].exposure_limits['+i+'].q',lines:['p2:L3']});
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
assert.equal(document.querySelector('[data-source-section]'),null);
assert.ok(document.querySelectorAll('button').length<=200,String(document.querySelectorAll('button').length));
const body=openDrawer();
assert.equal(body.querySelector('[data-source-section]'),null);
el('source-structure-open').click();
assert.ok(body.querySelector('[data-source-section="8"]'));
assert.ok(body.querySelectorAll('[data-source-path]').length>1000);
assert.equal(body.querySelector('details'),null);
drawerClose();assert.equal(document.querySelector('[data-source-section]'),null);
assert.ok(document.querySelectorAll('button').length<=200);
""")


def test_picking_a_value_in_the_structure_closes_the_drawer_and_opens_its_row():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const body=openDrawer();el('source-structure-open').click();
Array.from(body.querySelectorAll('[data-source-path]')).find(e=>e.dataset.sourcePath===view.values[2].path&&e.dataset.side==='result').click();
assert.equal(el('details-drawer').open,false);
assert.equal(sourceCurrentRow().id,row(2));assert.equal(pick(2).getAttribute('aria-pressed'),'true');
// 문제 없는 행도 고르면 목록 안에 보인다.
assert.ok(rowButton(row(2)));
""")


def test_line_list_shows_linked_lines_and_lines_near_the_pick_and_can_show_all():
    run_js(fixture() + STEPS + r"""
view.lines=[...view.lines,...Array.from({length:12},(_,i)=>({id:'p2:L'+(i+10),page:2,no:i+10,text:'Plain line '+i,bbox:null}))];
view.silver_only[0].lines=['p2:L15'];
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const lines=()=>Array.from(el('source-page').querySelectorAll('[data-line]'),b=>b.dataset.line);
assert.deepEqual(lines(),['p2:L3','p2:L4','p2:L10']);// 고른 줄 p2:L3과 그 근처
assert.ok(!el('source-lines').textContent.includes(T('source.labels.line_values',{count:0})));
const toggle=el('source-lines-toggle');assert.equal(toggle.textContent,T('steps.source.all_lines'));
toggle.click();assert.equal(lines().length,14);
assert.equal(el('source-lines-toggle').textContent,T('steps.source.near_lines'));
el('source-lines-toggle').click();assert.equal(lines().length,3);
pick(5,'silver_only').click();
assert.deepEqual(lines(),['p2:L3','p2:L13','p2:L14','p2:L15','p2:L16','p2:L17']);
assert.equal(el('source-page').querySelector('[data-line="p2:L15"]').getAttribute('aria-pressed'),'true');
""")


def test_line_list_says_what_to_do_when_nothing_on_the_page_is_linked():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8});S.source.page=1;sourceRenderPage();
assert.equal(el('source-page').querySelectorAll('[data-line]').length,0);
assert.ok(el('source-lines').textContent.includes(T('steps.source.no_linked_lines')));
""")


def test_send_step_passes_the_focus_to_retest_and_compare_can_skip_it():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});atStep('compare');
await el('source-step-send').click();atStep('send');
const body=el('source-top');
assert.ok(body.textContent.includes('T21-X01'));assert.ok(body.textContent.includes('8 fake-unit'));assert.ok(body.textContent.includes('5 fake-unit'));
assert.ok(body.textContent.includes(T('source.evidence.location',{page:2,line_no:3})));
assert.ok(el('source-retest').classList.contains('primary'));assert.equal(el('source-retest').textContent,T('steps.source.send'));
assert.equal(S.shell.route,'s02');
await el('source-retest').click();assert.equal(S.shell.route,'s03');
for(const [k,v] of Object.entries({run:'current',doc:'T21-X01',section:8,item:'Fake criterion',path:view.values[1].path,kind:'wrong'}))assert.equal(S.focus[k],v,k);
// 2단계에서 바로 간다.
await go('s02');sourceGoStep('compare');atStep('compare');
await el('source-retest').click();assert.equal(S.shell.route,'s03');assert.equal(S.focus.path,view.values[1].path);
""")


def test_send_step_says_when_the_estimated_line_is_only_an_estimate():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',path:view.silver_only[0].path,kind:'missing'});
await el('source-step-send').click();
assert.ok(el('source-top').textContent.includes(T('source.missing.location',{page:2,line_no:4})));
""")


def test_no_details_in_any_step_and_drawer_holds_the_records():
    run_js(fixture() + STEPS + r"""
await go('s02');assert.equal(folds(),0);atStep('choose');
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});assert.equal(folds(),0);atStep('compare');
await el('source-step-send').click();assert.equal(folds(),0);atStep('send');
sourceGoStep('compare');
const body=openDrawer();assert.equal(body.querySelector('details'),null);
for(const text of [T('steps.source.raw_value_title'),T('source.structure.doc_comparison'),T('source.estimation.expand'),T('source.selection.eval_reason'),'Fake evaluation lock',view.ui_text.howto])
 assert.ok(body.textContent.includes(text),text);
assert.deepEqual(JSON.parse(body.querySelector('.source-raw pre').textContent),view.values[1].value);
""")


def test_load_failure_has_fact_and_todo_on_screen_and_the_raw_error_in_the_drawer():
    run_js(fixture() + STEPS + r"""
await go('s02');api=async()=>{throw new Error('<b>fake error</b>');};await sourceLoad(true);
const note=el('source-top').querySelector('.error-note');assert.ok(note);assert.equal(note.querySelector('details'),null);
assert.ok(note.textContent.includes(T('source.load_failed.fact')));assert.ok(note.textContent.includes(T('source.load_failed.todo')));
assert.ok(!note.textContent.includes('fake error'));
assert.equal(openDrawer().querySelector('b'),null);
assert.ok(document.querySelector('#details-drawer .drawer-body').textContent.includes('<b>fake error</b>'));
""")


def test_rows_span_documents_and_next_row_moves_to_the_other_document_without_reading_it_again():
    run_js(fixture() + STEPS + r"""
const second=JSON.parse(JSON.stringify(view));second.values=[{...second.values[1],text:'Second document value',lines:['p1:L1']}];second.silver_only=[];
const base=api;api=async path=>{if(path.startsWith('/api/doc?')&&new URLSearchParams(path.split('?')[1]).get('doc')==='T21-X02'){calls.push(path);return {...second,doc_id:'T21-X02',row_groups:rowGroupsOf(second)};}return base(path);};
await go('s02',{run:'current',doc:'T21-X01',section:8,item:'Fake criterion',path:view.silver_only[0].path,kind:'missing'});await flush();
const groups=el('source-problem-list').querySelectorAll('[data-problem-doc]');
assert.deepEqual(Array.from(groups,g=>g.dataset.problemDoc),['T21-X01','T21-X02']);
assert.ok(groups[1].textContent.includes(T('steps.source.doc_rows',{doc:'T21-X02',count:1})));
const before=calls.length;
assert.equal(el('source-next-row').disabled,false);
await el('source-next-row').click();await flush();
assert.equal(S.source.doc,'T21-X02');assert.equal(sourceCurrentRow().id,row(1));
assert.ok(el('source-selection').textContent.includes('Second document value'));
assert.equal(calls.slice(before).filter(p=>p.includes('doc=T21-X02')).length,0);
assert.equal(el('source-problem-list').querySelectorAll('[aria-pressed="true"]').length,1);
assert.equal(el('source-next-row').disabled,true);
await el('source-prev-row').click();await flush();assert.equal(S.source.doc,'T21-X01');
assert.equal(el('source-problem-list').querySelectorAll('[data-problem-doc]').length,2);
""")


def test_actions_keep_the_next_action_last_and_a_value_without_a_line_reads_the_section_first():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const bar=()=>Array.from(el('source-actions').querySelectorAll('button'));
assert.equal(bar().at(-1).id,'source-retest');assert.ok(bar().at(-1).classList.contains('primary'));
assert.equal(bar()[0].id,'source-prev-row');assert.equal(bar()[1].id,'source-next-row');
assert.ok(el('source-actions').textContent.includes(T('steps.source.compare_note')));
pick(4).click();
assert.equal(bar().at(-1).id,'source-read-section');assert.ok(bar().at(-1).classList.contains('primary'));
assert.ok(!el('source-retest').classList.contains('primary'));
""")


def test_warnings_and_answer_mismatch_stay_visible_on_the_compare_step():
    run_js(fixture() + STEPS + r"""
S.shell.keys=[{id:'gold/fake',label:'Reviewed fake answers'},{id:'gold/other',label:'Other answers'}];view.key={id:'gold/other'};
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const panel=el('source-selection').textContent;
assert.ok(panel.includes('Fake warning'));
assert.ok(panel.includes(T('context.answer_mismatch',{result_key:'Other answers',selected_key:'Reviewed fake answers'})));
""")


def test_raw_mode_chooses_document_and_section_then_reads_the_page_without_rows():
    run_js(fixture() + STEPS + r"""
await go('s02');await el('source-raw-open').click();atStep('choose');
assert.equal(S.source.run,null);assert.equal(el('source-values').hidden,true);
await change('source-section-choice','8');atStep('choose');
await el('source-next').click();atStep('compare');
assert.equal(el('source-values').hidden,true);assert.ok(el('source-selection').textContent.includes(T('source.raw.title')));
assert.ok(el('source-page').querySelector('[data-line]'));
""")


def test_step_bar_can_go_back_to_choose_keeping_the_pick_and_says_what_was_chosen():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const back=el('source-step-choose');
assert.ok(back.textContent.includes('Fake criterion'));
back.click();atStep('choose');assert.equal(S.source.selection.path,view.values[1].path);
await el('source-next').click();atStep('compare');assert.equal(S.source.selection.path,view.values[1].path);
""")


def test_next_needs_something_to_look_at():
    run_js(fixture() + STEPS + r"""
S.score.run=runs[1];view.has_gold=false;await go('s02',{doc:'T21-X01',run:'current'});
assert.equal(el('source-next').disabled,true);
assert.ok(el('source-actions').textContent.includes(T('source.labels.choose_scope')));
await change('source-section-choice','8');assert.equal(el('source-next').disabled,false);
""")


def test_run_made_after_the_first_list_is_found_when_a_result_opens_it():
    run_js(fixture() + STEPS + r"""
const fresh={name:'manual/fake',label:{title:'Fresh fake result'},docs:['T21-X01'],no_gold:[]};
const base=api;api=async path=>path.split('?')[0]==='/api/runs'?{runs:[...runs,fresh],current:'current'}:base(path);
await go('s02',{run:'current'});
await go('s02',{run:'manual/fake',doc:'T21-X01',section:8,path:view.values[1].path});
assert.equal(S.source.run,'manual/fake');atStep('compare');assert.equal(S.source.selection.path,view.values[1].path);
await go('s03');await go('s02');assert.equal(S.source.run,'manual/fake');
assert.equal(S.source.list.filter(r=>r.name==='manual/fake').length,1);
""")


def test_opening_a_problem_keeps_the_compare_step_while_the_document_is_read():
    run_js(fixture() + STEPS + r"""
const base=api;let release,held=true;api=path=>held&&path.startsWith('/api/doc?')?new Promise(resolve=>release=()=>resolve(base(path))):base(path);
const opening=go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});await flush();
atStep('compare');assert.ok(el('source-top').textContent.includes(T('source.loading')));assert.equal(el('source-doc-select'),null);
// 첫 문서를 받은 뒤에는 같은 기준의 다른 문서도 읽는다. 그 요청은 잡아 두지 않는다.
held=false;release();await opening;atStep('compare');assert.equal(el('source-top').hidden,true);
""")


def test_line_pick_keeps_focus_on_the_new_line_button():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
el('source-page').querySelector('[data-line="p2:L3"]').click();
assert.equal(document.activeElement.dataset.line,'p2:L3');assert.ok(document.activeElement.isConnected);
""")



# ── G5 전 고침: 메인 세션이 가짜 자료 앱으로 실제 브라우저에서 찾은 문제들 ──

def test_old_picture_finishing_late_does_not_move_the_new_picture():
    # 화면을 다시 그리면 그림이 새로 만들어진다. 버려진 그림의 load가 늦게 돌면 새 그림 칸의 스크롤을 0으로 되돌렸다.
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const old=el('source-image').querySelector('img');
sourceRenderPage();
const fresh=el('source-image').querySelector('img');assert.notEqual(old,fresh);assert.equal(old.isConnected,false);
const box=el('source-image');box.scrollTop=120;
old.naturalWidth=1000;old.naturalHeight=1400;old.clientWidth=0;
old.dispatchEvent({type:'load'});
assert.equal(box.scrollTop,120);
""")


def test_picture_scrolls_to_the_box_when_it_is_on_screen():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const box=el('source-image'),img=box.querySelector('img');box.clientHeight=90;
img.naturalWidth=1000;img.naturalHeight=1400;img.clientWidth=500;
img.dispatchEvent({type:'load'});
assert.equal(box.querySelectorAll('rect').length,1);
assert.equal(box.scrollTop,20*500/1000-90/3);
""")


def test_filters_without_counts_show_only_the_kind_name():
    # 항목을 고르기 전에는 API의 칸 수가 없다. '기록 없음'이라고 쓰면 아래 목록의 행과 어긋난다.
    run_js(fixture() + STEPS + r"""
await go('s02',{doc:'T21-X01',section:8});
for(const kind of ['wrong','made','missing'])assert.equal(el('source-filter-'+kind).textContent,T('source.kinds.'+kind));
assert.ok(!el('source-values').textContent.includes(T('common.legacy.cell_labels.c_none')));
""")


def test_list_title_names_the_document_when_only_one_is_listed():
    run_js(fixture() + STEPS + r"""
await go('s02',{doc:'T21-X01',section:8});
const head=el('source-values').querySelector('.source-rows-head');
assert.ok(head.textContent.includes(T('steps.source.list_title_one',{doc:'T21-X01'})),head.textContent);
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});await flush();
const after=el('source-values').querySelector('.source-rows-head');
assert.ok(after.textContent.includes(T('steps.source.list_title',{count:2})),after.textContent);
""")


def test_choose_step_has_one_list_and_one_strong_button():
    # 시안처럼 ①에는 항목 표 하나만 둔다. 왼쪽 행 목록이 함께 있으면 어느 쪽부터 고를지 헷갈린다(처음 보는 사람 시험).
    run_js(fixture() + STEPS + r"""
await go('s02');atStep('choose');
assert.equal(el('source-values').hidden,true);assert.equal(el('source-problem-list'),null);
assert.equal(el('source-next').classList.contains('primary'),false);
assert.equal(el('screen-s02').querySelectorAll('button.primary').length,1);
assert.ok(el('source-top').querySelector('button.primary').classList.contains('source-open-criterion'));
// 항목 이름을 눌러도 그 항목의 ②로 간다
await el('source-top').querySelectorAll('.source-criterion-name')[1].click();await flush();
atStep('compare');assert.equal(S.source.item,'Other criterion');assert.ok(el('source-problem-list'));
""")


def test_choose_step_without_a_table_keeps_next_as_the_strong_button():
    run_js(fixture() + STEPS + r"""
S.score.run={...runs[1]};
await go('s02');atStep('choose');
await change('source-section-choice','8');
assert.ok(el('source-next').classList.contains('primary'));
""")


def test_row_table_shows_problem_cells_first():
    run_js(fixture() + STEPS + r"""
view.values.unshift({...view.values[2],row:1,path:'msds[0].exposure_limits[1].comp_ref',field:'comp_ref',items:['Fake criterion'],silver:{same:true,value:'1',text:'1'},lines:['p2:L3']});
await go('s02',{section:8,item:'Fake criterion',path:'msds[0].exposure_limits[1].q',kind:'wrong'});
const kinds=el('source-selection').querySelectorAll('tr.source-cell-row').map(r=>r.querySelector('.source-cell-state').textContent);
assert.equal(kinds[0],T('source.kinds.wrong'));assert.equal(kinds.at(-1),T('source.kinds.same'));
""")


def test_evidence_of_an_ai_value_says_it_is_the_line_the_ai_gave():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
assert.ok(el('source-selection').textContent.includes(T('steps.source.evidence_title')));
assert.ok(!el('source-selection').textContent.includes('원문에 적힌 줄'));
""")


def test_section_choice_placeholder_is_short():
    run_js(fixture() + STEPS + r"""
await go('s02');
const first=el('source-section-choice').querySelector('option');
assert.equal(first.textContent,T('steps.source.choose_section'));
assert.ok(T('steps.source.choose_section').length<=8);
""")


def test_picked_cell_is_shown_inside_the_comparison_area():
    # 낮은 창에서는 표가 비교 영역보다 길다. 고른 칸이 영역 밖이면 영역 안에서만 움직인다. 창은 움직이지 않는다.
    run_js(fixture() + STEPS + _LIST_LAYOUT + r"""
const baseRect2=Node.prototype.getBoundingClientRect;
Node.prototype.getBoundingClientRect=function(){
 if(this.tagName==='tr'&&this.classList.contains('source-cell-row'))return {top:500-(el('source-selection').scrollTop||0),bottom:540-(el('source-selection').scrollTop||0),left:0,right:10};
 if(this.id==='source-selection')return {top:100,bottom:324,left:0,right:10};
 return baseRect2.call(this);
};
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
const panel=el('source-selection');
assert.ok(panel.scrollTop>0,String(panel.scrollTop));
const cell=panel.querySelector('.source-value[aria-pressed="true"]').closest('tr').getBoundingClientRect();
assert.ok(cell.top>=100&&cell.bottom<=324,JSON.stringify(cell));
assert.deepEqual(scrolled,[]);
""")


def test_comparison_area_starts_from_the_top_when_another_row_opens():
    run_js(fixture() + STEPS + _LIST_LAYOUT + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
const panel=el('source-selection');panel.scrollTop=80;
const other=sourceVisibleRows().find(r=>!sourceIsCurrentRow(r));
await sourceOpenRow(other);await flush();
assert.equal(panel.scrollTop,0);
""")


def test_every_cell_of_the_row_table_has_its_own_name_not_the_table_name():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
const v=(table,field)=>({table,field});
assert.equal(sourceFieldName(v('ecotox','endpoint')),T('source.field_names.endpoint'));
assert.equal(sourceFieldName(v('toxicity','statements[1]')),T('source.field_names.statements'));
assert.equal(sourceFieldName(v('companies','contacts[1].type')),T('source.field_names.contacts.type'));
assert.equal(sourceFieldName(v('product','name')),T('source.value_titles.product.name'));
assert.equal(sourceFieldName(v('hazard','nfpa.fire')),UI.source.value_titles.hazard['nfpa.fire']);
assert.equal(sourceFieldName(v('regulations','no_such_field')),UI.source.table_names.regulations);
""")


def test_code_values_show_their_plain_name_next_to_the_code():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
const text=(field,value)=>sourceValueText({field},value);
assert.equal(text('endpoint','ECO_ALGAE'),T('source.labels.code_value',{name:UI.source.row_parts.endpoint.ECO_ALGAE,code:'ECO_ALGAE'}));
assert.equal(text('comp_ref','MIX'),T('source.labels.code_value',{name:T('source.rows.mix'),code:'MIX'}));
assert.equal(text('standard','국내'),UI.source.row_parts.standard['국내']);
assert.equal(text('comp_ref','1'),'1');
assert.equal(text('endpoint','MADE_UP'),'MADE_UP');
assert.equal(text('q',null),T('common.none'));
""")


def test_action_row_reaches_the_bottom_of_the_window_on_the_source_screen():
    # 스크롤하지 않는 화면에서 sticky는 행동 줄을 부모 안에 가둔다. 그러면 창 아래에 32px이 남고 비교 영역 16px을 가린다.
    rules = _css_rules()
    assert 'position: static' in rules['#screen-s02 .step-actions']


def test_picture_panel_keeps_its_choosers_in_the_head_and_the_range_in_the_drawer():
    # 그림 칸의 높이를 그림에 쓴다. 시안도 머리 한 줄이다. 줄 구간은 기록이라 서랍으로 옮긴다.
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const panel=el('source-image').parentElement,head=panel.querySelector('.source-panel-head');
assert.ok(head.querySelector('h3'));assert.ok(head.querySelector('#source-page-select'));assert.ok(head.querySelector('#source-section-select'));
const range=T('source.labels.range',{start:'p2:L3',end:'p2:L4'});
assert.ok(!el('source-page').textContent.includes(range));
assert.ok(openDrawer().textContent.includes(range));
""")


def test_comparison_head_always_says_where_the_evidence_is():
    run_js(fixture() + STEPS + r"""
const head=()=>el('source-selection').querySelector('.source-row-evidence').textContent;
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
assert.ok(head().includes(T('steps.source.evidence_title')));assert.ok(head().includes(T('source.evidence.location',{page:2,line_no:3})));
await go('s02',{section:8,item:'Fake criterion',pick:'missing'});
assert.ok(head().includes(T('source.missing.evidence_title')));assert.ok(head().includes(T('source.missing.location',{page:2,line_no:4})));
view.values[1].lines=[];await sourceLoad(true);
await go('s02',{section:8,item:'Fake criterion',path:view.values[1].path,kind:'wrong'});
assert.ok(head().includes(T('source.unlinked.title')));
""")


def test_drawer_starts_with_plain_summaries_and_ends_with_the_raw_records():
    run_js(fixture() + STEPS + r"""
await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
const titles=openDrawer().querySelectorAll('h3').map(n=>n.textContent);
const at=key=>titles.indexOf(T(key));
assert.ok(at('source.structure.doc_comparison')>=0);
assert.ok(at('source.structure.doc_comparison')<at('steps.source.raw_value_title'),JSON.stringify(titles));
assert.ok(at('source.estimation.expand')<at('steps.source.raw_value_title'),JSON.stringify(titles));
assert.ok(at('steps.source.raw_value_title')<at('steps.source.target_title'),JSON.stringify(titles));
""")


def test_comparison_head_says_when_the_picture_cannot_mark_the_line():
    # version17에서 값의 12%는 줄 좌표가 없다. 그림에 표시가 없는 이유를 표 아래까지 내려가지 않고 읽는다.
    run_js(fixture() + STEPS + r"""
const head=()=>el('source-selection').querySelector('.source-row-evidence').textContent;
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
assert.ok(!head().includes(T('source.page.no_coordinates')));
view.lines[1].bbox=null;await sourceLoad(true);
await go('s02',{section:8,item:'Fake criterion',pick:'wrong'});
assert.ok(head().includes(T('source.page.no_coordinates')),head());
""")


def test_comparison_area_is_not_crushed_when_the_guide_strip_is_open():
    # 안내 띠(약 430px)가 열리면 칸들이 눌려 쓸 수 없었다. 그때만 작업 영역이 안쪽으로 스크롤한다.
    rules = _css_rules()
    assert 'overflow-y: auto' in rules['.work:has(> #journey-strip:not([hidden])):has(> #screen-s02:not([hidden]))']
    assert 'height: calc(100vh - 112px)' in rules['.work:has(> #journey-strip:not([hidden])) > #screen-s02:not([hidden])']
    assert 'overflow: hidden' in rules['.work:has(> #screen-s02:not([hidden]))']


def test_choose_table_follows_the_shown_loss_when_one_document_is_chosen():
    # 문서를 고르면 그 문서의 깎인 점수를 보인다. API 순서(전체 기준)로 두면 '많이 깎은 순서'라는 글과 어긋난다.
    run_js(fixture() + STEPS + r"""
scored.problem_rows['Other criterion'].docs[0].loss=4.5;
await go('s02',{doc:'T21-X01'});atStep('choose');
const rows=el('source-top').querySelector('tbody').querySelectorAll('tr');
assert.ok(rows[0].textContent.includes(scoreItemName('Other criterion')),rows[0].textContent);
assert.ok(rows[0].querySelector('button.primary'));assert.equal(rows[1].querySelector('button.primary'),null);
assert.ok(!rows[1].textContent.includes(T('guide.example.biggest')));
await change('source-doc-select','');
const whole=el('source-top').querySelector('tbody').querySelectorAll('tr');
assert.ok(whole[0].textContent.includes(scoreItemName('Fake criterion')),whole[0].textContent);
assert.ok(whole[0].textContent.includes(T('guide.example.biggest')));
""")
