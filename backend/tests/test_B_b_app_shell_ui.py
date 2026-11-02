"""공통 뼈대의 조작 계약. 가짜 응답만 쓰며 브라우저 배치를 판정하지 않는다."""
from test_B_b_app_dom import run_js

FIXTURES = r"""
const sets={default:'prev/v9',sets:[
 {id:'prev/v9',label:'Development nine',usable:true,docs:[{doc_id:'T21-X01',locked:false}]},
 {id:'.',label:'New documents',usable:true,docs:[{doc_id:'RAW-X01',locked:false}]},
 {id:'locked',label:'Locked set',usable:false,reason:'Evaluation documents are locked',docs:[]}]};
const keys={default:'silver/fake',keys:[
 {id:'silver/fake',label:'Draft answers',usable:true,updated_at:'2026-10-30T12:00:00+09:00',fingerprint:'1234567890abcdef',docs:['T21-X01']},
 {id:'gold/fake',label:'Reviewed answers',usable:true,updated_at:'2026-10-31T12:00:00+09:00',fingerprint:'abcdef1234567890',docs:['T21-X01']},
 {id:'gold/empty',label:'Empty answers',usable:false,reason:'No answer files',updated_at:null,fingerprint:null,docs:[]}]};
const calls=[];
api=async path=>{calls.push(path);if(path==='/api/sets')return sets;if(path==='/api/keys')return keys;
 if(path==='/api/servers')return {models:[]};throw new Error(path);};
"""


def test_initial_route_is_pure_and_defaults_to_recent():
    run_js(r"""
      localStorage.getItem=()=>{throw new Error('must not read storage');};
      for(const hash of ['', '#unknown', null, '#start', '#s08'])assert.equal(shellInitialRoute(hash),'s01');
      for(let n=1;n<=10;n++){if(n===8)continue;const id='s'+String(n).padStart(2,'0');assert.equal(shellInitialRoute('#'+id),id);}
    """)


def test_navigation_menu_focus_registration_and_hash_changes():
    run_js(FIXTURES + r"""
      location.hash='#s02';await start();
      const shared=document.getElementById('global-context');
      for(let n=1;n<=10;n++){
        if(n===8||n===9)continue;  // S09는 다시 시험 첫 단계의 갈래가 됐다. 옛 주소는 아래에서 본다.
        const id='s'+String(n).padStart(2,'0');
        const button=document.querySelector('[data-screen="'+id+'"]');
        assert.equal(button.tagName,'button');
        await go(id,{doc:'T21-X01',section:8});
        assert.equal(location.hash,'#'+id);assert.equal(S.focus.doc,'T21-X01');
        const visible=document.querySelectorAll('main section').filter(el=>el.id.startsWith('screen-')&&!el.hidden);
        assert.equal(visible.length,1);assert.equal(visible[0].id,'screen-'+id);
        assert.equal(button.getAttribute('aria-current'),'page');
        assert.equal(document.getElementById('global-context'),shared);
      }
      await go('s09');assert.equal(location.hash,'#s03');assert.equal(document.getElementById('screen-s03').hidden,false);
      let loaded=0;
      shellDefineView('source-top',{render:el=>el.textContent='source view',load:async()=>{loaded++;}});
      await go('s02');assert.equal(loaded,1);assert.equal(document.getElementById('source-top').textContent,'source view');
      location.hash='#missing';window.dispatchEvent({type:'hashchange'});
      assert.equal(location.hash,'#s01');assert.equal(document.getElementById('screen-s01').hidden,false);
      assert.equal(document.querySelectorAll('#global-context').length,1);
      assert.ok(shared.closest('header'));
    """)


