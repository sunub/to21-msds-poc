"""Step 9 정적 마감. 가짜 API/DOM만 사용하며 실제 화면 확인을 대신하지 않는다."""
import json
import re
from pathlib import Path

import pytest

from test_B_b_app_dom import STATIC, run_js
from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
from test_B_b_app_score_ui import FIXTURE as SCORE_FIXTURE
from test_B_b_app_servers_ui import FIXTURE as SERVERS_FIXTURE
from test_B_b_app_source_ui import STEPS as SOURCE_STEPS, fixture as source_fixture


SCREENS = tuple(f"s{n:02}" for n in range(1, 11) if n not in (8, 9))  # S09는 S03의 갈래가 됐다 (ADR-039).
BUILD = STATIC / "design/BUILD.md"
SETUP = SCORE_FIXTURE + r"""
const scoreApi=api;
const doc={doc_id:'T21-X01',pages:[1],lines:[{id:'p1:L1',page:1,no:1,text:'Fake evidence',bbox:null}],
 sections:{'8':{start:'p1:L1',end:'p1:L1'}},
 values:[{path:'fake.q',table:'exposure_limits',field:'q',row:0,section:8,value:0,text:'0',
   lines:['p1:L1'],items:['Criterion 0'],silver:{same:false,value:5,text:'5'}}],
 silver_only:[],line_index:{'p1:L1':['fake.q']},has_gold:true,legend:[],warnings:[],
 image_base:'/pages/T21-X01/',image_query:'?set=prev%2Ffake',set:{id:'prev/fake',label:'Fake pages',source:'run'},key};
const pack={id:'prev/fake',label:'Fake pages',usable:true,counts:{dev:2,eval_locked:1},docs:[
 {doc_id:'T21-X01',group:'dev',runnable:{try:true,run:true},run_reason:{}},
 {doc_id:'T21-X02',group:'dev',runnable:{try:true,run:true},run_reason:{}},
 {doc_id:'T21-X99',group:'eval',locked:true,reason:'Fake evaluation lock',
   runnable:{try:false,run:false},run_reason:{try:'Fake evaluation lock',run:'Fake evaluation lock'}}]};
const options={models:[{tag:'fake-model',label:'Fake model',connected:false}],sets:[pack],
 pages_dirs:[{id:pack.id,value:'../data/pages/prev/fake'}],run_names:{},try_hint:{note:'Fake connection state'}};
const servers={models:[],pods:[],rngd:{diagnosis:'no_model',models:[],tunnel:{port:18000,open:false}},
 can:{},why:{},rngd_choices:[],env_problems:[],volumes:null,log_tail:[]};
const diff={a:{name:previous.name},b:{name:run.name},same_conditions:true,conditions:[],
 headline:{headline:'Fake comparison'},docs:{common:['T21-X01'],only_a:[],only_b:[]},
 weighted:{a:81.2,b:82.4,delta:1.2},targets:{a:targets,b:targets},items:[],rows:{},changed_values:{},key};
const job={id:'fake-job',kind:'try',status:'done',returncode:0,dry_run:true,stoppable:false,
 target:{kind:'try',doc:'T21-X01',sections:[8],model:'fake-model',set:pack.id,key,dry_run:true},warnings:[]};
let empty=false, failurePath=null, holdPath=null, release;
const raw='<fake-error>audit failure</fake-error>';
api=async(path,opts)=>{
 const base=path.split('?')[0];
 if(base===failurePath)throw new Error(raw);
 if(base===holdPath)await new Promise(resolve=>{release=resolve;});
 if(base==='/api/sets')return {sets:empty?[]:[pack],default:pack.id};
 if(base==='/api/keys')return {keys:[{...key,usable:true}],default:key.id};
 if(base==='/api/servers')return servers;
 if(base==='/api/options')return empty?{models:[],sets:[],pages_dirs:[]}:options;
 if(base==='/api/prompt')return {text:'Fake instruction',no:8,hash:'fakehash'};
 if(base==='/api/jobs')return {jobs:empty?[]:[job],running:[]};
 if(base.endsWith('/log'))return {text:'Fake log'};
 if(base.endsWith('/result'))return {plan:{doc_id:'T21-X01',model_tag:'fake-model',sections:{'8':{lines:1,pages:[1],images:[]}}}};
 if(base==='/api/journey')return {journey:journeyDefault(),problems:[]};
 if(base==='/api/glossary')return {items:[{term:'Fake term',short:'Fake meaning',example:'Fake example',also:[]}]};
 if(base==='/api/doc')return doc;
 if(base==='/api/diff')return diff;
 if(empty&&base==='/api/runs')return {runs:[],count:0,current:null,key};
 return scoreApi(path);
};
post=async()=>{throw Error('Unexpected mutation');};
S.shell.sets=[pack];S.shell.keys=[{...key,usable:true}];
shellRenderHeader();shellRenderContext();
const args={run:run.name,doc:'T21-X01',section:8,a:previous.name,b:run.name,base_run:run.name};
const visible=node=>!node.hidden&&(!node.parentElement||visible(node.parentElement));
const assertClean=node=>assert.doesNotMatch(node.textContent,/null|undefined|NaN|⟦|\[object Object\]/);
"""


