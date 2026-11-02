"""단계 표시, 행동 줄, 자세히 서랍의 조작 계약 (phase app-steps, ADR-039). 가짜 값만 쓰며 브라우저 배치를 판정하지 않는다."""
import re

from test_B_b_app_dom import STATIC, run_js

BASE = r"""
const el=id=>document.getElementById(id);
const host=h('div',{id:'host'});document.body.append(host);
const STEPS=[
 {id:'pick',label:'Pick',done:true,summary:'Picked value',reachable:true},
 {id:'see',label:'See',done:false,summary:'Hint for see',reachable:true},
 {id:'send',label:'Send',done:false,summary:'Hint for send',reachable:false}];
"""


# ── 단계 표시 ─────────

def test_current_step_is_marked_and_says_it_is_current():
    run_js(BASE + r"""
      stepsRenderBar(host,{steps:STEPS,current:'see',onGo:()=>assert.fail('no click')});
      const now=host.querySelectorAll('[aria-current="step"]');
      assert.equal(now.length,1);assert.ok(now[0].textContent.includes('See'));
      assert.ok(now[0].textContent.includes(T('steps.current')));
      assert.equal(now[0].querySelector('button'),null);
      assert.equal(host.querySelector('ol').getAttribute('aria-label'),T('steps.a11y'));
    """)


def test_done_step_is_a_button_showing_the_choice_and_goes_back():
    run_js(BASE + r"""
      const went=[];stepsRenderBar(host,{steps:STEPS,current:'see',onGo:id=>went.push(id)});
      const buttons=host.querySelectorAll('button');assert.equal(buttons.length,1);
      assert.ok(buttons[0].textContent.includes('Pick'));assert.ok(buttons[0].textContent.includes('Picked value'));
      buttons[0].click();assert.deepEqual(went,['pick']);
    """)


def test_unreachable_step_cannot_be_pressed_and_is_announced():
    run_js(BASE + r"""
      const went=[];stepsRenderBar(host,{steps:STEPS,current:'see',onGo:id=>went.push(id)});
      const send=host.querySelectorAll('li').at(-1);
      assert.ok(send.textContent.includes('Send'));assert.equal(send.querySelector('button'),null);
      assert.equal(send.getAttribute('aria-disabled'),'true');assert.deepEqual(went,[]);
    """)


def test_reachable_later_step_is_a_button_and_done_step_explicitly_unreachable_is_not():
    run_js(BASE + r"""
      const went=[];
      stepsRenderBar(host,{steps:[{id:'a',label:'A',done:false,reachable:true},{id:'b',label:'B',done:false,reachable:true},
        {id:'c',label:'C',done:true,reachable:false}],current:'a',onGo:id=>went.push(id)});
      const items=host.querySelectorAll('li');
      items[1].querySelector('button').click();assert.deepEqual(went,['b']);
      assert.equal(items[2].querySelector('button'),null);
    """)


def test_redrawing_the_bar_replaces_the_old_one():
    run_js(BASE + r"""
      stepsRenderBar(host,{steps:STEPS,current:'pick',onGo:()=>{}});stepsRenderBar(host,{steps:STEPS,current:'see',onGo:()=>{}});
      assert.equal(host.querySelectorAll('ol').length,1);assert.equal(host.querySelectorAll('[aria-current="step"]').length,1);
    """)


def test_first_open_step_skips_finished_steps():
    run_js(BASE + r"""
      assert.equal(stepsFirstOpen(STEPS),'see');
      assert.equal(stepsFirstOpen([{id:'a',done:false},{id:'b',done:true}]),'a');
      assert.equal(stepsFirstOpen([{id:'a',done:true},{id:'b',done:true}]),'b');
      assert.equal(stepsFirstOpen([]),null);
    """)


# ── 행동 줄 ─────────

def test_next_action_is_always_the_last_slot():
    run_js(BASE + r"""
      const hits=[];const act=label=>({label,onClick:()=>hits.push(label)});
      stepsRenderActions(host,{note:'A note',back:act('Back'),secondary:act('Practice'),primary:act('Next')});
      const row=host.querySelector('.step-actions');const kids=row.children;
      assert.equal(kids.at(-1).textContent,'Next');assert.ok(kids.at(-1).classList.contains('primary'));
      assert.equal(kids[0].textContent,'Back');assert.ok(row.textContent.includes('A note'));
      for(const b of row.querySelectorAll('button'))b.click();
      assert.deepEqual(hits,['Back','Practice','Next']);
    """)


def test_blocked_next_action_explains_why_in_text_and_does_not_fire():
    run_js(BASE + r"""
      const hits=[];
      stepsRenderActions(host,{primary:{label:'Next',onClick:()=>hits.push('next'),disabled:true,reason:'Choose a value first'}});
      const row=host.querySelector('.step-actions'),next=row.children.at(-1);
      assert.equal(next.disabled,true);next.click();assert.deepEqual(hits,[]);
      assert.ok(row.textContent.includes('Choose a value first'));
      assert.ok(row.querySelector('.step-actions-say').textContent.includes('Choose a value first'));
    """)


