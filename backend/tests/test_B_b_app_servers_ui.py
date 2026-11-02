"""모델 연결 화면. 가짜 API와 시계만 쓰며 실제 서버를 부르지 않는다."""
import re

import pytest

from test_B_b_app_dom import STATIC, run_js


FIXTURE = r"""
Date.now=()=>Date.parse('2026-10-31T12:12:00+09:00');
const data={models:[
 {tag:'company-a',model_expected:'Fake model A',model_served:null,where:'RNGD',url_set:true,reachable:false,match:false},
 {tag:'rented-b',model_expected:'Fake model B',model_served:'Fake model B',where:'RunPod',url_set:true,reachable:true,match:true}],
 create_quote:{tag:'rented-b',cost_per_hr:1.73,max_hours:4,max_cost:6.92,basis:'Fake basis'},
 pods:[{id:'owned1',name:'Our server',owned:true,deletable:true,session:true,status:'RUNNING',uptime_s:4320,cost_per_hr:2.5,cost_est:3,auto_delete_min:168},
 {id:'external1',name:'External server',owned:false,deletable:false,status:'STOPPED',uptime_s:null,cost_per_hr:null,cost_est:null}],
 session:{pod_id:'owned1',tag:'rented-b',ready:true,adopted:true,others:['owned2']},volumes:2,
 rngd:{ok:true,diagnosis:'no_model',models:[],loading_since:null,
 tunnel:{port:18000,open:true,owned:true,pid:71,since:'2026-10-31T11:00:00+09:00'}},
 rngd_choices:[{tag:'company-a',label:'Model A',model:'Fake model A',cards:4,devices:'0,1,2,3'}],
 env_problems:[],log_tail:[],running_jobs:[],locked:false,lock_reason:null,
 can:{pod_create:true,pod_delete:true,rngd_up:true,rngd_down:true,tunnel_open:false,tunnel_close:true},why:{}};
const calls=[];
api=async path=>{calls.push(['get',path]);if(path==='/api/servers')return data;
 if(path==='/api/sets')return {sets:[]};if(path==='/api/keys')return {keys:[]};throw new Error(path);};
post=async(path,body)=>{calls.push(['post',path,body]);
 if(path.endsWith('/propose'))return {token:'single-use-token',action:body.action,summary:body.action==='pod_create'?'Action summary. 시간당 약 $1.73. Pending.':'Action summary',warning:'Action warning',expires_in:600};
 if(path.endsWith('/execute'))return {ok:true,result:{pod_id:'owned1',gone:true,remaining:[],started:true,killed:[71]},log_line:'Action recorded'};
 if(path.endsWith('/reload_env'))return {ok:true,names:['RUNPOD_VLLM_API_KEY'],changed:['RUNPOD_VLLM_API_KEY'],removed:[],problems:[]};
 throw new Error(path);};
const action=(name,root=document)=>root.querySelector('[data-server-action="'+name+'"]');
const view=()=>document.getElementById('screen-s06');
const setup=async()=>{shellRenderContext();await shellPollServers();await go('s06');};
const byId=id=>document.getElementById(id);
const stage=()=>byId('servers-flow');
const stepNow=()=>byId('servers-step-bar').querySelector('[aria-current="step"]').textContent;
const atStep=id=>assert.ok(stepNow().includes(T('steps.server.'+id)),stepNow());
const modelsOff=()=>{for(const model of data.models)Object.assign(model,{reachable:false,match:false,model_served:null});};
const allOff=()=>{data.session=null;data.pods=[];modelsOff();};
const pending=()=>{modelsOff();data.session={pod_id:'owned1',tag:'rented-b',ready:false,adopted:false,others:[]};
 Object.assign(data.pods[0],{uptime_s:200,cost_est:.14,auto_delete_min:36});};
const drawer=()=>document.querySelector('#details-drawer .drawer-body');
const openDrawer=()=>{byId('servers-details-open').click();return drawer();};
const posts=()=>calls.filter(c=>c[0]==='post');
const executions=()=>calls.filter(c=>c[1].endsWith('/execute'));
const lastAction=()=>[...stage().querySelector('.step-actions').querySelectorAll('button')].at(-1);
"""


def test_pod_ownership_deletability_and_adoption_are_visible():
    run_js(FIXTURE + r"""
      data.pods.push({id:'locked1',name:'Locked server',owned:true,deletable:false});
      data.why.pod_delete='Waiting for another job';await setup();
      const pods=openDrawer();
      assert.equal(pods.querySelectorAll('[data-server-action="pod_delete"]').length,1);
      const external=pods.querySelector('[data-pod="external1"]'),locked=pods.querySelector('[data-pod="locked1"]');
      assert.equal(action('pod_delete',external),null);assert.equal(action('pod_delete',locked),null);
      assert.ok(external.textContent.includes(T('servers.messages.pod_not_ours')));
      assert.ok(locked.textContent.includes(data.why.pod_delete));
      assert.ok(pods.textContent.includes(T('servers.session.adopted',{pod_id:'owned1'})));
      assert.ok(pods.textContent.includes('owned2'));
    """)


def test_pod_uptime_cost_and_unknown_do_not_claim_free():
    run_js(FIXTURE + r"""
      await setup();const body=openDrawer(),own=body.querySelector('[data-pod="owned1"]'),other=body.querySelector('[data-pod="external1"]');
      assert.ok(own.textContent.includes(T('servers.time.hours_minutes',{hours:1,minutes:12})));
      assert.ok(own.textContent.includes('$3.00'));assert.ok(own.textContent.includes('$2.50'));
      assert.ok(other.textContent.includes(T('servers.rented.unknown')));assert.ok(!other.textContent.includes('$0'));
      assert.ok(own.textContent.includes(T('servers.time.auto_delete',{minutes:168})));
      assert.ok(body.textContent.includes(T('servers.rented.volumes',{count:2})));
    """)


def test_tunnel_port_ownership_and_elapsed_time():
    run_js(FIXTURE + r"""
      await setup();const el=openDrawer();
      assert.ok(el.textContent.includes(T('servers.connection.tunnel_owned',{port:18000})));
      assert.ok(el.textContent.includes(T('servers.time.hours_minutes',{hours:1,minutes:12})));
      assert.ok(el.textContent.includes('71'));assert.ok(action('tunnel_close'));
      data.rngd.tunnel.owned=false;data.can.tunnel_close=false;data.why.tunnel_close=T('servers.controls.not_owned');
      await shellPollServers();assert.ok(el.textContent.includes(T('servers.controls.not_owned')));
      assert.equal(action('tunnel_close').disabled,true);
    """)