def screen_views():
    section = BUILD.read_text().split("## 화면과 모듈\n", 1)[1].split("## 정보 보존표", 1)[0]
    return {cells[1].strip(" `"): re.findall(r"`([a-z]+-[a-z-]+)`", cells[3])
            for line in section.splitlines() if re.match(r"\| `s\d\d`", line)
            for cells in [line.split("|")]}


def test_registered_views_match_build_and_html():
    expected = screen_views()
    assert set(expected) == set(SCREENS)
    assert sum(map(len, expected.values())) == 28  # S08의 두 구역은 안내 층과 도움말로 옮겼다. S06 다섯 구역은 단계 흐름 하나다 (ADR-039).
    run_js("const expected=" + json.dumps(expected) + r""";
for(const [id,views] of Object.entries(expected)){
 assert.deepEqual([...SHELL_SCREENS[id].views],views);
 for(const view of views){assert.equal(typeof shellViews.get(view)?.render,'function',view);
  assert.ok(document.getElementById('screen-'+id).contains(document.getElementById(view)),view);}
}
""")


@pytest.mark.parametrize("screen", SCREENS)
@pytest.mark.parametrize("is_empty", [False, True])
def test_every_screen_renders_safe_nonblank_content_and_native_controls(screen, is_empty):
    run_js(SETUP + f"empty={json.dumps(is_empty)};const route={json.dumps(screen)};" + r"""
await go(route,empty?{}:args);await flush();
const root=el('screen-'+route);
assert.equal(root.hidden,false);assert.ok(root.textContent.trim());assertClean(root);
if(!empty){
 if(route==='s05'){await jobsOpenLog(job.id);}
 for(const id of SHELL_SCREENS[route].views){const region=el(id);assert.ok(region.hidden||region.textContent.trim(),id);}
}
for(const node of root.querySelectorAll('*')){
 if(node.events.click?.length)assert.ok(['button','a','select','input','summary'].includes(node.tagName),node.tagName);
 if(node.tagName==='summary')assert.equal(node.getAttribute('aria-expanded'),String(node.parentElement.open),node.textContent);
 if(node.tagName==='button'&&node.getAttribute('aria-controls'))assert.ok(['true','false'].includes(node.getAttribute('aria-expanded')));
 if(['button','a','summary'].includes(node.tagName))assert.ok((node.getAttribute('aria-label')||node.textContent).trim());
 if(['input','select','textarea'].includes(node.tagName))assert.ok(node.getAttribute('aria-label')||node.closest('label')||
  (node.id&&root.querySelector('label[for="'+node.id+'"]')),node.id);
 for(const attr of ['aria-controls','aria-describedby','aria-labelledby']){
  for(const id of (node.getAttribute(attr)||'').split(/\s+/).filter(Boolean))assert.ok(el(id),attr+' '+id);
 }
}
""")


ERROR_PATHS = dict(zip(SCREENS, ["/api/runs", "/api/doc", "/api/options", "/api/diff", "/api/jobs",
                               "/api/servers", "/api/glossary", "/api/runs"]))


