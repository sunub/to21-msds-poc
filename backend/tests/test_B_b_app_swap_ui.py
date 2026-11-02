"""자료 바꾸기 화면(S11)과 윗줄 상태의 조작 계약. 가짜 응답만 쓰며 브라우저 배치를 판정하지 않는다."""
from test_B_b_app_dom import STATIC, run_js

FIXTURES = r"""
const el=id=>document.getElementById(id);
const text=id=>el(id).textContent;
// 막대에는 상태와 요금만 쓰고 긴 설명은 AI 칩의 말풍선에 있다 (ADR-039). 둘을 합쳐 읽는다.
const modelInfo=()=>text('context-model')+'\n'+el('context-model-open').getAttribute('data-tip');
const sets={default:'version17',sets:[
 {id:'version17',label:'version17',usable:true,counts:{dev:1,eval_locked:1},docs:[{doc_id:'T21-X01',locked:false},{doc_id:'T21-X09',locked:true}]},
 {id:'newset',label:'newset',usable:true,counts:{outside:1},docs:[{doc_id:'RAW-90',locked:false}]}]};
const keys={default:'gold',keys:[
 {id:'gold',label:'Reviewed answers',kind:'gold',usable:true,docs:['T21-X01'],fingerprint:'abc'},
 {id:'silver/claude',label:'Draft answers',kind:'silver',usable:true,docs:['T21-X01'],fingerprint:'def'}]};
const candidates={folder:'/fake/Downloads',error:null,items:[
 {name:'newset',path:'/fake/Downloads/newset',docs:40,modified_at:'2026-11-01T01:43:00+09:00',in_app:false},
 {name:'version17',path:'/fake/Downloads/version17',docs:20,modified_at:'2026-11-01T01:40:00+09:00',in_app:true}]};
const FORMAT={name:'newset',path:'/fake/Downloads/newset',docs_total:40,verdict:'format_only',score_docs:0,gold_docs:10,batch_docs:39,try_docs:0,
 no_line_numbers:0,locked:{eval:1,unknown:0,same_as:{'RAW-50':'T21-X09'}},existing:{state:'new',set_id:null},target:'data/pages/newset',
 score_alternative:{id:'version17',docs:10}};
const SCORE={...FORMAT,name:'version17',verdict:'score',score_docs:10,batch_docs:10,try_docs:10,score_alternative:null,
 locked:{eval:10,unknown:0,same_as:{}},existing:{state:'same',set_id:'version17'},target:'data/pages/version17'};
const GOLD={path:'data/gold',docs:10,eval_docs:10,commit:{sha:'85d599f',at:'2026-11-01T18:52:00+09:00'},branch:'main',fetched:true,
 behind:{dev:[],eval:0},changed:null,pull:'git -C /fake/repo pull'};
const calls=[];
let checkResult=FORMAT,applyResult={set_id:'newset',copied:true},goldResult=GOLD,servers={models:[]},runs=[];
api=async(path,options={})=>{
 calls.push([options.method||'GET',path,options.body?JSON.parse(options.body):null]);
 if(path==='/api/sets')return sets;
 if(path==='/api/keys')return keys;
 if(path==='/api/servers')return servers;
 if(path==='/api/swap/candidates')return candidates;
 if(path==='/api/swap/check'){if(checkResult instanceof Error)throw checkResult;return checkResult;}
 if(path==='/api/swap/apply'){if(applyResult instanceof Error)throw applyResult;return applyResult;}
 if(path.startsWith('/api/swap/gold'))return goldResult;
 if(path.startsWith('/api/runs'))return {runs,current:null,key:{id:S.ctx.key}};
 throw new Error(path);
};
const problem=(message,fix)=>Object.assign(new Error(message),{status:400,body:{error:message,message,fix}});
const button=label=>document.querySelector('#screen-s11').querySelectorAll('button').find(b=>b.textContent===label);
const settle=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
const open=async(view='start')=>{await start();await go('s11',{swapView:view});await settle();};
"""


