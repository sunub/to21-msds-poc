"""승인 S01의 읽기·선택·복구 계약. 모든 API는 가짜이며 서버를 부르지 않는다."""
from test_B_b_app_dom import run_js

FIXTURE = r"""
S.shell.contextLoaded=true; S.ctx={version:1,set:'prev/fake',key:'gold/fake'};
const key={id:'gold/fake',label:'Reviewed fake answers'};
const losses=Array.from({length:23},(_,i)=>({name:'Criterion '+i,level:'required',weight:3,
 score:75+i,target:80,loss:i===0?2.946:1.2,below_target:i<5,section:8,rank:i+1,
 counts:i===1?null:{'빠뜨림':6,'틀림':1,'지어냄':2},cause:i===1?null:'빠뜨림'}));
const criteria={pass_score:99,weights:{required:3},items:losses.map(x=>({name:x.name,level:x.level,target:x.target/100,help:'Fake help',metric:'F1'}))};
const targets={weighted:{value:82.4,line:87,met:false},must:{total:19,met_count:12,met:false}};
const run={name:'fake-current',kind:'run',run_kind:'dev10',comparable:true,set:{id:'prev/fake',label:'Fake pages',usable:true},
 key,weighted:82.4,targets,docs:['T21-X01','T21-X02'],no_gold:['T21-X03'],excluded:['T21-X99'],
 label:{title:'Current result'},model_tag:'fake-model',model_label:'Fake model',model:'Fake full model',prompt_version:'s-test',
 pages_dir:'data/pages/prev/fake',started_at:'2026-10-31T12:00:00',progress:{done:3,total:3,running:false},
 status_text:{headline:'API headline',next_action:'API next action',top_drops:[{name:'WRONG OLD RANK',section:2}],losses,
 top_problem:{...losses[0],docs:[{doc_id:'T21-X02',score:50,loss:2},{doc_id:'T21-X01',score:90,loss:.946}]},
 loss_basis:{weight_total:61,loss_total:17.6}},weighted_na_excluded:86.7,
 items:criteria.items.map(x=>({...x,score:.1})),items_na_excluded:[{name:losses[0].name,score:.9}],
 details:[{doc_id:'T21-X01',item:losses[0].name,kind:'틀림',content:'Fake mismatch <b>safe text</b>'}],
 per_doc:{'T21-X01':{weighted:81,seconds:301,failed_must:['Criterion 0']},'T21-X02':{weighted:83.8,seconds:null,failed_must:[]}},
 grid:{'T21-X01':{'m0:1':{ok:true,attempts:1,seconds:2,mode:'rows'},'m0:2':{ok:true,reextracted:true},
 'm0:3':{ok:true,limit_kind:'long output'},'m0:4':{ok:false},'m1:1':{ok:true}}},
 rows:{components:{pred:2,gold:4},extras:{pred:0,gold:0}},
 card_summaries:{history:'SERVER HISTORY best 81.2',docs:'SERVER DOCS',grid:'SERVER GRID',rows:'SERVER ROWS'}};
const previous={...run,name:'fake-previous',label:{title:'Previous result'},weighted:81.2};
const silver={...run,name:'fake-answer',run_kind:'silver',comparable:false,weighted:99.9};
const manual={...run,name:'manual/fake-one',kind:'manual',run_kind:'single',comparable:false};
const allRuns=[previous,run,silver,manual];
const calls=[];
const gaps=[{item:'Criterion 0',note:'Fake answer gap',source:'Fake review',since:'2026-10-30'}];
api=async path=>{calls.push(path);const [p,q]=path.split('?');const params=new URLSearchParams(q);
 if(p==='/api/runs'&&params.has('count'))return {count:allRuns.length};
 if(p==='/api/runs')return {runs:allRuns,current:run.name,key,criteria,doc_time_limit:300};
 if(p.startsWith('/api/run/'))return {...run,...allRuns.find(x=>x.name===decodeURIComponent(p.slice(9)))};
 if(p==='/api/criteria')return criteria;
 if(p==='/api/silver_gaps')return {key,gaps};
 throw new Error('unexpected '+path);};
const el=id=>document.getElementById(id);
const screen=()=>el('screen-s01').textContent;
const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
"""