@pytest.mark.parametrize("screen", SCREENS)
def test_each_screen_api_error_has_fact_action_and_closed_safe_raw(screen):
    run_js(SETUP + f"failurePath={json.dumps(ERROR_PATHS[screen])};const route={json.dumps(screen)};" + r"""
await go(route,args);await flush();
if(['s02','s03','s06'].includes(route)){ // 단계 화면에는 접힘이 없다. 사실과 할 일은 단계에, 원래 오류는 자세히 서랍에 있다 (ADR-039).
 const flat=el('screen-'+route).querySelector('.error-note');assert.ok(flat);assert.ok(flat.querySelector('strong').textContent.trim());
 assert.ok(flat.textContent.includes(T('common.todo',{action:''})));assert.equal(flat.querySelector('details'),null);
 assert.ok(!flat.textContent.includes(raw));assertClean(flat);
 el({s02:'source-details-open',s03:'jobs-details-open',s06:'servers-details-open'}[route]).click();const body=document.querySelector('#details-drawer .drawer-body');
 assert.ok(body.textContent.includes(raw));assert.equal(body.querySelector('details'),null);assert.equal(body.querySelector('fake-error'),null);assertClean(body);
 return;
}
const roots=[el('screen-'+route),el('journey-notices')];
const note=roots.flatMap(root=>root.querySelectorAll('.error-note')).find(n=>visible(n)&&n.textContent.includes(raw));
assert.ok(note,route+' lost the actual API error');
assert.ok(note.querySelector('strong').textContent.trim());
assert.ok(note.textContent.includes(T('common.todo',{action:''})));
const detail=note.querySelector('details');assert.ok(detail);assert.equal(detail.open,false);
assert.equal(detail.getAttribute('open'),null);assert.ok(detail.querySelector('pre').textContent.includes(raw));
assert.equal(note.querySelector('fake-error'),null);assertClean(note);
""")


@pytest.mark.parametrize("screen", SCREENS)
def test_navigation_loading_and_displayed_state_are_announced(screen):
    run_js(SETUP + f"holdPath={json.dumps(ERROR_PATHS[screen])};const route={json.dumps(screen)};" + r"""
const opening=go(route,args);await flush();
const statusNode=el('status');assert.equal(statusNode.getAttribute('role'),'status');
assert.ok(statusNode.textContent.includes(shellLoadingText(route)));
assert.ok([...el('screen-'+route).querySelectorAll('[role="status"]')].some(n=>visible(n)&&n.textContent.trim()));
holdPath=null;release();await opening;await flush();
assert.equal(statusNode.textContent,T('common.screen_shown',{screen:T(SHELL_SCREENS[route].title)}));
assertClean(statusNode);
""")


# 쉬운 이름 옆에 작게 두는 원래 이름(.raw, .technical)과 값(option의 value)만 내부 이름을 쓸 수 있다.
VISIBLE_TEXT = r"""
const plainText=node=>{
 if(typeof node==='string')return node;
 if(node.hidden)return '';
 const cls=node.getAttribute('class')||'';
 if(/(^|\s)(raw|technical)(\s|$)/.test(cls))return '';
 return node.children.map(plainText).join(' ');
};
"""


@pytest.mark.parametrize("screen", SCREENS)
def test_screens_show_no_folder_or_set_names_outside_the_raw_style(screen):
    run_js(SETUP + VISIBLE_TEXT + f"const route={json.dumps(screen)};" + r"""
run.name='20261101_sections_fake_s9_v17_dev3_r1';previous.name='20261031_sections_fake_s8_v17_dev3_r2';
args.run=run.name;args.b=run.name;args.a=previous.name;args.base_run=run.name;
await go(route,args);await flush();
const steps={s02:['choose','compare','send'],s03:['target','model','prompt'],s06:['choose','start']}[route]||[null];
for(const step of steps){
 if(route==='s02'&&step)sourceGoStep(step);
 if(route==='s03'&&step)jobsGoStep(step);
 if(route==='s06'&&step)serversGo?.(step);
 await flush();
 const text=plainText(el('screen-'+route));
 for(const name of [run.name,previous.name,'prev/fake','다른 모델 응답'])assert.ok(!text.includes(name),route+' '+step+' shows '+name);
}
""")


@pytest.mark.parametrize("screen,opener", [("s02", "source-details-open"), ("s03", "jobs-details-open"), ("s06", "servers-details-open")])
def test_drawers_keep_folder_names_in_the_raw_style(screen, opener):
    run_js(SETUP + VISIBLE_TEXT + f"const route={json.dumps(screen)},opener={json.dumps(opener)};" + r"""
run.name='20261101_sections_fake_s9_v17_dev3_r1';previous.name='20261031_sections_fake_s8_v17_dev3_r2';
args.run=run.name;args.b=run.name;args.a=previous.name;args.base_run=run.name;
job.target.base_run=run.name;
await go(route,args);await flush();
if(route==='s03'){await jobsWatch(job.id,true);await flush();}
el(opener).click();await flush();
const body=document.querySelector('#details-drawer .drawer-body');
const text=plainText(body);
for(const name of [run.name,previous.name,'prev/fake'])assert.ok(!text.includes(name),route+' drawer shows '+name+': '+text.slice(0,400));
""")


