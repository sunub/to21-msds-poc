"""두 실행 비교의 실제 조작을 가짜 API와 DOM으로 확인한다. 서버는 부르지 않는다."""
from test_B_b_app_dom import run_js


SETUP = r"""
const diff = () => ({a:{name:'a'},b:{name:'b'},same_conditions:true,
  headline:{headline:'서버가 만든 비교 결론'},
  conditions:[{what:'모델',a:'fake-model',b:'fake-model',changed:false},
    {what:'안내문 버전',a:'s7',b:'s7',changed:false},
    {what:'입력 판',a:'data/pages/fake',b:'data/pages/fake',changed:false},
    {what:'동시 호출',a:16,b:16,changed:false},{what:'코드 커밋',a:'abc',b:'abc',changed:false}],
  prompt_changed_sections:[],docs:{common:['T21-X01'],only_a:[],only_b:[]},
  weighted:{a:80,b:77,delta:-3},weighted_na_excluded:{a:81,b:78,delta:-3},
  targets:{a:{weighted:{line:88,value:80,met:false},must:{total:12,met_count:7,met:false}},
    b:{weighted:{line:88,value:77,met:false},must:{total:12,met_count:6,met:false}}},
  items:[{name:'11항 급성독성',level:'필수',delta:-3,a:80,b:77,sections:[11]},
    {name:'8항 노출기준',level:'필수',delta:2,a:80,b:82,sections:[8]},
    {name:'동일 기준',delta:0,a:80,b:80,sections:[]},
    {name:'미채점 기준',delta:null,a:null,b:null,sections:[]}],
  causes:[{item:'11항 급성독성',reasons:['가짜 원인 첫째','가짜 원인 둘째']}],
  changed_values:{'11항 급성독성':{fixed:[{doc_id:'T21-X01',kind:'틀림',content:'고친 가짜 값'}],
    broken:[{doc_id:'T21-X01',kind:'틀림',content:'새로 틀린 가짜 값'}]}},
  rows:{toxicity:{a:4,b:2,gold:5}},key:{id:'silver/fake',label:'가짜 정답',fingerprint:'abcdef'}});
const runs = [{name:'a',label:{title:'가짜 이전 실행'},kind:'run',run_kind:'dev10',comparable:true,
    weighted:80,set:{id:'fake'},docs:['T21-X01']},
  {name:'probe',label:{title:'가짜 단건 실행'},kind:'run',run_kind:'single',comparable:false,weighted:70,set:{id:'fake'}},
  {name:'b',label:{title:'가짜 최근 실행'},kind:'run',run_kind:'dev10',comparable:true,weighted:77,set:{id:'fake'},docs:['T21-X01']},
  {name:'silver',label:{title:'가짜 정답 생성'},kind:'run',run_kind:'silver',comparable:false,weighted:100,set:{id:'fake'}},
  {name:'eval',label:{title:'평가 기록'},kind:'run',run_kind:'eval',comparable:false},
  {name:'models',label:{title:'표 파일'},kind:'models',run_kind:'models',comparable:false}];
S.ctx={version:1,set:'fake',key:'silver/fake'}; S.shell.contextLoaded=true;
S.shell.route='s04'; S.score.name='b';
const calls=[];
api=async path=>{calls.push(path);if(path.startsWith('/api/runs')) return {runs,current:'b'};
  if(path.startsWith('/api/diff')) return diff();throw Error('Unexpected API '+path);};
const show=async()=>{await compareEnsure(); compareRenderAll();};
const screen=()=>document.getElementById('screen-s04');
const clickText=(el,text)=>{const b=el.querySelectorAll('button').find(b=>b.textContent===text);assert.ok(b,text);b.click();return b;};
"""


def test_short_headline_precedes_conditions_and_all_deltas_are_neutral():
    run_js(SETUP + r"""
      await show();const el=screen(),head=el.querySelector('.compare-headline');
      assert.equal(head.textContent,T('compare.same.title'));
      assert.ok(el.textContent.indexOf(head.textContent)<el.textContent.indexOf(T('compare.conditions.same')));
      assert.ok(el.textContent.includes(T('compare.conditions.variation')));
      assert.equal(el.querySelectorAll('.compare-up,.compare-down,.diff-up,.diff-down').length,0);
      assert.ok(head.classList.contains('compare-neutral'));
      assert.ok(el.textContent.indexOf(head.textContent)<el.textContent.indexOf(T('compare.selection.expand')));
      assert.ok(el.textContent.includes(T('compare.must_met',{met:6,total:12})));
      assert.ok(el.textContent.includes('88'));assert.ok(el.textContent.includes('가짜 정답'));
      assert.doesNotMatch(el.textContent,/null|undefined|⟦/);
    """)


