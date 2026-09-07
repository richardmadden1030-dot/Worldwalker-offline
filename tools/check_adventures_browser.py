"""Production shell, signed activity APIs and tactical controls; no paid models.

The inherited fixture uses a real loopback Flask server in CI; sandbox-only
in-memory transport is opt-in. Activities themselves run their actual rules.
"""
import copy
import os
import re
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).parent))
from check_reliability_browser import browser, ui, ROOT
from test_living_adventures import mission
from world_calendar import view


def map_home(page):
    if page.viewport_size['width'] <= 720:
        page.locator('#mobile-bottom-nav [data-mobile-view="map"]').click()
    else:
        page.locator('#workspace-map-tab').click()
    page.wait_for_selector('[data-location-home]')
    page.locator('[data-location-home]').click()
    page.wait_for_selector('[data-town-action="rest:60"]')


def review(page,action):
    b=page.locator(f'[data-town-action="{action}"]')
    # Open a genuine collapsed group, never force-click through it.
    parent=b.locator('xpath=ancestor::details[1]')
    if parent.count() and parent.get_attribute('open') is None:
        parent.locator('summary').click()
    b.click()
    page.wait_for_function("!!document.querySelector('#adventure-confirmation[open] [data-confirm-yes]:not(:disabled)')")


def confirm(page):
    page.locator('[data-confirm-yes]').click()
    page.wait_for_function('!APP.busy')
    page.wait_for_selector('#adventure-confirmation[open]',state='hidden')


def test_timed_confirmation_cancel_then_real_resolution_preserves_draft_and_plan(ui):
    page,game,calls=ui
    game.state['queued_actions']=['Do not lose this future plan']
    game.state['standing_orders']=['Maintain my existing watch']
    # Load the new state once before quoting, just as ordinary polling does.
    page.evaluate('apiGet("/api/state").then(r=>renderState(r.state))')
    map_home(page)
    page.locator('#action-input').fill('My own unrelated idea stays here.')
    assert '1h' in page.locator('[data-town-action="rest:60"]').inner_text()
    before=copy.deepcopy(game.state)
    review(page,'rest:60')
    assert '1h will pass' in page.locator('.adventure-time').inner_text()
    assert view(game.state)['date'] in page.locator('.adventure-time').inner_text()
    page.locator('[data-confirm-cancel]').click()
    assert game.state==before
    review(page,'rest:60');confirm(page)
    assert game.state['canon_time_minutes']==before['canon_time_minutes']+60
    assert game.state['queued_actions']==before['queued_actions']
    assert game.state['standing_orders']==before['standing_orders']
    assert not calls
    assert page.locator('#action-input').input_value()=='My own unrelated idea stays here.'
    assert page.locator('.turn-receipt').count()==1
    page.locator('#workspace-map-tab').click()
    page.wait_for_selector('[data-town-action="rest:60"]')
    if not page.fixture_memory:
        page.wait_for_function("document.querySelector('.adventure-location-art')?.naturalWidth > 0")
    screenshot=os.getenv('WORLDWALKER_ADVENTURE_SCREENSHOT')
    if screenshot:page.screenshot(path=screenshot)


def test_confirming_training_uses_displayed_time_and_real_progress(ui):
    page,game,calls=ui
    game.state.update(resource=100,resource_max=100)
    page.evaluate('apiGet("/api/state").then(r=>renderState(r.state))')
    map_home(page);stat=next(iter(game.state['stats']));before=game.state['canon_time_minutes']
    review(page,'train:'+stat);assert '2h' in page.locator('[data-confirm-yes]').inner_text()
    confirm(page)
    assert game.state['canon_time_minutes']==before+120 and not calls


def test_real_purchase_requires_confirmation_and_stock_is_not_duplicated(ui):
    page,game,_=ui
    game.state['shops']=[{'name':'Road supplier','location':'Winston','inventory':[{'name':'Field rope','price':2,'stock':2}]}]
    page.evaluate('apiGet("/api/state").then(r=>renderState(r.state))');map_home(page)
    buy=page.locator('[data-town-action^="purchase:"]').get_attribute('data-town-action')
    review(page,buy);assert '10 min' in page.locator('[data-confirm-yes]').inner_text()
    confirm(page)
    assert game.state['shops'][0]['inventory'][0]['stock']==1
    assert sum(i.get('quantity',1) for i in game.state['inventory'] if i.get('name')=='Field rope')==1


def test_stale_confirmation_is_rejected_without_spending(ui):
    page,game,_=ui;map_home(page);review(page,'rest:60');game.state['hp']-=1
    minute=game.state['canon_time_minutes']
    page.locator('[data-confirm-yes]').click();page.wait_for_function('!APP.busy')
    assert page.locator('[data-confirm-error]').inner_text()
    assert game.state['canon_time_minutes']==minute
    page.locator('[data-confirm-cancel]').click()


def test_remote_location_plans_real_journey_no_remote_services(ui):
    page,game,calls=ui;map_home(page)
    routes=page.evaluate('apiGet("/api/adventures/routes?destination=Reinhardt")')
    assert routes['routes']
    page.evaluate('LivingAdventures.showLocation("Reinhardt")')
    page.wait_for_selector('[data-route-id]:not(:disabled)')
    assert page.locator('[data-town-action]').count()==0
    old=game.state['canon_time_minutes']
    page.locator('[data-route-id]:not(:disabled)').first.click()
    page.wait_for_function("!!document.querySelector('[data-confirm-yes]:not(:disabled)')")
    page.locator('[data-confirm-cancel]').click();assert game.state['canon_time_minutes']==old
    page.locator('[data-travel-preparation]').select_option('cautious')
    page.wait_for_selector('[data-route-id]:not(:disabled)')
    page.locator('[data-route-id]:not(:disabled)').first.click()
    page.wait_for_function("!!document.querySelector('[data-confirm-yes]:not(:disabled)')")
    # Discard scheduled reference events only in this journey fixture so the
    # chosen route is exercised without a deliberate calendar interruption.
    confirm(page)
    assert game.state['canon_time_minutes']>old and not calls
    assert game.state['location']=='Reinhardt' or game.state['adventures'].get('journey')


