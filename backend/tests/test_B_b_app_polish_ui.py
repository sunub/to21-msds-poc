"""마지막 접근성·오류 상태 수정의 DOM 대역 회귀 시험. 네트워크는 쓰지 않는다."""
import json
import runpy

from test_B_b_app_score_ui import APP_JS, run_js as _run_js


def run_js(body):
    copy = runpy.run_path(str(APP_JS.parent.parent / "b_app_text.py")).get("POLISH_TEXT", {})
    _run_js("if (typeof UI !== 'undefined') Object.assign(UI, " + json.dumps(copy) + ");" + body)


def test_item_toggle_is_button_and_preserves_focus_and_expansion():
    run_js(r"""
      S.criteria={items:[],weights:{'필수':3}};
      S.run={items:[{name:'가짜 항목',level:'필수',score:.5,target:.9,pass:false}]};
      renderItems(S.run);
      let row=document.getElementById('items-card').querySelector('.item');
      assert.equal(row.tagName,'button');
      assert.equal(row.getAttribute('aria-expanded'),'false');
      row.focus(); row.click();
      row=document.getElementById('items-card').querySelector('.item');
      assert.equal(row.getAttribute('aria-expanded'),'true');
      assert.equal(document.activeElement,row);
      assert.match(document.getElementById('items-card').textContent,/틀린 값 기록이 없습니다/);
      row.click();
      assert.equal(document.getElementById('items-card').querySelector('.item').getAttribute('aria-expanded'),'false');
    """)


def test_changed_values_toggle_is_button_and_keeps_both_lists():
    run_js(r"""
      S.diff.data={changed_values:{'가짜 항목':{fixed:[{doc_id:'T21-X01',kind:'틀림',content:'고친 값'}],broken:[]}}};
      renderDiffValues();
      const card=document.getElementById('diff-values-card');
      let row=card.querySelector('.vrow');
      assert.equal(row.tagName,'button'); row.focus(); row.click();
      row=card.querySelector('.vrow');
      assert.equal(row.getAttribute('aria-expanded'),'true');
      assert.equal(document.activeElement,row);
      assert.match(card.textContent,/고친 값/);
      assert.match(card.textContent,/새로 틀린 것: 없음/);
    """)


def test_history_points_are_buttons_and_storage_denial_keeps_selection():
    run_js(r"""
      S.criteria={pass_score:90};
      S.list=['a','b'].map((name,i)=>({name,kind:'run',weighted:70+i,model_tag:'fake',label:{title:'가짜 '+name}}));
      S.name='b';
      renderHistory();
      const card=document.getElementById('history-card');
      let points=card.querySelectorAll('.history-point');
      assert.equal(points.length,2);
      assert.ok(points.every(p=>p.tagName==='button' && p.getAttribute('aria-label').includes('가짜')));
      localStorage.setItem=()=>{throw new Error('denied');};
      points[0].focus(); points[0].click();
      points=card.querySelectorAll('.history-point');
      assert.equal(points[0].getAttribute('aria-pressed'),'true');
      assert.equal(document.activeElement,points[0]);
      assert.deepEqual(S.pick,['a']);
      assert.match(card.textContent,/가짜 a/);
    """)


def test_source_lines_are_buttons_with_selection_and_no_page_is_empty():
    run_js(r"""
      const line={id:'p1:L1',page:1,no:1,text:'직접 만든 가짜 줄'};
      S.doc.data={doc_id:'T21-X01',lines:[line],line_index:{},pages:[1]};
      S.doc.page=1; S.doc.sec={};
      renderDocLeft();
      const left=document.getElementById('doc-left');
      const button=left.querySelector('.ln');
      assert.equal(button.tagName,'button');
      assert.equal(button.getAttribute('aria-pressed'),'false');
      let picked; pickLine=id=>{picked=id;}; button.click();
      assert.equal(picked,'p1:L1');
      assert.equal(left.querySelector('img').getAttribute('alt'),'1쪽 그림');
      S.doc.page=null; S.doc.data.pages=[];
      renderDocLeft();
      assert.equal(left.querySelector('img'),null);
      assert.ok(left.textContent.length>0);
    """)


def test_grid_states_and_silver_status_have_visible_text():
    run_js(r"""
      for(const c of [undefined,{ok:true},{ok:true,reextracted:true},{ok:false},{ok:false,limit_kind:'긴출력'}]) {
        const cell=gridCell('T21-X01',0,1,c);
        assert.ok(cell.textContent.trim().length>0);
        if(c?.ok===false) assert.match(cell.textContent,/실패/);
      }
      for(const [only,silver,label] of [[true,null,'실버에만'],[false,{same:true,value:'가짜',text:'가짜'},'실버와 같음'],
        [false,{same:false,value:'다른 값',text:'다른 값'},'실버와 다름']]) {
        const row=valueRow({only,v:{field:'name',text:'가짜',lines:[],path:'fake',silver}});
        assert.match(row.textContent,new RegExp(label));
      }
    """)


