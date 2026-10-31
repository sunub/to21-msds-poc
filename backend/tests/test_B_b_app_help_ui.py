"""도움말의 정보 보존과 문맥 이동. 가짜 API만 쓰며 브라우저 검증은 별도다."""
import html
import json
import re
import runpy

import pytest

from test_B_b_app_dom import STATIC, _Page, run_js


TOPICS = ('flow', 'score', 'source', 'setup', 'retest', 'prompt', 'servers', 'recovery', 'protection')
CONTEXT = {'s01': 'score', 's02': 'source', 's03': 'retest', 's04': 'score',
           's05': 'recovery', 's06': 'servers', 's08': 'flow', 's09': 'retest', 's10': 'score'}
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
      assert.equal(document.querySelectorAll('#help-glossary [data-glossary-term]').length,40);
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
      assert.equal(document.querySelectorAll('#help-glossary [data-glossary-term]').length,40);
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
      assert.equal(count(),40);
      assert.ok(document.getElementById('help-methods').textContent.includes(T('help.navigation.methods_failed')));
      await document.getElementById('help-reload-methods').click();
      assert.equal(document.getElementById('help-score').open,true);assert.equal(count(),40);
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
      S.journey.outcomes.t1.real={count:2,first_at:'2026-01-01T00:00:00Z',last_at:'2026-01-02T00:00:00Z'};
      const before=JSON.stringify(S.journey.outcomes);
      await go('s07'); document.getElementById('help-replay').click();
      await Promise.resolve(); await Promise.resolve();
      assert.equal(S.shell.route,'s08'); assert.equal(JSON.stringify(S.journey.outcomes),before);
    ''')