def test_context_picker_applies_once_keeps_cancel_and_shows_reasons_dates_and_fingerprint():
    run_js(FIXTURES + r"""
      await start();let changes=[];on('context_changed',e=>changes.push(e));
      await go('s03');S.focus={doc:'T21-X01',section:8};
      document.getElementById('context-change-key').focus();document.getElementById('context-change-key').click();
      const dialog=document.getElementById('context-picker');assert.equal(dialog.open,true);
      const set=document.getElementById('context-set'),key=document.getElementById('context-key');
      assert.equal(set.querySelector('[value="locked"]').disabled,true);
      assert.equal(key.querySelector('[value="gold/empty"]').disabled,true);
      assert.ok(dialog.textContent.includes(sets.sets[2].reason));assert.ok(dialog.textContent.includes(keys.keys[2].reason));
      assert.ok(dialog.textContent.includes(when(keys.keys[0].updated_at)));
      const details=dialog.querySelectorAll('details').find(el=>el.textContent.includes(keys.keys[0].fingerprint));
      assert.ok(details);assert.equal(details.open,false);
      set.value='.';key.value='gold/fake';key.dispatchEvent({type:'change'});
      assert.equal(S.ctx.key,'silver/fake');assert.equal(changes.length,0);
      document.getElementById('context-cancel').click();assert.equal(S.ctx.key,'silver/fake');
      assert.equal(document.activeElement.id,'context-change-key');
      document.getElementById('context-change-key').click();
      document.getElementById('context-set').value='.';document.getElementById('context-key').value='gold/fake';
      document.getElementById('context-apply').click();
      assert.equal(changes.length,1);assert.equal(S.ctx.set,'.');assert.equal(S.ctx.key,'gold/fake');
      assert.deepEqual(JSON.parse(localStorage.getItem('b_app.context')),{version:1,set:'.',key:'gold/fake'});
      assert.ok(document.getElementById('global-context').textContent.includes('Reviewed answers'));
      assert.ok(document.getElementById('global-context').textContent.includes('New documents'));
      assert.equal(location.hash,'#s03');assert.equal(dialog.open,false);
    """)


def test_context_restores_only_usable_values_and_survives_storage_errors():
    run_js(FIXTURES + r"""
      localStorage.setItem('b_app.context',JSON.stringify({version:1,set:'locked',key:'missing'}));
      await start();assert.equal(S.ctx.set,sets.default);assert.equal(S.ctx.key,keys.default);
      localStorage.getItem=()=>{throw new Error('denied');};localStorage.setItem=()=>{throw new Error('denied');};
      await shellLoadContext();document.getElementById('context-change-key').click();
      document.getElementById('context-key').value='gold/fake';document.getElementById('context-apply').click();
      assert.equal(S.ctx.key,'gold/fake');await go('s07');
      assert.equal(document.getElementById('screen-s07').hidden,false);
    """)
    run_js(FIXTURES + r"""
      localStorage.setItem('b_app.context',JSON.stringify({version:1,set:'.',key:'gold/fake'}));
      await start();assert.equal(S.ctx.set,'.');assert.equal(S.ctx.key,'gold/fake');
    """)


def test_context_empty_lists_and_request_failure_keep_navigation_and_honest_state():
    run_js(FIXTURES + r"""
      sets.sets=[];sets.default=null;keys.keys=[];keys.default=null;await start();
      assert.equal(S.ctx.set,null);assert.equal(S.ctx.key,null);
      document.getElementById('context-change-key').click();assert.equal(document.getElementById('context-apply').disabled,true);
      document.getElementById('context-cancel').click();
      api=async()=>{throw new Error('unavailable');};await shellLoadContext();await go('s06');
      assert.equal(document.getElementById('screen-s06').hidden,false);
      assert.ok(document.getElementById('global-context').querySelector('.error-note'));
    """)


def test_context_url_adds_key_only_to_contract_paths_preserving_other_arguments():
    run_js(r"""
      S.ctx={set:'prev/test',key:'gold/fake answer'};
      for(const path of ['/api/runs','/api/run/fake/run','/api/diff','/api/silver_gaps','/api/doc']){
        const out=ctxUrl(path+'?doc=T21-X01&key=old');const q=new URLSearchParams(out.split('?')[1]);
        assert.equal(q.get('key'),S.ctx.key);assert.equal(q.get('doc'),'T21-X01');assert.equal(q.has('set'),false);
      }
      for(const path of ['/api/sets','/api/keys','/api/servers','/api/options','/api/jobs','/api/runs-extra','/api/diff/prompts','/pages/T21-X01/p001.png'])assert.equal(ctxUrl(path),path);
      assert.equal(new URLSearchParams(ctxUrl('/api/doc?set=explicit').split('?')[1]).get('set'),'explicit');
      S.ctx.key=null;assert.equal(ctxUrl('/api/silver_gaps'),'/api/silver_gaps');
    """)