def test_strip_says_whether_the_chosen_documents_can_get_a_score():
    run_js(FIXTURES + r"""
      await start();
      assert.equal(text('context-score-chip'),T('swap.context.score_docs_short',{count:1}));   // 잠긴 평가 문서는 세지 않는다
      assert.ok(el('context-score-chip').classList.contains('yes'));
      assert.ok(el('context-change-set').getAttribute('data-tip').includes(T('swap.context.score_docs',{count:1})));
      shellApplyContext({set:'newset',key:'gold'});
      assert.equal(text('context-score-chip'),T('swap.context.no_score_short'));
      assert.ok(el('context-score-chip').classList.contains('no'));
      assert.ok(el('context-change-set').getAttribute('data-tip').includes(T('swap.context.no_score')));
    """)


def test_strip_labels_say_what_the_next_test_uses_and_link_to_swap():
    run_js(FIXTURES + r"""
      await start();
      assert.ok(text('global-context').includes(T('context.documents.short')));
      assert.ok(el('context-change-set').getAttribute('data-tip').includes(T('context.documents.label')));
      el('context-swap').click();await settle();
      assert.equal(S.shell.route,'s11');
      assert.equal(el('screen-s11').hidden,false);
      assert.equal(text('title-s11'),T('swap.start.title'));
    """)


def test_start_offers_two_paths_and_calls_neither_ai_nor_network():
    run_js(FIXTURES + r"""
      await open();
      for(const key of ['docs_title','docs_note','gold_title','gold_note'])assert.ok(text('swap-view').includes(T('swap.start.'+key)),key);
      assert.ok(button(T('swap.start.docs_action')));assert.ok(button(T('swap.start.gold_action')));
      assert.deepEqual(calls.filter(c=>c[0]==='POST'),[]);
      assert.equal(calls.filter(c=>c[1].includes('fetch=1')).length,0);
    """)


def test_pick_lists_found_folders_and_never_moves_files():
    run_js(FIXTURES + r"""
      await open();button(T('swap.start.docs_action')).click();await settle();
      assert.equal(text('title-s11'),T('swap.pick.title'));
      assert.ok(text('swap-view').includes('newset'));assert.ok(text('swap-view').includes(T('swap.pick.not_in_app')));
      assert.ok(text('swap-view').includes(T('swap.pick.in_app')));
      assert.ok(text('swap-view').includes(T('swap.pick.other_hint')));
      assert.deepEqual(calls.filter(c=>c[0]==='POST'),[]);
      const first=document.querySelector('#swap-candidates').querySelectorAll('button')[0];first.click();await settle();
      assert.deepEqual(calls.filter(c=>c[0]==='POST'),[['POST','/api/swap/check',{path:'/fake/Downloads/newset'}]]);
      assert.equal(calls.filter(c=>c[1]==='/api/swap/apply').length,0);
      assert.equal(S.ctx.set,'version17');                                             // 검사만으로는 윗줄이 바뀌지 않는다
    """)


def test_pick_explains_empty_and_unreadable_downloads():
    run_js(FIXTURES + r"""
      candidates.items=[];await open('pick');
      assert.ok(text('swap-view').includes(T('swap.pick.empty')));
      candidates.error='unreadable';await go('s11',{swapView:'pick'});await settle();
      assert.ok(text('swap-view').includes(T('swap.pick.unreadable')));
    """)


def test_pick_checks_typed_path_and_shows_plain_problem_without_losing_it():
    run_js(FIXTURES + r"""
      await open('pick');
      checkResult=problem('Folder not found','Type the full path');
      el('swap-other-path').value='/typed/place';
      el('swap-other-check').click();await settle();
      assert.deepEqual(calls.at(-1),['POST','/api/swap/check',{path:'/typed/place'}]);
      assert.equal(text('title-s11'),T('swap.pick.title'));
      assert.ok(text('swap-view').includes('Folder not found'));assert.ok(text('swap-view').includes('Type the full path'));
      assert.equal(el('swap-other-path').value,'/typed/place');
      el('swap-other-path').value='';el('swap-other-check').click();await settle();
      assert.equal(calls.filter(c=>c[1]==='/api/swap/check').length,1);                // 빈 칸은 보내지 않는다
    """)


