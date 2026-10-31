"""승인된 시험/본 실행/작업 기록을 가짜 API와 DOM으로 검증한다."""
import pytest
from test_B_b_app_dom import run_js

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
api=async path=>{requests.push(path);
 if(path.startsWith('/api/options')){if(optionsError)throw new Error('options unavailable');return options;}
 if(path==='/api/jobs'){if(jobsError)throw new Error('jobs unavailable');return {jobs:listed,running};}
 if(path.startsWith('/api/runs'))return {runs:[{name:'base',label:'Base',model_tag:'first',docs:['T21-X01'],run_kind:'dev10',set:{id:'pack'}},
 {name:'other',label:'Other',model_tag:'first',docs:['T21-X01'],run_kind:'probe',set:{id:'pack'}}]};
 if(path.includes('/result'))return response;
 if(path.includes('/log'))return {text:'fake log\n'.repeat(100)};
 if(path.startsWith('/api/prompt'))return {text:'fake prompt',no:8,hash:'fakehash'};
 throw new Error(path);
};
post=async(path,body)=>{posted.push({path,body});return {id:'j1',stopped:true};};
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
await el('jobs-send').click();
assert.equal(posted.length,1);const b=posted[0].body;
assert.equal(b.set,'pack');assert.equal(b.key,'gold/fake');assert.equal(b.doc,'T21-X01');
assert.deepEqual(b.sections,[8]);assert.equal(b.base_run,'base');assert.equal(b.dry_run,false);
assert.ok(!('pages_dir' in b));
""")


def test_offline_recovery_keeps_edits_scope_and_explicit_practice():
    run_js(SETUP + r"""
options=makeOptions(false);await go('s03',{doc:'T21-X01',section:8});
assert.equal(el('jobs-dry').checked,true);assert.equal(el('jobs-dry').disabled,true);
assert.equal(el('jobs-send').textContent,T('jobs.actions.preview'));
assert.ok(textOf('jobs-try').includes(T('jobs.trial.practice_meaning')));
assert.ok(el('jobs-connection').querySelector('button'));
change(el('jobs-edit'),true);input(el('jobs-prompt'),'edited text');
el('jobs-scope').open=true;el('jobs-scope').dispatchEvent({type:'toggle'});
const editor=el('jobs-prompt');await jobsPoll();assert.equal(el('jobs-prompt'),editor);
options=makeOptions(true);await jobsPoll();
assert.equal(S.jobs.t.text,'edited text');assert.deepEqual([...S.jobs.t.secs],[8]);
assert.equal(el('jobs-scope').open,true);assert.equal(el('jobs-dry').disabled,false);
assert.equal(el('jobs-dry').checked,true);change(el('jobs-dry'),false);
assert.equal(el('jobs-send').textContent,T('jobs.actions.send'));
await go('s09');assert.equal(el('jobs-run-start').disabled,false);
options={...makeOptions(false),models:[]};await jobsPoll();assert.equal(el('jobs-run-start').disabled,true);
""")


def test_poll_failures_and_same_data_recovery_are_visible_without_losing_input():
    run_js(SETUP + r"""
await go('s03');change(el('jobs-edit'),true);input(el('jobs-prompt'),'keep me');
optionsError=true;await jobsPoll();assert.ok(textOf('jobs-try').includes('options unavailable'));
assert.equal(el('jobs-send').disabled,true);
optionsError=false;await jobsPoll();assert.ok(!textOf('jobs-try').includes('options unavailable'));
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
 line_text:'fake source',estimated:kind==='missing'};await go('s03');
assert.ok(textOf('jobs-focus').includes(T('jobs.focus.'+copyKey,{key_value:'5',ai_value:'8'})));
if(kind){assert.ok(textOf('jobs-focus').includes('fake.path'));
 assert.ok(textOf('jobs-focus').includes(T('jobs.focus.'+(kind==='missing'?'line_estimated':'line'),{page:2,line_no:23,line_text:'fake source'})));}
noGarbage(el('jobs-try'));
""")


def test_result_six_stages_descriptions_sent_key_and_safe_text():
    run_js(SETUP + r"""
listed=[job('done')];response=result(true);await go('s03');await jobsWatch('j1');
const node=el('jobs-result');for(const [head,help] of [['input','input'],['prompt','prompt'],['raw_answer','raw_answer'],['parsed','parsed'],['converted','to21'],['score','score']]){
 assert.ok(node.textContent.includes(T('jobs.detail.'+head)));assert.ok(node.textContent.includes(T('jobs.stages.'+help)));}
assert.ok(node.textContent.includes('Sent key'));assert.ok(!node.textContent.includes('Chosen key'));
assert.ok(node.textContent.includes('50.0'));assert.ok(node.textContent.includes('55.0'));
assert.equal(node.querySelector('script'),null);noGarbage(node);
""")


@pytest.mark.parametrize('status', ['failed','done'])
def test_failure_and_success_warnings_have_actionable_text(status):
    run_js(SETUP + f"const state='{status}';" + r"""
listed=[job(state,{returncode:1,error:state==='failed'?{message:'Known error',fix:'Known action',raw:'raw exception'}:null,
 warnings:[{message:'Settings warning',fix:'Fix settings'}]})];await go('s05');
const node=el('jobs-list');assert.ok(node.textContent.includes('Settings warning'));
if(state==='failed'){
 assert.ok(node.querySelectorAll('strong').some(n=>n.textContent==='Known error'));
 assert.ok(node.textContent.includes(T('errors.job.no_line.fix')));
 assert.ok(node.querySelectorAll('button').some(n=>n.textContent===T('jobs.result_missing.open_log')));
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
await go('s03',{doc:'T21-X01',section:8});await el('jobs-load-prompt').click();assert.equal(el('jobs-prompt').value,'fake prompt');
assert.ok(requests.includes('/api/prompt?model=first&no=8'));
await go('s09');input(el('jobs-run-name'),'custom-name');input(el('jobs-repeat'),'2');
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
await go('s03',{doc:'T21-X01',section:8});let resolve;
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
await jobsPoll();assert.equal(S.jobs.t.doc,null);assert.equal(el('jobs-send').disabled,true);
""")


def test_boolean_problem_values_have_copy_and_expansion_survives_storage_errors():
    run_js(SETUP + r"""
S.focus={doc:'T21-X01',section:8,path:'fake.bool',kind:'wrong',expected:true,actual:false};await go('s03');
noGarbage(el('jobs-focus'));assert.ok(textOf('jobs-focus').includes(T('source.value.true')));
const d=el('jobs-scope');d.open=true;d.dispatchEvent({type:'toggle'});
assert.equal(JSON.parse(store.get('b_app.cards'))['jobs-scope'],false);
localStorage.setItem=()=>{throw new Error('denied');};d.open=false;d.dispatchEvent({type:'toggle'});
jobsRenderTry();assert.equal(el('jobs-scope').open,false);
""")


def test_run_confirmation_uses_shared_dialog_with_keyboard_cancel():
    run_js(SETUP + r"""
await go('s09');post=async()=>{const e=new Error('confirm');e.status=409;e.body={needs_confirm:true,summary:'Review exact conditions'};throw e;};
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
await go('s03',{doc:'T21-X01',section:8});
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
let resolve;const previous=api;api=path=>path.includes('/j1/result')?new Promise(r=>resolve=r):previous(path);
const late=jobsLoadResult('j1');listed=[...listed,job('done',{id:'j2'})];await jobsPoll();response=result(false);await jobsWatch('j2');
resolve(result(true));await late;assert.equal(S.jobs.watch,'j2');assert.equal(S.jobs.result.results['8'].ok,false);
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
