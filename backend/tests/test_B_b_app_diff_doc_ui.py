"""비교·원문 대조의 선택 흐름을 DOM 대역으로 확인한다. 네트워크는 쓰지 않는다."""
from test_B_b_app_dom import run_old_js as run_js


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
