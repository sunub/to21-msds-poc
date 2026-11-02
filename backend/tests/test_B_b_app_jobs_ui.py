"""승인된 시험/본 실행/작업 기록을 가짜 API와 DOM으로 검증한다."""
import pytest
from test_B_b_app_dom import STATIC, run_js

SETUP = r"""
const el=id=>document.getElementById(id);
const change=(node,value)=>{node.value=value;node.checked=!!value;return node.dispatchEvent({type:'change'});};
const input=(node,value)=>{node.value=value;return node.dispatchEvent({type:'input'});};
const textOf=id=>el(id).textContent;
const noGarbage=node=>assert.doesNotMatch(node.textContent,/null|undefined|⟦/);
S.ctx={version:1,set:'pack',key:'gold/fake'};
S.shell.sets=[{id:'pack',label:'Chosen pack',usable:true}];
S.shell.keys=[{id:'gold/fake',label:'Chosen key',usable:true}];
S.shell.servers={models:[],rngd:{},runpod:{}};
const makeOptions=connected=>({
 models:[{tag:'first',label:'First',option_label:'First option',connected},
 {tag:'second',label:'Second',option_label:'Second option',connected:false}],
 sets:[{id:'pack',label:'Chosen pack',usable:true,docs:[
 {doc_id:'T21-X01',runnable:{try:true,run:false},run_reason:{try:null,run:'RUN LOCK'},reason:'NOT RUN REASON'},
 {doc_id:'RAW-FAKE',runnable:{try:true,run:true},run_reason:{try:null,run:null}},
 {doc_id:'T21-X02',runnable:{try:false,run:true},run_reason:{try:'TRY LOCK',run:null}},
 {doc_id:'T21-X03',runnable:{try:false,run:false},run_reason:{try:'TRY BOTH',run:'RUN BOTH'}}]}],
 default_set:'ignored',pages_dirs:[{id:'pack',value:'../data/pages/fake'}],
 run_names:{first:{'../data/pages/fake':{dev10:'fake-all',probe:'fake-probe'}}},
 try_hint:{dry_run_forced:!connected,note:connected?T('jobs.try_hint.ready',{count:1}):T('jobs.try_hint.off')}
});
let options=makeOptions(true), listed=[], running=[], response=null, requests=[], posted=[], optionsError=false,jobsError=false;
const plan={doc_id:'T21-X01',model_tag:'first',pages_dir:'../data/pages/fake',sections_method:'title',msds_count:1,
 sections:{'8':{section:8,lines:3,preamble_lines:1,first:'p1:L2',last:'p1:L4',pages:[1],images:[],method:'title',rows:true,prompt_hash:'fakehash'}}};
const target={kind:'try',doc:'T21-X01',sections:[8],all:false,model:'first',set:'pack',pages_dir:'../data/pages/fake',
 key:{id:'gold/sent',label:'Sent key',fingerprint:'abc123',given:true},base_run:'base',dry_run:false,custom_prompt:false};
const job=(status='running',overrides={})=>({id:'j1',kind:'try',label:'Untrusted legacy label',command:'do not parse this',started:10,
 status,returncode:status==='done'?0:null,stoppable:status==='running',target:{...target},dry_run:false,warnings:[],...overrides});
const result=ok=>({plan,results:{'8':{section:8,ok,raw_text:'<script>fake answer</script>',parsed:{x:1},errors:ok?[]:['parse error'],
 check_problems:[],dropped_rows:0,attempts:1,usage:{prompt_tokens:8,completion_tokens:4}}},fields:{'8':{exposure_limits:2}},
 score:{before:{weighted:50},after:{weighted:55},changed:[{name:'fake item',before:.5,after:.55}],warnings:[]},base_run:'base',saved:'runs/manual/fake'});
api=async(path,opts={})=>{requests.push(path);
 if(path.startsWith('/api/options')){if(optionsError)throw new Error('options unavailable');return options;}
 if(path==='/api/jobs'){if(jobsError)throw new Error('jobs unavailable');return {jobs:listed,running};}
 if(path.startsWith('/api/runs'))return {runs:[{name:'base',label:'Base',model_tag:'first',docs:['T21-X01'],run_kind:'dev10',set:{id:'pack'}},
 {name:'other',label:'Other',model_tag:'first',docs:['T21-X01'],run_kind:'probe',set:{id:'pack'}}]};
 if(path.includes('/result'))return opts.withStatus?{status:response===null?204:200,data:response}:response;
 if(path.includes('/log'))return {text:'fake log\n'.repeat(100)};
 if(path.startsWith('/api/prompt'))return {text:'fake prompt',no:8,hash:'fakehash'};
 throw new Error(path);
};
post=async(path,body)=>{posted.push({path,body});return {id:'j1',stopped:true};};
const stepNow=()=>el('jobs-step-bar').querySelector('[aria-current="step"]').textContent;
const atStep=key=>assert.ok(stepNow().includes(T('steps.trial.'+key)),stepNow());
const stepTo=id=>jobsGoStep(id);
const openDrawer=()=>{drawerClose();el('jobs-details-open').click();return document.querySelector('#details-drawer .drawer-body');};
const chosenModel=(id='jobs-model')=>el(id).querySelector('input[checked]')?.value||'';
const barText=()=>el('jobs-actions').textContent;
const folds=()=>el('screen-s03').querySelectorAll('details').length;
"""


def test_documents_follow_separate_server_capabilities_and_raw_can_be_tried():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});
const docs=el('jobs-doc').querySelectorAll('option');
assert.equal(docs.find(n=>n.value==='T21-X02').disabled,true);
assert.equal(docs.find(n=>n.value==='RAW-FAKE').disabled,false);
assert.ok(textOf('jobs-try').includes('TRY LOCK'));assert.ok(!textOf('jobs-try').includes('NOT RUN REASON'));
await go('s09');
assert.equal(el('jobs-run-doc-T21-X01').disabled,true);
assert.equal(el('jobs-run-doc-T21-X02').disabled,false);
assert.ok(textOf('jobs-run').includes('RUN LOCK'));assert.ok(!textOf('jobs-run').includes('TRY LOCK'));
assert.ok(!S.jobs.r.docs.has('T21-X01'));
""")


def test_focus_and_common_context_are_in_the_try_request():
    run_js(SETUP + r"""
S.focus={doc:'T21-X01',section:8,run:'base'};await go('s03');
assert.equal(el('jobs-doc').value,'T21-X01');assert.deepEqual([...S.jobs.t.secs],[8]);
stepTo('prompt');await el('jobs-send').click();
assert.equal(posted.length,1);const b=posted[0].body;
assert.equal(b.set,'pack');assert.equal(b.key,'gold/fake');assert.equal(b.doc,'T21-X01');
assert.deepEqual(b.sections,[8]);assert.equal(b.base_run,'base');assert.equal(b.dry_run,false);
assert.ok(!('pages_dir' in b));
""")


def test_offline_recovery_keeps_edits_scope_and_explicit_practice():
    run_js(SETUP + r"""