def test_delete_needs_confirmation_then_uses_token_once():
    run_js(FIXTURE + r"""
      await setup();const button=action('pod_delete');button.focus();await button.click();
      const dialog=document.getElementById('action-confirm');assert.equal(dialog.open,true);
      assert.ok(dialog.textContent.includes('Action summary'));assert.ok(dialog.textContent.includes('Action warning'));
      assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,0);
      const confirm=document.getElementById('servers-confirm');await confirm.click();await confirm.click();
      const executed=calls.filter(c=>c[1].endsWith('/execute'));assert.equal(executed.length,1);
      assert.deepEqual(executed[0][2],{token:'single-use-token'});assert.equal(dialog.open,false);
      assert.ok(view().textContent.includes('Action recorded'));
    """)


def test_dialog_traps_focus_escape_restores_trigger_and_cancels_without_execution():
    run_js(FIXTURE + r"""
      await setup();const button=action('pod_delete');button.focus();await button.click();
      const dialog=document.getElementById('action-confirm'),cancel=document.getElementById('servers-cancel'),confirm=document.getElementById('servers-confirm');
      assert.ok(dialog.contains(document.activeElement));
      confirm.focus();dialog.dispatchEvent({type:'keydown',key:'Tab'});assert.equal(document.activeElement,cancel);
      cancel.focus();dialog.dispatchEvent({type:'keydown',key:'Tab',shiftKey:true});assert.equal(document.activeElement,confirm);
      dialog.dispatchEvent({type:'keydown',key:'Escape'});assert.equal(dialog.open,false);
      assert.equal(document.activeElement,action('pod_delete'));assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,0);
      await action('pod_delete').click();dialog.dispatchEvent({type:'cancel'});assert.equal(dialog.open,false);
    """)


@pytest.mark.parametrize("diagnosis,key,button", [
    ("ok", "servers.diagnosis.ready.fact", "#servers-return"),
    ("no_model", "servers.diagnosis.no_model.fact", '[data-server-action="rngd_up"]'),
    ("tunnel_closed", "servers.diagnosis.tunnel_closed.fact", '[data-server-action="tunnel_open"]'),
    ("loading", "servers.diagnosis.loading.unknown", "#servers-read-results"),
])
def test_rngd_diagnosis_fact_and_next_action(diagnosis, key, button):
    import json
    run_js(FIXTURE + f"data.rngd.diagnosis={json.dumps(diagnosis)};" + r"""
      S.focus={doc:'T21-X01',section:8,model:'company-a'};
      if(data.rngd.diagnosis==='ok')Object.assign(data.models[0],{reachable:true,match:true,model_served:'Fake model A'});
      if(data.rngd.diagnosis==='tunnel_closed'){data.rngd.tunnel.open=false;data.can.tunnel_open=true;}
      await setup();if(byId('servers-use-company'))await byId('servers-use-company').click();
    """ + f"assert.ok(view().textContent.includes(T({json.dumps(key)})));assert.ok(view().querySelector({json.dumps(button)}));")


def test_unknown_diagnosis_uses_model_friendly_not_invented_cause():
    run_js(FIXTURE + r"""
      data.rngd.diagnosis=null;data.rngd.ok=false;data.models[0].friendly={message:'Cannot inspect model',fix:'Check model settings',raw:'SyntheticFailure'};
      S.focus={model:'company-a'};await setup();const el=stage();
      assert.ok(el.textContent.includes('Cannot inspect model'));assert.ok(el.textContent.includes('Check model settings'));
      assert.ok(!el.textContent.includes(T('servers.diagnosis.no_model.fact')));
      assert.equal(el.querySelector('details'),null);assert.ok(!el.textContent.includes('SyntheticFailure'));
      assert.ok(openDrawer().textContent.includes('SyntheticFailure'));
    """)


def test_loading_elapsed_fake_clock_unknown_time_and_no_duplicate_load():
    run_js(FIXTURE + r"""
      data.rngd.diagnosis='loading';data.rngd.loading_since='2026-10-31T12:00:00+09:00';S.focus={model:'company-a'};await setup();atStep('wait');
      assert.ok(view().textContent.includes(T('servers.diagnosis.loading.elapsed',{minutes:12})));
      assert.ok(view().textContent.includes(T('servers.diagnosis.loading.todo')));
      assert.equal(action('rngd_up'),null);assert.equal(serversReason('rngd_up'),T('servers.connection.loading_locked'));
      data.rngd.loading_since='invalid';await shellPollServers();
      assert.ok(view().textContent.includes(T('servers.diagnosis.loading.unknown')));
    """)


def test_tunnel_open_uses_confirmation_and_token_even_while_running():
    run_js(FIXTURE + r"""
      data.locked=true;data.lock_reason='Running test';data.rngd.diagnosis='tunnel_closed';data.rngd.tunnel.open=false;
      data.can.tunnel_open=true;data.can.tunnel_close=false;S.focus={model:'company-a'};await setup();await byId('servers-use-company').click();
      assert.equal(action('tunnel_open').disabled,false);await action('tunnel_open').click();
      assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'tunnel_open',params:{}});
      assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,0);
      await document.getElementById('servers-confirm').click();
      assert.deepEqual(calls.find(c=>c[1].endsWith('/execute'))[2],{token:'single-use-token'});
    """)


def test_reload_env_posts_then_refreshes_and_shows_names_only():
    run_js(FIXTURE + r"""
      data.env_problems=[{line:17,message:T('servers.env.title',{line_no:17}),fix:T('servers.env.todo')}];
      await setup();assert.ok(view().textContent.includes(T('servers.env.title',{line_no:17})));
      calls.length=0;await document.getElementById('servers-reload-env').click();
      assert.deepEqual(calls.map(c=>c[1]),['/api/servers/reload_env','/api/servers']);
      assert.ok(view().textContent.includes(T('servers.reload.done')));
      const body=openDrawer();assert.ok(body.textContent.includes('RUNPOD_VLLM_API_KEY'));
      assert.doesNotMatch(body.textContent,/[A-Z_]*(?:API_KEY|BASE_URL|SSH)\s*=/);
      assert.ok(body.textContent.includes(T('servers.reload.changed')));
    """)


def test_409_locks_actions_shows_jobs_and_preserves_tunnel_exception():
    run_js(FIXTURE + r"""
      allOff();await setup();await byId('servers-use-rented').click();
      post=async()=>{throw Object.assign(new Error('Locked'),{status:409,body:{lock_reason:'Fake job running',running:[{id:'job1',label:'Fake extraction',kind:'try'}]}});};
      await action('pod_create').click();
      assert.equal(action('pod_create').disabled,true);assert.ok(serversReason('rngd_up').includes('Fake job running'));
      assert.ok(view().textContent.includes('Fake job running'));assert.ok(view().textContent.includes('Fake extraction'));
      assert.ok(view().textContent.includes(T('servers.busy.title')));
      await shellPollServers();assert.equal(action('pod_create').disabled,false);
    """)


def test_503_disables_actions_with_fact_todo_and_collapsed_raw():
    run_js(FIXTURE + r"""
      await setup();api=async()=>{throw Object.assign(new Error('Disabled'),{status:503});};await shellPollServers();
      const el=stage();
      assert.ok(el.textContent.includes(T('servers.disabled.fact')));assert.ok(el.textContent.includes(T('servers.disabled.todo')));
      assert.equal(el.querySelector('details'),null);assert.equal(action('pod_create'),null);assert.ok(serversReason('pod_create'));
      assert.ok(!view().textContent.includes('Our server'));assert.ok(openDrawer().textContent.includes('Disabled'));
    """)