def test_focus_line_reads_as_page_and_line_not_as_a_code():
    run_js(SETUP + VISIBLE_TEXT + r"""
await go('s03',{doc:'T21-X01',section:8,path:'fake.q',kind:'wrong',line:'p1:L29',expected:5,actual:0,expected_text:'5',actual_text:'0',lines:['p1:L29']});await flush();
jobsGoStep('target');await flush();
const text=plainText(el('screen-s03'));
assert.ok(!text.includes('p1:L29'),text);
assert.ok(text.includes(T('jobs.form.focus_line',{page:'1',line_no:'29'})),text);
""")


def test_set_mismatch_note_uses_the_set_label_not_the_folder_name():
    run_js(SETUP + VISIBLE_TEXT + r"""
S.shell.sets=[pack,{id:'next/other',label:'Other pages',usable:true,docs:[]}];
S.ctx.set=pack.id;
await go('s03',{doc:'T21-X01',section:8,path:'fake.q',kind:'wrong',source_set:'next/other'});await flush();
jobsGoStep('target');await flush();
const text=plainText(el('screen-s03'));
assert.ok(text.includes(T('jobs.form.source_set',{set:'Other pages'})),text);
assert.ok(text.includes(T('jobs.form.next_set',{set:'Fake pages'})),text);
assert.ok(!text.includes('next/other'));assert.ok(!text.includes(pack.id));
""")


@pytest.mark.parametrize("screen", SCREENS)
def test_no_screen_repeats_an_action_word(screen):
    run_js(SETUP + f"const route={json.dumps(screen)};" + r"""
await go(route,args);await flush();
const words=/(펼치기|접기|보기|닫기|열기)\s*\1/;
const walk=node=>{
 if(typeof node==='string')return;
 if(['summary','button'].includes(node.tagName))assert.ok(!words.test(node.textContent),node.textContent);
 node.children.forEach(walk);
};
walk(el('screen-'+route));
""")


def test_native_details_toggle_keeps_expansion_state_current():
    run_js(SETUP + r"""
await go('s07');
for(const detail of el('screen-s07').querySelectorAll('details')){
 const summary=detail.querySelector('summary');
 detail.open=true;detail.dispatchEvent({type:'toggle'});assert.equal(summary.getAttribute('aria-expanded'),'true');
 detail.open=false;detail.dispatchEvent({type:'toggle'});assert.equal(summary.getAttribute('aria-expanded'),'false');
}
""")


def test_retest_uses_browser_nodelist_and_preserves_structured_run_labels():
    run_js(SETUP + r"""
// DOM 대역의 Array가 숨기던 실제 NodeList 제약을 재현한다.
const selectAll=Node.prototype.querySelectorAll;
Node.prototype.querySelectorAll=function(selector){
 const nodes=selectAll.call(this,selector);
 return Object.assign({length:nodes.length,forEach:nodes.forEach.bind(nodes),
  [Symbol.iterator]:nodes[Symbol.iterator].bind(nodes),item:i=>nodes[i]??null},nodes);
};
await go('s03',args);await flush();
assert.equal(el('screen-s03').querySelector('.error-note'),null);
assert.ok(el('jobs-base'));assert.equal(el('jobs-base').value,run.name);
assert.ok(el('jobs-base').textContent.includes(run.label.title));assertClean(el('screen-s03'));
await go('s10');assert.ok(el('screen-s10').textContent.includes(run.label.title));assertClean(el('screen-s10'));
""")


def css_rules():
    """CSS 블록을 상위 at-rule과 함께 읽는다. 주석 안의 단어는 제외한다."""
    source = re.sub(r"/\*[\s\S]*?\*/", "", (STATIC / "app.css").read_text())
    def walk(text, parents=()):
        start = 0
        while "{" in text[start:]:
            op = text.index("{", start)
            selector = text[start:op].strip()
            depth, end = 1, op + 1
            while depth:
                depth += (text[end] == "{") - (text[end] == "}")
                end += 1
            body = text[op + 1:end - 1]
            if selector.startswith("@"):
                yield from walk(body, (*parents, selector))
            else:
                yield selector, body, parents
            start = end
    return list(walk(source))