def test_api_and_post_preserve_error_status_and_gaps_response_shapes():
    run_js(r"""
      let sent;
      globalThis.fetch=async(path,opts)=>{sent={path,opts};return {ok:true,status:200,json:async()=>path.includes('?key=')?{key:{id:'gold/fake'},gaps:[]} : []};};
      S.ctx.key='gold/fake';assert.deepEqual(await api(ctxUrl('/api/silver_gaps')),{key:{id:'gold/fake'},gaps:[]});
      S.ctx.key=null;assert.deepEqual(await api(ctxUrl('/api/silver_gaps')),[]);
      await post('/api/test',{n:0});assert.equal(sent.opts.method,'POST');assert.equal(sent.opts.headers['Content-Type'],'application/json');
      assert.deepEqual(JSON.parse(sent.opts.body),{n:0});
      globalThis.fetch=async()=>({ok:false,status:503,json:async()=>({error:'disabled'})});
      await assert.rejects(api('/api/servers'),e=>e.message==='disabled'&&e.status===503);
      globalThis.fetch=async()=>({ok:true,status:204,json:async()=>{throw new Error('empty');}});
      assert.equal(await api('/api/jobs/fake/result'),null);
    """)


def test_model_connection_names_count_neutral_absence_and_error_recovery():
    run_js(FIXTURES + r"""
      await start();const el=document.getElementById('context-model');
      assert.ok(el.textContent.includes(T('context.model.readiness_unknown')));assert.equal(el.classList.contains('error'),false);
      api=async()=>({models:[{label:'Fake model A',model_expected:'fake-a',reachable:true,match:true},{model_expected:'fake-b',reachable:true,match:true},{model_expected:'wrong',reachable:true,match:false}]});
      await shellPollServers();assert.ok(el.textContent.includes('Fake model A'));assert.ok(el.textContent.includes('fake-b'));
      assert.ok(document.getElementById('context-model-open').getAttribute('data-tip').includes(T('context.model.connected_count',{count:2,names:'Fake model A, fake-b'})));
      assert.equal(el.textContent.includes('wrong'),false);
      api=async()=>{throw Object.assign(new Error('disabled'),{status:503});};await shellPollServers();
      assert.ok(el.textContent.includes(T('context.model.readiness_unknown')));assert.equal(el.classList.contains('error'),false);
      api=async()=>{throw new Error('read failed');};await shellPollServers();assert.equal(el.classList.contains('error'),true);
      api=async()=>({models:[]});await shellPollServers();assert.equal(el.classList.contains('error'),false);
      assert.equal(timers.size,1);assert.ok([...timers.values()].some(t=>t.at===60000));
    """)


def test_start_draws_navigation_before_pending_requests_and_polls_without_duplicates():
    run_js(FIXTURES + r"""
      let release;const wait=new Promise(resolve=>{release=resolve;});
      const normal=api;api=async path=>path==='/api/servers'?wait:normal(path);
      const pending=start();assert.equal(document.getElementById('screen-s01').hidden,false);
      assert.ok(document.getElementById('context-model').textContent.includes(T('context.model.query_pending')));
      await go('s07');release({models:[]});await pending;await shellPollServers();
      assert.equal(location.hash,'#s07');const count=timers.size;await start();assert.equal(timers.size,count);
    """)


def test_text_interpolation_missing_key_zero_false_and_shell_has_no_missing_copy():
    run_js(FIXTURES + r"""
      assert.equal(T('context.model.option',{model:'Fake',state:'ready'}),'Fake — ready');
      assert.equal(T('absent.key'),'⟦absent.key⟧');assert.equal(T('common.run.document',{doc:0}),'문서 0 한 건');
      await start();document.getElementById('context-change-key').click();
      for(const id of ['app-header','main-nav','global-context','context-picker','screen-s01'])
        assert.doesNotMatch(document.getElementById(id).textContent,/null|undefined|⟦/);
    """)


def test_card_preserves_content_state_focus_and_works_without_storage():
    run_js(r"""
      document.body.append(h('div',{id:'sample-card'}));
      card('sample-card','Title','Hint',{collapsed:true,summary:'Summary'},h('p',null,'Content'));
      const el=document.getElementById('sample-card'),toggle=el.querySelector('.card-toggle');
      assert.equal(el.querySelector('.card-body').hidden,true);assert.ok(el.textContent.includes('Content'));
      toggle.focus();toggle.click();assert.equal(el.querySelector('.card-body').hidden,false);
      assert.equal(JSON.parse(localStorage.getItem('b_app.cards'))['sample-card'],false);
      card('sample-card','Title',null,{collapsed:true,summary:'Updated'},h('p',null,'New content'));
      assert.equal(el.querySelector('.card-body').hidden,false);assert.equal(document.activeElement,el.querySelector('.card-toggle'));
      S.cards=loadCards();localStorage.setItem=()=>{throw new Error('denied');};el.querySelector('.card-toggle').click();
      assert.equal(el.querySelector('.card-body').hidden,true);
      for(const v of ['[]','{','null']){localStorage.getItem=()=>v;assert.deepEqual(loadCards(),{});}
      localStorage.getItem=()=>{throw new Error('denied');};assert.deepEqual(loadCards(),{});
    """)