def test_errors_share_fact_action_and_collapsed_raw_on_each_tab():
    run_js(r"""
      // 서버에서 최초 HTML에 넣은 글을 사용한다. 임의 오류는 원문 펼침 안에만 둔다.
      Object.assign(UI,{load_error:{message:'자료를 불러오지 못했습니다.',fix:'앱 상태를 보고 다시 여세요.'}});
      const raw='<가짜 오류>';
      for(const render of [
        ()=>{S.diff.error=raw;renderDiffTop();return 'diff-top-card';},
        ()=>{S.doc.error=raw;renderDocTop();return 'doc-top-card';},
        ()=>{S.jobs.error=raw;renderJobTry();return 'jobs-try-card';},
        ()=>{S.srv.error=raw;renderSrvTop();return 'srv-top-card';}
      ]) {
        const el=document.getElementById(render()).querySelector('.error-note');
        assert.ok(el);
        assert.match(el.querySelector('strong').textContent,/불러오지 못했습니다/);
        assert.match(el.textContent,/할 일:/);
        const details=el.querySelector('details');
        assert.equal(details.getAttribute('open'),null);
        assert.equal(details.querySelector('pre').textContent,raw);
      }
    """)


def test_tooltip_targets_get_keyboard_access_without_nested_tab_stops():
    run_js(r"""
      const standalone=h('span',{'data-tip':'가짜 설명'},'용어');
      assert.equal(standalone.getAttribute('tabindex'),'0');
      assert.equal(standalone.getAttribute('aria-describedby'),'tip');
      const nested=h('button',{type:'button'},h('span',{'data-tip':'단추 설명'},'항목'));
      assert.notEqual(nested.querySelector('span').getAttribute('tabindex'),'0');
      assert.equal(nested.getAttribute('data-tip'),'단추 설명');
    """)


def test_start_pending_and_jobs_refresh_error_do_not_leave_blank_or_stale_states():
    run_js(r"""
      renderStart();
      assert.match(document.getElementById('start-content').textContent,/불러오는 중/);
      S.jobs.opts={models:[],pages_dirs:[],docs:[],run_names:{},default_pages_dir:'fake',
        try_hint:{dry_run_forced:true,note:'서버 없는 시험'},field_help:{},job_ui_text:{},try_stage_help:{}};
      S.jobs.r.docs=new Set();
      S.jobs.error='가짜 새로고침 오류';
      renderJobTry();
      const card=document.getElementById('jobs-try-card');
      assert.match(card.textContent,/가짜 새로고침 오류/);
      assert.ok(card.querySelector('.error-note'));
      assert.equal(card.querySelectorAll('select').length,0);
    """)


def test_start_shows_run_list_failure_after_guide_has_loaded():
    run_js(r"""
      S.startText={intro:[],steps:[],later:[]};
      scoreLoadFailure(new Error('가짜 실행 조회 실패'));
      const el=document.getElementById('start-content');
      assert.match(el.textContent,/가짜 실행 조회 실패/);
      assert.match(el.textContent,/할 일:/);
    """)


def test_tooltip_keyboard_escape_and_pointer_transfer():
    run_js(r"""
      const handlers={}, winHandlers={};
      document.addEventListener=(k,fn)=>{handlers[k]=fn;};
      globalThis.window={innerWidth:1280,innerHeight:900,addEventListener:(k,fn)=>{winHandlers[k]=fn;}};
      const target=h('span',{'data-tip':'가짜 설명'},'용어');
      target.isConnected=true;
      target.closest=()=>target;
      target.getBoundingClientRect=()=>({left:20,right:80,top:20,bottom:40});
      const tip=document.getElementById('tip');
      tip.style={};tip.offsetWidth=200;tip.offsetHeight=50;
      tip.contains=x=>x===tip;
      setupTip();
      handlers.focusin({target});
      assert.equal(tip.hidden,false);
      assert.equal(tip.textContent,'가짜 설명');
      handlers.keydown({key:'Escape'}); assert.equal(tip.hidden,true);
      handlers.focusout({relatedTarget:null});
      handlers.mouseover({target,clientX:30,clientY:30});
      handlers.mouseout({relatedTarget:null});
      // 설명으로 옮기는 짧은 틈에는 닫히지 않아야 한다.
      assert.equal(tip.hidden,false);
      handlers.mouseover({target:tip});
      await new Promise(resolve=>setTimeout(resolve,200));
      assert.equal(tip.hidden,false);
      handlers.mouseout({relatedTarget:null});
      await new Promise(resolve=>setTimeout(resolve,200));
      assert.equal(tip.hidden,true);
    """)


def test_options_poll_reports_failure_and_same_data_recovery_as_state_changes():
    run_js(r"""
      const opts={models:[],pages_dirs:[],docs:[],run_names:{},default_pages_dir:'fake',
        try_hint:{dry_run_forced:true,note:'서버 없는 시험'}};
      S.jobs.opts=opts;
      api=async()=>{throw new Error('가짜 오류');};
      assert.equal(await loadOptions(),true);
      assert.equal(S.jobs.error,'가짜 오류');
      api=async()=>opts;
      assert.equal(await loadOptions(),true);
      assert.equal(S.jobs.error,null);
      assert.equal(await loadOptions(),false);
    """)
