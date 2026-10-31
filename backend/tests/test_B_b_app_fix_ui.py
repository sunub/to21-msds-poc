"""S5 사실 표시와 작업 차단 회귀. 가짜 문서·응답·시계만 사용한다."""
import pytest

from test_B_b_app_dom import run_js


def test_s06_recommended_server_and_two_way_comparison_first():
    from test_B_b_app_servers_ui import FIXTURE
    run_js(FIXTURE + FIX_VISIBLE + r"""
      data.session=null;data.models[1].reachable=false;data.models[1].match=false;
      await setup();const page=view(),company=document.getElementById('servers-rngd');
      const visible=visibleText(page),comparison=document.getElementById('servers-comparison');
      assert.ok(comparison,'both choices must be compared before opening the alternative');
      const order=page.querySelectorAll('*');assert.ok(order.indexOf(action('rngd_up')) < order.indexOf(comparison));
      assert.equal(action('rngd_up').classList.contains('primary'),true);
      assert.equal(company.closest('details'),null);
      const rows=comparison.querySelectorAll('tbody tr');assert.equal(rows.length,2);
      for(const key of ['servers.compare.company.wait','servers.compare.rented.wait','servers.empty.new_cost'])
        assert.ok(visibleText(comparison).includes(T(key)));
      assert.ok(visibleText(comparison).includes('$2.50'));
      const alternate=document.getElementById('servers-runpod').querySelector('details');
      assert.ok(alternate);assert.equal(alternate.open,false);
      assert.equal(alternate.querySelector('summary').textContent,T('servers.company.alternative'));
      assert.ok(!visible.includes(T('servers.rented.confirm_create')));
      const diagnostics=document.getElementById('servers-models').querySelector('details');
      assert.ok(diagnostics);assert.equal(diagnostics.open,false);
      assert.ok(!visible.includes(T('servers.connection.expected')));
      alternate.open=true;await shellPollServers();
      assert.equal(document.getElementById('servers-runpod').querySelector('details').open,true);
      data.rngd.tunnel.open=false;data.can.tunnel_open=true;data.rngd.diagnosis='tunnel_closed';await shellPollServers();
      assert.ok(action('tunnel_open').classList.contains('primary'));
      assert.ok(!action('rngd_up').classList.contains('primary'));
      data.pods=[];await shellPollServers();
      assert.ok(visibleText(document.getElementById('servers-comparison')).includes(T('servers.rented.unknown')));
      assert.ok(!visibleText(document.getElementById('servers-comparison')).includes('$0'));
      assert.equal(calls.filter(c=>c[0]==='post').length,0);
    """)


@pytest.mark.parametrize('cost', ['3.17', '0.83'])
def test_p02_create_button_shows_hourly_cost(cost):
    from test_B_b_app_servers_ui import FIXTURE
    import json
    # The backend's present contract puts the quoted rate in summary, not in a numeric key.
    summary = f"Fake GPU. 시간당 약 ${cost}. 준비 시간 미확인."
    run_js(FIXTURE + f"const quoted={json.dumps(summary)},cost={json.dumps(cost)};" + r"""
      await setup();const original=post;let quote=quoted;
      post=async(path,body)=>path.endsWith('/propose')?{token:'priced-once',action:body.action,summary:quote,expires_in:600}:original(path,body);
      await action('pod_create').click();let confirm=document.getElementById('servers-confirm');
      assert.equal(confirm.textContent,T('servers.confirm.create.action',{cost_per_hour:cost}));
      assert.ok(confirm.textContent.includes('$'+cost));assert.equal(confirm.disabled,false);
      assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,0);
      await confirm.click();assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,1);
      for(const missing of ['No quote available',quoted+' '+quoted,'Total $99.00']) {
        quote=missing;await action('pod_create').click();confirm=document.getElementById('servers-confirm');
        assert.equal(confirm.disabled,true);assert.ok(document.getElementById('servers-confirm-blocked').textContent);
        await serversExecute(S.servers.proposal);
        assert.equal(calls.filter(c=>c[1].endsWith('/execute')).length,1);
        document.getElementById('servers-cancel').click();
      }
    """)


def test_s08_recommended_track_is_primary():
    from test_B_b_app_journey_ui import SETUP
    run_js(SETUP + FIX_VISIBLE + r"""
      await go('s08');await flush();
      const read=el('journey-start-t1'),trial=el('journey-start-t2');
      assert.ok(read.classList.contains('primary'));assert.ok(!trial.classList.contains('primary'));
      assert.equal(el('screen-s08').querySelectorAll('button.primary').length,1);
      assert.ok(read.closest('.journey-choice').textContent.includes(T('journey.choice.read_ready')));
      assert.ok(trial.closest('.journey-choice').textContent.includes(T('context.model.readiness_unknown')));
      assert.ok(trial.closest('.journey-choice').textContent.includes(T('journey.choice.trial_requires_model')));
      assert.equal(trial.closest('.journey-choice').querySelector('.journey-connection').querySelectorAll('button').length,0);
      assert.ok(trial.classList.contains('text-button'));assert.ok(el('journey-practice').classList.contains('text-button'));
      const records=el('journey-records').querySelector('details');assert.ok(records);assert.equal(records.open,false);
      assert.ok(!visibleText(el('journey-records')).includes(T('journey.history.real_success')));
      assert.ok(records.querySelector('table'));
      runData=null;await journeyLoadRuns();journeyRenderChoice();
      assert.equal(el('journey-start-t1').disabled,true);
      assert.ok(visibleText(el('journey-choice')).includes(T('journey.start.empty')));
      let destination;go=async(id,args)=>{destination=[id,args];};
      await el('journey-start-t2').click();assert.equal(destination[0],'s03');
      assert.equal(S.journey.outcomes.t2.real,null);
    """)


