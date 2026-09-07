"""Versioned, start-independent political atlas. Never writes to campaign saves.

Coordinates are schematic (not survey-grade canon). Each land tile has exactly
one owner. Geography is immutable; narrative claims replace ownership only.
See MAP_ATLAS_AUDIT.md for the canon/gameplay boundary.
"""
import copy
import hashlib
import math
import re
from collections import deque
from functools import lru_cache
from atlas_context import contextualize, explicitly_established, VILLAGE_COUNTRIES
from atlas_districts import AUTHORED_DISTRICTS

STEP = 1.5
DY = STEP * math.sqrt(3) / 2


def land(points, owner, label, x, y, terrain="green"):
    return {"polygon": points, "owner": owner, "name": label, "x": x, "y": y, "terrain": terrain}


def island(x, y, rx=4, ry=5):
    # Authored angular coastline, not a radius used as a territorial blob.
    shape = [(-1,-.25),(-.7,-.8),(-.25,-1),(.1,-.77),(.6,-.95),(.87,-.35),(.68,0),(1,.4),(.36,.65),(.1,1),(-.6,.74),(-.8,.22)]
    return [[round(x+dx*rx,3), round(y+dy*ry,3)] for dx,dy in shape]


CONTINENT = [[3,9],[17,4],[25,7],[35,4],[48,7],[61,3],[72,7],[83,5],[92,13],[94,25],[89,32],[94,39],[89,46],[93,56],[86,62],[88,71],[77,78],[72,88],[62,92],[51,86],[43,92],[30,86],[24,78],[12,81],[7,69],[11,59],[4,49],[8,37],[3,26]]
NARUTO_LAND = [[2,5],[21,3],[37,7],[49,3],[57,7],[64,4],[72,7],[77,4],[81,12],[79,23],[84,27],[81,33],[74,35],[72,43],[75,48],[71,52],[70,60],[64,63],[62,72],[55,73],[52,83],[43,91],[36,88],[29,93],[19,87],[11,90],[3,80],[5,69],[1,60],[4,49],[2,37],[4,23]]
JAPAN = [
    [[80,4],[85,9],[90,8],[95,14],[90,21],[86,24],[82,20],[77,23],[75,17],[78,13]],
    [[74,26],[80,28],[78,34],[80,38],[76,44],[76,49],[71,54],[69,60],[72,63],[66,67],[60,65],[55,67],[51,64],[46,66],[43,64],[37,69],[30,68],[28,65],[34,61],[42,60],[45,57],[50,59],[56,55],[61,55],[65,48],[67,42],[70,37],[69,31]],
    [[32,72],[39,70],[45,72],[41,76],[36,79],[30,77]],
    [[22,70],[28,72],[28,79],[24,82],[23,90],[18,87],[16,81],[19,77],[17,74]],
]


