"""두 갈래 안내의 저장·성공 계약. 가짜 API와 DOM만 사용한다."""
import pytest

from test_B_b_app_dom import run_js


SETUP = r"""
const clone=x=>JSON.parse(JSON.stringify(x));
const el=id=>document.getElementById(id);
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
let saved=journeyDefault(), puts=[], gets=0, failRead=false, failWrite=false;
let runData={name:'fake-run',weighted:71,key:{id:'silver/fake',label:'Fake answers'},set:{id:'fake-set'},
 status_text:{top_problem:{name:'Fake criterion',section:8,loss:2,docs:[{doc_id:'T21-X01'}]}}};
const options={sets:[{id:'fake-set',usable:true,docs:[{doc_id:'T21-X01',runnable:{try:true}}]}],models:[{tag:'fake-model',connected:false}]};
api=async(path,opts={})=>{
 if(path==='/api/journey'){
  if(opts.method==='PUT'){const body=JSON.parse(opts.body);puts.push(clone(body));if(failWrite)throw new Error('write denied');saved=clone(body.journey);return {journey:clone(saved),problems:[]};}
  gets++;if(failRead)throw new Error('read denied');return {journey:clone(saved),problems:[]};
 }
 if(path.startsWith('/api/runs'))return {current:runData?.name,runs:runData?[runData]:[]};
 if(path.startsWith('/api/run/'))return clone(runData);
 if(path==='/api/options')return options;
 if(path==='/api/jobs')return {jobs:[],running:[]};
 if(path==='/api/servers')return {models:[]};
 if(path==='/api/sets')return {sets:options.sets,default:'fake-set'};
 if(path==='/api/keys')return {keys:[{id:'silver/fake',usable:true}],default:'silver/fake'};
 throw new Error(path);
};
post=async()=>{throw new Error('Unexpected POST');};
S.ctx={set:'fake-set',key:'silver/fake'};S.shell.contextLoaded=true;
S.shell.keys=[{id:'silver/fake',usable:true}];S.shell.servers={models:[]};
const target={run:'fake-run',doc:'T21-X01',section:8,item:'Fake criterion'};
const evidence={...target,mismatch:true,line:'p2:L3',path:'fake.value'};
"""


def test_boot_reads_once_no_band_before_reply_and_hash_wins():
    run_js(SETUP + r"""
let release;const normal=api;api=(path,opts)=>path==='/api/journey'&&!opts?.method?
 new Promise(r=>{gets++;release=r;}):normal(path,opts);
location.hash='#s07';await start();await start();
assert.equal(gets,1);assert.equal(el('journey-band').hidden,true);
assert.equal(location.hash,'#s07');release({journey:saved,problems:[]});await flush();
assert.equal(location.hash,'#s07');await go('s01');assert.equal(el('journey-band').hidden,false);
assert.ok(el('journey-band').textContent.includes(T('journey.band.title')));
""")


@pytest.mark.parametrize('change', [
    "saved.progress.dismissed_at='2026-10-31T00:00:00.000Z'",
    "saved.progress.t1.state='skipped'",
    "saved.outcomes.t1.real={first_at:'2026-10-31T00:00:00.000Z',last_at:'2026-10-31T00:00:00.000Z',count:1}",
    "saved.outcomes.t2.practice={first_at:'2026-10-31T00:00:00.000Z',last_at:'2026-10-31T00:00:00.000Z',count:1,last_job:'practice1'}",
])
def test_returning_records_do_not_show_first_visit(change):
    run_js(SETUP + change + r""";await journeyEnsure();journeyRender();assert.equal(el('journey-band').hidden,true);""")


def test_resume_and_pending_are_separate_from_first_visit():
    run_js(SETUP + r"""
saved.progress.active='t2';saved.progress.t2={state:'in_progress',step:1,updated_at:null};
await journeyEnsure();assert.ok(el('journey-band').textContent.includes(T('journey.resume.action')));
saved.pending={attempt:'a1',job:'job1',mode:'real',started_at:new Date().toISOString()};
const normal=api;api=async(p,o)=>p==='/api/jobs'?{jobs:[{id:'job1',kind:'try',status:'done'}]}:normal(p,o);
await journeyLoad();assert.ok(el('journey-band').textContent.includes(T('journey.pending.open_result')));
assert.equal(S.journey.outcomes.t2.real,null);
""")


