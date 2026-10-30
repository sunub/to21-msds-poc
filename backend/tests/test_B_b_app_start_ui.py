"""시작 안내 사건·저장 계약의 DOM 대역 시험. 실제 브라우저 검증과 구분한다."""
from test_B_b_app_score_ui import run_js


def test_start_state_restore_reset_and_storage_denied():
    run_js(r"""
      assert.equal(initialTab(''),'start');
      S.journey = {version:1,last_step:2,dismissed:true,completed:false,first_success_at:null};
      saveJourney();
      assert.equal(loadJourney().last_step,2);
      assert.equal(initialTab(''),'score');
      assert.equal(initialTab('#doc'),'doc');
      S.journey.dismissed=false; S.journey.completed=true;
      assert.equal(initialTab(''),'score');
      localStorage.setItem('b_app.cards','keep-cards');
      localStorage.setItem('b_app.advanced','1');
      let tab; visitTab = id => { tab=id; };
      resetJourney();
      assert.equal(tab,'start');
      assert.deepEqual(JSON.parse(localStorage.getItem('b_app.journey')),
        {version:1,last_step:0,dismissed:false,completed:false,first_success_at:null});
      assert.equal(localStorage.getItem('b_app.cards'),'keep-cards');
      assert.equal(localStorage.getItem('b_app.advanced'),'1');
      for (const invalid of ['{','[]','null','{"version":2}',
        '{"version":1,"last_step":9,"completed":true}']) {
        localStorage.setItem('b_app.journey',invalid);
        assert.equal(loadJourney().last_step,0);
      }
      localStorage.getItem = () => { throw new Error('denied'); };
      assert.equal(loadJourney().completed,false);
      localStorage.setItem = () => { throw new Error('denied'); };
      advanceJourney(1);
      assert.equal(S.journey.last_step,1);
      dismissJourney();
      assert.equal(S.journey.dismissed,true);
      assert.equal(S.journey.completed,false);
    """)


def test_start_score_requires_loaded_visible_current_run():
    run_js(r"""
      S.name='fake-run'; S.run={name:'fake-run',status_text:{top_drops:[]}};
      S.scoreReady=false;
      document.getElementById('tab-score').classList.add('on');
      recordScoreView(); assert.equal(S.journey.last_step,0);
      S.scoreReady=true; S.name='other';
      recordScoreView(); assert.equal(S.journey.last_step,0);
      S.name='fake-run'; document.getElementById('tab-score').classList.remove('on');
      recordScoreView(); assert.equal(S.journey.last_step,0);
      document.getElementById('tab-score').classList.add('on');
      recordScoreView(); assert.equal(S.journey.last_step,1);
      assert.equal(S.journey.completed,false);
    """)


def test_start_tabs_hash_advanced_status_link_and_help_replay():
    run_js(r"""
      const ids=['start','score','diff','doc','jobs','servers','help'];
      const tabs=ids.map(id=>{const b=document.createElement('button');b.setAttribute('data-tab',id);return b;});
      const sections=ids.map(id=>{const s=document.getElementById('tab-'+id);s.id='tab-'+id;return s;});
      const link=document.createElement('a');
      document.querySelectorAll=sel=>sel==='.tabs button'?tabs:sel==='section.tab'?sections:[];
      document.querySelector=sel=>sel==='.start-link'?link:tabs.find(b=>sel.includes(`data-tab="${b.dataset.tab}"`));
      globalThis.window={addEventListener:()=>{}};
      history.replaceState=(_,unused,hash)=>{location.hash=hash;};
      renderConnNow=()=>{}; renderServers=()=>{};
      location.hash=''; setupTabs();
      assert.equal(location.hash,'#start');
      assert.equal(document.getElementById('tab-start').classList.contains('on'),true);
      assert.equal(tabs.find(t=>t.dataset.tab==='servers').hidden,true);
      visitTab('servers');
      assert.equal(document.getElementById('advanced').checked,true);
      assert.equal(location.hash,'#servers');
      document.getElementById('journey-replay').click();
      assert.equal(location.hash,'#start');
      assert.equal(localStorage.getItem('b_app.advanced'),'1');
      visitTab('score');
      link.events.click({preventDefault:()=>{}});
      assert.equal(location.hash,'#start');
      S.journey.dismissed=true; location.hash='#jobs'; setupTabs();
      assert.equal(location.hash,'#jobs');
      location.hash=''; setupTabs();
      assert.equal(location.hash,'#score');
    """)