def test_score_summary_uses_api_targets_key_scope_and_loss_without_recalculation():
    run_js(FIXTURE + r"""
      await go('s01');const summary=el('score-summary').textContent;
      for(const value of ['82.4','87','19','12',key.label,'2','Criterion 0','2.95'])assert.ok(summary.includes(value),value);
      assert.ok(!screen().includes('합격'));assert.ok(!summary.includes('WRONG OLD RANK'));
      assert.ok(!/null|undefined|⟦/.test(screen()));
      assert.equal(el('score-summary').getAttribute('aria-busy'),'false');
      assert.ok(document.querySelector('[data-guide="s01-score"]'));
      assert.ok(document.querySelector('[data-guide="s01-top-problem"]'));
      assert.ok(calls.some(x=>x.startsWith('/api/run/fake-current?key=')));
    """)


def test_score_largest_problem_navigation_preserves_run_document_section_item_and_pick():
    run_js(FIXTURE + r"""
      await go('s01');const jumps=[];go=async(id,args)=>jumps.push({id,args});
      await el('score-open-source').click();
      assert.equal(jumps[0].id,'s02');assert.deepEqual(jumps[0].args,
        {run:run.name,doc:'T21-X02',section:8,item:'Criterion 0',pick:'mismatch'});
      assert.equal(S.focus.run,run.name);assert.equal(S.focus.section,8);assert.equal(S.focus.doc,'T21-X02');
      assert.ok(el('score-summary').textContent.includes(T('score.problem.evidence_hint',{count:6})));
    """)


def test_score_empty_problem_empty_set_and_unscored_never_imply_zero():
    run_js(FIXTURE + r"""
      run.status_text.top_problem=null;await go('s01');
      assert.ok(screen().includes(T('score.no_problem.title')));assert.equal(el('score-open-source'),null);
      S.ctx.set='other';emit('context_changed');await S.score.pending;
      assert.ok(screen().includes(T('score.empty.state')));assert.ok(!screen().includes('82.4'));
      assert.ok(!el('score-summary').textContent.includes('0.0'));assert.equal(el('score-summary').querySelector('svg'),null);
      S.ctx.set='prev/fake';run.weighted=null;run.targets=null;run.status_text.losses=[];
      emit('context_changed');await S.score.pending;
      assert.ok(screen().includes(T('score.summary.unscored')));assert.ok(!el('score-summary').textContent.includes('0.0'));
    """)


def test_score_problem_order_unrecorded_filter_and_focus_survive_expansion():
    run_js(FIXTURE + r"""
      await go('s01');const rows=()=>el('score-problems').querySelectorAll('.score-item-toggle');
      assert.deepEqual(Array.from(rows(),x=>x.dataset.item),losses.map(x=>x.name));
      const row=rows()[1];assert.ok(row.textContent.includes(T('common.legacy.cell_labels.c_none')));
      assert.equal(row.querySelectorAll('.score-count').length,0);
      row.focus();row.click();assert.equal(document.activeElement,row);assert.equal(row.getAttribute('aria-expanded'),'true');
      row.click();assert.equal(row.getAttribute('aria-expanded'),'false');
      el('score-filter-below').click();assert.equal(rows().length,5);
      assert.ok(el('score-problems').textContent.includes(T('score.criteria.hidden',{count:18})));
      el('score-filter-all').click();assert.equal(rows().length,23);
      rows()[0].click();assert.ok(el('score-problems').textContent.includes('Fake mismatch <b>safe text</b>'));
      assert.ok(el('score-problems').textContent.includes('90.0'));assert.equal(el('score-problems').querySelector('b'),null);
    """)


def test_score_run_selector_groups_run_kind_and_keeps_api_current():
    run_js(FIXTURE + r"""
      await go('s01');const select=el('score-run-select');assert.equal(select.value,run.name);
      for(const kind of ['dev10','single','silver'])assert.ok(select.querySelector('[data-kind="'+kind+'"]'));
      const option=select.querySelector('[value="manual/fake-one"]');
      assert.ok(option.textContent.includes(T('score.selection.not_comparable')));
      select.value='manual/fake-one';await select.dispatchEvent({type:'change'});
      assert.equal(S.score.run.name,'manual/fake-one');assert.ok(calls.some(x=>x.includes('/api/run/manual/fake-one?key=')));
    """)