def test_check_format_only_warns_and_points_to_folder_with_answers():
    run_js(FIXTURES + r"""
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      const view=()=>text('swap-view');
      assert.equal(text('title-s11'),T('swap.check.title.format_only'));
      assert.ok(view().includes('newset'));
      assert.ok(view().includes(T('swap.check.no_overlap_title')));
      assert.ok(view().includes(T('swap.check.alternative',{count:10,set:'version17'})));
      assert.ok(view().includes(T('swap.check.batch_yes',{count:39})));
      assert.ok(view().includes(T('swap.check.score_no')));assert.ok(view().includes(T('swap.check.try_no')));
      assert.ok(view().includes(T('swap.check.lines_all',{count:39})));
      assert.ok(view().includes(T('swap.check.locked_eval',{count:1})));
      assert.ok(view().includes(T('swap.check.locked_same',{doc:'RAW-50',eval_doc:'T21-X09'})));
      assert.ok(view().includes('data/pages/newset'));assert.ok(view().includes(T('swap.check.target_new')));
      assert.ok(view().includes(T('swap.check.past_value')));assert.ok(view().includes(T('swap.check.apply_note_new')));
      assert.ok(button(T('swap.check.apply')));assert.ok(button(T('swap.check.other')));
    """)


def test_check_score_folder_has_no_warning_and_says_already_in_app():
    run_js(FIXTURES + r"""
      checkResult=SCORE;await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      assert.equal(text('title-s11'),T('swap.check.title.score'));
      assert.ok(!text('swap-view').includes(T('swap.check.no_overlap_title')));
      assert.ok(text('swap-view').includes(T('swap.check.score_yes',{count:10})));
      assert.ok(text('swap-view').includes(T('swap.check.try_yes',{count:10})));
      assert.ok(text('swap-view').includes(T('swap.check.target_same')));
      assert.ok(text('swap-view').includes(T('swap.check.apply_note_same')));
    """)


def test_check_counts_missing_line_numbers_and_unknown_docs():
    run_js(FIXTURES + r"""
      checkResult={...FORMAT,batch_docs:37,no_line_numbers:2,locked:{eval:0,unknown:1,same_as:{}}};
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      assert.ok(text('swap-view').includes(T('swap.check.lines_some',{count:2})));
      assert.ok(text('swap-view').includes(T('swap.check.locked_unknown',{count:1})));
      checkResult={...FORMAT,locked:{eval:0,unknown:0,same_as:{}}};
      button(T('swap.check.other')).click();await settle();
      document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      assert.ok(text('swap-view').includes(T('swap.check.locked_none')));
    """)


def test_check_gives_no_apply_when_unusable_or_name_is_taken():
    run_js(FIXTURES + r"""
      checkResult={...FORMAT,verdict:'unusable',batch_docs:0,score_alternative:null};
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      assert.equal(text('title-s11'),T('swap.check.title.unusable'));
      assert.ok(text('swap-view').includes(T('swap.check.unusable_body')));
      assert.ok(!text('swap-view').includes(T('swap.check.can_title')));                // 시험을 못 하는 폴더에 틀린 이유를 늘어놓지 않는다
      assert.ok(!text('swap-view').includes(T('swap.check.score_no')));
      assert.ok(!text('swap-view').includes(T('swap.check.target_new')));               // 넣지 못하는 폴더의 넣을 곳은 보이지 않는다
      assert.equal(button(T('swap.check.apply')),undefined);
      checkResult={...FORMAT,existing:{state:'different',set_id:'newset'}};
      button(T('swap.check.other')).click();await settle();
      document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      assert.ok(text('swap-view').includes(T('swap.check.target_conflict_title')));
      assert.ok(text('swap-view').includes(T('swap.check.target_conflict')));
      assert.equal(button(T('swap.check.apply')),undefined);
    """)


def test_apply_switches_strip_once_and_undo_returns_without_deleting():
    run_js(FIXTURES + r"""
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      const changes=[];on('context_changed',e=>changes.push(e.set));
      button(T('swap.check.apply')).click();await settle();
      assert.deepEqual(calls.filter(c=>c[1]==='/api/swap/apply'),[['POST','/api/swap/apply',{path:'/fake/Downloads/newset'}]]);
      assert.equal(S.ctx.set,'newset');assert.deepEqual(changes,['newset']);
      assert.equal(JSON.parse(localStorage.getItem('b_app.context')).set,'newset');
      assert.equal(text('title-s11'),T('swap.done.title'));
      assert.ok(text('swap-view').includes(T('swap.done.changed')));
      assert.ok(text('swap-view').includes(T('swap.done.results_none')));
      assert.equal(text('context-score-chip'),T('swap.context.no_score_short'));
      assert.ok(text('swap-view').includes(T('swap.done.undo_note',{set:'version17'})));
      button(T('swap.done.undo')).click();await settle();
      assert.equal(S.ctx.set,'version17');assert.deepEqual(changes,['newset','version17']);
      assert.equal(calls.filter(c=>c[0]==='POST').length,2);                            // 되돌리기는 서버에 아무것도 보내지 않는다
      assert.equal(text('title-s11'),T('swap.start.title'));
      assert.equal(text('status'),T('swap.done.undone'));
    """)