def test_css_preserves_words_focus_and_no_motion():
    rules = css_rules()
    assert any(s == "body" and re.search(r"word-break:\s*keep-all", b) for s, b, _ in rules)
    source = (STATIC / "app.css").read_text()
    assert not re.search(r"word-break:\s*break-all|outline:\s*(?:none|0)(?:;|\s*})", source)
    assert not re.search(r"@keyframes|\banimation(?:-[\w-]+)?\s*:|\btransition(?:-[\w-]+)?\s*:|backdrop-filter|background-clip:\s*text", source)


def test_css_anywhere_wrap_is_limited_to_documented_data_classes():
    table = BUILD.read_text().split("| class |", 1)[1].split("## 화면과 모듈", 1)[0]
    allowed = set(re.findall(r"`(\.[a-z-]+)`", table))
    assert allowed
    for selectors, body, _ in css_rules():
        if re.search(r"overflow-wrap:\s*anywhere", body):
            assert set(s.strip() for s in selectors.split(",")) <= allowed


def test_css_has_no_fixed_desktop_overflow_or_untokenized_color():
    for selector, body, parents in css_rules():
        if not any(p.startswith("@media") for p in parents):
            for value in re.findall(r"(?:^|[;\s])(?:min-)?width\s*:\s*(\d+(?:\.\d+)?)px", body):
                assert float(value) <= 1240, selector
        if selector != ":root":
            # transparent/currentColor는 투명·상속이다. 실제 색의 예외는 두지 않는다.
            assert not re.search(r"#[\da-fA-F]{3,8}\b|\b(?:rgb|hsl|oklch|lab|color)\(", body), selector


def test_source_help_and_controls_precede_the_two_column_content():
    # 옛 두 열 순서의 뜻: 도움말과 고르는 칸이 내용에 겹치지 않고, 지금 단계의 근거와 행동이 보인다 (ADR-039).
    styles = {}
    for selectors, body, parents in css_rules():
        if parents:
            continue
        for selector in selectors.split(","):
            styles.setdefault(selector.strip(), {}).update(
                (name.strip(), value.strip()) for name, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body))
    assert styles["#source-stage"]["display"] == "grid"
    assert styles['#screen-s02[data-step="compare"] #source-stage']["grid-template-rows"] == "minmax(0, 2fr) minmax(0, 3fr)"
    assert styles['#screen-s02[data-step="compare"] #source-values']["grid-row"] == "1 / span 2"
    run_js(r"""
const nodes=Array.from(document.getElementById('screen-s02').querySelectorAll('*')),at=id=>nodes.indexOf(document.getElementById(id));
assert.ok(at('source-step-bar')<at('title-s02'));assert.ok(at('title-s02')<at('help-context-s02'));
assert.ok(at('help-context-s02')<at('source-stage'));assert.ok(at('source-stage')<at('source-actions'));
assert.ok(at('source-values')<at('source-selection'));assert.ok(at('source-selection')<at('source-page'));
""")


def test_preservation_rows_have_resolvable_new_function_or_dom_id():
    section = BUILD.read_text().split("## 정보 보존표", 1)[1].split("## 옛 시험 옮기기", 1)[0]
    rows = [line.split("|") for line in section.splitlines() if re.match(r"\| I\d+", line)]
    assert len(rows) == 94
    sources = "\n".join(p.read_text() for p in sorted((STATIC / "js").glob("*.js")))
    html = (STATIC / "index.html").read_text()
    functions = set(re.findall(r"^(?:async )?function (\w+)\(", sources, re.M))
    # 각 새 자리의 첫 코드 표기가 기계로 확인할 수 있는 대표 위치다.
    for cells in rows:
        place = cells[-2].strip()
        assert place, cells[1]
        ref = re.match(r"`([^`]+)`", place)
        assert ref, (cells[1], place)
        name = ref[1]
        if name.startswith("#"):
            assert f'id="{name[1:]}"' in html or re.search(r'\bid:\s*[\"\']' + re.escape(name[1:]) + r'[\"\']', sources), name
        else:
            assert name in functions, (cells[1], name)


def test_legacy_surface_and_helpers_are_removed_and_text_contract_remains():
    assert not (STATIC / "app.js").exists()
    tests = Path(__file__).parent
    assert not (tests / "test_B_b_app_polish_ui.py").exists()
    for path in tests.glob("*.py"):
        assert not any(token in path.read_text() for token in ("run_" + "old_js", "OLD_" + "APP_JS")), path
    import runpy
    data = runpy.run_path(str(STATIC.parent / "b_app_text.py"))
    assert data["POLISH_TEXT"] is data["UI_TEXT"]
    for name in ("START_TEXT", "FIELD_HELP", "TRY_STAGE_HELP", "JOB_UI_TEXT", "GLOSSARY"):
        assert data[name]