def test_changed_conditions_have_separate_lines_and_direction_with_text():
    run_js(SETUP + r"""
      await show();const d=diff();d.same_conditions=false;
      d.conditions[0]={what:'모델',a:'one',b:'two',changed:true};
      d.conditions[2]={what:'입력 판',a:'old',b:'new',changed:true};
      S.compare.data=d;
      for(const [delta,cls,key] of [[-3,'compare-down','decreased'],[2,'compare-up','increased'],[0,'compare-neutral','same'],[null,'compare-neutral','unknown']]){
        d.weighted.delta=delta;compareRenderAll();
        assert.ok(screen().querySelector('.compare-headline').classList.contains(cls));
        assert.ok(screen().textContent.includes(T('compare.criteria.'+key)));
      }
      const changed=screen().querySelectorAll('.compare-condition-change');
      assert.equal(changed.length,2);assert.ok(changed[0].textContent.includes('one → two'));
      assert.ok(changed[1].textContent.includes('old → new'));
      assert.ok(screen().textContent.includes(T('compare.interpretation.causality')));
      assert.doesNotMatch(screen().textContent,/null|undefined|⟦/);
    """)


def test_filter_sort_keeps_all_rows_hidden_count_and_candidate_reasons():
    run_js(SETUP + r"""
      await show();const before=JSON.stringify(S.compare.data.items);
      const el=document.getElementById('compare-items');
      assert.ok(el.textContent.includes(T('compare.items.hidden',{count:3})));
      assert.equal(el.querySelectorAll('[data-item]').length,1);
      clickText(el,T('compare.items.show_causes'));
      assert.ok(el.textContent.indexOf(T('compare.items.candidate'))<el.textContent.indexOf('가짜 원인 첫째'));
      assert.ok(el.textContent.indexOf('가짜 원인 첫째')<el.textContent.indexOf('가짜 원인 둘째'));
      clickText(el,T('compare.items.show_all'));
      assert.equal(el.querySelectorAll('[data-item]').length,4);
      const sort=document.getElementById('compare-sort');sort.value='up';sort.dispatchEvent({type:'change'});
      assert.equal(el.querySelector('[data-item]').dataset.item,'8항 노출기준');
      clickText(el,T('compare.items.show_drops'));assert.equal(el.querySelectorAll('[data-item]').length,1);
      assert.equal(JSON.stringify(S.compare.data.items),before);
    """)


def test_empty_filter_can_restore_unscored_and_positive_items():
    run_js(SETUP + r"""
      await show();S.compare.data.items=S.compare.data.items.slice(1);compareRenderAll();
      const el=document.getElementById('compare-items');assert.ok(el.textContent.includes(T('compare.items.empty')));
      clickText(el,T('compare.items.show_all'));assert.equal(el.querySelectorAll('[data-item]').length,3);
      assert.ok(el.textContent.includes('미채점 기준'));
    """)


def test_changed_values_toggle_is_button_keeps_focus_and_both_lists():
    run_js(SETUP + r"""
      await show();const el=document.getElementById('compare-values');
      let row=el.querySelector('.compare-value-toggle');assert.equal(row.tagName,'button');
      row.focus();row.click();row=el.querySelector('.compare-value-toggle');
      assert.equal(row.getAttribute('aria-expanded'),'true');assert.equal(document.activeElement,row);
      assert.ok(el.textContent.includes('고친 가짜 값'));assert.ok(el.textContent.includes('새로 틀린 가짜 값'));
      assert.ok(el.textContent.includes(T('compare.values.scope')));
      row.click();assert.equal(row.getAttribute('aria-expanded'),'false');assert.equal(document.activeElement,row);
      S.compare.data.changed_values['11항 급성독성'].broken=[];compareRenderValues();
      el.querySelector('.compare-value-toggle').click();
      assert.ok(el.textContent.includes(T('compare.values.wrong_count',{total:0,shown:0})));
      assert.doesNotMatch(el.textContent,/null|undefined|⟦/);
    """)