def test_done_screen_appears_before_saved_results_are_read():
    run_js(FIXTURES + r"""
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      let finish;const real=api;
      api=(path,options)=>path.startsWith('/api/runs')?new Promise(resolve=>{finish=()=>resolve({runs:[{name:'a',set:{id:'newset'},key:{id:'gold'}}],current:null,key:{id:'gold'}});}):real(path,options);
      button(T('swap.check.apply')).click();await settle();
      assert.equal(text('title-s11'),T('swap.done.title'));                             // 저장된 결과를 다 읽기 전에 완료 화면이 나온다
      assert.ok(text('swap-view').includes(T('swap.done.changed')));
      assert.ok(!text('swap-view').includes(T('swap.done.results_none')));
      assert.equal(document.querySelectorAll('[role="status"]').filter(e=>e.textContent===T('swap.check.applying')).length,0);
      finish();await settle();
      assert.ok(text('swap-view').includes(T('swap.done.results_found',{count:1})));
    """)


def test_start_offers_switching_to_what_is_already_in_the_app():
    run_js(FIXTURES + r"""
      await open();
      assert.ok(text('swap-view').includes(T('swap.start.have_note')));
      button(T('swap.start.have_action')).click();await settle();
      assert.equal(el('context-picker').open,true);
    """)


def test_status_line_follows_the_screen():
    run_js(FIXTURES + r"""
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      button(T('swap.check.apply')).click();await settle();
      assert.equal(text('status'),T('swap.done.title'));
      button(T('swap.done.undo')).click();await settle();
      assert.equal(text('status'),T('swap.done.undone'));
      button(T('swap.start.gold_action')).click();await settle();
      assert.equal(text('status'),'');
      await go('s11',{swapView:'start'});await settle();
      button(T('swap.start.docs_action')).click();await settle();
      assert.equal(text('status'),'');
    """)


def test_strip_links_sit_in_their_own_row():
    run_js(FIXTURES + r"""
      await start();
      const row=document.querySelector('.context-links');
      assert.equal(el('context-change-set').parentElement,row);assert.equal(el('context-swap').parentElement,row);
    """)


def test_apply_problem_stays_on_check_and_keeps_strip():
    run_js(FIXTURES + r"""
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      applyResult=problem('Same name exists','Rename the folder');
      button(T('swap.check.apply')).click();await settle();
      assert.equal(S.ctx.set,'version17');
      assert.equal(text('title-s11'),T('swap.check.title.format_only'));
      assert.ok(text('swap-view').includes('Same name exists'));assert.ok(text('swap-view').includes('Rename the folder'));
    """)


def test_done_reports_saved_results_and_hides_undo_when_set_did_not_change():
    run_js(FIXTURES + r"""
      runs=[{name:'a',set:{id:'version17'},key:{id:'gold'}},{name:'b',set:{id:'version17'},key:{id:'gold'}}];
      checkResult=SCORE;applyResult={set_id:'version17',copied:false};
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      button(T('swap.check.apply')).click();await settle();
      assert.ok(text('swap-view').includes(T('swap.done.results_found',{count:2})));
      assert.equal(button(T('swap.done.undo')),undefined);
    """)


def test_done_next_step_opens_a_screen_and_never_starts_a_server_or_a_test():
    run_js(FIXTURES + r"""
      await open('pick');document.querySelector('#swap-candidates').querySelector('button').click();await settle();
      button(T('swap.check.apply')).click();await settle();
      assert.ok(text('swap-view').includes(T('swap.done.off_note')));
      button(T('swap.done.off_action')).click();await settle();
      assert.equal(S.shell.route,'s06');
      S.swap.view='done';S.shell.servers={models:[{tag:'m',reachable:true,match:true}]};
      await go('s11',{swapView:'done'});await settle();
      assert.ok(text('swap-view').includes(T('swap.done.on_note')));
      button(T('swap.done.on_action')).click();await settle();
      assert.equal(S.shell.route,'s09');
      assert.deepEqual(calls.filter(c=>c[0]==='POST').map(c=>c[1]),['/api/swap/check','/api/swap/apply']);
    """)


