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


# 접힌 상세의 textContent와 첫 화면 노출을 구분한다. 실제 앱의 DOM 동작을 검증한다.
FIX_VISIBLE = r"""
const visibleText=node=>{
 if(typeof node==='string')return node;
 if(node.hidden)return '';
 if(node.tagName==='details'&&!node.open)return node.querySelector('summary')?.textContent||'';
 return node.children?.length ? Array.from(node.children,visibleText).join('') : node.textContent;
};
"""


def test_s01_counts_are_field_level_and_scorer_counts_only_in_detail():
    from test_B_b_app_score_ui import FIXTURE
    run_js(FIXTURE + FIX_VISIBLE + r"""
      Object.assign(losses[0],{counts_basis:'field',counts:{'빠뜨림':13,'틀림':7,'지어냄':4},
        scorer_counts:{'빠뜨림':211,'틀림':212,'지어냄':213}});
      Object.assign(run.status_text.top_problem,losses[0]);
      await go('s01');
      for(const [kind,count] of [['missing',13],['wrong',7],['made',4]])
        assert.ok(visibleText(el('score-summary')).includes(T('score.problem.counts.'+kind,{count})));
      for(const id of ['score-summary','score-problems'])for(const count of [211,212,213])
        assert.ok(!el(id).textContent.includes(String(count)),id);
      const detail=el('score-rule');
      for(const count of [211,212,213])assert.ok(detail.textContent.includes(String(count)));
      assert.ok(!visibleText(detail).includes('211'));
      detail.querySelector('.card-toggle').click();
      assert.ok(visibleText(detail).includes('211'));
    """)


