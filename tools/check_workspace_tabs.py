"""Isolated browser regressions for the Map/Chronicle presentation layer.

Uses the production atlas/controller with a reduced center-column DOM and
representative sizing rules plus the v3.62.0 split/mobile selectors. Script
content is injected in-memory; HTTP loading and the full game are not tested. It does not boot the game
backend or make AI requests. Run: python -m pytest tools/check_workspace_tabs.py
Requires pytest, playwright and a Chromium installation.
"""
from pathlib import Path
import shutil
import pytest
sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'frontend/js/workspace-tabs.js'
ATLAS = ROOT / 'frontend/js/world-atlas.js'
FIXTURE = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<style>
:root{--bg:#0c0f1e;--panel:#16202f;--border:#3c5264;--accent:#c7a15c;--accent-rgb:199,161,92;--sub:#a9b7c2;--text:#eef2f0;--font-body:Arial,sans-serif}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:var(--bg);color:var(--text);font:14px Arial;overflow:hidden}
.app-shell{display:grid;grid-template-columns:230px minmax(0,1fr) 280px;grid-template-rows:56px minmax(0,1fr);grid-template-areas:"top top top" "left center right";height:100vh;gap:12px;padding:12px}
.topbar{grid-area:top}.col-left{grid-area:left}.col-center{grid-area:center;min-width:0;position:relative}.col-right{grid-area:right}
.col{display:flex;flex-direction:column;gap:12px;overflow-y:auto;padding-right:2px;min-height:0}.col.col-center{overflow:hidden;height:100%;min-height:0}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;overflow:hidden}.panel-head{padding:14px;border-bottom:1px solid var(--border);display:flex;gap:8px;align-items:center}.panel-head span{margin-right:auto}.panel-body{padding:14px}
.living-map-main{flex:1 1 64%;min-height:300px;overflow:hidden;display:flex;flex-direction:column;padding:0}
.living-map-main-body{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.living-map-main iframe{width:100%;height:100%;border:0;min-height:300px}
.col-center>.story-card{flex:0 1 35%;min-height:210px;display:flex;flex-direction:column}
.story-feed{flex:1;min-height:0;overflow:auto}.story-entry{padding:16px;border-bottom:1px solid var(--border);line-height:1.8}
.suggestion-dock{padding:12px;border-top:1px solid var(--border)}button,textarea{font:inherit}button{background:#213347;color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px}textarea{width:100%;height:150px;background:#0c0f1e;color:var(--text)}.mobile-bottom-nav,.mobile-chronicle-tools{display:none}
@media(max-width:800px){.living-map-main .map-wrap{min-height:calc(100dvh - 290px)}}
@media(max-width:720px){body{overflow:auto}.app-shell{display:flex;flex-direction:column;height:auto;min-height:100dvh;padding-bottom:64px}.topbar{height:48px}.col.col-center{height:auto;overflow:visible}.col{display:none}body[data-mobile-view="chronicle"] .col-center,body[data-mobile-view="map"] .col-center{display:flex}body[data-mobile-view="chronicle"] .living-map-main{display:none}body[data-mobile-view="map"] .story-card{display:none}body[data-mobile-view="map"] .living-map-main{display:flex;flex:1 1 auto;min-height:calc(100dvh - 230px)}.story-feed{height:auto;min-height:calc(100dvh - 430px);max-height:none;overflow:visible}.mobile-bottom-nav{display:flex;position:fixed;bottom:0;left:0;right:0;justify-content:space-around;background:#16202f;padding:10px}}
</style></head><body data-mobile-view="chronicle"><div class="app-shell">
<header class="topbar panel panel-head"><b>WORLDWALKER</b><span>Workspace regression fixture</span></header>
<aside class="col col-left"><section class="panel panel-body"><h3>Character</h3><p>Existing left rail</p><button data-journal="map">Open Map</button></section></aside>
<main class="col col-center">
<section id="living-map-main" class="panel living-map-main no-collapse" aria-label="Living world map"><div id="living-map-main-body" class="living-map-main-body"><iframe id="map-frame" title="Live map fixture" srcdoc="<html><body style='background:#19383e;color:#eef2f0;font:18px Georgia;padding:24px'><h2>Living world map fixture</h2><p>This iframe must not reload when tabs change.</p><button id='zoom' onclick='window.zoomLevel=(window.zoomLevel||1)+1;this.textContent=window.zoomLevel'>Zoom</button><script>window.instance=Math.random();window.zoomLevel=1;parent.mapLoads=(parent.mapLoads||0)+1;</script></body></html>"></iframe></div></section>
<section class="panel story-card no-collapse"><header class="panel-head story-head"><span id="chronicle-title">Chronicle</span><button id="btn-story-latest">Latest</button></header><div class="mobile-chronicle-tools">Existing filters</div><div id="story-feed" class="panel-body story-feed"></div><div class="suggestion-dock"><b>Possible next moves</b><p>Explore the region · Talk with your allies · Continue training</p></div></section>
</main><aside class="col col-right"><section class="panel panel-body"><h3>Action Chat</h3><textarea id="action-input">Keep my draft intact.</textarea><button id="btn-event-window-continue">Acknowledge event</button></section></aside></div>
<nav id="mobile-bottom-nav" class="mobile-bottom-nav"><button data-mobile-view="chronicle" aria-selected="true">Chronicle</button><button data-mobile-view="map" aria-selected="false">Map</button></nav>
<script>
window.mapLoads=0;window.focusCalls=0;
window.focusApprovedLivingMap=function(){window.focusCalls++;return 'original-result';};
var feed=document.getElementById('story-feed');
feed.innerHTML=Array.from({length:30},(_,i)=>'<article class="story-entry" data-log-index="'+i+'"><b>Story beat '+(i+1)+'</b><p>Your campaign continues. This sample text checks that the Chronicle has space to read and can scroll to its final entry.</p><button>Inspect entry</button></article>').join('');
window.originalFeed=feed;window.originalFrame=document.getElementById('map-frame');window.originalMapParent=document.getElementById('living-map-main').parentElement;
document.getElementById('btn-story-latest').onclick=()=>feed.scrollTop=feed.scrollHeight;
document.querySelectorAll('#mobile-bottom-nav button').forEach(b=>b.onclick=()=>{document.body.dataset.mobileView=b.dataset.mobileView;document.querySelectorAll('#mobile-bottom-nav button').forEach(p=>p.setAttribute('aria-selected',String(p===b)));});
</script><script src="/js/world-atlas.js"></script></body></html>'''

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        executable = shutil.which('chromium') or shutil.which('google-chrome')
        b = p.chromium.launch(headless=True, executable_path=executable)
        yield b
        b.close()

@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={'width':1366,'height':768})
    page = context.new_page()
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    # In-memory documents keep this test offline. Storage is simulated so the
    # preference can be tested even on an opaque about:blank origin.
    page.goto('about:blank')
    page.evaluate("""() => {
      const values = new Map();
      Object.defineProperty(window, 'localStorage', {configurable:true, value:{
        getItem:key=>values.get(key)??null,
        setItem:(key,value)=>values.set(key,String(value)),
        removeItem:key=>values.delete(key)
      }});
    }""")
    page.set_content(FIXTURE.replace('<script src="/js/world-atlas.js"></script>', ''))
    page.add_script_tag(content=ATLAS.read_text(encoding='utf-8'))
    page.add_script_tag(content=SCRIPT.read_text(encoding='utf-8'))
    page.wait_for_selector('[data-workspace-ready]')
    page.wait_for_function('window.mapLoads === 1')
    yield page
    assert not page.errors, page.errors
    context.close()

def selected(page):
    return page.locator('.col-center').get_attribute('data-workspace-view')

def settle(page):
    page.wait_for_timeout(340)

def test_default_readable_and_latest_reachable(page):
    assert selected(page) == 'chronicle'
    assert page.locator('#story-feed').bounding_box()['height'] > 450
    assert page.locator('#living-map-main').get_attribute('inert') == ''
    page.locator('#btn-story-latest').click()
    assert page.eval_on_selector('#story-feed','e => Math.abs(e.scrollHeight-e.clientHeight-e.scrollTop) < 2')
    assert page.locator('.suggestion-dock').bounding_box()['height'] > 30

def test_map_dimensions_iframe_scroll_and_draft_survive(page):
    page.eval_on_selector('#story-feed', 'e => e.scrollTop=420')
    instance = page.frames[1].evaluate('window.instance')
    before = page.locator('#living-map-main').evaluate('e=>[e.clientWidth,e.clientHeight]')
    page.locator('#workspace-map-tab').click(); settle(page)
    assert page.locator('#living-map-main').evaluate('e=>[e.clientWidth,e.clientHeight]') == before
    page.frames[1].locator('#zoom').click()
    for _ in range(5):
        page.locator('#workspace-chronicle-tab').click()
        page.locator('#workspace-map-tab').click()
    settle(page)
    assert page.frames[1].evaluate('window.instance') == instance
    assert page.frames[1].evaluate('window.zoomLevel') == 2
    assert page.evaluate('window.mapLoads') == 1
    page.locator('#workspace-chronicle-tab').click(); settle(page)
    assert page.eval_on_selector('#story-feed','e=>e.scrollTop') == 420
    assert page.locator('#action-input').input_value() == 'Keep my draft intact.'
    assert page.evaluate('originalFeed===document.getElementById("story-feed") && originalFrame===document.getElementById("map-frame") && originalMapParent===document.getElementById("living-map-main").parentElement')

def test_unread_and_identical_rerenders(page):
    page.locator('#workspace-map-tab').click()
    page.eval_on_selector('#story-feed','e=>e.innerHTML=e.innerHTML'); settle(page)
    assert page.locator('.workspace-tab-badge').is_hidden()
    page.eval_on_selector('#story-feed','e=>e.insertAdjacentHTML("beforeend","<article>A new quest is available.</article>")'); settle(page)
    assert page.locator('.workspace-tab-badge').is_visible()
    assert 'new updates' in page.locator('#workspace-chronicle-tab').get_attribute('aria-label')
    assert selected(page) == 'map'
    page.locator('#workspace-chronicle-tab').click()
    assert page.locator('.workspace-tab-badge').is_hidden()

def test_keyboard_and_inactive_panel_focus(page):
    page.locator('#workspace-chronicle-tab').focus()
    page.keyboard.press('ArrowRight')
    assert selected(page)=='map'
    assert page.evaluate('document.activeElement.id') == 'workspace-map-tab'
    page.keyboard.press('Home')
    assert selected(page)=='chronicle'
    page.keyboard.press('End')
    assert selected(page)=='map'
    page.locator('#btn-story-latest').evaluate('e=>e.focus()')
    assert page.evaluate('document.activeElement.id') != 'btn-story-latest'
    assert page.locator('#workspace-map-tab').get_attribute('aria-controls')=='living-map-main'

def test_saved_view_and_programmatic_map_shortcut(page):
    page.locator('#workspace-map-tab').click()
    page.set_content(FIXTURE.replace('<script src="/js/world-atlas.js"></script>', ''))
    page.add_script_tag(content=SCRIPT.read_text(encoding='utf-8'))
    page.wait_for_selector('[data-workspace-ready]')
    assert selected(page)=='map'
    page.locator('#workspace-chronicle-tab').click()
    assert page.evaluate('focusApprovedLivingMap()') == 'original-result'
    assert page.evaluate('window.focusCalls') == 1
    assert selected(page)=='map'
    page.locator('#btn-event-window-continue').click()
    assert selected(page)=='chronicle'
    page.locator('[data-journal="map"]').click()
    assert selected(page)=='map'

@pytest.mark.parametrize('width', [390,720,721,800,801,1024,1920])
def test_breakpoints_and_mobile_restore(page,width):
    page.locator('#workspace-map-tab').click()
    page.set_viewport_size({'width':width,'height':844}); settle(page)
    if width <=720:
        assert page.locator('.workspace-tabs').is_hidden()
        assert page.locator('#living-map-main').get_attribute('inert') is None
        assert page.locator('.story-card').get_attribute('inert') is None
        assert page.locator('.story-card').get_attribute('role') is None
        assert page.locator('#story-feed').is_visible()
        page.locator('#mobile-bottom-nav [data-mobile-view="map"]').click()
        assert page.locator('#living-map-main').is_visible()
        assert page.locator('.story-card').is_hidden()
        page.locator('#mobile-bottom-nav [data-mobile-view="chronicle"]').click()
        assert page.locator('#story-feed').is_visible()
    else:
        assert page.locator('.workspace-tabs').is_visible()
        assert page.locator('#living-map-main').is_visible()
        assert page.locator('#living-map-main').bounding_box()['height'] > 600
        page.locator('#workspace-chronicle-tab').click(); settle(page)
        assert page.locator('#story-feed').bounding_box()['height'] > page.locator('.story-card').bounding_box()['height'] * .6
    page.set_viewport_size({'width':1366,'height':768}); settle(page)
    assert page.locator('.workspace-tabs').is_visible()
    assert page.locator('.workspace-panel:not(.is-workspace-active)').get_attribute('inert') == ''


def test_reduced_motion_duplicate_init_and_blocked_storage(page):
    page.emulate_media(reduced_motion='reduce')
    page.locator('#workspace-map-tab').click()
    assert page.eval_on_selector('#living-map-main','e=>getComputedStyle(e).animationName')=='none'
    assert page.eval_on_selector('.workspace-tab-indicator','e=>getComputedStyle(e).transitionDuration')=='0s'
    page.add_script_tag(content=SCRIPT.read_text(encoding='utf-8'))
    assert page.locator('.workspace-tabs').count()==1
    assert page.locator('#workspace-tabs-style').count()==1
    page.evaluate("Object.defineProperty(window,'localStorage',{configurable:true,get(){throw new Error('blocked')}})")
    page.set_content(FIXTURE.replace('<script src="/js/world-atlas.js"></script>', ''))
    page.add_script_tag(content=SCRIPT.read_text(encoding='utf-8'))
    page.wait_for_selector('[data-workspace-ready]')
    assert selected(page)=='chronicle'
    page.locator('#workspace-map-tab').click()
    assert selected(page)=='map'


def test_atlas_renderer_still_works(page):
    page.evaluate('''() => {
      const host=document.getElementById('living-map-main-body');
      const wrap=document.createElement('div');wrap.className='map-wrap';wrap.style.cssText='position:relative;flex:1;overflow:hidden';
      const plane=document.createElement('div');plane.style.cssText='position:absolute;transform-origin:0 0';wrap.append(plane);host.replaceChildren(wrap);
      WorldAtlas.render(plane,{id:'fixture',context:{extent:'diagram'},cells:[],land:[{polygon:[[10,10],[90,10],[90,90],[10,90]]}],labels:[]},'fixture');
      WorldAtlas.bind(wrap,plane,'fixture');window.testPlane=plane;
    }''')
    page.locator('#workspace-map-tab').click(); settle(page)
    assert page.locator('.atlas-geography').count()==1
    assert page.evaluate('testPlane.clientWidth>0')
    page.evaluate('WorldAtlas.zoom(2)')
    before=page.evaluate('testPlane.style.transform')
    page.locator('#workspace-chronicle-tab').click()
    page.locator('#workspace-map-tab').click(); settle(page)
    assert page.evaluate('testPlane.style.transform')==before
    assert 'NaN' not in before
