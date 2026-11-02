"""전체 화면 안내: 실제 모델/브라우저 없이 가짜 API와 DOM으로 동작을 검증한다."""
import pytest

from test_B_b_app_dom import run_js, STATIC
from test_B_b_app_journey_ui import SETUP


def test_g14_lists_usable_combinations_first():
    run_js(PRACTICE_SETUP + r"""
pack.label='Current pages';
const extra={id:'other-set',label:'Other pages',usable:true,docs:[{doc_id:'T21-X03',locked:false}]};
const unusable={id:'bad-set',label:'Unnumbered pages',usable:false,reason:'No line numbers',docs:extra.docs};
const answers=[
 {id:'silver/fake',label:'Draft',usable:true,docs:['T21-X01','T21-X03']},
 {id:'gold/other',label:'Reviewed',usable:true,docs:['T21-X03']},
 {id:'gold/locked-only',label:'Locked only',usable:true,docs:['T21-X99']},
 {id:'gold/empty',label:'Empty',usable:false,reason:'No answer files',docs:[]}];
const normal=api;
api=async(p,o)=>p==='/api/sets'?{sets:[unusable,extra,pack]}:p==='/api/keys'?{keys:answers}:normal(p,o);
await enter('G14');
const content=el('guide-content'),fold=content.querySelector('details');
assert.ok(fold);assert.equal(fold.open,false);
assert.equal(content.querySelectorAll('details').length,1);
assert.equal(fold.querySelector('summary').textContent,T('guide.defaults.unavailable',{count:9}));
const cards=content.querySelectorAll('.guide-choice-card');
assert.equal(cards.length,3);assert.ok(cards[0].textContent.includes(T('guide.defaults.current')));
assert.ok(cards.every(card=>!fold.contains(card)&&!card.querySelector('input').disabled));
assert.deepEqual(clone(cards.map(card=>[card.querySelector('input').dataset.set,card.querySelector('input').dataset.key])),
 [['fake-set','silver/fake'],['other-set','silver/fake'],['other-set','gold/other']]);
// The set name is a shared group label, not repeated in each answer card.
assert.ok(cards.slice(1).every(card=>!card.textContent.includes('Other pages')));
const group=cards[1].parentElement;
assert.equal(group.textContent.split('Other pages').length-1,1);
assert.equal(fold.querySelectorAll('input').length,9);
assert.ok(fold.querySelectorAll('input').every(input=>input.disabled));
for(const reason of ['No line numbers','No answer files',T('guide.defaults.no_answers')])assert.ok(fold.textContent.includes(reason));
fold.open=true;await flush();
await cards[1].querySelector('input').dispatchEvent({type:'change'});
assert.equal(el('guide-content').querySelector('details').open,true);
assert.equal(posted.length,0);
""")


def test_p01_says_what_applying_changes():
    run_js(PRACTICE_SETUP + r"""
const extra={id:'other-set',label:'Other pages',usable:true,docs:[{doc_id:'T21-X02'}]};
const answers=[{id:'silver/fake',label:'Draft',usable:true,docs:['T21-X02']},
 {id:'gold/other',label:'Reviewed',usable:true,docs:['T21-X02']}];
const normal=api;let broken=false,mismatch=false,release,delay=false;const calls=[];
api=async(p,o)=>{
 if(p==='/api/sets')return {sets:[pack,extra]};if(p==='/api/keys')return {keys:answers};
 if(p.startsWith('/api/runs')){
  calls.push(p);const key=new URLSearchParams(p.split('?')[1]).get('key');
  if(delay)await new Promise(resolve=>release=resolve);
  if(broken)throw Error('offline');
  return {key:{id:mismatch?'wrong':key},current:'selected',runs:key==='gold/other'?[
   {name:'selected',set:{id:'other-set'},run_kind:'sections',weighted:38.2},
   {name:'second',set:{id:'other-set'},run_kind:'sections',weighted:94.6},
   {name:'other-pages',set:{id:'fake-set'},run_kind:'sections'},
   {name:'answer-maker',set:{id:'other-set'},run_kind:'silver'},
   {name:'locked',set:{id:'other-set'},run_kind:'eval'},
   {name:'broken',set:{id:'other-set'},error:'unreadable'},
   {name:'wrong-key',set:{id:'other-set'},key:{id:'wrong'}}]:[]};
 }
 if(p.startsWith('/api/run/'))return {name:'selected',weighted:38.2,set:{id:'other-set'},key:{id:'gold/other'}};
 return normal(p,o);
};
await enter('G14');const original=clone(S.ctx);await guideClose();
shellOpenContext();await flush();
const pick=async(set,key)=>{el('context-set').value=set;el('context-key').value=key;await el('context-key').dispatchEvent({type:'change'});await flush();};
await pick('other-set','silver/fake');
assert.equal(el('context-result-effect').textContent,T('context.picker.results_empty'));
assert.equal(el('context-result-effect').getAttribute('aria-live'),'polite');
await pick('other-set','gold/other');
assert.equal(el('context-result-effect').textContent,T('context.picker.results_found',{count:2}));
el('context-set').value='fake-set';await el('context-set').dispatchEvent({type:'change'});await flush();
assert.equal(el('context-result-effect').textContent,T('context.picker.results_found',{count:1}));
assert.ok(calls.some(p=>new URLSearchParams(p.split('?')[1]).get('key')==='gold/other'));
assert.deepEqual(S.ctx,original);assert.equal(posted.length,0);
// A stale candidate cannot overwrite the new one or a newly opened dialog.
delay=true;const late=pick('other-set','gold/other');await flush();delay=false;
await pick('other-set','silver/fake');release();await late;
assert.equal(el('context-result-effect').textContent,T('context.picker.results_empty'));
delay=true;const closed=pick('other-set','gold/other');await flush();delay=false;
shellCloseContext();shellOpenContext();await flush();release();await closed;
assert.equal(el('context-result-effect').textContent,T('context.picker.results_empty'));
broken=true;await pick('other-set','gold/other');
assert.ok(el('context-result-effect').textContent.includes(T('context.picker.results_failed')));
assert.ok(!el('context-result-effect').textContent.includes(T('context.picker.results_empty')));
assert.equal(el('context-apply').disabled,false);
broken=false;mismatch=true;await pick('other-set','gold/other');
assert.ok(el('context-result-effect').textContent.includes(T('context.picker.results_failed')));
mismatch=false;shellCloseContext();await guideOpen();await guideShow('G14');
const guidePick=async key=>{const n=guideNode().querySelectorAll('input').find(n=>n.dataset.set==='other-set'&&n.dataset.key===key);await n.dispatchEvent({type:'change'});};
await guidePick('gold/other');
assert.ok(guideNode().querySelector('.guide-choice-preview').textContent.includes(T('context.picker.results_found',{count:2})));
assert.ok(guideNode().querySelector('.guide-choice-preview').textContent.includes('38.2'));
await guidePick('silver/fake');
assert.ok(guideNode().querySelector('.guide-choice-preview').textContent.includes(T('context.picker.results_empty')));
assert.deepEqual(S.ctx,original);assert.equal(posted.length,0);
""")


def test_guide_body_fits_at_900px():
    import re
    from test_B_b_app_audit_ui import css_rules

    rules = css_rules()
    for width in (1280, 1440, 1680):
        def declarations(selector):
            result = {}
            for selectors, body, parents in rules:
                if selector not in [s.strip() for s in selectors.split(',')]:
                    continue
                active = True
                for parent in parents:
                    for bound, axis, value in re.findall(r'(min|max)-(width|height):\s*(\d+)px', parent):
                        size = width if axis == 'width' else 900
                        active &= size >= int(value) if bound == 'min' else size <= int(value)
                if active:
                    result.update(re.findall(r'([\w-]+)\s*:\s*([^;]+)', body))
            return result

        inner = declarations('.guide-inner')
        body = declarations('.guide-step-body')
        action = declarations('.guide-action')
        button = declarations('.guide-action > .primary')
        variables = {**declarations(':root'), **inner}

        def pixels(value):
            while 'var(' in value:
                value = re.sub(r'var\((--[\w-]+)\)', lambda m: variables[m[1]], value)
            return float(value.removesuffix('px'))

        assert inner['grid-template-rows'].replace(' ', '') == 'autominmax(0,1fr)auto'
        assert body['min-height'] == '0'
        assert body['overflow'] == 'auto'
        assert action.get('position', 'static') not in ('absolute', 'fixed')
        assert pixels(body.get('padding-bottom', '0px')) >= pixels(button['min-height'])
        assert pixels(body.get('scroll-padding-bottom', '0px')) >= pixels(button['min-height'])

    run_js(PRACTICE_SETUP + r"""
await readyTarget('G08');listed=[trialJob(true)];reply={plan};
await el('guide-next').click();await guidePollTrial();
assert.equal(guideNode().getAttribute('data-variant'),'G08-done');
const body=guideNode().querySelector('.guide-step-body'),footer=guideNode().querySelector('.guide-action');
assert.equal(body.parentElement,footer.parentElement);assert.equal(body.contains(footer),false);
assert.ok(body.contains(el('guide-result-summary')));assert.ok(footer.contains(el('guide-next')));
const details=el('guide-plan-details');assert.ok(details);assert.equal(details.open,false);
assert.ok(details.textContent.includes(plan.sections['8'].prompt_hash));
assert.ok(el('guide-result-summary').textContent.includes(T('guide.practice.done')));
details.open=true;assert.ok(body.contains(details));assert.equal(posted.length,1);
""")


def test_g15_shows_only_real_records():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();await guideOpen();await guideShow('G15');
assert.equal(UI.guide.example.records,undefined);
assert.ok(el('guide-records').textContent.includes(T('journey.history.none')));
// In-memory practice state and the mockup must never manufacture a saved outcome.
S.guide.session={source:'2024-03-02T20:01:00.000Z',practice:42,trial:'2024-03-02T20:03:00.000Z'};
guideRender();assert.ok(!guideNode().textContent.includes(T('guide.records.count',{count:42})));
const at='2024-03-02T23:05:06.000Z';
await journeyChange(j=>{j.outcomes.t1.real={first_at:at,last_at:at,count:2};
 j.outcomes.t2.practice={first_at:at,last_at:at,count:7,last_job:'practice-7'};});
guideRender();el('guide-records').querySelector('details').open=true;
const local=when(at);
for(const count of [2,7])assert.ok(el('guide-records').textContent.includes(T('journey.history.first_count',{time:local,count})));
assert.ok(el('guide-records').textContent.includes(T('journey.history.none')));
assert.ok(!el('guide-example').textContent.includes(local));
assert.ok(!el('guide-example').textContent.includes(T('guide.records.title')));
// The guide uses the same local clock in its readiness, session and history views.
S.guide.session.source=at;await guideShow('G12');
assert.ok(el('guide-session-records').textContent.includes(local));
await guideShow('G10');S.shell.serverAt=at;guideRender();
assert.ok(el('guide-content').textContent.includes(T('guide.ai.checked',{time:local})));
""")


@pytest.mark.parametrize('screen', ['G05', 'G07', 'G08', 'G11'])
def test_reload_mid_guide_reopens_last_confirmed_screen(screen):
    run_js(PRACTICE_SETUP + f"const screen={screen!r};" + r"""
saved.progress.guide=guideSaved(screen);ready=true;
if(['G08','G11'].includes(screen)){
 const dry=screen==='G08';listed=[trialJob(dry,'running')];
 saved.pending={attempt:'saved-attempt',job:'g1',mode:dry?'practice':'real',started_at:'2026-10-31T01:00:00.000Z'};
}
// go() leaves #s01 in the address bar, including while the guide is open.
location.hash='#s01';await start();await flush();
assert.equal(guideNode().hidden,false);assert.equal(guideScreen(),screen);
assert.equal(el('guide-resume').hidden,true);assert.equal(posted.length,0);
if(screen==='G05')assert.ok(requests.includes('/api/servers'));
if(['G08','G11'].includes(screen))assert.equal(S.guide.trial.id,'g1');
await el('guide-close').click();await flush();
assert.ok(saved.progress.dismissed_at);assert.equal(guideNode().hidden,true);
assert.equal(el('guide-resume').hidden,false);
// Replay a fresh page boot with the persisted close decision.
S.guide.bootChecked=false;S.shell.navigation=1;emit('shell_started',{hash:'#s01'});guideSync();await flush();
assert.equal(guideNode().hidden,true);assert.equal(el('guide-resume').hidden,false);
await el('guide-resume-button').click();await flush();
assert.equal(guideNode().hidden,false);assert.equal(guideScreen(),screen);
assert.equal(saved.progress.dismissed_at,null);assert.equal(el('guide-resume').hidden,true);
S.guide.open=false;guideBackground(false);guideNode().hidden=true;
S.guide.bootChecked=false;S.shell.navigation=1;guideSync();await flush();
assert.equal(guideNode().hidden,false);assert.equal(guideScreen(),screen);assert.equal(posted.length,0);
// An explicit different screen continues to take priority over guide resumption.
S.guide.open=false;guideBackground(false);guideNode().hidden=true;
S.guide.bootChecked=false;emit('shell_started',{hash:'#s03'});guideSync();await flush();
assert.equal(guideNode().hidden,true);assert.equal(posted.length,0);
""")


def test_g07_card_names_the_criterion():
    run_js(PRACTICE_SETUP + r"""
