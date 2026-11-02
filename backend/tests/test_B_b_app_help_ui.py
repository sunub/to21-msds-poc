"""도움말의 정보 보존과 문맥 이동. 가짜 API만 쓰며 브라우저 검증은 별도다."""
import html
import json
import re
import runpy

import pytest

from test_B_b_app_dom import STATIC, _Page, run_js


TOPICS = ('flow', 'score', 'source', 'data', 'setup', 'retest', 'prompt', 'servers', 'recovery', 'protection')
CONTEXT = {'s01': 'score', 's02': 'source', 's03': 'retest', 's04': 'score',
           's05': 'recovery', 's06': 'servers', 's10': 'score'}
ENV_NAMES = ('RUNPOD_VLLM_BASE_URL', 'RUNPOD_VLLM_API_KEY', 'RNGD_BASE_URL',
             'RNGD_API_KEY', 'RUNPOD_API_KEY', 'RNGD_SSH')


def copy_rows():
    return {row.split('|')[0]: html.unescape(row.split('|')[1]).replace('<br>', '\n')
            for row in (STATIC / 'design/COPY.md').read_text().splitlines()
            if re.match(r'^[a-z][a-z0-9_.]+\|', row)}


def nodes(node):
    if isinstance(node, dict):
        yield node
        for child in node['kids']:
            yield from nodes(child)


def content(node):
    return ''.join(content(child) for child in node['kids']) if isinstance(node, dict) else node


def guide_tree():
    page = _Page()
    page.feed((STATIC / 'guide.html').read_text())
    return list(nodes(page.root))


def test_guide_headings_and_deep_links_follow_copy_order():
    tree, copy = guide_tree(), copy_rows()
    assert [content(n) for n in tree if n['tag'] == 'h2'] == [copy[f'help.guide.{t}.title'] for t in TOPICS]
    for topic in TOPICS:
        section = next(n for n in tree if n['attrs'].get('id') == topic)
        assert copy[f'help.guide.{topic}.summary'] in content(section)
        assert any(n['tag'] == 'a' and n['attrs'].get('href') == '#' + topic for n in tree)


def test_data_chapter_explains_source_and_answers_in_both_help_pages():
    copy = copy_rows()
    keys = [k for k in copy if k.startswith('help.data.')]
    assert len(keys) >= 12
    page = _Page(); page.feed((STATIC / 'guide.html').read_text())
    section = next(n for n in nodes(page.root) if n['attrs'].get('id') == 'data')
    for key in keys:
        assert copy[key] in content(section), key
    text = content(section)
    for fact in ('data/pages/', 'data/silver/', 'data/gold', 'p001.txt', 'L001', 'meta.json', 'T21-S001.json'):
        assert fact in text
    run_js(setup() + r"""
      await go('s07',{helpTopic:'data'});
      const body=document.getElementById('help-data');
      assert.equal(body.open,true);
      for(const key of """ + json.dumps(keys) + r""")assert.ok(body.textContent.includes(T(key)),key);
    """)


def test_guide_environment_cells_have_correct_proxy_fact_and_no_secrets_or_addresses():
    source = (STATIC / 'guide.html').read_text()
    assert all(name in source for name in ENV_NAMES)
    descriptions = [content(n) for n in guide_tree() if n['tag'] in {'tr', 'li', 'p'}
                    and 'RUNPOD_VLLM_BASE_URL' in content(n)]
    assert descriptions
    assert all('터널' not in text for text in descriptions)
    assert any(copy_rows()['help.settings.runpod_url_meaning'] in text for text in descriptions)
    assert not re.search(r'https?://|\b(?:[A-Z][A-Z0-9_]*|finish_reason)\s*=\s*\S+', source)
    assert 'href="/static/app.css"' in source