def test_s01_main_button_opens_doc_with_wrong_value_first():
    from test_B_b_app_score_ui import FIXTURE
    run_js(FIXTURE + r"""
      const top=run.status_text.top_problem;
      top.docs=[{doc_id:'T21-X01',loss:4,counts:{'틀림':0,'지어냄':3}},
        {doc_id:'T21-X02',loss:3,counts:{'틀림':2,'지어냄':0}},
        {doc_id:'T21-X03',loss:1,counts:{'틀림':4,'지어냄':1}}];
      top.counts={'틀림':6,'지어냄':4,'빠뜨림':9};
      await go('s01');const jumps=[];go=async(id,args)=>jumps.push({id,args});
      assert.equal(el('score-open-source').textContent,T('score.problem.open_wrong',{count:6}));
      await el('score-open-source').click();
      assert.deepEqual(jumps.pop(),{id:'s02',args:{run:run.name,doc:'T21-X02',section:8,item:top.name,pick:'mismatch'}});
      top.docs.forEach(d=>d.counts['틀림']=0);scoreRenderSummary();await el('score-open-source').click();
      assert.equal(jumps.pop().args.doc,'T21-X01');
      top.docs.forEach(d=>d.counts=null);scoreRenderSummary();await el('score-open-source').click();
      assert.equal(jumps.pop().args.doc,'T21-X01');
    """)
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      view.values[1].lines=['p9:L999'];view.values[4].lines=['p2:L3'];
      await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
      assert.equal(S.source.selection.path,view.values[4].path);
      view.values[4].lines=[];await sourceLoad(true);
      await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
      assert.equal(S.source.selection.path,view.values[1].path);
      assert.ok(el('source-read-section'));assert.equal(S.journey.outcomes.t1.real,null);
    """)


def test_s01_button_and_hint_follow_the_kind_that_exists():
    from test_B_b_app_score_ui import FIXTURE
    run_js(FIXTURE + FIX_VISIBLE + r"""
      const top=run.status_text.top_problem;
      top.counts={'틀림':0,'지어냄':3,'빠뜨림':8};await go('s01');
      assert.equal(el('score-open-source').textContent,T('score.problem.open_made',{count:3}));
      assert.ok(visibleText(el('score-summary')).includes(T('score.problem.made_hint')));
      assert.ok(!visibleText(el('score-summary')).includes(T('score.problem.evidence_hint',{count:8})));
      top.counts['지어냄']=0;scoreRenderSummary();
      assert.equal(el('score-open-source').textContent,T('score.problem.open_missing',{count:8}));
      assert.ok(visibleText(el('score-summary')).includes(T('score.problem.missing_hint')));
      top.counts=null;scoreRenderSummary();
      assert.ok(visibleText(el('score-summary')).includes(T('common.legacy.cell_labels.c_none')));
      assert.ok(!visibleText(el('score-summary')).includes(T('score.problem.counts.wrong',{count:0})));
      assert.ok(visibleText(el('score-summary')).includes(T('score.problem.evidence_unrecorded')));
    """)


def test_s01_conclusion_first_and_path_on_s01_to_s03():
    from test_B_b_app_score_ui import FIXTURE
    from test_B_b_app_source_ui import fixture
    from test_B_b_app_jobs_ui import SETUP
    check = r"""
      const area=el('screen-'+S.shell.route), heading=area.querySelector('h1');
      assert.notEqual(heading.textContent,T(SHELL_SCREENS[S.shell.route].title));
      const flow=area.querySelector('.score-flow');assert.ok(flow);
      assert.deepEqual(Array.from(flow.querySelectorAll('li'),n=>n.textContent),
        ['result','cause','retest'].map(k=>T('score.flow.'+k)));
      assert.equal(flow.querySelector('[aria-current="step"]').textContent,T('score.flow.'+current));
      assert.equal(flow.querySelector('button'),null);
      const nodes=Array.from(area.querySelectorAll('*'));
      assert.ok(nodes.indexOf(flow)<nodes.indexOf(heading));
    """
    run_js(FIXTURE + "await go('s01');const current='result';" + check + r"""
      assert.equal(heading.textContent,T('score.summary.headline_model',{model:'Fake model'}));
      api=async()=>{throw new Error('Fake failure');};await scoreLoad(true);
      assert.equal(el('title-s01').textContent,T('score.load_failed.fact'));
      assert.equal(el('screen-s01').querySelector('.score-flow'),null);
    """)
    run_js(fixture() + "await go('s02',{section:8});const current='cause';" + check + r"""
      assert.equal(heading.textContent,T('source.title'));
      api=async()=>{throw new Error('Fake failure');};await sourceLoad(true);
      assert.equal(el('title-s02').textContent,T('source.load_failed.fact'));
      assert.equal(el('screen-s02').querySelector('.score-flow'),null);
    """)
    run_js(SETUP + "await go('s03',{doc:'T21-X01',section:8});const current='retest';" + check + r"""
      assert.equal(heading.textContent,T('jobs.trial.title'));
      options=makeOptions(false);await jobsLoadOptions();jobsRenderTry();
      assert.equal(el('title-s03').textContent,T('jobs.off.title'));
      optionsError=true;await jobsLoadOptions();jobsRenderTry();
      assert.equal(el('screen-s03').querySelector('.score-flow'),null);
    """)


def test_s01_target_gap_sentence_and_must_explained():
    from test_B_b_app_score_ui import FIXTURE
    run_js(FIXTURE + FIX_VISIBLE + r"""
      await go('s01');const summary=el('score-summary');
      assert.ok(visibleText(summary).includes(T('score.summary.headline_below',{line:87,gap:'4.6'})));
      assert.ok(visibleText(summary).includes(T('score.summary.must_some',{total:19,met:12})));
      assert.equal(summary.querySelectorAll('.score-bar').length,1);
      const block=summary.querySelector('.score-block');
      assert.ok(block.textContent.indexOf(T('score.summary.scope',{model:'Fake model',count:2}))<block.textContent.indexOf('82.4'));
      run.targets={weighted:{value:92,line:91,met:true},must:{total:21,met_count:21,met:true}};
      await scoreLoad(true);
      assert.ok(visibleText(summary).includes(T('score.summary.headline_met',{line:91})));
      assert.ok(visibleText(summary).includes(T('score.summary.must_all',{total:21})));
      assert.ok(!visibleText(summary).includes('4.6'));
    """)


def test_s01_no_results_hides_run_selector_and_offers_next_step():
    from test_B_b_app_score_ui import FIXTURE
    run_js(FIXTURE + FIX_VISIBLE + r"""
      S.ctx.set='empty-pack';await go('s01');
      assert.equal(el('score-run-select'),null);assert.equal(el('score-reload'),null);
      assert.equal(el('title-s01').textContent,T('score.empty.title'));
      assert.ok(visibleText(el('score-summary')).includes(T('score.empty.state')));
      assert.ok(el('score-prepare').classList.contains('primary'));
      assert.ok(!el('score-change-set').classList.contains('primary'));
      const jumps=[];go=async(id,args)=>jumps.push(id);await el('score-prepare').click();
      assert.deepEqual(jumps,['s03']);
      assert.ok(!visibleText(el('score-summary')).includes('82.4'));
    """)


def test_s02_direct_entry_starts_from_document_and_section_choice():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + FIX_VISIBLE + r"""
      view.values=Array.from({length:854},(_,i)=>({...view.values[1],path:'fake['+i+'].q'}));
      await go('s02');
      assert.equal(el('source-problem-list'),null);
      assert.ok(el('source-doc-select').closest('details').open);
      assert.ok(el('source-section-choice'));assert.equal(el('source-section-choice').value,'');
      assert.ok(visibleText(el('source-top')).includes(T('source.labels.choose_scope')));
      await change('source-section-choice','8');
      el('source-problem-list').querySelector('button').click();
      const structure=document.querySelector('[data-source-section="8"]').closest('details');
      assert.equal(structure.open,false);
      assert.ok(Array.from(el('source-selection').querySelectorAll('details')).every(d=>!d.open));
      assert.equal(document.querySelector('[data-source-section="8"]').parentElement.open,false);
      const nodes=Array.from(el('screen-s02').querySelectorAll('*'));
      assert.ok(nodes.indexOf(el('source-selection'))<nodes.indexOf(el('source-page')));
      assert.ok(nodes.indexOf(el('source-page'))<nodes.indexOf(document.querySelector('[data-source-section="8"]')));
    """)


SOURCE_GROUPS = r"""
S.score.run={...runs[1],status_text:{top_problem:{name:'Fake criterion',section:8,
 docs:[{doc_id:'T21-X01',counts:{'틀림':2}},{doc_id:'T21-X02',counts:{'틀림':1}}]}}};
