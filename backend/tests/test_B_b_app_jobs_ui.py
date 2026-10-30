"""작업 탭의 상태 전환을 DOM 대역으로 검사한다. 서버와 네트워크는 부르지 않는다."""
from test_B_b_app_score_ui import run_js


SETUP = r"""
  const originalGetElement=document.getElementById;
  document.getElementById=id=>id==='job-log'?null:originalGetElement(id);
  const makeOptions = connected => ({
    models:[{tag:'first',label:'첫 모델',connected,option_label:'서버가 준 첫 선택지',rows_sections:[]},
      {tag:'second',label:'둘째 모델',connected:false,option_label:'서버가 준 둘째 선택지',rows_sections:[11]}],
    status_checked:true, docs:[{doc_id:'T21-X01'}],pages_dirs:[{name:'version9',value:'v9'}],
    default_pages_dir:'v9',run_names:{first:{v9:{dev10:'fake-run'}}},
    field_help:Object.fromEntries(['model','doc','pages','scope','prompt','base_run','dry_run','repeat','run_name','compare_label'].map(k=>[k, '도움말 '+k])),
    try_hint:{dry_run_forced:!connected,note:connected?'연결 안내':'연결 없음 안내'},
    job_ui_text:{send:'모델에 보내기',preview:'입력·안내문 보기',run_unavailable:'연결 필요 안내',more_summary:'더 하기 요약'},
    try_stage_help:{'① 보낸 입력':'입력 설명','② 안내문':'지시문 설명','③ 모델 원문 답':'원문 설명',
      '④ 읽은 결과':'중간 형식 설명','⑤ 펼친 TO21 칸':'최종 칸 설명','⑥ 점수 전 → 후':'점수 설명'}
  });
  let options=makeOptions(false), requests=[];
  api=async path=>{requests.push(path); if(path.startsWith('/api/options')) return options;
    if(path==='/api/jobs') return {jobs:[],running:[]}; throw new Error(path);};
  const tryCard=()=>document.getElementById('jobs-try-card');
  const dryBox=()=>tryCard().querySelectorAll('input').find(n=>n.getAttribute('id')==='try-dry');
  const sendButton=()=>tryCard().querySelector('.primary');
  const change=(el,value)=>el.events.change({target:{value,checked:value}});
"""


def test_jobs_try_offline_recovery_and_explicit_preview_choice():
    run_js(SETUP + r"""
      await loadOptions(); renderJobs();
      assert.equal(S.jobs.t.dry,true);
      assert.equal(dryBox().getAttribute('checked'),'');
      assert.equal(dryBox().getAttribute('disabled'),'');
      assert.equal(sendButton().textContent,'입력·안내문 보기');
      assert.equal(sendButton().getAttribute('disabled'),null);
      assert.match(tryCard().textContent,/연결 없음 안내/);
      assert.equal(document.getElementById('jobs-run-card').querySelector('.primary').getAttribute('disabled'),'');
      assert.match(document.getElementById('jobs-run-card').textContent,/연결 필요 안내/);
      options=makeOptions(true);
      await loadOptions(); renderJobs();
      assert.equal(S.jobs.t.model,'first'); // 행 형식이 없어도 연결된 첫 모델을 고른다.
      assert.equal(dryBox().getAttribute('disabled'),null);
      assert.equal(S.jobs.t.dry,true); // 자동 해제는 실행 방식을 바꾸지 않는다.
      change(dryBox(),false);
      assert.equal(sendButton().textContent,'모델에 보내기');
      assert.equal(sendButton().getAttribute('disabled'),null);
      const select=tryCard().querySelector('select');
      assert.equal(select.querySelectorAll('option')[0].textContent,'서버가 준 첫 선택지');
      S.jobs.t.model=null; S.jobs.t.dry=false; renderJobTry();
      assert.equal(sendButton().getAttribute('disabled'),'');
      options={...makeOptions(false),models:[]}; await loadOptions(); renderJobTry();
      assert.equal(sendButton().getAttribute('disabled'),'');
    """)


def test_jobs_poll_refreshes_options_keeps_edits_and_more_state():
    run_js(SETUP + r"""
      options=makeOptions(true); await loadOptions(); renderJobs();
      const more=document.getElementById('jobs-more-card');
      assert.match(more.textContent,/더 하기/);
      assert.equal(more.querySelector('.card-body').hidden,true);
      assert.match(more.textContent,/본 실행/);
      assert.match(more.textContent,/비교표/);
      more.querySelector('.card-toggle').click();
      assert.equal(JSON.parse(localStorage.getItem('b_app.cards'))['jobs-more-card'],false);
      S.jobs.t.text='가짜로 고친 안내문'; S.jobs.t.edit=true; S.jobs.r.name='내이름'; S.jobs.r.edited=true;
      S.jobs.c.title='내비교'; S.jobs.t.secs=new Set([8]);
      renderJobTry(); const editor=tryCard().querySelector('textarea');
      let interval;
      setTimeout=(_,ms)=>{interval=ms;return 1;}; clearTimeout=()=>{};
      await pollJobs();
      assert.equal(tryCard().querySelector('textarea'),editor); // 같은 옵션이면 편집 중인 DOM 유지
      assert.equal(interval,10000);
      document.getElementById('advanced').checked=true;
      options=makeOptions(false); await pollJobs();
      assert.ok(requests.includes('/api/options?advanced=1'));
      assert.equal(S.jobs.t.dry,true);
      assert.equal(dryBox().getAttribute('disabled'),'');
      assert.equal(S.jobs.t.text,'가짜로 고친 안내문');
      assert.equal(S.jobs.r.name,'내이름'); assert.equal(S.jobs.c.title,'내비교');
      assert.deepEqual([...S.jobs.t.secs],[8]);
      assert.equal(more.querySelector('.card-body').hidden,false);
      assert.equal(sendButton().textContent,'입력·안내문 보기');
    """)


def test_jobs_four_steps_field_help_and_six_result_descriptions():
    run_js(SETUP + r"""
      options=makeOptions(true); await loadOptions(); renderJobs();
      const content=tryCard().textContent;
      const steps=['① 모델','② 문서','③ 범위(항)','④ 돌리기'].map(s=>content.indexOf(s));
      assert.ok(steps.every(n=>n>=0)); assert.deepEqual(steps,[...steps].sort((a,b)=>a-b));
      for(const key of ['model','doc','pages','scope','prompt','base_run','dry_run']) assert.ok(content.includes('도움말 '+key));
      for(const key of ['repeat','run_name']) assert.ok(document.getElementById('jobs-run-card').textContent.includes('도움말 '+key));
      assert.ok(document.getElementById('jobs-compare-card').textContent.includes('도움말 compare_label'));
      const stages=tryStages({plan:{sections:{}},results:{11:{section:11,ok:true}},fields:{}});
      for(const [title,description] of Object.entries(options.try_stage_help)) {
        const summary=stages.map(n=>n.querySelector('summary')).find(n=>n?.textContent.includes(title));
        assert.ok(summary?.textContent.includes(description),title);
      }
    """)
