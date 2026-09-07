"""Real HTML/CSS/scripts + Flask routes, with deterministic turn outcomes.

No live narrator, remote image generation, or billing calls. The deliberately
stubbed resolution lets recovery, storage, rendering and controls be exercised
without changing a player's campaign. Run with pytest and Playwright Chromium.
"""
import copy
import os
import json
import re
from urllib.parse import urlsplit
from pathlib import Path
import shutil
import sys
import threading

import pytest
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'tests'))
from game import GameSession
from test_reliability_update import state


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True, executable_path=shutil.which('chromium') or shutil.which('google-chrome'))
        yield b
        b.close()


@pytest.fixture
def ui(browser,tmp_path,monkeypatch):
    import app
    game=GameSession(save_dir=tmp_path/'saves',settings_path=tmp_path/'settings.json')
    game.state=state();game.campaign_active=True
    game.settings.update(onboarding_seen=True,portrait_generation_enabled=False,sound_enabled=False,music_enabled=False,animations_enabled=False,
                         model='offline-test',provider='local',simulation_mode='economy',ai_connection_status='ready')
    monkeypatch.setattr(app,'game',game)
    monkeypatch.setattr(app,'_single_game',game)
    monkeypatch.setattr(app,'_start_due_lore_refresh_once',lambda:None)
    monkeypatch.setattr(game,'ai_ready',lambda:True)
    # Fail hard rather than accidentally contacting a paid provider.
    def no_network(*args,**kwargs):raise AssertionError('Unexpected external model request')
    monkeypatch.setattr('urllib.request.urlopen',no_network)
    calls=[]
    def resolve(*args,**kwargs):
        calls.append(1);game.state['hp']-=3;game.state['turn']+=1;game.state['canon_time_minutes']+=120
        game.state['xp']+=5;game.state['world_time']='Day 11 — Afternoon'
        game.append('The controlled training session is complete. Your stance becomes steadier.',canon_day=game.state['canon_day'])
        return {'status':'resolved','state':game.public_state(),'story':game.story_log[-1:], 'elapsed':{'amount':2,'unit':'hours'},'events':[]}
    monkeypatch.setattr(game,'run_time_skip',resolve)
    memory = os.getenv('WORLDWALKER_IN_MEMORY_BROWSER') == '1'
    server=make_server('127.0.0.1',0,app.app,threaded=True) if not memory else None
    thread=threading.Thread(target=server.serve_forever,daemon=True) if server else None
    if thread: thread.start()
    context=browser.new_context(viewport={'width':1366,'height':900})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('https://fonts.googleapis.com/**',lambda route:route.abort())
    page.route('https://fonts.gstatic.com/**',lambda route:route.abort())
    # Separate background jobs are not part of a player's resolving request.
    page.route('**/api/background/run',lambda route:route.fulfill(json={'started':False}))
    if memory:
        # Sandboxed Chromium disallows HTTP navigation. Keep the real shell,
        # styles/scripts and Flask handlers; replace only transport with an
        # in-process Response adapter and optional simulated response damage.
        client=app.app.test_client()
        def request_app(path,method,headers,body):
            if path.startswith('/api/background/run'):
                return {'status':200,'body':'{"started":false}'}
            parsed=urlsplit(path)
            response=client.open(parsed.path+('?' + parsed.query if parsed.query else ''),method=method,headers=headers,data=body)
            return {'status':response.status_code,'body':response.get_data(as_text=True)}
        page.expose_function('__fixtureRequest',request_app)
        html=(ROOT/'frontend/index.html').read_text()
        html=re.sub(r'<link[^>]*https://fonts[^>]*>', '', html)
        html=re.sub(r'<audio\b[^>]*>.*?</audio>',lambda m:re.sub(r' src="[^"]*"','',m[0]),html)
        html=re.sub(r'<script\b[^>]*src="([^"]+)"[^>]*></script>',lambda m:'<script>'+ (ROOT/'frontend'/urlsplit(m[1]).path.lstrip('/')).read_text().replace('</script>','<\\/script>')+'</script>',html)
        html=re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>',lambda m:'<style>'+ (ROOT/'frontend'/urlsplit(m[1]).path.lstrip('/')).read_text()+'</style>',html)
        # Load the optional workspace controller synchronously in the harness;
        # the real HTTP path and asynchronous loader are tested in CI mode.
        html=html.replace('</body>','<script>'+ (ROOT/'frontend/js/workspace-tabs.js').read_text()+'</script></body>')
        def boot(storage=None):
            page.goto('about:blank')
            page.evaluate("""values => {
              for (const name of ['localStorage','sessionStorage']) {
                const map=new Map(Object.entries(values[name]||{}));
                Object.defineProperty(window,name,{configurable:true,value:{getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k),clear:()=>map.clear(),export:()=>Object.fromEntries(map)}});
              }
              window.fetch=async (path,options={})=> {
                const headers=Object.fromEntries(new Headers(options.headers||{}));
                const route=new URL(String(path),'http://fixture.test').pathname;
                if(window.__fixtureFault && route===window.__fixtureFault.path && window.__fixtureFault.before){
                  const fault=window.__fixtureFault;delete window.__fixtureFault;return new Response(fault.body,{status:fault.status||200});
                }
                const response=await window.__fixtureRequest(String(path),options.method||'GET',headers,options.body||null);
                if(window.__fixtureFault && route===window.__fixtureFault.path){const fault=window.__fixtureFault;delete window.__fixtureFault;return new Response(fault.body,{status:fault.status||200});}
                return new Response(response.body,{status:response.status});
              };
            }""", storage or {})
            page.set_content(html,wait_until='domcontentloaded')
        boot()
        def reload_fixture():
            storage=page.evaluate('({localStorage:localStorage.export(),sessionStorage:sessionStorage.export()})')
            boot(storage)
        page.fixture_reload=reload_fixture
    else:
        page.goto(f'http://127.0.0.1:{server.server_port}/')
        page.fixture_reload=page.reload
    page.fixture_memory=memory
    page.wait_for_function('typeof APP !== "undefined" && APP.state && APP.state.name === "Ari"')
    page.wait_for_selector('[data-workspace-ready]')
    # Wait for the actual boot request, not a fixed sleep: Windows can deliver
    # the first-launch notes after the game state and workspace are ready.
    page.wait_for_selector('#modal-patch-notes.open')
    page.locator('#btn-patch-notes-done').click()
    page.wait_for_selector('#modal-patch-notes.open', state='hidden')
    yield page,game,calls
    assert not errors, errors
    context.close()
    if server: server.shutdown();thread.join(2)