def test_canon_is_visible_searchable_and_planning_spends_no_time(ui):
    page,game,_=ui;before=copy.deepcopy(game.state)
    page.evaluate('openJournal("timeline")')
    page.wait_for_selector('.canon-reference-head')
    assert 'SPOILERS VISIBLE' in page.locator('.canon-reference-head').inner_text()
    page.locator('[data-canon-filter]').select_option('upcoming')
    page.wait_for_selector('[data-canon-plan]')
    first=page.locator('[data-canon-plan]').first.get_attribute('data-canon-plan')
    page.locator('[data-canon-search]').fill(first)
    assert first in page.locator('[data-canon-list]').inner_text()
    page.locator('[data-canon-plan]').first.click()
    assert first in page.locator('#action-input').input_value()
    assert game.state['canon_time_minutes']==before['canon_time_minutes']
    assert game.state.get('npc_knowledge')==before.get('npc_knowledge')


@pytest.mark.parametrize('width',[390,721,1024,1920])
def test_locations_and_confirmation_fit_responsive_shell(ui,width):
    page,game,_=ui;page.set_viewport_size({'width':width,'height':900});map_home(page)
    details=page.locator('#map-detail').bounding_box()
    assert details['width']>=240 and details['x']>=-2
    assert details['x']+details['width']<=width+2
    review(page,'rest:60')
    d=page.locator('#adventure-confirmation').bounding_box()
    assert d['x']>=0 and d['x']+d['width']<=width and d['y']>=0 and d['height']<=900
    page.locator('[data-confirm-cancel]').click()


def test_explicit_mission_acceptance_and_aftermath_link(ui):
    page,game,_=ui;map_home(page);before=game.state['canon_time_minutes']
    review(page,'mission:accept');confirm(page)
    assert game.state['canon_time_minutes']==before+15
    assert game.state['adventures']['active']['status']=='active'
    page.locator('#workspace-map-tab').click();review(page,'mission:withdraw');confirm(page)
    assert game.state['adventures'].get('active') is None
    page.locator('#workspace-map-tab').click()
    page.wait_for_selector('[data-aftermath-story]')
    page.locator('[data-aftermath-story]').first.click()
    page.wait_for_selector('.adventure-source')
    assert 'Recorded aftermath' in page.locator('#adventure-confirm-title').inner_text()
    assert page.locator('[data-confirm-yes]').is_disabled()


def tactical_page(page):
    if not page.fixture_memory:
        origin=page.url.split('/',3)[:3]
        page.goto('/'.join(origin)+'/tactical/campaign.html')
    else:
        from urllib.parse import urlsplit
        folder=ROOT/'frontend/tactical'
        html=(folder/'campaign.html').read_text()
        html=re.sub(r'<script\b[^>]*src="([^"]+)"[^>]*></script>',lambda m:'<script>'+(folder/urlsplit(m[1]).path).read_text().replace('</script>','<\\/script>')+'</script>',html)
        html=re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>',lambda m:'<style>'+(folder/urlsplit(m[1]).path).read_text()+'</style>',html)
        page.goto('about:blank')
        page.evaluate('''() => {
          window.fetch=async(path,options={})=>{
            const r=await __fixtureRequest(String(path),options.method||'GET',Object.fromEntries(new Headers(options.headers||{})),options.body||null);
            return new Response(r.body,{status:r.status});
          };
        }''')
        page.set_content(html,wait_until='domcontentloaded')
    page.wait_for_selector('#objective-panel:not([hidden])')


@pytest.mark.parametrize('kind',['retrieval','protection','escape'])
def test_tactical_objective_markers_survive_highlighting_and_controls(ui,kind):
    page,game,calls=ui;b,g=mission(game,kind)
    tactical_page(page)
    assert page.locator('.objective-exit').count()==(0 if kind=='protection' else 1)
    assert page.locator('.objective-target').count()==(0 if kind=='escape' else 1)
    page.locator('#attack').click();page.locator('#move').click()
    assert page.locator('.objective-exit').count()==(0 if kind=='protection' else 1)
    assert page.locator('.objective-target').count()==(0 if kind=='escape' else 1)
    assert 'Visible enemy intentions' in page.locator('#objective-panel').inner_text()
    if kind=='escape':assert page.locator('#objective').is_hidden()
    assert not calls
    screenshot=os.getenv('WORLDWALKER_ADVENTURE_SCREENSHOT')
    if screenshot and kind=='protection':
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(full_page=True,path=str(Path(screenshot).with_name('living-objective-qa.png')))


def test_retrieval_from_real_tactical_controls_not_kill_all(ui):
    page,game,calls=ui;b,g=mission(game,'retrieval')
    actor=next(u for u in b['units'] if u.get('player'))
    # Keep one short route so this is a UI contract test, not a balance test.
    b['obstacles']=[];g['target']=[actor['x']+1,actor['y']];g['exit']=[actor['x'],actor['y']]
    for u in b['units']:
        if u['side']=='enemy':u['hp']=0;u['defeated']=True
    tactical_page(page)
    assert game.state['combat']['active']
    assert page.locator('#story').is_disabled()
    page.locator('#objective').click()
    page.wait_for_function('view && !view.combat.active')
    assert game.state['combat']['outcome']=='objective_complete'
    assert len(game.state['adventures']['aftermath'])==1
    assert page.locator('#story').is_enabled()
    assert not calls