const second=JSON.parse(JSON.stringify(view));second.doc_id='T21-X02';
second.values=[{...second.values[1],text:'Second document value',lines:['p1:L1']}];
second.silver_only=[];
const originalApi=api;
api=async path=>{
 if(path.startsWith('/api/doc?')&&new URLSearchParams(path.split('?')[1]).get('doc')==='T21-X02'){
   calls.push(path);return second;
 }return originalApi(path);
};
"""


def test_s02_problem_list_spans_documents_of_the_same_criterion():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + SOURCE_GROUPS + r"""
      await go('s02',{run:'current',doc:'T21-X01',section:8,item:'Fake criterion',pick:'mismatch'});
      const groups=el('source-problem-list').querySelectorAll('[data-problem-doc]');
      assert.deepEqual(Array.from(groups,g=>g.dataset.problemDoc),['T21-X01','T21-X02']);
      assert.ok(!el('source-problem-list').textContent.includes(view.values[3].path));
      const b=groups[1].querySelector('button');await b.click();
      assert.equal(S.source.data.doc_id,'T21-X02');assert.equal(S.source.item,'Fake criterion');
      assert.equal(S.source.section,8);assert.equal(S.source.selection.path,second.values[0].path);
      assert.ok(el('source-selection').textContent.includes('Second document value'));
      const selected=el('source-problem-list').querySelectorAll('[aria-pressed="true"]');
      assert.equal(selected.length,1);assert.equal(selected[0].closest('[data-problem-doc]').dataset.problemDoc,'T21-X02');
      assert.ok(calls.filter(p=>p.startsWith('/api/doc?')).every(p=>p.includes('key=gold%2Ffake')));
      el('source-filter-wrong').click();
      assert.ok(!el('source-problem-list').textContent.includes(T('source.kinds.missing')));
    """)


def test_s02_problem_list_uses_plain_field_names():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      view.ui_text.value_field_labels={comp_ref:'Fake component label',limit_type:'Fake limit label',q:'Fake numeric label'};
      view.values[0].field='comp_ref';view.values[1].field='limit_type';
      await go('s02',{section:8,item:'Fake criterion'});
      const list=el('source-problem-list'),text=list.textContent;
      assert.doesNotMatch(text,/comp_ref|limit_type|msds\[0\]|\bq\b/);
      for(const label of Object.values(view.ui_text.value_field_labels))assert.ok(text.includes(label));
      assert.equal(text.split('T21-X01').length-1,1);
      list.querySelector('button').click();
      assert.ok(el('screen-s02').textContent.includes(view.values[0].path));
    """)