options=makeOptions(false);await go('s03',{doc:'T21-X01',section:8});stepTo('model');
assert.equal(el('jobs-practice').disabled,false);assert.equal(el('jobs-send'),null);
assert.ok(textOf('jobs-try').includes(T('jobs.trial.practice_meaning')));
assert.ok(el('jobs-prepare'));assert.equal(el('jobs-connection').hidden,false);
stepTo('prompt');assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));assert.equal(el('jobs-send').disabled,true);
change(el('jobs-edit'),true);input(el('jobs-prompt'),'edited text');
const editor=el('jobs-prompt');await jobsPoll();assert.equal(el('jobs-prompt'),editor);
options=makeOptions(true);await jobsPoll();
assert.equal(S.jobs.t.text,'edited text');assert.deepEqual([...S.jobs.t.secs],[8]);
assert.equal(el('jobs-send').disabled,false);
assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));
await go('s09');stepTo('prompt');assert.equal(el('jobs-run-start').disabled,false);
options={...makeOptions(false),models:[]};await jobsPoll();atStep('target');assert.equal(el('jobs-next').disabled,true);
""")


def test_poll_failures_and_same_data_recovery_are_visible_without_losing_input():
    run_js(SETUP + r"""
await go('s03');stepTo('prompt');change(el('jobs-edit'),true);input(el('jobs-prompt'),'keep me');
optionsError=true;await jobsPoll();assert.ok(textOf('jobs-try').includes(T('common.legacy.load_error.message')));
assert.ok(openDrawer().textContent.includes('options unavailable'));drawerClose();
assert.equal(el('jobs-send').disabled,true);
optionsError=false;await jobsPoll();assert.ok(!textOf('jobs-try').includes(T('common.legacy.load_error.message')));
assert.equal(S.jobs.t.text,'keep me');
await go('s05');jobsError=true;await jobsPoll();assert.ok(textOf('jobs-list').includes('jobs unavailable'));
jobsError=false;await jobsPoll();assert.ok(!textOf('jobs-list').includes('jobs unavailable'));
assert.ok([...timers.values()].some(t=>t.at===10000));
""")


@pytest.mark.parametrize('kind,copy_key', [('wrong','pair'),('missing','missing'),('made','made'),(None,'none')])
def test_focus_value_and_estimated_line(kind, copy_key):
    import json
    run_js(SETUP + f"const kind={json.dumps(kind)},copyKey={json.dumps(copy_key)};" + r"""
S.focus={doc:'T21-X01',section:8,path:kind?'fake.path':null,kind,expected:5,actual:8,line:'p2:L23',page:2,
 line_text:'fake source',estimated:kind==='missing'};await go('s03');stepTo('target');
assert.ok(textOf('jobs-focus').includes(T('jobs.focus.'+copyKey,{key_value:'5',ai_value:'8'})));
if(kind){assert.ok(!textOf('jobs-focus').includes('fake.path'));assert.ok(openDrawer().textContent.includes('fake.path'));drawerClose();
 assert.ok(textOf('jobs-focus').includes(T('jobs.focus.'+(kind==='missing'?'line_estimated':'line'),{page:2,line_no:23,line_text:'fake source'})));}
noGarbage(el('jobs-try'));
""")


def test_result_six_stages_descriptions_sent_key_and_safe_text():
    run_js(SETUP + r"""
listed=[job('done')];response=result(true);await go('s03');await jobsWatch('j1');
// 다섯 기록은 서랍에, 시험 전후 점수는 결과 단계 본문에 있다.
const node=el('jobs-result'),records=openDrawer();for(const [head,help] of [['input','input'],['prompt','prompt'],['raw_answer','raw_answer'],['parsed','parsed'],['converted','to21']]){
 assert.ok(records.textContent.includes(T('jobs.detail.'+head)));assert.ok(records.textContent.includes(T('jobs.stages.'+help)));}
assert.equal(records.querySelector('script'),null);noGarbage(records);drawerClose();
assert.ok(node.textContent.includes('Sent key'));assert.ok(!node.textContent.includes('Chosen key'));
assert.ok(node.textContent.includes('50.0'));assert.ok(node.textContent.includes('55.0'));
assert.equal(node.querySelector('script'),null);noGarbage(node);
""")


@pytest.mark.parametrize('status', ['failed','done'])
def test_failure_and_success_warnings_have_actionable_text(status):
    run_js(SETUP + f"const state='{status}';" + r"""
listed=[job(state,{returncode:1,error:state==='failed'?{message:'Known error',fix:'Known action',raw:'raw exception'}:null,
 warnings:[{message:'Settings warning',fix:'Fix settings'}]})];await go('s05');
assert.ok(!el('jobs-list').textContent.includes('Settings warning'));
await el('jobs-log-j1').click();const node=el('jobs-detail');assert.ok(node.textContent.includes('Settings warning'));
if(state==='failed'){
 assert.ok(node.querySelectorAll('strong').some(n=>n.textContent==='Known error'));
 assert.ok(node.textContent.includes(T('errors.job.no_line.fix')));
 assert.equal(el('jobs-list').querySelectorAll('button').filter(n=>n.textContent===T('jobs.result_missing.open_log')).length,1);
 const raw=node.querySelectorAll('details').find(n=>n.textContent.includes(T('jobs.legacy.exit_code',{count:1})));
 assert.ok(raw);assert.equal(raw.open,false);
}noGarbage(node);
""")


def test_failure_without_error_and_legacy_unknown_target():
    run_js(SETUP + r"""
listed=[job('failed',{error:null,target:null,returncode:1}),job('unknown',{id:'j2',target:null})];await go('s05');
assert.ok(textOf('jobs-list').includes(T('errors.job.other.message')));
assert.ok(textOf('jobs-list').includes(T('jobs.record.unknown')));
assert.ok(textOf('jobs-list').includes(T('jobs.status.unknown')));noGarbage(el('jobs-list'));
""")


@pytest.mark.parametrize('mode,ok', [('real',True),('real',False),('practice',True)])
def test_result_view_event_only_once_after_observed_running(mode, ok):
    run_js(SETUP + f"const mode='{mode}',ok={str(ok).lower()};" + r"""
