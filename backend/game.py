"""Core game engine: GameSession composes topic mixins so no single file has
to hold the whole engine. Each engine_*.py is a focused slice (campaign
creation, the turn loop, time skips, chat/social, persistence, journal
helpers); combat.py is the local, AI-cost-free combat resolver. Splitting
these out is purely organizational — every mixin operates on the same
self.state via ordinary Python attribute access, so behavior is unchanged
from the single-file version this replaced.

MRO note: only CoreMixin defines __init__; every other mixin assumes it has
already run (self.state, self.ai, self.lock, etc. all come from there), so
CoreMixin must stay last in the GameSession bases list.
"""
import random  # noqa: F401 — re-exported so tests can `patch("game.random.X")`; same module object as engine_*.random
from util import SAVE_DIR  # noqa: F401 — re-exported so tests/callers can `patch("game.SAVE_DIR", ...)`; engine_persistence reads it live via this module

from engine_core import CoreMixin
from engine_campaign import CampaignMixin
from engine_turns import TurnsMixin
from engine_time import TimeSkipMixin
from engine_social import SocialMixin
from engine_persistence import PersistenceMixin
from engine_journal import JournalMixin
from combat import CombatMixin


class GameSession(CombatMixin, CampaignMixin, TurnsMixin, TimeSkipMixin, SocialMixin,
                   PersistenceMixin, JournalMixin, CoreMixin):
    """The full game engine. See the module docstring for how this is assembled."""
    pass