def test_gold_screen_checks_github_and_shows_command_when_behind():
    run_js(FIXTURES + r"""
      goldResult={...GOLD,behind:{dev:['T21-X01','T21-X02'],eval:1}};
      await open();button(T('swap.start.gold_action')).click();await settle();
      assert.equal(text('title-s11'),T('swap.gold.title'));
      assert.ok(calls.some(c=>c[1].includes('fetch=1')));
      const view=()=>text('swap-view');
      assert.ok(view().includes('data/gold'));assert.ok(view().includes('85d599f'));
      assert.ok(view().includes(T('swap.gold.docs_value',{count:10})));assert.ok(view().includes(T('swap.gold.eval_value',{count:10})));
      assert.ok(view().includes(T('swap.gold.behind_title',{dev:2,eval_docs:1})));
      assert.ok(view().includes('git -C /fake/repo pull'));
      assert.ok(view().includes(T('swap.gold.after')));
      assert.ok(!view().includes(T('swap.gold.latest')));
    """)


def test_gold_screen_says_latest_offline_and_side_branch():
    run_js(FIXTURES + r"""
      await open('gold');
      assert.ok(text('swap-view').includes(T('swap.gold.latest')));
      goldResult={...GOLD,fetched:false};button(T('swap.gold.recheck')).click();await settle();
      assert.ok(text('swap-view').includes(T('swap.gold.offline')));
      assert.ok(!text('swap-view').includes(T('swap.gold.latest')));
      goldResult={...GOLD,branch:'b/side',pull:'git -C /fake/repo merge origin/main',behind:{dev:['T21-X01'],eval:0}};
      button(T('swap.gold.recheck')).click();await settle();
      assert.ok(text('swap-view').includes(T('swap.gold.branch_note',{branch:'b/side'})));
      assert.ok(text('swap-view').includes('git -C /fake/repo merge origin/main'));
    """)


def test_gold_screen_says_when_comparing_with_another_answer_and_can_switch():
    run_js(FIXTURES + r"""
      await open('gold');
      assert.ok(!text('swap-view').includes(T('swap.gold.other_selected')));
      shellApplyContext({set:'version17',key:'silver/claude'});await go('s11',{swapView:'gold'});await settle();
      assert.ok(text('swap-view').includes(T('swap.gold.other_selected')));
      assert.ok(text('swap-view').includes('Draft answers'));
      button(T('swap.gold.use_gold')).click();await settle();
      assert.equal(S.ctx.key,'gold');
    """)


def test_gold_screen_hides_switch_when_gold_is_not_a_choice():
    run_js(FIXTURES + r"""
      keys.keys=keys.keys.filter(k=>k.id!=='gold');keys.default='silver/claude';
      await open('gold');
      assert.ok(text('swap-view').includes(T('swap.gold.other_selected')));
      assert.equal(button(T('swap.gold.use_gold')),undefined);
    """)


def test_first_visit_remembers_gold_without_a_notice():
    run_js(FIXTURES + r"""
      goldResult={...GOLD,fetched:null};
      await start();await settle();
      assert.equal(JSON.parse(localStorage.getItem('b_app.swap.gold_seen')),'85d599f');
      assert.equal(el('context-gold-open'),null);
      assert.equal(calls.filter(c=>c[1].includes('fetch=1')).length,0);                 // 켤 때 네트워크를 부르지 않는다
    """)


def test_strip_tells_when_new_gold_arrived_and_screen_clears_it():
    run_js(FIXTURES + r"""
      localStorage.setItem('b_app.swap.gold_seen',JSON.stringify('oldsha1'));
      goldResult={...GOLD,fetched:null,changed:{dev:['T21-X01','T21-X02'],eval:1}};
      const changes=[];on('context_changed',e=>changes.push(e.key));
      await start();await settle();
      assert.ok(calls.some(c=>c[1]==='/api/swap/gold?since=oldsha1'));
      assert.ok(text('context-gold-notice').includes(T('swap.context.gold_changed',{count:3})));   // 막대 한 줄 아래에 다 보인다
      assert.equal(changes.length,1);                                                   // 열려 있던 점수를 새 정답으로 다시 읽는다
      el('context-gold-open').click();await settle();
      assert.equal(text('title-s11'),T('swap.gold.title'));
      assert.ok(text('swap-view').includes(T('swap.gold.changed_title',{dev:2,eval_docs:1})));
      assert.ok(text('swap-view').includes(T('swap.gold.changed_docs',{docs:'T21-X01, T21-X02'})));
      assert.equal(JSON.parse(localStorage.getItem('b_app.swap.gold_seen')),'85d599f');
      assert.ok(!text('context-gold-notice').includes(T('swap.context.gold_changed',{count:3})));
    """)