const practice=mode==='practice';const events=[];on('try_result_viewed',e=>events.push(e));
listed=[job('running',{dry_run:practice,target:{...target,dry_run:practice}})];await go('s03');await jobsWatch('j1');
assert.equal(events.length,0);response=practice?{plan}:result(ok);
listed=[job('done',{dry_run:practice,target:{...target,dry_run:practice}})];await jobsPoll();
assert.equal(events.length,1);assert.equal(events[0].job,'j1');assert.equal(events[0].mode,mode);
assert.equal(events[0].section_ok,practice?null:ok);
jobsRenderResult();await jobsPoll();assert.equal(events.length,1);
""")


@pytest.mark.parametrize('status', ['failed','stopped','done'])
def test_no_event_for_failed_stopped_or_already_finished_jobs(status):
    run_js(SETUP + f"const state='{status}';" + r"""
const events=[];on('try_result_viewed',e=>events.push(e));
listed=[job(state==='done'?'done':'running')];response=result(true);await go('s03');await jobsWatch('j1');
listed=[job(state)];await jobsPoll();assert.equal(events.length,0);
""")


def test_result_event_waits_until_s03_visible_and_rejects_mismatched_target():
    run_js(SETUP + r"""
const events=[];on('try_result_viewed',e=>events.push(e));listed=[job()];await go('s03');await jobsWatch('j1');
await go('s05');response=result(true);listed=[job('done')];await jobsPoll();assert.equal(events.length,0);
await go('s03');assert.equal(events.length,1);
listed=[job('running',{id:'j2'})];await jobsPoll();await jobsWatch('j2');
response={...result(true),plan:{...plan,doc_id:'T21-X02'}};listed=[job('done',{id:'j2'})];await jobsPoll();
assert.equal(events.length,1);assert.ok(textOf('jobs-result').includes(T('jobs.target_mismatch.fact')));
""")


@pytest.mark.parametrize('shape', ['practice','whole','empty'])
def test_result_shape_branch_and_204(shape):
    run_js(SETUP + f"const shape='{shape}';" + r"""
listed=[job('done',{dry_run:shape==='practice',target:{...target,dry_run:shape==='practice',all:shape==='whole',sections:shape==='whole'?null:[8]}})];
response=shape==='practice'?{plan}:shape==='whole'?{plan,run:{sections_ok:15,sections_failed:1,reextracted:2,seconds:30},summary:{weighted:70},score:null,saved:'runs/manual/whole'}:null;
await go('s03');await jobsWatch('j1');
const key=shape==='practice'?'jobs.practice_done.title':shape==='whole'?'jobs.whole_done.kind':'jobs.result_missing.fact';
assert.ok(textOf('jobs-result').includes(T(key)));noGarbage(el('jobs-result'));
if(shape==='empty')assert.ok(textOf('jobs-result').includes('204'));
""")


def test_task_conditions_use_target_and_external_process_has_no_stop():
    run_js(SETUP + r"""
listed=[job('done'),job('running',{id:'batch',kind:'run',target:{kind:'run',docs:['RAW-FAKE'],model:'first',set:'pack',repeat:2,run_names:['r1','r2']},progress:[{name:'r1',done:1,total:2}]}),
 job('done',{id:'cmp',kind:'compare',target:{kind:'models',runs:['base','other'],title:'my-table'},output:'runs/fake/compare.md'})];
running=[{mine:false,pid:123,kind:'run',run_name:'external-name'}];await go('s05');
assert.ok(textOf('jobs-list').includes('T21-X01'));assert.ok(textOf('jobs-list').includes('RAW-FAKE'));assert.ok(textOf('jobs-list').includes('my-table'));
assert.ok(textOf('jobs-list').includes(T('jobs.list.external')));
const external=el('jobs-list').querySelector('[data-external]');assert.equal(external.querySelector('button'),null);
noGarbage(el('jobs-list'));
""")


def test_prompt_fetch_scope_and_run_confirmation_use_snapshot():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');await el('jobs-load-prompt').click();assert.equal(el('jobs-prompt').value,'fake prompt');
assert.ok(requests.includes('/api/prompt?model=first&no=8'));
await go('s09');input(el('jobs-run-name'),'custom-name');input(el('jobs-repeat'),'2');stepTo('prompt');
let asked=false;post=async(path,body)=>{posted.push({path,body});if(!body.confirm){const e=new Error('confirm');e.status=409;e.body={needs_confirm:true,summary:'Review exact conditions'};throw e;}return {id:'batch'};};
await el('jobs-run-start').click();assert.equal(posted.length,1);assert.ok(textOf('jobs-run').includes('Review exact conditions'));
S.ctx.set='changed';await el('jobs-run-confirm').click();assert.equal(posted.length,2);
assert.equal(posted[1].body.set,'pack');assert.equal(posted[1].body.repeat,2);assert.equal(posted[1].body.confirm,true);
assert.ok(!posted[1].body.docs.includes('T21-X01'));
""")


def test_compare_selection_order_labels_and_default_key_notice():
    run_js(SETUP + r"""
await go('s10');change(el('jobs-compare-pick-other'),true);change(el('jobs-compare-pick-base'),true);
input(el('jobs-compare-label-other'),'After');input(el('jobs-compare-title'),'table');await el('jobs-compare-start').click();
assert.deepEqual(posted[0].body,{title:'table',runs:['other','base'],labels:['After',null]});
assert.ok(textOf('jobs-compare').includes(T('jobs.compare.key_default')));
""")


def test_log_scroll_and_stop_confirmation():
    run_js(SETUP + r"""
listed=[job()];await go('s05');await jobsOpenLog('j1');const log=el('jobs-log');
log.scrollTop=27;log.clientHeight=10;log.scrollHeight=100;log.dispatchEvent({type:'scroll'});
await jobsPoll();assert.equal(el('jobs-log').scrollTop,27);
await el('jobs-stop-j1').click();assert.equal(posted.length,0);await el('jobs-stop-confirm').click();
assert.equal(posted[0].path,'/api/jobs/j1/stop');
""")


def test_prompt_late_response_keeps_newer_draft_and_scope():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');let resolve;
const previous=api;api=path=>path.startsWith('/api/prompt')?new Promise(r=>resolve=r):previous(path);
const loading=jobsLoadPrompt();input(el('jobs-prompt'),'newer draft');resolve({text:'stale prompt'});await loading;
assert.equal(S.jobs.t.text,'newer draft');
const next=jobsLoadPrompt();S.jobs.t.secs=new Set([9]);resolve({text:'wrong section'});await next;
assert.equal(S.jobs.t.text,'newer draft');
""")


def test_changed_set_does_not_silently_choose_a_different_document_on_poll():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});
options={...options,sets:[...options.sets,{id:'other-pack',usable:true,docs:[{doc_id:'T21-X99',runnable:{try:true,run:true}}]}]};
S.ctx.set='other-pack';await jobsPoll();assert.equal(S.jobs.t.doc,null);
await jobsPoll();assert.equal(S.jobs.t.doc,null);atStep('target');assert.equal(el('jobs-next').disabled,true);
""")


