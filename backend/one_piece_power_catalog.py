"""Curated, battle-relevant One Piece canon powers.

Catalog presence describes a power; it never grants ownership. Save state and
timeline remain authoritative about who can actually select an application.
"""
from __future__ import annotations
import re

def _fruit(name, kind, owner, rule, moves=(), forms=(), first_arc="Unknown"):
    return {"name":name,"type":kind,"canon_owner":owner,"governing_rule":rule,
            "techniques":list(moves),"forms":list(forms),"first_arc":first_arc,
            "weaknesses":["Standing water drains strength and prevents useful movement","Sea-Prism Stone suppresses the ability"]}

DEVIL_FRUITS = {
 "gum-gum":_fruit("Human-Human Fruit, Model: Nika","Mythical Zoan","Monkey D. Luffy","A rubber-bodied warrior whose awakening grants freer rubber transformation to body and surroundings.",
  ("Gum-Gum Pistol","Gum-Gum Gatling","Gum-Gum Bazooka","Gum-Gum Red Hawk","Gum-Gum Elephant Gatling","King Kong Gun","Gum-Gum Bajrang Gun"),("Gear Second","Gear Third","Gear Fourth: Boundman","Gear Fourth: Snakeman","Gear Fifth"),"Romance Dawn"),
 "chop-chop":_fruit("Chop-Chop Fruit","Paramecia","Buggy","Splits the body into independently controlled pieces while making ordinary cutting attacks ineffective.",( "Chop-Chop Cannon","Chop-Chop Car"),first_arc="Orange Town"),
 "slip-slip":_fruit("Slip-Slip Fruit","Paramecia","Alvida","Makes the body frictionless so ordinary attacks and objects slide away.",first_arc="Loguetown"),
 "smoke-smoke":_fruit("Smoke-Smoke Fruit","Logia","Smoker","Creates, controls and becomes smoke.",( "White Blow","White Snake","White Launcher"),first_arc="Loguetown"),
 "bomb-bomb":_fruit("Bomb-Bomb Fruit","Paramecia","Gem","Makes any part or emission of the body explosively detonatable.",( "Nose Fancy Cannon","Full-Body Explosion"),first_arc="Whiskey Peak"),
 "kilo-kilo":_fruit("Kilo-Kilo Fruit","Paramecia","Mikita","Changes body weight from nearly weightless to ten thousand kilograms.",( "Ten-Thousand Kilo Press",),first_arc="Whiskey Peak"),
 "wax-wax":_fruit("Wax-Wax Fruit","Paramecia","Galdino","Creates and shapes candle wax that hardens like steel.",( "Candle Wall","Candle Champion","Candle Lock"),first_arc="Little Garden"),
 "munch-munch":_fruit("Munch-Munch Fruit","Paramecia","Wapol","Consumes and combines matter, weapons and bodies into new configurations.",( "Munch-Munch Factory",),first_arc="Drum Island"),
 "flower-flower":_fruit("Flower-Flower Fruit","Paramecia","Nico Robin","Blooms replicas of body parts on surfaces within perception.",( "Clutch","Gigantesco Mano","Demonio Fleur"),forms=("Demonio Fleur",),first_arc="Whiskey Peak"),
 "sand-sand":_fruit("Sand-Sand Fruit","Logia","Crocodile","Creates, controls and becomes sand while draining moisture by contact.",( "Desert Spada","Sables","Ground Secco","Desert Grande Espada"),first_arc="Alabasta"),
 "clone-clone":_fruit("Clone-Clone Fruit","Paramecia","Bentham","Copies the physical appearance of a person whose face has been touched.",first_arc="Alabasta"),
 "flame-flame":_fruit("Flame-Flame Fruit","Logia","Portgas D. Ace / Sabo","Creates, controls and becomes fire.",( "Fire Fist","Fire Gun","Flame Emperor","Flame Dragon King"),first_arc="Alabasta"),
 "spring-spring":_fruit("Spring-Spring Fruit","Paramecia","Bellamy","Turns limbs into springs for stored-force movement and impacts.",( "Spring Hopper","Spring Death Knock"),first_arc="Jaya"),
 "rumble-rumble":_fruit("Rumble-Rumble Fruit","Logia","Enel","Creates, controls and becomes lightning, with electromagnetic and conductive applications.",( "El Thor","Kari","Thunderbird","Raigo"),first_arc="Skypiea"),
 "slow-slow":_fruit("Slow-Slow Fruit","Paramecia","Foxy","Emits photons that slow affected targets for thirty seconds.",( "Slow-Slow Beam",),first_arc="Long Ring Long Land"),
 "ice-ice":_fruit("Ice-Ice Fruit","Logia","Kuzan","Creates, controls and becomes ice, freezing targets and large bodies of water.",( "Ice Age","Ice Time","Ice Block: Pheasant Beak","Ice Ball"),first_arc="Long Ring Long Land"),
 "dark-dark":_fruit("Dark-Dark Fruit","Logia","Marshall D. Teach","Controls darkness and gravity-like attraction while nullifying Devil Fruit powers through touch.",( "Black Hole","Liberation","Dark Vortex"),first_arc="Jaya"),
 "paw-paw":_fruit("Paw-Paw Fruit","Paramecia","Bartholomew Kuma","Repels anything touched by the paw pads, including air, pain and people.",( "Pad Cannon","Ursus Shock","Pain Extraction"),first_arc="Thriller Bark"),
 "shadow-shadow":_fruit("Shadow-Shadow Fruit","Paramecia","Gecko Moria","Removes, manipulates and implants shadows to animate corpses or empower bodies.",( "Shadow Revolution","Brick Bat","Doppelman"),forms=("Shadows Asgard",),first_arc="Thriller Bark"),
 "hollow-hollow":_fruit("Hollow-Hollow Fruit","Paramecia","Perona","Creates ghosts that pass through targets to crush morale or explode.",( "Negative Hollow","Mini Hollow","Special Hollow"),first_arc="Thriller Bark"),
 "clear-clear":_fruit("Clear-Clear Fruit","Paramecia","Absalom / Shiryu","Makes the user and touched objects invisible.",first_arc="Thriller Bark"),
 "glint-glint":_fruit("Glint-Glint Fruit","Logia","Borsalino","Creates, controls and becomes light for lasers, flashes and linear movement.",( "Yasakani Sacred Jewel","Ama no Murakumo","Yata Mirror","Laser Beam"),first_arc="Sabaody"),
 "op-op":_fruit("Op-Op Fruit","Paramecia","Trafalgar Law","Within a created ROOM, spatially operates on targets and objects according to surgical rules.",( "Room: Shambles","Room: Takt","Gamma Knife","Counter Shock","Injection Shot","Shock Wille","Puncture Wille"),first_arc="Sabaody"),
 "magnet-magnet":_fruit("Magnet-Magnet Fruit","Paramecia","Eustass Kid","Controls magnetic forces and assigns polarity to gather or repel metal.",( "Punk Gibson","Punk Rotten","Assign","Damned Punk"),forms=("Punk Rotten",),first_arc="Sabaody"),
 "castle-castle":_fruit("Castle-Castle Fruit","Paramecia","Capone Bege","Turns the body into a fortress that houses and deploys people and weapons.",( "Big Father",),forms=("Big Father",),first_arc="Sabaody"),
 "straw-straw":_fruit("Straw-Straw Fruit","Paramecia","Basil Hawkins","Creates straw constructs and transfers damage through prepared straw dolls.",( "Straw Man's Card","Goma no So"),forms=("Straw Man",),first_arc="Sabaody"),
 "quake-quake":_fruit("Quake-Quake Fruit","Paramecia","Edward Newgate / Marshall D. Teach","Generates vibrations and quakes through air, sea and matter.",( "Seaquake","Island Shaking","Quake Bubble"),first_arc="Marineford"),
 "love-love":_fruit("Love-Love Fruit","Paramecia","Boa Hancock","Petrifies targets whose attraction or emotional response leaves them susceptible, with contact attacks also petrifying struck matter.",( "Love-Love Mellow","Slave Arrow","Perfume Femur"),first_arc="Amazon Lily"),
 "poison-poison":_fruit("Venom-Venom Fruit","Paramecia","Magellan","Creates and controls multiple poisons but does not become intangible poison.",( "Poison Hydra","Venom Road","Venom Demon"),forms=("Venom Demon",),first_arc="Impel Down"),
 "horm-horm":_fruit("Horm-Horm Fruit","Paramecia","Emporio Ivankov","Injects hormones that alter physiology, recovery, sex characteristics and performance.",( "Healing Hormone","Energy Hormone","Face Growth Hormone"),first_arc="Impel Down"),
 "magma-magma":_fruit("Magma-Magma Fruit","Logia","Sakazuki","Creates, controls and becomes magma.",( "Great Eruption","Meteor Volcano","Hell Hound"),first_arc="Marineford"),
 "mark-mark":_fruit("Mark-Mark Fruit","Paramecia","Vander Decken IX","Makes thrown objects pursue targets whose bodies were touched by designated hands.",first_arc="Fish-Man Island"),
 "gas-gas":_fruit("Gas-Gas Fruit","Logia","Caesar Clown","Creates, controls and becomes gas, including removal of breathable oxygen and altered gas mixtures.",( "Gastanet","Blue Sword","Shinokuni"),first_arc="Punk Hazard"),
 "snow-snow":_fruit("Snow-Snow Fruit","Logia","Monet","Creates, controls and becomes snow.",( "Snow Rabbit","Snow Fence","Kamakkura"),first_arc="Punk Hazard"),
 "string-string":_fruit("String-String Fruit","Paramecia","Donquixote Doflamingo","Creates and controls extraordinarily strong strings for cutting, puppetry, movement and constructs.",( "Parasite String","Overheat","Black Knight","Birdcage String Bind","God Thread"),first_arc="Jaya"),
 "barrier-barrier":_fruit("Barrier-Barrier Fruit","Paramecia","Bartolomeo","Creates nearly unbreakable barriers through a finger-crossing gesture.",( "Bartolomeo Barrier","Barrier Crash","Barrier Stairs"),first_arc="Dressrosa"),
 "gravity-gravity":_fruit("Press-Press Fruit","Paramecia","Issho","Controls gravitational force around selected targets and areas.",( "Gravity Blade","Raging Tiger","Meteor Drop"),first_arc="Dressrosa"),
 "hobby-hobby":_fruit("Hobby-Hobby Fruit","Paramecia","Sugar","Stops the user's aging and turns touched people into contract-bound toys erased from others' memories.",first_arc="Dressrosa"),
 "ton-ton":_fruit("Ton-Ton Fruit","Paramecia","Machvise","Changes body weight by tons for crushing impacts.",( "Ten-Thousand Ton Vise",),first_arc="Dressrosa"),
 "stone-stone":_fruit("Stone-Stone Fruit","Paramecia","Pica","Assimilates with and controls stone structures.",( "Stone Giant","Charlestone"),forms=("Stone Giant",),first_arc="Dressrosa"),
 "soul-soul":_fruit("Soul-Soul Fruit","Paramecia","Charlotte Linlin","Manipulates lifespan and installs soul fragments into objects or phenomena to create Homies.",( "Soul Pocus","Prometheus Heavenly Fire","Fulgora","Maser Cannon"),forms=("Bigger Mom",),first_arc="Whole Cake Island"),
 "mochi-mochi":_fruit("Mochi-Mochi Fruit","Special Paramecia","Charlotte Katakuri","Creates, controls and becomes mochi; awakening converts surroundings into mochi.",( "Power Mochi","Peerless Donuts","Mochi Thrust","Buzz Cut Mochi"),first_arc="Whole Cake Island"),
 "mirror-mirror":_fruit("Mirror-Mirror Fruit","Paramecia","Charlotte Brulee","Creates reflections and accesses the Mirror World through mirrors.",( "Mirror Reflection","Mirror World Passage"),first_arc="Whole Cake Island"),
 "biscuit-biscuit":_fruit("Biscuit-Biscuit Fruit","Paramecia","Charlotte Cracker","Creates and controls biscuits, including armored biscuit soldiers.",( "Biscuit Soldier","Pretzel Roll"),forms=("Biscuit Armor",),first_arc="Whole Cake Island"),
 "dragon-dragon-azure":_fruit("Fish-Fish Fruit, Model: Azure Dragon","Mythical Zoan","Kaido","Transforms into an azure dragon or hybrid with flight, weather influence and elemental breath.",( "Blast Breath","Thunder Bagua","Flaming Drum Dragon"),forms=("Azure Dragon Form","Hybrid Form","Flaming Drum Dragon"),first_arc="Wano"),
 "phoenix":_fruit("Bird-Bird Fruit, Model: Phoenix","Mythical Zoan","Marco","Transforms into a phoenix whose blue flames rapidly regenerate living tissue.",( "Phoenix Brand","Blue Flame Restoration"),forms=("Phoenix Form","Hybrid Form"),first_arc="Marineford"),
 "dinosaur-allosaurus":_fruit("Dragon-Dragon Fruit, Model: Allosaurus","Ancient Zoan","X Drake","Transforms into an Allosaurus or hybrid with enhanced power and durability.",forms=("Allosaurus Form","Hybrid Form"),first_arc="Sabaody"),
 "dinosaur-brachiosaurus":_fruit("Dragon-Dragon Fruit, Model: Brachiosaurus","Ancient Zoan","Queen","Transforms into a Brachiosaurus or hybrid with immense mass, durability and cyborg integrations.",( "Brachiosnakeus",),forms=("Brachiosaurus Form","Hybrid Form"),first_arc="Wano"),
 "spider-rosamygale":_fruit("Spider-Spider Fruit, Model: Rosamygale Grauvogeli","Ancient Zoan","Black Maria","Transforms into an ancient spider hybrid that produces webs and traps.",forms=("Spider Hybrid Form",),first_arc="Wano"),
 "dog-yamato":_fruit("Dog-Dog Fruit, Model: Okuchi-no-Makami","Mythical Zoan","Yamato","Transforms into a guardian wolf deity with ice-based breath and defenses.",( "Namuji Glacier Fang","Mirror Mountain"),forms=("Guardian Wolf Form","Hybrid Form"),first_arc="Wano"),
 "age-age":_fruit("Age-Age Fruit","Paramecia","Jewelry Bonney","Manipulates apparent age and accesses possible future bodily states.",( "Distorted Future",),forms=("Distorted Future",),first_arc="Sabaody"),
 "brain-brain":_fruit("Brain-Brain Fruit","Paramecia","Vegapunk","Provides unlimited storage of acquired knowledge while physically expanding the brain.",first_arc="Egghead"),
 "warp-warp":_fruit("Warp-Warp Fruit","Paramecia","Van Augur","Teleports the user and selected people between visible or known positions.",( "Warp",),first_arc="Egghead"),
 "strong-strong":_fruit("Strong-Strong Fruit","Paramecia","Jesus Burgess","Grants extreme physical strength.",( "Galleon Lariat",),first_arc="Egghead"),
}