def test_s09_runnable_docs_first_and_locked_docs_grouped():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + FIX_VISIBLE + r"""
      options=makeOptions(false);
      options.sets[0].docs.unshift(...['T21-X90','T21-X91'].map(doc_id=>({doc_id,group:'eval',locked:true,
        runnable:{try:false,run:false},run_reason:{try:'EVAL LOCK',run:'EVAL LOCK'}})));
      await go('s09');const form=el('jobs-run'),checks=form.querySelectorAll('input[type="checkbox"]');
      assert.equal(checks[0].id,'jobs-run-doc-RAW-FAKE');assert.equal(checks[0].disabled,false);
      assert.equal(el('jobs-run-doc-T21-X02').disabled,false);
      const locked=el('jobs-run-locked');assert.ok(locked);
      assert.ok(locked.textContent.includes('T21-X90'));assert.ok(locked.textContent.includes('T21-X91'));
      assert.equal(locked.textContent.split('EVAL LOCK').length-1,1);
      assert.ok(locked.textContent.includes(T('jobs.batch.eval_locked',{count:2})));
      assert.equal(form.textContent.split('EVAL LOCK').length-1,1);
      assert.ok(form.textContent.indexOf(T('jobs.form.count',{count:2,repeats:1}))<form.textContent.indexOf('EVAL LOCK'));
      assert.ok(form.textContent.includes('RUN LOCK'));assert.ok(!form.textContent.includes('NOT RUN REASON'));
      await el('jobs-select-all').click();assert.deepEqual([...S.jobs.r.docs],['RAW-FAKE','T21-X02']);
      const prepare=form.querySelectorAll('button').find(b=>b.textContent===T('context.prepare_model'));
      assert.ok(prepare);let dest;const normalGo=go;go=async(id,args)=>{dest=[id,args];};await prepare.click();
      assert.equal(dest[0],'s06');assert.equal(dest[1].returnScreen,'s09');assert.equal(dest[1].model,'first');go=normalGo;
      options=JSON.parse(JSON.stringify(options));options.models[0].connected=true;await jobsPoll();await el('jobs-run-start').click();
      assert.deepEqual(posted[0].body.docs,['RAW-FAKE','T21-X02']);
      assert.equal(posted[0].body.set,'pack');
    """)


def test_p01_compares_current_and_candidate_and_keeps_apply_visible():
    from test_B_b_app_shell_ui import FIXTURES
    from test_B_b_app_dom import STATIC
    import re
    run_js(FIXTURES + FIX_VISIBLE + r"""
      sets.sets[0].counts={dev:1,eval_locked:0,outside:0};keys.keys[0].kind='silver';keys.keys[1].kind='gold';
      sets.sets[1].docs=[{doc_id:'RAW-X01',locked:false},{doc_id:'RAW-X02',locked:false}];
      sets.sets[1].counts={dev:0,eval_locked:0,outside:2};keys.keys[1].docs=['RAW-X01'];
      sets.sets.push({id:'unnumbered',label:'No line numbers',usable:false,reason:'No line ids'},
        {id:'empty',label:'Empty folder',usable:false,reason:'No document folders'});
      await start();shellOpenContext();const d=document.getElementById('context-picker');
      const compare=document.getElementById('context-comparison');assert.ok(compare);
      assert.ok(compare.textContent.includes(T('common.current')));assert.ok(compare.textContent.includes(T('common.candidate')));
      const candidates=document.getElementById('context-candidates');assert.ok(candidates);assert.equal(candidates.open,false);
      const apply=document.getElementById('context-apply'),body=document.getElementById('context-picker-body');
      assert.ok(body);assert.equal(body.contains(apply),false);assert.equal(apply.closest('dialog'),d);
      assert.ok(visibleText(d).includes(T('context.picker.effect_key')));
      for(const [id,values] of [['context-set',['locked','unnumbered','empty']],['context-key',['gold/empty']]])
        for(const value of values) {const opt=document.getElementById(id).querySelector('[value="'+value+'"]');assert.equal(opt.disabled,true);}
      assert.ok(document.getElementById('context-set').querySelector('[value="unnumbered"]').textContent.includes('No line ids'));
      assert.ok(document.getElementById('context-key').querySelector('[value="gold/empty"]').textContent.includes('No answer files'));
      assert.equal(document.getElementById('context-key').querySelector('[value="silver/fake"]').textContent,'Draft answers');
      assert.ok(candidates.textContent.includes('No document folders'));assert.ok(candidates.textContent.includes('No line ids'));
      assert.ok(candidates.textContent.includes('No answer files'));assert.ok(d.textContent.includes(keys.keys[0].updated_at));
      const set=document.getElementById('context-set'),key=document.getElementById('context-key');
      set.value='.';set.dispatchEvent({type:'change'});key.value='gold/fake';key.dispatchEvent({type:'change'});
      const updated=document.getElementById('context-comparison');
      assert.ok(updated.textContent.includes('Development nine'));assert.ok(updated.textContent.includes('New documents'));
      assert.ok(updated.textContent.includes('1/2'));assert.ok(updated.textContent.includes('1/1'));
      assert.ok(d.textContent.includes('RAW-X02'));assert.ok(d.textContent.includes(T('common.none')));
      assert.equal(S.ctx.set,'prev/v9');assert.equal(S.ctx.key,'silver/fake');
      document.getElementById('context-cancel').click();assert.equal(S.ctx.set,'prev/v9');
    """)
    css = (STATIC / 'app.css').read_text()
    assert re.search(r'#context-picker\[open\]\s*\{[^}]*display:\s*flex', css)
    assert re.search(r'#context-picker-body\s*\{[^}]*overflow-y:\s*auto', css)
    assert re.search(r'#context-picker-body\s*\{[^}]*min-height:\s*0', css)
    assert re.search(r'#context-picker\s+\.dialog-actions\s*\{[^}]*flex-shrink:\s*0', css)


