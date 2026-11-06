"""
This is to allow an API like:

from catanatron import Game, Player, Color, Accumulator
"""

from catanatron.game import Game, GameAccumulator
from catanatron.models.player import Player, Color, RandomPlayer
from catanatron.models.enums import (
    Action,
    ActionType,
    WOOD,
    BRICK,
    SHEEP,
    WHEAT,
    ORE,
    RESOURCES,
)

#: Version of the Bobcat fork's API (seeds, seat order, 1v1 friendly robber,
#: fast copy, ...). Bumped whenever something the Bobcat agent relies on
#: changes, so the agent can refuse to run on an older engine. Read from code
#: rather than package metadata, so a ``git pull`` is enough to update it.
BOBCAT_FORK_VERSION = 4  # 2: Longest Road fixes (counting, recompute, set aside); 3: create_app(analyzer=...); 4: 1v1 only (API, registry), no MINI map
