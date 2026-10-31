"""S5 사실 표시와 작업 차단 회귀. 가짜 문서·응답·시계만 사용한다."""
import pytest

from test_B_b_app_dom import run_js


def test_dom_stringifies_non_node_arguments_like_browser():
    run_js(r"""
      for (const method of ['append','prepend','replaceChildren','before','after','replaceWith']) {
        const parent=h('div'), target=h('span'); parent.append(target);
        const detail=h('details'), object={fake:1};
        target[method]([detail],object,null,undefined,7,false);
        assert.equal(parent.querySelector('details'),null,method);
        assert.ok(parent.textContent.includes(String([detail])+String(object)+'nullundefined7false'),method);
        assert.equal(detail.parentElement,undefined,method);
      }
      const parent=h('div'), target=h('span'); parent.append(target);
      target.before(h('b',null,'B')); target.after(h('i',null,'I'));
      target.prepend('P'); target.append('A'); assert.equal(parent.textContent,'BPAI');
      target.replaceWith(h('strong',null,'S'),'T'); assert.equal(parent.textContent,'BSTI');
    """)


def test_help_renders_nine_chapters_as_elements():
    from test_B_b_app_help_ui import setup
    run_js(setup() + r"""
      await go('s07',{helpTopic:'score'});
      assert.equal(document.querySelectorAll('details[data-help-topic]').length,9);
      assert.doesNotMatch(document.getElementById('screen-s07').textContent,/\[object/);
      assert.ok(document.getElementById('help-methods').isConnected);
      assert.ok(document.getElementById('help-methods').textContent.includes('Fake method'));
      const host=h('div',{id:'fake-card'}); document.body.append(host);
      card('fake-card','Fake',null,[h('p',null,'One'),h('p',null,'Two')]);
      assert.equal(host.querySelectorAll('p').length,2);
    """)


def test_model_lookup_failure_is_not_ai_off():
    run_js(r"""
      const model={tag:'fake',where:'RunPod',url_set:true,reachable:false,match:null,error:'TimeoutError'};
      let data={models:[model],rngd:{}};
      api=async path=>{assert.equal(path,'/api/servers');return data;};
      shellRenderContext(); await shellPollServers(); await go('s06');
      const context=()=>document.getElementById('context-model').textContent;
      const row=()=>document.getElementById('servers-models').textContent;
      assert.ok(context().includes(T('context.model.query_failed')));
      assert.ok(row().includes(T('context.model.query_failed')));
      assert.ok(!context().includes(T('context.model.state_off')));
      data.session={tag:'fake',ready:false,adopted:true}; await shellPollServers();
      assert.ok(context().includes(T('context.model.query_failed')));
      assert.ok(!context().includes(T('context.model.rented_loading')));
      data={models:[{...model,reachable:true,match:false,model_served:'other',error:null}]};
      await shellPollServers();
      assert.ok(context().includes(T('context.model.wrong_reply')));
      assert.ok(row().includes(T('context.model.wrong_reply')));
      data={models:[{...model,where:'RNGD'}],rngd:{ok:true,diagnosis:'loading',models:[{model:'fake'}]}};
      await shellPollServers();
      assert.ok(context().includes(T('context.model.company_loading')));
      assert.ok(row().includes(T('context.model.company_loading')));
      data.rngd={ok:true,diagnosis:'no_model',models:[]}; await shellPollServers();
      assert.ok(context().includes(T('context.model.state_off')));
      data.rngd={ok:true,diagnosis:'tunnel_closed',models:[{model:'fake'}]}; await shellPollServers();
      assert.ok(context().includes(T('context.model.tunnel_closed')));
      assert.ok(!context().includes(T('context.model.state_off')));
      data={models:[model,{tag:'ready',label:'Ready fake',reachable:true,match:true}]}; await shellPollServers();
      assert.ok(context().includes('Ready fake'));
      assert.ok(context().includes(T('context.model.query_failed')));
      assert.ok(!context().includes(T('context.model.state_off')));
      data={models:[{...model,url_set:false,error:null}]}; await shellPollServers();
      assert.ok(context().includes(T('context.model.readiness_unknown')));
      data={models:[]}; await shellPollServers();
      assert.ok(context().includes(T('context.model.readiness_unknown')));
      data={models:[{tag:'empty',reachable:true,model_served:null,match:null}]}; await shellPollServers();
      assert.ok(context().includes(T('context.model.state_off')));
    """)