# Additional confirmed canon fruits with battle-relevant applications. Keeping
# these local prevents the GM from having to reconstruct their rules or names.
DEVIL_FRUITS.update({
 "dice-dice":_fruit("Dice-Dice Fruit","Paramecia","Daz Bonez","Turns the body into steel blades.",( "Spiral Hollow","Atomic Spurt"),first_arc="Alabasta"),
 "spike-spike":_fruit("Spike-Spike Fruit","Paramecia","Zala","Creates sharp spikes from any part of the body.",( "Double Stinger","Stinger Hedgehog"),first_arc="Alabasta"),
 "jackal":_fruit("Dog-Dog Fruit, Model: Jackal","Zoan","Chaka","Transforms into a jackal or jackal hybrid.",forms=("Jackal Form","Hybrid Form"),first_arc="Alabasta"),
 "falcon":_fruit("Bird-Bird Fruit, Model: Falcon","Zoan","Pell","Transforms into a falcon or winged hybrid and grants flight.",forms=("Falcon Form","Hybrid Form"),first_arc="Alabasta"),
 "mole":_fruit("Mole-Mole Fruit","Zoan","Drophy","Transforms into a mole or mole hybrid and tunnels through earth.",forms=("Mole Form","Hybrid Form"),first_arc="Alabasta"),
 "dachshund":_fruit("Dog-Dog Fruit, Model: Dachshund","Zoan","Lassoo","Transforms the host gun into a dachshund hybrid that fires explosive baseballs.",( "Cannon Ball Pitch",),forms=("Dachshund Gun Form",),first_arc="Alabasta"),
 "horse-horse":_fruit("Horse-Horse Fruit","Zoan","Pierre","Transforms the user into a horse; a bird user becomes a winged horse hybrid.",forms=("Horse Form","Hybrid Form"),first_arc="Skypiea"),
 "door-door":_fruit("Door-Door Fruit","Paramecia","Blueno","Creates doors through matter, bodies and the atmosphere.",( "Air Door","Revolving Door"),first_arc="Water 7"),
 "cat-leopard":_fruit("Cat-Cat Fruit, Model: Leopard","Zoan","Rob Lucci","Transforms into a leopard or powerful hybrid.",( "Leopard Shigan","Rokuogan"),forms=("Leopard Form","Hybrid Form","Life Return Hybrid"),first_arc="Water 7"),
 "ox-giraffe":_fruit("Ox-Ox Fruit, Model: Giraffe","Zoan","Kaku","Transforms into a giraffe or highly flexible hybrid.",( "Pasta Machine","Giraffe Cannon"),forms=("Giraffe Form","Hybrid Form"),first_arc="Enies Lobby"),
 "dog-wolf":_fruit("Dog-Dog Fruit, Model: Wolf","Zoan","Jabra","Transforms into a wolf or wolf hybrid.",( "Wolf Fang Shigan",),forms=("Wolf Form","Hybrid Form"),first_arc="Enies Lobby"),
 "bubble-bubble":_fruit("Bubble-Bubble Fruit","Paramecia","Kalifa","Creates soap bubbles that clean away strength and make surfaces slippery.",( "Golden Hour","Bubble Master"),first_arc="Enies Lobby"),
 "rust-rust":_fruit("Rust-Rust Fruit","Paramecia","Shu","Corrodes metal through contact.",( "Rust Touch",),first_arc="Enies Lobby"),
 "berry-berry":_fruit("Berry-Berry Fruit","Paramecia","Very Good","Splits the body into floating berry-shaped spheres that resist blunt force.",( "Berry Volley",),first_arc="Enies Lobby"),
 "wheel-wheel":_fruit("Wheel-Wheel Fruit","Paramecia","Sharinguru","Turns limbs into rapidly spinning wheels.",( "Wheel Drive",),first_arc="Enies Lobby"),
 "jacket-jacket":_fruit("Jacket-Jacket Fruit","Paramecia","Kelly Funk","Turns the user into a wearable jacket that controls a consenting or captured wearer.",( "Jacket Fusion",),forms=("Jacket Fusion",),first_arc="Dressrosa"),
 "swim-swim":_fruit("Swim-Swim Fruit","Paramecia","Senor Pink","Allows swimming through solid ground and walls as if they were liquid.",( "Nyan Nyan Suplex","Baby Buster"),first_arc="Dressrosa"),
 "arms-arms":_fruit("Arms-Arms Fruit","Paramecia","Baby 5","Transforms body parts or the whole body into weapons.",( "Missile Girl","Revolver Leg"),forms=("Weapon Transformation",),first_arc="Dressrosa"),
 "art-art":_fruit("Art-Art Fruit","Paramecia","Giolla","Transforms people and objects into distorted artwork that loses normal function.",( "Heaven's Door Art","Dying Art"),first_arc="Dressrosa"),
 "glare-glare":_fruit("Glare-Glare Fruit","Paramecia","Viola","Sees through matter, reads minds and projects memories across great distances.",( "Mind Reading","Insight Whale"),first_arc="Dressrosa"),
 "heal-heal":_fruit("Heal-Heal Fruit","Paramecia","Mansherry","Heals living beings through tears or restorative energy at a real cost.",( "Healing Tears","Recovery Dandelion"),first_arc="Dressrosa"),
 "stitch-stitch":_fruit("Stitch-Stitch Fruit","Paramecia","Leo","Stitches targets and objects together without necessarily harming them.",( "Stitch Bond",),first_arc="Dressrosa"),
 "pop-pop":_fruit("Pop-Pop Fruit","Paramecia","Gladius","Inflates and ruptures the user or inorganic objects.",( "Fashion Punk","Punc Hair"),first_arc="Dressrosa"),
 "flag-flag":_fruit("Ripple-Ripple Fruit","Paramecia","Diamante","Makes solid objects ripple like cloth while retaining their material properties.",( "Army Bandera","Death Enjambre"),first_arc="Dressrosa"),
 "lick-lick":_fruit("Lick-Lick Fruit","Paramecia","Charlotte Perospero","Creates and controls candy for weapons, restraints and structures.",( "Candy Wall","Candy Maiden","Candy Slug"),first_arc="Whole Cake Island"),
 "book-book":_fruit("Book-Book Fruit","Paramecia","Charlotte Mont-d'Or","Manipulates books and can imprison living targets within book worlds.",( "Book Prison","World of Books"),first_arc="Whole Cake Island"),
 "memo-memo":_fruit("Memo-Memo Fruit","Paramecia","Charlotte Pudding","Extracts, edits and replaces memories as film strips.",( "Memory Edit","Memory Extraction"),first_arc="Whole Cake Island"),
 "heat-heat":_fruit("Heat-Heat Fruit","Paramecia","Charlotte Oven","Heats the user's body and surrounding materials to extreme temperatures.",( "Heat Punch","Ocean Boil"),first_arc="Whole Cake Island"),
 "puff-puff":_fruit("Puff-Puff Fruit","Paramecia","Charlotte Daifuku","Summons a powerful genie by rubbing the body.",( "Genie Halberd",),forms=("Genie Manifestation",),first_arc="Whole Cake Island"),
 "cook-cook":_fruit("Cook-Cook Fruit","Paramecia","Streusen","Transforms objects into edible food, though taste may suffer.",( "Food Transformation",),first_arc="Whole Cake Island"),
 "cream-cream":_fruit("Cream-Cream Fruit","Paramecia","Charlotte Opera","Creates and controls cream that can generate heat through friction.",( "Cream Monster",),first_arc="Whole Cake Island"),
 "butter-butter":_fruit("Butter-Butter Fruit","Paramecia","Charlotte Galette","Creates and controls butter to restrain targets.",( "Butter Restraint",),first_arc="Whole Cake Island"),
 "wring-wring":_fruit("Wring-Wring Fruit","Paramecia","Charlotte Smoothie","Wrings liquid from people and objects, storing it to enlarge the body or release slashes.",( "Liquid Extraction","Juicy Giant Slash"),forms=("Absorbed Giant Form",),first_arc="Whole Cake Island"),
 "pteranodon":_fruit("Dragon-Dragon Fruit, Model: Pteranodon","Ancient Zoan","King","Transforms into a pteranodon or hybrid with high-speed flight.",( "Imperial Deep Pride Stake",),forms=("Pteranodon Form","Hybrid Form"),first_arc="Wano"),
 "mammoth":_fruit("Elephant-Elephant Fruit, Model: Mammoth","Ancient Zoan","Jack","Transforms into a mammoth or hybrid with enormous durability and force.",( "Mammoth Charge",),forms=("Mammoth Form","Hybrid Form"),first_arc="Zou"),
 "triceratops":_fruit("Dragon-Dragon Fruit, Model: Triceratops","Ancient Zoan","Sasaki","Transforms into a triceratops or hybrid with rotating frill propulsion.",( "Triceratops Bullet",),forms=("Triceratops Form","Hybrid Form"),first_arc="Wano"),
 "pachycephalosaurus":_fruit("Dragon-Dragon Fruit, Model: Pachycephalosaurus","Ancient Zoan","Ulti","Transforms into a pachycephalosaurus or hybrid specialized in headbutts.",( "Ulti Mortar","Ulti Meteor"),forms=("Pachycephalosaurus Form","Hybrid Form"),first_arc="Wano"),
 "spinosaurus":_fruit("Dragon-Dragon Fruit, Model: Spinosaurus","Ancient Zoan","Page One","Transforms into a spinosaurus or hybrid with powerful jaws and endurance.",( "Spinosaurus Bite",),forms=("Spinosaurus Form","Hybrid Form"),first_arc="Wano"),
})