def test_guide_preserves_commands_stages_rules_and_all_glossary_entries():
    page = _Page(); page.feed((STATIC / 'guide.html').read_text()); text = content(page.root)
    copy = copy_rows()
    for key in ['help.setup.command', 'help.protection.command', 'help.settings.runpod_url_fact',
                'help.recovery.columns', 'help.recovery.slow', 'help.protection.eval_locked']:
        assert copy[key] in text
    for key, value in copy.items():
        if key.startswith('jobs.stages.') or key.startswith('glossary.'):
            assert value in text, key
    for flag in ('--section', '--all', '--dry-run', '--system-file', '--base-run', '--show-prompt', '--json'):
        assert flag in text
    for fact in ('SECTION_PROMPT_VERSION', 'section_prompts.py', 'rows.py', 'rows_guide', '50%', '20자', '4번', 'docs/'):
        assert fact in text
    assert '합격' not in text
    assert '고급을 켜고' not in text


def setup():
    entries = runpy.run_path(str(STATIC.parent / 'b_app_text.py'))['glossary_entries']()
    return 'const helpEntries=' + json.dumps(entries) + r''';
      const helpCalls=[];
      api=async path=>{helpCalls.push(path);
        if(path==='/api/glossary')return {items:helpEntries};
        if(path==='/api/criteria')return {weights:{required:3},items:[{name:'Fake criterion',level:'required',target:.95,help:'Fake method'}]};
        throw new Error('Unexpected API '+path);
      };
    '''


def test_help_opens_requested_topic_and_loads_glossary_and_methods_without_model():
    run_js(setup() + r'''
      await go('s07',{helpTopic:'setup'});
      assert.equal(document.getElementById('screen-s07').hidden,false);
      assert.equal(document.getElementById('help-setup').open,true);
      assert.equal(document.getElementById('help-score').open,false);
      assert.equal(document.activeElement,document.getElementById('help-setup').querySelector('summary'));
      assert.equal(document.querySelectorAll('#help-glossary [data-glossary-term]').length,47);
      assert.ok(document.getElementById('help-methods').textContent.includes('Fake method'));
      assert.ok(document.getElementById('help-topics').textContent.includes(T('help.settings.runpod_url_meaning')));
      assert.ok(!document.getElementById('screen-s07').textContent.includes('⟦'));
      assert.deepEqual(helpCalls.sort(),['/api/criteria','/api/glossary']);
    ''')


@pytest.mark.parametrize('screen,topic', CONTEXT.items())
def test_each_screen_links_to_relevant_help_and_returns_to_same_selection(screen, topic):
    run_js(setup() + f"const screen={json.dumps(screen)}, topic={json.dumps(topic)};" + r'''
      for(const [id,view] of shellViews)if(!id.startsWith('help-'))shellViews.set(id,{render:()=>{}});
      S.focus={run:'fake-run',doc:'T21-X01',section:8,path:'fake.path'};
      await go(screen);
      const before=JSON.stringify(S.focus);
      const link=document.getElementById('help-context-'+screen).querySelector('a');
      assert.equal(link.getAttribute('href'),'/static/guide.html#'+topic);
      await link.click();
      assert.equal(S.shell.route,'s07');
      assert.equal(document.getElementById('help-'+topic).open,true);
      await document.getElementById('help-return').click();
      assert.equal(S.shell.route,screen);
      assert.equal(JSON.stringify(S.focus),before);
      assert.equal(document.querySelectorAll('#help-context-'+screen).length,1);
    ''')


def test_glossary_failed_load_can_retry_without_losing_help_or_target():
    run_js(setup() + r'''
      const good=api; let failOnce=true;
      api=async path=>{if(path==='/api/glossary'&&failOnce){failOnce=false;throw new Error('Fake failure');}return good(path);};
      await go('s07',{helpTopic:'recovery'});
      assert.ok(document.getElementById('help-glossary').textContent.includes(T('help.failed.title')));
      assert.equal(document.getElementById('help-recovery').open,true);
      await document.getElementById('help-reload-terms').click();
      assert.equal(document.querySelectorAll('#help-glossary [data-glossary-term]').length,47);
      assert.equal(document.getElementById('help-recovery').open,true);
      assert.ok(!document.getElementById('help-glossary').textContent.includes('⟦'));
    ''')