# ── 끝 검사 (step 7, ADR-039): 세 화면의 모든 단계와 서랍 ──
# 단계 표시와 행동 줄은 단계마다 하나다. S06 ③의 확인 줄(.server-progress)은 G3에서 승인한 확인 목록이라 세지 않는다.
STEP_AUDIT = r"""
const auditStep=(route,label)=>{
 const root=document.getElementById('screen-'+route);
 assert.equal(root.querySelectorAll('details').length,0,label+': fold on the step');
 assert.equal(root.querySelectorAll('ol.steps').length,1,label+': step bar count');
 assert.equal(root.querySelectorAll('[aria-current="step"]').length,1,label+': current step count');
 assert.equal(root.querySelectorAll('.step-actions').length,1,label+': action row count');
 assert.doesNotMatch(root.textContent,/null|undefined|⟦/,label);
};
const auditDrawer=async(opener,label)=>{
 drawerClose();document.getElementById(opener).click();
 const body=document.querySelector('#details-drawer .drawer-body');
 assert.equal(body.querySelectorAll('details').length,0,label+': fold in the drawer');
 assert.doesNotMatch(body.textContent,/null|undefined|⟦/,label+' drawer');
 drawerClose();
};
"""


def test_s02_every_step_and_its_drawer_has_no_fold_one_bar_one_action_row_and_clean_text():
    run_js(source_fixture() + SOURCE_STEPS + STEP_AUDIT + r"""
const audit=async label=>{await flush();auditStep('s02',label);await auditDrawer('source-details-open',label);};
await go('s02');atStep('choose');await audit('choose from the menu');
await scoreOpenSource({...top,docs:docRows});atStep('compare');await audit('compare with a problem');
sourceGoStep('send');await flush();atStep('send');await audit('send');
sourceGoStep('choose');await flush();atStep('choose');await audit('choose after coming back');
await go('s02',{doc:'T21-X01',section:8});atStep('compare');await audit('compare one part');
// 문서 전체 표를 연 서랍도 접지 않는다.
drawerClose();el('source-details-open').click();el('source-structure-open').click();
assert.equal(document.querySelector('#details-drawer .drawer-body').querySelectorAll('details').length,0);drawerClose();
// 결과 없이 원문만 볼 때
S.score.list=[];S.score.run=null;S.score.name=null;api=async path=>{if(path.startsWith('/api/runs'))return {runs:[]};return {...view,values:[],silver_only:[],row_groups:[],has_gold:false,doc_id:'T21-X01'};};
await sourceLoad(true);await flush();auditStep('s02','no results');await auditDrawer('source-details-open','no results');
// 읽기 실패
api=async()=>{throw new Error('Fake failure');};await sourceLoad(true);await flush();auditStep('s02','load failure');await auditDrawer('source-details-open','load failure');
""")


def test_s03_every_step_branch_and_drawer_has_no_fold_one_bar_one_action_row_and_clean_text():
    run_js(JOBS_SETUP + STEP_AUDIT + r"""
const flush=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const audit=async label=>{await flush();auditStep('s03',label);await auditDrawer('jobs-details-open',label);};
await go('s03',{doc:'T21-X01',section:8,path:'fake.path',kind:'wrong',expected:5,actual:8});
for(const step of ['target','model','prompt']){stepTo(step);atStep(step);await audit('part '+step);}
stepTo('target');await el('jobs-branch-document').click();
for(const step of ['target','model','prompt']){stepTo(step);atStep(step);await audit('document '+step);}
stepTo('target');await el('jobs-branch-batch').click();
for(const step of ['target','model','prompt']){stepTo(step);atStep(step);await audit('batch '+step);}
stepTo('target');await el('jobs-branch-part').click();
// AI가 꺼진 ②
options=makeOptions(false);await go('s03',{doc:'T21-X01',section:8});stepTo('model');atStep('model');await audit('model off');
options=makeOptions(true);
// ④ 진행 중, 연습 진행 중
listed=[job('running')];await go('s03');await jobsWatch('j1');atStep('running');await audit('running');
listed=[job('running',{id:'j4',dry_run:true,target:{...target,dry_run:true}})];await jobsPoll();await jobsWatch('j4');atStep('running');await audit('practice running');
// ⑤ 성공, 해석 실패, 연습, 실패, 중단, 결과 파일 없음, 여러 문서
const finish=async(label,one,answer)=>{listed=[one];response=answer;await jobsPoll();await jobsWatch(one.id);await flush();await audit(label);};
await finish('result ok',job('done',{id:'r1'}),result(true));atStep('result');
await finish('result parse failure',job('done',{id:'r2'}),result(false));
await finish('result practice',job('done',{id:'r3',dry_run:true,target:{...target,dry_run:true}}),{plan});
await finish('job failed',job('failed',{id:'r4',returncode:1,error:{message:'Fake failure',fix:'Fake fix'}}),null);
await finish('job stopped',job('stopped',{id:'r5',returncode:-15}),null);
await finish('no result file',job('done',{id:'r6'}),null);
await finish('batch',job('done',{id:'r7',kind:'run',target:{kind:'run',docs:['RAW-FAKE'],model:'first',set:'pack',repeat:1,run_names:['r1']}}),null);
""")