def test_enabled_action_shows_no_reason_and_no_action_row_stays_valid():
    run_js(BASE + r"""
      stepsRenderActions(host,{primary:{label:'Next',onClick:()=>{},reason:'Should not show'}});
      assert.equal(host.textContent.includes('Should not show'),false);
      stepsRenderActions(host,{note:'Only a note'});
      assert.equal(host.querySelectorAll('.step-actions').length,1);
      assert.equal(host.querySelectorAll('button').length,0);assert.ok(host.textContent.includes('Only a note'));
    """)


def test_several_secondary_actions_keep_the_next_action_last():
    run_js(BASE + r"""
      stepsRenderActions(host,{secondary:[{label:'One',onClick:()=>{}},{label:'Two',onClick:()=>{}}],primary:{label:'Next',onClick:()=>{}}});
      assert.deepEqual(Array.from(host.querySelectorAll('button'),b=>b.textContent),['One','Two','Next']);
    """)


# ── 자세히 서랍 ─────────

DRAWER = BASE + r"""
const opener=h('button',{id:'open-details',type:'button'},'Open');host.append(opener);opener.focus();
const drawer=el('details-drawer');
let drawn=0;const body=node=>{drawn++;node.append(h('p',null,'Body text'));};
"""


def test_drawer_is_one_panel_with_a_place_in_the_page_and_draws_only_when_opened():
    run_js(DRAWER + r"""
      assert.equal(drawer.tagName,'dialog');assert.equal(drawer.open,false);assert.equal(drawn,0);
      drawerOpen({title:'Details title',render:body,trigger:opener});
      assert.equal(drawer.open,true);assert.equal(drawn,1);
      assert.ok(drawer.textContent.includes('Details title'));assert.ok(drawer.textContent.includes('Body text'));
      assert.equal(drawer.getAttribute('aria-labelledby'),el('details-drawer-title').id);
      assert.ok(drawer.contains(document.activeElement));
    """)


def test_drawer_close_button_closes_and_returns_focus():
    run_js(DRAWER + r"""
      drawerOpen({title:'T',render:body,trigger:opener});
      const close=drawer.querySelector('.drawer-close');assert.equal(close.textContent,T('steps.details.close'));
      close.click();assert.equal(drawer.open,false);assert.equal(document.activeElement,opener);
    """)


def test_drawer_escape_closes_and_returns_focus():
    run_js(DRAWER + r"""
      drawerOpen({title:'T',render:body,trigger:opener});
      const event={type:'cancel'};drawer.dispatchEvent(event);
      assert.equal(event.defaultPrevented,true);assert.equal(drawer.open,false);assert.equal(document.activeElement,opener);
    """)


def test_drawer_returns_focus_to_a_redrawn_trigger_with_the_same_id():
    run_js(DRAWER + r"""
      drawerOpen({title:'T',render:body,trigger:opener});
      opener.remove();const redrawn=h('button',{id:'open-details',type:'button'},'Open');host.append(redrawn);
      drawerClose();assert.equal(document.activeElement,redrawn);
    """)


def test_drawer_uses_the_focused_element_when_no_trigger_is_given():
    run_js(DRAWER + r"""
      drawerOpen({title:'T',render:body});drawerClose();assert.equal(document.activeElement,opener);
    """)


def test_only_one_drawer_is_open_at_a_time():
    run_js(DRAWER + r"""
      let shown=0;const native=drawer.showModal.bind(drawer);drawer.showModal=()=>{shown++;native();};
      const second=h('button',{id:'open-second',type:'button'},'Second');host.append(second);
      drawerOpen({title:'First',render:node=>node.append('First body'),trigger:opener});
      drawerOpen({title:'Second',render:node=>node.append('Second body'),trigger:second});
      assert.equal(shown,1);assert.equal(document.querySelectorAll('dialog#details-drawer').length,1);
      assert.equal(drawer.textContent.includes('First'),false);assert.ok(drawer.textContent.includes('Second body'));
      drawerClose();assert.equal(document.activeElement,second);
    """)


def test_drawer_has_no_folds_even_when_shared_helpers_make_them():
    run_js(DRAWER + r"""
      drawerOpen({title:'T',trigger:opener,render:node=>node.append(rawError('Raw message'),coreCodeRecord('code-value'),
        h('details',null,h('summary',null,'Outer'),h('p',null,'Outer text'),h('details',null,h('summary',null,'Inner'),h('p',null,'Inner text'))))});
      assert.equal(drawer.querySelectorAll('details').length,0);assert.equal(drawer.querySelectorAll('summary').length,0);
      for(const shown of ['Raw message','code-value','Outer','Outer text','Inner','Inner text',T('common.raw_error_title'),T('common.code_record_title')])
        assert.ok(drawer.textContent.includes(shown),shown);
      // 펼칠 것이 없으므로 제목에 펼치기나 보기를 쓰지 않는다.
      for(const hidden of [T('common.raw_error'),T('common.code_record')]) assert.equal(drawer.textContent.includes(hidden),false,hidden);
      assert.deepEqual(Array.from(drawer.querySelectorAll('h3'),n=>n.textContent).filter(t=>['Outer','Inner'].includes(t)),['Outer','Inner']);
    """)