const criteria=Object.keys(UI.score.item_names);
const exposure=criteria.find(name=>name.startsWith('8'));
const different=criteria.find(name=>name.startsWith('14'));
for(const criterion of [exposure,different]){
 runData.status_text.top_problem.name=criterion;value.items=[criterion];
 await readyTarget('G07');
 assert.equal(el('guide-practice').querySelector('h2').textContent,UI.score.item_names[criterion]);
 if(criterion===exposure){
  const definition=UI.glossary.exposure.meaning.split(' 예: ')[0];
  const copy=el('guide-content').textContent;
  assert.ok(copy.includes(definition));
  assert.ok(copy.indexOf(definition)<copy.indexOf(T('guide.source.ai_value')));
 }
 await el('guide-next').click();
 assert.equal(el('guide-practice').querySelector('h2').textContent,UI.score.item_names[criterion]);
}
assert.equal(posted.length,0);
""")


def test_reload_waits_for_context_before_loading_last_screen():
    run_js(PRACTICE_SETUP + r"""
saved.progress.guide=guideSaved('G07');location.hash='#s01';
S.ctx={version:1,set:null,key:null};S.shell.contextLoaded=false;
const normal=api;let release;
api=(p,o)=>p==='/api/sets'?new Promise(resolve=>release=()=>resolve({sets:[pack],default:pack.id})):normal(p,o);
const boot=start();await flush();
assert.equal(guideNode().hidden,true);
release();await boot;await flush();
assert.equal(guideScreen(),'G07');assert.equal(S.guide.source.state,'waiting');
assert.ok(requests.some(p=>p.startsWith('/api/doc?')&&p.includes('key=silver%2Ffake')));
assert.equal(posted.length,0);
""")


def test_try_model_and_value_are_plain():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
const visibleText=node=>{
 if(typeof node==='string')return node;
 if(node.hidden)return '';
 if(node.tagName==='details'&&!node.open)return visibleText(node.querySelector('summary'));
 return node.children.map(visibleText).join('');
};
const tags=Object.keys(UI.context.models), chosen=tags[0], previous=tags[1];
options.models=[{tag:chosen,connected:false}];
const normal=api;api=(p,o)=>p.startsWith('/api/runs')?Promise.resolve({runs:[{name:'base',model_tag:previous,docs:['T21-X01']}]}):normal(p,o);
for(const field of ['q','comp_ref']){
 await go('s03',{doc:'T21-X01',section:8,base_run:'base',path:`msds[0].exposure_limits[2].${field}`,
  kind:'wrong',expected:5,actual:8,line:'p2:L3'});
 stepTo('target');const focus=el('jobs-focus');
 assert.doesNotMatch(visibleText(focus),/msds\[0\]\.|comp_ref|\bq\b/);
 assert.ok(visibleText(focus).includes(UI.source.field_names[field] || UI.source.fields[field]));
 // 기술 경로는 접힘이 아니라 자세히 서랍에 있다.
 assert.equal(focus.querySelector('details'),null);assert.ok(openDrawer().textContent.includes(S.focus.path));drawerClose();
 stepTo('model');assert.ok(visibleText(el('jobs-try')).includes(UI.context.models[chosen]));
 assert.equal(el('jobs-model').querySelector('b').textContent,UI.context.models[chosen]);
 assert.ok(visibleText(el('jobs-try')).includes(T('jobs.focus.model_difference',{model:UI.context.models[previous]})));
 assert.doesNotMatch(visibleText(el('jobs-try')),/⟦|undefined/);
}
S.jobs.runs[0].model_tag=chosen;jobsRenderTry();
assert.ok(!el('jobs-try').textContent.includes(T('jobs.focus.model_difference',{model:UI.context.models[chosen]})));
S.jobs.runs.push({name:'other-base',model_tag:previous,docs:['T21-X01']});stepTo('target');
el('jobs-base').value='other-base';await el('jobs-base').dispatchEvent({type:'change'});
stepTo('model');assert.ok(visibleText(el('jobs-try')).includes(T('jobs.focus.model_difference',{model:UI.context.models[previous]})));
options.models[0].connected=true;await jobsLoadOptions();jobsRenderTry();
assert.ok(visibleText(el('jobs-try')).includes(UI.context.models[chosen]));
assert.ok(visibleText(el('jobs-try')).includes(T('jobs.focus.model_difference',{model:UI.context.models[previous]})));
assert.equal(posted.length,0);
""")
    run_js(PRACTICE_SETUP + r"""
const tags=Object.keys(UI.context.models),chosen=tags[0],previous=tags[1];
runData.model_tag=previous;
const normal=api;api=(p,o)=>p==='/api/options'?Promise.resolve({...options,models:[{tag:chosen,connected:false}]}):normal(p,o);
await readyTarget('G08');
assert.ok(el('guide-practice').textContent.includes(UI.context.models[chosen]));
assert.ok(el('guide-practice').textContent.includes(T('jobs.focus.model_difference',{model:UI.context.models[previous]})));
assert.doesNotMatch(el('guide-practice').textContent,/⟦|undefined/);
S.guide.trial.state='success';S.guide.trial.result={plan};S.guide.trial.job={dry_run:true};guideRender();
assert.ok(el('guide-practice').textContent.includes(UI.context.models[chosen]));
assert.ok(el('guide-practice').textContent.includes(T('jobs.focus.model_difference',{model:UI.context.models[previous]})));
assert.equal(posted.length,0);
""")


def test_g02_choice_skips_unchosen_practice():
    run_js(PRACTICE_SETUP + r"""
await enter('G01');await el('guide-next').click();assert.equal(guideScreen(),'G02');
assert.equal(el('guide-next').disabled,true);
assert.ok(guideNode().textContent.includes(T('guide.choices.disabled')));
assert.ok([...guideNode().querySelectorAll('input')].every(n=>!n.checked));
const choose=async name=>{const box=el('guide-choice-'+name);box.checked=!box.checked;await box.dispatchEvent({type:'change'});await flush();};
await choose('source');assert.equal(el('guide-next').disabled,false);
assert.deepEqual(saved.progress.guide.choices,['source']);assert.deepEqual(saved.progress.guide.skipped,['p2','p3']);
await el('guide-next').click();assert.equal(guideScreen(),'G03');await el('guide-back').click();
assert.equal(guideScreen(),'G02');assert.equal(el('guide-choice-source').checked,true);
await guideShow('G06');await el('guide-next').click();assert.equal(guideScreen(),'G07');
await el('guide-next').click();await el('guide-next').click();assert.equal(guideScreen(),'G12');
assert.ok(el('guide-progress').textContent.includes(T('guide.skipped')));assert.equal(S.journey.outcomes.t2.practice,null);
await el('guide-back').click();assert.equal(guideScreen(),'G07');
await guideShow('G02');await choose('source');assert.equal(el('guide-next').disabled,true);
await journeyLoad();await guideOpen({resume:true});assert.equal(guideScreen(),'G02');assert.equal(el('guide-next').disabled,true);
await choose('retest');await guideShow('G06');await el('guide-next').click();assert.equal(guideScreen(),'G08');
await el('guide-skip-practice').click();assert.equal(guideScreen(),'G09');
await el('guide-next').click();assert.equal(guideScreen(),'G10');
await guideShow('G02');await choose('retest');await choose('ai');
await guideShow('G06');await el('guide-next').click();assert.equal(guideScreen(),'G10');
await guideShow('G02');await choose('ai');await choose('score');
await guideShow('G06');await el('guide-next').click();assert.equal(guideScreen(),'G07');
assert.equal(posted.length,0);
""")


def test_g14_preview_and_apply_context():
    run_js(PRACTICE_SETUP + r"""
const extra={id:'other-set',label:'Other documents',usable:true,docs:[{doc_id:'T21-X03',group:'dev'}]};
const answers=[{id:'silver/fake',label:'Draft',usable:true,kind:'silver',docs:['T21-X01','T21-X02','T21-X03']},
 {id:'gold/other',label:'Reviewed',usable:true,kind:'gold',docs:['T21-X01','T21-X02','T21-X03']},
 {id:'gold/locked',label:'Locked',usable:false,reason:'Unavailable',docs:[]}];
const normal=api;let failPreview=false, delayPreview=false, release;const previewCalls=[];
api=async(p,o)=>{
 if(p==='/api/sets')return {sets:[pack,extra],default:pack.id};
 if(p==='/api/keys')return {keys:answers,default:answers[0].id};
 if(p.startsWith('/api/runs'))return {current:'current-other',runs:[runData,
  {name:'current-other',set:{id:'other-set'},run_kind:'sections'},
  {name:'excluded',set:{id:'other-set'},run_kind:'silver'}]};
 if(p.startsWith('/api/run/')){previewCalls.push(p);if(failPreview)throw Error('preview unreadable');
  if(delayPreview)await new Promise(r=>release=r);
  const other=p.includes('current-other');return {name:other?'current-other':'fake-run',weighted:other?63.7:71,
   set:{id:other?'other-set':'fake-set'},key:{id:new URLSearchParams(p.split('?')[1]).get('key'),label:'Reviewed'}};}
 return normal(p,o);
};
await enter('G14');assert.equal(guideScreen(),'G14');assert.equal(el('guide-next').disabled,true);
assert.ok(guideNode().textContent.includes(T('guide.defaults.disabled')));
const pick=(set,key)=>guideNode().querySelectorAll('input').find(n=>n.dataset.set===set&&n.dataset.key===key);
const original=clone(S.ctx);let applied=0;const apply=shellApplyContext;
shellApplyContext=(...args)=>{applied++;return apply(...args);};
await pick('other-set','gold/other').dispatchEvent({type:'change'});await flush();
assert.equal(el('guide-next').disabled,false);assert.deepEqual(S.ctx,original);
assert.ok(previewCalls.some(p=>p==='/api/run/current-other?key=gold%2Fother'));
assert.equal(guideNode().querySelectorAll('.guide-choice-preview').length,1);
assert.ok(guideNode().querySelector('.guide-choice-preview').textContent.includes('63.7'));
assert.ok(!previewCalls.some(p=>p.includes('excluded')));
await el('guide-keep-context').click();assert.equal(guideScreen(),'G15');assert.deepEqual(S.ctx,original);assert.equal(applied,0);
await guideShow('G14');failPreview=true;
await pick('other-set','gold/other').dispatchEvent({type:'change'});await flush();
assert.equal(el('guide-next').disabled,false);assert.ok(guideNode().querySelector('[role="alert"]'));
await el('guide-next').click();await flush();assert.equal(guideScreen(),'G15');assert.equal(applied,1);
assert.deepEqual(S.ctx,{version:1,set:'other-set',key:'gold/other'});
assert.deepEqual(JSON.parse(localStorage.getItem('b_app.context')),S.ctx);
assert.ok(el('global-context').textContent.includes('Other documents'));
// 늦은 이전 후보 응답이 현재 카드를 덮지 않는다.
failPreview=false;await guideShow('G14');delayPreview=true;
const late=pick('fake-set','silver/fake').dispatchEvent({type:'change'});await flush();delayPreview=false;
await pick('other-set','gold/other').dispatchEvent({type:'change'});release();await late;await flush();
assert.ok(guideNode().querySelector('.guide-choice-preview').textContent.includes('63.7'));
assert.equal(posted.length,0);
""")


