"""모델 연결 화면. 가짜 API와 시계만 쓰며 실제 서버를 부르지 않는다."""
import pytest

from test_B_b_app_dom import run_js


FIXTURE = r"""
Date.now=()=>Date.parse('2026-10-31T12:12:00+09:00');
const data={models:[
 {tag:'company-a',model_expected:'Fake model A',model_served:null,where:'RNGD',url_set:true,reachable:false,match:false},
 {tag:'rented-b',model_expected:'Fake model B',model_served:'Fake model B',where:'RunPod',url_set:true,reachable:true,match:true}],
 pods:[{id:'owned1',name:'Our server',owned:true,deletable:true,status:'RUNNING',uptime_s:4320,cost_per_hr:2.5,cost_est:3,auto_delete_min:168},
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
"""


def test_pod_ownership_deletability_and_adoption_are_visible():
    run_js(FIXTURE + r"""
      data.pods.push({id:'locked1',name:'Locked server',owned:true,deletable:false});
      data.why.pod_delete='Waiting for another job';await setup();
      const pods=document.getElementById('servers-runpod');
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
      await setup();const own=document.querySelector('[data-pod="owned1"]'),other=document.querySelector('[data-pod="external1"]');
      assert.ok(own.textContent.includes(T('servers.time.hours_minutes',{hours:1,minutes:12})));
      assert.ok(own.textContent.includes('$3.00'));assert.ok(own.textContent.includes('$2.50'));
      assert.ok(other.textContent.includes(T('servers.rented.unknown')));assert.ok(!other.textContent.includes('$0'));
      assert.ok(own.textContent.includes(T('servers.time.auto_delete',{minutes:168})));
      assert.ok(view().textContent.includes(T('servers.rented.volumes',{count:2})));
    """)


def test_tunnel_port_ownership_and_elapsed_time():
    run_js(FIXTURE + r"""
      await setup();const el=document.getElementById('servers-rngd');
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
      await setup();
    """ + f"assert.ok(view().textContent.includes(T({json.dumps(key)})));assert.ok(view().querySelector({json.dumps(button)}));")


def test_unknown_diagnosis_uses_model_friendly_not_invented_cause():
    run_js(FIXTURE + r"""
      data.rngd.diagnosis=null;data.rngd.ok=false;data.models[0].friendly={message:'Cannot inspect model',fix:'Check model settings',raw:'SyntheticFailure'};
      await setup();const el=document.getElementById('servers-rngd');
      assert.ok(el.textContent.includes('Cannot inspect model'));assert.ok(el.textContent.includes('Check model settings'));
      assert.ok(!el.textContent.includes(T('servers.diagnosis.no_model.fact')));
      assert.equal(el.querySelector('details').open,false);
    """)


def test_loading_elapsed_fake_clock_unknown_time_and_no_duplicate_load():
    run_js(FIXTURE + r"""
      data.rngd.diagnosis='loading';data.rngd.loading_since='2026-10-31T12:00:00+09:00';await setup();
      assert.ok(view().textContent.includes(T('servers.diagnosis.loading.elapsed',{minutes:12})));
      assert.ok(view().textContent.includes(T('servers.diagnosis.loading.todo')));assert.equal(action('rngd_up').disabled,true);
      data.rngd.loading_since='invalid';await shellPollServers();
      assert.ok(view().textContent.includes(T('servers.diagnosis.loading.unknown')));
    """)


def test_tunnel_open_uses_confirmation_and_token_even_while_running():
    run_js(FIXTURE + r"""
      data.locked=true;data.lock_reason='Running test';data.rngd.diagnosis='tunnel_closed';data.rngd.tunnel.open=false;
      data.can.tunnel_open=true;data.can.tunnel_close=false;await setup();
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
      assert.ok(view().textContent.includes('RUNPOD_VLLM_API_KEY'));
      assert.doesNotMatch(view().textContent,/[A-Z_]*(?:API_KEY|BASE_URL|SSH)\s*=/);
      assert.ok(view().textContent.includes(T('servers.reload.changed')));
    """)


def test_409_locks_actions_shows_jobs_and_preserves_tunnel_exception():
    run_js(FIXTURE + r"""
      await setup();post=async()=>{throw Object.assign(new Error('Locked'),{status:409,body:{lock_reason:'Fake job running',running:[{id:'job1',label:'Fake extraction',kind:'try'}]}});};
      await action('pod_create').click();
      assert.equal(action('pod_create').disabled,true);assert.equal(action('rngd_up').disabled,true);
      assert.ok(view().textContent.includes('Fake job running'));assert.ok(view().textContent.includes('Fake extraction'));
      assert.ok(view().textContent.includes(T('servers.busy.title')));
      await shellPollServers();assert.equal(action('pod_create').disabled,false);
    """)


def test_503_disables_actions_with_fact_todo_and_collapsed_raw():
    run_js(FIXTURE + r"""
      await setup();api=async()=>{throw Object.assign(new Error('Disabled'),{status:503});};await shellPollServers();
      const el=document.getElementById('servers-summary');
      assert.ok(el.textContent.includes(T('servers.disabled.fact')));assert.ok(el.textContent.includes(T('servers.disabled.todo')));
      assert.equal(el.querySelector('details').open,false);assert.equal(action('pod_create').disabled,true);
      assert.ok(!view().textContent.includes('Our server'));
    """)