def test_server_log_instruction_only_with_lines():
    run_js(FIXTURE + r"""
      await setup();const el=openDrawer();
      assert.ok(el.textContent.includes(T('servers.logs.empty')));assert.ok(!el.textContent.includes(T('servers.logs.manual_copy')));
      data.log_tail=['Fake log line'];await shellPollServers();
      assert.ok(el.textContent.includes('Fake log line'));assert.ok(el.textContent.includes(T('servers.logs.manual_copy')));
      assert.ok(el.textContent.includes('runs/manual/server_log.md'));
    """)


def test_compact_shares_status_for_only_selected_model_and_keeps_target():
    run_js(FIXTURE + r"""
      await setup();const el=document.getElementById('jobs-connection');calls.length=0;
      S.focus={doc:'T21-X01',section:8,model:'company-a'};serversRenderCompact(el,{model:'company-a'});
      assert.ok(el.textContent.includes('Fake model A'));assert.ok(!el.textContent.includes('Fake model B'));
      assert.ok(el.querySelector('button'));assert.equal(calls.length,0);
      await el.querySelector('button').click();assert.equal(location.hash,'#s06');assert.equal(S.focus.doc,'T21-X01');
      Object.assign(data.models[0],{reachable:true,match:true,model_served:'Fake model A'});data.rngd.diagnosis='ok';
      await shellPollServers();assert.ok(el.textContent.includes(T('servers.models.connected')));
      await document.getElementById('servers-return').click();assert.equal(location.hash,'#s03');assert.equal(S.focus.section,8);
    """)


def test_model_mismatch_unknown_and_no_missing_strings():
    run_js(FIXTURE + r"""
      data.models[0].reachable=true;data.models[0].model_served='Different model';
      data.models.push({tag:'unknown',model_expected:'Unknown model',reachable:null,match:null,url_set:false});
      await setup();const el=openDrawer();
      assert.ok(el.textContent.includes(T('servers.mismatch.title')));assert.ok(el.textContent.includes('Different model'));
      assert.ok(el.textContent.includes(T('servers.models.unknown')));
      assert.doesNotMatch(view().textContent+el.textContent,/null|undefined|⟦/);
    """)


def test_one_poll_timer_and_one_request_for_shell_server_view_and_compact():
    run_js(FIXTURE + r"""
      location.hash='#s06';await start();serversRenderCompact(document.getElementById('jobs-connection'),{model:'rented-b'});
      assert.equal(calls.filter(c=>c[1]==='/api/servers').length,1);
      assert.equal(timers.size,1);
      let release;api=async()=>new Promise(resolve=>{release=resolve;});
      const a=shellPollServers(),b=shellPollServers();release(data);await Promise.all([a,b]);
      assert.ok(document.getElementById('context-model').textContent.includes('Fake model B'));
    """)


def test_slow_double_submit_and_failed_create_are_not_retried_automatically():
    run_js(FIXTURE + r"""
      allOff();await setup();await byId('servers-use-rented').click();
      let release,count=0;post=async()=>{count++;return new Promise(resolve=>{release=resolve;});};
      const first=action('pod_create').click();await action('pod_create').click();assert.equal(count,1);
      assert.ok(view().textContent.includes(T('servers.status.busy')));
      release({token:'once',action:'pod_create',summary:'Review cost. 시간당 약 $1.73. Pending.',expires_in:600});await first;
      post=async()=>{count++;throw new Error('Request lost');};await document.getElementById('servers-confirm').click();
      assert.equal(count,2);assert.ok(view().textContent.includes(T('servers.create_unknown.title')));
      assert.equal(document.getElementById('action-confirm').open,false);
    """)


def test_poll_schedule_follows_visible_screen_without_a_second_timer():
    run_js(FIXTURE + r"""
      location.hash='#s06';await start();calls.length=0;
      clockTick(9999);assert.equal(calls.length,0);clockTick(1);
      for(let n=0;n<10;n++)await Promise.resolve();
      assert.equal(calls.filter(c=>c[1]==='/api/servers').length,1);assert.equal(timers.size,1);
      await go('s07');calls.length=0;clockTick(59999);assert.equal(calls.length,0);clockTick(1);
      for(let n=0;n<10;n++)await Promise.resolve();
      assert.equal(calls.filter(c=>c[1]==='/api/servers').length,1);assert.equal(timers.size,1);
    """)


def test_changed_lock_or_failed_poll_invalidates_open_confirmation():
    run_js(FIXTURE + r"""
      await setup();await action('pod_delete').click();
      data.locked=true;data.lock_reason='A new job started';await shellPollServers();
      const confirm=document.getElementById('servers-confirm');assert.equal(confirm.disabled,true);
      await confirm.click();assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,0);
      assert.ok(document.getElementById('action-confirm').textContent.includes('A new job started'));
      document.getElementById('servers-cancel').click();data.locked=false;await shellPollServers();
      await action('pod_delete').click();api=async()=>{throw new Error('Status unavailable');};await shellPollServers();
      assert.equal(document.getElementById('servers-confirm').disabled,true);
    """)


def test_expired_confirmation_does_not_post_and_keeps_recovery():
    run_js(FIXTURE + r"""
      allOff();await setup();await byId('servers-use-rented').click();
      await action('pod_create').click();Date.now=()=>Date.parse('2026-10-31T12:23:00+09:00');
      await document.getElementById('servers-confirm').click();
      assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,0);
      assert.ok(view().textContent.includes(T('servers.confirm.expired.fact')));
      assert.ok(document.getElementById('servers-refresh'));
    """)


def test_failed_delete_keeps_actual_remaining_resources_and_record():
    run_js(FIXTURE + r"""
      await setup();await action('pod_delete').click();
      post=async()=>({ok:false,result:{pod_id:'owned1',gone:false,remaining:['owned1','external1'],minutes:72,est_cost:3},log_line:'Deletion checked'});
      await document.getElementById('servers-confirm').click();
      assert.ok(view().textContent.includes(T('servers.result.deleting',{pod_id:'owned1'})));
      assert.ok(view().textContent.includes('Deletion checked'));
      assert.ok(!view().textContent.includes(T('servers.result.done')));
    """)


def test_refresh_preserves_device_details_and_keyboard_selection():
    run_js(FIXTURE + r"""
      allOff();await setup();await byId('servers-use-company').click();
      data.rngd_choices.push({tag:'company-c',label:'Model C',model:'Fake model C',cards:1});
      await shellPollServers();const select=document.getElementById('servers-choice');select.value='company-c';select.dispatchEvent({type:'change'});
      document.getElementById('servers-choice').focus();await shellPollServers();
      assert.equal(document.getElementById('servers-choice').value,'company-c');assert.equal(document.activeElement.id,'servers-choice');
      atStep('start');openDrawer();byId('servers-reload-env-drawer').focus();await shellPollServers();
      assert.equal(byId('details-drawer').open,true);assert.equal(document.activeElement.id,'servers-reload-env-drawer');
    """)