def test_sticky_header_does_not_cover_focused_controls():
    from test_B_b_app_shell_ui import FIXTURES
    from test_B_b_app_dom import STATIC
    import re
    run_js(FIXTURES + r"""
      let height=248;document.getElementById('global-context').getBoundingClientRect=()=>({height});
      await start();
      assert.ok(parseFloat(document.body.style.getPropertyValue?.('--sticky-offset'))>=248);
      height=322;shellRenderModels();
      assert.ok(parseFloat(document.body.style.getPropertyValue?.('--sticky-offset'))>=322);
      height=184;window.dispatchEvent({type:'resize'});
      assert.ok(parseFloat(document.body.style.getPropertyValue?.('--sticky-offset'))>=184);
    """)
    css = (STATIC / 'app.css').read_text()
    assert re.search(r'(?:button|:focus)[^{]*\{[^}]*scroll-margin-top:\s*var\(--sticky-offset', css)
    assert re.search(r'dialog[^{}]*\{[^}]*scroll-margin-top:\s*0', css)


def test_s06_action_failure_and_recovery_remain_visible_before_details():
    from test_B_b_app_servers_ui import FIXTURE
    run_js(FIXTURE + FIX_VISIBLE + r"""
      await setup();post=async()=>{throw new Error('Request failed');};await action('tunnel_close').click();
      assert.ok(visibleText(document.getElementById('servers-summary')).includes(T('servers.status.failure.fact')));
      api=async()=>{throw new Error('Status failed');};await shellPollServers();
      const summary=document.getElementById('servers-summary');
      assert.ok(visibleText(summary).includes(T('servers.failed.retry')));
      assert.ok(visibleText(summary).includes(T('servers.status.failure.todo')));
    """)


def test_s09_selection_summary_updates_repeats_without_replacing_input():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      await go('s09');const repeat=el('jobs-repeat');repeat.focus();input(repeat,'3');
      assert.ok(textOf('jobs-run').includes(T('jobs.form.count',{count:2,repeats:3})));
      assert.ok(!textOf('jobs-run').includes(T('jobs.form.count',{count:2,repeats:1})));
      assert.equal(el('jobs-repeat'),repeat);assert.equal(document.activeElement,repeat);
    """)


def test_s03_instruction_box_is_prefilled_with_current_instruction():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      const normal=api;let release,failPrompt=false;
      api=(path,opts)=>path.startsWith('/api/prompt')?new Promise((resolve,reject)=>{
        release=()=>failPrompt?reject(new Error('Fake prompt failure')):resolve({text:'current instruction'});
      }):normal(path,opts);
      await go('s03',{doc:'T21-X01',section:8});
      assert.ok(release,'instruction should load on entry');
      assert.ok(el('jobs-prompt-status').textContent.includes(T('jobs.form.prompt_loading')));
      assert.ok(el('jobs-prompt').getAttribute('aria-describedby').includes('jobs-prompt-status'));
      release();await S.jobs.promptPending;assert.equal(el('jobs-prompt').value,'current instruction');
      assert.equal(S.jobs.t.edit,false);assert.equal(posted.length,0);
      S.jobs.t.secs=new Set([9]);jobsRenderTry();await Promise.resolve();
      input(el('jobs-prompt'),'my edit');release();await S.jobs.promptPending;
      assert.equal(el('jobs-prompt').value,'my edit');
      await go('s03',{doc:'RAW-FAKE',section:8});await Promise.resolve();
      assert.equal(el('jobs-prompt').value,'my edit');
      S.jobs.t.edit=false;failPrompt=true;const retry=jobsLoadPrompt();release();await retry;
      assert.ok(el('jobs-prompt-status').textContent.includes('Fake prompt failure'));
      failPrompt=false;const recovered=el('jobs-load-prompt').click();release();await recovered;
      assert.equal(el('jobs-prompt').value,'current instruction');
      assert.ok(!el('jobs-prompt-status').textContent.includes('Fake prompt failure'));
    """)