def test_boolean_problem_values_have_copy_and_expansion_survives_storage_errors():
    run_js(SETUP + r"""
S.focus={doc:'T21-X01',section:8,path:'fake.bool',kind:'wrong',expected:true,actual:false};await go('s03');stepTo('target');
noGarbage(el('jobs-focus'));assert.ok(textOf('jobs-focus').includes(T('source.value.true')));
// 접힘은 다시 시험에서 사라졌다. 저장 오류에도 펼침 상태가 남는지는 작업 기록의 접힘으로 본다.
listed=[job()];await go('s05');await jobsPoll();await jobsOpenLog('j1');
const d=el('jobs-target-j1');d.open=true;d.dispatchEvent({type:'toggle'});
assert.equal(JSON.parse(store.get('b_app.cards'))['jobs-target-j1'],false);
localStorage.setItem=()=>{throw new Error('denied');};d.open=false;d.dispatchEvent({type:'toggle'});
jobsRenderDetail();assert.equal(el('jobs-target-j1').open,false);
""")


def test_run_confirmation_uses_shared_dialog_with_keyboard_cancel():
    run_js(SETUP + r"""
await go('s09');stepTo('prompt');post=async()=>{const e=new Error('confirm');e.status=409;e.body={needs_confirm:true,summary:'Review exact conditions'};throw e;};
el('jobs-run-start').focus();await el('jobs-run-start').click();const dialog=el('action-confirm');
assert.equal(dialog.open,true);assert.ok(dialog.contains(el('jobs-run-confirm')));
assert.equal(document.activeElement,el('jobs-confirm-cancel'));
el('jobs-run-confirm').focus();dialog.dispatchEvent({type:'keydown',key:'Tab'});
assert.equal(document.activeElement,el('jobs-confirm-cancel'));
dialog.dispatchEvent({type:'keydown',key:'Escape'});assert.equal(dialog.open,false);
assert.equal(document.activeElement,el('jobs-run-start'));
""")


def test_connection_can_open_tunnel_in_place_and_return_without_losing_target():
    run_js(SETUP + r"""
options=makeOptions(false);S.shell.servers={models:[{tag:'first',where:'RNGD',reachable:false,match:false}],
 rngd:{diagnosis:'tunnel_closed',tunnel:{open:false},models:[]},can:{tunnel_open:true,rngd_up:true},
 rngd_choices:[{tag:'first',label:'First',cards:1}]};
await go('s03',{doc:'T21-X01',section:8});stepTo('model');
const action=el('jobs-connection').querySelector('[data-server-action="tunnel_open"]');assert.ok(action);
post=async(path,body)=>{posted.push({path,body});return {action:body.action,token:'fake-confirm',summary:'Fake tunnel',expires_in:60};};
await action.click();assert.equal(S.shell.route,'s03');assert.equal(el('action-confirm').open,true);
assert.equal(S.focus.doc,'T21-X01');assert.equal(S.focus.section,8);
""")


def test_result_race_does_not_overwrite_selected_job_and_whole_has_no_event():
    run_js(SETUP + r"""
listed=[job('running',{target:{...target,all:true,sections:null}})];await go('s03');await jobsWatch('j1');
const events=[];on('try_result_viewed',e=>events.push(e));
response={plan,run:{sections_ok:16,sections_failed:0},summary:{weighted:60},score:result(true).score};listed=[job('done',{target:{...target,all:true,sections:null}})];
await jobsPoll();assert.equal(events.length,0);assert.ok(!textOf('jobs-result').includes(T('jobs.result.partial_score',{before:'50.0',after:'55.0'})));
let resolve;const previous=api;api=(path,opts)=>path.includes('/j1/result')?new Promise(r=>resolve=r):previous(path,opts);
const late=jobsLoadResult('j1');listed=[...listed,job('done',{id:'j2'})];await jobsPoll();response=result(false);await jobsWatch('j2');
resolve({status:200,data:result(true)});await late;assert.equal(S.jobs.watch,'j2');assert.equal(S.jobs.result.results['8'].ok,false);
""")


def test_slow_send_and_used_confirmation_cannot_submit_twice():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});let resolve;
post=(path,body)=>{posted.push({path,body});return new Promise(r=>resolve=r);};
const first=jobsStartTry();await jobsStartTry();assert.equal(posted.length,1);
resolve({id:'j1'});await first;post=async(path,body)=>{posted.push({path,body});return {id:'batch'};};
await go('s09');const before=posted.length;await jobsStartRun(true);assert.equal(posted.length,before);
""")


def test_score_retest_button_enters_same_document_section_and_base():
    run_js(SETUP + r"""
const node=scoreConditions({name:'base',model_tag:'first',status_text:{top_problem:{name:'fake item',section:8,docs:[{doc_id:'T21-X01'}]}}});
await node.querySelector('#score-retest').click();
assert.equal(S.shell.route,'s03');assert.equal(el('jobs-doc').value,'T21-X01');
assert.deepEqual([...S.jobs.t.secs],[8]);assert.equal(S.jobs.t.base,'base');
""")


def test_explicit_retest_does_not_inherit_another_problem_value():
    run_js(SETUP + r"""
S.focus={doc:'T21-X99',section:9,path:'old.path',kind:'wrong',expected:5,actual:8,line:'p1:L2',source_set:'old'};
await go('s03',{doc:'T21-X01',section:8,base_run:'base'});
assert.ok(textOf('jobs-focus').includes(T('jobs.focus.none')));assert.ok(!textOf('jobs-focus').includes('old.path'));
""")


def test_missing_selected_doc_prompts_selection_without_claiming_all_docs_locked():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X99',section:8});
assert.equal(S.jobs.t.doc,null);assert.ok(!textOf('jobs-try').includes(T('jobs.no_runnable.fact')));
assert.ok(textOf('jobs-try').includes(T('jobs.form.no_doc')));
""")


def test_compare_candidates_show_recorded_conditions_and_scoring_scope():
    run_js(SETUP + r"""
await go('s10');S.jobs.runs[0]={...S.jobs.runs[0],key:{label:'Recorded answer'},set:{id:'recorded-pack',label:'Recorded pack'},prompt_version:'prompt-example',concurrency:3};
jobsRenderCompare();assert.ok(textOf('jobs-compare').includes('Recorded answer'));assert.ok(textOf('jobs-compare').includes('Recorded pack'));
assert.ok(textOf('jobs-compare').includes('prompt-example'));
assert.ok(textOf('jobs-compare').includes(T('score.conditions.score_counts',{total:1,scored:1,missing:0,excluded:0})));
""")


