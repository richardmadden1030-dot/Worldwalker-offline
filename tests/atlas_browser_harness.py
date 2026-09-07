"""Local-only disposable atlas QA. Never opens a real save or calls AI."""
import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
scratch=tempfile.TemporaryDirectory(prefix='worldwalker-atlas-qa-')
os.environ['WORLDWALKER_DATA_DIR']=scratch.name
os.environ['WORLDWALKER_ACCOUNTS_ENABLED']='0'
sys.path.insert(0,str(ROOT/'backend'))
import app as module
from flask import request,jsonify,redirect
from worlds import BASE_STATE,WORLD_DATA

def setup(world):
    state=copy.deepcopy(BASE_STATE)
    state.update(world=world,name='Atlas Test',location=WORLD_DATA[world]['map'][0][0],campaign_id='atlas-qa-'+world,turn=2)
    module._single_game.state=state
    module._single_game.campaign_active=True

@module.app.route('/qa/atlas',methods=['POST'])
def qa():
    data=request.get_json() or {}
    if data.get('world'):setup(data['world'])
    module._single_game.state.update(data.get('patch',{}))
    return jsonify(ok=True)

setup('Naruto')
@module.app.route('/qa/view/<world>')
def view(world):
    if world not in WORLD_DATA:return 'Unknown test world',404
    setup(world)
    return redirect('/')

if __name__=='__main__':module.app.run(host='127.0.0.1',port=int(sys.argv[1]) if len(sys.argv)>1 else 8788,threaded=True,use_reloader=False)