def test_s03_ai_off_makes_model_setup_primary_and_practice_secondary():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      options=makeOptions(false);options.models=[{tag:'gpt',connected:false}];
      await go('s03',{doc:'T21-X01',section:8});await Promise.resolve();
      const page=el('screen-s03'),prepare=el('jobs-connection').querySelector('button');
      assert.ok(prepare.classList.contains('primary'));
      assert.ok(!el('jobs-send').classList.contains('primary'));
      assert.equal(page.querySelectorAll('button.primary').length,1);
      assert.ok(page.textContent.indexOf(T('context.prepare_model'))<page.textContent.indexOf(T('jobs.actions.preview')));
      assert.equal(page.textContent.split(T('jobs.actions.preview')).length-1,1);
      assert.ok(el('jobs-connection').textContent.includes(UI.context.models.gpt));
      let dest;go=async(id,args)=>{dest=[id,args];};await prepare.click();
      assert.equal(dest[0],'s06');assert.equal(dest[1].returnScreen,'s03');
      assert.equal(posted.length,0);
    """)


def test_s03_offline_selected_model_still_offers_practice_with_other_model_ready():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      await go('s03',{doc:'T21-X01',section:8});
      change(el('jobs-model'),'second');
      assert.equal(el('jobs-send').textContent,T('jobs.actions.preview'));
      assert.equal(el('jobs-send').disabled,false);
      await el('jobs-send').click();assert.equal(posted[0].body.dry_run,true);
      assert.equal(posted[0].body.model,'second');
    """)


def test_s03_accepted_request_focuses_result_before_slow_poll():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      await go('s03',{doc:'T21-X01',section:8});const normal=api;
      let release;api=(path,opts)=>path==='/api/options'?new Promise(resolve=>release=()=>resolve(options)):normal(path,opts);
      const region=el('jobs-result');let scrolls=0;region.scrollIntoView=()=>scrolls++;
      const sending=el('jobs-send').click();await Promise.resolve();await Promise.resolve();
      assert.equal(scrolls,1);assert.equal(document.activeElement,region);
      release();await sending;assert.equal(scrolls,1);
    """)


def test_s03_automatic_instruction_ignores_stale_targets_and_does_not_run_elsewhere():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      const normal=api,waiting=[];
      api=(path,opts)=>path.startsWith('/api/prompt')?new Promise(resolve=>waiting.push({path,resolve})):normal(path,opts);
      await go('s05');assert.equal(waiting.length,0);
      await go('s03',{doc:'T21-X01',section:8});const first=S.jobs.promptPending;
      change(el('jobs-model'),'second');const second=S.jobs.promptPending;
      assert.equal(waiting.length,2);waiting[1].resolve({text:'new model instruction'});await second;
      waiting[0].resolve({text:'old model instruction'});await first;
      assert.equal(el('jobs-prompt').value,'new model instruction');assert.equal(S.jobs.promptBusy,false);
      S.jobs.t.all=true;jobsRenderTry();assert.equal(waiting.length,2);
      S.jobs.t.all=false;S.jobs.t.doc=null;jobsRenderTry();assert.equal(waiting.length,2);
      assert.equal(posted.length,0);
    """)


def test_s03_disabling_custom_instruction_does_not_erase_the_draft():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      await go('s03',{doc:'T21-X01',section:8});await S.jobs.promptPending;
      input(el('jobs-prompt'),'keep disabled draft');change(el('jobs-edit'),false);
      const count=requests.filter(p=>p.startsWith('/api/prompt')).length;
      await go('s03',{doc:'RAW-FAKE',section:9});await S.jobs.promptPending;
      assert.equal(el('jobs-prompt').value,'keep disabled draft');
      assert.equal(requests.filter(p=>p.startsWith('/api/prompt')).length,count);
      await el('jobs-load-prompt').click();assert.equal(el('jobs-prompt').value,'fake prompt');
    """)


def test_practice_result_says_practice_done_not_done():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      listed=[job('done',{dry_run:true,target:{...target,dry_run:true}})];response={plan};
      await go('s03');await jobsWatch('j1');
      for(const id of ['jobs-result','jobs-list']) {
        const states=el(id).querySelectorAll('[data-job-status]');assert.equal(states.length,1);
        assert.equal(states[0].textContent,T('jobs.practice_done.state'));
        assert.notEqual(states[0].textContent,T('jobs.status.done'));
      }
      listed=[job('done')];response=result(true);await jobsPoll();await jobsLoadResult('j1');
      assert.equal(el('jobs-result').querySelector('[data-job-status]').textContent,T('jobs.status.done'));
      assert.equal(S.journey.outcomes.t2.real,null);
    """)


@pytest.mark.parametrize('practice', [False, True])
def test_s03_after_send_moves_focus_to_result(practice):
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + f"const practice={str(practice).lower()};" + r"""
      options=makeOptions(!practice);await go('s03',{doc:'T21-X01',section:8});
      const region=el('jobs-result');let scrolls=0;region.scrollIntoView=()=>scrolls++;
      listed=[job('running',{dry_run:practice,target:{...target,dry_run:practice}})];
      el('jobs-send').focus();await el('jobs-send').click();
      assert.equal(document.activeElement,region);assert.equal(scrolls,1);
      assert.equal(region.getAttribute('tabindex'),'-1');
      await jobsPoll();assert.equal(scrolls,1);
      post=async()=>{throw new Error('rejected');};await el('jobs-send').click();assert.equal(scrolls,1);
    """)