def test_after_git_pull_recheck_reports_change_and_rereads_scores():
    run_js(FIXTURES + r"""
      await open('gold');
      goldResult={...GOLD,commit:{sha:'aaaaaaa',at:'2026-11-02T09:00:00+09:00'},changed:{dev:['T21-X01'],eval:0}};
      const changes=[];on('context_changed',e=>changes.push(e.key));
      button(T('swap.gold.recheck')).click();await settle();
      assert.ok(calls.some(c=>c[1].includes('since=85d599f')));
      assert.ok(text('swap-view').includes(T('swap.gold.changed_title',{dev:1,eval_docs:0})));
      assert.equal(changes.length,1);
      assert.equal(JSON.parse(localStorage.getItem('b_app.swap.gold_seen')),'aaaaaaa');
      button(T('swap.gold.open_scores')).click();await settle();
      assert.equal(S.shell.route,'s01');
    """)


def test_strip_shows_gold_upload_date_only_for_main_gold():
    run_js(FIXTURES + r"""
      await start();await settle();
      assert.ok(text('context-answer-note').includes(T('swap.context.gold_note',{date:'11/1',count:1})));
      shellApplyContext({set:'version17',key:'silver/claude'});await settle();
      assert.ok(!text('context-answer-note').includes('11/1'));
    """)


def test_gold_check_failure_does_not_break_the_app():
    run_js(FIXTURES + r"""
      const real=api;api=async(path,options)=>{if(path.startsWith('/api/swap/gold'))throw problem('Nope','Fix');return real(path,options);};
      await start();await settle();
      assert.equal(S.shell.route,'s01');
      await go('s11',{swapView:'gold'});await settle();
      assert.ok(text('swap-view').includes('Nope'));
    """)


# ── 윗줄의 AI 상태 (시안 6, 지금 닫기 단추 없음) ─────────

MODEL_OFF = "{tag:'q',where:'RunPod',url_set:false,reachable:false,match:false}"
MODEL_ON = "{tag:'q',where:'RunPod',url_set:true,reachable:true,match:true}"


def test_strip_shows_loading_minutes_while_pod_starts():
    run_js(FIXTURES + r"""
      servers={models:[{tag:'q',where:'RunPod',url_set:true,reachable:false,error:'HTTP 502'}],session:{pod_id:'p1',ready:false,idle_minutes:20},
        pods:[{id:'p1',session:true,owned:true,status:'RUNNING',minutes:3.4,cost_per_hr:2.49,auto_delete_min:37}]};
      await start();await settle();
      assert.ok(modelInfo().includes(T('context.model.rented_loading')));
      assert.ok(modelInfo().includes(T('context.model.rented_elapsed',{minutes:3})));
      assert.ok(modelInfo().includes(T('context.model.rented_close_where')));
    """)


def test_strip_shows_cost_and_auto_close_when_connected():
    run_js(FIXTURES + r"""
      servers={models:[""" + MODEL_ON + r"""],session:{pod_id:'p1',ready:true,idle_minutes:20},
        pods:[{id:'p1',session:true,owned:true,status:'RUNNING',minutes:9,cost_per_hr:2.49,auto_delete_min:18}]};
      await start();await settle();
      for(const shown of [T('context.model.rented_hourly',{cost:2.49}),T('context.model.rented_auto_close',{idle:20}),T('context.model.rented_auto_left',{minutes:18}),T('context.model.rented_close_where')])
        assert.ok(modelInfo().includes(shown),shown);
    """)


def test_strip_has_no_close_button_for_rented_server():
    run_js(FIXTURES + r"""
      servers={models:[""" + MODEL_ON + r"""],session:{pod_id:'p1',ready:true,idle_minutes:20},
        pods:[{id:'p1',session:true,owned:true,status:'RUNNING',minutes:9,cost_per_hr:2.49,auto_delete_min:18}]};
      await start();await settle();
      const buttons=el('context-model').querySelectorAll('button');
      assert.equal(buttons.length,1);assert.ok(buttons[0].getAttribute('data-tip').includes(T('context.prepare_model')));
      buttons[0].click();await settle();assert.equal(S.shell.route,'s06');
    """)