def test_s02_no_evidence_line_offers_reading_the_section():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      const events=[];on('evidence_line_shown',e=>events.push(e));
      await go('s02',{section:8,item:'Fake criterion'});pick(4).click();
      assert.ok(!el('source-selection').textContent.includes(T('source.evidence.recorded')));
      const read=el('source-read-section');assert.ok(read);assert.equal(read.textContent,T('source.unlinked.read_section'));
      assert.ok(read.classList.contains('primary'));assert.ok(!el('source-retest').classList.contains('primary'));
      await read.click();assert.equal(S.source.page,2);assert.equal(events.length,0);
      pick(5,'silver_only').click();
      assert.ok(el('source-selection').textContent.includes(T('source.missing.evidence_title')));
      assert.ok(el('source-selection').textContent.includes(T('source.doc.guess')));
      assert.equal(events.length,0);assert.equal(S.journey.outcomes.t1.real,null);
      view.silver_only[0].lines=[];await sourceLoad(true);pick(5,'silver_only').click();
      assert.ok(el('source-read-section'));assert.ok(!el('source-selection').textContent.includes(T('source.doc.guess')));
      pick(1).click();assert.ok(el('source-selection').textContent.includes(T('source.evidence.recorded')));
      assert.equal(events.length,1);
    """)


def test_first_visit_band_links_both_tracks():
    from test_B_b_app_journey_ui import SETUP
    for track, text_key in [('t1', 'start_read'), ('t2', 'start_trial')]:
        run_js(SETUP + f"const desiredTrack='{track}',labelKey='{text_key}';" + r"""
          await journeyEnsure();journeyRenderBand();
          const band=el('journey-band');
          for(const key of ['start_read','start_trial'])assert.ok(band.textContent.includes(T('journey.choice.'+key)));
          const button=Array.from(band.querySelectorAll('button')).find(b=>b.textContent===T('journey.choice.'+labelKey));
          assert.ok(button);await button.click();await flush();
          assert.equal(S.journey.progress.active,desiredTrack);
          assert.equal(S.shell.route,desiredTrack==='t1'?'s01':'s03');
          assert.equal(S.journey.outcomes.t1.real,null);assert.equal(S.journey.outcomes.t2.real,null);
          assert.ok(puts.length);
        """)


def test_s02_criterion_counts_use_run_api_without_recounting_loaded_values():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + SOURCE_GROUPS + r"""
      const top=S.score.run.status_text.top_problem;
      top.counts_basis='field';top.counts={'빠뜨림':17,'틀림':11,'지어냄':9};
      await go('s02',{run:'current',doc:'T21-X01',section:8,item:'Fake criterion',pick:'mismatch'});
      for(const [kind,count] of [['missing',17],['wrong',11],['made',9]])
        assert.equal(el('source-filter-'+kind).textContent,T('source.filter.'+kind,{count}));
      top.counts=null;sourceRenderProblems();
      assert.ok(el('source-values').textContent.includes(T('common.legacy.cell_labels.c_none')));
      assert.ok(!el('source-filter-wrong').textContent.includes('0'));
    """)


def test_s02_late_document_click_does_not_replace_new_key_selection():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + SOURCE_GROUPS + r"""
      await go('s02',{run:'current',doc:'T21-X01',section:8,item:'Fake criterion',pick:'mismatch'});
      const upstream=api;let releaseOld;
      api=async path=>{
        const p=new URLSearchParams(path.split('?')[1]);
        if(p.get('doc')==='T21-X01'&&p.get('key')==='gold/fake')
          return new Promise(resolve=>{releaseOld=()=>resolve({...view,doc_id:'T21-X01'});});
        return upstream(path);
      };
      const pendingPick=sourcePickProblem('T21-X02',second.values[0],false);await flush();
      assert.equal(typeof releaseOld,'function');S.ctx.key='gold/new';
      second.values.push({...second.values[0],path:'new-answer-value',text:'New choice'});
      await sourceLoad(true);sourcePick(S.source.values['new-answer-value']);
      releaseOld();await pendingPick;
      assert.equal(S.source.selection.path,'new-answer-value');
    """)


def test_s02_value_selection_preserves_list_scroll_and_visible_focus():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      await go('s02',{section:8,item:'Fake criterion'});
      el('source-problem-list').scrollTop=120;
      el('source-problem-list').querySelector('button').click();
      assert.equal(el('source-problem-list').scrollTop,120);
      assert.equal(document.activeElement.closest('[data-problem-doc]').dataset.problemDoc,'T21-X01');
      const section=document.querySelector('[data-source-section="8"]');
      const outer=section.parentElement;outer.open=true;outer.dispatchEvent({type:'toggle'});
      section.open=true;section.dispatchEvent({type:'toggle'});
      const table=section.querySelector('details');table.open=true;table.dispatchEvent({type:'toggle'});
      const same=pick(2);same.focus();same.click();
      assert.ok(document.activeElement.isConnected);assert.equal(document.activeElement.dataset.sourcePath,view.values[2].path);
    """)