def test_s04_summary_separates_whole_score_and_one_criterion():
    from test_B_b_app_compare_ui import SETUP
    run_js(SETUP + r"""
      await show();const d=S.compare.data;
      d.headline={headline:'LONG A LONG B combined scopes',biggest:{name:d.items[0].name,delta:-11.6}};
      d.weighted.delta=-0.3;compareRenderAll();
      assert.equal(document.getElementById('title-s04').textContent,T('compare.same.title'));
      const total=document.getElementById('compare-total-change'),criterion=document.getElementById('compare-criterion-change');
      assert.ok(total.textContent.includes(T('compare.total_score')));assert.ok(total.textContent.includes('−0.3'));
      assert.ok(!total.textContent.includes('11.6'));
      assert.ok(criterion.textContent.includes(d.items[0].name));assert.ok(criterion.textContent.includes('−11.6'));
      assert.ok(!criterion.textContent.includes('−0.3'));
      assert.ok(!screen().textContent.includes(d.headline.headline));
      assert.ok(document.getElementById('compare-summary').querySelector('table').textContent.includes(runs[0].label.title));
      assert.equal(document.getElementById('compare-summary').textContent.split(T('compare.conditions.same')).length-1,1);
    """)


def test_s04_offers_source_of_changed_value():
    from test_B_b_app_compare_ui import SETUP
    run_js(SETUP + r"""
      await show();const item=S.compare.data.items[0].name;
      S.compare.data.changed_values[item].broken[0].path='msds[0].toxicity[0].q';compareRenderSummary();
      let dest;go=async(id,args)=>{dest=[id,args];};
      let button=document.getElementById('compare-open-source');assert.ok(button.classList.contains('primary'));
      assert.equal(button.textContent,T('compare.values.open_changed'));
      await button.click();assert.equal(dest[0],'s02');assert.equal(dest[1].run,'b');
      assert.equal(dest[1].doc,'T21-X01');assert.equal(dest[1].section,11);assert.equal(dest[1].item,item);
      assert.equal(dest[1].path,'msds[0].toxicity[0].q');
      for(const id of ['compare-build-table','compare-retry'])assert.ok(!document.getElementById(id).classList.contains('primary'));
      S.compare.data.changed_values[item].broken=[];compareRenderSummary();await document.getElementById('compare-open-source').click();
      assert.equal(dest[1].run,'a');assert.equal(dest[1].path,null);
      assert.ok(document.getElementById('compare-summary').textContent.includes(T('compare.values.path_missing')));
      S.compare.data.changed_values={};compareRenderSummary();
      assert.equal(document.getElementById('compare-open-source'),null);
      assert.ok(document.getElementById('compare-summary').textContent.includes(T('compare.values.same')));
      S.compare.data.changed_values[item]={broken:[{content:'unlinked'}]};compareRenderSummary();
      assert.ok(document.getElementById('compare-summary').textContent.includes(T('compare.values.unlinked')));
    """)


def test_s04_no_runs_shows_reason_without_pickers():
    from test_B_b_app_compare_ui import SETUP
    run_js(SETUP + r"""
      api=async()=>({runs:[]});await show();
      assert.equal(document.getElementById('title-s04').textContent,T('compare.headline.none'));
      for(const id of ['compare-a','compare-b','compare-swap','compare-retry'])assert.equal(document.getElementById(id),null);
      const next=document.getElementById('compare-summary').querySelector('button');assert.ok(next);
      let dest;go=async(id,args)=>{dest=[id,args];};await next.click();assert.equal(dest[0],'s03');
      assert.equal(calls.filter(p=>p.startsWith('/api/diff')).length,0);
    """)


def test_s05_list_is_short_and_details_show_once():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      const error={message:'Short failure',fix:'Detailed recovery',raw:'Unique raw error'};
      listed=[job('failed',{returncode:1,error,warnings:[{message:'Unique settings warning',fix:'Settings recovery'}]}),
        job('failed',{id:'j2',error})];await go('s05');
      const list=el('jobs-list');assert.equal(list.querySelectorAll('.error-note,details').length,0);
      assert.ok(list.textContent.includes('Short failure'));assert.ok(!list.textContent.includes('Detailed recovery'));
      assert.ok(!list.textContent.includes('Unique settings warning'));
      const row=list.querySelector('tbody').querySelector('tr'),state=row.querySelector('[data-job-status]');
      assert.notEqual(state.closest('td'),row.querySelector('td'));
      assert.equal(row.querySelectorAll('button').filter(b=>b.textContent===T('jobs.result_missing.open_log')).length,1);
      await el('jobs-log-j1').click();
      const detail=el('jobs-detail');for(const text of ['Unique settings warning','Unique raw error','Detailed recovery'])
        assert.equal(detail.textContent.split(text).length-1,1);
      assert.equal(detail.querySelectorAll('pre').filter(p=>p.textContent.includes('fake log')).length,1);
      S.jobs.watch='j1';await el('jobs-log-j2').click();
      assert.equal(el('jobs-list').querySelectorAll('.job-selected').length,1);
      assert.ok(el('jobs-list').querySelector('.job-selected').contains(el('jobs-log-j2')));
      await el('jobs-close-log').click();assert.equal(el('jobs-detail').textContent,'');
      assert.ok(el('jobs-list').querySelector('.job-selected'));
    """)


def test_s10_receives_two_runs_from_s04_in_order():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      S.compare.a='other';S.compare.b='base';S.compare.list=[
        {name:'base',label:{title:'Base label'},run_kind:'dev10'},
        {name:'other',label:{title:'Other label'},run_kind:'probe'}];
      S.compare.data={weighted:{a:80,b:79,delta:-1},items:[],docs:{common:[]}};compareRenderSummary();
      await el('compare-build-table').click();
      assert.deepEqual(S.jobs.c.picked,['other','base']);
      assert.equal(el('jobs-compare-label-other').value,'Other label');
      assert.equal(el('jobs-compare-label-base').value,'Base label');
      assert.equal(posted.length,0);await go('s10',{runs:['base','unknown','base','other']});
      assert.deepEqual(S.jobs.c.picked,['base','other']);
      S.jobs.runs.push({name:'locked',run_kind:'eval'});await go('s10',{runs:['locked','other']});
      assert.deepEqual(S.jobs.c.picked,['other']);assert.equal(posted.length,0);
    """)