def preset(world, board=""):
    """Seeds define districts; identical owners have no internal border."""
    positions, seeds, lands, labels, structures = {}, [], [], [], []
    def seed(name, owner, x, y):
        seeds.append(dict(name=name, owner=owner, x=x, y=y))
    if world == "Naruto":
        lands = [land(NARUTO_LAND,"Konohagakure","Shinobi mainland",45,48),land(island(85,61,9,16),"Kirigakure","Land of Water",85,61),land(island(70,78,4,4),"Land of Waves","Land of Waves",70,78),land(island(68,68,2.8,3),"Land of Whirlpools","Land of Whirlpools",68,68)]
        for row in [("Land of Earth","Iwagakure",20,20),("Land of Wind","Sunagakure",20,67),("Land of Fire","Konohagakure",51,52),("Land of Lightning","Kumogakure",73,19),("Iron Country","Iron Country",49,13),("Land of Rain","Amegakure",31,47),("Land of Grass","Kusagakure",37,34),("Land of Waterfalls","Takigakure",44,26),("Land of Rice Fields","Otogakure",58,30),("Land of Hot Water","Yugakure",67,44),("Land of Rivers","Land of Rivers",39,70),("Land of Tea","Land of Tea",51,77)]: seed(*row)
        positions = {"Kusagakure":(37,34),"Takigakure":(44,26),"Kannabi Bridge":(34,35),"Valley of the End":(49,42),"Otogakure":(60,31),"Land of Rice Fields":(58,28),"Kirigakure":(85,61),"Land of Waves":(70,78),"Uzushiogakure Ruins":(68,68),"Fourth War Front":(67,34)}
        labels=[("SOUTHERN SEA",79,91)]
    elif world == "One Piece":
        # A route chart, with deliberately enlarged islands. Sky/subsea sites
        # remain markers, not extra countries superimposed on the ocean.
        rows=[("Dawn Island","Goa Kingdom",78,18,5,6),("Shells Town","Marines",91,23,3,4),("Orange Town","Organ Islands",67,22,3,4),("Syrup Village","Gecko Islands",61,29,3,4),("Conomi Islands","Arlong Pirates",78,33,4,5),("Loguetown","World Government",58,37,3,4),("Whiskey Peak","Cactus Island",17,51,2.3,4),("Little Garden","Little Garden",24,47,2.5,4),("Drum Island","Drum Kingdom",30,55,3,5),("Alabasta","Alabasta Kingdom",37,48,4,6),("Jaya","Jaya communities",43,56,2.5,4),("Water 7","Water 7",46,46,2.3,3),("Enies Lobby","World Government",47,37,2,3),("Sabaody","World Government",54,46,2,3),("Amazon Lily","Kuja",34,69,3,4),("Impel Down","World Government",44,67,1.5,3),("Marineford","Marines",51,59,2,3),("Punk Hazard","World Government",61,52,2.5,4),("Dressrosa","Dressrosa Kingdom",67,46,3,4),("Zou","Mokomo Dukedom",74,57,2,3),("Totto Land","Big Mom Pirates",81,46,4,5),("Wano Country","Kaido's Beasts Pirates",87,59,4,6),("Egghead Island","World Government",94,48,2.5,4),("Ohara","Ohara",26,79,2.5,4),("Kano Country","Kano Country",18,70,3,4),("Sorbet Kingdom","Sorbet Kingdom",71,83,4,5),("Baltigo","Revolutionary Army",39,83,3,4),("Lulusia Kingdom","Lulusia Kingdom",59,76,3,4)]
        for name,owner,x,y,rx,ry in rows:
            lands.append(land(island(x,y,rx,ry),owner,name,x,y)); positions[name]=(x,y)
        lands += [land([[8,0],[11,0],[12,32],[10,47],[12,63],[11,100],[8,100],[9,63],[7,47],[9,31]],"World Government","Red Line · western meridian",9,20,"stone"),land([[52,0],[55,0],[54,30],[56,42],[55,69],[57,100],[54,100],[52,70],[53,42],[51,28]],"World Government","Red Line",53,20,"stone")]
        positions.update({"Foosha Village":(79,20),"Goa Kingdom":(76,16),"Cocoyasi Village":(76,31),"Arlong Park":(80,34),"Shimotsuki Village":(81,15),"Baratie":(65,36),"Reverse Mountain":(9,48),"Mary Geoise":(53,41),"Skypiea":(42,29),"Fishman Island":(54,66),"Thriller Bark":(41,62),"Germa Kingdom":(25,17)})
        labels=[("NORTH BLUE",30,17),("EAST BLUE",72,8),("WEST BLUE",18,91),("SOUTH BLUE",80,93),("PARADISE",29,39),("NEW WORLD",74,68)]
    elif world == "Hunter x Hunter":
        lands=[land([[6,15],[16,9],[23,13],[31,11],[36,19],[33,26],[39,32],[34,42],[39,50],[33,60],[23,63],[19,57],[11,59],[7,47],[10,36],[5,28]],"Republic of Padokea","Padokea",23,37),land([[44,24],[54,19],[63,24],[67,31],[65,42],[60,50],[54,57],[44,54],[40,46],[43,37]],"Yorbian states","Yorbian continent",51,38),land(island(80,32,13,18),"Kakin Empire","Kakin Empire",80,32),land([[42,68],[48,64],[56,66],[64,64],[69,70],[67,79],[58,82],[52,78],[44,80],[39,74]],"Mitene Union","Mitene Union",54,72),land(island(79,66,5,7),"Greed Island administrators","Greed Island",79,66),land(island(24,78,4,5),"Whale Island community","Whale Island",24,78),land(island(35,68,2,3),"Hunter Association","Zevil Island",35,68)]
        for row in [("Padokea","Republic of Padokea",21,40),("Zoldyck estate","Zoldyck Family",29,28),("Yorknew district","Yorknew civic authorities",50,41),("Meteor City","Meteor City elders",45,50),("Hunter Association HQ","Hunter Association",57,27),("NGL","NGL Autonomous Region",46,73),("East Gorteau","East Gorteau",64,73)]: seed(*row)
        positions={"Yorknew City":(50,41),"Kukuroo Mountain":(29,28),"Whale Island":(24,78),"Hunter Exam Site":(50,33),"Heavens Arena":(24,48),"Meteor City":(45,50),"Greed Island":(79,66),"NGL":(46,73),"East Gorteau":(64,73),"Hunter Association HQ":(57,27),"Kakin Empire":(80,32),"Republic of Padokea":(20,35),"Yorbian Continent":(53,46),"Mitene Union":(54,69),"Dark Continent Expedition Route":(88,8),"Zevil Island":(35,68)}
        labels=[("KNOWN WORLD · LAKE MOBIUS",51,92)]
    elif world == "Overgeared":
        west=[[3,8],[17,5],[28,9],[35,5],[46,8],[58,6],[65,17],[63,29],[68,38],[64,49],[68,59],[60,71],[55,88],[45,91],[34,86],[23,90],[18,78],[7,76],[4,64],[8,52],[3,41],[6,29]]
        lands=[land(west,"Eternal Kingdom","West continent",35,53),land(island(85,45,11,32),"Hwan Kingdom","East continent",85,45),land(island(75,84,6,5),"Behen island domains","Behen Archipelago",75,84)]
        for row in [("Saharan Empire","Saharan Empire",40,23),("Eternal Kingdom","Eternal Kingdom",33,63),("Valhalla","Valhalla",57,52),("Talima","Talima",15,24),("Vatican","Rebecca Church",55,39)]: seed(*row)
        positions={"Winston":(39,63),"Patrian":(30,71),"Reidan":(18,59),"Bairan":(37,56),"Titan":(42,26),"Saharan Empire":(37,18),"Frontier":(48,77),"Northern Frontier":(30,13),"Kesan Canyon":(21,65),"Temple of Yatan":(26,76),"Reinhardt":(38,72),"Pangea":(83,48),"Talima":(15,24),"Vatican":(55,39),"Valhalla":(57,52),"Behen Archipelago":(75,84)}
        labels=[("WEST CONTINENT",32,96),("EAST CONTINENT",83,92)]
    elif world == "Reincarnated as a Slime":
        lands=[land(CONTINENT,"Jura Forest communities","Central World",50,48),land(island(13,91,6,4),"El Dorado","El Dorado",13,91)]
        for row in [("Great Jura Forest","Jura Forest communities",53,47),("Dwargon","Armed Nation of Dwargon",54,21),("Falmuth","Kingdom of Falmuth",39,32),("Blumund","Kingdom of Blumund",34,52),("Ingrassia","Kingdom of Ingrassia",21,44),("Lubelius","Holy Empire of Lubelius",18,24),("Thalion","Sorcerous Dynasty of Thalion",25,72),("Eurazania","Beast Kingdom Eurazania",64,69),("Jistav","Jistav",75,51),("Milim's Domain","Milim's Domain",76,79),("Eastern Empire","Eastern Empire",85,26),("Tempest","Jura Tempest Federation",51,51)]: seed(*row)
        positions={"Kingdom of Falmuth":(39,32),"Blumund":(34,52),"Dwargon":(54,21),"Sorcerous Dynasty of Thalion":(25,72),"Jistav":(75,51),"Holy Empire of Lubelius":(18,24),"Ingrassia":(21,44),"Eurazania":(64,69),"Milim's Domain":(76,79),"Tempest":(51,51),"El Dorado":(13,91)}
    elif world == "Jujutsu Kaisen":
        lands=[land(poly,"Japan",name,x,y,"green") for poly,name,x,y in zip(JAPAN,["Hokkaido","Honshu","Shikoku","Kyushu"],[85,60,37,23],[15,54,75,80])]
        # Colonies are barriers, not sovereign nations. Never seed them as owners.
        labels=[("SEA OF JAPAN",44,34),("PACIFIC OCEAN",79,81)]
    elif world == "Bleach":
        # Regional realm diagrams have no invented ocean coastline. They
        # remain full land boards with the same claim coordinates.
        realm_extent = [[1,1],[99,1],[99,99],[1,99]]
        if board == "World of the Living":
            lands=[land(realm_extent,"Japan","Karakura / Naruki district",50,50)]
            structures=[{'kind':'river','points':[[68,0],[64,23],[70,42],[66,65],[75,100]],'name':'Local river corridor'}]
        elif board == "Hueco Mundo":
            lands=[land(realm_extent,"Hollow dominions","Hueco Mundo",45,56,"sand")]
            seed("Las Noches","Las Noches court",72,25)
            structures=[{'kind':'enclosure','x':72,'y':25,'rx':12,'ry':10,'name':'Las Noches'}]
        elif board == "Royal Realm":
            lands=[land(island(50,44,17,19),"Royal Guard","Soul King Palace",50,44,"stone"),land(island(28,28,10,11),"Royal Guard","Royal Guard Domains",28,28,"stone")]
        elif board == "Hell":
            lands=[land(realm_extent,"Hell wardens","Hell",50,50,"stone")]
        else:
            lands=[land(realm_extent,"Soul Society","Soul Society",50,50)]
            labels=[("NORTH RUKONGAI",50,18),("WEST RUKONGAI",21,49),("EAST RUKONGAI",79,49),("SOUTH RUKONGAI",50,80),("SEIREITEI",50,39)]
            structures=[{'kind':'enclosure','x':50,'y':40,'rx':18,'ry':22,'name':'Seireitei walls'}]
    elif world == "Solo Max-Level Newbie":
        lands=[land(CONTINENT,"Tower administration" if board != "Earth" else "Local civil authorities",board or "Earth",50,50,"stone")]
    else:
        lands=[land(CONTINENT,"Local Faction","Starting Region",50,55)]
        for row in [("Northern Reach","Northern communities",50,20),("Western March","Western communities",20,50),("Eastern Reach","Eastern communities",80,50),("Southern Wilds","Southern communities",50,82)]: seed(*row)
    relief = {
        "Naruto": [[[8,17],[15,23],[21,31],[28,33]],[[42,8],[46,14],[54,17]],[[65,10],[71,18],[75,28]]],
        "Overgeared": [[[12,39],[13,49],[15,57],[14,68]],[[30,13],[40,17],[49,15]],[[80,20],[85,32],[88,49],[84,66]]],
        "Reincarnated as a Slime": [[[38,20],[47,23],[54,24],[63,21],[68,25]],[[7,15],[15,25],[21,32]]],
        "Jujutsu Kaisen": [[[75,30],[73,41],[67,52],[56,61]],[[80,10],[85,15],[88,20]]],
        "Hunter x Hunter": [[[13,20],[23,24],[28,30],[25,36]],[[72,25],[77,34],[86,41]]],
    }.get(world,[])
    # Fine coastline detail is deterministic and moves no landmark. This is
    # cartographic stylization, not additional claimed canonical geography.
    for index,l in enumerate(lands):
        detailed=[]
        polygon=l['polygon']
        for i,a in enumerate(polygon):
            b=polygon[(i+1)%len(polygon)];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy) or 1
            for part in range(4):
                t=part/4
                noise=((i*17+part*13+index*7)%11-5)*.045 if part else 0
                detailed.append([max(0,min(100,round(a[0]+dx*t-dy/length*noise,3))),max(0,min(100,round(a[1]+dy*t+dx/length*noise,3)))])
        l['polygon']=detailed
    return {"id":world+":"+board, "version":2, "land":lands,"seeds":seeds,"positions":positions,"labels":labels,"relief":relief,"structures":structures}