def test_full_put_and_server_merged_response_replace_memory():
    run_js(SETUP + r"""
await journeyEnsure();const normal=api;
api=async(p,o)=>{const r=await normal(p,o);if(o?.method==='PUT')r.journey.migrated_from=1;return r;};
journeyDismiss();await flush();assert.equal(puts.length,1);
assert.deepEqual(Object.keys(puts[0]),['journey']);assert.deepEqual(Object.keys(puts[0].journey).sort(),Object.keys(journeyDefault()).sort());
assert.equal(S.journey.migrated_from,1);assert.ok(S.journey.progress.dismissed_at);
""")


def test_puts_serialize_and_coalesce_latest_without_reverting_progress():
    run_js(SETUP + r"""
await journeyEnsure();let release,active=0,max=0;const normal=api;
api=async(p,o)=>{if(o?.method==='PUT'){active++;max=Math.max(max,active);if(!release){
 const request=JSON.parse(o.body);puts.push(request);return new Promise(r=>release=()=>{active--;r({journey:request.journey});});}
 const r=await normal(p,o);active--;return r;}return normal(p,o);};
journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
journeyChange(j=>{j.progress.t1.step=1;});journeyChange(j=>{j.progress.t1.step=2;});
assert.equal(puts.length,1);release();await flush();assert.equal(max,1);assert.equal(puts.length,2);
assert.equal(puts[1].journey.progress.t1.step,2);assert.equal(S.journey.progress.t1.step,2);
""")


def test_late_get_and_visibility_refresh():
    run_js(SETUP + r"""
await journeyEnsure();let release;const normal=api;
api=(p,o)=>p==='/api/journey'&&!o?.method?new Promise(r=>release=r):normal(p,o);
const old=journeyLoad();journeyDismiss();await flush();release({journey:journeyDefault()});await old;
assert.ok(S.journey.progress.dismissed_at);
api=normal;document.visibilityState='visible';document.dispatchEvent({type:'visibilitychange'});await flush();assert.equal(gets,2);
""")


def test_storage_failures_are_not_first_visit_and_notify_once_but_work_continues():
    run_js(SETUP + r"""
let notices=0;on('journey_storage_unavailable',()=>notices++);
failRead=true;await journeyEnsure();assert.equal(el('journey-band').textContent.includes(T('journey.band.title')),false);
assert.ok(el('journey-notices').textContent.includes(T('journey.save_failed.title')));
failWrite=true;journeyDismiss();await flush();journeyReplay();await flush();assert.equal(notices,1);
assert.equal(S.journey.progress.t1.step,0);failWrite=false;journeyDismiss();await flush();assert.ok(saved.progress.dismissed_at);
""")


def test_problems_notify_once_and_400_keeps_server_reason():
    run_js(SETUP + r"""
const normal=api;api=async(p,o)=>{const r=await normal(p,o);if(p==='/api/journey'&&!o?.method)r.problems=[{part:'pending',message:'Damaged pending'}];return r;};
await journeyEnsure();await journeyLoad();assert.equal(el('journey-notices').querySelectorAll('[data-notice="problems"]').length,1);
assert.ok(el('journey-notices').textContent.includes('Damaged pending'));
api=async(p,o)=>{if(o?.method==='PUT')throw Object.assign(new Error('Bad body'),{status:400,body:{message:'Invalid field',fix:'Reload guide'}});return normal(p,o);};
journeyDismiss();await flush();assert.ok(el('journey-notices').textContent.includes('Invalid field'));
""")