@pytest.mark.parametrize('label,step,prepare', [
    ('choose', 'choose', "allOff();await setup();"),
    ('start rented', 'start', "allOff();await setup();await byId('servers-use-rented').click();"),
    ('start company', 'start', "allOff();await setup();await byId('servers-use-company').click();"),
    ('start company, tunnel closed', 'start', "allOff();data.rngd.tunnel={port:18000,open:false};data.rngd.diagnosis='tunnel_closed';await setup();await byId('servers-use-company').click();"),
    ('wait rented', 'wait', "pending();await setup();"),
    ('wait company', 'wait', "allOff();data.rngd.diagnosis='loading';data.rngd.loading_since='2026-10-31T12:00:00+09:00';data.rngd.models=[{model:'Fake model A',pid:7}];S.focus.model='company-a';await setup();"),
    ('stop rented', 'stop', "await setup();"),
    ('stop company', 'stop', "allOff();data.rngd.diagnosis='ok';data.rngd.models=[{model:'Fake model A',pid:7}];Object.assign(data.models[0],{reachable:true,match:true,model_served:'Fake model A'});await setup();"),
    ('status failure', 'choose', "await setup();api=async()=>{throw new Error('Status unavailable');};await shellPollServers();"),
    ('account failure', 'choose', "allOff();data.friendly={message:'Fake',fix:'Fake fix',raw:'FakeRaw'};data.runpod_error='FakeRaw';data.rngd.diagnosis=null;data.rngd.ok=false;data.rngd.friendly={message:'Fake two',fix:'Fix two',raw:'FakeRawTwo'};await setup();"),
    ('action failure', 'stop', "await setup();post=async()=>{throw new Error('Request failed');};await action('pod_delete').click();"),
])
def test_s06_every_step_and_its_drawer_has_no_fold_one_bar_one_action_row_and_clean_text(label, step, prepare):
    run_js(SERVERS_FIXTURE + STEP_AUDIT + prepare + f"const label={json.dumps(label)};atStep({json.dumps(step)});" + r"""
auditStep('s06',label);await auditDrawer('servers-details-open',label);
""")


@pytest.mark.parametrize("screen", SCREENS)
def test_no_screen_has_two_progress_bars(screen):
    run_js(SETUP + f"const route={json.dumps(screen)};" + r"""
await go(route,args);await flush();
const root=el('screen-'+route),bars=root.querySelectorAll('ol.steps').length,now=root.querySelectorAll('[aria-current="step"]').length;
assert.equal(bars,['s02','s03','s06'].includes(route)?1:0);assert.equal(now,bars);
""")


# 시안의 가짜 값. 실제 요금과 시간은 API에서 읽는다. 시험 대역과 서버 설정 POD_COST_HINT는 고정 글이 아니다.
MOCKUP_VALUES = ("$2.49", "2.49", "$0.33", "0.33", "5분 안팎", "3시간 52분")


@pytest.mark.parametrize("value", MOCKUP_VALUES)
def test_mockup_fake_values_are_not_fixed_text(value):
    for path in [*sorted((STATIC / "js").glob("*.js")), STATIC.parent / "b_app_text.py"]:
        assert value not in path.read_text(), (value, path.name)


# 이 phase가 쓰이지 않게 만든 글과 도우미. phase 전부터 쓰이지 않던 것은 STEPS.md 10장에 적고 그대로 둔다.
RETIRED_TEXT = (
    "common.method", "jobs.trial.title", "jobs.prompt.details", "jobs.prompt.edit", "jobs.scope.expand",
    "jobs.off.title", "jobs.completion.title", "jobs.parse_failed.todo", "jobs.practice_done.omitted_stages",
    "jobs.form.waiting", "source.problem_count", "source.evidence.title", "source.selection.expand",
    "source.page.expand", "source.structure.expand", "source.labels.raw_value", "servers.choice.company",
    "servers.choice.rented", "servers.compare.cost", "servers.company.alternative", "servers.connection.processes",
    "servers.rented.ownership", "servers.rented.identity", "servers.models.title", "servers.models.state",
)