def test_guide_events_have_no_content():
    run_js(PRACTICE_SETUP + r"""
const telemetry=[];
for(const name of ['onboarding_step_viewed','onboarding_action','practice_result','onboarding_completed'])
 on(name,data=>telemetry.push({name,data:clone(data)}));
Date.now=()=>1200;
await readyTarget('G07');await el('guide-next').click();
await guideShow('G08');listed=[trialJob(true)];reply={plan};await el('guide-next').click();
ready=true;await guideShow('G11');listed=[trialJob(false,'done','g2')];reply=trialResult(true);
post=async()=>({id:'g2'});await el('guide-next').click();
await guideShow('G15');await el('guide-next').click();await flush();
assert.ok(telemetry.some(e=>e.name==='onboarding_step_viewed'&&e.data.screen==='G11'));
assert.ok(telemetry.some(e=>e.name==='onboarding_action'&&e.data.screen==='G07'&&e.data.action==='next'));
const results=telemetry.filter(e=>e.name==='practice_result').map(e=>e.data);
assert.deepEqual(results.map(e=>[e.scenario,e.source,e.outcome]),[['p1','real','success'],['p2','practice','success'],['p3','real','success']]);
assert.ok(results.every(e=>Number.isFinite(e.latency_ms)&&e.latency_ms>=0));
assert.equal(telemetry.filter(e=>e.name==='onboarding_completed').length,1);
assert.ok(events.some(e=>e.type==='evidence'&&e.mismatch));assert.ok(events.some(e=>e.type==='result'&&e.section_ok));
const allowed={onboarding_step_viewed:['screen'],onboarding_action:['screen','action'],
 practice_result:['scenario','source','outcome','latency_ms'],onboarding_completed:[]};
for(const e of telemetry)assert.deepEqual(Object.keys(e.data).sort(),allowed[e.name].sort());
for(const secret of ['T21-X02','fake-run','fake.value',value.text,view.lines[0].text,'Invented section extraction instruction'])
 assert.ok(!JSON.stringify(telemetry).includes(secret));
""")


def test_guide_column_keeps_cta_visible():
    import re
    from test_B_b_app_audit_ui import css_rules

    rules = css_rules()
    inner = next(body for selector, body, parents in rules if selector == '.guide-inner' and not parents)
    assert re.search(r'grid-template-rows:\s*auto minmax\(0,\s*1fr\) auto', inner)
    assert re.search(r'min-height:\s*0', inner)
    assert re.search(r'overflow:\s*hidden', inner)
    assert any(selector == '.guide-step-body' and re.search(r'overflow:\s*auto', body) for selector, body, _ in rules)
    assert any(selector == 'body.guide-open' and re.search(r'overflow:\s*hidden', body) for selector, body, _ in rules)
    run_js(PRACTICE_SETUP + r"""
await enter('G01');
for(const screen of ['G01','G02','G03','G04','G05','G06','G07','G08','G09','G10','G11','G12','G13','G14','G15']){
 await guideShow(screen);const inner=guideNode().querySelector('.guide-inner'),body=inner.querySelector('.guide-step-body');
 const footer=inner.querySelector('.guide-action');assert.equal(footer.parentElement,inner);
 assert.ok(!body.contains(footer));assert.ok(footer.contains(el('guide-next')));
 assert.equal(inner.children.at(-1),footer);assert.ok(document.body.classList.contains('guide-open'));
 assert.doesNotMatch(guideNode().textContent,/⟦|undefined|NaN/);
}
await guideClose();assert.equal(document.body.classList.contains('guide-open'),false);
""")


def test_guide_practice_events_cover_failure_cancel_skip_without_duplicates():
    run_js(PRACTICE_SETUP + r"""
const results=[];on('practice_result',e=>results.push(e));
Date.now=()=>1000;ready=true;await readyTarget('G11');listed=[trialJob()];reply=trialResult(false);
await el('guide-next').click();await guidePollTrial();guideRender();
assert.deepEqual(results.map(e=>[e.scenario,e.source,e.outcome]),[['p3','real','failed']]);
await el('guide-skip-practice').click();assert.equal(results.at(-1).outcome,'skipped');
await guideShow('G08');listed=[trialJob(true,'running')];await el('guide-next').click();
await el('guide-cancel-practice').click();assert.equal(results.at(-1).outcome,'cancelled');
await guideShow('G07');value.lines=[];await guideShow('G07');await el('guide-next').click();
assert.deepEqual([results.at(-1).scenario,results.at(-1).outcome],['p1','failed']);
assert.ok(results.every(e=>Object.keys(e).sort().join(',')==='latency_ms,outcome,scenario,source'));
assert.equal(S.journey.outcomes.t1.real,null);assert.equal(S.journey.outcomes.t2.real,null);
""")


def test_g14_missing_result_zero_score_and_key_repair():
    run_js(PRACTICE_SETUP + r"""
const original=api;let previewScore=0, mismatch=false, noRuns=false, brokenList=false;
api=async(p,o)=>{
 if(p==='/api/sets'&&brokenList)throw Error('list unavailable');
 if(p.startsWith('/api/runs')&&noRuns)return {runs:[]};
 if(p.startsWith('/api/run/'))return {...runData,weighted:previewScore,key:{id:mismatch?'wrong':S.ctx.key||'silver/fake'}};
 return original(p,o);
};
await enter('G14');let input=guideNode().querySelector('input');await input.dispatchEvent({type:'change'});
assert.ok(guideNode().querySelector('.guide-choice-preview').textContent.includes('0.0'));
assert.equal(el('guide-next').disabled,false);
mismatch=true;await input.dispatchEvent({type:'change'});assert.ok(guideNode().querySelector('[role="alert"]'));
noRuns=true;await input.dispatchEvent({type:'change'});
assert.ok(guideNode().querySelector('.guide-choice-preview').textContent.includes(T('guide.defaults.empty')));
assert.equal(el('guide-next').disabled,false);
await guideShow('G05');S.ctx.key=null;await guideCheckReadiness();assert.equal(el('guide-ready-key').dataset.state,'absent');
await el('guide-next').click();assert.equal(guideScreen(),'G14');
await guideNode().querySelector('input').dispatchEvent({type:'change'});await el('guide-next').click();
assert.equal(guideScreen(),'G05');assert.equal(S.ctx.key,'silver/fake');
brokenList=true;await guideShow('G14');assert.ok(guideNode().querySelector('[role="alert"]'));
assert.equal(el('guide-next').disabled,true);await el('guide-keep-context').click();assert.equal(guideScreen(),'G15');
assert.equal(posted.length,0);
""")


@pytest.mark.parametrize("leave", ["keep", "back", "close", "replay"])
def test_g14_repair_return_does_not_leak_into_later_defaults(leave):
    run_js(PRACTICE_SETUP + f"const leave={leave!r};" + r"""
await enter('G05');S.ctx.key=null;await guideCheckReadiness();await el('guide-next').click();
assert.equal(guideScreen(),'G14');
if(leave==='keep')await el('guide-keep-context').click();
if(leave==='back')await el('guide-back').click();
if(leave==='close'){await guideClose();await guideOpen({resume:true});}
if(leave==='replay')await guideOpen({replay:true});
await guideShow('G14');await guideNode().querySelector('input').dispatchEvent({type:'change'});
await el('guide-next').click();assert.equal(guideScreen(),'G15');
""")


GUIDE_SETUP = SETUP + r"""
const guideNode=()=>el('guide-overlay');
const guideScreen=()=>guideNode().getAttribute('data-screen');
const guideSaved=(screen='G09',state='in_progress')=>({state,screen,choices:[],skipped:[],updated_at:'2026-10-31T01:00:00.000Z'});
const key=(key,shiftKey=false)=>document.dispatchEvent({type:'keydown',key,shiftKey});
"""


PRACTICE_SETUP = GUIDE_SETUP + r"""
const requests=[], posted=[], events=[];
let ready=false, runFailure=false, keyFailure=false, docFailure=false, resultFailure=false;
let resultStatus=200, listed=[], reply=null;
const pack={id:'fake-set',usable:true,docs:[
 {doc_id:'T21-X01',group:'dev',runnable:{try:true}},
 {doc_id:'T21-X02',group:'dev',runnable:{try:true}},
 {doc_id:'T21-X99',group:'eval',locked:true,runnable:{try:false}}]};
S.shell.sets=[pack];options.sets=[pack];
runData.docs=['T21-X01','T21-X02'];
runData.status_text.top_problem.docs=[
 {doc_id:'T21-X01',loss:3,counts:{[UI.score.cause_keys.wrong]:0}},
 {doc_id:'T21-X99',loss:2.5,counts:{[UI.score.cause_keys.wrong]:2}},
 {doc_id:'T21-X02',loss:2,counts:{[UI.score.cause_keys.wrong]:1}}];
const value={path:'fake.value',section:8,field:'q',table:'exposure_limits',items:['Fake criterion'],
 value:8,text:'8 fake-units',lines:['p2:L3'],silver:{same:false,value:5,text:'5 fake-units'}};
const view={doc_id:'T21-X02',has_gold:true,pages:[2],sections:{},set:{id:'fake-set'},
 lines:[{id:'p2:L3',page:2,no:3,text:'<em>Invented source 5</em>'}],values:[value],
 silver_only:[{...value,path:'missing.value',lines:['p2:L3']}],silver_lines:{basis:'text_match'}};
const plan={doc_id:'T21-X02',model_tag:'fake-model',pages_dir:'fake-pages',sections_method:'title',msds_count:1,
 sections:{'8':{section:8,lines:1,preamble_lines:0,first:'p2:L3',last:'p2:L3',pages:[2],images:[],method:'title',prompt_hash:'fake-hash'}}};
const trialJob=(dry=false,status='done',id='g1')=>({id,kind:'try',status,returncode:status==='done'?0:null,dry_run:dry,
 target:{kind:'try',doc:'T21-X02',model:'fake-model',sections:[8],all:false,set:'fake-set',dry_run:dry,
 key:{id:'silver/fake',label:'Fake answers'},base_run:'fake-run'}});
const trialResult=ok=>({plan,results:{'8':{ok,parsed:{fake:5}}},fields:{},score:null});
const baseApi=api;
api=async(p,o={})=>{
 requests.push(p);
 if(p.startsWith('/api/runs')&&runFailure)throw new Error('runs unreadable');
 if(p==='/api/keys'&&keyFailure)throw new Error('keys unreadable');
 if(p==='/api/keys')return {keys:[{id:'silver/fake',label:'Fake answers',usable:true,docs:['T21-X01','T21-X02']}],default:'silver/fake'};
 if(p==='/api/servers')return {models:[{tag:'fake-model',where:'RNGD',reachable:ready,match:ready}],rngd:{ok:true,diagnosis:ready?'ok':'no_model'}};
 if(p==='/api/options')return {...options,models:[{tag:'fake-model',connected:ready}]};
 if(p.startsWith('/api/prompt?'))return {text:'Invented section extraction instruction',hash:'fake-hash'};
 if(p.startsWith('/api/doc?')){assert.notEqual(new URLSearchParams(p.split('?')[1]).get('doc'),'T21-X99');if(docFailure)throw new Error('document unreadable');return clone(view);}
 if(p==='/api/jobs')return {jobs:listed,running:[]};
 if(p.endsWith('/result')){if(resultFailure)throw new Error('result unreadable');return {status:resultStatus,data:reply};}
 return baseApi(p,o);
};
post=async(p,b)=>{posted.push({path:p,body:clone(b)});return {id:'g1'};};
on('evidence_line_shown',e=>events.push({type:'evidence',...e}));
on('try_result_viewed',e=>events.push({type:'result',...e}));
async function enter(screen){await journeyEnsure();await guideOpen();await guideShow(screen);await flush();}
async function readyTarget(screen){await enter('G05');await guideShow('G07');await guideShow(screen);await flush();}
"""