EVAL_OPTIONS = r"""
options.sets[0].docs.unshift({doc_id:'T21-E01',group:'eval',runnable:{try:false,run:false},run_reason:{try:'EVAL LOCK',run:'EVAL LOCK'}},
 {doc_id:'T21-E02',group:'eval',runnable:{try:false,run:false},run_reason:{try:'EVAL LOCK',run:'EVAL LOCK'}});
"""


def test_doc_choice_lists_open_documents_first_and_folds_evaluation_documents():
    run_js(SETUP + EVAL_OPTIONS + r"""
await go('s03');
const values=[...el('jobs-doc').querySelectorAll('option')].map(n=>n.value).filter(Boolean);
assert.deepEqual(values,['T21-X01','RAW-FAKE','T21-X02','T21-X03']);
assert.ok(!textOf('jobs-try').includes('EVAL LOCK'));
assert.ok(textOf('jobs-try').includes(T('jobs.batch.eval_locked',{count:2})));
""")


def test_same_reason_documents_share_one_line():
    run_js(SETUP + r"""
options.sets[0].docs.push({doc_id:'T21-X04',runnable:{try:false,run:true},run_reason:{try:'TRY LOCK',run:null}});
await go('s03');
const lines=el('jobs-try').querySelectorAll('ul li').map(n=>n.textContent).filter(t=>t.includes('TRY LOCK'));
assert.equal(lines.join('|'),'T21-X02, T21-X04 — TRY LOCK');
""")


def test_trial_model_follows_connection_until_the_user_picks_one():
    run_js(SETUP + r"""
options=makeOptions(false);S.focus={model:'first'};await go('s03');stepTo('model');
assert.equal(S.jobs.t.model,'first');
options=makeOptions(false);options.models[1].connected=true;
await jobsLoadOptions();jobsRenderTry();
assert.equal(S.jobs.t.model,'second');assert.equal(chosenModel(),'second');
assert.equal(S.focus.model,'second');
change(el('jobs-model'),'first');assert.equal(S.jobs.t.model,'first');
await jobsLoadOptions();assert.equal(S.jobs.t.model,'first');
""")


def test_main_button_keeps_its_meaning_when_connection_changes_and_practice_does_not_stick():
    # 옛 시험(연결이 없으면 연습 체크가 켜지고 주 단추가 연습으로 바뀜)의 뜻은 요청 밖 문제 12번으로 뒤집혔다.
    run_js(SETUP + r"""
options=makeOptions(false);await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');
assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));assert.equal(el('jobs-send').disabled,true);
options=makeOptions(true);await jobsPoll();
assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));assert.equal(el('jobs-send').disabled,false);
await el('jobs-practice').click();assert.equal(posted[0].body.dry_run,true);
S.jobs.step='prompt';jobsRenderTry();assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));
await el('jobs-send').click();assert.equal(posted[1].body.dry_run,false);
""")


# ── 다시 시험 5단계와 세 갈래 (ADR-039, phase app-steps step 3) ──
PICKED = "{doc:'T21-X01',section:8,base_run:'base',path:'fake.path',kind:'wrong',expected:5,actual:8,line:'p2:L23',source_set:'pack'}"


def test_entry_starts_at_prompt_with_source_value_and_ai_on():
    run_js(SETUP + "await go('s03'," + PICKED + ");" + r"""
atStep('prompt');assert.ok(el('jobs-prompt'));assert.ok(el('jobs-send'));assert.equal(el('jobs-doc'),null);
""")


def test_entry_starts_at_model_with_source_value_and_ai_off():
    run_js(SETUP + "options=makeOptions(false);await go('s03'," + PICKED + ");" + r"""
atStep('model');assert.ok(el('jobs-model'));assert.equal(el('jobs-prompt'),null);
""")


def test_entry_starts_at_target_without_a_chosen_value():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8,base_run:'base'});atStep('target');
assert.ok(el('jobs-doc'));assert.equal(el('jobs-prompt'),null);
""")


def test_entry_does_not_skip_when_source_set_differs_or_document_is_locked():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8,path:'fake.path',kind:'wrong',source_set:'other-pack'});atStep('target');
assert.ok(textOf('jobs-try').includes(T('jobs.set_mismatch.title')));
await go('s03',{doc:'T21-X02',section:8,path:'fake.path',kind:'wrong',source_set:'pack'});atStep('target');
""")


def test_moving_between_steps_and_screens_keeps_every_input():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});
change(el('jobs-doc'),'RAW-FAKE');await el('jobs-next').click();atStep('model');
change(el('jobs-model'),'second');options=makeOptions(true);
const J=S.jobs;J.t.model='first';jobsRenderTry();await el('jobs-next').click();atStep('prompt');
await J.promptPending;input(el('jobs-prompt'),'edited text');
assert.equal(J.t.edit,true);
await el('jobs-back').click();atStep('model');await el('jobs-back').click();atStep('target');
assert.equal(el('jobs-doc').value,'RAW-FAKE');assert.deepEqual([...J.t.secs],[8]);
await go('s05');await go('s03');atStep('target');
assert.equal(J.t.text,'edited text');assert.equal(J.t.doc,'RAW-FAKE');assert.equal(J.t.model,'first');
stepTo('prompt');assert.equal(el('jobs-prompt').value,'edited text');
await go('s10');await go('s03');atStep('prompt');assert.equal(el('jobs-prompt').value,'edited text');
assert.equal(posted.length,0);
""")


def test_moving_between_steps_sends_nothing():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});
for(const id of ['model','prompt','target','prompt'])stepTo(id);
assert.equal(posted.length,0);
""")


def test_model_choice_is_open_on_step_two_and_marks_on_and_off():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('model');
const group=el('jobs-model');assert.equal(group.closest('details'),null);
assert.deepEqual(Array.from(group.querySelectorAll('input[type="radio"]'),n=>n.value),['first','second']);
assert.equal(chosenModel(),'first');
assert.ok(group.textContent.includes(T('steps.trial.state_on')));assert.ok(group.textContent.includes(T('steps.trial.state_off')));
assert.equal(el('jobs-connection').hidden,true);
assert.equal(el('jobs-next').textContent,T('steps.next',{name:T('steps.trial.prompt')}));
""")


def test_ai_off_shows_the_way_to_turn_on_and_coming_back_passes_step_two():
    run_js(SETUP + "options=makeOptions(false);await go('s03'," + PICKED + ");" + r"""