def test_model_process_and_tunnel_actions_use_api_targets():
    run_js(FIXTURE + r"""
      allOff();await setup();await byId('servers-use-company').click();await action('rngd_up').click();
      assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'rngd_up',params:{tag:'company-a'}});
      document.getElementById('servers-cancel').click();
      data.rngd.models=[{model:'Another fake model',pid:555}];await shellPollServers();calls.length=0;
      await action('rngd_down').click();assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'rngd_down',params:{model:'Another fake model'}});
      document.getElementById('servers-cancel').click();calls.length=0;
      await action('tunnel_close',openDrawer()).click();assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'tunnel_close',params:{}});
    """)


def test_empty_and_long_hostile_text_stays_text_with_no_placeholder():
    run_js(FIXTURE + r"""
      data.pods[0].name='<img onerror=alert(1)>'+ 'long'.repeat(100);data.log_tail=['<script>fake</script>'];
      data.models[0].friendly={message:'<b>Failure</b>',fix:'Read details',raw:'<script>fake</script>'};
      await setup();const body=openDrawer();for(const place of [view(),body]){assert.equal(place.querySelector('img'),null);assert.equal(place.querySelector('script'),null);}
      data.models=[];data.pods=[];data.session=null;data.rngd={};data.rngd_choices=[];await shellPollServers();
      assert.doesNotMatch(view().textContent+body.textContent,/null|undefined|⟦/);assert.ok(body.textContent.includes(T('servers.empty.title')));
    """)


def test_expected_offline_diagnosis_is_neutral_in_table_and_compact():
    run_js(FIXTURE + r"""
      data.models[0].friendly={message:T('servers.diagnosis.no_model.fact'),fix:T('servers.diagnosis.no_model.todo'),raw:'ConnectionRefusedError'};
      await setup();openDrawer();assert.equal(byId('servers-model-list').querySelector('.error-note'),null);drawerClose();
      const el=document.getElementById('jobs-connection');serversRenderCompact(el,{model:'company-a'});
      assert.equal(el.querySelector('.error-note'),null);assert.ok(el.textContent.includes(T('servers.diagnosis.no_model.fact')));
      data.rngd.diagnosis=null;await shellPollServers();assert.ok(el.querySelector('.error-note'));
    """)


def test_reload_waits_for_old_inflight_status_then_reads_fresh_status():
    run_js(FIXTURE + r"""
      await setup();let finishOld,requests=0;
      api=async()=>{requests++;if(requests===1)return new Promise(resolve=>{finishOld=resolve;});return {...data,env_problems:[]};};
      openDrawer();const old=shellPollServers();const reload=document.getElementById('servers-reload-env-drawer').click();
      await Promise.resolve();finishOld({...data,env_problems:[{message:'Old settings',fix:'Old advice'}]});
      await Promise.all([old,reload]);assert.equal(requests,2);assert.equal(S.shell.servers.env_problems.length,0);
    """)


def test_connection_entry_keeps_requested_model_and_unknown_target_is_not_ready():
    run_js(FIXTURE + r"""
      data.rngd_choices.push({tag:'company-c',label:'Model C',model:'Fake model C',cards:1});
      await setup();await go('s06',{model:'company-a'});await byId('servers-use-company').click();assert.equal(document.getElementById('servers-choice').value,'company-a');
      await go('s06',{model:'company-c'});await byId('servers-use-company').click();assert.equal(document.getElementById('servers-choice').value,'company-c');
      await go('s06',{model:'removed-model'});assert.equal(document.getElementById('servers-return'),null);
      assert.ok(!view().textContent.includes(T('servers.ready.title',{model:'Fake model B'})));
    """)


def test_session_pod_state_is_readable_not_an_unknown_record():
    run_js(FIXTURE + r"""
      data.pods[0].state='준비됨';await setup();const body=openDrawer();
      assert.ok(body.querySelector('[data-pod="owned1"]').textContent.includes(T('servers.rented.state',{state:'준비됨'})));
      assert.equal(body.querySelector('[data-pod="owned1"]').textContent.includes(T('common.codes.unknown')),false);
    """)


# ── 단계 흐름 (phase app-steps step 2, ADR-039) ─────────

def test_opens_choose_step_when_no_ai_is_on():
    run_js(FIXTURE + r"""
      allOff();await setup();atStep('choose');
      assert.ok(byId('servers-use-rented'));assert.ok(byId('servers-use-company'));
      assert.equal(byId('title-s06').textContent,T('steps.server.choose_title'));
      assert.equal(posts().length,0);
    """)


def test_opens_wait_step_while_a_server_is_being_made():
    run_js(FIXTURE + r"""
      pending();await setup();atStep('wait');
      allOff();data.rngd.diagnosis='loading';await shellPollServers();atStep('wait');
      data.rngd.diagnosis='no_model';await shellPollServers();atStep('choose');
    """)


def test_opens_stop_step_when_the_chosen_ai_replies():
    run_js(FIXTURE + r"""
      await setup();atStep('stop');
      await go('s06',{model:'rented-b'});atStep('stop');
      assert.equal(byId('title-s06').textContent,T('servers.ready.title',{model:'Fake model B'}));
    """)


def test_another_ai_replying_is_not_ready_for_the_chosen_one():
    run_js(FIXTURE + r"""
      await setup();await go('s06',{model:'company-a'});atStep('choose');
      assert.equal(byId('servers-return'),null);
      assert.ok(stage().textContent.includes(T('steps.server.other_on',{model:'Fake model B'})));
      await byId('servers-see-live').click();atStep('stop');
    """)


def test_status_update_moves_the_flow_from_wait_to_stop():
    run_js(FIXTURE + r"""
      pending();await setup();atStep('wait');
      Object.assign(data.models[1],{reachable:true,match:true,model_served:'Fake model B'});data.session.ready=true;
      await shellPollServers();atStep('stop');
    """)


@pytest.mark.parametrize('model,fits,other', [('rented-b', 'rented', 'company'), ('company-a', 'company', 'rented')])
def test_choose_marks_only_the_server_that_can_start_the_chosen_ai(model, fits, other):
    run_js(FIXTURE + f"const model='{model}',fits='{fits}',other='{other}';" + r"""
      allOff();await setup();await go('s06',{model});
      const cards=stage().querySelectorAll('.server-card');assert.equal(cards.length,2);
      assert.equal(cards[0].dataset.serverKind,fits);
      const fit=stage().querySelector('[data-server-kind="'+fits+'"]'),no=stage().querySelector('[data-server-kind="'+other+'"]');
      assert.ok(fit.textContent.includes(T('steps.server.matches')));assert.ok(!fit.textContent.includes(T('steps.server.mismatch')));
      assert.ok(no.textContent.includes(T('steps.server.mismatch')));assert.ok(!no.textContent.includes(T('steps.server.matches')));
      assert.equal(byId('servers-use-'+fits).classList.contains('primary'),true);
      assert.equal(byId('servers-use-'+other).classList.contains('primary'),false);
      assert.ok(!view().textContent.includes(T('servers.choice.recommendation')));
    """)