def test_real_assess_and_advance_renders_receipt_and_keeps_tabs(ui):
    page,game,calls=ui
    page.evaluate('beginTimeSkip(1,"moment","Practice my stance","normal")')
    page.wait_for_selector('.turn-receipt')
    assert len(calls)==1 and page.evaluate('APP.state.turn')==6
    page.locator('.turn-receipt summary').click()
    assert '80 → 77' in page.locator('.turn-receipt').inner_text()
    page.locator('#action-input').fill('Keep my next idea intact.')
    page.locator('#workspace-map-tab').click()
    page.locator('#workspace-chronicle-tab').click()
    assert page.locator('#action-input').input_value()=='Keep my next idea intact.'
    assert page.locator('#story-feed').bounding_box()['height']>400
    screenshot=os.environ.get('WORLDWALKER_QA_SCREENSHOT')
    if screenshot:page.screenshot(path=screenshot)


@pytest.mark.parametrize('bad_body',['<html>proxy error</html>','{}','{"state":null}','{"state":{"world":"Overgeared","turn":"6"}}'])
def test_successful_but_unreadable_result_is_recovered_not_repeated(ui,bad_body):
    page,game,calls=ui
    def damage_response(route):
        response=route.fetch()
        assert response.status==200
        route.fulfill(status=200,content_type='text/html',body=bad_body)
    if page.fixture_memory: page.evaluate('(body)=>window.__fixtureFault={path:"/api/time/resolve",body}',bad_body)
    else: page.route('**/api/time/resolve',damage_response,times=1)
    error=page.evaluate('''async () => { try { await apiPost('/api/time/resolve',{orders:['Practice']}); return ''; }
      catch(e) { return e.message; } }''')
    assert error and len(calls)==1
    request_id=page.evaluate('APP.retryRequest.payload.request_id')
    assert page.locator('#turn-recovery-notice').is_visible()
    result=page.evaluate('''async () => { const pending=APP.retryRequest;
      const result=await apiPost(pending.path,pending.payload);
      renderState(result.state); appendStoryEntries(result.story); return result; }''')
    assert result['replayed_request'] and len(calls)==1
    assert page.evaluate('APP.retryRequest') is None
    assert page.locator('.turn-receipt').count()==1
    page.evaluate('(entries)=>appendStoryEntries(entries)',result['story'])
    assert page.locator('.turn-receipt').count()==1
    assert request_id


def test_pending_request_survives_browser_reload(ui):
    page,game,calls=ui
    def damage(route):
        route.fetch();route.fulfill(status=200,body='not json')
    if page.fixture_memory: page.evaluate('window.__fixtureFault={path:"/api/time/resolve",body:"not json"}')
    else: page.route('**/api/time/resolve',damage,times=1)
    page.evaluate('apiPost("/api/time/resolve",{orders:["Practice"]}).catch(()=>{})')
    original=page.evaluate('APP.retryRequest.payload.request_id')
    page.fixture_reload();page.wait_for_function('typeof APP!=="undefined" && APP.retryRequest')
    assert page.evaluate('APP.retryRequest.payload.request_id')==original
    result=page.evaluate('apiPost(APP.retryRequest.path,APP.retryRequest.payload)')
    assert result['replayed_request'] and len(calls)==1


def test_unknown_changed_state_is_not_resent(ui):
    page,game,calls=ui
    if page.fixture_memory: page.evaluate('window.__fixtureFault={path:"/api/time/resolve",body:"bad gateway",status:502,before:true}')
    else: page.route('**/api/time/resolve',lambda r:r.fulfill(status=502,body='bad gateway'),times=1)
    page.evaluate('apiPost("/api/time/resolve",{orders:["Practice"]}).catch(()=>{})')
    game.state['hp']-=1
    error=page.evaluate('apiPost(APP.retryRequest.path,APP.retryRequest.payload).then(()=>"").catch(e=>e.message)')
    assert 'safely match' in error and not calls
    assert page.evaluate('!!APP.retryRequest')