def test_drawer_closes_when_another_screen_is_shown_but_not_on_redraw_of_the_same_screen():
    run_js(DRAWER + r"""
      S.shell.route='s02';drawerOpen({title:'T',render:body,trigger:opener});
      emit('screen_shown',{screen:'s02',args:{}});assert.equal(drawer.open,true);
      emit('screen_shown',{screen:'s05',args:{}});assert.equal(drawer.open,false);
    """)


def test_closing_a_closed_drawer_changes_nothing():
    run_js(DRAWER + r"""
      const other=h('button',{id:'other',type:'button'},'Other');host.append(other);other.focus();
      drawerClose();assert.equal(document.activeElement,other);assert.equal(drawer.open,false);
    """)


# ── 위치와 모양 ─────────

def test_steps_script_loads_after_shell_and_before_screens():
    html = (STATIC / 'index.html').read_text()
    names = re.findall(r'src="/static/js/([\w-]+)\.js"', html)
    assert names.index('shell') + 1 == names.index('steps')
    assert names.index('steps') < names.index('score')
    assert 'id="details-drawer"' in html


def test_step_css_has_fixed_action_row_and_right_drawer_without_motion():
    css = (STATIC / 'app.css').read_text()
    assert re.search(r'\.step-actions\s*\{[^}]*position:\s*sticky[^}]*bottom:\s*0', css)
    assert re.search(r'#details-drawer\s*\{[^}]*margin:\s*0 0 0 auto', css)
    assert re.search(r'\.steps\s*\{', css)
    assert re.search(r'\.step-card\s*\{', css)


def test_action_row_reaches_the_bottom_of_a_step_screen_without_a_page_scroll():
    # 행동 줄을 담은 자리가 단계 화면의 직계 항목이어야 margin-top:auto와 sticky가 듣는다. 11/2 브라우저에서 줄이 화면 가운데에 떴다.
    css = (STATIC / 'app.css').read_text()
    assert re.search(r'\.step-screen\s*>\s*:has\(>\s*\.step-actions\)\s*\{[^}]*display:\s*contents', css)
    # 제목과 설명이 위에 있으므로 창 높이로 정하면 페이지가 넘친다. 남은 높이를 채운다.
    step_screen = re.search(r'\.step-screen\s*\{([^}]*)\}', css).group(1)
    assert 'min-height' not in step_screen and re.search(r'flex:\s*1', step_screen)
    # 화면 구역의 아래 여백이 남으면 줄이 창 맨 아래에서 32px 떠 있다. `#screen-s06 > div`를 이기려면 #work로 시작해야 한다.
    assert re.search(r'#work > section:not\(\[hidden\]\) > :has\(\.step-screen\)\s*\{[^}]*margin-bottom:\s*0', css)
    assert re.search(r'\.work:has\(>\s*section:not\(\[hidden\]\)\s+\.step-screen\)\s*\{[^}]*flex-direction:\s*column', css)
    # 처리 알림 글은 맨 아래 줄 밑에 띠를 만들지 않는다. 오류는 계속 보인다.
    assert re.search(r'body:has\(.*?\.step-screen\)\s+#status:not\(\.error\)\s*\{[^}]*clip-path', css)


def test_drawer_leaves_the_top_bar_readable_so_cost_stays_visible():
    # 서랍이 위쪽 막대까지 덮으면 요금 글이 가려진다. 11/2 코덱스 판독과 캡처로 확인했다.
    css = (STATIC / 'app.css').read_text()
    assert re.search(r'#details-drawer\s*\{[^}]*top:\s*calc\(var\(--sticky-offset\) - 16px\)', css)
    assert re.search(r'#details-drawer\s*\{[^}]*height:\s*calc\(100vh - var\(--sticky-offset\) \+ 16px\)', css)
    assert re.search(r'#details-drawer::backdrop\s*\{[^}]*top:\s*calc\(var\(--sticky-offset\) - 16px\)', css)


def test_money_and_failure_read_differently_from_off_in_the_top_bar():
    # 꺼짐과 켜는 중이 같은 빈 원이었고, 비용 글이 작고 옅었다. 켜는 중에도 돈이 나간다.
    css = (STATIC / 'app.css').read_text()
    assert re.search(r'\.context-ai\.billing\s*\{[^}]*border-color:\s*var\(--accent\)', css)
    assert re.search(r'\.context-ai\.billing \.context-dot\s*\{[^}]*border-color:\s*var\(--accent\)', css)
    assert re.search(r'\.context-ai\.billing small:last-child\s*\{[^}]*color:\s*var\(--ink\)', css)
    assert re.search(r'#context-model\.error \.context-ai b\s*\{[^}]*color:\s*var\(--failure\)', css)