def test_error_is_fact_action_and_closed_raw_detail_and_code_is_safe():
    run_js(r"""
      const el=loadFailure('<script>raw</script>');
      assert.equal(el.querySelector('strong').textContent,T('common.legacy.load_error.message'));
      assert.ok(el.textContent.includes(T('common.legacy.load_error.fix')));
      assert.equal(el.querySelector('details').open,false);assert.ok(el.textContent.includes('<script>raw</script>'));
      assert.equal(el.querySelector('script'),null);
      const custom=friendlyError({message:'Failed `VARIABLE`',fix:'Repair `VARIABLE`',raw:'raw'});
      assert.equal(custom.querySelector('code').textContent,'VARIABLE');
    """)


def test_tooltip_targets_get_keyboard_access_without_nested_tab_stops():
    run_js(r"""
      const lone=h('span',{'data-tip':'Explanation'},'Word');
      assert.equal(lone.getAttribute('tabindex'),'0');assert.equal(lone.getAttribute('aria-describedby'),'tip');
      const button=h('button',null,h('span',{'data-tip':'Explanation'},'Word'));
      assert.equal(button.querySelector('span').getAttribute('tabindex'),'-1');
      assert.equal(button.getAttribute('aria-describedby'),'tip');
      assert.equal(term('Unknown').textContent,'Unknown');
    """)


def test_tooltip_keyboard_escape_and_pointer_transfer():
    run_js(r"""
      const target=h('span',{'data-tip':'Explanation'},'Word');document.body.append(target);setupTip();
      const tip=document.getElementById('tip');target.focus();assert.equal(tip.hidden,false);assert.equal(tip.textContent,'Explanation');
      document.dispatchEvent({type:'keydown',key:'Escape'});assert.equal(tip.hidden,true);
      document.dispatchEvent({type:'focusout',relatedTarget:null});document.dispatchEvent({type:'mouseover',target});
      document.dispatchEvent({type:'mouseout',relatedTarget:null});assert.equal(tip.hidden,false);
      document.dispatchEvent({type:'mouseover',target:tip});clockTick(200);assert.equal(tip.hidden,false);
      document.dispatchEvent({type:'mouseout',relatedTarget:null});clockTick(200);assert.equal(tip.hidden,true);
    """)


def test_model_strip_names_the_connected_model_without_other_models_noise():
    # 실제 응답 모양(11/2): 회사 서버는 꺼짐, 주소 없는 태그 하나, Pod 하나가 Qwen3.6을 제공, 같은 주소의 다른 태그는 다른 모델 응답
    run_js(FIXTURES + r"""
      await start();const el=document.getElementById('context-model');
      api=async()=>({rngd:{ok:true,diagnosis:'no_model'},models:[
       {tag:'fake_rngd',where:'RNGD',url_set:true,reachable:false,error:'URLError'},
       {tag:'fake_no_address',where:'vLLM',url_set:false,reachable:false,error:null},
       {tag:'qwen36_35b_runpod',where:'RunPod',url_set:true,reachable:true,match:true,model_expected:'raw/model-id'},
       {tag:'fake_same_pod',where:'RunPod',url_set:true,reachable:true,match:false}]});
      await shellPollServers();
      assert.ok(el.textContent.includes(UI.context.models.qwen36_35b_runpod));
      assert.equal(el.textContent.includes('raw/model-id'),false);
      assert.equal(el.textContent.includes(T('context.model.readiness_unknown')),false);
      assert.equal(el.textContent.includes(T('context.model.wrong_reply')),false);
    """)