def test_score_history_buttons_save_order_survive_storage_denial_and_compare():
    run_js(FIXTURE + r"""
      await go('s01');const points=()=>el('score-history').querySelectorAll('.score-history-point');
      assert.deepEqual(Array.from(points(),x=>x.dataset.run),['fake-previous','fake-current']);
      assert.ok(el('score-history').textContent.includes(run.card_summaries.history));
      points()[0].focus();points()[0].click();assert.equal(points()[0].getAttribute('aria-pressed'),'true');
      assert.deepEqual(JSON.parse(localStorage.getItem('b_app.pick')),['fake-previous']);
      localStorage.setItem=()=>{throw new Error('denied');};const second=points()[1];second.focus();second.click();
      assert.equal(document.activeElement,second);assert.deepEqual(S.score.pick,['fake-previous','fake-current']);
      const jumps=[];go=async(id,args)=>jumps.push({id,args});await el('score-compare-picks').click();
      assert.deepEqual(jumps,[{id:'s04',args:{a:'fake-previous',b:'fake-current'}}]);
      el('score-clear-picks').click();assert.deepEqual(S.score.pick,[]);
    """)


def test_score_details_preserve_documents_grid_rows_rules_and_selected_answer_gaps():
    run_js(FIXTURE + r"""
      await go('s01');for(const id of ['score-problems','score-history','score-docs','score-grid','score-rows','score-rule','score-gaps']){
        assert.equal(el(id).querySelector('details').open,false,id);
      }
      const docs=el('score-docs').textContent;
      for(const t of ['301',T('common.legacy.time_over'),T('score.documents.time_unknown'),'Criterion 0',key.label])assert.ok(docs.includes(t),t);
      const grid=el('score-grid');assert.equal(grid.querySelectorAll('.score-call').length,32);
      for(const code of ['c_ok','c_re','c_limit','c_fail','c_none'])assert.ok(grid.textContent.includes(T('common.legacy.cell_labels.'+code)));
      assert.ok(grid.textContent.includes('long output'));assert.ok(grid.textContent.includes('rows'));
      const rows=el('score-rows').textContent;assert.ok(rows.includes('50%'));assert.ok(rows.includes(T('score.tables.extras')));
      assert.ok(el('score-rule').textContent.includes('86.7'));assert.ok(el('score-rule').textContent.includes('F1'));
      assert.ok(el('score-gaps').textContent.includes('Fake answer gap'));assert.ok(el('score-gaps').textContent.includes('Fake review'));
      assert.ok(calls.includes('/api/silver_gaps?key=gold%2Ffake'));assert.ok(!/null|undefined|⟦/.test(screen()));
    """)


def test_score_loading_count_failure_raw_and_retry():
    run_js(FIXTURE + r"""
      const base=api;let release;api=path=>path==='/api/runs?key=gold%2Ffake'?new Promise(resolve=>release=resolve):base(path);
      const pending=go('s01');await flush();assert.ok(el('score-summary').textContent.includes(T('score.loading.scoring',{count:4})));
      assert.equal(el('score-summary').getAttribute('aria-busy'),'true');
      release({runs:allRuns,current:run.name,key,criteria,doc_time_limit:300});await pending;
      assert.ok(!el('score-summary').textContent.includes(T('score.loading.scoring',{count:4})));
      api=async()=>{throw new Error('<b>fake failure</b>');};await scoreLoad(true);
      const error=el('score-summary').querySelector('.error-note');assert.ok(error);
      assert.ok(error.textContent.includes(T('score.load_failed.fact')));assert.ok(error.textContent.includes(T('score.load_failed.todo')));
      assert.equal(error.querySelector('details').open,false);assert.equal(error.querySelector('pre').textContent,'<b>fake failure</b>');
      assert.ok(!screen().includes('82.4'));api=base;await el('score-reload').click();assert.ok(screen().includes('82.4'));
    """)


def test_score_context_reload_hides_stale_scores_and_ignores_late_response():
    run_js(FIXTURE + r"""
      await go('s01');const base=api;let oldRelease;
      api=path=>path.includes('/api/run/')&&path.includes('gold%2Ffake')?new Promise(resolve=>oldRelease=resolve):base(path);
      const older=scoreLoad(true);await flush();
      S.ctx.key='gold/new';key.id='gold/new';key.label='New answers';emit('context_changed');
      assert.ok(!screen().includes('82.4'));await S.score.pending;
      oldRelease({...run,weighted:11,key:{label:'OLD answers'}});await older;
      assert.ok(el('score-summary').textContent.includes('New answers'));assert.ok(!screen().includes('OLD answers'));
      for(const p of ['/api/runs','/api/run/fake-current','/api/silver_gaps'])assert.ok(calls.includes(p+'?key=gold%2Fnew'),p);
    """)