def test_terms_open_on_keyboard_focus_and_stay_inside_viewport():
    run_js(setup() + r'''
      await go('s07'); setupTip();
      const el=term('exposure');document.getElementById('help-glossary').append(el);
      assert.equal(el.getAttribute('tabindex'),'0');
      el.getBoundingClientRect=()=>({left:1430,right:1440,top:880,bottom:900});
      el.focus(); const tip=document.getElementById('tip');
      assert.equal(tip.hidden,false);
      assert.ok(tip.textContent.includes(T('glossary.exposure.meaning').split(' 예:')[0]));
      assert.ok(parseInt(tip.style.left)+tip.offsetWidth<=window.innerWidth);
      assert.ok(parseInt(tip.style.top)+tip.offsetHeight<=window.innerHeight);
      document.dispatchEvent({type:'keydown',key:'Escape'}); assert.equal(tip.hidden,true);
    ''')


def test_first_use_terms_exist_even_before_help_api_is_opened():
    run_js(r'''
      for(const key of ['weighted','silver','prompt','prompt_version','exposure','concentration_unit','extras']){
        const el=term(key);
        assert.equal(el.tagName,'abbr',key);
        assert.equal(el.textContent,T('glossary.'+key+'.term'));
        assert.equal(el.getAttribute('tabindex'),'0');
      }
    ''')


def test_score_and_source_explain_exposure_and_unit_at_first_use():
    from test_B_b_app_score_ui import FIXTURE
    from test_B_b_app_source_ui import fixture
    for script, screen, args in [(FIXTURE, 's01', '{}'), (fixture(), 's02', '{section:8}')]:
        run_js(script + f"await go('{screen}',{args});" + r'''
          for(const key of ['exposure','concentration_unit']){
            const terms=document.querySelectorAll('#screen-'+S.shell.route+' abbr');
            const found=Array.from(terms).find(el=>el.dataset.term===T('glossary.'+key+'.term'));
            assert.ok(found,key); assert.equal(found.getAttribute('tabindex'),'0');
          }
        ''')


def test_context_does_not_call_unknown_answer_kind_a_draft():
    run_js(r'''
      S.ctx.key='custom';S.shell.keys=[{id:'custom',label:'Custom answers'}];
      shellRenderContext();
      assert.ok(document.getElementById('global-context').textContent.includes('Custom answers'));
      assert.equal(document.querySelectorAll('#global-context abbr').length,0);
    ''')


def test_scoring_methods_retry_keeps_glossary_and_open_topic():
    run_js(setup() + r'''
      const good=api;let fail=true;
      api=async path=>{if(path==='/api/criteria'&&fail){fail=false;throw new Error('Fake methods failure');}return good(path);};
      await go('s07',{helpTopic:'score'});
      const count=()=>document.querySelectorAll('#help-glossary [data-glossary-term]').length;
      assert.equal(count(),47);
      assert.ok(document.getElementById('help-methods').textContent.includes(T('help.navigation.methods_failed')));
      await document.getElementById('help-reload-methods').click();
      assert.equal(document.getElementById('help-score').open,true);assert.equal(count(),47);
      assert.equal(helpCalls.filter(x=>x==='/api/glossary').length,1);
      assert.ok(document.getElementById('help-methods').textContent.includes('Fake method'));
    ''')


def test_readme_describes_new_screens_and_split_scripts_under_70_lines():
    source = (STATIC.parent / 'README_b_app.md').read_text()
    assert len(source.splitlines()) <= 70
    for word in ('STRUCTURE.md', 'COPY.md', 'UI_TEXT', 'js/', 'design/', 'S07'):
        assert word in source
    assert '화면은 그대로' not in source


def test_guide_has_no_unfilled_data_placeholders():
    assert not re.search(r'\{[A-Za-z_]+\}', (STATIC / 'guide.html').read_text())