def test_valid_v1_completion_migrates_once_without_removing_key_or_server_progress():
    run_js(SETUP + r"""
const old={version:1,last_step:3,completed:true,dismissed:true,first_success_at:'2026-10-31T00:00:00.000Z'};
store.set('b_app.journey',JSON.stringify(old));saved.progress.t2.state='in_progress';saved.progress.t2.step=1;
await journeyEnsure();await flush();assert.equal(puts.length,1);assert.equal(S.journey.migrated_from,1);
assert.equal(S.journey.outcomes.t1.real.count,1);assert.equal(S.journey.progress.t2.step,1);
assert.equal(store.get('b_app.journey'),JSON.stringify(old));await journeyLoad();await flush();assert.equal(puts.length,1);
""")


@pytest.mark.parametrize('old', ['{','[]','null','{"version":1,"last_step":3,"completed":true,"dismissed":false,"first_success_at":null}'])
def test_invalid_v1_is_ignored(old):
    import json
    run_js(SETUP + 'store.set("b_app.journey",'+json.dumps(old)+');await journeyEnsure();await flush();assert.equal(puts.length,0);')


def test_evidence_only_for_top_problem_never_navigation_same_value_or_other_item():
    run_js(SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
S.score.run=runData;go=async(id,args)=>{S.shell.route=id;S.focus={...S.focus,...args};};
await scoreOpenSource(runData.status_text.top_problem);assert.equal(S.journey.outcomes.t1.real,null);
for(const e of [{...evidence,mismatch:false},{...evidence,section:9},{...evidence,item:'Other'},{...evidence,run:'Other'}])emit('evidence_line_shown',e);
assert.equal(S.journey.outcomes.t1.real,null);emit('evidence_line_shown',evidence);await flush();
assert.equal(S.journey.outcomes.t1.real.count,1);assert.equal(S.journey.progress.t1.step,3);
emit('evidence_line_shown',evidence);assert.equal(S.journey.outcomes.t1.real.count,1);
for(const forbidden of ['T21-X01','fake-run','Fake criterion','fake.value','p2:L3'])assert.ok(!JSON.stringify(puts).includes(forbidden));
""")


def test_practice_is_separate_real_requires_section_ok_and_repeated_job_not_counted():
    run_js(SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t2';j.progress.t2.state='in_progress';j.progress.t2.step=1;});
emit('try_result_viewed',{job:'p1',mode:'practice',section_ok:null});await flush();
assert.equal(S.journey.outcomes.t2.practice.count,1);assert.equal(S.journey.outcomes.t2.real,null);assert.equal(S.journey.progress.t2.step,1);
emit('try_result_viewed',{job:'p1',mode:'practice',section_ok:null});assert.equal(S.journey.outcomes.t2.practice.count,1);
emit('try_result_viewed',{job:'bad1',mode:'real',section_ok:false});assert.equal(S.journey.outcomes.t2.real,null);
assert.ok(el('journey-strip').textContent.includes(T('journey.trial.parse_failed')));
assert.ok(el('journey-strip').textContent.includes(T('journey.trial.parse_todo')));
journeyChange(j=>{j.pending={attempt:'a1',job:'r1',mode:'real',started_at:new Date().toISOString()};});
emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});await flush();assert.equal(S.journey.outcomes.t2.real.count,1);
assert.equal(S.journey.progress.t2.state,'completed');assert.equal(S.journey.pending,null);
emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});assert.equal(S.journey.outcomes.t2.real.count,1);
""")


def test_replay_only_resets_progress_detaches_job_and_preserves_outcomes_other_storage():
    run_js(SETUP + r"""
await journeyEnsure();store.set('b_app.cards','keep');store.set('b_app.context','keep context');
emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});await flush();const old=clone(S.journey.outcomes);
journeyChange(j=>{j.pending={attempt:'a1',job:'r2',mode:'real',started_at:new Date().toISOString()};});
await journeyReplay();await flush();assert.deepEqual(S.journey.progress,journeyDefault().progress);assert.deepEqual(S.journey.outcomes,old);
assert.equal(S.journey.pending,null);assert.deepEqual(puts.at(-1).journey.outcomes,old);
assert.equal(store.get('b_app.cards'),'keep');assert.equal(store.get('b_app.context'),'keep context');
assert.ok(el('journey-records').textContent.includes(T('journey.history.keep_outcomes')));
""")