def test_g05_reads_live_readiness_and_never_guesses():
    run_js(PRACTICE_SETUP + r"""
await enter('G05');
for(const p of ['/api/runs','/api/keys','/api/servers'])assert.ok(requests.some(r=>r.startsWith(p)));
assert.equal(el('guide-ready-results').dataset.state,'present');
assert.equal(el('guide-ready-key').dataset.state,'present');
assert.equal(el('guide-ready-ai').dataset.state,'absent');assert.equal(el('guide-next').disabled,false);
assert.ok(guideNode().textContent.includes(T('guide.ready.ai_optional')));
runData=null;await guideCheckReadiness();assert.equal(guideNode().dataset.variant,'G05-empty');
await el('guide-next').click();await el('guide-next').click();await flush();assert.equal(guideScreen(),'G08');
await guideShow('G05');runFailure=true;keyFailure=true;await guideCheckReadiness();
assert.equal(guideNode().dataset.variant,'G05-failed');assert.equal(el('guide-ready-results').dataset.state,'unknown');
assert.equal(el('guide-ready-key').dataset.state,'unknown');assert.equal(el('guide-next').textContent,T('guide.ready.retry'));
let release;const prior=api;api=(p,o)=>p==='/api/keys'?new Promise(r=>release=r):prior(p,o);
const checking=guideCheckReadiness();assert.equal(el('guide-ready-key').dataset.state,'checking');
release({keys:[]});await checking;assert.equal(el('guide-ready-key').dataset.state,'absent');
assert.equal(S.journey.outcomes.t1.real,null);
""")


def test_g07_success_only_with_real_ai_line():
    run_js(PRACTICE_SETUP + r"""
await readyTarget('G07');assert.ok(el('guide-practice').textContent.includes('T21-X02'));
assert.ok(el('guide-practice').textContent.includes(value.text));
assert.equal(S.journey.outcomes.t1.real,null);assert.equal(events.length,0);
await el('guide-next').click();await flush();
assert.equal(guideNode().dataset.variant,'G07-success');
assert.ok(el('guide-source-lines').textContent.includes(view.lines[0].text));
assert.equal(el('guide-source-lines').querySelector('em'),null);
assert.equal(events.filter(e=>e.type==='evidence'&&e.mismatch).length,1);
assert.equal(S.journey.outcomes.t1.real.count,1);guideRender();assert.equal(S.journey.outcomes.t1.real.count,1);
assert.ok(!requests.some(p=>p.includes('T21-X99')));
for(const p of puts)assert.ok(!JSON.stringify(p).includes('fake.value'));
""")


def test_g07_estimated_only_offers_another_value():
    run_js(PRACTICE_SETUP + r"""
value.lines=[];await readyTarget('G07');await el('guide-next').click();await flush();
assert.equal(guideNode().dataset.variant,'G07-estimated');
assert.equal(el('guide-next').textContent,T('guide.source.another'));assert.equal(S.journey.outcomes.t1.real,null);
assert.ok(el('guide-practice').textContent.includes(T('guide.source.not_recorded')));
assert.equal(events.length,0);docFailure=true;await guideShow('G07');
assert.ok(el('guide-practice').querySelector('[role="alert"]'));assert.ok(el('guide-practice').textContent.includes(T('guide.source.retry_todo')));
docFailure=false;value.lines=['p2:L3'];await el('guide-next').click();assert.equal(S.journey.outcomes.t1.real,null);
await el('guide-next').click();assert.equal(S.journey.outcomes.t1.real.count,1);
""")


def test_g08_practice_records_practice_only():
    run_js(PRACTICE_SETUP + r"""
await readyTarget('G08');listed=[trialJob(true)];reply={plan};
await el('guide-next').click();await flush();assert.equal(posted[0].body.dry_run,true);
assert.equal(posted[0].body.doc,'T21-X02');assert.deepEqual(posted[0].body.sections,[8]);
assert.equal(guideNode().dataset.variant,'G08-done');assert.ok(el('guide-practice').textContent.includes('fake-hash'));
assert.ok(el('guide-practice').textContent.includes('Invented section extraction instruction'));
assert.equal(S.journey.outcomes.t2.practice.count,1);assert.equal(S.journey.outcomes.t2.real,null);
await guideShow('G08');let release;post=(p,b)=>new Promise(r=>release=r);
const send=el('guide-next').click();await flush();assert.ok(el('guide-cancel-practice'));
await el('guide-cancel-practice').click();release({id:'late'});await send;await flush();
assert.equal(S.journey.outcomes.t2.practice.count,1);assert.equal(S.journey.outcomes.t2.real,null);
assert.ok(!requests.some(p=>p.includes('/late/result')));
""")


def test_g10_round_trip_rechecks_ai_and_returns():
    run_js(PRACTICE_SETUP + r"""
await readyTarget('G09');await el('guide-next').click();await flush();assert.equal(guideScreen(),'G10');
const before=requests.filter(p=>p==='/api/servers').length;
await el('guide-next').click();await flush();assert.equal(S.shell.route,'s06');assert.equal(guideNode().hidden,true);
assert.equal(saved.progress.guide.screen,'G10');assert.ok(el('servers-guide-return'));
await el('servers-guide-return').click();await flush();assert.equal(guideScreen(),'G10');
assert.equal(guideNode().dataset.variant,'G10-returned');assert.ok(requests.filter(p=>p==='/api/servers').length>before);
assert.ok(guideNode().textContent.includes(T('guide.ai.checked',{time:when(S.shell.serverAt)})));
assert.equal(S.journey.outcomes.t2.real,null);ready=true;await el('guide-ai-recheck').click();await flush();
assert.equal(guideScreen(),'G11');assert.equal(posted.length,0);
await guideClose();await go('s06');assert.equal(el('servers-guide-return'),null);
""")


def test_guide_never_presses_costly_actions():
    run_js(PRACTICE_SETUP + r"""
await enter('G05');await el('guide-ai-open').click();await el('servers-guide-return').click();
await guideShow('G10');await el('guide-next').click();await el('servers-guide-return').click();
await guideShow('G08');listed=[trialJob(true)];reply={plan};await el('guide-next').click();
ready=true;await guideShow('G11');listed=[trialJob(false,'done','g2')];reply=trialResult(true);
post=async(p,b)=>{posted.push({path:p,body:b});return {id:'g2'};};await el('guide-next').click();
assert.ok(posted.length>=2);assert.ok(posted.every(p=>p.path==='/api/jobs/try'));
""")


def test_g11_real_success_rules():
    run_js(PRACTICE_SETUP + r"""
ready=true;await readyTarget('G11');listed=[trialJob(false,'running')];reply=trialResult(true);
await el('guide-next').click();await flush();assert.equal(posted[0].body.dry_run,false);
assert.equal(guideNode().dataset.variant,'G11-running');assert.equal(S.journey.outcomes.t2.real,null);
assert.ok(el('guide-practice').textContent.includes(T('guide.trial.not_yet')));
listed=[trialJob()];await guidePollTrial();await flush();
assert.equal(guideNode().dataset.variant,'G11-result');assert.ok(el('guide-result-summary'));
assert.equal(S.journey.outcomes.t2.real.count,1);assert.equal(events.filter(e=>e.type==='result'&&e.section_ok).length,1);
guideRender();await guidePollTrial();assert.equal(S.journey.outcomes.t2.real.count,1);
""")
    for variant in ['returncode', 'dry_unknown', 'wrong_doc', 'whole', 'wrong_section']:
        run_js(PRACTICE_SETUP + f"const variant='{variant}';" + r"""
ready=true;await readyTarget('G11');const j=trialJob();listed=[j];reply=trialResult(true);
if(variant==='returncode')j.returncode=1;
if(variant==='dry_unknown'){delete j.dry_run;delete j.target.dry_run;}
if(variant==='wrong_doc')reply.plan={...plan,doc_id:'T21-X03'};
if(variant==='whole'){j.target.all=true;reply={plan,run:{sections_ok:16}};}
if(variant==='wrong_section')reply.results={'9':{ok:true}};
await el('guide-next').click();await flush();assert.equal(S.journey.outcomes.t2.real,null);
assert.notEqual(guideNode().dataset.variant,'G11-result');
""")


def test_g11_failed_and_late_responses():
    run_js(PRACTICE_SETUP + r"""
ready=true;await readyTarget('G11');listed=[trialJob()];reply=trialResult(false);
await el('guide-next').click();assert.equal(guideNode().dataset.variant,'G11-failed');
assert.ok(el('guide-practice').textContent.includes(T('guide.trial.record')));
assert.ok(el('guide-practice').textContent.includes(T('guide.trial.not_recorded')));
assert.equal(el('guide-next').textContent,T('guide.trial.retry'));assert.equal(S.journey.outcomes.t2.real,null);
for(const code of [202,204]){resultStatus=code;await guideShow('G11');await el('guide-next').click();
 assert.equal(S.journey.outcomes.t2.real,null);assert.ok(el('guide-result-retry'));
 assert.ok(!el('guide-practice').textContent.includes(T('guide.trial.done')));}
resultStatus=200;resultFailure=true;await el('guide-result-retry').click();assert.ok(el('guide-practice').querySelector('[role="alert"]'));
resultFailure=false;reply=trialResult(true);let release;const previous=api;
api=(p,o)=>p.endsWith('/result')?new Promise(r=>release=r):previous(p,o);
const pending=el('guide-result-retry').click();await flush();emit('attempt_cancelled',{job:'g1'});
release({status:200,data:reply});await pending;assert.equal(S.journey.outcomes.t2.real,null);
api=previous;listed=[trialJob(false,'running','g2')];post=async()=>({id:'g2'});
await guideShow('G11');await el('guide-next').click();assert.equal(el('guide-stop'),null);
clockTick(601000);await flush();assert.notEqual(guideNode().dataset.variant,'G11-running');
assert.ok(el('guide-result-retry'));assert.equal(S.journey.outcomes.t2.real,null);
""")


def test_g12_shows_records_without_false_celebration():
    run_js(PRACTICE_SETUP + r"""
saved.outcomes.t2.real={count:4,first_at:'2026-01-01',last_at:'2026-01-01',last_job:'old'};
await readyTarget('G08');listed=[trialJob(true)];reply={plan};await el('guide-next').click();
await guideShow('G12');assert.equal(guideNode().dataset.variant,'G12-no-success');
assert.equal(el('guide-title').textContent,T('guide.records.not_yet'));
assert.ok(el('guide-session-records').textContent.includes(T('guide.records.count',{count:1})));
assert.ok(!el('guide-session-records').textContent.includes('2026-01-01'));
await guideShow('G07');await el('guide-next').click();await guideShow('G12');
assert.equal(guideNode().dataset.variant,'G12-source-only');
ready=true;await guideShow('G11');listed=[trialJob(false,'done','g2')];reply=trialResult(true);post=async()=>({id:'g2'});
await el('guide-next').click();await guideShow('G12');assert.equal(guideNode().dataset.variant,'G12');
assert.equal(S.journey.outcomes.t2.real.count,5);
""")


def test_guide_practice_states_have_copy_and_one_primary_action():
    run_js(PRACTICE_SETUP + r"""
await enter('G05');
for(const screen of ['G05','G07','G08','G10','G11','G12']){
 ready=screen==='G11';await guideShow(screen);await flush();
 assert.doesNotMatch(guideNode().textContent,/null|undefined|⟦/);
 assert.equal(guideNode().querySelectorAll('button.primary').length,1);
 if(['G07','G08','G11'].includes(screen))assert.ok(el('guide-practice').textContent.startsWith(T('guide.before')));
}
""")


def test_guide_hidden_or_closed_result_waits_for_visible_summary():
    run_js(PRACTICE_SETUP + r"""
ready=true;await readyTarget('G11');listed=[trialJob(false,'running')];reply=trialResult(true);
await el('guide-next').click();key('Escape');listed=[trialJob()];await guidePollTrial();
assert.equal(el('guide-confirm').hidden,false);assert.equal(S.journey.outcomes.t2.real,null);
await el('guide-continue').click();assert.equal(S.journey.outcomes.t2.real.count,1);
""")
    run_js(PRACTICE_SETUP + r"""
ready=true;await readyTarget('G11');listed=[trialJob(false,'running')];reply=trialResult(true);
await el('guide-next').click();let release;const prior=api;
api=(p,o)=>p.endsWith('/result')?new Promise(r=>release=r):prior(p,o);
listed=[trialJob()];const polling=guidePollTrial();await flush();await guideClose();
release({status:200,data:reply});await polling;assert.equal(S.journey.outcomes.t2.real,null);
assert.equal(S.journey.pending.job,'g1');
api=prior;await guideOpen({resume:true});await flush();assert.equal(posted.length,1);
assert.equal(S.journey.outcomes.t2.real.count,1);
""")


def test_guide_readiness_preserves_close_dialog_during_late_get():
    run_js(PRACTICE_SETUP + r"""
await journeyEnsure();await guideOpen();let release;const prior=api;
api=(p,o)=>p==='/api/keys'?new Promise(r=>release=r):prior(p,o);
const loading=guideShow('G05');key('Escape');release({keys:[]});await loading;
assert.equal(el('guide-confirm').hidden,false);assert.ok(el('guide-confirm').contains(document.activeElement));
await el('guide-continue').click();assert.equal(S.journey.outcomes.t1.real,null);
""")