atStep('model');assert.equal(el('jobs-connection').hidden,false);
assert.ok(el('jobs-connection').textContent.includes(T('servers.connection.selected')));
assert.equal(el('jobs-connection').querySelector('details'),null);
await el('jobs-prepare').click();assert.equal(S.shell.route,'s06');
assert.equal(S.focus.model,'first');assert.equal(S.focus.returnScreen,'s03');
options=makeOptions(true);await go('s03');atStep('prompt');assert.equal(S.focus.returnScreen,undefined);
assert.equal(S.jobs.t.doc,'T21-X01');assert.deepEqual([...S.jobs.t.secs],[8]);
""")


def test_coming_back_with_another_ai_on_stays_and_does_not_change_the_choice():
    run_js(SETUP + "options=makeOptions(false);await go('s03'," + PICKED + ");" + r"""
await el('jobs-prepare').click();
options=makeOptions(false);options.models[1].connected=true;await go('s03');
atStep('model');assert.equal(S.jobs.t.model,'first');assert.equal(chosenModel(),'first');
""")


def test_practice_is_a_separate_action_and_the_main_button_keeps_its_meaning():
    run_js(SETUP + r"""
options=makeOptions(false);await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');
assert.equal(el('jobs-dry'),null);
assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));assert.equal(el('jobs-send').disabled,true);
assert.ok(barText().includes(T('jobs.actions.run_unavailable')));
assert.equal(el('jobs-practice').textContent,T('steps.trial.practice'));assert.equal(el('jobs-practice').disabled,false);
assert.ok(!el('jobs-practice').classList.contains('primary'));
options=makeOptions(true);await jobsPoll();
assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));assert.equal(el('jobs-send').disabled,false);
await el('jobs-practice').click();assert.equal(posted[0].body.dry_run,true);
S.jobs.step='prompt';jobsRenderTry();await el('jobs-send').click();assert.equal(posted[1].body.dry_run,false);
""")


def test_practice_is_offered_on_step_two_when_ai_is_off():
    run_js(SETUP + r"""
options=makeOptions(false);await go('s03',{doc:'T21-X01',section:8});stepTo('model');
assert.equal(el('jobs-practice').disabled,false);await el('jobs-practice').click();
assert.equal(posted[0].path,'/api/jobs/try');assert.equal(posted[0].body.dry_run,true);
""")


def test_practice_result_is_marked_practice_and_is_not_a_first_success():
    run_js(SETUP + r"""
options=makeOptions(false);await go('s03',{doc:'T21-X01',section:8});stepTo('model');
listed=[job('running',{dry_run:true,target:{...target,dry_run:true}})];await el('jobs-practice').click();atStep('running');
response={plan};listed=[job('done',{dry_run:true,target:{...target,dry_run:true}})];await jobsPoll();atStep('result');
assert.equal(el('jobs-result').querySelector('[data-job-status]').textContent,T('jobs.practice_done.state'));
assert.equal(el('title-s03').textContent,T('steps.trial.practice_title'));
assert.equal(S.journey.outcomes.t2.real,null);assert.ok(el('jobs-after-practice'));
await el('jobs-after-practice').click();atStep('model');
""")


def test_first_step_has_three_branches_and_batch_opens_the_old_inputs():
    run_js(SETUP + r"""
await go('s03');atStep('target');
for(const [id,key] of [['part','part'],['document','document'],['batch','batch']])
 assert.equal(el('jobs-branch-'+id).textContent,T('steps.trial.scope.'+key));
assert.equal(el('jobs-branch-part').getAttribute('aria-pressed'),'true');assert.equal(el('jobs-run').hidden,true);
await el('jobs-branch-document').click();assert.equal(S.jobs.t.all,true);
assert.equal(el('jobs-branch-document').getAttribute('aria-pressed'),'true');
await el('jobs-branch-batch').click();assert.equal(el('jobs-run').hidden,false);
assert.equal(el('jobs-doc'),null);
assert.equal(el('jobs-run-doc-T21-X01').disabled,true);assert.ok(textOf('jobs-run').includes('RUN LOCK'));
assert.ok(!textOf('jobs-run').includes('TRY LOCK'));assert.equal(el('jobs-run-doc-RAW-FAKE').disabled,false);
await el('jobs-branch-part').click();assert.equal(S.jobs.t.all,false);assert.equal(el('jobs-run').hidden,true);
assert.deepEqual([...S.jobs.t.secs],[1],'other branches keep the draft');
""")


def test_batch_branch_sends_the_same_start_request():
    run_js(SETUP + r"""
await go('s03');await el('jobs-branch-batch').click();input(el('jobs-repeat'),'2');input(el('jobs-run-name'),'my-run');
await el('jobs-next').click();atStep('model');assert.equal(chosenModel('jobs-run-model'),'first');
await el('jobs-next').click();atStep('prompt');assert.equal(el('jobs-prompt'),null);
assert.ok(textOf('jobs-run').includes(T('jobs.multiple.default_prompt')));assert.equal(el('jobs-practice'),null);
listed=[job('running',{id:'batch',kind:'run',target:{kind:'run',docs:['RAW-FAKE','T21-X02'],model:'first',set:'pack',repeat:2,run_names:['my-run','my-run_r2']}})];
post=async(path,body)=>{posted.push({path,body});return {id:'batch'};};
await el('jobs-run-start').click();
assert.equal(posted[0].path,'/api/jobs/run');
assert.deepEqual(posted[0].body,{model:'first',docs:['RAW-FAKE','T21-X02'],set:'pack',run_name:'my-run',repeat:2});
atStep('running');
listed=[job('done',{id:'batch',kind:'run',returncode:0,target:{kind:'run',docs:['RAW-FAKE','T21-X02'],model:'first',set:'pack',repeat:2,run_names:['my-run','my-run_r2']}})];
await jobsPoll();atStep('result');assert.equal(el('title-s03').textContent,T('steps.trial.batch_done_title'));
assert.ok(el('jobs-open-recent'));assert.equal(S.jobs.result,null);
""")


def test_batch_next_step_waits_for_a_valid_selection_with_a_reason():
    run_js(SETUP + r"""
await go('s03');await el('jobs-branch-batch').click();await el('jobs-select-none').click();
assert.equal(el('jobs-next').disabled,true);assert.ok(barText().includes(T('jobs.form.invalid_run')));
await el('jobs-select-all').click();assert.equal(el('jobs-next').disabled,false);
input(el('jobs-repeat'),'11');assert.equal(el('jobs-next').disabled,true);
input(el('jobs-repeat'),'3');assert.equal(el('jobs-next').disabled,false);
""")


def test_old_s09_address_opens_the_batch_branch():
    run_js(SETUP + r"""