def test_value_source_link_uses_exact_path_when_present_and_honest_section_fallback():
    run_js(SETUP + r"""
      await show();const destinations=[];go=(id,args)=>{destinations.push([id,args]);return Promise.resolve();};
      S.compare.data.changed_values['11항 급성독성'].broken[0].path='msds[0].toxicity[0].q';
      compareRenderValues();const el=document.getElementById('compare-values');el.querySelector('.compare-value-toggle').click();
      const links=el.querySelectorAll('.compare-source');assert.equal(links.length,2);
      await links[0].click();await links[1].click();
      assert.equal(destinations[0][0],'s02');assert.equal(destinations[0][1].run,'a');
      assert.equal(destinations[0][1].section,11);assert.equal(destinations[0][1].path,null);
      assert.equal(destinations[1][1].run,'b');assert.equal(destinations[1][1].doc,'T21-X01');
      assert.equal(destinations[1][1].path,'msds[0].toxicity[0].q');
      assert.ok(el.textContent.includes(T('compare.values.path_missing')));
    """)


def test_grouped_selection_reasons_and_default_pair_skip_other_kinds():
    run_js(SETUP + r"""
      await show();assert.equal(S.compare.a,'a');assert.equal(S.compare.b,'b');
      const el=screen(),select=document.getElementById('compare-a');
      assert.equal(select.querySelectorAll('optgroup').length,5);
      const option=n=>select.querySelectorAll('option').find(x=>x.value===n);
      assert.equal(option('probe').disabled,false);
      for(const name of ['silver','models','eval'])assert.equal(option(name).disabled,true);
      assert.ok(option('probe').textContent.includes('가짜 단건 실행'));
      assert.ok(option('probe').textContent.includes(T('compare.selection.reasons.single')));
      assert.ok(el.textContent.includes(T('compare.selection.reasons.silver')));
      const wanted={a:'b',b:'a'};await compareEnsure(wanted);assert.equal(S.compare.a,'b');assert.equal(S.compare.b,'a');
      await document.getElementById('compare-swap').click();assert.equal(S.compare.a,'a');assert.equal(S.compare.b,'b');
    """)


def test_key_changes_reload_and_late_old_response_cannot_replace_new_result():
    run_js(SETUP + r"""
      await show();assert.ok(calls.some(p=>p.startsWith('/api/diff?')&&new URLSearchParams(p.split('?')[1]).get('key')==='silver/fake'));
      let oldResolve;api=async path=>{calls.push(path);if(path.startsWith('/api/runs'))return {runs,current:'b'};
        if(path.includes('silver%2Ffake')) return new Promise(r=>{oldResolve=r;});
        const d=diff();d.headline.headline='새 정답으로 읽은 비교';d.key.label='New fake key';return d;};
      const old=compareLoad(true);await Promise.resolve();await Promise.resolve();
      S.ctx.key='gold/fake';emit('context_changed',{...S.ctx});await S.compare.pending;
      assert.ok(calls.some(p=>p.startsWith('/api/diff?')&&p.includes('gold%2Ffake')));
      oldResolve(diff());await old;assert.equal(S.compare.data.headline.headline,'새 정답으로 읽은 비교');
      assert.ok(screen().textContent.includes('New fake key'));
      assert.equal(document.getElementById('compare-summary').querySelector('.compare-basis').textContent,T('compare.basis',{key:'New fake key'}));
    """)


def test_prompt_is_lazy_cached_per_pair_and_failure_has_fact_action_raw_retry():
    run_js(SETUP + r"""
      await show();assert.equal(calls.filter(p=>p.startsWith('/api/prompt_diff')).length,0);
      let bad=true;api=async path=>{calls.push(path);if(!path.startsWith('/api/prompt_diff'))throw Error(path);
        if(bad)throw Error('<fake prompt failure>');
        return {section:11,a_lines:2,b_lines:3,a_hash:'now-a',b_hash:'now-b',recorded:{a:'old-a',b:'now-b'},
          rows:[true,false],same:false,diff:'--- A\n+++ B\n@@ fake @@\n-old <unsafe>\n+new'};};
      const el=document.getElementById('compare-prompts');let btn=el.querySelector('[data-section="11"]');
      btn.focus();await btn.click();
      const err=el.querySelector('.error-note');assert.ok(err.querySelector('strong').textContent);
      assert.ok(err.textContent.includes(T('common.todo',{action:''})));
      assert.equal(err.querySelector('details').open,false);assert.equal(err.querySelector('pre').textContent,'<fake prompt failure>');
      bad=false;await el.querySelector('.compare-prompt-retry').click();
      assert.ok(el.textContent.includes(T('compare.hash_mismatch.title')));
      assert.ok(el.textContent.includes('old-a'));assert.ok(el.textContent.includes('now-a'));
      assert.ok(el.textContent.includes(T('compare.prompt.rows')));assert.ok(el.textContent.includes(T('compare.prompt.json')));
      assert.equal(el.querySelector('unsafe'),null);assert.ok(el.textContent.includes('-old <unsafe>'));
      const count=calls.length;btn=el.querySelector('[data-section="11"]');await btn.click();await btn.click();assert.equal(calls.length,count);
      assert.doesNotMatch(el.textContent,/null|undefined|⟦/);
    """)