def test_help_menu_return_uses_latest_screen_and_retry_does_not_reset_open_topics():
    run_js(setup() + r'''
      for(const [id] of shellViews)if(!id.startsWith('help-'))shellViews.set(id,{render:()=>{}});
      await go('s01'); await helpOpen('score'); await go('s04'); await go('s07');
      await document.getElementById('help-return').click(); assert.equal(S.shell.route,'s04');
      await helpOpen('prompt'); document.getElementById('help-prompt').open=false;
      await go('s04'); await helpOpen('setup');
      assert.equal(document.getElementById('help-prompt').open,false);
      assert.equal(document.getElementById('help-setup').open,true);
    ''')


def test_help_replay_is_an_explicit_action_and_preserves_success():
    from test_B_b_app_journey_ui import SETUP
    # 기록 API도 해당 시험의 가짜 구현으로 처리한다.
    run_js(SETUP + r'''
      S.help.loaded=true;
      saved.outcomes.t1.real={count:2,first_at:'2026-01-01T00:00:00Z',last_at:'2026-01-02T00:00:00Z'};
      await journeyEnsure();
      const before=JSON.stringify(S.journey.outcomes);
      await go('s07'); document.getElementById('help-replay').click();
      await flush();
      assert.equal(document.getElementById('guide-overlay').hidden,false);assert.equal(document.getElementById('guide-overlay').getAttribute('data-screen'),'G01'); assert.equal(JSON.stringify(S.journey.outcomes),before);
    ''')


def in_order(text, parts):
    at = -1
    for part in parts:
        next_at = text.find(part, at + 1)
        assert next_at > at, (part, text[:200])
        at = next_at


STEP_TEXT = {
    'source': ['help.source.step_choose', 'help.source.step_compare', 'help.source.step_send'],
    'retest': ['help.facts.trial_scope', 'help.facts.trial_ready', 'help.facts.trial_send', 'help.facts.trial_running', 'help.facts.trial_result'],
    'servers': ['help.servers.step_choose', 'help.servers.step_start', 'help.servers.step_wait', 'help.servers.step_stop'],
}


def test_help_describes_the_new_steps_in_order_in_both_help_pages():
    copy = copy_rows()
    names = {'source': ['steps.source.choose', 'steps.source.compare', 'steps.source.send'],
             'retest': ['steps.trial.target', 'steps.trial.model', 'steps.trial.prompt', 'steps.trial.running', 'steps.trial.result'],
             'servers': ['steps.server.choose', 'steps.server.start', 'steps.server.wait', 'steps.server.stop']}
    tree = guide_tree()
    for topic, keys in STEP_TEXT.items():
        section = content(next(n for n in tree if n['attrs'].get('id') == topic))
        for key, name in zip(keys, names[topic]):
            assert copy[name] in copy[key], (key, name)
        in_order(section, [copy[k] for k in keys])
    run_js(setup() + "const STEP_TEXT=" + json.dumps(STEP_TEXT) + r""";
      for(const [topic,keys] of Object.entries(STEP_TEXT)){
        await go('s07',{helpTopic:topic});
        const body=document.getElementById('help-'+topic).textContent;let at=-1;
        for(const key of keys){const next=body.indexOf(T(key),at+1);assert.ok(next>at,key);at=next;}
      }
    """)


def test_help_explains_made_missing_and_the_order_of_stopping_and_returning():
    copy = copy_rows()
    kinds = copy['help.source.kinds']
    for key in ('source.kinds.wrong', 'source.kinds.made', 'source.kinds.missing'):
        assert copy[key] in kinds, key
    order = copy['help.servers.order']
    assert copy['guide.ai.return'] not in order
    assert '시험으로 돌아가기' in order and '끄지 않습니다' in order
    section = lambda topic: content(next(n for n in guide_tree() if n['attrs'].get('id') == topic))
    assert kinds in section('source')
    assert order in section('servers')
    run_js(setup() + r"""
      await go('s07',{helpTopic:'source'});assert.ok(document.getElementById('help-source').textContent.includes(T('help.source.kinds')));
      await go('s07',{helpTopic:'servers'});assert.ok(document.getElementById('help-servers').textContent.includes(T('help.servers.order')));
    """)


