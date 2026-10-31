"""마지막 접근성·오류 상태 수정의 DOM 대역 회귀 시험. 네트워크는 쓰지 않는다."""
import json
import runpy

from test_B_b_app_dom import OLD_APP_JS as APP_JS, run_old_js as _run_js


def run_js(body):
    copy = runpy.run_path(str(APP_JS.parent.parent / "b_app_text.py")).get("POLISH_TEXT", {})
    _run_js("if (typeof UI !== 'undefined') Object.assign(UI, " + json.dumps(copy) + ");" + body)


def test_server_log_copy_instruction_only_appears_with_lines():
    run_js(r"""
      S.srv.data={log_tail:[]};
      renderSrvLog();
      const card=document.getElementById('srv-log-card');
      assert.match(card.textContent,/아직 기록이 없습니다/);
      assert.doesNotMatch(card.textContent,/옮기세요/);
      S.srv.data.log_tail=['가짜 기록 한 줄'];
      renderSrvLog();
      assert.match(card.textContent,/가짜 기록 한 줄/);
      assert.match(card.textContent,/새 줄이 생기면.*옮기세요/);
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