assert.equal(SHELL_SCREENS.s09,undefined);assert.equal(el('screen-s09'),null);
assert.equal(shellInitialRoute('#s09'),'s09');
await go('s09');assert.equal(S.shell.route,'s03');assert.equal(location.hash,'#s03');
atStep('target');assert.equal(el('jobs-branch-batch').getAttribute('aria-pressed'),'true');
assert.equal(el('jobs-run').hidden,false);assert.equal(S.focus.trialBranch,undefined);
await go('s01');await go('#s09');assert.equal(S.shell.route,'s03');assert.equal(el('jobs-run').hidden,false);
""")


def test_batch_address_works_at_start_and_menu_has_no_batch_entry():
    run_js(SETUP + r"""
location.hash='#s09';await start();assert.equal(S.shell.route,'s03');assert.equal(el('jobs-run').hidden,false);
assert.equal(document.querySelector('[data-screen="s09"]'),null);
assert.equal(document.querySelector('[data-parent="s03"]'),null);
""")


def test_result_step_says_a_rented_server_is_still_on_with_its_cost():
    run_js(SETUP + r"""
S.shell.servers={models:[{tag:'first',where:'RunPod',reachable:true,match:true}],rngd:{},pods:[{id:'p1',session:true,status:'RUNNING',cost_per_hr:2.5,cost_est:.75}],session:{pod_id:'p1',tag:'first',ready:true}};
listed=[job('done')];response=result(true);await go('s03');await jobsWatch('j1');atStep('result');
assert.ok(textOf('jobs-result').includes(T('steps.trial.server_on')));
assert.ok(textOf('jobs-result').includes(T('context.model.rented_hourly',{cost:'2.50'})));
assert.ok(textOf('jobs-result').includes(T('context.model.rented_so_far',{cost:'0.75'})));
await el('jobs-server-open').click();assert.equal(S.shell.route,'s06');
""")


def test_result_step_says_a_company_model_is_still_on_without_rental_cost():
    run_js(SETUP + r"""
S.shell.servers={models:[{tag:'first',where:'RNGD',reachable:true,match:true}],rngd:{models:[{model:'first'}]},pods:[]};
listed=[job('done')];response=result(true);await go('s03');await jobsWatch('j1');
assert.ok(textOf('jobs-result').includes(T('steps.trial.company_on')));assert.ok(el('jobs-server-open'));
""")


def test_result_step_has_no_server_note_when_nothing_is_on():
    run_js(SETUP + r"""
listed=[job('done')];response=result(true);await go('s03');await jobsWatch('j1');atStep('result');
assert.equal(el('jobs-server-open'),null);assert.ok(!textOf('jobs-result').includes(T('steps.trial.server_on')));
""")


def test_trial_keeps_running_across_screens_and_returns_to_running_then_result():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');listed=[job()];
await el('jobs-send').click();atStep('running');assert.equal(el('jobs-result').hidden,false);assert.equal(el('jobs-try').hidden,true);
assert.ok(el('jobs-try-stop'));
await go('s05');await go('s02').catch(()=>{});assert.ok(!posted.some(p=>p.path.includes('/stop')));
await go('s03');atStep('running');
response=result(true);listed=[job('done')];await go('s05');await jobsPoll();await go('s03');atStep('result');
assert.equal(posted.filter(p=>p.path==='/api/jobs/try').length,1);
""")


def test_old_batch_address_during_a_running_trial_keeps_the_running_step():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');listed=[job()];
await el('jobs-send').click();atStep('running');
await go('s09');assert.equal(S.shell.route,'s03');assert.equal(S.jobs.batch,false);atStep('running');
await go('s03',{trialBranch:'batch'});assert.equal(S.jobs.batch,false);atStep('running');
// 끝난 뒤에는 옛 주소가 다시 여러 문서 갈래를 연다.
response=result(true);listed=[job('done')];await jobsPoll();
await go('s09');assert.equal(S.jobs.batch,true);atStep('target');assert.equal(el('jobs-run').hidden,false);
""")


def test_failed_stopped_and_empty_results_stay_on_the_running_step_with_recovery():
    for state, key in (("failed", "steps.trial.failed_title"), ("stopped", "jobs.stopped.fact")):
        run_js(SETUP + f"const state='{state}',key='{key}';" + r"""
listed=[job('running')];await go('s03');await jobsWatch('j1');atStep('running');
listed=[job(state,{returncode:1,error:state==='failed'?{message:'Known error',fix:'Known action',raw:'raw exception'}:null})];await jobsPoll();
atStep('running');assert.equal(el('title-s03').textContent,T(key));
assert.ok(el('jobs-return-target'));assert.equal(folds(),0);
await el('jobs-return-target').click();atStep('prompt');
""")
    run_js(SETUP + r"""
listed=[job('done')];response=null;await go('s03');await jobsWatch('j1');atStep('running');
assert.ok(textOf('jobs-result').includes('204'));assert.ok(el('jobs-result-retry'));assert.ok(el('jobs-return-target'));
""")


def test_stop_from_running_step_uses_the_confirmation_and_nothing_is_sent_before_it():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');listed=[job()];await el('jobs-send').click();
await el('jobs-try-stop').click();assert.equal(posted.filter(p=>p.path.includes('/stop')).length,0);
await el('jobs-stop-confirm').click();assert.equal(posted.at(-1).path,'/api/jobs/j1/stop');
""")


def test_result_title_uses_whole_document_score_and_changed_criteria():
    run_js(SETUP + r"""
listed=[job('done')];response=result(true);await go('s03');await jobsWatch('j1');
assert.equal(el('title-s03').textContent,T('steps.trial.score_up',{before:'50.0',after:'55.0'}));
assert.ok(textOf('jobs-result').includes('fake item'));assert.equal(el('jobs-result').querySelector('th[scope="row"]').textContent,'fake item');
""")


def test_result_says_a_chosen_value_cannot_be_compared_yet():
    run_js(SETUP + "listed=[job('done')];response=result(true);await go('s03'," + PICKED + ");await jobsWatch('j1');" + r"""
assert.ok(textOf('jobs-result').includes(T('steps.trial.change_unavailable')));
assert.ok(textOf('jobs-result').includes(T('jobs.focus.pair',{key_value:'5',ai_value:'8'})));
""")


def test_parse_failure_points_to_the_drawer_not_an_old_stage_number():
    run_js(SETUP + r"""
listed=[job('done')];response=result(false);await go('s03');await jobsWatch('j1');
assert.equal(el('title-s03').textContent,T('steps.trial.parse_title'));
assert.ok(textOf('jobs-result').includes(T('steps.trial.parse_todo')));
assert.ok(openDrawer().textContent.includes('parse error'));
""")