def test_run_list_loading_failure_and_no_null_optional_children():
    run_js(SETUP + r"""
await journeyEnsure();let reject;const normal=api;
api=(p,o)=>p.startsWith('/api/runs')?new Promise((_,r)=>reject=r):normal(p,o);
const pending=journeyLoadRuns();assert.ok(el('journey-choice').textContent.includes(T('journey.start.loading')));
reject(new Error('Runs failed'));await pending;
assert.ok(el('journey-choice').querySelector('.error-note'));assert.ok(el('journey-choice').textContent.includes('Runs failed'));
assert.ok(el('journey-choice').textContent.includes(T('common.legacy.load_error.fix')));
for(const id of ['journey-choice','journey-records','journey-strip','journey-band'])assert.doesNotMatch(el(id).textContent,/null|undefined|false|⟦/);
""")


def test_no_runs_cannot_start_read_and_trial_has_compact_connection():
    run_js(SETUP + r"""
runData=null;await journeyEnsure();await journeyLoadRuns();assert.equal(el('journey-start-t1').disabled,true);
assert.ok(el('journey-choice').textContent.includes(T('journey.start.empty')));
assert.ok(el('journey-choice').textContent.includes(T('servers.connection.selected')));
assert.ok(el('journey-start-t2'));assert.ok(el('journey-practice'));
""")


def test_score_step_only_accepts_visible_current_scored_key_and_missing_anchor():
    run_js(SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
S.score.run=runData;S.shell.route='s02';emit('score_summary_shown',{run:'fake-run',key:S.ctx.key,weighted:71});
assert.equal(S.journey.progress.t1.step,0);S.shell.route='s01';
for(const e of [{run:'old',key:S.ctx.key,weighted:71},{run:'fake-run',key:'other',weighted:71},{run:'fake-run',key:S.ctx.key,weighted:null}])emit('score_summary_shown',e);
assert.equal(S.journey.progress.t1.step,0);emit('score_summary_shown',{run:'fake-run',key:S.ctx.key,weighted:71});
assert.equal(S.journey.progress.t1.step,1);assert.equal(S.journey.outcomes.t1.real,null);
go=async id=>{S.shell.route=id;};await journeyGo('s01','not-there');assert.equal(S.journey.progress.t1.step,1);
assert.ok(el('journey-strip').textContent.includes(T('journey.target_missing.title')));
""")


def test_actual_top_problem_source_flow_and_estimated_lines():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault(),problems:[]}:normal(p,o);
await journeyEnsure();S.score.run.status_text={top_problem:{name:'Fake criterion',section:8,docs:[{doc_id:'T21-X01'}]}};
journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
await scoreOpenSource(S.score.run.status_text.top_problem);await flush();
assert.equal(S.journey.outcomes.t1.real,null);pick(1).click();await flush();
assert.equal(S.journey.outcomes.t1.real.count,1);assert.equal(S.journey.progress.t1.state,'completed');
const before=S.journey.outcomes.t1.real.count;sourcePick(view.silver_only[0],'silver_only');assert.equal(S.journey.outcomes.t1.real.count,before);
assert.ok(el('source-page').querySelector('[aria-pressed="true"]'));assert.equal(S.journey.progress.t1.step,3);
""")