def test_guide_skips_mark_progress_without_success_and_requests_time_out():
    run_js(PRACTICE_SETUP + r"""
await readyTarget('G07');await el('guide-skip-practice').click();await el('guide-skip-practice').click();
await guideShow('G12');assert.ok(saved.progress.guide.skipped.includes('p1'));assert.ok(saved.progress.guide.skipped.includes('p2'));
assert.equal(el('guide-progress').querySelectorAll('[data-skipped]').length,2);
assert.ok(el('guide-progress').textContent.includes(T('guide.skipped')));assert.equal(S.journey.outcomes.t1.real,null);
const prior=api;api=(p,o)=>p.startsWith('/api/runs')?new Promise(()=>{}):prior(p,o);
const checking=guideShow('G05');clockTick(16000);await checking;assert.equal(guideNode().dataset.variant,'G05-failed');
assert.equal(el('guide-next').disabled,false);
""")


def test_guide_job_failure_never_claims_an_ai_answer_and_stale_doc_is_ignored():
    run_js(PRACTICE_SETUP + r"""
ready=true;await readyTarget('G11');listed=[trialJob(false,'failed')];await el('guide-next').click();
assert.ok(!el('guide-title').textContent.includes(T('guide.trial.failed')));
assert.ok(el('guide-practice').textContent.includes(T('guide.trial.not_recorded')));assert.equal(S.journey.outcomes.t2.real,null);
let release;const prior=api;api=(p,o)=>p.startsWith('/api/doc?')?new Promise(r=>release=r):prior(p,o);
const reading=guideShow('G07');await flush();await guideShow('G12');release(clone(view));await reading;
assert.equal(guideScreen(),'G12');assert.equal(S.journey.outcomes.t1.real,null);
""")


def test_guide_ai_probe_failure_is_unknown_instead_of_off():
    run_js(PRACTICE_SETUP + r"""
const prior=api;api=(p,o)=>p==='/api/servers'?Promise.resolve({models:[{tag:'fake-model',reachable:false,error:'probe failed'}]}):prior(p,o);
await enter('G05');assert.equal(el('guide-ready-ai').dataset.state,'unknown');
assert.equal(el('guide-next').disabled,false);await guideShow('G10');
assert.ok(el('guide-content').textContent.includes(T('guide.ready.states.unknown')));
assert.ok(!el('guide-content').textContent.includes(T('guide.ai.off')));
assert.equal(posted.length,0);
""")


LIVE_SETUP = PRACTICE_SETUP + r"""
pack.label='Fake set label';pack.path='data/pages/fake-set';
pack.docs[0]={...pack.docs[0],pages:3,line_numbers:true};pack.docs[1]={...pack.docs[1],pages:4,line_numbers:true};
pack.counts={dev:2,eval_locked:1,other:0,outside:0,unknown:0};
S.shell.keys=[{id:'silver/fake',label:'Fake answers',path:'data/silver/fake',usable:true,docs:['T21-X01','T21-X02'],counts:{docs:2,eval_locked:1,outside:0}},
 {id:'gold/empty',label:'Empty answers',path:'data/gold/empty',usable:false,reason:'Fake reason',docs:[],counts:{docs:0,eval_locked:0,outside:0}}];
runData={...runData,model_tag:'fake-model',model_label:'Fake model',label:{title:'Fake run title'},run_kind:'dev10',
 targets:{weighted:{line:90,value:71,met:false},must:{total:17,met_count:4,met:false}}};
runData.status_text={...runData.status_text,loss_basis:{loss_total:19},top_problem:{...runData.status_text.top_problem,loss:2.5}};
const older={...clone(runData),name:'older-run',label:{title:'Older run title'}};
value.key='exposure[k=fake].q';
const sampleLines=[{id:'p1:L1',page:1,no:1,text:'Invented first line'},{id:'p1:L2',page:1,no:2,text:'Invented second line'}];
const liveApi=api;
let liveFails=false;
api=async(p,o={})=>{
 if(liveFails&&(p.startsWith('/api/runs')||p.startsWith('/api/doc?')))throw new Error('Invented failure');
 if(p.startsWith('/api/runs')){requests.push(p);return {current:runData?.name,runs:runData?[older,runData]:[]};}
 if(p.startsWith('/api/doc?')){
  const q=new URLSearchParams(p.split('?')[1]);
  if(q.get('run')==='older-run'){requests.push(p);const v=clone(view);v.values[0]={...v.values[0],path:'moved.row',value:11,text:'11 older-units'};return v;}
  if(!q.get('run')){requests.push(p);assert.equal(q.get('set'),'fake-set');return {...clone(view),doc_id:q.get('doc'),lines:sampleLines,pages:[1,2,3],values:[],silver_only:[]};}
 }
 return liveApi(p,o);
};
async function liveOpen(screen){await journeyEnsure();await guideOpen();await S.guide.livePending;await guideShow(screen);await S.guide.livePending;await flush();return el('guide-example').textContent;}
const notBlank=screen=>{
 const example=el('guide-example');
 assert.equal(example.querySelectorAll('.guide-placeholder').length,0,screen);
 assert.doesNotMatch(example.textContent,/\{\w+\}|⟦|null|undefined/,screen);
 assert.equal(example.getAttribute('role'),'img');
 assert.equal(example.getAttribute('aria-label'),T('guide.example.label'));
 for(const child of example.children)assert.equal(child.getAttribute('aria-hidden'),'true');
 assert.equal(example.querySelectorAll('button,input,select,a,textarea,[tabindex]').length,0,screen);
};
"""


def test_example_panels_show_real_saved_results():
    """왼쪽 칸은 빈 막대도 가짜 값도 아니라 최근 결과 화면과 같은 값을 보여 준다."""
    run_js(LIVE_SETUP + r"""
const copy=await liveOpen('G01');
for(const screen of guideOrder){
 S.guide.screen=screen;guideRender();notBlank(screen);
 assert.ok(el('guide-example').textContent.includes(T('guide.example.badge')),screen);
}
assert.ok(copy.includes('71.0'));assert.ok(copy.includes(T('score.summary.scope',{model:'Fake model',count:2})));
assert.ok(copy.includes(T('score.summary.must_some',{total:17,met:4})));
assert.ok(copy.includes(T('score.summary.top_problem',{item:'Fake criterion'})));
assert.ok(copy.includes(T('score.basis.label',{key:'Fake answers',count:2})));
const see=(screen,...expected)=>{S.guide.screen=screen;guideRender();const text=el('guide-example').textContent;
 for(const part of expected)assert.ok(text.includes(part),screen+': '+part+' / '+text);};
see('G03','8 fake-units','Invented source 5','11 older-units');
see('G05','Fake run title','Fake answers');
see('G07','8 fake-units','5 fake-units','Invented source 5');
see('G08','T21-X02',T('score.calls.section',{section:8}),'Invented section extraction instruction');
see('G09','11 older-units','8 fake-units','Older run title','Fake run title');
S.shell.servers={models:[],rngd:{ok:true,tunnel:{port:9,open:true}}};see('G10','Fake model',T('guide.example.tunnel_open'));
S.shell.servers={models:[],rngd:{ok:true,tunnel:{port:9,open:false}}};see('G10',T('guide.example.tunnel_closed'));
see('G14','Fake set label','Fake answers','71.0');
see('G16','data/pages/fake-set',T('guide.example.data_counts',{open:2,locked:1}),'Invented first line');
see('G17','Fake answers','data/silver/fake',T('guide.example.answers_count',{docs:2,locked:1}),'8 fake-units','5 fake-units');
assert.ok(!el('guide-example').textContent.includes('Empty answers'));
""")


def test_example_change_prefers_scored_table_cells_over_shifted_sentences():
    """서술 문장은 줄이 밀려 다른 내용끼리 맞붙는다. 채점하는 표의 칸을 먼저 보인다."""
    run_js(LIVE_SETUP + r"""
const row=(key,table,section,text,items=['Fake criterion'])=>({path:key,key,table,section,field:'f',value:text,text,items,lines:['p2:L3'],silver:{same:false,value:'x',text:'x'}});
view.values=[value,row('narr[k=1].s','narratives',8,'Invented new sentence'),row('reg[k=1].applicable','regulations',15,'Invented new cell')];
const baseDoc=api;
api=async(p,o={})=>{
 if(p.startsWith('/api/doc?')&&new URLSearchParams(p.split('?')[1]).get('run')==='older-run')
  return {...clone(view),values:[{...value},row('narr[k=1].s','narratives',8,'Invented old sentence'),row('reg[k=1].applicable','regulations',15,'Invented old cell')]};
 return baseDoc(p,o);
};
await liveOpen('G09');
const text=el('guide-example').textContent;
assert.ok(text.includes('Invented new cell'),text);assert.ok(text.includes('Invented old cell'));
assert.ok(!text.includes('Invented new sentence'));
assert.ok(text.includes('reg[k=1].applicable'));
assert.ok(text.includes(T('guide.target',{doc:'T21-X02',section:15})));
""")


def test_example_change_shows_only_round_of_long_run_label():
    run_js(LIVE_SETUP + r"""
older.label={title:'Long older title',parts:['Long older','Round one']};
runData.label={title:'Long newer title',parts:['Long newer','Round two']};
await liveOpen('G09');
const text=el('guide-example').textContent;
assert.ok(text.includes('Round one'));assert.ok(text.includes('Round two'));
assert.ok(!text.includes('Long older title'));assert.ok(!text.includes('Long newer title'));
""")


def test_example_panels_are_empty_only_in_words_when_no_result():
    run_js(LIVE_SETUP + r"""
runData=null;
await liveOpen('G01');
for(const screen of ['G01','G03','G07','G09','G14']){
 S.guide.screen=screen;guideRender();notBlank(screen);
 assert.ok(el('guide-example').textContent.includes(T('guide.example.empty')),screen);
 assert.doesNotMatch(el('guide-example').textContent,/\d+\.\d/,screen);
}
S.guide.screen='G16';guideRender();notBlank('G16');
assert.ok(el('guide-example').textContent.includes('Invented first line'));
""")


def test_example_panel_read_failure_keeps_guide_working():
    run_js(LIVE_SETUP + r"""
liveFails=true;
await liveOpen('G03');
notBlank('G03');
assert.ok(el('guide-example').textContent.includes(T('guide.example.failed')));
assert.equal(guideScreen(),'G03');
assert.equal(el('guide-next').disabled,false);
await el('guide-next').click();await flush();
assert.equal(guideScreen(),'G04');
""")


def test_example_panel_uses_only_open_docs_and_writes_nothing():
    run_js(LIVE_SETUP + r"""
const before=puts.length;
await journeyEnsure();await guideOpen();
const afterOpen=puts.length;
await S.guide.livePending;await flush();
assert.equal(puts.length,afterOpen);assert.equal(posted.length,0);assert.deepEqual(events,[]);
const docs=requests.filter(p=>p.startsWith('/api/doc?')).map(p=>new URLSearchParams(p.split('?')[1]).get('doc'));
assert.ok(docs.length);assert.ok(!docs.includes('T21-X99'));
assert.equal(journeyPristine?typeof journeyPristine:'function','function');
assert.equal(JSON.stringify(saved).includes('Invented'),false);assert.equal(JSON.stringify(saved).includes('fake-units'),false);
""")


def test_example_panel_ignores_results_of_previous_context():
    run_js(LIVE_SETUP + r"""
await journeyEnsure();await guideOpen();
const stale=S.guide.live;
S.ctx={...S.ctx,key:'gold/other'};
const pending=guideLiveLoad();
assert.notEqual(S.guide.live,stale);
await S.guide.livePending;await pending;await flush();
assert.equal(stale.run??null,null);
assert.equal(S.guide.live.context,scoreContext());
""")