def test_s10_selected_order_table_comes_first():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + r"""
      await go('s10',{runs:['other','base']});
      const root=el('jobs-compare'),table=el('jobs-compare-order'),candidates=el('jobs-compare-candidates');
      assert.ok(table);assert.equal(root.querySelector('table'),table);assert.equal(candidates.open,false);
      const order=()=>[...el('jobs-compare-order').querySelectorAll('[data-run]')].map(r=>r.dataset.run);
      assert.deepEqual(order(),['other','base']);
      assert.ok(root.textContent.indexOf(T('compare.table.caption'))<root.textContent.indexOf(candidates.textContent));
      assert.ok(root.textContent.indexOf(T('compare.table.create_ordered'))<root.textContent.indexOf(candidates.textContent));
      await el('jobs-compare-swap').click();assert.deepEqual(order(),['base','other']);
      input(el('jobs-compare-title'),'fake comparison');await el('jobs-compare-start').click();
      assert.deepEqual(posted[0].body.runs,['base','other']);
      S.jobs.runs.push({name:'third',label:'Third',run_kind:'probe'},{name:'locked',run_kind:'silver'});
      jobsRenderCompare();change(el('jobs-compare-pick-third'),true);
      assert.deepEqual(order(),['base','other','third']);await el('jobs-compare-up-third').click();
      assert.deepEqual(order(),['base','third','other']);
      assert.equal(el('jobs-compare-pick-locked').disabled,true);
      assert.ok(el('jobs-compare-candidates').textContent.includes(T('jobs.compare.unavailable')));
    """)


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


def _fix_copy():
    import importlib
    import sys
    from test_B_b_app_dom import STATIC
    from test_B_b_app_text import _ui_leaves
    if str(STATIC.parent) not in sys.path:
        sys.path.insert(0, str(STATIC.parent))
    module = importlib.import_module('b_app_text')
    return module, dict(_ui_leaves(module.UI_TEXT))


def test_added_copy_uses_approved_names():
    # C001–C053: 고칠 낱말과 승인된 이름 조각만 검사한다. 문장 전체는 복제하지 않는다.
    _, words = _fix_copy()
    groups = [
        ('채점', '점수', '''score.basis.label score.loading.scoring source.labels.criterion
          compare.items.name help.navigation.methods_failed help.navigation.methods_todo
          help.navigation.methods_reload help.navigation.loading compare.selection.reasons.outside
          compare.selection.reasons.unknown score.conditions.nonempty_meaning'''),
        ('목표선', '목표 점수', 'score.summary.target_line compare.target_line'),
        ('필수 {total}', '필수 기준', 'score.summary.must_progress'),
        ('무게', '비중', '''score.criteria.weight score.calculation.weight score.calculation.loss_formula
          score.calculation.weight_basis help.facts.scores'''),
        ('지시문', 'AI에게 시', '''compare.prompt.open compare.prompt.loading compare.prompt.failed
          compare.prompt.retry compare.prompt.same compare.prompt.note help.facts.run_name
          help.facts.ranking help.facts.cause_conditions help.facts.prompt_private'''),
        ('표 행 형식', '한 줄에 한 행', 'compare.prompt.rows'),
        ('항목 형식', '정해진 결과 형식', 'compare.prompt.json jobs.result.format_json'),
        ('연결 안 됨', 'AI 꺼짐', 'servers.models.off'),
        ('', 'AI 설정의 짧은 이름', 'servers.models.tag'),
        ('가중 종합', '중요도를 반영한 전체 점수', 'jobs.result.weighted'),
        ('채점', '점수를 매기는 기준', 'jobs.result.changed jobs.result.unchanged'),
        ('한 항', '한 부분', 'journey.band.trial journey.read.no_section'),
        ('첫 사용 안내', '처음 사용 안내', 'journey.band.open journey.band.resume'),
        ('재추출', 'AI에게 다시 뽑도록 요청', 'help.facts.cause_calls'),
        ('흔들림:', '같은 조건에서 생기는 결과 차이', 'help.facts.cause_variation'),
        ('입력 확인 연습', 'AI 없이 보낼 내용 확인', 'help.facts.journey_try help.facts.trial_practice'),
        ('본 실행', '여러 문서 시험', 'servers.session.active'),
        ('', '위험 문구 번호', 'source.table_names.hazard.h_statements'),
        ('', '예방 문구 번호', 'source.table_names.hazard.p_statements'),
        ('조성', '성분', 'source.table_names.composition'),
        ('CMR', '암·유전·생식 관련 독성', 'source.table_names.cmr'),
        ('생태 독성', '환경에 미치는 영향', 'source.table_names.ecotox'),
        ('물리화학적 특성', '물리·화학 성질', 'source.section_names.9'),
        ('목표선', '목표 시간', 'help.facts.slow'),
    ]
    keys = [key for _, _, group in groups for key in group.split()]
    assert len(keys) == len(set(keys)) == 53
    errors = []
    for old, approved, group in groups:
        for key in group.split():
            value = words[key]
            if (old and old in value) or approved not in value:
                errors.append((key, old, approved, value))
    assert not errors