def test_two_server_cards_compare_price_wait_and_cleanup():
    run_js(FIXTURE + r"""
      allOff();await setup();
      const rented=stage().querySelector('[data-server-kind="rented"]'),company=stage().querySelector('[data-server-kind="company"]');
      assert.ok(rented.textContent.includes(T('context.model.rented_hourly',{cost:'1.73'})));
      assert.ok(rented.textContent.includes(T('servers.compare.rented.wait')));
      assert.ok(rented.textContent.includes(T('servers.compare.rented.cleanup')));
      assert.ok(rented.textContent.includes('Fake model B'));
      assert.ok(company.textContent.includes(T('steps.server.company_cost')));
      assert.ok(company.textContent.includes(T('servers.compare.company.wait')));
      assert.ok(company.textContent.includes(T('servers.compare.company.limit')));
      assert.ok(company.textContent.includes('Model A'));
      assert.ok(company.textContent.includes(T('servers.compare.company.cost_meaning')));
    """)


def test_which_server_fits_comes_from_api_values():
    run_js(FIXTURE + r"""
      allOff();data.rngd_choices.push({tag:'rented-b',label:'Same',model:'Fake model B',cards:1});
      data.create_quote.tag='something-else';await setup();await go('s06',{model:'rented-b'});
      assert.ok(stage().querySelector('[data-server-kind="company"]').textContent.includes(T('steps.server.matches')));
      assert.ok(stage().querySelector('[data-server-kind="rented"]').textContent.includes(T('steps.server.mismatch')));
    """)
    source = (STATIC / 'js/servers.js').read_text()
    assert not re.search(r'qwen|gpt-oss|nuextract', source, re.I)


def test_ai_no_server_can_start_gets_no_recommendation():
    run_js(FIXTURE + r"""
      allOff();data.models.push({tag:'vision-c',model_expected:'Fake vision',where:'RNGD',url_set:true,reachable:false,match:false});
      await setup();await go('s06',{model:'vision-c'});
      assert.ok(view().textContent.includes(T('steps.server.no_server')));
      for(const kind of ['rented','company'])assert.equal(byId('servers-use-'+kind).classList.contains('primary'),false);
      assert.equal(stage().querySelectorAll('.server-card.fit').length,0);
    """)


def test_without_a_chosen_ai_company_server_is_recommended_first():
    run_js(FIXTURE + r"""
      allOff();await setup();
      assert.ok(view().textContent.includes(T('servers.choice.recommendation')));
      assert.equal(stage().querySelectorAll('.server-card')[0].dataset.serverKind,'company');
      assert.equal(byId('servers-use-company').classList.contains('primary'),true);
      assert.ok(!stage().textContent.includes(T('steps.server.matches')));
    """)


def test_rented_start_shows_the_quote_and_creates_only_after_confirmation():
    run_js(FIXTURE + r"""
      modelsOff();data.session=null;Object.assign(data.pods[0],{session:false,cost_per_hr:9.99,cost_est:36.55});
      await setup();await byId('servers-use-rented').click();atStep('start');
      const text=stage().textContent;
      for(const value of ['$1.73','$6.92','Fake basis','Fake model B',T('servers.rented.scheduler'),T('steps.server.stat_forgot',{hours:4})])
        assert.ok(text.includes(value),value);
      assert.ok(!text.includes('$9.99'));assert.ok(!text.includes('$36.55'));
      assert.equal(stage().querySelectorAll('[data-server-action]').length,1);
      assert.equal(lastAction(),action('pod_create'));assert.ok(lastAction().classList.contains('primary'));
      await action('pod_create').click();
      const dialog=byId('action-confirm');assert.equal(dialog.open,true);assert.equal(executions().length,0);
      assert.ok(dialog.textContent.includes(T('steps.server.confirm_create',{cost_per_hour:'1.73'})));
      assert.ok(byId('servers-confirm').textContent.includes('$1.73'));
      data.session={pod_id:'owned1',tag:'rented-b',ready:false,adopted:false,others:[]};data.pods[0].session=true;
      await byId('servers-confirm').click();assert.equal(executions().length,1);atStep('wait');
    """)


def test_cancelling_the_confirmation_stays_on_start_and_creates_nothing():
    run_js(FIXTURE + r"""
      allOff();await setup();await byId('servers-use-rented').click();
      await action('pod_create').click();byId('servers-cancel').click();
      atStep('start');assert.equal(executions().length,0);assert.equal(document.activeElement,action('pod_create'));
      await byId('servers-back').click();atStep('choose');assert.equal(executions().length,0);
    """)


def test_company_start_asks_for_one_action_at_a_time():
    run_js(FIXTURE + r"""
      allOff();data.rngd.diagnosis='no_model';data.rngd.tunnel.open=false;data.can.tunnel_open=true;data.can.tunnel_close=false;
      await setup();await byId('servers-use-company').click();atStep('start');
      assert.ok(action('tunnel_open'));assert.equal(action('rngd_up'),null);assert.equal(byId('servers-choice'),null);
      assert.equal(byId('title-s06').textContent,T('steps.server.start_company_tunnel_title'));
      assert.ok(stage().textContent.includes(T('servers.diagnosis.tunnel_closed.fact')));
      assert.ok(!stage().textContent.includes(T('servers.diagnosis.no_model.fact')));
      assert.equal(lastAction(),action('tunnel_open'));
      data.rngd.tunnel.open=true;await shellPollServers();
      assert.equal(action('tunnel_open'),null);assert.ok(action('rngd_up'));assert.ok(byId('servers-choice'));
      assert.equal(byId('title-s06').textContent,T('steps.server.start_company_pick_title'));
      assert.equal(lastAction(),action('rngd_up'));
      await action('rngd_up').click();assert.equal(byId('action-confirm').open,true);assert.equal(executions().length,0);
      const original=post;post=async(path,body)=>{const reply=await original(path,body);
        if(path.endsWith('/execute')){data.rngd.diagnosis='loading';data.rngd.models=[{model:'Fake model A',pid:9}];}return reply;};
      await byId('servers-confirm').click();assert.equal(executions().length,1);atStep('wait');
    """)


