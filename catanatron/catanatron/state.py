import pickle
import random
from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap, NumberPlacement
from catanatron.models.board import Board
from catanatron.models.enums import (
    DEVELOPMENT_CARDS,
    RESOURCES,
    ActionPrompt,
    ActionRecord,
)
from catanatron.models.decks import (
    starting_devcard_bank,
    starting_resource_bank,
)
from catanatron.models.player import Color, Player

# These will be prefixed by P0_, P1_, ...
# Create Player State blueprint
PLAYER_INITIAL_STATE = {
    "VICTORY_POINTS": 0,
    "ROADS_AVAILABLE": 15,
    "SETTLEMENTS_AVAILABLE": 5,
    "CITIES_AVAILABLE": 4,
    "HAS_ROAD": False,
    "HAS_ARMY": False,
    "HAS_ROLLED": False,
    "HAS_PLAYED_DEVELOPMENT_CARD_IN_TURN": False,
    # de-normalized features (for performance since we think they are good features)
    "ACTUAL_VICTORY_POINTS": 0,
    "LONGEST_ROAD_LENGTH": 0,
    "KNIGHT_OWNED_AT_START": False,
    "MONOPOLY_OWNED_AT_START": False,
    "YEAR_OF_PLENTY_OWNED_AT_START": False,
    "ROAD_BUILDING_OWNED_AT_START": False,
}
for resource in RESOURCES:
    PLAYER_INITIAL_STATE[f"{resource}_IN_HAND"] = 0
for dev_card in DEVELOPMENT_CARDS:
    PLAYER_INITIAL_STATE[f"{dev_card}_IN_HAND"] = 0
    PLAYER_INITIAL_STATE[f"PLAYED_{dev_card}"] = 0