HAKI_APPLICATIONS = {
 "Observation Haki":{"branch":"Observation","applications":{
   "Presence Sensing":{"mastery":1,"effect":"detect"},"Intent Sensing":{"mastery":20,"effect":"buff"},
   "Emotion Sensing":{"mastery":30,"effect":"detect"},"Future Sight":{"mastery":80,"effect":"buff","advanced":True}}},
 "Armament Haki":{"branch":"Armament","applications":{
   "Hardening":{"mastery":1,"effect":"buff"},"Imbuement":{"mastery":15,"effect":"buff"},
   "Emission":{"mastery":55,"effect":"damage","advanced":True},"Internal Destruction":{"mastery":80,"effect":"damage","advanced":True}}},
 "Conqueror's Haki":{"branch":"Conqueror","applications":{
   "Dominating Burst":{"mastery":1,"effect":"control"},"Selective Pressure":{"mastery":30,"effect":"control"},
   "Conqueror's Coating":{"mastery":75,"effect":"buff","advanced":True},"Sky Splitting Clash":{"mastery":95,"effect":"damage","advanced":True}}},
}

FIGHTING_STYLES = {
 "Rokushiki":("Soru","Geppo","Tekkai","Shigan","Rankyaku","Kami-e","Rokuogan"),
 "Fish-Man Karate":("Fish-Man Karate Punch","Arabesque Brick Fist","Shark Brick Fist","Vagabond Drill"),
 "Fish-Man Jujutsu":("Water Shot","Ocean Current Shoulder Throw"),
 "Three Sword Style":("Three Sword Style: Onigiri","Three Thousand Worlds","Flying Dragon Blaze","Demon Aura Nine-Sword Style: Asura"),
 "Black Leg Style":("Collier","Concasser","Diable Jambe","Ifrit Jambe"),
 "Foxfire Style":("Flame-Rend","Foxfire Style: Fire Willow Flash"),
 "Electro":("Electro Claw","Electro Shower"),
 "Sulong":("Sulong Transformation",),
 "Hasshoken":("Drill Dragon Nail","Martial Backwater"),
 "Okama Kenpo":("Death Wink","Galaxy Wink","Rolling Aesthetic"),
}