def test_company_start_with_another_model_up_offers_only_unload():
    run_js(FIXTURE + r"""
      allOff();data.rngd.models=[{model:'Another fake model',pid:555}];data.rngd.diagnosis='ok';
      await setup();await go('s06',{model:'company-a'});atStep('choose');await byId('servers-use-company').click();atStep('start');
      assert.equal(action('rngd_up').disabled,true);
      assert.ok(stage().textContent.includes(T('servers.connection.replace_locked')));
      assert.ok(stage().textContent.includes(T('servers.mismatch.title')));
      assert.ok(!stage().textContent.includes(T('servers.diagnosis.ready.todo')));
      await action('rngd_down').click();
      assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'rngd_down',params:{model:'Another fake model'}});
      data.rngd.models=[];data.rngd.diagnosis='no_model';await byId('servers-confirm').click();
      atStep('start');assert.equal(action('rngd_up').disabled,false);
    """)


def test_wait_step_says_only_what_the_app_knows():
    run_js(FIXTURE + r"""
      pending();await setup();atStep('wait');
      let list=stage().querySelector('.server-progress');
      assert.equal(list.querySelectorAll('li.done').length,1);assert.equal(list.querySelectorAll('li.now').length,1);
      assert.ok(list.querySelector('li.done').textContent.includes(T('steps.server.wait_server')));
      assert.ok(list.querySelector('li.now').textContent.includes(T('steps.server.wait_reply')));
      assert.ok(stage().textContent.includes(T('steps.server.wait_on_for',{elapsed:T('servers.time.minutes',{minutes:3})})));
      assert.ok(!stage().textContent.includes(T('steps.server.prepared_time',{elapsed:T('servers.time.minutes',{minutes:3})})));
      data.pods[0].status='EXITED';await shellPollServers();atStep('wait');list=stage().querySelector('.server-progress');
      assert.equal(list.querySelectorAll('li.done').length,0,'a finished server is not running');
      data.pods=[];await shellPollServers();atStep('wait');list=stage().querySelector('.server-progress');
      assert.equal(list.querySelectorAll('li.done').length,0);
      assert.ok(list.textContent.includes(T('steps.server.wait_server_unseen')));
    """)


def test_wait_step_never_turns_a_wrong_reply_into_ready():
    run_js(FIXTURE + r"""
      pending();Object.assign(data.models[1],{reachable:true,match:false,model_served:'Other model'});data.session.ready=true;
      await setup();atStep('wait');assert.ok(stage().textContent.includes(T('servers.mismatch.title')));
      assert.equal(byId('servers-return'),null);
    """)


def test_wait_step_can_cancel_only_our_server_and_can_read_results_meanwhile():
    run_js(FIXTURE + r"""
      pending();await setup();assert.equal(action('pod_delete').textContent,T('steps.server.cancel_rented'));
      assert.ok(byId('servers-refresh'));assert.equal(lastAction(),byId('servers-read-results'));
      await action('pod_delete').click();assert.equal(byId('action-confirm').open,true);assert.equal(executions().length,0);
      byId('servers-cancel').click();
      Object.assign(data.pods[0],{owned:false,deletable:false});await shellPollServers();atStep('wait');
      assert.equal(action('pod_delete'),null);
    """)


def test_prepared_time_is_a_number_only_with_a_record():
    run_js(FIXTURE + r"""
      await setup();atStep('stop');
      assert.ok(stage().textContent.includes(T('steps.server.preparation_unknown')));
      data.session.ready_seconds=250;await shellPollServers();
      assert.ok(stage().textContent.includes(T('steps.server.prepared_time',{elapsed:T('servers.time.minutes',{minutes:4})})));
      assert.ok(!stage().textContent.includes(T('steps.server.preparation_unknown')));
    """)


def test_stop_step_has_cost_numbers_and_delete_goes_through_confirmation():
    run_js(FIXTURE + r"""
      await setup();atStep('stop');
      const numbers=stage().querySelector('.server-stats').textContent;
      for(const value of ['$2.50','$3.00',T('servers.time.hours_minutes',{hours:1,minutes:12}),T('servers.time.hours_minutes',{hours:2,minutes:48}),
        T('steps.server.stat_hourly'),T('steps.server.stat_uptime'),T('steps.server.stat_total'),T('steps.server.stat_auto')])assert.ok(numbers.includes(value),value);
      assert.equal(action('pod_delete').textContent,T('steps.server.delete_action'));
      await action('pod_delete').click();assert.equal(byId('action-confirm').open,true);assert.equal(executions().length,0);
    """)


def test_stop_step_does_not_invent_unknown_numbers():
    run_js(FIXTURE + r"""
      Object.assign(data.pods[0],{uptime_s:null,cost_per_hr:null,cost_est:null,auto_delete_min:null});await setup();atStep('stop');
      const numbers=stage().querySelector('.server-stats').textContent;
      assert.ok(numbers.includes(T('steps.server.auto_unknown')));assert.ok(numbers.includes(T('servers.rented.unknown')));
      assert.ok(!numbers.includes('$0'));
    """)


def test_stop_step_has_no_delete_for_a_server_not_ours():
    run_js(FIXTURE + r"""
      data.session=null;Object.assign(data.pods[0],{owned:false,deletable:false,session:false});await setup();atStep('stop');
      assert.equal(action('pod_delete',stage()),null);assert.ok(stage().textContent.includes(T('servers.messages.pod_not_ours')));
      assert.equal(action('pod_delete',openDrawer()),null);
    """)


def test_stop_step_warns_about_our_other_running_servers():
    run_js(FIXTURE + r"""
      await setup();assert.ok(stage().textContent.includes(T('steps.server.others_running',{count:1})));
      data.session.others=[];await shellPollServers();
      assert.ok(!stage().textContent.includes(T('steps.server.others_running',{count:1})));
    """)


def test_stop_step_next_action_returns_to_the_trial():
    run_js(FIXTURE + r"""
      await setup();await go('s06',{model:'rented-b',returnScreen:'s03',doc:'T21-X01',section:8});
      assert.equal(lastAction(),byId('servers-return'));assert.ok(lastAction().classList.contains('primary'));
      assert.equal(lastAction().textContent,T('servers.ready.return_trial'));
      assert.ok(stage().textContent.includes(T('servers.company.return_target',{doc:'T21-X01',section:8})));
      await lastAction().click();assert.equal(location.hash,'#s03');assert.equal(S.focus.section,8);assert.equal(posts().length,0);
    """)


def test_company_stop_step_separates_unload_from_closing_the_tunnel_and_has_no_price():
    run_js(FIXTURE + r"""
      modelsOff();data.session=null;data.pods=[];Object.assign(data.models[0],{reachable:true,match:true,model_served:'Fake model A'});
      data.rngd.diagnosis='ok';data.rngd.models=[{model:'Fake model A',pid:71,elapsed_s:600}];
      await setup();atStep('stop');
      assert.ok(view().textContent.includes(T('servers.ready.company_cost')));
      assert.ok(stage().textContent.includes(T('servers.time.minutes',{minutes:10})));
      assert.ok(action('rngd_down',stage()));assert.ok(action('tunnel_close',stage()));assert.equal(action('pod_delete',stage()),null);
      assert.ok(!stage().textContent.includes('$'));
    """)