def _leaf(tree, key):
    for part in key.split("."):
        if not isinstance(tree, dict) or part not in tree:
            return None
        tree = tree[part]
    return tree


def test_text_this_phase_stopped_using_is_gone_from_the_text_and_copy_and_stays_in_the_approval_table():
    import runpy
    data = runpy.run_path(str(STATIC.parent / "b_app_text.py"))
    copy = (STATIC / "design/COPY.md").read_text()
    steps = (STATIC / "design/STEPS.md").read_text().split("## 12. 문구 승인표", 1)[1].split("\n## ", 1)[0]
    sources = "\n".join(p.read_text() for p in sorted((STATIC / "js").glob("*.js")))
    for key in RETIRED_TEXT:
        assert _leaf(data["UI_TEXT"], key) is None, key
        assert key not in data["COPY_EXCEPTIONS"], key
        assert not re.search(r"^" + re.escape(key) + r"\|", copy, re.M), key
        assert f'"{key}"' not in sources, key
        assert re.search(r"^\| `" + re.escape(key) + r"` \| .* \| \(지움\) \| ", steps, re.M), key


def test_helpers_this_phase_stopped_using_are_gone():
    source = (STATIC / "js/source.js").read_text()
    doc = (STATIC.parent / "b_app_doc.py").read_text()
    assert "sourceShowRow" not in source
    assert "def field_counts" not in doc and "def run_field_counts" not in doc


def _preservation():
    source = (STATIC / "design/STRUCTURE.md").read_text()
    return source.split("## 3. 정보 보존표", 1)[1].split("\n## 4.", 1)[0]


def test_preservation_table_deletions_are_exactly_the_approved_ones():
    table = _preservation().split("### 승인된 삭제", 1)[1]
    rows = re.findall(r"^\| (D\d+) \|", table, re.M)
    approved = re.findall(r"^\| (D\d+) \|", (STATIC / "design/STEPS.md").read_text().split("## 2. 지울 항목 목록", 1)[1].split("\n## 3.", 1)[0], re.M)
    assert rows == approved == ["D1", "D2", "D3", "D4"]


@pytest.mark.parametrize("row,place,gone", [
    ("I36", "①", "대상 막대"), ("I37", "자세히 서랍", "접음"), ("I38", "②", "쪽·항 이동과"), ("I39", "②", "결과 열 머리글"),
    ("I40", "②", "왼쪽 열"), ("I41", "서랍", "오른쪽 열"), ("I42", "②", "값 대조 표"), ("I43", "②", "선택 상태줄"),
    ("I44", "②", "전역 모델 칸"), ("I45", "①", "시험 대상"), ("I46", "③", "‘모델 지시문’"), ("I47", "③", "편집 영역"),
    ("I48", "연습 단추", "입력 확인 연습"), ("I49", "⑤", "S03 결과와"),
])
def test_preservation_rows_of_the_step_screens_point_to_the_new_places(row, place, gone):
    line = next(line for line in _preservation().splitlines() if line.startswith(f"| {row} |"))
    new_place = line.rstrip(" |").rsplit(" | ", 1)[1]
    assert place in new_place, (row, new_place)
    assert gone not in new_place, (row, new_place)


def test_final_check_covers_every_success_criterion_and_problem_with_tests_that_exist():
    steps = (STATIC / "design/STEPS.md").read_text()
    section = steps.split("## 13. 끝 점검", 1)[1].split("\n## ", 1)[0]
    names = set(re.findall(r"`(test_\w+)`", section))
    assert len(names) >= 15
    known = {name for path in Path(__file__).parent.glob("test_*.py")
             for name in re.findall(r"^def (test_\w+)\(", path.read_text(), re.M)}
    assert names <= known, names - known
    problems = re.findall(r"^\| (\d+|10장-[12]) \| ", section.split("### 요청 밖 문제", 1)[1].split("\n### ", 1)[0], re.M)
    assert problems == [str(n) for n in range(1, 15)] + ["10장-1", "10장-2"]
    assert section.count("G7") >= 2
    assert "### step 7" in steps.split("## 13. 끝 점검", 1)[1]