class State:
    """Collection of variables representing state

    Attributes:
        players (List[Player]): DEPRECATED. Reference to list of players.
            Use .colors instead, and move this reference to the Game class.
            Deprecated because we want this class to only contain state
            information that can be easily copiable.
        board (Board): Board state. Settlement locations, cities,
            roads, ect... See Board class.
        player_state (Dict[str, Any]): See PLAYER_INITIAL_STATE. It will
            contain one of each key in PLAYER_INITIAL_STATE but prefixed
            with "P<index_of_player>".
            Example: { P0_HAS_ROAD: False, P1_SETTLEMENTS_AVAILABLE: 18, ... }
        color_to_index (Dict[Color, int]): Color to seating location cache
        colors (Tuple[Color]): Represents seating order.
        resource_freqdeck (List[int]): Represents resource cards in the bank.
            Each element is the amount of [WOOD, BRICK, SHEEP, WHEAT, ORE].
        development_listdeck (List[FastDevCard]): Represents development cards in
            the bank. Already shuffled.
        buildings_by_color (Dict[Color, Dict[FastBuildingType, List]]): Cache of
            buildings. Can be used like: `buildings_by_color[Color.RED][SETTLEMENT]`
            to get a list of all node ids where RED has settlements.
        action_records (List[ActionRecord]): Log of all actions taken with their results if
            non-deterministic.
        num_turns (int): number of turns thus far
        current_player_index (int): index per colors array of player that should be
            making a decision now. Not necesarilly the same as current_turn_index
            because there are out-of-turn decisions like discarding.
        current_turn_index (int): index per colors array of player whose turn is it.
        current_prompt (ActionPrompt): DEPRECATED. Not needed; use is_initial_build_phase,
            is_moving_knight, etc... instead.
        is_discarding (bool): If current player needs to discard.
        discard_counts (List[int]): Color-index aligned number of cards each player
            must discard in the current discard sequence.
        is_moving_knight (bool): If current player needs to move robber.
        is_road_building (bool): If current player needs to build free roads per Road
            Building dev card.
        free_roads_available (int): Number of roads available left in Road Building
            phase.
        dice_seed (int, optional): When set, the n-th roll of the game is
            ``seeded_roll(dice_seed, n)``: dice independent of everything else
            (board, deck, players' searches). Never carried over to copies, so
            simulations on copies cannot see the real game's future rolls.
    """

    #: Class default, so copies (``copy``, ``fast_copy``) roll with ``random``.
    dice_seed = None

    def __init__(
        self,
        players: Sequence[Player],
        catan_map=None,
        discard_limit=7,
        friendly_robber=False,
        number_placement: NumberPlacement = "official_spiral",
        initialize=True,
        rng=None,
    ):
        if initialize:
            self.random = rng if rng is not None else random.Random()
            self.players = self.random.sample(players, len(players))
            self.colors = tuple([player.color for player in self.players])
            self.board = Board(
                catan_map
                or CatanMap.from_template(
                    BASE_MAP_TEMPLATE, number_placement, rng=self.random
                )
            )
            self.discard_limit = discard_limit
            self.friendly_robber = friendly_robber

            # feature-ready dictionary
            self.player_state = dict()
            for index in range(len(self.colors)):
                for key, value in PLAYER_INITIAL_STATE.items():
                    self.player_state[f"P{index}_{key}"] = value
            self.color_to_index = {
                color: index for index, color in enumerate(self.colors)
            }

            self.resource_freqdeck = starting_resource_bank()
            self.development_listdeck = starting_devcard_bank()
            self.random.shuffle(self.development_listdeck)

            # Auxiliary attributes to implement game logic
            self.buildings_by_color: Dict[Color, Dict[Any, Any]] = {
                p.color: defaultdict(list) for p in players
            }
            # for undo and to show in the UI the action log
            self.action_records: List[ActionRecord] = []
            self.num_turns = 0  # num_completed_turns

            # Current prompt / player
            # Two variables since there can be out-of-turn plays
            self.current_player_index = 0
            self.current_turn_index = 0

            # TODO: Deprecate self.current_prompt in favor of indicator variables
            self.current_prompt = ActionPrompt.BUILD_INITIAL_SETTLEMENT
            self.is_initial_build_phase = True
            self.is_discarding = False
            self.discard_counts: List[int] = [0] * len(self.colors)
            self.is_moving_knight = False
            self.is_road_building = False
            self.free_roads_available = 0

            self.is_resolving_trade = False
            self.current_trade: Tuple = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            self.acceptees = tuple(False for _ in self.colors)

    def current_player(self):
        """Helper for accessing Player instance who should decide next"""
        return self.players[self.current_player_index]

    def current_color(self):
        """Helper for accessing color (player) who should decide next"""
        return self.colors[self.current_player_index]

    def set_seat_order(self, colors):
        """Seats the players in the order of ``colors`` (the first one places
        first, 1-2-2-1, and starts the game).

        Only before the first action: then every seat's state is still the
        initial one, so reordering players and color indices is enough. The
        board, the deck and the random stream stay as they are.
        """
        if self.action_records:
            raise ValueError("Seat order can only be changed before the first action")
        colors = tuple(colors)
        by_color = {player.color: player for player in self.players}
        if set(colors) != set(by_color) or len(colors) != len(by_color):
            raise ValueError(
                f"Seat order {[c.value for c in colors]} does not match players "
                f"{[c.value for c in by_color]}"
            )
        self.players = [by_color[color] for color in colors]
        self.colors = colors
        self.color_to_index = {color: index for index, color in enumerate(colors)}

    def copy(self):
        """Creates a copy of this State class that can be modified without
        repercusions to this one. Immutable values are just copied over.

        Returns:
            State: State copy.
        """
        state_copy = State([], None, initialize=False)
        # Shared by reference: simulations on copies must advance the same stream.
        state_copy.random = self.random
        state_copy.players = self.players
        state_copy.discard_limit = self.discard_limit  # immutable
        state_copy.friendly_robber = self.friendly_robber  # immutable

        state_copy.board = self.board.copy()

        state_copy.player_state = self.player_state.copy()
        state_copy.color_to_index = self.color_to_index
        state_copy.colors = self.colors  # immutable

        state_copy.resource_freqdeck = self.resource_freqdeck.copy()
        state_copy.development_listdeck = self.development_listdeck.copy()

        state_copy.buildings_by_color = pickle.loads(
            pickle.dumps(self.buildings_by_color)
        )
        state_copy.action_records = self.action_records.copy()
        state_copy.num_turns = self.num_turns

        # Current prompt / player
        # Two variables since there can be out-of-turn plays
        state_copy.current_player_index = self.current_player_index
        state_copy.current_turn_index = self.current_turn_index

        state_copy.current_prompt = self.current_prompt
        state_copy.is_initial_build_phase = self.is_initial_build_phase
        state_copy.is_discarding = self.is_discarding
        state_copy.discard_counts = self.discard_counts.copy()
        state_copy.is_moving_knight = self.is_moving_knight
        state_copy.is_road_building = self.is_road_building
        state_copy.free_roads_available = self.free_roads_available

        state_copy.is_resolving_trade = self.is_resolving_trade
        state_copy.current_trade = self.current_trade
        state_copy.acceptees = self.acceptees

        return state_copy

    def fast_copy(self):
        """Same result as :meth:`copy`, without pickle (~2-3x faster).

        Used by tree search, where copying is a large part of each simulation.
        ``tests/test_fast_copy.py`` checks it field by field against ``copy``.
        """
        state_copy = State.__new__(State)
        state_copy.random = self.random  # shared, as in copy()
        state_copy.players = self.players
        state_copy.discard_limit = self.discard_limit
        state_copy.friendly_robber = self.friendly_robber

        state_copy.board = self.board.fast_copy()

        state_copy.player_state = self.player_state.copy()
        state_copy.color_to_index = self.color_to_index
        state_copy.colors = self.colors

        state_copy.resource_freqdeck = self.resource_freqdeck.copy()
        state_copy.development_listdeck = self.development_listdeck.copy()

        buildings_by_color = {}
        for color, by_type in self.buildings_by_color.items():
            copied = defaultdict(list)
            for building_type, items in by_type.items():
                copied[building_type] = list(items)
            buildings_by_color[color] = copied
        state_copy.buildings_by_color = buildings_by_color
        state_copy.action_records = self.action_records.copy()
        state_copy.num_turns = self.num_turns

        state_copy.current_player_index = self.current_player_index
        state_copy.current_turn_index = self.current_turn_index

        state_copy.current_prompt = self.current_prompt
        state_copy.is_initial_build_phase = self.is_initial_build_phase
        state_copy.is_discarding = self.is_discarding
        state_copy.discard_counts = self.discard_counts.copy()
        state_copy.is_moving_knight = self.is_moving_knight
        state_copy.is_road_building = self.is_road_building
        state_copy.free_roads_available = self.free_roads_available

        state_copy.is_resolving_trade = self.is_resolving_trade
        state_copy.current_trade = self.current_trade
        state_copy.acceptees = self.acceptees

        return state_copy