def test_trial_guide_real_flow_blank_target_fresh_model_pending_and_result():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
const normal=api;let stored=journeyDefault();
api=async(p,o)=>{if(p==='/api/journey'){if(o?.body)stored=JSON.parse(o.body).journey;return {journey:stored,problems:[]};}return normal(p,o);};
await journeyStart('t2');assert.equal(S.jobs.t.doc,null);assert.equal(S.jobs.t.secs.size,0);
assert.equal(el('journey-next').disabled,true);assert.equal(document.activeElement.id,'jobs-doc');
change(el('jobs-doc'),'T21-X01');S.jobs.t.secs=new Set([8]);jobsRenderTry();
assert.equal(S.journey.progress.t2.step,1);const before=requests.filter(p=>p==='/api/options').length;
await journeyNext();assert.ok(requests.filter(p=>p==='/api/options').length>before);assert.equal(S.journey.progress.t2.step,2);
await journeyNext();assert.equal(S.jobs.t.dry,false);assert.equal(S.journeyUI.phase,3);
listed=[job()];await jobsStartTry();assert.equal(S.journey.pending.job,'j1');assert.equal(S.journey.progress.t2.step,3);
response=result(true);listed=[job('done')];await jobsPoll();assert.equal(S.journey.outcomes.t2.real.count,1);
assert.equal(S.journey.progress.t2.step,4);assert.equal(S.journey.pending,null);
""")


def test_practice_full_flow_does_not_advance_model_stage():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault()}:normal(p,o);
options=makeOptions(false);await journeyStart('t2',true);
change(el('jobs-doc'),'T21-X01');S.jobs.t.secs=new Set([8]);jobsRenderTry();await journeyNext();
assert.equal(S.journey.progress.t2.step,1);assert.equal(el('journey-next').disabled,true);
listed=[job('running',{dry_run:true,target:{...target,dry_run:true}})];await jobsStartTry();
response={plan};listed=[job('done',{dry_run:true,target:{...target,dry_run:true}})];await jobsPoll();
assert.equal(S.journey.outcomes.t2.practice.count,1);assert.equal(S.journey.outcomes.t2.real,null);
assert.equal(S.journey.progress.t2.step,1);assert.equal(S.journeyUI.phase,2);
""")


def test_pending_done_on_refresh_can_open_result_without_resending():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
let stored=journeyDefault();stored.progress.active='t2';stored.progress.t2={state:'in_progress',step:3,updated_at:null};
stored.pending={attempt:'a1',job:'j1',mode:'real',started_at:new Date().toISOString()};
const normal=api;api=async(p,o)=>{if(p==='/api/journey'){if(o?.body)stored=JSON.parse(o.body).journey;return {journey:stored};}return normal(p,o);};
listed=[job('done')];response=result(true);await journeyEnsure();await journeyOpenPending();
assert.equal(posted.length,0);assert.equal(S.journey.outcomes.t2.real.count,1);assert.equal(S.journey.pending,null);
""")


def test_detached_result_records_outcome_without_advancing_new_guide():
    run_js(SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t2';j.progress.t2.state='in_progress';j.progress.t2.step=1;
 j.pending={attempt:'a1',job:'j1',mode:'real',started_at:new Date().toISOString()};});
journeySkip();journeyChange(j=>{j.progress.active='t2';j.progress.t2.state='in_progress';j.progress.t2.step=0;});
emit('try_result_viewed',{job:'j1',mode:'real',section_ok:true});assert.equal(S.journey.outcomes.t2.real.count,1);
assert.equal(S.journey.progress.t2.step,0);assert.equal(S.journey.progress.t2.state,'in_progress');
""")


@pytest.mark.parametrize('variant', ['multiple', 'unknown_dry', 'stopped'])
def test_trial_nonqualifying_results_never_record_success(variant):
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + f"const variant='{variant}';" + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault()}:normal(p,o);
await journeyEnsure();const custom=job();if(variant==='multiple'){custom.target.sections=[8,9];plan.sections['9']={section:9};}
if(variant==='unknown_dry'){delete custom.dry_run;delete custom.target.dry_run;}
listed=[custom];await go('s03');await jobsWatch('j1');response=result(true);response.results['9']={ok:true};
custom.status=variant==='stopped'?'stopped':'done';custom.returncode=0;await jobsPoll();assert.equal(S.journey.outcomes.t2.real,null);
""")


def test_no_problem_or_link_shows_recovery_without_claiming_completion():
    run_js(SETUP + r"""