def test_new_terms_have_plain_explanations_waiting_for_approval():
    from test_B_b_app_dom import STATIC
    module, words = _fix_copy()
    # C054–C083. 단순히 예외로 등록하는 것만으로 통과하지 않는다.
    meanings = {
        'common.raw_error': '오류 기록', 'score.load_failed.todo': '명령 입력 창',
        'compare.load_failed.todo': '명령 입력 창', 'score.calls.mode': '답을 받는 방식',
        'jobs.result.raw_meta': '답을 받는 방식', 'score.calls.limit_reason': '답변 길이 제한',
        'servers.rented.state': '서버 상태', 'servers.connection.tunnel_closed': '통로 번호',
        'servers.connection.tunnel_external': '통로 번호', 'servers.connection.tunnel_unknown': '통로 번호',
        'servers.connection.process': '실행 중인 프로그램', 'servers.connection.none': '모델 실행 프로그램',
        'servers.result.started': '모델 실행 프로그램', 'servers.result.stopped': '프로그램 번호',
        'servers.result.process_remaining': '프로그램 번호', 'jobs.record.pid': '실행 중인 프로그램',
        'jobs.record.unknown_tip': '실행 기록', 'jobs.record.close_log': '실행 기록',
        'jobs.record.log_empty': '실행 기록', 'jobs.record.exit_missing': '작업이 끝난 이유',
        'jobs.result.input_meta': '부분을 나눈 방법', 'jobs.result.input_rows': '공통 줄',
        'help.facts.cards': '상세 영역', 'help.facts.setup_copy': '코드 변경 기록 저장소',
        'help.facts.cli_command': 'AI설정이름', 'help.facts.prompt_spec': '결과 형식을 정한 문서',
        'help.facts.prompt_version': 'AI에게 시킬 일의 버전 번호', 'help.facts.limit': '길이 한도',
        'help.facts.setup_open': '명령 입력 창', 'help.facts.protect_keys': '실행 기록',
    }
    assert len(meanings) == 30
    table = (STATIC / 'design/BUILD.md').read_text().split('### ⑤ 승인 대기 문구\n', 1)[1].split('\n### ', 1)[0]
    errors = []
    for key, meaning in meanings.items():
        if (meaning not in words[key] or module.COPY_EXCEPTIONS.get(key) != 'S5 결정 2: ⑤ 수락에서 승인 대기'
                or f'| `{key}` |' not in table):
            errors.append(key)
    # 이전 step의 새 문장과 이번 표시 이름까지 빠짐없이 승인 표에 올린다.
    for key, reason in module.COPY_EXCEPTIONS.items():
        if reason == 'S5 결정 2: ⑤ 수락에서 승인 대기':
            assert f'| `{key}` |' in table, key
            assert words[key].replace('\n', '<br>').replace('|', '&#124;') in table, key
    assert not errors


def _fix_css_rules():
    import re
    from test_B_b_app_dom import STATIC
    css = re.sub(r'/\*.*?\*/', '', (STATIC / 'app.css').read_text(), flags=re.S)
    return css, re.findall(r'([^{}]+)\{([^{}]*)\}', css)


def test_only_approved_colors_carry_meaning():
    import re
    from test_B_b_app_dom import STATIC
    css, rules = _fix_css_rules()
    design = (STATIC / 'DESIGN.md').read_text()
    palette = set(re.findall(r'#[0-9a-fA-F]{6}\b', design))
    assert set(re.findall(r'#[0-9a-fA-F]{6}\b', css)) <= palette
    for name in ('.score-below', '.compare-down', '.source-missing .source-cell-state'):
        colors = [re.search(r'color:\s*([^;]+)', body).group(1).strip()
                  for selectors, body in rules if name in selectors.split(',') or name in [s.strip() for s in selectors.split(',')]
                  if re.search(r'color:\s*([^;]+)', body)]
        assert colors and colors[-1] in {'var(--muted)', 'var(--ink)'}, (name, colors)
    for selectors, body in rules:
        if 'var(--failure)' in body and selectors.strip() != ':root':
            assert all('error' in s or 'fail' in s for s in selectors.split(',')), selectors
    module, _ = _fix_copy()
    assert all(entry['color'] in palette for entry in module.doc_legend())
    # 오류와 값 차이의 색을 혼동하지 않는다. 상태 글은 그대로 보인다.
    run_js(r"""
      const low=scoreCall(8,{ok:false,mode:'json_schema'});
      assert.ok(low.classList.contains('c_fail'));assert.ok(low.textContent.includes(T('common.legacy.cell_labels.c_fail')));
    """)