def test_model_without_address_is_off_and_real_problems_still_show_when_nothing_is_connected():
    run_js(FIXTURES + r"""
      await start();const el=document.getElementById('context-model');
      assert.equal(shellModelState({where:'RunPod',url_set:false,reachable:false,error:null}),'state_off');
      assert.equal(shellModelState({where:'RNGD',url_set:false,reachable:false,error:null},{rngd:{ok:true,diagnosis:'no_model'}}),'state_off');
      assert.equal(shellModelState({where:'RunPod',url_set:true,reachable:false,error:'URLError'}),'query_failed');
      api=async()=>({rngd:{ok:true,diagnosis:'no_model'},models:[
       {tag:'fake_rngd',where:'RNGD',url_set:true,reachable:false,error:'URLError'},
       {tag:'fake_pod',where:'RunPod',url_set:false,reachable:false,error:null}]});
      await shellPollServers();
      assert.ok(el.textContent.includes(T('context.model.state_off')));
      assert.ok(document.getElementById('context-model-open').getAttribute('data-tip').includes(T('context.model.off_normal')));
      assert.equal(el.textContent.includes(T('context.model.readiness_unknown')),false);
      api=async()=>({rngd:{ok:true,diagnosis:'no_model'},models:[{tag:'fake_pod',where:'RunPod',url_set:true,reachable:true,match:false}]});
      await shellPollServers();assert.ok(el.textContent.includes(T('context.model.wrong_reply')));
    """)


def test_session_pod_that_is_still_starting_reads_as_loading_not_failed():
    # RunPod 프록시는 모델이 뜨기 전까지 404와 502를 돌려준다 (11/2 실제 Pod로 확인)
    run_js(FIXTURES + r"""
      await start();const el=document.getElementById('context-model');
      const row={tag:'fake_pod',where:'RunPod',url_set:true,reachable:false,match:null,error:'HTTP 404'};
      assert.equal(shellModelState(row,{session:{tag:'fake_pod',ready:false}}),'rented_loading');
      assert.equal(shellModelState(row,{session:null}),'query_failed');
      assert.equal(shellModelState({...row,error:'HTTP 502'},{session:{tag:'fake_pod',ready:false}}),'rented_loading');
      assert.equal(shellModelState({...row,error:'HTTP 401'},{session:{tag:'fake_pod',ready:false}}),'query_failed');
      assert.equal(shellModelState({...row,error:'TimeoutError'},{session:{tag:'fake_pod',ready:false}}),'query_failed');
      api=async()=>({session:{tag:'fake_pod',ready:false},rngd:{ok:true,diagnosis:'no_model'},
       models:[row,{tag:'fake_rngd',where:'RNGD',url_set:true,reachable:false,error:'URLError'}]});
      await shellPollServers();
      assert.ok(el.textContent.includes(T('context.model.rented_loading')));
      assert.equal(el.textContent.includes(T('context.model.query_failed')),false);
    """)


# ── 위쪽 막대 한 줄과 왼쪽 메뉴 묶음 (phase app-steps, ADR-039) ─────────

TOP_BAR = r"""
const el=id=>document.getElementById(id);
const chipOf=()=>el('context-model-open');
const seen=()=>chipOf().textContent;
const tip=()=>chipOf().getAttribute('data-tip');
const POD={id:'p1',session:true,owned:true,status:'RUNNING',minutes:8,cost_per_hr:2.49,cost_est:0.33,uptime_s:480,auto_delete_min:18};
const ON={tag:'q',label:'Fake rented model',where:'RunPod',url_set:true,reachable:true,match:true};
const OFF={tag:'q',where:'RunPod',url_set:false,reachable:false,match:false};
const LOADING={tag:'q',where:'RunPod',url_set:true,reachable:false,match:null,error:'HTTP 502'};
const serve=async value=>{api=async path=>{if(path==='/api/servers'){if(value instanceof Error)throw value;return value;}if(path==='/api/sets')return sets;if(path==='/api/keys')return keys;throw new Error(path);};await shellPollServers();};
"""