TRANSFORMATIONS = {
 "Gear Second":{"owner":"Monkey D. Luffy","boosts":{"speed_pct":.35,"power_pct":.18}},
 "Gear Third":{"owner":"Monkey D. Luffy","boosts":{"power_pct":.35,"speed_pct":-.08}},
 "Gear Fourth: Boundman":{"owner":"Monkey D. Luffy","boosts":{"power_pct":.55,"defense_pct":.35,"speed_pct":.25}},
 "Gear Fourth: Snakeman":{"owner":"Monkey D. Luffy","boosts":{"power_pct":.35,"speed_pct":.55}},
 "Gear Fifth":{"owner":"Monkey D. Luffy","boosts":{"power_pct":.7,"defense_pct":.45,"speed_pct":.55}},
 "Monster Point":{"owner":"Tony Tony Chopper","boosts":{"power_pct":.55,"defense_pct":.45,"speed_pct":-.1}},
 "Demonio Fleur":{"owner":"Nico Robin","boosts":{"power_pct":.4,"defense_pct":.2}},
 "Sulong Transformation":{"owner":"Mink tribe","boosts":{"power_pct":.45,"speed_pct":.45}},
}

def fruit_by_name(name):
    low=str(name or '').lower()
    return next((row for row in DEVIL_FRUITS.values() if low in {row['name'].lower(), row['name'].lower().replace('human-human fruit, model: nika','gum-gum fruit')}),None)