def inside(x,y,poly):
    result=False
    j=len(poly)-1
    for i,(px,py) in enumerate(poly):
        qx,qy=poly[j]
        if (py>y)!=(qy>y) and x < (qx-px)*(y-py)/(qy-py)+px: result=not result
        j=i
    return result


def cell_vertices(x,y):
    r=STEP/math.sqrt(3)
    return [[round(x+r*math.cos(math.radians(30+60*i)),4),round(y+r*math.sin(math.radians(30+60*i)),4)] for i in range(6)]


@lru_cache(maxsize=80)
def base_atlas(world,board=""):
    atlas=preset(world,board)
    cells=[]
    for row in range(int(100/DY)+2):
        y=row*DY
        for col in range(int(100/STEP)+2):
            x=(col+.5*(row%2))*STEP
            vertices=cell_vertices(x,y)
            # Boundary cells extend under the coastline clip: no unshaded slivers.
            idx=next((i for i,l in enumerate(atlas["land"]) if inside(x,y,l["polygon"]) or any(inside(px,py,l["polygon"]) for px,py in vertices) or any(abs(px-x)<STEP/2 and abs(py-y)<DY/2 for px,py in l["polygon"])),None)
            if idx is None: continue
            l=atlas["land"][idx]
            seeds=[s for s in atlas["seeds"] if inside(s["x"],s["y"],l["polygon"])]
            if seeds and not any(s['owner']==l['owner'] for s in seeds): seeds.append(l)
            owner=min(seeds,key=lambda s:(s["x"]-x)**2+(s["y"]-y)**2) if seeds else l
            if idx == 0:
                authored = next((name for name, polygon in reversed(AUTHORED_DISTRICTS.get(world, [])) if inside(x,y,polygon)), None)
                if authored:
                    owner = next((s for s in atlas['seeds'] if s['name']==authored), l)
            cells.append({"id":f"{col}:{row}","x":round(x,4),"y":round(y,4),"land":idx,"district":owner["name"],"owner":owner.get("owner",l["owner"])})
    atlas["cells"]=cells
    return atlas