def test_start_navigation_buttons_never_complete_and_no_drops_offer_diff():
    run_js(r"""
      S.startText={intro:['a','b','c'],heading:'할 일',steps:[
        {no:1,title:'점수',why:'이유',button:'보기',tab:'score'},
        {no:2,title:'고르기',why:'이유',button:'항목',tab:'score'},
        {no:3,title:'확인',why:'이유',button:'원문',tab:'doc'}],later:[],
        empty_runs:'실행 없음',no_drops:'② 비교하기',no_line:'다른 값',
        loading:'로딩',later_title:'다음',dismiss:'닫기',replay:'다시',done:'완료',current:'현재',
        skipped:'건너뜀',resume:'다시 고르기',success:'실제 확인',compare_button:'비교'};
      S.runsLoaded=true;
      renderStart();
      assert.match(document.getElementById('start-content').textContent,/실행 없음/);
      let visited; visitTab=id=>{visited=id;};
      await journeyStep(1);
      assert.equal(visited,undefined); // 빈 실행 안내를 숨기는 탭 이동을 하지 않는다.
      S.list=[{name:'fake-run'}]; S.name='fake-run';
      S.run={name:S.name,status_text:{verdict:'pass',top_drops:[]}}; S.scoreReady=true;
      renderStart();
      assert.match(document.getElementById('start-content').textContent,/② 비교하기/);
      await journeyStep(2); assert.equal(visited,'diff');
      assert.equal(S.journey.completed,false);
      assert.equal(S.journey.first_success_at,null);
    """)


def test_start_success_needs_mismatched_value_in_selected_section_and_rendered_line():
    run_js(r"""
      S.startText={no_line:'이 값은 원문 줄을 못 찾았습니다. 다른 값을 눌러 보세요.',success:'원문 확인 완료'};
      renderStart=()=>{}; scrollInto=()=>{}; markValues=()=>{}; noteSel=()=>{};
      const line=document.createElement('div'); line.setAttribute('data-id','p2:L3');
      line.setAttribute('class','ln');
      document.querySelectorAll=sel=>sel==='#doc-lines .ln'?[line]:[];
      document.querySelector=sel=>sel.includes('[data-id="p2:L3"]')?line:null;
      S.doc.run='fake-run'; S.doc.doc='T21-X01'; S.doc.page=2;
      S.doc.data={}; S.doc.line={'p2:L3':{id:'p2:L3',page:2}};
      S.doc.value={bad:{path:'bad',section:8,lines:['p2:L3'],silver:{same:false}},
        missing:{path:'missing',section:8,lines:['p2:L99'],silver:{same:false}},
        same:{path:'same',section:8,lines:['p2:L3'],silver:{same:true}}};
      S.journeyTarget={run:'fake-run',doc:'T21-X01',section:8};
      document.getElementById('tab-doc').classList.add('on');
      pickValue('missing');
      assert.equal(S.journey.completed,false);
      assert.match(document.getElementById('doc-sel').textContent,/다른 값/);
      pickValue('same'); assert.equal(S.journey.completed,false);
      S.journeyTarget.section=3;
      pickValue('bad'); assert.equal(S.journey.completed,false);
      S.journeyTarget.section=8;
      const realMark=markLines; markLines=()=>line.classList.remove('hl');
      pickValue('bad'); assert.equal(S.journey.completed,false);
      markLines=realMark;
      pickValue('bad');
      assert.equal(line.classList.contains('hl'),true);
      assert.equal(S.journey.completed,true);
      assert.equal(S.journey.last_step,3);
      assert.ok(Number.isFinite(Date.parse(S.journey.first_success_at)));
      const time=S.journey.first_success_at;
      pickValue('bad'); assert.equal(S.journey.first_success_at,time);
      assert.equal(JSON.parse(localStorage.getItem('b_app.journey')).completed,true);
    """)