def technique_index():
    index={}
    for fruit in DEVIL_FRUITS.values():
        for move in fruit['techniques']:index.setdefault(move,{"source":fruit['name'],"owner":fruit['canon_owner'],"category":"devil fruit"})
        for form in fruit['forms']:index.setdefault(form,{"source":fruit['name'],"owner":fruit['canon_owner'],"category":"transformation","effect":"transform"})
    for style,moves in FIGHTING_STYLES.items():
        for move in moves:index.setdefault(move,{"source":style,"category":"fighting style"})
    for profile in HAKI_APPLICATIONS.values():
        for move,row in profile['applications'].items():index.setdefault(move,{"source":profile['branch']+" Haki","category":"haki",**row})
    return index

CANON_TECHNIQUES=technique_index()

def _preset(name, meta):
    """Create one frozen, deterministic board contract at import time."""
    low=name.lower();source=str(meta.get('source','')).lower();effect=meta.get('effect') or 'damage'
    if effect=='transform' or any(word in low for word in (' form','gear ','sulong','big father','punk rotten','demonio')):
        return {'effect_type':'transform','resource_cost':18,'tactical':{'shape':'self','origin':'self','effect':'transform','handler':'form'},'visual_effect':{'family':'release-transformation','delivery':'self'}}
    if any(word in low for word in ('heal','restoration','hormone')):effect='heal'
    elif any(word in low for word in ('barrier','wall','fence','armor','tekkai','mirror mountain')):effect='shield'
    elif any(word in low for word in ('slow','lock','parasite','negative','soul pocus','candle lock')):effect='control'
    elif any(word in low for word in ('warp','shambles','passage','geppo','soru','yata mirror')):effect='movement'
    elif meta.get('effect'):effect=meta['effect']
    shape='self' if effect in {'buff','heal','shield','transform'} else 'burst' if any(word in low for word in ('age','volcano','raigo','gatling','jewel','shock','explosion','island shaking','sky splitting','shower')) else 'line' if any(word in low for word in ('beam','gun','spada','fist','cannon','wink','blaze','thrust','departure','lariat','drill')) else 'single'
    if effect=='control' and any(word in low for word in ('burst','pocus')):shape='burst'
    element='fire' if any(word in low+source for word in ('fire','flame','magma','heat','prometheus')) else 'ice' if 'ice' in low+source else 'lightning' if any(word in low+source for word in ('thunder','lightning','fulgora','raigo','el thor')) else 'water' if any(word in low+source for word in ('water','ocean','shark')) else 'poison' if any(word in low+source for word in ('poison','venom','gas')) else 'wind' if any(word in low+source for word in ('wind','rankyaku','tempest')) else 'spirit'
    family={'fire':'living-flame','ice':'frost-bloom','lightning':'storm-vein','water':'tidal-surge','poison':'poison-mist','wind':'wind-shear'}.get(element,'spirit-bolt')
    if effect=='shield':family='spirit-barrier'
    elif effect=='heal':family='restoration-pulse'
    elif effect=='control':family='binding-bands'
    elif effect=='movement':family='flash-step'
    elif 'slash' in low or 'sword' in source or 'onigiri' in low:family='blade-trail'
    asset={
        'living-flame':'fire-breath','frost-bloom':'water-wave','storm-vein':'lightning-bolt',
        'tidal-surge':'water-wave','poison-mist':'insect-swarm','wind-shear':'wind-blade',
        'spirit-barrier':'chakra-guard','restoration-pulse':'healing','binding-bands':'shadow-bind',
        'flash-step':'wind-blade','blade-trail':'slash','release-transformation':'chakra-guard',
    }.get(family,'lightning-lance')
    tactical={'shape':shape,'origin':'self' if shape in {'self','line'} else 'target','effect':effect}
    if shape=='line':tactical['length']=6 if any(v in low for v in ('beam','jewel','departure')) else 4
    elif shape=='burst':tactical.update(range=5,radius=2)
    elif shape=='single':tactical['range']=1 if any(v in low for v in ('clutch','kick','femur','lariat','onigiri')) else 4
    if effect=='movement':tactical['handler']='room_shambles' if 'shambles' in low else 'movement'
    if 'internal destruction' in low:tactical['handler']='advanced_haki'
    result={'effect_type':effect,'resource_cost':16 if meta.get('advanced') else 12,'tactical':tactical,
            'visual_effect':{'family':family,'asset':asset,'delivery':'self' if shape=='self' else 'area' if shape=='burst' else 'line' if shape=='line' else 'target'},
            'element':element,'armor_piercing':'internal destruction' in low}
    if effect in {'buff','detect'}:
        result['effect_type']='buff';result['tactical']['effect']='buff';result['duration_rounds']=3
        result['combat_boosts']={'speed_pct':.3} if 'observation' in source else {'power_pct':.35 if 'conqueror' in source else .2,'defense_pct':.2}
    if effect=='control':result['duration_rounds']=1
    return result

TACTICAL_PRESETS={name:_preset(name,meta) for name,meta in CANON_TECHNIQUES.items()}