def test_strip_says_no_cost_when_off_and_nothing_of_ours_runs():
    run_js(FIXTURES + r"""
      servers={models:[""" + MODEL_OFF + r"""],pods:[{id:'team',owned:false,status:'RUNNING'}]};
      await start();await settle();
      assert.ok(modelInfo().includes(T('context.model.off_no_cost')));
      servers={models:[""" + MODEL_OFF + r"""],pods:[{id:'p1',owned:true,status:'RUNNING'}]};
      await shellPollServers();
      assert.ok(!modelInfo().includes(T('context.model.off_no_cost')));
      servers={models:[""" + MODEL_OFF + r"""],pods:[],runpod_error:'RUNPOD_API_KEY'};
      await shellPollServers();
      assert.ok(!modelInfo().includes(T('context.model.off_no_cost')));       // 목록을 못 읽으면 단정하지 않는다
    """)


def test_strip_explains_automatic_close_after_it_happens():
    run_js(FIXTURES + r"""
      servers={models:[""" + MODEL_OFF + r"""],pods:[],last_auto_close:{kind:'idle',limit_min:20,minutes:26,cost:1.08}};
      await start();await settle();
      assert.ok(modelInfo().includes(T('context.model.auto_closed_idle',{limit:20})));
      assert.ok(modelInfo().includes(T('context.model.auto_closed_cost',{minutes:26,cost:1.08})));
      servers={...servers,last_auto_close:{kind:'no_reply',limit_min:40,minutes:41,cost:null}};
      await shellPollServers();
      assert.ok(modelInfo().includes(T('context.model.auto_closed_no_reply',{limit:40})));
      assert.ok(!modelInfo().includes(T('context.model.auto_closed_cost',{minutes:41,cost:null})));
    """)


# ── 안내 ───────────────────────────────────────────────

def test_help_points_to_swap_screen_and_explains_connection_states():
    run_js(FIXTURES + r"""
      await start();await go('s07',{helpTopic:'setup'});await settle();
      assert.ok(text('help-setup').includes(T('help.setup.new_data')));
      await go('s07',{helpTopic:'servers'});await settle();
      for(const key of ['states','waiting'])assert.ok(text('help-servers').includes(T('help.servers.'+key)),key);
    """)


def test_full_guide_page_has_same_new_lines():
    import importlib
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
    help_text = importlib.import_module("b_app_text").UI_TEXT["help"]
    page = (STATIC / "guide.html").read_text(encoding="utf-8")
    for line in (help_text["setup"]["new_data"], help_text["servers"]["states"], help_text["servers"]["waiting"]):
        assert line in page, line


def test_first_use_guide_tells_where_new_folder_and_new_answers_come_in():
    run_js(FIXTURES + r"""
      await start();await settle();
      S.guide.open=true;S.guide.screen='G16';guideRender();
      assert.ok(text('guide-overlay').includes(T('guide.data.source.receive')));
      assert.ok(text('guide-overlay').includes(T('guide.data.source.add_title')));
      S.guide.screen='G17';guideRender();
      assert.ok(text('guide-overlay').includes(T('guide.data.answers.receive')));
    """)


def test_help_data_chapter_tells_where_new_folder_and_new_answers_come_in():
    run_js(FIXTURES + r"""
      await start();await go('s07',{helpTopic:'data'});await settle();
      for(const key of ['source_receive','answer_receive'])assert.ok(text('help-data').includes(T('help.data.'+key)),key);
    """)


def test_swap_screen_links_to_help_and_returns():
    run_js(FIXTURES + r"""
      await open();
      const link=el('help-context-s11').querySelector('a');
      assert.equal(link.textContent,T('help.guide.data.title'));
      link.click();await settle();
      assert.equal(S.shell.route,'s07');assert.equal(el('help-data').open,true);
    """)


def test_guide_says_rented_server_start_time_and_automatic_close():
    run_js(FIXTURES + r"""
      await start();await settle();
      S.guide.open=true;S.guide.screen='G10';guideRender();
      assert.ok(text('guide-overlay').includes(T('guide.ai.rented_time')));
    """)