def test_help_says_the_picture_is_for_position_and_the_text_box_is_for_reading():
    copy = copy_rows()
    note = copy['help.source.image_text']
    assert '위치' in note and '원문 글자' in note
    assert note in content(next(n for n in guide_tree() if n['attrs'].get('id') == 'source'))
    from test_B_b_app_text import _ui_leaves
    for key, value in _ui_leaves(runpy.run_path(str(STATIC.parent / 'b_app_text.py'))['UI_TEXT']):
        assert '그림을 읽' not in value, key


def test_retired_screen_has_no_help_text_or_link():
    for path in (STATIC / 'js/help.js', STATIC / 'guide.html', STATIC.parent / 'README_b_app.md'):
        assert not re.search(r's09|S09', path.read_text()), path
    run_js(setup() + r"""
      assert.equal(Object.values(HELP_CONTEXT).includes('s09'),false);assert.equal(Object.hasOwn(HELP_CONTEXT,'s09'),false);
      await go('s07');
      for(const link of document.querySelectorAll('#help-topics a'))assert.doesNotMatch(link.getAttribute('href')||'',/s09/);
    """)


def test_help_and_guide_page_do_not_describe_the_old_positions():
    tree_text = content(_page_root())
    from test_B_b_app_text import _ui_leaves
    leaves = dict(_ui_leaves(runpy.run_path(str(STATIC.parent / 'b_app_text.py'))['UI_TEXT']))
    old = ('필요할 때 문서 바꾸기', '필요할 때 정답 바꾸기', '여섯 단계를 차례로', '④ 해석한 값', '장비 상세와 설정 이름', '정답에만 있음은')
    for phrase in old:
        assert phrase not in tree_text, phrase
        for key, value in leaves.items():
            if key.split('.')[0] in ('guide', 'help', 'journey'):
                assert phrase not in value, (key, phrase)


def _page_root():
    page = _Page(); page.feed((STATIC / 'guide.html').read_text())
    return page.root


def test_help_returns_to_the_same_retest_step():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
      const realApi=api;api=async(p,o)=>p==='/api/glossary'?{items:[{term:'t',short:'s',example:'e',also:[]}]}:p==='/api/criteria'?{items:[]}:realApi(p,o);
      await go('s03',{doc:'T21-X01',section:8});jobsGoStep('prompt');
      await document.getElementById('help-context-s03').querySelector('a').click();assert.equal(S.shell.route,'s07');
      await document.getElementById('help-return').click();
      assert.equal(S.shell.route,'s03');assert.equal(jobsStep(),'prompt');atStep('prompt');
    """)


def test_help_returns_to_the_same_source_step():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      const realApi=api;api=async(p,o)=>p==='/api/glossary'?{items:[{term:'t',short:'s',example:'e',also:[]}]}:p==='/api/criteria'?{items:[]}:realApi(p,o);
      await go('s02',{run:'current',doc:'T21-X01',section:8});await flush();assert.equal(sourceStep(),'compare');
      const row=S.source.rowId;
      await document.getElementById('help-context-s02').querySelector('a').click();assert.equal(S.shell.route,'s07');
      await document.getElementById('help-return').click();await flush();
      assert.equal(S.shell.route,'s02');assert.equal(sourceStep(),'compare');assert.equal(S.source.rowId,row);
    """)