def test_data_screens_explain_meaning_and_how_to_change_and_add():
    run_js(LIVE_SETUP + r"""
await journeyEnsure();await guideOpen();await S.guide.livePending;
assert.deepEqual(guideOrder.slice(-5),['G13','G16','G17','G14','G15']);
await guideShow('G13');await flush();
assert.equal(guideNode().querySelector('h1').textContent,T('guide.screens.G13.title'));
await el('guide-next').click();await flush();
assert.equal(guideScreen(),'G16');
const source=el('guide-content').textContent;
for(const key of ['lead','example','set','change_title','change','add_title','add1','add2','add3','add4','caution'])
 assert.ok(source.includes(T('guide.data.source.'+key)),key);
assert.ok(source.includes('data/pages/'));assert.ok(source.includes(T('context.change_documents')));
assert.equal(el('guide-progress').children.length,4);
await el('guide-next').click();await flush();
assert.equal(guideScreen(),'G17');
const answers=el('guide-content').textContent;
for(const key of ['lead','kinds_title','gold','silver','change_title','change','add_title','add1','add2','add3','caution'])
 assert.ok(answers.includes(T('guide.data.answers.'+key)),key);
assert.ok(answers.includes('data/gold'));assert.ok(answers.includes('data/silver/'));assert.ok(answers.includes(T('context.change_answer')));
await el('guide-next').click();await flush();
assert.equal(guideScreen(),'G14');
await el('guide-back').click();await flush();
assert.equal(guideScreen(),'G17');
assert.equal(saved.progress.guide.screen,'G14');
""")


def test_first_visit_opens_guide_full_screen():
    run_js(GUIDE_SETUP + r"""
await start();await flush();
assert.equal(guideNode().hidden,false);assert.equal(guideScreen(),'G01');
assert.equal(guideNode().getAttribute('role'),'dialog');assert.equal(guideNode().getAttribute('aria-modal'),'true');
assert.equal(document.activeElement.id,'guide-title');
assert.equal(el('guide-title').textContent,T('guide.screens.G01.title'));
for(const id of ['app-header','work'])assert.ok(el(id).getAttribute('inert')!==null);
assert.ok(document.body.classList.contains('guide-open'));
assert.equal(puts.length,0);assert.equal(S.journey.outcomes.t1.real,null);
assert.ok(el('guide-example').textContent.includes(T('guide.example.badge')));
""")


def test_hash_route_and_unknown_journey_do_not_open_guide():
    run_js(GUIDE_SETUP + r"""
let release;const normal=api;api=(p,o)=>p==='/api/journey'&&!o?.method?new Promise(r=>release=r):normal(p,o);
location.hash='#s03';await start();await flush();assert.equal(guideNode().hidden,true);
release({journey:saved,problems:[]});await flush();assert.equal(guideNode().hidden,true);assert.equal(S.shell.route,'s03');
await go('s01');assert.equal(guideNode().hidden,true);
""")
    run_js(GUIDE_SETUP + r"""
failRead=true;await start();await flush();assert.equal(guideNode().hidden,true);
assert.ok(el('journey-notices').textContent.includes(T('journey.save_failed.title')));
failRead=false;await journeyLoad();assert.equal(guideNode().hidden,true);
""")
    run_js(GUIDE_SETUP + r"""
let release;const normal=api;api=(p,o)=>p==='/api/journey'&&!o?.method?new Promise(r=>release=r):normal(p,o);
await start();await flush();assert.equal(guideNode().hidden,true);
await go('s07');release({journey:saved,problems:[]});await flush();assert.equal(guideNode().hidden,true);
""")


def test_returning_visit_lands_on_s01_with_resume_line():
    run_js(GUIDE_SETUP + r"""
saved.progress.guide=guideSaved();saved.progress.dismissed_at='2026-10-31T02:00:00.000Z';
await start();await flush();assert.equal(S.shell.route,'s01');assert.equal(guideNode().hidden,true);
assert.ok(el('guide-resume').textContent.includes(T('guide.resume')));
await el('guide-resume-button').click();await flush();assert.equal(guideScreen(),'G09');assert.equal(puts.length,1);
assert.equal(saved.progress.dismissed_at,null);assert.equal(saved.progress.guide.screen,'G09');
""")
    for state in ['completed', 'skipped']:
        run_js(GUIDE_SETUP + f"saved.progress.guide=guideSaved('G15','{state}');" + r"""
await start();await flush();assert.equal(guideNode().hidden,true);assert.equal(el('guide-resume').hidden,true);
""")


def test_guide_progress_saves_last_confirmed_screen_only():
    run_js(GUIDE_SETUP + r"""
await start();await flush();assert.equal(puts.length,0);
await el('guide-next').click();await flush();assert.equal(guideScreen(),'G02');
assert.equal(saved.progress.guide.screen,'G02');assert.equal(puts.length,1);
el('guide-choice-source').checked=true;el('guide-choice-source').dispatchEvent({type:'change'});await flush();
await el('guide-next').click();await flush();assert.equal(guideScreen(),'G03');assert.equal(saved.progress.guide.screen,'G03');
assert.deepEqual(Object.keys(saved.progress.guide).sort(),['choices','screen','skipped','state','updated_at']);
await el('guide-next').click();await flush();assert.equal(saved.progress.guide.screen,'G04');
el('guide-back').click();assert.equal(guideScreen(),'G03');
assert.equal(saved.progress.guide.screen,'G04');const before=puts.length;
guideRender();await journeyLoad();assert.equal(puts.length,before);
await guideOpen({resume:true});assert.equal(guideScreen(),'G04');assert.equal(puts.length,before);
failWrite=true;await el('guide-next').click();await flush();assert.equal(guideScreen(),'G05');
assert.ok(el('guide-notices').textContent.includes(T('journey.save_failed.title')));
assert.ok(el('guide-next'));assert.equal(S.journeyUI.unsaved,true);
await journeyLoad();assert.equal(S.journey.progress.guide.screen,'G05');
failWrite=false;await el('guide-next').click();await flush();assert.equal(saved.progress.guide.screen,'G06');
for(const forbidden of ['T21-X01','fake-run','Fake criterion','p2:L3'])assert.ok(!JSON.stringify(puts).includes(forbidden));
""")
    run_js(GUIDE_SETUP + r"""
saved.progress.guide=guideSaved('G06');await start();await flush();
assert.equal(guideScreen(),'G06');assert.equal(puts.length,0);
assert.equal(S.journey.outcomes.t2.real,null);assert.equal(S.journey.outcomes.t2.practice,null);
""")


def test_chapter_row_and_progress_text():
    run_js(GUIDE_SETUP + r"""
await start();await flush();
const order=['G01','G03','G04','G06','G09','G13','G15'];
for(const screen of order){
 await guideShow(screen,{save:false});
 assert.equal(guideScreen(),screen);
 const progress=el('guide-progress'),chapters=el('guide-chapters');
 if(['G03','G09'].includes(screen)){
   const chapter=screen==='G03'?1:3,n=screen==='G03'?3:4,total=screen==='G03'?3:7;
   assert.equal(chapters.querySelectorAll('[data-chapter]').length,5);
   assert.equal(chapters.querySelector('[aria-current="step"]').getAttribute('data-chapter'),String(chapter));
   assert.equal(progress.children.length,total);
   assert.equal(el('guide-progress-text').textContent,T('guide.progress',{chapter:T('guide.chapters.'+chapter),n,m:total,k:chapter}));
 }else{assert.equal(progress,null);assert.equal(chapters,null);}
 assert.equal(guideNode().querySelectorAll('button.primary').length,1);
 assert.doesNotMatch(guideNode().textContent,/null|undefined|⟦/);
}
await el('guide-next').click();await flush();
assert.equal(guideNode().hidden,true);assert.equal(saved.progress.guide.state,'completed');
assert.equal(S.journey.outcomes.t1.real,null);assert.equal(S.journey.outcomes.t2.real,null);
""")


def test_close_skip_and_escape():
    run_js(GUIDE_SETUP + r"""
await start();await flush();assert.ok(el('guide-skip'));assert.equal(el('guide-close'),null);
await el('guide-skip').click();await flush();assert.equal(guideNode().hidden,true);
assert.equal(saved.progress.guide.state,'skipped');assert.equal(S.shell.route,'s01');
assert.equal(el('app-header').getAttribute('inert'),null);
const opener=el('guide-open');opener.focus();await opener.click();await flush();
await el('guide-next').click();await flush();assert.ok(el('guide-close'));assert.equal(el('guide-skip'),null);
el('guide-choice-source').checked=true;el('guide-choice-source').dispatchEvent({type:'change'});
await el('guide-next').click();await flush();assert.equal(guideScreen(),'G03');
const next=el('guide-next');next.focus();key('Tab');assert.equal(document.activeElement.id,'guide-back');
key('Tab',true);assert.equal(document.activeElement.id,'guide-next');
el('context-change-key').focus();assert.ok(guideNode().contains(document.activeElement));
next.focus();key('Escape');assert.equal(el('guide-confirm').hidden,false);
assert.ok(el('guide-frame').getAttribute('inert')!==null);
assert.equal(document.activeElement.id,'guide-confirm-title');
el('guide-continue').focus();key('Tab');assert.equal(document.activeElement.id,'guide-confirm-close');
el('guide-continue').click();assert.equal(el('guide-confirm').hidden,true);assert.equal(document.activeElement,next);
key('Escape');key('Escape');assert.equal(el('guide-confirm').hidden,true);assert.equal(document.activeElement,next);
await el('guide-close').click();await flush();assert.equal(S.shell.route,'s01');
assert.equal(saved.progress.guide.screen,'G03');assert.equal(guideNode().hidden,true);
assert.equal(document.activeElement,opener);assert.equal(document.body.classList.contains('guide-open'),false);
assert.ok(el('guide-resume').textContent.includes(T('guide.resume')));
""")


def test_replay_keeps_outcomes():
    run_js(GUIDE_SETUP + r"""
saved.progress.guide=guideSaved('G15','completed');
saved.progress.t1={state:'completed',step:3,updated_at:'2026-10-31T01:00:00.000Z'};
saved.outcomes.t1.real={count:2,first_at:'2026-10-30T01:00:00.000Z',last_at:'2026-10-31T01:00:00.000Z'};
saved.outcomes.t2.practice={count:3,first_at:'2026-10-30T01:00:00.000Z',last_at:'2026-10-31T01:00:00.000Z',last_job:'p3'};
await start();await flush();const outcomes=clone(S.journey.outcomes),old=clone(S.journey.progress.t1);
store.set('b_app.cards','keep');await go('s07');el('help-replay').click();await flush();
assert.equal(guideScreen(),'G01');assert.equal(S.journey.progress.guide.screen,'G01');
assert.deepEqual(S.journey.outcomes,outcomes);assert.deepEqual(S.journey.progress.t1,old);
assert.equal(store.get('b_app.cards'),'keep');assert.deepEqual(saved.outcomes,outcomes);
await el('guide-skip').click();await el('guide-open').click();await flush();assert.equal(guideScreen(),'G01');
assert.deepEqual(saved.outcomes,outcomes);
""")


def test_s08_and_band_are_removed_and_records_moved():
    run_js(GUIDE_SETUP + r"""
saved.progress.guide=guideSaved('G15');saved.progress.dismissed_at='2026-10-31T02:00:00.000Z';
saved.outcomes.t1.real={first_at:'2026-10-31T01:00:00.000Z',last_at:'2026-10-31T01:30:00.000Z',count:2};
saved.outcomes.t2.practice={first_at:'2026-10-31T01:00:00.000Z',last_at:'2026-10-31T01:20:00.000Z',count:3,last_job:'p3'};
await start();await flush();assert.equal(el('screen-s08'),null);assert.equal(el('journey-band'),null);
assert.equal(document.querySelector('[data-screen="s08"]'),null);assert.equal(SHELL_SCREENS.s08,undefined);
await el('guide-resume-button').click();
const record=el('guide-records');assert.ok(record.textContent.includes(T('journey.history.real_success')));
assert.ok(record.textContent.includes(T('journey.history.first_count',{time:when(saved.outcomes.t1.real.first_at),count:2})));
assert.ok(record.textContent.includes(T('journey.history.first_count',{time:when(saved.outcomes.t2.practice.first_at),count:3})));
assert.ok(record.textContent.includes(T('journey.history.none')));
await el('guide-next').click();await go('s07');
assert.ok(el('help-guide-records').textContent.includes(T('journey.history.real_success')));
assert.ok(el('help-guide-records').textContent.includes(T('journey.history.keep_outcomes')));
assert.equal(el('help-guide-records').querySelector('details').open,false);
""")
    scripts = (STATIC / 'index.html').read_text()
    assert scripts.index('js/journey.js') < scripts.index('js/guide.js') < scripts.index('js/help.js')


