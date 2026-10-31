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
        if(n===8)continue;
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
      assert.ok(dialog.textContent.includes(keys.keys[0].updated_at));
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
      assert.ok(el.textContent.includes('2'));assert.equal(el.textContent.includes('wrong'),false);
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