def test_no_folds_in_any_branch_or_step_and_details_live_in_the_drawer():
    run_js(SETUP + r"""
S.jobs.t.dry=false;options.sets[0].docs.push({doc_id:'T21-E01',group:'eval',locked:true,runnable:{try:false,run:false},run_reason:{try:'EVAL LOCK',run:'EVAL LOCK'}});
await go('s03',{doc:'T21-X01',section:8,path:'fake.path',kind:'wrong',expected:5,actual:8});
for(const step of ['target','model','prompt']){stepTo(step);assert.equal(folds(),0,step);}
const front=openDrawer();assert.equal(front.querySelector('details'),null);
assert.ok(front.textContent.includes('fake.path'));assert.ok(front.textContent.includes(T('jobs.prompt.origin')));
drawerClose();
stepTo('target');await el('jobs-branch-document').click();assert.equal(folds(),0);
await el('jobs-branch-batch').click();assert.equal(folds(),0);
const batch=openDrawer();assert.ok(batch.textContent.includes(T('jobs.batch.keep_awake')));
assert.ok(el('jobs-run-locked').textContent.includes('T21-E01'));assert.equal(el('jobs-run-locked').textContent.split('EVAL LOCK').length-1,1);
assert.ok(!textOf('jobs-run').includes('EVAL LOCK'));assert.ok(textOf('jobs-run').includes(T('jobs.batch.eval_locked',{count:1})));
drawerClose();stepTo('model');assert.equal(folds(),0);stepTo('prompt');assert.equal(folds(),0);
""")


def test_result_step_has_no_folds_and_records_are_flat_in_the_drawer():
    run_js(SETUP + r"""
listed=[job('done')];response=result(true);await go('s03');await jobsWatch('j1');assert.equal(folds(),0);
const body=openDrawer();assert.equal(body.querySelector('details'),null);
for(const [head,help] of [['input','input'],['prompt','prompt'],['raw_answer','raw_answer'],['parsed','parsed'],['converted','to21']]){
 assert.ok(body.textContent.includes(T('jobs.detail.'+head)));assert.ok(body.textContent.includes(T('jobs.stages.'+help)));}
assert.ok(body.textContent.includes('runs/manual/fake'));assert.ok(body.textContent.includes('j1'));
""")


def test_errors_show_fact_and_action_in_step_and_raw_in_drawer():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');
post=async()=>{const e=new Error('raw send problem');e.status=500;throw e;};
await el('jobs-send').click();atStep('prompt');assert.equal(folds(),0);
assert.ok(textOf('jobs-try').includes(T('jobs.send_unknown.fact')));assert.ok(!textOf('jobs-try').includes('raw send problem'));
assert.ok(openDrawer().textContent.includes('raw send problem'));
""")


def test_step_bar_lets_finished_steps_go_back_and_blocks_them_while_running():
    run_js(SETUP + r"""
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');
const bar=()=>el('jobs-step-bar');
assert.equal(bar().querySelectorAll('button').length,2);
await bar().querySelector('button').click();atStep('target');
stepTo('prompt');listed=[job()];await el('jobs-send').click();atStep('running');
assert.equal(bar().querySelectorAll('button').length,0);
response=result(true);listed=[job('done')];await jobsPoll();atStep('result');
assert.ok(bar().querySelectorAll('button').length>=3);
assert.ok(bar().textContent.includes('T21-X01'));assert.ok(bar().textContent.includes('First'));
""")


def test_result_can_go_back_to_edit_and_reopen_without_counting_again():
    run_js(SETUP + r"""
const events=[];on('try_result_viewed',e=>events.push(e));
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');listed=[job()];await el('jobs-send').click();
response=result(true);listed=[job('done')];await jobsPoll();atStep('result');assert.equal(events.length,1);
await el('jobs-edit-again').click();atStep('prompt');
const reopen=el('jobs-step-bar').querySelectorAll('button').find(b=>b.textContent.includes(T('steps.trial.result')));
await reopen.click();atStep('result');assert.equal(events.length,1);assert.equal(posted.length,1);
""")


def test_same_condition_time_is_shown_only_after_a_matching_real_trial():
    run_js(SETUP + r"""
const seen=()=>barText().includes(T('steps.trial.previous_time',{seconds:48}));
await go('s03',{doc:'T21-X01',section:8});stepTo('prompt');assert.ok(!seen());
listed=[job()];await el('jobs-send').click();
response=result(true);response.results['8'].seconds=48;listed=[job('done')];await jobsPoll();atStep('result');
await el('jobs-edit-again').click();assert.ok(seen());
stepTo('target');change(el('jobs-doc'),'RAW-FAKE');stepTo('prompt');assert.ok(!seen(),'other document is another condition');
""")


def test_job_records_first_open_does_not_talk_about_results():
    run_js(SETUP + r"""
let release;const normal=api;api=(path,opts)=>path==='/api/jobs'?new Promise(r=>release=()=>r({jobs:[],running:[]})):normal(path,opts);
const opening=go('s05');await Promise.resolve();
assert.equal(el('status').textContent,T('steps.jobs.loading'));
for(let i=0;i<20&&!release;i++)await Promise.resolve();
assert.ok(el('jobs-list').textContent.includes(T('steps.jobs.loading')));
assert.ok(!el('jobs-list').textContent.includes(T('errors.loading.fact')));
release();await opening;
""")


def test_finished_result_does_not_repeat_the_step_bar_and_server_note_comes_before_the_picked_value():
    # 결과 화면에서 서버가 켜져 있다는 글이 첫 화면 아래로 밀렸다. 11/2 G4 캡처. 결과를 본 뒤가 끄기 가장 좋은 때다.
    run_js(SETUP + "S.shell.servers={models:[{tag:'first',where:'RunPod',reachable:true,match:true}],rngd:{},pods:[{id:'p1',session:true,status:'RUNNING',cost_per_hr:2.5,cost_est:.75}],session:{pod_id:'p1',tag:'first',ready:true}};await go('s03'," + PICKED + ");listed=[job('done')];response=result(true);await jobsPoll();await jobsWatch('j1');" + r"""
atStep('result');
assert.equal(el('jobs-result').querySelector('.job-target'),null);
const text=textOf('jobs-result');
assert.ok(text.indexOf(T('steps.trial.server_on'))<text.indexOf(T('jobs.focus.title')));
assert.ok(text.indexOf(T('steps.trial.server_on'))>=0);
""")


def test_no_picked_value_is_a_plain_line_not_a_highlighted_box():
    run_js(SETUP + r"""
await go('s03',{trialBranch:'try'});atStep('target');
assert.ok(textOf('jobs-focus').includes(T('jobs.focus.none')));
assert.equal(el('jobs-focus').classList.contains('job-focus'),false);
await go('s03',""" + PICKED + r""");stepTo('target');
assert.ok(el('jobs-focus').classList.contains('job-focus'));
""")


def test_model_choices_use_two_columns_so_the_list_fits_on_the_screen():
    css = (STATIC / 'app.css').read_text()
    assert '#jobs-model, #jobs-run-model { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));' in css