def test_input_border_contrast_at_least_3_to_1():
    import re
    from test_B_b_app_dom import STATIC
    css, _ = _fix_css_rules()
    tokens = dict(re.findall(r'--([\w-]+):\s*(#[0-9a-fA-F]{6})', css))
    def luminance(value):
        rgb = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
    def contrast(a, b):
        light, dark = sorted([luminance(a), luminance(b)], reverse=True)
        return (light + .05) / (dark + .05)
    color = tokens['input-line']
    assert contrast(color, '#ffffff') >= 3
    assert contrast(color, tokens['ground']) >= 3
    design = (STATIC / 'DESIGN.md').read_text()
    assert re.search(r'^  input-line: "' + color + '"$', design, re.M)
    assert re.search(r'^  input: "1px solid ' + color + '"$', design, re.M)


def test_focus_ring_only_on_controls():
    import re
    css, rules = _fix_css_rules()
    focus = [selector.strip() for selector, body in rules if ':focus-visible' in selector and 'outline:' in body]
    assert focus
    assert not re.search(r'outline:\s*(none|0)([^.0-9]|$)', css)
    # 한정된 조작 요소 목록. tabindex=-1 제목까지 잡는 범용 선택자는 허용하지 않는다.
    allowed = {'button', 'a[href]', 'input', 'select', 'textarea', 'summary', '[tabindex="0"]'}
    seen = set()
    for selector in focus:
        # 쉼표별 :focus-visible 또는 :is(요소 목록):focus-visible 두 표기를 받는다.
        match = re.fullmatch(r':is\((.*)\):focus-visible', selector)
        parts = match.group(1).split(',') if match else selector.replace(':focus-visible', '').split(',')
        seen.update(part.strip() for part in parts)
    assert seen <= allowed
    assert {'button', 'a[href]', 'input', 'select', 'textarea', 'summary', '[tabindex="0"]'} <= seen


def test_machine_values_use_plain_labels_and_keep_original_details():
    from test_B_b_app_jobs_ui import SETUP
    run_js(SETUP + FIX_VISIBLE + r"""
      const modes=['json_schema','json_schema_compact','json_object','none','rows','nuextract_template'];
      for(const mode of modes){
        const cell=scoreCall(8,{ok:true,mode,limit_kind:'공백폭주',seconds:1,attempts:1});
        cell.open=true;const shown=visibleText(cell);
        assert.ok(shown.includes(T('common.codes.mode.'+mode)));
        assert.ok(shown.includes(T('common.codes.limit.whitespace')));
        assert.ok(!shown.includes(mode));assert.ok(!shown.includes('공백폭주'));
        const raw=cell.querySelector('.code-record');assert.ok(raw);assert.equal(raw.open,false);
        assert.ok(raw.textContent.includes(mode));assert.ok(raw.textContent.includes('공백폭주'));
      }
      await go('s03',{doc:'T21-X01',section:8});await el('jobs-send').click();
      response={plan:{doc_id:'T21-X01',model_tag:'first',msds_count:1,sections_method:'provisional',sections:{'8':{
        method:'fallback',lines:2,preamble_lines:1,first:'p1:L1',last:'p1:L2',pages:[1],images:[],rows:false}}},
        results:{'8':{ok:true,mode:'json_schema',finish_reason:'length',seconds:1,raw_text:'fake',parsed:{}}}};
      listed=[job('done')];await jobsPoll();const inputStage=el('jobs-stage-j1-0'),answer=el('jobs-stage-j1-2');
      for(const section of [inputStage,answer])section.open=true;
      assert.ok(visibleText(inputStage).includes(T('common.codes.split.provisional')));
      assert.ok(visibleText(inputStage).includes(T('common.codes.split.fallback')));
      assert.ok(visibleText(answer).includes(T('common.codes.finish.length')));
      assert.ok(!visibleText(answer).includes('json_schema'));
      assert.ok(answer.querySelector('.code-record').textContent.includes('json_schema'));
      assert.ok(answer.querySelector('.code-record').textContent.includes('length'));
      assert.equal(coreCodeLabel('mode','future_mode'),T('common.codes.unknown'));
      assert.equal(coreCodeLabel('mode',null),T('common.none'));
    """)


def test_server_state_has_plain_label_and_raw_state_in_detail():
    from test_B_b_app_servers_ui import FIXTURE
    run_js(FIXTURE + FIX_VISIBLE + r"""
      await setup();
      for(const state of ['RUNNING','EXITED','FUTURE_STATE']){
        data.pods[0].state=state;await shellPollServers();
        const table=document.getElementById('servers-runpod');table.querySelector('details').open=true;
        const label=state==='FUTURE_STATE'?T('common.codes.unknown'):T('common.codes.pod.'+state);
        assert.ok(visibleText(table).includes(label));assert.ok(!visibleText(table).includes(state));
        const raw=table.querySelector('.code-record');assert.ok(raw);assert.equal(raw.open,false);
        assert.ok(raw.textContent.includes(state));
      }
    """)


def test_value_details_and_error_records_have_distinct_names():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      await go('s02',{run:'current',doc:'T21-X01',section:8});pick(1).click();
      const details=document.querySelector('.source-raw');assert.ok(details);
      assert.equal(details.querySelector('summary').textContent,T('source.labels.raw_value'));
      assert.notEqual(T('source.labels.raw_value'),T('common.raw_error'));
      assert.equal(rawError('fake').querySelector('summary').textContent,T('common.raw_error'));
    """)