await journeyEnsure();S.journeyUI.phase=2;S.journeyUI.run=runData;
journeyChange(j=>{j.progress.active='t1';j.progress.t1={state:'in_progress',step:1,updated_at:null};});
assert.ok(el('journey-strip').textContent.includes(T('journey.unlinked.reason')));
assert.equal(el('journey-next').disabled,true);S.journeyUI.run.status_text.top_problem=null;journeyRender();
assert.ok(el('journey-strip').textContent.includes(T('journey.start.no_problem')));assert.equal(S.journey.outcomes.t1.real,null);
""")


def test_revisiting_guide_can_repeat_same_evidence_and_marks_only_real_missing_lines():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault()}:normal(p,o);
await journeyEnsure();S.score.run.status_text={top_problem:{name:'Fake criterion',section:8,docs:[{doc_id:'T21-X01'}]}};
journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
await scoreOpenSource(S.score.run.status_text.top_problem);
assert.equal(el('journey-strip').textContent.includes(T('journey.start.no_line')),false);
assert.equal(S.journey.progress.t1.step,2);pick(1).click();await flush();assert.equal(S.journey.outcomes.t1.real.count,1);
// 다시 하기는 기존 성공을 그대로 두고 같은 실제 기능을 다시 연습할 수 있다.
S.journeyUI.target=null;S.journeyUI.runsLoaded=true;S.journeyUI.run={...runs[1],weighted:70};
journeyChange(j=>{j.progress=journeyDefault().progress;j.progress.active='t1';j.progress.t1.state='in_progress';});
await scoreOpenSource(S.score.run.status_text.top_problem);pick(1).click();await flush();
assert.equal(S.journey.outcomes.t1.real.count,2);assert.equal(S.journey.progress.t1.state,'completed');
""")


def test_unknown_pending_is_cleared_and_failed_lookup_keeps_retryable_job():
    run_js(SETUP + r"""
saved.pending={attempt:'a1',job:null,mode:'real',started_at:new Date().toISOString()};
await journeyEnsure();await flush();assert.equal(S.journey.pending,null);
assert.ok(el('journey-strip').textContent.includes(T('journey.pending.unknown')));
journeyChange(j=>{j.pending={attempt:'a2',job:'job2',mode:'real',started_at:new Date().toISOString()};});await flush();
const normal=api;api=async(p,o)=>{if(p==='/api/jobs')throw new Error('Jobs unreadable');return normal(p,o);};
await journeyCheckPending();journeyRender();assert.equal(S.journey.pending.job,'job2');
assert.ok(el('journey-band').textContent.includes('Jobs unreadable'));
""")


def test_unsaved_success_survives_visibility_get_and_next_change_retries():
    run_js(SETUP + r"""
await journeyEnsure();failWrite=true;emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});await flush();
assert.equal(saved.outcomes.t2.real,null);await journeyLoad();assert.equal(S.journey.outcomes.t2.real.count,1);
failWrite=false;journeyDismiss();await flush();assert.equal(saved.outcomes.t2.real.count,1);
""")


def test_default_record_key_order_does_not_change_first_visit():
    run_js(SETUP + r"""
saved.progress={t2:saved.progress.t2,t1:{updated_at:null,step:0,state:'not_started'},dismissed_at:null,active:null};
await journeyEnsure();assert.equal(el('journey-band').hidden,false);
""")


def test_pending_failure_is_not_shown_as_waiting():
    run_js(SETUP + r"""
saved.pending={attempt:'a1',job:'j1',mode:'real',started_at:new Date().toISOString()};
const normal=api;api=async(p,o)=>p==='/api/jobs'?{jobs:[{id:'j1',status:'failed',error:{message:'Fake job failed',fix:'Retry input'}}]}:normal(p,o);
await journeyEnsure();assert.ok(el('journey-band').textContent.includes('Fake job failed'));
assert.equal(el('journey-band').textContent.includes(T('journey.trial.waiting')),false);
""")