def test_guide_puts_serialize_and_merge_other_tab_outcomes():
    run_js(GUIDE_SETUP + r"""
await start();await flush();let release;const normal=api;
api=(p,o)=>{if(o?.method==='PUT'&&!release){const sent=JSON.parse(o.body).journey;
 return new Promise(r=>release=()=>{sent.outcomes.t1.real={first_at:'2026-10-31T01:00:00.000Z',last_at:'2026-10-31T02:00:00.000Z',count:4};r({journey:sent});});}return normal(p,o);};
el('guide-next').click();el('guide-choice-source').checked=true;el('guide-choice-source').dispatchEvent({type:'change'});
el('guide-next').click();el('guide-next').click();assert.equal(guideScreen(),'G04');
release();await flush();assert.equal(saved.progress.guide.screen,'G04');assert.equal(saved.outcomes.t1.real.count,4);
""")


def test_guide_resume_null_screen_starts_without_writing():
    run_js(GUIDE_SETUP + r"""
saved.progress.guide=guideSaved(null);await journeyEnsure();await guideOpen({resume:true});
assert.equal(guideScreen(),'G01');assert.equal(puts.length,0);
""")


def test_guide_entry_and_one_primary_action_do_not_wait_for_model_status():
    run_js(GUIDE_SETUP + r"""
const normal=api;let release;api=(p,o)=>p==='/api/servers'?new Promise(r=>release=r):normal(p,o);
const starting=start();await flush();assert.equal(guideScreen(),'G01');assert.equal(guideNode().hidden,false);
assert.equal(guideNode().querySelectorAll('button.primary').length,1);
assert.equal(S.journey.outcomes.t1.real,null);assert.equal(S.journey.outcomes.t2.real,null);
release({models:[]});await starting;await flush();assert.equal(guideScreen(),'G01');
""")


def test_legacy_track_actions_keep_real_and_practice_contract_without_s08():
    for track in ['t1', 't2']:
        run_js(GUIDE_SETUP + f"const desiredTrack='{track}';" + r"""
await journeyEnsure();await journeyStart(desiredTrack);await flush();
assert.equal(S.journey.progress.active,desiredTrack);
assert.equal(S.shell.route,desiredTrack==='t1'?'s01':'s03');
assert.equal(S.journey.outcomes.t1.real,null);assert.equal(S.journey.outcomes.t2.real,null);
assert.ok(puts.length);assert.equal(el('screen-s08'),null);
""")


def test_guide_g15_example_records_stay_separate_from_actual_records():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();S.journey.progress.guide=guideSaved('G15');await guideOpen({resume:true});
const demo=el('guide-example');assert.equal(UI.guide.example.records,undefined);
assert.ok(!demo.textContent.includes(T('guide.records.title')));
const records=el('guide-records');assert.ok(records.textContent.includes(T('journey.history.none')));
assert.equal(S.journey.outcomes.t1.real,null);assert.equal(S.journey.outcomes.t2.practice,null);
""")


# S08 제거: 저장·성공·연습·취소·재방문 회귀를 이 파일로 이동했다.
def test_boot_reads_once_no_band_before_reply_and_hash_wins():
    run_js(GUIDE_SETUP + r"""
let release;const normal=api;api=(path,opts)=>path==='/api/journey'&&!opts?.method?
 new Promise(r=>{gets++;release=r;}):normal(path,opts);
location.hash='#s07';await start();await start();
assert.equal(gets,1);assert.equal(el('guide-overlay').hidden,true);
assert.equal(location.hash,'#s07');release({journey:saved,problems:[]});await flush();
assert.equal(location.hash,'#s07');await go('s01');assert.equal(el('guide-overlay').hidden,true);
await el('guide-open').click();await flush();assert.equal(el('guide-title').textContent,T('guide.screens.G01.title'));
""")


@pytest.mark.parametrize('change', [
    "saved.progress.dismissed_at='2026-10-31T00:00:00.000Z'",
    "saved.progress.t1.state='skipped'",
    "saved.outcomes.t1.real={first_at:'2026-10-31T00:00:00.000Z',last_at:'2026-10-31T00:00:00.000Z',count:1}",
    "saved.outcomes.t2.practice={first_at:'2026-10-31T00:00:00.000Z',last_at:'2026-10-31T00:00:00.000Z',count:1,last_job:'practice1'}",
])
def test_returning_records_do_not_show_first_visit(change):
    run_js(GUIDE_SETUP + change + r""";await start();await flush();assert.equal(el('guide-overlay').hidden,true);""")


def test_resume_and_pending_are_separate_from_first_visit():
    run_js(GUIDE_SETUP + r"""
saved.progress.active='t2';saved.progress.t2={state:'in_progress',step:1,updated_at:null};
saved.progress.guide=guideSaved();saved.progress.dismissed_at='2026-10-31T02:00:00.000Z';
await journeyEnsure();assert.ok(el('guide-resume').textContent.includes(T('guide.resume_action')));
saved.pending={attempt:'a1',job:'job1',mode:'real',started_at:new Date().toISOString()};
const normal=api;api=async(p,o)=>p==='/api/jobs'?{jobs:[{id:'job1',kind:'try',status:'done'}]}:normal(p,o);
await journeyLoad();assert.ok(el('journey-notices').textContent.includes(T('journey.pending.open_result')));
assert.equal(S.journey.outcomes.t2.real,null);
""")


def test_full_put_and_server_merged_response_replace_memory():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();const normal=api;
api=async(p,o)=>{const r=await normal(p,o);if(o?.method==='PUT')r.journey.migrated_from=1;return r;};
journeyDismiss();await flush();assert.equal(puts.length,1);
assert.deepEqual(Object.keys(puts[0]),['journey']);assert.deepEqual(Object.keys(puts[0].journey).sort(),Object.keys(journeyDefault()).sort());
assert.equal(S.journey.migrated_from,1);assert.ok(S.journey.progress.dismissed_at);
""")


def test_puts_serialize_and_coalesce_latest_without_reverting_progress():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();let release,active=0,max=0;const normal=api;
api=async(p,o)=>{if(o?.method==='PUT'){active++;max=Math.max(max,active);if(!release){
 const request=JSON.parse(o.body);puts.push(request);return new Promise(r=>release=()=>{active--;r({journey:request.journey});});}
 const r=await normal(p,o);active--;return r;}return normal(p,o);};
journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
journeyChange(j=>{j.progress.t1.step=1;});journeyChange(j=>{j.progress.t1.step=2;});
assert.equal(puts.length,1);release();await flush();assert.equal(max,1);assert.equal(puts.length,2);
assert.equal(puts[1].journey.progress.t1.step,2);assert.equal(S.journey.progress.t1.step,2);
""")


def test_late_get_and_visibility_refresh():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();let release;const normal=api;
api=(p,o)=>p==='/api/journey'&&!o?.method?new Promise(r=>release=r):normal(p,o);
const old=journeyLoad();journeyDismiss();await flush();release({journey:journeyDefault()});await old;
assert.ok(S.journey.progress.dismissed_at);
api=normal;document.visibilityState='visible';document.dispatchEvent({type:'visibilitychange'});await flush();assert.equal(gets,2);
""")


def test_storage_failures_are_not_first_visit_and_notify_once_but_work_continues():
    run_js(GUIDE_SETUP + r"""
let notices=0;on('journey_storage_unavailable',()=>notices++);
failRead=true;await journeyEnsure();assert.equal(el('guide-overlay').hidden,true);
assert.ok(el('journey-notices').textContent.includes(T('journey.save_failed.title')));
failWrite=true;journeyDismiss();await flush();journeyReplay();await flush();assert.equal(notices,1);
assert.equal(S.journey.progress.t1.step,0);failWrite=false;journeyDismiss();await flush();assert.ok(saved.progress.dismissed_at);
""")


def test_problems_notify_once_and_400_keeps_server_reason():
    run_js(GUIDE_SETUP + r"""
const normal=api;api=async(p,o)=>{const r=await normal(p,o);if(p==='/api/journey'&&!o?.method)r.problems=[{part:'pending',message:'Damaged pending'}];return r;};
await journeyEnsure();await journeyLoad();assert.equal(el('journey-notices').querySelectorAll('[data-notice="problems"]').length,1);
assert.ok(el('journey-notices').textContent.includes('Damaged pending'));
api=async(p,o)=>{if(o?.method==='PUT')throw Object.assign(new Error('Bad body'),{status:400,body:{message:'Invalid field',fix:'Reload guide'}});return normal(p,o);};
journeyDismiss();await flush();assert.ok(el('journey-notices').textContent.includes('Invalid field'));
""")


def test_valid_v1_completion_migrates_once_without_removing_key_or_server_progress():
    run_js(GUIDE_SETUP + r"""
const old={version:1,last_step:3,completed:true,dismissed:true,first_success_at:'2026-10-31T00:00:00.000Z'};
store.set('b_app.journey',JSON.stringify(old));saved.progress.t2.state='in_progress';saved.progress.t2.step=1;
await journeyEnsure();await flush();assert.equal(puts.length,1);assert.equal(S.journey.migrated_from,1);
assert.equal(S.journey.outcomes.t1.real.count,1);assert.equal(S.journey.progress.t2.step,1);
assert.equal(store.get('b_app.journey'),JSON.stringify(old));await journeyLoad();await flush();assert.equal(puts.length,1);
""")


@pytest.mark.parametrize('old', ['{','[]','null','{"version":1,"last_step":3,"completed":true,"dismissed":false,"first_success_at":null}'])
def test_invalid_v1_is_ignored(old):
    import json
    run_js(GUIDE_SETUP + 'store.set("b_app.journey",'+json.dumps(old)+');await journeyEnsure();await flush();assert.equal(puts.length,0);')


def test_evidence_only_for_top_problem_never_navigation_same_value_or_other_item():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
S.score.run=runData;go=async(id,args)=>{S.shell.route=id;S.focus={...S.focus,...args};};
await scoreOpenSource(runData.status_text.top_problem);assert.equal(S.journey.outcomes.t1.real,null);
for(const e of [{...evidence,mismatch:false},{...evidence,section:9},{...evidence,item:'Other'},{...evidence,run:'Other'}])emit('evidence_line_shown',e);
assert.equal(S.journey.outcomes.t1.real,null);emit('evidence_line_shown',evidence);await flush();
assert.equal(S.journey.outcomes.t1.real.count,1);assert.equal(S.journey.progress.t1.step,3);
emit('evidence_line_shown',evidence);assert.equal(S.journey.outcomes.t1.real.count,1);
for(const forbidden of ['T21-X01','fake-run','Fake criterion','fake.value','p2:L3'])assert.ok(!JSON.stringify(puts).includes(forbidden));
""")


def test_practice_is_separate_real_requires_section_ok_and_repeated_job_not_counted():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t2';j.progress.t2.state='in_progress';j.progress.t2.step=1;});
emit('try_result_viewed',{job:'p1',mode:'practice',section_ok:null});await flush();
assert.equal(S.journey.outcomes.t2.practice.count,1);assert.equal(S.journey.outcomes.t2.real,null);assert.equal(S.journey.progress.t2.step,1);
emit('try_result_viewed',{job:'p1',mode:'practice',section_ok:null});assert.equal(S.journey.outcomes.t2.practice.count,1);
emit('try_result_viewed',{job:'bad1',mode:'real',section_ok:false});assert.equal(S.journey.outcomes.t2.real,null);
assert.ok(el('journey-strip').textContent.includes(T('journey.trial.parse_failed')));
assert.ok(el('journey-strip').textContent.includes(T('journey.trial.parse_todo')));
journeyChange(j=>{j.pending={attempt:'a1',job:'r1',mode:'real',started_at:new Date().toISOString()};});
emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});await flush();assert.equal(S.journey.outcomes.t2.real.count,1);
assert.equal(S.journey.progress.t2.state,'completed');assert.equal(S.journey.pending,null);
emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});assert.equal(S.journey.outcomes.t2.real.count,1);
""")


