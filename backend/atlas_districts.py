"""Authored atlas districts in the existing normalized projection.

These preserve source-established relative geography, not invented precision.
Later polygons take precedence for small enclaves. Unspecified hinterland keeps
the preset regional owner; changing a landmark cannot reshape a border.
"""
NARUTO_DISTRICTS = [
    ('Land of Fire', [[0,0],[100,0],[100,100],[0,100]]),
    ('Land of Earth', [[0,0],[43,0],[44,23],[39,32],[30,39],[0,43]]),
    ('Land of Wind', [[0,43],[26,43],[33,57],[34,71],[32,100],[0,100]]),
    ('Iron Country', [[43,0],[59,0],[60,19],[51,25],[44,23]]),
    ('Land of Lightning', [[59,0],[100,0],[100,37],[72,37],[64,28],[60,19]]),
    ('Land of Rain', [[26,40],[33,38],[39,44],[38,56],[33,57],[28,52]]),
    ('Land of Grass', [[30,33],[38,28],[44,32],[43,40],[39,44],[33,38],[30,39]]),
    ('Land of Waterfalls', [[39,24],[44,23],[51,25],[51,32],[44,32],[38,28]]),
    ('Land of Rice Fields', [[51,25],[60,19],[64,28],[63,36],[54,38],[51,32]]),
    ('Land of Hot Water', [[64,28],[72,37],[76,41],[74,51],[65,50],[63,36]]),
    ('Land of Rivers', [[33,57],[38,56],[43,65],[42,78],[38,88],[32,100],[34,71]]),
    ('Land of Tea', [[43,72],[53,70],[62,72],[57,100],[38,100],[38,88],[42,78]]),
]

# The Saharan Empire occupies the larger northern/western share; tiny named
# sites no longer carve nation-sized nearest-neighbor wedges out of it.
OVERGEARED_DISTRICTS = [
    ('Saharan Empire', [[0,0],[70,0],[70,51],[56,56],[47,49],[31,49],[25,53],[0,53]]),
    ('Eternal Kingdom', [[0,53],[25,53],[31,49],[47,49],[56,56],[70,51],[70,100],[0,100]]),
    ('Talima', [[11,20],[19,20],[19,29],[11,29]]),
    ('Vatican', [[52,36],[58,36],[58,42],[52,42]]),
    ('Valhalla', [[54,47],[62,47],[64,54],[56,56],[53,52]]),
]

SLIME_DISTRICTS = [
    ('Great Jura Forest', [[0,0],[100,0],[100,100],[0,100]]),
    ('Lubelius', [[0,0],[36,0],[37,32],[25,35],[0,37]]),
    ('Dwargon', [[36,0],[69,0],[70,25],[62,30],[48,29],[37,32]]),
    ('Eastern Empire', [[69,0],[100,0],[100,55],[79,51],[70,40],[70,25]]),
    ('Falmuth', [[32,28],[48,29],[48,38],[39,42],[31,37]]),
    ('Ingrassia', [[0,37],[25,35],[31,37],[29,57],[0,64]]),
    ('Blumund', [[29,42],[39,42],[41,54],[31,59],[29,57]]),
    ('Thalion', [[0,64],[31,59],[43,64],[42,84],[34,100],[0,100]]),
    ('Eurazania', [[43,64],[58,61],[68,62],[71,77],[63,100],[34,100],[42,84]]),
    ('Jistav', [[70,40],[79,51],[100,55],[100,68],[78,68],[68,62]]),
    ("Milim's Domain", [[78,68],[100,68],[100,100],[63,100],[71,77]]),
    ('Tempest', [[49,49],[53,49],[54,52],[51,54],[49,52]]),
]

AUTHORED_DISTRICTS = {'Naruto': NARUTO_DISTRICTS, 'Overgeared': OVERGEARED_DISTRICTS,
                      'Reincarnated as a Slime': SLIME_DISTRICTS}