def _number(value,default=0):
    try: return float(value)
    except (TypeError,ValueError): return default


def _key(s): return str(s or "").strip().casefold()


def political_atlas(state,nodes,world,board=""):
    """Read-only overlay: era preset -> explicit location control -> authored claims.

    Village command is local; only explicit national claims transfer a country.
    Unanchored claims are never placed at the player.
    """
    atlas=copy.deepcopy(base_atlas(world,board))
    node_context = contextualize(atlas,state,world,board)
    cells=atlas["cells"]
    lookup={c["id"]:c for c in cells}
    node_by_name={_key(n["name"]):n for n in nodes}
    notes=[]
    for n in nodes:
        if n["name"] in atlas["positions"]: n["x"],n["y"]=atlas["positions"][n["name"]]
    details=state.get("location_details")
    details=details if isinstance(details,dict) else {}
    owners={}
    for name,d in details.items():
        if not isinstance(d,dict) or "controlling_faction" not in d: continue
        if not isinstance(d["controlling_faction"],str): continue
        owner=d["controlling_faction"].strip() or "Unclaimed"
        n=node_by_name.get(_key(name))
        district=next((s["name"] for s in atlas["seeds"] if _key(s["name"])==_key(name)),None)
        # Island countries need not have seeds. Match the authored land name.
        if not district:
            district=next((l['name'] for l in atlas['land'] if _key(l['name'])==_key(name)),None)
        local_only = world == 'Naruto' and name in VILLAGE_COUNTRIES
        if not district and n:
            nearest=min(cells,key=lambda c:(c["x"]-_number(n["x"]))**2+(c["y"]-_number(n["y"]))**2)
            district=nearest["district"]
            # A city or island anchor can transfer its preset district. Minor
            # facilities do not annex an entire sovereign nation accidentally.
            if local_only or n.get("kind") not in {"nation","kingdom","region","island","empire","floor"}:
                for c in cells:
                    if c["land"]==nearest["land"] and (c["x"]-n["x"])**2+(c["y"]-n["y"])**2<=4: owners[c["id"]]=owner
                continue
        if district:
            for c in cells:
                if c["district"]==district:
                    owners[c["id"]]=owner
                    c['sovereignty']=owner
    for c in cells: c["owner"]=owners.get(c["id"],c["owner"])
    raw_claims=state.get("political_regions",[])
    for claim in raw_claims if isinstance(raw_claims,list) else []:
        if not isinstance(claim,dict) or not isinstance(claim.get("controller"),str): continue
        if str(claim.get('status','active')).lower() in {'lost','inactive','removed','abandoned','dissolved','retired'}: continue
        scope=claim.get("board") or claim.get("realm")
        if scope and _key(scope) not in {_key(board),_key(atlas["id"])}: continue
        if claim.get("world") and claim["world"]!=world: continue
        anchor=node_by_name.get(_key(claim.get("anchor") or claim.get("name")))
        # Realm-less coordinates are unsafe in a multi-board world.
        if world in {"Bleach","Solo Max-Level Newbie"} and not scope and not anchor: continue
        if not anchor and (claim.get("x") is None or claim.get("y") is None):
            notes.append(f"{claim.get('name','Claim')}: needs a map anchor")
            continue
        x=_number(claim.get("x"),_number((anchor or {}).get("x"),50))
        y=_number(claim.get("y"),_number((anchor or {}).get("y"),50))
        first=min(cells,key=lambda c:(c["x"]-x)**2+(c["y"]-y)**2)
        polygon=claim.get("polygon")
        polygon=[p for p in polygon if isinstance(p,(list,tuple)) and len(p)>=2 and all(isinstance(v,(int,float)) for v in p[:2])] if isinstance(polygon,list) else []
        count=max(0,min(900,int(_number(claim.get("hex_count")))))
        if claim.get("player_founded"): count=max(1,count)
        selected=[]
        if len(polygon)>=3: selected=[c for c in cells if inside(c["x"],c["y"],polygon)]
        elif count:
            # Contiguous growth, no jumping a sea channel to acquire spare tiles.
            queue=deque([first]); seen={first["id"]}
            while queue and len(selected)<count:
                c=queue.popleft(); selected.append(c)
                col,row=map(int,c["id"].split(":")); shift=1 if row%2 else -1
                adjacent=[(col-1,row),(col+1,row),(col,row-1),(col+shift,row-1),(col,row+1),(col+shift,row+1)]
                neighbors=[lookup.get(f"{a}:{b}") for a,b in adjacent]
                for n in sorted((n for n in neighbors if n and n["land"]==first["land"]),key=lambda n:(n["x"]-x)**2+(n["y"]-y)**2):
                    if n["id"] not in seen: seen.add(n["id"]); queue.append(n)
        elif claim.get("scale") in {"country","nation","realm","continent","island"}:
            selected=[c for c in cells if c["district"]==first["district"]]
        else:
            radius=max(1,min(20,_number(claim.get("size"),4)))
            selected=[c for c in cells if c["land"]==first["land"] and (c["x"]-x)**2+(c["y"]-y)**2<=radius**2]
        for c in selected:
            c["owner"]=claim["controller"]
            if claim.get('scale') in {'country','nation','realm','continent','island'}:
                c['sovereignty']=claim['controller']
            c["claim"]=str(claim.get("name") or claim["controller"])
    for n in nodes:
        c=min(cells,key=lambda c:(c["x"]-n["x"])**2+(c["y"]-n["y"])**2)
        n["controller"]=c["owner"]
        n['sovereignty']=c['sovereignty']
        context = node_context.get(n['name'], {})
        n.update({k:v for k,v in context.items() if k not in {'sovereignty','era_unavailable'}})
        if context.get('era_unavailable') and not explicitly_established(state,n['name']):
            n['era_unavailable']=True
        if world == 'Naruto' and n['name'] in VILLAGE_COUNTRIES:
            n['local_authority'] = details.get(n['name'],{}).get('controlling_faction', n.get('local_authority')) if isinstance(details.get(n['name'],{}),dict) else n.get('local_authority')
            if c.get('claim'): n['local_authority']=c['owner']
        if world == 'Overgeared' and n['name']=='Valhalla' and (c.get('claim') or explicitly_established(state,'Valhalla')):
            n.pop('display_name',None)
            n['local_authority']=n['controller']
        n["atlas_district"]=c.get("claim",c["district"])
        n["offshore"]=not any(inside(n["x"],n["y"],l["polygon"]) for l in atlas["land"])
        if n.get('kind') in {'sky','dimension','otherworld','mobile kingdom','sea','hidden realm'}: n['offshore']=True
        if n["offshore"]: n["controller"]=details.get(n["name"],{}).get("controlling_faction","Not a surface territory") if isinstance(details.get(n["name"],{}),dict) else "Not a surface territory"
        if world=='One Piece' and n['name']=='Fishman Island':
            n.update(controller='Ryugu Kingdom',offshore=True,sovereignty='Ryugu Kingdom')
            if isinstance(details.get(n['name']),dict) and 'controlling_faction' in details[n['name']]:
                n['controller']=details[n['name']]['controlling_faction'] or 'Unclaimed'
        # Political metadata written in the campaign supersedes historical
        # defaults too. Do not leave a defeated occupier in the details panel.
        detail = details.get(n['name'],{})
        if isinstance(detail,dict):
            for key in ('sovereignty','local_authority','protection'):
                if key in detail and isinstance(detail[key],str): n[key]=detail[key]
            if 'controlling_faction' in detail and 'local_authority' not in detail:
                n['local_authority']=n['controller']
        if c.get('claim'): n['local_authority']=c['owner']
    atlas["warnings"]=notes
    nodes[:] = [n for n in nodes if not n.get('era_unavailable')]
    atlas["revision"]=hashlib.sha256(repr([(c["id"],c["owner"],c.get("claim")) for c in cells]).encode()).hexdigest()[:16]
    # No AI prompt pays for the tile grid; map_snapshot alone receives this.
    atlas.pop("positions",None)
    return atlas
