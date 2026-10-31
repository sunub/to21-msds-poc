"""마지막 접근성·오류 상태 수정의 DOM 대역 회귀 시험. 네트워크는 쓰지 않는다."""
import json
import runpy

from test_B_b_app_dom import OLD_APP_JS as APP_JS, run_old_js as _run_js


def run_js(body):
    copy = runpy.run_path(str(APP_JS.parent.parent / "b_app_text.py")).get("POLISH_TEXT", {})
    _run_js("if (typeof UI !== 'undefined') Object.assign(UI, " + json.dumps(copy) + ");" + body)


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