def test_ready_rented_server_shows_no_company_todo():
    run_js(FIXTURE + r"""
      data.models[0].friendly={message:T('servers.diagnosis.no_model.fact'),fix:T('servers.diagnosis.no_model.todo'),raw:'ConnectionRefusedError'};
      await setup();atStep('stop');
      for(const text of [view().textContent,openDrawer().textContent]){
        assert.ok(!text.includes(T('servers.diagnosis.no_model.todo')));
        assert.ok(!text.includes(T('servers.diagnosis.tunnel_closed.todo')));
      }
      assert.ok(!view().textContent.includes(T('servers.diagnosis.no_model.fact')));
    """)


def test_status_failure_never_comes_with_no_model_or_no_program():
    run_js(FIXTURE + r"""
      await setup();api=async()=>{throw new Error('Status unavailable');};await shellPollServers();
      assert.equal(byId('title-s06').textContent,T('servers.failed.title'));
      for(const text of [view().textContent,openDrawer().textContent]){
        assert.ok(!text.includes(T('servers.diagnosis.no_model.fact')));
        assert.ok(!text.includes(T('servers.connection.none')));
        assert.ok(!text.includes(T('servers.models.empty')));
      }
      assert.ok(view().textContent.includes(T('servers.failed.retry')));
      assert.equal(stage().querySelectorAll('.server-card').length,0);
      assert.ok(drawer().textContent.includes('Status unavailable'));
    """)


def test_finished_and_others_servers_stay_out_of_first_screen_costs():
    run_js(FIXTURE + r"""
      data.pods.push({id:'done1',name:'Finished server',owned:true,deletable:true,status:'EXITED',uptime_s:90000,cost_per_hr:9.99,cost_est:36.55},
        {id:'other1',name:'Someone server',owned:false,deletable:false,status:'RUNNING',uptime_s:7200,cost_per_hr:7.77,cost_est:15.54});
      await setup();atStep('stop');
      const check=()=>{for(const value of ['36.55','9.99','15.54','7.77','Finished server','Someone server','External server'])
        assert.ok(!stage().textContent.includes(value),value);};
      check();modelsOff();data.session=null;data.pods[0].session=false;await shellPollServers();atStep('choose');check();
      const body=openDrawer();
      for(const value of ['$36.55','$15.54','Finished server','Someone server','External server'])assert.ok(body.textContent.includes(value),value);
      assert.equal(action('pod_delete',body.querySelector('[data-pod="other1"]')),null);
      assert.ok(action('pod_delete',body.querySelector('[data-pod="done1"]')));
    """)


@pytest.mark.parametrize('prepare', [
    "allOff();await setup();",
    "allOff();await setup();await byId('servers-use-rented').click();",
    "allOff();await setup();await byId('servers-use-company').click();",
    "pending();await setup();",
    "await setup();",
    "await setup();api=async()=>{throw new Error('Status unavailable');};await shellPollServers();",
    "allOff();data.friendly={message:'Fake',fix:'Fake fix',raw:'FakeRaw'};data.runpod_error='FakeRaw';data.rngd.diagnosis=null;"
    "data.rngd.ok=false;data.rngd.friendly={message:'Fake two',fix:'Fix two',raw:'FakeRawTwo'};await setup();",
    "await setup();post=async()=>{throw new Error('Request failed');};await action('pod_delete').click();",
])
def test_steps_have_no_folds(prepare):
    run_js(FIXTURE + prepare + r"""
      assert.equal(view().querySelectorAll('details').length,0);
      assert.doesNotMatch(view().textContent,/null|undefined|⟦/);
    """)


def test_action_failure_shows_fact_and_todo_on_the_step_and_raw_in_the_drawer():
    run_js(FIXTURE + r"""
      await setup();post=async()=>{throw new Error('Request failed badly');};await action('pod_delete').click();
      assert.ok(stage().textContent.includes(T('servers.status.failure.fact')));
      assert.ok(!stage().textContent.includes('Request failed badly'));
      assert.ok(byId('servers-refresh'));assert.ok(byId('servers-reload-env'));
      assert.ok(openDrawer().textContent.includes('Request failed badly'));
    """)


def test_drawer_holds_server_list_settings_and_log_with_unique_titles():
    run_js(FIXTURE + r"""
      data.log_tail=['Fake log line'];await setup();
      for(const value of ['Our server is hidden','External server','RUNPOD_VLLM_API_KEY','Fake log line'])assert.ok(!stage().textContent.includes(value),value);
      const body=openDrawer();
      for(const value of ['Our server','External server','RUNPOD_VLLM_API_KEY','Fake log line','Fake model A',T('servers.env.hidden_values')])
        assert.ok(body.textContent.includes(value),value);
      const titles=body.querySelectorAll('h3').map(title=>title.textContent);
      assert.equal(new Set(titles).size,titles.length,titles.join(' | '));
      for(const key of ['steps.server.settings','steps.server.connection'])assert.ok(titles.includes(T(key)),key);
      assert.ok(!titles.includes(T('servers.connection.details')));
      assert.equal(body.querySelectorAll('details').length,0);
      assert.equal(byId('details-drawer').open,true);assert.ok(document.activeElement.classList.contains('drawer-close'));
      drawerClose();assert.equal(document.activeElement,byId('servers-details-open'));
    """)


def test_drawer_titles_stay_unique_with_every_kind_of_error_and_many_servers():
    run_js(FIXTURE + r"""
      data.pods.push({id:'more1',name:'More',owned:true,deletable:true,state:'RUNNING'},{id:'more2',name:'More two',owned:true,deletable:true,state:'EXITED'});
      data.friendly={message:'A',fix:'B',raw:'RawOne'};data.rngd.friendly={message:'C',fix:'D',raw:'RawTwo'};
      data.models[0].friendly={message:'E',fix:'F',raw:'RawThree'};data.env_problems=[{message:'G',fix:'H',raw:'RawFour'}];
      await setup();const body=openDrawer();const titles=body.querySelectorAll('h3').map(title=>title.textContent);
      assert.equal(new Set(titles).size,titles.length,titles.join(' | '));
      for(const raw of ['RawOne','RawTwo','RawThree','RawFour'])assert.ok(body.textContent.includes(raw),raw);
    """)


def test_open_drawer_follows_status_updates_and_keeps_owner_rules():
    run_js(FIXTURE + r"""
      await setup();openDrawer();data.pods[0].name='Renamed server';await shellPollServers();
      assert.ok(drawer().textContent.includes('Renamed server'));assert.equal(drawer().querySelectorAll('details').length,0);
      await action('pod_delete',drawer()).click();assert.equal(byId('action-confirm').open,true);assert.equal(executions().length,0);
    """)


def test_going_back_to_choose_sends_nothing_and_live_step_stays_reachable():
    run_js(FIXTURE + r"""
      await setup();atStep('stop');byId('servers-step-choose').click();atStep('choose');
      await shellPollServers();atStep('choose');
      byId('servers-step-stop').click();atStep('stop');assert.equal(posts().length,0);
      byId('servers-step-choose').click();await go('s06');atStep('stop');
    """)