def test_error_keeps_selection_hides_stale_scores_and_recovers():
    run_js(SETUP + r"""
      await show();const good=api;api=async()=>{throw Error('<fake load error>');};
      await compareLoad(true);assert.equal(S.compare.a,'a');assert.equal(S.compare.b,'b');
      assert.equal(S.compare.data,null);assert.equal(screen().querySelector('.compare-headline'),null);
      const err=screen().querySelector('.error-note');assert.ok(err);assert.equal(err.querySelector('details').open,false);
      assert.ok(err.textContent.includes(T('compare.load_failed.fact')));
      api=good;await document.getElementById('compare-retry').click();assert.ok(S.compare.data);
    """)


def test_different_document_sets_lead_conclusion_and_prompt_changes_remain_visible():
    run_js(SETUP + r"""
      await show();S.compare.data.same_conditions=false;S.compare.data.docs.only_a=['T21-X02'];
      S.compare.data.prompt_changed_sections=[11];compareRenderAll();
      const el=screen(),headline=el.querySelector('.compare-headline').textContent;
      assert.equal(headline,T('compare.different.title'));
      assert.ok(el.textContent.includes('T21-X01'));assert.ok(el.textContent.includes('T21-X02'));
      assert.ok(el.textContent.includes(T('compare.different.no_inference')));
      assert.ok(el.textContent.includes(T('compare.conditions.prompt_text')));
      assert.ok(el.textContent.includes('11'));
      assert.equal(calls.filter(p=>p.startsWith('/api/prompt_diff')).length,0);
    """)


def test_missing_metadata_targets_and_empty_runs_remain_unknown_not_zero():
    run_js(SETUP + r"""
      await show();S.compare.data={same_conditions:null,conditions:[],headline:{headline:'미채점 비교'},items:[],rows:{},docs:{},key:null};
      compareRenderAll();assert.doesNotMatch(screen().textContent,/null|undefined|⟦|90|17/);
      assert.ok(screen().textContent.includes(T('compare.conditions.unknown')));
      api=async()=>({runs:[],current:null});await compareLoad(true);
      assert.equal(S.compare.data,null);assert.ok(screen().textContent.includes(T('compare.headline.none')));
    """)


def test_rows_keep_all_counts_and_direction_is_neutral_for_repeat():
    run_js(SETUP + r"""
      await show();const el=document.getElementById('compare-rows');
      assert.ok(el.textContent.includes('4'));assert.ok(el.textContent.includes('2'));assert.ok(el.textContent.includes('5'));
      assert.equal(el.querySelectorAll('.compare-down,.compare-up').length,0);
      assert.ok(el.textContent.includes(T('compare.rows.farther')));
      S.compare.data.same_conditions=false;compareRenderRows();assert.ok(el.querySelector('.compare-down'));
    """)


def test_score_history_navigation_and_compare_table_link_preserve_order():
    run_js(SETUP + r"""
      await go('s04',{a:'b',b:'a'});assert.equal(S.compare.a,'b');assert.equal(S.compare.b,'a');
      let dest;go=(id,args)=>{dest=[id,args];return Promise.resolve();};
      await document.getElementById('compare-build-table').click();assert.equal(dest[0],'s10');
      assert.equal(JSON.stringify(dest[1].runs),JSON.stringify(['b','a']));
    """)


def test_first_hash_visit_waits_for_context_before_requesting_comparison():
    run_js(SETUP + r"""
      S.shell.contextLoaded=false;S.shell.started=false;S.compare.initialized=false;S.score.name=null;
      location.hash='#s04';const regular=api;
      api=async path=>{calls.push(path);
        if(path==='/api/sets')return {sets:[{id:'fake',label:'가짜 묶음',usable:true}],default:'fake'};
        if(path==='/api/keys')return {keys:[{id:'silver/fake',label:'가짜 정답',usable:true}],default:'silver/fake'};
        if(path==='/api/servers')return {models:[]};return regular(path);};
      await start();await S.compare.pending;
      assert.equal(S.shell.route,'s04');assert.ok(S.compare.data);
      assert.equal(S.compare.a,'a');assert.equal(S.compare.b,'b');
      assert.ok(calls.filter(p=>p.startsWith('/api/diff?')).every(p=>p.includes('silver%2Ffake')));
      assert.equal(screen().querySelector('.compare-headline').textContent,T('compare.same.title'));
    """)


