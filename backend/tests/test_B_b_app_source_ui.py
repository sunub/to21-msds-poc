"""S02 원문 보기. 직접 만든 자료와 API 대역만 사용한다."""
import json
import runpy
from pathlib import Path

import pytest

from test_B_b_app_dom import run_js


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
    return "const view=" + json.dumps(view) + r""";
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
 if(base==='/api/doc')return {...view,doc_id:p.get('doc')};
 throw new Error('Unexpected '+path);};
const el=id=>document.getElementById(id);
const screen=()=>el('screen-s02').textContent;
const pick=(n,side='result')=>Array.from(document.querySelectorAll("[data-source-path]")).find(e=>e.dataset.sourcePath==='msds[0].exposure_limits['+n+'].q'&&e.dataset.side===side)||null;
const flush=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const change=async(id,value)=>{const e=el(id);e.value=value;await e.dispatchEvent({type:'change'});};
"""


def test_source_first_open_current_run_then_preserves_manual_document_value_and_page():
    run_js(fixture() + r"""
await go('s02');assert.equal(S.source.run,'current');assert.equal(S.source.doc,'T21-X01');
await change('source-doc-select','T21-X02');pick(1).click();
S.score.name='older';S.score.run=runs[0];await go('s03');await go('s02');
assert.equal(S.source.run,'current');assert.equal(S.source.doc,'T21-X02');assert.equal(S.source.page,2);
assert.equal(pick(1).getAttribute('aria-pressed'),'true');
await change('source-run-select','older');assert.equal(S.source.doc,'T21-X04');
assert.equal(S.source.selection,null);
""")


def test_source_key_default_input_and_response_metadata_image_contract():
    run_js(fixture() + r"""
await go('s02',{run:'current',section:8});
const request=new URLSearchParams(calls.find(x=>x.startsWith('/api/doc?')).split('?')[1]);
assert.equal(request.get('key'),'gold/fake');assert.equal(request.has('set'),false);
assert.ok(screen().includes(view.set.label));assert.ok(screen().includes(view.set.note));
assert.ok(screen().includes(T('source.origin.moved')));
assert.equal(el('source-page').querySelector('img').getAttribute('src'),view.image_base+'p002.png'+view.image_query);
assert.ok(el('source-page').querySelector('img').getAttribute('alt').includes('2'));
await change('source-set-select','prev/fake');assert.ok(calls.at(-1).includes('set=prev%2Ffake'));
""")


def test_source_value_tips_and_raw_json_are_safe_on_all_three_sides():
    run_js(fixture() + r"""
view.values[1].value.text='<em>not markup</em>';view.values[1].text='<em>not markup</em>';
await go('s02',{section:8});
for(const [n,side,v] of [[1,'result',view.values[1].value],[1,'silver',view.values[1].silver.value],[5,'silver_only',view.silver_only[0].value]]){
 const b=pick(n,side);assert.equal(b.tagName,'button');
 assert.ok(b.getAttribute('data-tip').includes(T('source.fields.value')+':'));
 b.click();const raw=el('source-selection').querySelector('details.source-raw');
 assert.equal(raw.open,false);assert.equal(raw.querySelector('summary').textContent,T('source.labels.raw_value'));
 assert.deepEqual(JSON.parse(raw.querySelector('pre').textContent),v);
 assert.equal(el('screen-s02').querySelector('em'),null);
}
""")


def test_source_legend_section_summaries_and_visible_comparison_states():
    run_js(fixture() + r"""
await go('s02',{section:8});
// 색으로 구분하는 것은 선택 표시뿐이다. 값의 세 상태는 글자로 구분하므로 색 칸을 그리지 않는다.
const chips=el('source-top').querySelectorAll('.source-chip');assert.equal(chips.length,1);
assert.ok(chips[0].getAttribute('style').includes(view.legend.find(x=>x.key==='picked').color));
view.legend.forEach(x=>assert.ok(screen().includes(x.label)));
assert.ok(screen().includes(view.ui_text.sections['8']));assert.ok(screen().includes(view.ui_text.howto));
for(const key of ['same','different','missing'])assert.ok(screen().includes(T('source.legend.'+key)));
// P1-04: 항 선택은 원문만 이동하고 상세는 사용자가 펼친다.
assert.equal(document.querySelector('[data-source-section="8"]').open,false);
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
assert.ok(screen().includes(T('source.estimation.coverage',{total:6,matched:4})));
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
assert.equal(err.querySelector('details').open,false);assert.equal(err.querySelector('pre').textContent,'<b>fake error</b>');
api=base;await el('source-reload').click();assert.ok(pick(1));assert.ok(!/null|undefined|⟦/.test(screen()));
""")


def test_source_latest_document_and_key_win_races_and_key_reload_keeps_manual_choice():
    run_js(fixture() + r"""
await go('s02',{section:8});pick(1).click();const base=api;let release;
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
view.has_gold=true;await go('s02',{item:'Absent criterion',section:12,pick:'mismatch'});
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
await change('source-doc-select','T21-X02');assert.equal(S.source.item,'Fake criterion');
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
assert.ok(screen().includes('Fake list read failure'));
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


def test_source_opening_a_problem_shows_the_comparison_card_below_the_fixed_bar():
    run_js(fixture() + _LAYOUT + r"""
await go('s02',landing);await flush();
assert.deepEqual(scrolled.filter(x=>x.target==='source-selection'),[{target:'source-selection',block:'start'}]);
// 원문 줄을 찾겠다고 페이지 전체를 움직이지 않는다. 움직이면 비교 카드가 고정 막대에 가린다.
assert.deepEqual(scrolled.filter(x=>String(x.target).startsWith('p')),[]);
""")


def test_source_picking_a_value_moves_the_page_only_when_the_card_is_not_fully_visible():
    run_js(fixture() + _LAYOUT + r"""
await go('s02',landing);await flush();
scrolled.length=0;
panelRect={top:200,bottom:650};pick(1).click();
assert.deepEqual(scrolled,[]);
panelRect={top:-38,bottom:411};pick(1).click();
assert.deepEqual(scrolled,[{target:'source-selection',block:'start'}]);
scrolled.length=0;
panelRect={top:524,bottom:973};pick(1).click();
assert.deepEqual(scrolled,[{target:'source-selection',block:'start'}]);
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
    import re
    css = (Path(__file__).parents[1] / 'scripts/b_app_static/app.css').read_text()
    assert re.search(r'#source-selection\s*\{[^}]*scroll-margin-top:\s*var\(--sticky-offset\)', css)