def test_score_missing_targets_fallback_key_partial_failures_and_no_false_problem():
    run_js(FIXTURE + r"""
      delete run.key;run.targets=null;run.status_text.top_problem={...losses[0],section:null,docs:[]};
      allRuns.push({name:'broken',kind:'run',error:'Partial fake failure'});
      await go('s01');assert.ok(screen().includes(T('score.basis.fallback')));
      assert.ok(screen().includes(T('context.unavailable')));assert.ok(screen().includes(T('score.partial.title',{total:5,failed:1})));
      assert.equal(el('score-open-source').disabled,true);assert.ok(!/null|undefined|⟦/.test(screen()));
    """)


def test_score_initial_load_waits_for_restored_context():
    run_js(FIXTURE + r"""
      S.shell.contextLoaded=false;S.ctx={version:1,set:null,key:null};const base=api;
      api=async path=>{
        if(path==='/api/sets')return {default:'prev/fake',sets:[{id:'prev/fake',label:'Fake pages',usable:true}]};
        if(path==='/api/keys')return {default:'gold/fake',keys:[{...key,usable:true}]};
        if(path==='/api/servers')return {models:[]};return base(path);};
      await start();await flush();await S.score.pending;
      assert.equal(S.ctx.key,'gold/fake');assert.ok(screen().includes('82.4'));
      assert.ok(!calls.some(p=>p==='/api/runs'||p==='/api/run/fake-current'));
    """)


def test_score_saved_history_selection_survives_refresh_and_run_selector_stays_current():
    run_js(FIXTURE + r"""
      S.score.pick=['fake-previous'];await go('s01');await scoreLoad(true);
      assert.deepEqual(S.score.pick,['fake-previous']);
      const selected=el('score-history').querySelector('[data-run="fake-previous"]');
      assert.equal(selected.getAttribute('aria-pressed'),'true');
      assert.equal(el('score-run-select').value,run.name);
    """)


def test_score_conditions_keep_status_next_action_and_retest_target():
    run_js(FIXTURE + r"""
      await go('s01');assert.ok(screen().includes(run.status_text.headline));assert.ok(screen().includes(run.status_text.next_action));
      const jumps=[];go=async(id,args)=>jumps.push({id,args});await el('score-retest').click();
      assert.equal(jumps[0].id,'s03');assert.equal(jumps[0].args.doc,'T21-X02');
      assert.equal(jumps[0].args.section,8);assert.equal(jumps[0].args.run,run.name);
    """)


def test_score_unrecorded_top_problem_does_not_invent_count_and_cards_keep_scope():
    run_js(FIXTURE + r"""
      run.status_text.top_problem.counts=null;await go('s01');
      const summary=el('score-summary').textContent;
      assert.ok(summary.includes(T('common.legacy.cell_labels.c_none')));
      assert.ok(!summary.includes(T('score.problem.counts.missing',{count:0})));
      assert.ok(!summary.includes('기록 없음건'));
      const row=el('score-problems').querySelector('.score-item-toggle');assert.ok(row.getAttribute('data-tip').includes(key.label));
      assert.ok(el('score-history').querySelector('.score-history-point').getAttribute('aria-label').includes(key.label));
    """)


def test_score_uses_readable_names_for_full_api_criterion_labels():
    run_js(FIXTURE + r"""
      run.status_text.top_problem.name='8항 노출기준(성분·출처·종류·값)';
      await go('s01');
      assert.ok(el('score-summary').textContent.includes(T('score.criteria.exposure')));
      assert.ok(el('score-summary').textContent.includes(run.status_text.top_problem.name));
      assert.equal(scoreItemName('15항 국내 규제 기준농도'),T('score.criteria.regulation_concentration'));
      assert.equal(scoreItemName('구성성분(CAS 기준 매칭)'),T('score.criteria.components'));
    """)


def test_score_unknown_set_does_not_match_unresolved_run_set():
    run_js(FIXTURE + r"""
      S.ctx.set=null;for(const r of allRuns)r.set={id:null,usable:false,source:'none'};
      await go('s01');assert.ok(screen().includes(T('score.empty.state')));
      assert.ok(!el('score-summary').textContent.includes('82.4'));
    """)