def test_later_steps_cannot_be_pressed_before_they_are_real():
    run_js(FIXTURE + r"""
      allOff();await setup();
      for(const id of ['start','wait','stop'])assert.equal(byId('servers-step-'+id),null);
      await byId('servers-use-rented').click();atStep('start');
      for(const id of ['wait','stop'])assert.equal(byId('servers-step-'+id),null);
      assert.ok(byId('servers-step-choose').textContent.includes(T('steps.server.rented_name')));
    """)


def test_deleting_the_server_returns_to_choose_with_the_result():
    run_js(FIXTURE + r"""
      await setup();await action('pod_delete').click();
      const original=post;post=async(path,body)=>{const reply=await original(path,body);if(path.endsWith('/execute'))allOff();return reply;};
      await byId('servers-confirm').click();
      atStep('choose');assert.ok(stage().textContent.includes('Action recorded'));
    """)


def test_coming_from_the_trial_with_another_ai_forgets_the_old_choice():
    run_js(FIXTURE + r"""
      allOff();await setup();await byId('servers-use-company').click();atStep('start');
      await go('s06',{model:'rented-b',returnScreen:'s03'});atStep('choose');
      assert.equal(stage().querySelectorAll('.server-card')[0].dataset.serverKind,'rented');
      assert.ok(byId('servers-back'));await byId('servers-back').click();assert.equal(location.hash,'#s03');
    """)


def test_screen_registers_one_flow_view_and_html_has_its_places():
    run_js(FIXTURE + r"""
      assert.deepEqual(SHELL_SCREENS.s06.views,['servers-flow']);
      for(const id of ['servers-step-bar','servers-step-say','servers-flow','help-context-s06','title-s06'])assert.ok(byId(id),id);
      for(const id of ['servers-summary','servers-rngd','servers-runpod','servers-models','servers-log'])assert.equal(byId(id),null,id);
      await setup();const screen=stage().querySelector('.step-screen');assert.ok(screen);
      assert.equal(screen.children.at(-1).querySelector('.step-actions').parentElement,screen.children.at(-1));
    """)


def test_list_failure_never_calls_our_server_someone_elses():
    run_js(FIXTURE + r"""
      data.pods=[];data.runpod_error='List failed';data.friendly={message:'Cannot list servers',fix:'Check the key',raw:'List failed'};
      await setup();atStep('stop');
      assert.ok(stage().textContent.includes('Cannot list servers'));
      assert.ok(!stage().textContent.includes(T('servers.messages.pod_not_ours')));
      assert.equal(action('pod_delete',stage()),null);
      modelsOff();data.session={pod_id:'owned1',tag:'rented-b',ready:false,adopted:false,others:[]};await shellPollServers();atStep('wait');
      assert.ok(stage().textContent.includes('Cannot list servers'));
    """)


def test_drawer_has_no_tooltips_that_would_open_behind_it():
    # 말풍선(#tip)은 일반 요소라 모달 서랍 뒤에 그려진다.
    run_js(FIXTURE + r"""
      await setup();assert.equal(openDrawer().querySelector('[data-tip]'),null);
    """)


def test_card_that_cannot_start_the_chosen_ai_offers_another_ai_instead_of_turning_it_on():
    # 11/2 코덱스 판독: "고른 AI는 이 서버에서 켤 수 없습니다" 아래에 "켜기"가 있어 글이 충돌했다.
    run_js(FIXTURE + r"""
      allOff();await setup();await go('s06',{model:'rented-b'});
      assert.equal(byId('servers-use-company').textContent,T('steps.server.use_other_ai'));
      assert.equal(byId('servers-use-rented').textContent,T('steps.server.use_rented'));
      await go('s06',{model:'company-a'});
      assert.equal(byId('servers-use-rented').textContent,T('steps.server.use_other_ai'));
      assert.equal(byId('servers-use-company').textContent,T('steps.server.use_company'));
    """)


def test_status_lookup_failure_does_not_say_a_change_failed_and_retry_is_the_next_action():
    run_js(FIXTURE + r"""
      await setup();api=async()=>{throw Object.assign(new Error('Status down'),{status:500});};await shellPollServers();
      assert.ok(stage().textContent.includes(T('servers.failed.fact')));
      assert.ok(stage().textContent.includes(T('servers.failed.todo')));
      assert.equal(stage().textContent.includes(T('servers.status.failure.fact')),false);
      assert.equal(lastAction().id,'servers-refresh');
      assert.equal(Array.from(stage().querySelectorAll('button')).filter(b=>b.id==='servers-refresh').length,1);
    """)


def test_waiting_offers_other_work_first_and_says_what_cancel_and_auto_delete_mean():
    # 준비되면 저절로 넘어가므로 "다시 확인하기"가 주 행동이면 반복해서 눌러야 하는 것처럼 보인다.
    run_js(FIXTURE + r"""
      pending();await setup();atStep('wait');
      assert.equal(lastAction().id,'servers-read-results');
      assert.ok(byId('servers-refresh'));
      assert.equal(action('pod_delete').textContent,T('steps.server.cancel_rented'));
      assert.ok(stage().textContent.includes(T('steps.server.wait_auto',{minutes:36})));
    """)


def test_company_with_another_model_on_makes_turning_it_off_the_next_action():
    run_js(FIXTURE + r"""
      allOff();data.rngd.diagnosis='ok';data.rngd.models=[{model:'Other model',pid:5}];
      await setup();await go('s06',{model:'company-a'});serversChoose('company');atStep('start');
      assert.equal(byId('title-s06').textContent,T('steps.server.start_company_other_title'));
      assert.equal(lastAction().getAttribute('data-server-action'),'rngd_down');
      assert.equal(action('rngd_up').disabled,true);
    """)


def test_finished_server_in_the_drawer_has_no_hourly_rate():
    # 끝난 서버 옆의 시간당 요금은 지금도 돈이 나가는 것처럼 읽힌다. 쓴 금액은 남긴다.
    run_js(FIXTURE + r"""
      data.pods.push({id:'old1',name:'Old server',owned:true,deletable:true,status:'EXITED',uptime_s:null,cost_per_hr:2.5,cost_est:36.55});
      await setup();const pods=openDrawer(),old=pods.querySelector('[data-pod="old1"]');
      assert.equal(old.textContent.includes(T('servers.rented.hourly_rate')),false);
      assert.ok(old.textContent.includes('36.55'));
      assert.ok(pods.querySelector('[data-pod="owned1"]').textContent.includes(T('servers.rented.hourly_rate')));
    """)


def test_old_preparation_time_is_not_written_as_a_general_record():
    # G1에서 승인한 표 A2: 지난 기록의 고정 숫자를 일반 기록처럼 쓰지 않는다. 실제 기록은 session.ready_seconds다.
    assert '기록 약 6분' not in (STATIC.parent / 'b_app_servers.py').read_text()