def test_replay_only_resets_guide_and_preserves_pending_outcomes_other_storage():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();store.set('b_app.cards','keep');store.set('b_app.context','keep context');
emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});await flush();const old=clone(S.journey.outcomes);
journeyChange(j=>{j.pending={attempt:'a1',job:'r2',mode:'real',started_at:new Date().toISOString()};});
await journeyReplay();await flush();assert.equal(S.journey.progress.guide.screen,'G01');assert.equal(S.journey.progress.t1.step,0);assert.deepEqual(S.journey.outcomes,old);
assert.equal(S.journey.pending.job,'r2');assert.deepEqual(puts.at(-1).journey.outcomes,old);
assert.equal(store.get('b_app.cards'),'keep');assert.equal(store.get('b_app.context'),'keep context');
await guideClose();await go('s07');assert.ok(el('help-guide-records').textContent.includes(T('journey.history.keep_outcomes')));
""")


def test_run_list_loading_failure_and_no_null_optional_children():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();let reject;const normal=api;
api=(p,o)=>p.startsWith('/api/runs')?new Promise((_,r)=>reject=r):normal(p,o);
const pending=journeyLoadRuns();assert.equal(S.journeyUI.runsLoading,true);
reject(new Error('Runs failed'));await pending;
assert.equal(S.journeyUI.runsLoading,false);assert.equal(S.journeyUI.runsError,'Runs failed');
assert.equal(S.journeyUI.run,null);await guideOpen();
for(const id of ['guide-overlay','journey-strip','journey-notices'])assert.doesNotMatch(el(id).textContent,/null|undefined|false|⟦/);
""")


def test_no_runs_cannot_start_read_and_guide_never_claims_success():
    run_js(GUIDE_SETUP + r"""
runData=null;await journeyEnsure();await journeyLoadRuns();
assert.equal(S.journeyUI.run,null);await journeyStart('t1');assert.equal(S.journey.progress.active,null);
await guideOpen();for(let n=0;n<7;n++){await el('guide-next').click();await flush();}
assert.equal(S.journey.outcomes.t1.real,null);assert.equal(S.journey.outcomes.t2.real,null);
assert.equal(S.journey.outcomes.t2.practice,null);
""")


def test_score_step_only_accepts_visible_current_scored_key_and_missing_anchor():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
S.score.run=runData;S.shell.route='s02';emit('score_summary_shown',{run:'fake-run',key:S.ctx.key,weighted:71});
assert.equal(S.journey.progress.t1.step,0);S.shell.route='s01';
for(const e of [{run:'old',key:S.ctx.key,weighted:71},{run:'fake-run',key:'other',weighted:71},{run:'fake-run',key:S.ctx.key,weighted:null}])emit('score_summary_shown',e);
assert.equal(S.journey.progress.t1.step,0);emit('score_summary_shown',{run:'fake-run',key:S.ctx.key,weighted:71});
assert.equal(S.journey.progress.t1.step,1);assert.equal(S.journey.outcomes.t1.real,null);
go=async id=>{S.shell.route=id;};await journeyGo('s01','not-there');assert.equal(S.journey.progress.t1.step,1);
assert.ok(el('journey-strip').textContent.includes(T('journey.target_missing.title')));
""")


def test_actual_top_problem_source_flow_and_estimated_lines():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault(),problems:[]}:normal(p,o);
await journeyEnsure();S.score.run.status_text={top_problem:{name:'Fake criterion',section:8,docs:[{doc_id:'T21-X01'}]}};
journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
await scoreOpenSource(S.score.run.status_text.top_problem);await flush();
assert.equal(S.journey.outcomes.t1.real,null);pick(1).click();await flush();
assert.equal(S.journey.outcomes.t1.real.count,1);assert.equal(S.journey.progress.t1.state,'completed');
const before=S.journey.outcomes.t1.real.count;sourcePick(view.silver_only[0],'silver_only');assert.equal(S.journey.outcomes.t1.real.count,before);
assert.ok(el('source-page').querySelector('[aria-pressed="true"]'));assert.equal(S.journey.progress.t1.step,3);
""")


def test_trial_guide_real_flow_blank_target_fresh_model_pending_and_result():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
const normal=api;let stored=journeyDefault();
api=async(p,o)=>{if(p==='/api/journey'){if(o?.body)stored=JSON.parse(o.body).journey;return {journey:stored,problems:[]};}return normal(p,o);};
await journeyStart('t2');assert.equal(S.jobs.t.doc,null);assert.equal(S.jobs.t.secs.size,0);
assert.equal(el('journey-next').disabled,true);assert.equal(document.activeElement.id,'jobs-doc');
change(el('jobs-doc'),'T21-X01');S.jobs.t.secs=new Set([8]);jobsRenderTry();
assert.equal(S.journey.progress.t2.step,1);const before=requests.filter(p=>p==='/api/options').length;
await journeyNext();assert.ok(requests.filter(p=>p==='/api/options').length>before);assert.equal(S.journey.progress.t2.step,2);
await journeyNext();assert.equal(S.jobs.t.dry,false);assert.equal(S.journeyUI.phase,3);
listed=[job()];await jobsStartTry();assert.equal(S.journey.pending.job,'j1');assert.equal(S.journey.progress.t2.step,3);
response=result(true);listed=[job('done')];await jobsPoll();assert.equal(S.journey.outcomes.t2.real.count,1);
assert.equal(S.journey.progress.t2.step,4);assert.equal(S.journey.pending,null);
""")


def test_practice_full_flow_does_not_advance_model_stage():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault()}:normal(p,o);
options=makeOptions(false);await journeyStart('t2',true);
change(el('jobs-doc'),'T21-X01');S.jobs.t.secs=new Set([8]);jobsRenderTry();await journeyNext();
assert.equal(S.journey.progress.t2.step,1);assert.equal(el('journey-next').disabled,true);
listed=[job('running',{dry_run:true,target:{...target,dry_run:true}})];await jobsStartTry();
response={plan};listed=[job('done',{dry_run:true,target:{...target,dry_run:true}})];await jobsPoll();
assert.equal(S.journey.outcomes.t2.practice.count,1);assert.equal(S.journey.outcomes.t2.real,null);
assert.equal(S.journey.progress.t2.step,1);assert.equal(S.journeyUI.phase,2);
""")


def test_pending_done_on_refresh_can_open_result_without_resending():
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + r"""
let stored=journeyDefault();stored.progress.active='t2';stored.progress.t2={state:'in_progress',step:3,updated_at:null};
stored.pending={attempt:'a1',job:'j1',mode:'real',started_at:new Date().toISOString()};
const normal=api;api=async(p,o)=>{if(p==='/api/journey'){if(o?.body)stored=JSON.parse(o.body).journey;return {journey:stored};}return normal(p,o);};
listed=[job('done')];response=result(true);await journeyEnsure();await journeyOpenPending();
assert.equal(posted.length,0);assert.equal(S.journey.outcomes.t2.real.count,1);assert.equal(S.journey.pending,null);
""")


def test_detached_result_records_outcome_without_advancing_new_guide():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();journeyChange(j=>{j.progress.active='t2';j.progress.t2.state='in_progress';j.progress.t2.step=1;
 j.pending={attempt:'a1',job:'j1',mode:'real',started_at:new Date().toISOString()};});
journeySkip();journeyChange(j=>{j.progress.active='t2';j.progress.t2.state='in_progress';j.progress.t2.step=0;});
emit('try_result_viewed',{job:'j1',mode:'real',section_ok:true});assert.equal(S.journey.outcomes.t2.real.count,1);
assert.equal(S.journey.progress.t2.step,0);assert.equal(S.journey.progress.t2.state,'in_progress');
""")


@pytest.mark.parametrize('variant', ['multiple', 'unknown_dry', 'stopped'])
def test_trial_nonqualifying_results_never_record_success(variant):
    from test_B_b_app_jobs_ui import SETUP as JOBS_SETUP
    run_js(JOBS_SETUP + f"const variant='{variant}';" + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault()}:normal(p,o);
await journeyEnsure();const custom=job();if(variant==='multiple'){custom.target.sections=[8,9];plan.sections['9']={section:9};}
if(variant==='unknown_dry'){delete custom.dry_run;delete custom.target.dry_run;}
listed=[custom];await go('s03');await jobsWatch('j1');response=result(true);response.results['9']={ok:true};
custom.status=variant==='stopped'?'stopped':'done';custom.returncode=0;await jobsPoll();assert.equal(S.journey.outcomes.t2.real,null);
""")


def test_no_problem_or_link_shows_recovery_without_claiming_completion():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();S.journeyUI.phase=2;S.journeyUI.run=runData;
journeyChange(j=>{j.progress.active='t1';j.progress.t1={state:'in_progress',step:1,updated_at:null};});
assert.ok(el('journey-strip').textContent.includes(T('journey.unlinked.reason')));
assert.equal(el('journey-next').disabled,true);S.journeyUI.run.status_text.top_problem=null;journeyRender();
assert.ok(el('journey-strip').textContent.includes(T('journey.start.no_problem')));assert.equal(S.journey.outcomes.t1.real,null);
""")


def test_revisiting_guide_can_repeat_same_evidence_and_marks_only_real_missing_lines():
    from test_B_b_app_source_ui import fixture
    run_js(fixture() + r"""
const normal=api;api=async(p,o)=>p==='/api/journey'?{journey:o?.body?JSON.parse(o.body).journey:journeyDefault()}:normal(p,o);
await journeyEnsure();S.score.run.status_text={top_problem:{name:'Fake criterion',section:8,docs:[{doc_id:'T21-X01'}]}};
journeyChange(j=>{j.progress.active='t1';j.progress.t1.state='in_progress';});
await scoreOpenSource(S.score.run.status_text.top_problem);
assert.equal(el('journey-strip').textContent.includes(T('journey.start.no_line')),false);
assert.equal(S.journey.progress.t1.step,2);pick(1).click();await flush();assert.equal(S.journey.outcomes.t1.real.count,1);
// 다시 하기는 기존 성공을 그대로 두고 같은 실제 기능을 다시 연습할 수 있다.
S.journeyUI.target=null;S.journeyUI.runsLoaded=true;S.journeyUI.run={...runs[1],weighted:70};
journeyChange(j=>{j.progress=journeyDefault().progress;j.progress.active='t1';j.progress.t1.state='in_progress';});
await scoreOpenSource(S.score.run.status_text.top_problem);pick(1).click();await flush();
assert.equal(S.journey.outcomes.t1.real.count,2);assert.equal(S.journey.progress.t1.state,'completed');
""")


def test_unknown_pending_is_cleared_and_failed_lookup_keeps_retryable_job():
    run_js(GUIDE_SETUP + r"""
saved.pending={attempt:'a1',job:null,mode:'real',started_at:new Date().toISOString()};
await journeyEnsure();await flush();assert.equal(S.journey.pending,null);
assert.ok(el('journey-strip').textContent.includes(T('journey.pending.unknown')));
journeyChange(j=>{j.pending={attempt:'a2',job:'job2',mode:'real',started_at:new Date().toISOString()};});await flush();
const normal=api;api=async(p,o)=>{if(p==='/api/jobs')throw new Error('Jobs unreadable');return normal(p,o);};
await journeyCheckPending();journeyRender();assert.equal(S.journey.pending.job,'job2');
assert.ok(el('journey-notices').textContent.includes('Jobs unreadable'));
""")


def test_unsaved_success_survives_visibility_get_and_next_change_retries():
    run_js(GUIDE_SETUP + r"""
await journeyEnsure();failWrite=true;emit('try_result_viewed',{job:'r1',mode:'real',section_ok:true});await flush();
assert.equal(saved.outcomes.t2.real,null);await journeyLoad();assert.equal(S.journey.outcomes.t2.real.count,1);
failWrite=false;journeyDismiss();await flush();assert.equal(saved.outcomes.t2.real.count,1);
""")


def test_default_record_key_order_does_not_change_first_visit():
    run_js(GUIDE_SETUP + r"""
saved.progress={t2:saved.progress.t2,t1:{updated_at:null,step:0,state:'not_started'},dismissed_at:null,active:null};
await start();await flush();assert.equal(el('guide-overlay').hidden,false);
""")


def test_pending_failure_is_not_shown_as_waiting():
    run_js(GUIDE_SETUP + r"""
saved.pending={attempt:'a1',job:'j1',mode:'real',started_at:new Date().toISOString()};
const normal=api;api=async(p,o)=>p==='/api/jobs'?{jobs:[{id:'j1',status:'failed',error:{message:'Fake job failed',fix:'Retry input'}}]}:normal(p,o);
await journeyEnsure();assert.ok(el('journey-notices').textContent.includes('Fake job failed'));
assert.equal(el('journey-notices').textContent.includes(T('journey.trial.waiting')),false);
""")