def test_top_bar_holds_documents_answers_ai_and_guide_on_one_line():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();const bar=el('global-context');
      for(const id of ['context-change-set','context-change-key','context-model-open','guide-open','context-swap'])
        assert.ok(bar.contains(el(id)),id);
      assert.ok(bar.textContent.includes(T('nav.app_name')));
      assert.ok(bar.textContent.includes('Development nine'));assert.ok(bar.textContent.includes('Draft answers'));
      assert.ok(el('context-change-set').textContent.includes(T('context.documents.short')));
      assert.ok(el('context-change-key').textContent.includes(T('context.answer.short')));
      assert.equal(bar.querySelectorAll('p').length,0);
      assert.equal(bar.querySelectorAll('details').length,0);
      // 원래 폴더 이름은 막대에 그대로 쓰지 않고 말풍선과 선택 창에 남긴다
      assert.equal(bar.textContent.includes('prev/v9'),false);
      assert.ok(el('context-change-set').getAttribute('data-tip').includes('prev/v9'));
      assert.ok(el('context-change-key').getAttribute('data-tip').includes(T('context.answer_trust')));
    """)


def test_top_bar_shows_price_and_cost_so_far_for_the_session_server():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();await serve({models:[ON],session:{pod_id:'p1',ready:true,idle_minutes:20},pods:[POD]});
      assert.ok(seen().includes(T('context.model.chip_on')));
      assert.ok(seen().includes(T('context.model.rented_hourly',{cost:2.49})));
      assert.ok(seen().includes(T('context.model.rented_so_far',{cost:0.33})));
      assert.ok(seen().includes('Fake rented model'));
      assert.ok(tip().includes(T('steps.server.cost_basis')));
      assert.equal(seen().includes(T('context.model.chip_no_cost')),false);
    """)


def test_top_bar_makes_room_for_price_by_dropping_the_answer_date_first():
    # 요금이 붙으면 칩이 길어져 1440px에서 문서 묶음과 정답 이름이 잘렸다. 날짜 글을 먼저 뺀다. 11/2 브라우저 측정.
    run_js(FIXTURES + TOP_BAR + r"""
      await start();await serve({models:[OFF],pods:[]});
      assert.equal(chipOf().classList.contains('billing'),false);
      await serve({models:[ON],session:{pod_id:'p1',ready:true,idle_minutes:20},pods:[POD]});
      assert.ok(chipOf().classList.contains('billing'));
    """)
    from test_B_b_app_dom import STATIC
    css = (STATIC / 'app.css').read_text()
    assert '@media (max-width: 1599px) { .context-fields:has(.context-ai.billing) #context-answer-note { display: none; } }' in css
    # 1280px에서는 실패 글만으로도 문서 묶음 이름이 잘렸다. 날짜 글을 상태와 상관없이 뺀다.
    assert '@media (max-width: 1439px) { #context-answer-note { display: none; } }' in css


def test_top_bar_shows_cost_while_the_server_is_still_starting():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();await serve({models:[LOADING],session:{pod_id:'p1',ready:false,idle_minutes:20},pods:[POD]});
      assert.ok(seen().includes(T('context.model.rented_loading')));
      assert.ok(seen().includes(T('context.model.rented_hourly',{cost:2.49})));
      assert.ok(seen().includes(T('context.model.rented_so_far',{cost:0.33})));
      assert.equal(seen().includes(T('context.model.chip_on')),false);
    """)


def test_top_bar_says_off_without_cost_only_when_nothing_of_ours_runs():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();await serve({models:[OFF],pods:[{id:'team',owned:false,status:'RUNNING',cost_per_hr:9,cost_est:9}]});
      assert.ok(seen().includes(T('context.model.state_off')));
      assert.ok(seen().includes(T('context.model.chip_no_cost')));
      assert.equal(seen().includes('9'),false);                                     // 남의 서버 금액을 합치지 않는다
      await serve({models:[OFF],pods:[],runpod_error:'RUNPOD_API_KEY'});
      assert.ok(seen().includes(T('context.model.state_off')));
      assert.equal(seen().includes(T('context.model.chip_no_cost')),false);          // 목록을 못 읽으면 무료라고 쓰지 않는다
      assert.ok(seen().includes(T('context.model.chip_cost_unknown')));
    """)


def test_top_bar_lookup_failure_reads_differently_from_off():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();await serve(new Error('read failed'));
      assert.ok(seen().includes(T('context.model.query_failed')));
      assert.equal(seen().includes(T('context.model.state_off')),false);
      assert.equal(seen().includes(T('context.model.chip_no_cost')),false);
      assert.ok(seen().includes(T('context.model.chip_cost_unknown')));
      assert.equal(el('context-model').classList.contains('error'),true);
      assert.ok(tip().includes('read failed'));
    """)


def test_top_bar_session_server_without_price_says_unknown_instead_of_a_number():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();await serve({models:[ON],session:{pod_id:'p1',ready:true,idle_minutes:20},pods:[{...POD,cost_per_hr:null,cost_est:null}]});
      assert.ok(seen().includes(T('context.model.chip_cost_unknown')));
      assert.equal(seen().includes('null'),false);assert.equal(seen().includes('$'),false);
    """)