def test_pair_switch_does_not_display_delayed_prompt_for_another_pair():
    run_js(SETUP + r"""
      await show();let finish;const regular=api;
      api=async path=>path.startsWith('/api/prompt_diff')?new Promise(r=>{finish=r;}):regular(path);
      const old=document.getElementById('compare-prompts').querySelector('[data-section="11"]').click();
      await compareEnsure({a:'b',b:'a'});
      finish({same:false,diff:'OLD PAIR PROMPT',a_lines:1,b_lines:1,rows:[false,false]});await old;
      assert.ok(!document.getElementById('compare-prompts').textContent.includes('OLD PAIR PROMPT'));
    """)


def test_source_navigation_reaches_real_source_module_with_answer_key():
    run_js(SETUP + r"""
      await show();const regular=api;
      api=async path=>{if(path.startsWith('/api/doc?')){calls.push(path);return {doc_id:'T21-X01',pages:[2],
        lines:[{id:'p2:L1',page:2,no:1,text:'가짜 독성 근거'}],
        sections:{'11':{start:'p2:L1',end:'p2:L1'}},values:[{path:'fake.path',section:11,table:'toxicity',
        field:'q',text:'가짜 값',value:'가짜 값',lines:['p2:L1'],items:['11항 급성독성'],silver:{same:false,value:'가짜 정답'}}],
        silver_only:[],line_index:{'p2:L1':['fake.path']},legend:[],warnings:[],has_gold:true,
        set:{id:'fake',label:'가짜 원문'},key:{id:'silver/fake',label:'가짜 정답'}};}return regular(path);};
      const value=S.compare.data.changed_values['11항 급성독성'].broken[0];value.path='fake.path';
      await compareOpenSource(value,'11항 급성독성','b');
      assert.equal(S.shell.route,'s02');assert.equal(S.source.run,'b');assert.equal(S.source.doc,'T21-X01');
      assert.ok(S.source.selection, JSON.stringify({data:!!S.source.data,error:S.source.error?.message,top:document.getElementById('source-top').textContent}));
      assert.equal(S.source.selection.path,'fake.path');assert.equal(S.source.page,2);
      assert.ok(calls.some(p=>p.startsWith('/api/doc?')&&p.includes('key=silver%2Ffake')));
    """)


def test_value_list_can_reveal_every_record_without_changing_input():
    run_js(SETUP + r"""
      await show();S.compare.data.changed_values['11항 급성독성'].fixed=Array.from({length:305},(_,i)=>({doc_id:'T21-X01',kind:'틀림',content:'fake-'+i}));
      const before=JSON.stringify(S.compare.data.changed_values);compareRenderValues();
      const el=document.getElementById('compare-values');el.querySelector('.card-toggle').click();
      const toggle=el.querySelector('.compare-value-toggle');toggle.focus();toggle.click();
      assert.ok(el.textContent.includes(T('compare.values.correct_count',{total:305,shown:300})));
      clickText(el,T('compare.values.more',{count:5}));assert.ok(el.textContent.includes('fake-304'));
      assert.ok(el.textContent.includes(T('compare.values.correct_count',{total:305,shown:305})));
      assert.equal(JSON.stringify(S.compare.data.changed_values),before);
    """)


def test_same_condition_api_headline_never_changes_computation_inputs():
    run_js(SETUP + r"""
      await show();const before=JSON.stringify(S.compare.data);
      // 서버의 delta를 일부러 a/b 산술값과 다르게 둬 화면에서 다시 계산하지 않는지 본다.
      S.compare.data.weighted.delta=-8.2;S.compare.data.items[0].delta=-9.1;
      compareRenderAll();assert.ok(screen().textContent.includes(T('compare.criteria.delta',{delta:'−8.2'})));
      assert.ok(screen().textContent.includes(T('compare.criteria.delta',{delta:'−9.1'})));
      S.compare.data.weighted.delta=-3;S.compare.data.items[0].delta=-3;
      assert.equal(JSON.stringify(S.compare.data),before);
    """)


def test_both_target_states_use_api_booleans_without_recalculating():
    run_js(SETUP + r"""
      await show();S.compare.data.targets.a.weighted.met=true;S.compare.data.targets.b.weighted.met=false;
      compareRenderSummary();const el=document.getElementById('compare-summary');
      assert.ok(el.textContent.includes(T('score.criteria.met')));
      assert.ok(el.textContent.includes(T('score.criteria.below')));
    """)