def test_server_log_instruction_only_with_lines():
    run_js(FIXTURE + r"""
      await setup();let el=document.getElementById('servers-log');
      assert.ok(el.textContent.includes(T('servers.logs.empty')));assert.ok(!el.textContent.includes(T('servers.logs.manual_copy')));
      data.log_tail=['Fake log line'];await shellPollServers();el=document.getElementById('servers-log');
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
      await setup();const el=document.getElementById('servers-models');
      assert.ok(el.textContent.includes(T('servers.mismatch.title')));assert.ok(el.textContent.includes('Different model'));
      assert.ok(el.textContent.includes(T('servers.models.unknown')));
      assert.doesNotMatch(view().textContent,/null|undefined|⟦/);
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
      await setup();let release,count=0;post=async()=>{count++;return new Promise(resolve=>{release=resolve;});};
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
      await setup();await action('pod_create').click();Date.now=()=>Date.parse('2026-10-31T12:23:00+09:00');
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
      await setup();data.rngd_choices.push({tag:'company-c',label:'Model C',model:'Fake model C',cards:1});
      await shellPollServers();const select=document.getElementById('servers-choice');select.value='company-c';select.dispatchEvent({type:'change'});
      const detail=document.getElementById('servers-rngd').querySelector('details');detail.open=true;
      document.getElementById('servers-choice').focus();await shellPollServers();
      assert.equal(document.getElementById('servers-rngd').querySelector('details').open,true);
      assert.equal(document.getElementById('servers-choice').value,'company-c');assert.equal(document.activeElement.id,'servers-choice');
    """)


def test_model_process_and_tunnel_actions_use_api_targets():
    run_js(FIXTURE + r"""
      await setup();await action('rngd_up').click();
      assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'rngd_up',params:{tag:'company-a'}});
      document.getElementById('servers-cancel').click();
      data.rngd.models=[{model:'Another fake model',pid:555}];await shellPollServers();calls.length=0;
      await action('rngd_down').click();assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'rngd_down',params:{model:'Another fake model'}});
      document.getElementById('servers-cancel').click();calls.length=0;
      await action('tunnel_close').click();assert.deepEqual(calls.find(c=>c[1].endsWith('/propose'))[2],{action:'tunnel_close',params:{}});
    """)


def test_empty_and_long_hostile_text_stays_text_with_no_placeholder():
    run_js(FIXTURE + r"""
      data.pods[0].name='<img onerror=alert(1)>'+ 'long'.repeat(100);data.log_tail=['<script>fake</script>'];
      data.models[0].friendly={message:'<b>Failure</b>',fix:'Read details',raw:'<script>fake</script>'};
      await setup();assert.equal(view().querySelector('img'),null);assert.equal(view().querySelector('script'),null);
      data.models=[];data.pods=[];data.session=null;data.rngd={};data.rngd_choices=[];await shellPollServers();
      assert.doesNotMatch(view().textContent,/null|undefined|⟦/);assert.ok(view().textContent.includes(T('servers.empty.title')));
    """)


def test_expected_offline_diagnosis_is_neutral_in_table_and_compact():
    run_js(FIXTURE + r"""
      data.models[0].friendly={message:T('servers.diagnosis.no_model.fact'),fix:T('servers.diagnosis.no_model.todo'),raw:'ConnectionRefusedError'};
      await setup();assert.equal(document.getElementById('servers-models').querySelector('.error-note'),null);
      const el=document.getElementById('jobs-connection');serversRenderCompact(el,{model:'company-a'});
      assert.equal(el.querySelector('.error-note'),null);assert.ok(el.textContent.includes(T('servers.diagnosis.no_model.fact')));
      data.rngd.diagnosis=null;await shellPollServers();assert.ok(el.querySelector('.error-note'));
    """)


def test_reload_waits_for_old_inflight_status_then_reads_fresh_status():
    run_js(FIXTURE + r"""
      await setup();let finishOld,requests=0;
      api=async()=>{requests++;if(requests===1)return new Promise(resolve=>{finishOld=resolve;});return {...data,env_problems:[]};};
      const old=shellPollServers();const reload=document.getElementById('servers-reload-env').click();
      await Promise.resolve();finishOld({...data,env_problems:[{message:'Old settings',fix:'Old advice'}]});
      await Promise.all([old,reload]);assert.equal(requests,2);assert.equal(S.shell.servers.env_problems.length,0);
    """)


def test_connection_entry_keeps_requested_model_and_unknown_target_is_not_ready():
    run_js(FIXTURE + r"""
      data.rngd_choices.push({tag:'company-c',label:'Model C',model:'Fake model C',cards:1});
      await setup();assert.equal(document.getElementById('servers-choice').value,'company-a');
      await go('s06',{model:'company-c'});assert.equal(document.getElementById('servers-choice').value,'company-c');
      await go('s06',{model:'removed-model'});assert.equal(document.getElementById('servers-return'),null);
      assert.ok(!document.getElementById('servers-summary').textContent.includes(T('servers.ready.title',{model:'Fake model B'})));
    """)