def test_s02_late_initial_problem_selection_does_not_replace_new_key_selection():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + SOURCE_GROUPS + r"""
      const upstream=api;let releaseOld;
      api=async path=>{
        const p=new URLSearchParams(path.split('?')[1]);
        if(p.get('doc')==='T21-X02'&&p.get('key')==='gold/fake')
          return new Promise(resolve=>{releaseOld=()=>resolve(second);});
        return upstream(path);
      };
      const opening=go('s02',{run:'current',doc:'T21-X01',section:8,item:'Fake criterion',pick:'mismatch'});
      await flush();assert.equal(typeof releaseOld,'function');S.ctx.key='gold/new';
      view.values.push({...view.values[1],path:'new-answer-value',text:'New choice'});
      await sourceLoad(true);sourcePick(S.source.values['new-answer-value']);
      releaseOld();await opening;assert.equal(S.source.selection.path,'new-answer-value');
    """)


def test_s02_key_change_refreshes_counts_when_run_response_finishes_later():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + SOURCE_GROUPS + r"""
      S.score.run.key={id:'gold/fake'};
      S.score.run.status_text.top_problem.counts={'빠뜨림':4,'틀림':3,'지어냄':2};
      await go('s02',{run:'current',doc:'T21-X01',section:8,item:'Fake criterion'});
      const next=JSON.parse(JSON.stringify(S.score.run));next.key={id:'gold/new'};
      next.status_text.top_problem.counts={'빠뜨림':12,'틀림':8,'지어냄':5};
      let release;scoreLoad=()=>{S.score.run=null;S.score.pending=new Promise(resolve=>release=()=>{S.score.run=next;resolve();});return S.score.pending;};
      S.ctx.key='gold/new';emit('context_changed');await S.source.pending;
      release();await flush();
      assert.equal(el('source-filter-wrong').textContent,T('source.filter.wrong',{count:8}));
      assert.equal(el('source-problem-list').querySelectorAll('[data-problem-doc]').length,2);
    """)


def test_s02_choosing_another_section_clears_the_previous_value():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      await go('s02',{section:8,item:'Fake criterion',pick:'mismatch'});
      assert.ok(S.source.selection);
      await change('source-section-choice','12');
      assert.equal(S.source.section,12);assert.equal(S.source.item,null);
      assert.equal(S.source.selection,null);assert.equal(S.source.selectedLines.size,0);
      assert.ok(!el('source-selection').textContent.includes('8 fake-unit'));
    """)
