from pathlib import Path
import shutil, re, sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
boot=root/'offline_bootstrap'
shutil.copy2(boot/'offline_mode.py',root/'backend/offline_mode.py')
shutil.copy2(boot/'offline-mode.js',root/'frontend/js/offline-mode.js')

# Offline repo defaults to local structured play while retaining normal save shape.
p=root/'backend/engine_core.py'; s=p.read_text()
if '"offline_mode": True' not in s:
    anchor='    "developer_mode": False,\n'
    if anchor not in s: raise SystemExit('engine_core DEFAULT_SETTINGS anchor changed')
    s=s.replace(anchor,'    "offline_mode": True,\n'+anchor,1)
p.write_text(s)

p=root/'backend/app.py'; s=p.read_text()
needle='"local_mode": game.local_mode()})'
if '"offline_mode": bool(game.settings.get("offline_mode", True))' not in s:
    if needle not in s: raise SystemExit('api_state anchor changed')
    s=s.replace(needle,'"offline_mode": bool(game.settings.get("offline_mode", True)),\n                     '+needle,1)
old='''def api_campaign_opening():\n    if not game.ai_ready():'''
new='''def api_campaign_opening():\n    if game.settings.get("offline_mode", True):\n        try:\n            from offline_mode import opening as offline_opening\n            return jsonify(offline_opening(game))\n        except Exception as e:\n            return err(e, 400)\n    if not game.ai_ready():'''
if old in s and new not in s: s=s.replace(old,new,1)
settings_anchor='"onboarding_seen", "simulation_mode", "canon_foreknowledge"'
if '"offline_mode", "onboarding_seen"' not in s:
    if settings_anchor not in s: raise SystemExit('settings whitelist anchor changed')
    s=s.replace(settings_anchor,'"offline_mode", "onboarding_seen", "simulation_mode", "canon_foreknowledge"',1)
if "/api/offline/actions" not in s:
    marker='\n\nif __name__ == "__main__":\n'
    if marker not in s: raise SystemExit('app end marker changed')
    routes='''\n\n# ---------- Offline Mode: structured local play over existing systems ----------\n@app.get('/api/offline/actions')\ndef api_offline_actions():\n    try:\n        from offline_mode import catalog\n        return jsonify(catalog(game))\n    except Exception as exc:\n        return err(exc, 400)\n\n\n@app.post('/api/offline/resolve')\ndef api_offline_resolve():\n    if not acquire_busy():\n        return busy_error()\n    try:\n        from offline_mode import resolve_action\n        payload=request.get_json(force=True) or {}\n        return jsonify(atomic_game_call('offline_resolve',payload,lambda:resolve_action(game,payload)))\n    except Exception as exc:\n        return err(exc,400)\n    finally:\n        release_busy()\n'''
    s=s.replace(marker,routes+marker,1)
p.write_text(s)

p=root/'frontend/index.html'; s=p.read_text()
if 'offline-mode.js' not in s:
    matches=list(re.finditer(r'(<script src="/js/app\.js\?v=[^"]+"></script>)',s))
    if not matches: raise SystemExit('app.js script tag not found')
    m=matches[-1]; s=s[:m.end()]+'\n<script src="/js/offline-mode.js?v=offline-mode-1"></script>'+s[m.end():]
p.write_text(s)

p=root/'frontend/css/style.css'; s=p.read_text(); css=(boot/'offline-mode.css').read_text()
if '/* Offline Mode — same Worldwalker shell' not in s: s+='\n\n'+css+'\n'
p.write_text(s)

p=root/'frontend/sw.js'; s=p.read_text()
if '/js/offline-mode.js' not in s:
    s=re.sub(r'("/js/api-client\.js\?v=[^"]+",\s*"/js/action-deck\.js\?v=[^"]+",)',r'\1 "/js/offline-mode.js?v=offline-mode-1",',s,count=1)
    if '/js/offline-mode.js' not in s: raise SystemExit('service worker shell anchor changed')
s=re.sub(r'const CACHE = "[^"]+";', 'const CACHE = "worldwalker-offline-v364-1";', s, count=1)
p.write_text(s)

shutil.copy2(boot/'test_offline_mode.py',root/'tests/test_offline_mode.py')
shutil.copy2(boot/'OFFLINE_MODE.md',root/'OFFLINE_MODE.md')
print('Offline Mode overlay applied to',root)