def test_six_expert_terms_and_stop_order_have_tips_and_entries():
    data = runpy.run_path(str(STATIC.parent / 'b_app_text.py'))
    words = {'twa': 'TWA', 'stel': 'STEL', 'acgih': 'ACGIH', 'ld50': 'LD50', 'lc50': 'LC50', 'ec50': 'EC50'}
    for key, word in words.items():
        entry = data['UI_TEXT']['glossary'][key]
        assert word in entry['term'] and ' 예: ' in entry['meaning'], key
        assert data['explain'](word), word
    assert data['explain']('stop_order')
    assert len(data['glossary_entries']()) == 47
    assert data['UI_TEXT']['help']['terms']['title'] == '화면에서 쓰는 말 47개'
    tree_text = content(_page_root())
    for key in (*words, 'stop_order'):
        assert data['UI_TEXT']['glossary'][key]['term'] in tree_text, key
    assert '화면에서 쓰는 말 47개' in tree_text


def test_compare_row_title_explains_expert_words_but_keeps_them_out_of_buttons():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      const plain=api;api=async(p,o)=>{const r=await plain(p,o);if(p.startsWith('/api/doc'))r.row_groups=r.row_groups.map(g=>({...g,title:'Fake part / ACGIH / TWA'}));return r;};
      await go('s02',{run:'current',doc:'T21-X01',section:8});await flush();pick(1).click();await flush();
      const head=document.querySelector('#source-selection .source-row-head h2');
      assert.equal(head.textContent,'Fake part / ACGIH / TWA');
      const tips=[...head.querySelectorAll('abbr')];assert.deepEqual(tips.map(n=>n.textContent),['ACGIH','TWA']);
      assert.ok(tips[0].getAttribute('data-tip').includes(T('glossary.acgih.meaning').split(' 예:')[0]));
      assert.ok(tips[1].getAttribute('data-tip').includes(T('glossary.twa.meaning').split(' 예:')[0]));
      for(const button of document.querySelectorAll('#source-values button'))assert.equal(button.querySelector('abbr'),null);
    """)


def test_problem_kind_legend_has_tips_for_made_and_missing():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
      await go('s02',{run:'current',doc:'T21-X01',section:8});await flush();
      const legend=document.querySelector('#source-values .source-kinds');
      const tips=[...legend.querySelectorAll('abbr')];
      assert.deepEqual(tips.map(n=>n.textContent),[T('source.kinds.wrong'),T('source.kinds.made'),T('source.kinds.missing')]);
      assert.ok(tips[1].getAttribute('data-tip').includes(T('glossary.invented.meaning').split(' 예:')[0]));
      assert.ok(tips[2].getAttribute('data-tip').includes(T('glossary.missing.meaning').split(' 예:')[0]));
      for(const key of ['wrong','made','missing'])assert.ok(legend.textContent.includes(T('steps.source.kind_notes.'+key)),key);
    """)


def test_stop_step_explains_the_order_of_returning_and_stopping_in_a_tip():
    from test_B_b_app_servers_ui import FIXTURE as SERVERS_FIXTURE
    run_js(SERVERS_FIXTURE + r"""
      await setup();atStep('stop');
      const tip=byId('servers-step-say').querySelector('abbr');assert.ok(tip);
      assert.equal(tip.textContent,T('steps.server.stop_order'));
      assert.ok(tip.getAttribute('data-tip').includes(T('glossary.stop_order.meaning').split(' 예:')[0]));
      assert.ok(tip.getAttribute('data-tip').includes('시험으로 돌아가기'));
      allOff();await shellPollServers();atStep('choose');assert.equal(byId('servers-step-say').querySelector('abbr'),null);
    """)


def test_readme_describes_the_new_flows():
    source = (STATIC.parent / 'README_b_app.md').read_text()
    for flow in ('문제 고르기 → 원문과 맞춰 보기 → 다시 시험으로 보내기',
                 '무엇을 → 어느 AI로 → 무엇을 시킬지 → 시험 → 결과',
                 '서버 고르기 → 켜기 → 준비 기다리기 → 쓰고 나서 끄기'):
        assert flow in source, flow
    assert '자세히' in source and '여러 문서' in source
    assert 'S08 처음 사용' not in source
    assert '용어 47개' in source