def test_top_bar_ai_chip_opens_servers_and_notes_move_to_its_tip():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();await serve({models:[OFF],pods:[]});
      for(const key of ['off_normal','off_no_cost','saved_readable'])assert.ok(tip().includes(T('context.model.'+key)),key);
      assert.ok(tip().includes(T('context.prepare_model')));
      assert.ok(tip().includes(when(S.shell.serverAt)));
      assert.equal(el('context-model').querySelectorAll('button').length,1);
      chipOf().click();await Promise.resolve();assert.equal(S.shell.route,'s06');
    """)


def test_top_bar_keeps_set_and_answer_change_flow_and_swap_entry():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();let changes=0;on('context_changed',()=>changes++);
      el('context-change-set').focus();el('context-change-set').click();
      assert.equal(el('context-picker').open,true);
      el('context-set').value='.';el('context-apply').click();
      assert.equal(S.ctx.set,'.');assert.equal(changes,1);assert.equal(document.activeElement.id,'context-change-set');
      assert.ok(el('global-context').textContent.includes('New documents'));
      el('context-swap').click();await Promise.resolve();assert.equal(S.shell.route,'s11');
    """)


def test_context_errors_appear_below_the_line_and_notes_keep_their_place():
    run_js(FIXTURES + TOP_BAR + r"""
      await start();assert.equal(el('context-errors').children.length,0);
      api=async()=>{throw new Error('unavailable');};await shellLoadContext();
      assert.ok(el('context-errors').querySelector('.error-note'));
      assert.equal(el('context-fields').contains(el('context-errors')),false);
      assert.ok(el('context-fields').contains(el('context-answer-note')));
      assert.equal(el('context-fields').contains(el('context-gold-notice')),false);
    """)


def test_app_purpose_and_definition_stay_visible_in_the_menu():
    run_js(FIXTURES + r"""
      await start();const nav=document.getElementById('main-nav');
      assert.ok(nav.textContent.includes(T('nav.purpose')));
      assert.ok(nav.textContent.includes(T('common.document_definition')));
      assert.ok(nav.textContent.includes(T('common.local_only')));
    """)


def test_menu_groups_the_work_order_and_the_rest_without_numbers():
    # 메뉴 번호가 단계 표시 번호와 겹쳐 헷갈렸다. 11/2 G2 사용자 결정으로 숫자는 단계 표시에만 둔다.
    run_js(FIXTURES + r"""
      await start();const nav=document.getElementById('main-nav');
      const groups=nav.querySelectorAll('.nav-group');assert.equal(groups.length,2);
      const ids=g=>Array.from(g.querySelectorAll('[data-screen]'),b=>b.dataset.screen);
      assert.deepEqual(ids(groups[0]).filter(id=>id!=='s10'),['s01','s02','s03','s04']);
      assert.deepEqual(ids(groups[1]),['s06','s05','s07']);
      assert.ok(groups[0].textContent.includes(T('nav.group_flow')));
      assert.ok(groups[1].textContent.includes(T('nav.group_other')));
      assert.equal(nav.querySelectorAll('.nav-no').length,0);
    """)


def test_screens_have_no_second_text_only_path():
    run_js(FIXTURES + r"""
      await start();
      for(const id of ['s01','s02','s03']){
        shellConclusion(id,'Conclusion');
        assert.equal(document.getElementById('title-'+id).textContent,'Conclusion');
        assert.equal(document.getElementById('flow-'+id),null);
      }
      assert.equal(document.querySelectorAll('.score-flow').length,0);
    """)


def test_jobs_are_reached_from_the_menu_and_not_duplicated_in_the_bar():
    run_js(FIXTURES + r"""
      await start();
      assert.equal(document.querySelectorAll('[data-screen="s05"]').length,1);
      assert.ok(document.getElementById('main-nav').contains(document.querySelector('[data-screen="s05"]')));
    """)


def test_bar_css_is_one_56px_line_with_tokens_only():
    import re
    from test_B_b_app_dom import STATIC
    css = (STATIC / 'app.css').read_text()
    assert re.search(r'\.context\s*\{[^}]*min-height:\s*56px', css)
    assert re.search(r'\.context-fields\s*\{[^}]*flex-wrap:\s*nowrap', css)
    assert re.search(r'--sticky-offset:\s*72px', css)
    assert '.score-flow' not in css