def test_confirmation_recovery_opens_confirmation_not_result(ui,monkeypatch):
    page,game,calls=ui
    monkeypatch.setattr(game,'run_time_skip',lambda *a,**k:{'status':'lethal_confirm_required','check':{'lethal_risk':'high','lethal_warning':'Confirm this test'}})
    def damage(route):route.fetch();route.fulfill(status=200,body='bad')
    if page.fixture_memory: page.evaluate('window.__fixtureFault={path:"/api/time/resolve",body:"not json"}')
    else: page.route('**/api/time/resolve',damage,times=1)
    page.evaluate('apiPost("/api/time/resolve",{orders:["Practice"]}).catch(()=>{})')
    page.locator('#btn-inline-retry').click()
    page.wait_for_selector('#modal-lethal.open')
    assert not calls and page.locator('.turn-receipt').count()==0


def test_contextual_suggestions_filter_unavailable_people_and_old_questions(ui):
    page,_,_=ui
    result=page.evaluate('''() => {
      const s=structuredClone(APP.state);s.hp=10;s.name='Ari';
      s.quests=[{name:'Old mission',status:'Completed'},{name:'Clinic',status:'Active',next_hint:'Deliver medicine'}];
      s.contacts={Gone:{status:'dead'},Mira:{last_known_location:s.location}};
      s.scene_state={location:s.location,turn:s.turn,unresolved_question:'Will you help the clinic?',present:['Mira']};
      s.obligation_ledger=[{owner:'Other NPC',text:'Hidden enemy plan',status:'due'},{owner:'Ari',text:'Deliver medicine',status:'due'}];
      const choices=buildActionDeckChoices(s);const recommended=choices.filter(r=>r.category==='recommended');
      s.scene_state.turn=-100;
      return {choices,recommended,stale:buildActionDeckChoices(s).filter(r=>r.category==='recommended')};
    }''')
    assert result['recommended'][0]['id'].endswith('personal-rest')
    assert not any('Gone' in r['text'] or 'Old mission' in r['text'] or 'Hidden enemy plan' in r['text'] for r in result['choices'])
    assert any('Will you help' in r['text'] for r in result['recommended'])
    assert not any('Will you help' in r['text'] for r in result['stale'])


@pytest.mark.parametrize('width',[390,721,1366,1920])
def test_long_chronicle_real_shell_at_responsive_widths(ui,width):
    page,game,calls=ui
    page.set_viewport_size({'width':width,'height':900})
    page.evaluate('''() => { const entries=Array.from({length:400},(_,i)=>({id:'old-'+i,text:'Historical scene '+i+'. '+ 'The campaign continues. '.repeat(12),tag:'narrative'}));appendStoryEntries(entries); }''')
    page.evaluate('beginTimeSkip(1,"moment","Practice my stance","normal")')
    page.wait_for_selector('.turn-receipt',state='attached')
    if width>720:
        assert page.locator('#story-feed').bounding_box()['height']>400
        page.locator('#workspace-map-tab').click()
        page.locator('#workspace-chronicle-tab').click()
    page.locator('.turn-receipt summary').scroll_into_view_if_needed()
    page.locator('.turn-receipt summary').click()
    assert page.locator('.turn-receipt-body').is_visible()
    overflow=page.evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,grid:getComputedStyle(document.querySelector('.app-shell')).gridTemplateColumns, elements:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2 && getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none').slice(0,15).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().right])})")
    # Hidden, fixed-position legacy modals contribute to scrollWidth. Verify
    # the visible interface instead of mistaking those closed dialogs for a
    # clipped campaign layout.
    assert not overflow['elements'], overflow


def test_map_zero_size_and_rebind_are_safe(browser):
    page=browser.new_page()
    page.set_content('<div id="wrap" style="display:none;width:800px;height:500px"><div id="plane"></div></div>')
    page.add_script_tag(content=(ROOT/'frontend/js/world-atlas.js').read_text())
    page.evaluate('''() => { const w=document.getElementById('wrap'),p=document.getElementById('plane');WorldAtlas.bind(w,p,'zero');WorldAtlas.refresh();WorldAtlas.zoom(2); }''')
    page.eval_on_selector('#wrap','e=>e.style.display="block"')
    page.wait_for_timeout(100)
    assert 'NaN' not in page.locator('#plane').get_attribute('style')
    assert 'scale(1)' in page.locator('#plane').get_attribute('style')
    page.evaluate('''() => { const w=document.getElementById('wrap'),p=document.getElementById('plane');WorldAtlas.bind(w,p,'zero');WorldAtlas.bind(w,p,'zero');w.dispatchEvent(new WheelEvent('wheel',{deltaY:-1,clientX:400,clientY:250,bubbles:true})); }''')
    assert 'scale(1.15)' in page.locator('#plane').get_attribute('style')
    page.close()