@pytest.mark.parametrize('route', ['s01', 's02', 's08'])
def test_saved_results_do_not_wait_for_model_status(route):
    from test_B_b_app_score_ui import FIXTURE
    run_js(FIXTURE + f"location.hash='#{route}';" + r"""
      S.shell.contextLoaded=false; S.ctx={version:1,set:null,key:null};
      const normal=api; let serverSignal, releaseServer, releaseList, releaseContext;
      const listWait=new Promise(resolve=>releaseList=resolve);
      const contextWait=new Promise(resolve=>releaseContext=resolve);
      api=async(path,opts={})=>{
        if(path==='/api/servers') {serverSignal=opts.signal;return new Promise(resolve=>releaseServer=resolve);}
        if(path==='/api/sets'){await contextWait;return {default:'prev/fake',sets:[{id:'prev/fake',usable:true,docs:[{doc_id:'T21-X01'}]}]};}
        if(path==='/api/keys'){await contextWait;return {default:key.id,keys:[{...key,usable:true}]};}
        if(path==='/api/journey')return {journey:journeyDefault(),problems:[]};
        if(path.startsWith('/api/doc')) {calls.push(path);return {doc_id:'T21-X01',pages:[],lines:[],values:[],silver_only:[],sections:{},key};}
        if(path.startsWith('/api/runs')&&!path.includes('count='))await listWait;
        return normal(path);
      };
      const started=start(); await flush();
      assert.equal(S.shell.contextLoaded,false);
      releaseContext(); await flush();
      assert.equal(S.shell.contextLoaded,true);
      if(location.hash==='#s01')assert.ok(el('score-summary').textContent.includes(T('score.loading.scoring',{count:4})));
      releaseList(); await flush();
      if(location.hash==='#s01') {
        assert.ok(calls.some(p=>p.startsWith('/api/run/fake-current')));
        assert.ok(el('score-summary').textContent.includes('82.4'));
      } else if(location.hash==='#s02')assert.ok(calls.some(p=>p.startsWith('/api/doc')));
      else {assert.ok(calls.some(p=>p.startsWith('/api/run/fake-current')));assert.equal(S.journeyUI.run.weighted,82.4);}
      assert.ok(el('context-model').textContent.includes(T('context.model.query_pending')));
      clockTick(60000); await flush();
      assert.ok(el('context-model').textContent.includes(T('context.model.query_failed')));
      assert.equal(serverSignal.aborted,true);
      assert.equal(S.shell.polling,null);
      if(location.hash==='#s01')assert.ok(el('score-summary').textContent.includes('82.4'));
      releaseServer({models:[{tag:'stale',reachable:true,match:true}]}); await flush();
      assert.ok(el('context-model').textContent.includes(T('context.model.query_failed')));
      await started;
    """)


def test_missing_key_name_shows_unknown_not_draft():
    from test_B_b_app_score_ui import FIXTURE
    from test_B_b_app_source_ui import fixture
    run_js(FIXTURE + r"""
      S.shell.keys=[{id:key.id,label:key.label},{id:'gold/current',label:'Current key'}];
      delete run.key.label; await go('s01');
      assert.ok(el('score-summary').textContent.includes('Reviewed fake answers'));
      run.key={id:'gold/missing'}; await scoreLoad(true);
      assert.ok(el('score-summary').textContent.includes(T('score.basis.fallback')));
      assert.equal(T('score.basis.fallback'),T('jobs.external.unknown'));
      assert.ok(el('score-summary').textContent.includes(T('context.answer_mismatch',
        {result_key:T('score.basis.fallback'),selected_key:'Reviewed fake answers'})));
      assert.ok(!el('score-summary').textContent.includes(T('context.answer_draft')));
      run.key=null; await scoreLoad(true);
      assert.ok(el('score-summary').textContent.includes(T('score.basis.fallback')));
      assert.equal(el('score-summary').querySelector('.answer-mismatch'),null);
    """)
    run_js(fixture() + r"""
      S.shell.keys=[{id:view.key.id,label:view.key.label}]; delete view.key.label;
      await go('s02'); assert.ok(el('source-top').textContent.includes('Reviewed fake answers'));
      view.key={id:'gold/missing'}; await sourceLoad(true);
      assert.ok(el('source-top').textContent.includes(T('score.basis.fallback')));
      assert.ok(el('source-top').textContent.includes(T('context.answer_mismatch',
        {result_key:T('score.basis.fallback'),selected_key:'Reviewed fake answers'})));
    """)


@pytest.mark.parametrize('response_status', [202, 204, 206, 200, 'broken'])
def test_try_success_requires_http_200(response_status):
    from test_B_b_app_jobs_ui import SETUP
    status = repr(response_status)
    run_js(
      "const realApi=api;" + SETUP + f"const responseStatus={status};" + r"""
      const events=[];on('try_result_viewed',e=>events.push(e));
      await go('s03',{doc:'T21-X01',section:8});
      S.jobs.observed.add('j1'); listed=[job('done')]; S.jobs.list=listed;
      response=result(true); let code=responseStatus;
      globalThis.fetch=async(path,opts)=>path==='/api/journey'
        ? {ok:true,status:200,json:async()=>JSON.parse(opts.body)}
        : ({ok:true,status:code==='broken'?200:code,json:async()=>{
        if(code==='broken')throw new Error('Unreadable result');return response;
      }});
      api=realApi;
      await jobsWatch('j1');
      if(code===200) {
        assert.equal(events.length,1);assert.equal(events[0].section_ok,true);
        assert.equal(S.journey.outcomes.t2.real.count,1);
      } else {
        assert.equal(events.length,0);assert.equal(S.journey.outcomes.t2.real,null);
        assert.ok(el('jobs-result-retry'));
        assert.ok(!textOf('jobs-result').includes(T('jobs.result.plain_done')));
        code=200; await el('jobs-result-retry').click();
        assert.equal(events.length,1);assert.equal(S.journey.outcomes.t2.real.count,1);
      }
      await jobsLoadResult('j1');assert.equal(events.length,1);
    """)


def test_retest_focus_shows_plain_values_not_json():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      view.values[1].value={raw:'8 fake-unit',value:8,unit:'fake-unit',approx:null};
      view.values[1].silver.value={raw:'5 fake-unit',value:5,unit:'fake-unit',approx:null};
      await go('s02',{section:8}); pick(1).click(); sourceRemember();
      S.jobs.t.doc=S.focus.doc; S.jobs.t.secs=new Set([8]);
      let box=jobsRenderFocus();
      assert.ok(box.textContent.includes(T('jobs.focus.pair',{key_value:'5 fake-unit',ai_value:'8 fake-unit'})));
      assert.doesNotMatch(box.textContent,/[{}]|"raw"|null|\[object/);
      delete view.values[1].value.raw; delete view.values[1].silver.value.raw; sourceRemember();
      box=jobsRenderFocus(); assert.ok(box.textContent.includes('5 fake-unit')); assert.ok(box.textContent.includes('8 fake-unit'));
      assert.doesNotMatch(box.textContent,/[{}]|"raw"|null|\[object/);
    """)
