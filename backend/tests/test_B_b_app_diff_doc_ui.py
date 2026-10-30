"""비교·원문 대조의 선택 흐름을 DOM 대역으로 확인한다. 네트워크는 쓰지 않는다."""
from test_B_b_app_score_ui import run_js


def test_diff_filter_retains_all_rows_and_candidate_reasons():
    run_js(r"""
      S.criteria = {items:[]};
      S.diff.data = {items:[
        {name:'내린 항목',delta:-3,a:80,b:77,sections:[11]},
        {name:'오른 항목',delta:2,a:80,b:82,sections:[8]},
        {name:'같은 항목',delta:0,a:80,b:80},
        {name:'미채점',delta:null,a:null,b:null}],
        prompt_changed_sections:[], causes:[{item:'내린 항목',reasons:['기존 원인 1','기존 원인 2']}],
        ui_text:{hidden:'내려가지 않았거나 점수가 없는 항목 3개 숨김',
          candidate:'후보입니다. 확정은 ③ 원문 대조에서 눈으로 합니다.'}};
      renderDiffItems();
      const card = document.getElementById('diff-items-card');
      assert.match(card.textContent,/3개 숨김/);
      assert.match(card.textContent,/내린 항목/);
      assert.doesNotMatch(card.textContent,/오른 항목|같은 항목|미채점/);
      card.querySelectorAll('button').find(b => b.textContent === '왜 내려갔나?').click();
      const why = card.querySelector('.sub');
      assert.ok(why.textContent.indexOf('후보입니다.') < why.textContent.indexOf('기존 원인 1'));
      assert.ok(why.textContent.indexOf('기존 원인 1') < why.textContent.indexOf('기존 원인 2'));
      card.querySelectorAll('button').find(b => b.textContent === '모두 보기').click();
      assert.match(card.textContent,/오른 항목/);
      assert.match(card.textContent,/같은 항목/);
      assert.match(card.textContent,/미채점/);
      card.querySelectorAll('button').find(b => b.textContent.includes('내려간 항목만 보기')).click();
      assert.doesNotMatch(card.textContent,/오른 항목/);
    """)


def test_diff_server_headline_leads_controls_and_uses_direction_class():
    run_js(r"""
      S.diff.data = {headline:{headline:'서버의 비교 결론'}, conditions:[], prompt_changed_sections:[],
        docs:{only_a:[],only_b:[],common:[]}, weighted:{delta:-.5},weighted_na_excluded:{}};
      for (const [delta, cls] of [[-.5,'diff-down'],[.5,'diff-up'],[0,'diff-same'],[null,'diff-same']]) {
        S.diff.data.weighted.delta = delta;
        renderDiffTop();
        const card = document.getElementById('diff-top-card');
        const headline = card.querySelector('.diff-headline');
        assert.equal(headline.textContent,'서버의 비교 결론');
        assert.equal(headline.classList.contains(cls),true);
        assert.ok(card.textContent.indexOf('서버의 비교 결론') < card.textContent.indexOf('A (전)'));
      }
    """)


def test_doc_first_open_uses_current_score_then_preserves_manual_selection():
    run_js(r"""
      renderDoc = () => {};
      renderScoreLoading = () => {};
      initDiff = async () => {};
      const requests = [];
      const page = {pages:[1,2],lines:[],values:[],silver_only:[],sections:{},line_index:{}};
      api = async path => {
        if (path === '/api/runs?count=1') return {count:2};
        if (path === '/api/runs') return {runs:[{name:'old',docs:['T21-X01']},
          {name:'current',docs:['T21-X02','T21-X03']}],criteria:{},current:'old'};
        if (path === '/api/silver_gaps') return [];
        if (path.startsWith('/api/doc?')) { requests.push(path); return page; }
        throw new Error(path);
      };
      loadRun = async name => { S.name = name; };
      await loadAll();
      assert.equal(S.doc.run,null); // 처음 탭을 열 때 현재 점수판 실행을 고른다.
      assert.equal(requests.length,0);
      S.name = 'current';
      await initDoc();
      assert.equal(S.doc.run,'current');
      assert.equal(S.doc.doc,'T21-X02');
      assert.equal(S.doc.page,1);
      S.doc.doc = 'T21-X03';
      await loadDoc();
      S.name = 'old';
      await initDoc();
      assert.equal(S.doc.run,'current');
      assert.equal(S.doc.doc,'T21-X03');
      S.list = []; S.name = null;
      await initDoc();
      assert.equal(S.doc.doc,null);
      assert.equal(S.doc.data,null);
    """)


def test_doc_chips_use_api_colors_and_section_summary():
    run_js(r"""
      renderDocLeft = () => {};
      noteSel = () => {};
      S.doc.data = {legend:[
        {key:'same',label:'실버와 같음',color:'#8c959f'},
        {key:'diff',label:'다름',color:'#bc4c00'},
        {key:'silver_only',label:'빠뜨림',color:'#cf222e'},
        {key:'picked',label:'고른 값·줄',color:'#fff8c5'}],
        ui_text:{howto:'오른쪽에서 값을 누르면 왼쪽 원문 줄이 노랗게 켜집니다.',
          sections:{'3':'값 2개 중 실버와 다른 것 1개, 결과가 빠뜨린 것 1개'}}};
      S.doc.groups = [[3,new Map()]];
      renderDocMain();
      const card = document.getElementById('doc-main-card');
      const chips = card.querySelectorAll('.chip');
      assert.equal(chips.length,4);
      chips.forEach((chip,i) => assert.equal(chip.getAttribute('style'),`background:${S.doc.data.legend[i].color}`));
      S.doc.data.legend.forEach(x => assert.ok(card.textContent.includes(x.label)));
      assert.match(card.textContent,/오른쪽에서 값을 누르면/);
      assert.match(document.getElementById('doc-right').textContent,/값 2개 중 실버와 다른 것 1개, 결과가 빠뜨린 것 1개/);
    """)
