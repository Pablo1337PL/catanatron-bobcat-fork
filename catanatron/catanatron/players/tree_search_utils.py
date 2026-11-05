import math
from collections import defaultdict

from catanatron.game import Game
from catanatron.models.map import number_probability
from catanatron.models.enums import (
    DEVELOPMENT_CARDS,
    RESOURCES,
    SETTLEMENT,
    CITY,
    Action,
    ActionRecord,
    ActionType,
)
from catanatron.state_functions import (
    get_player_buildings,
    get_dev_cards_in_hand,
    get_player_freqdeck,
    get_enemy_colors,
)
from catanatron.features import build_production_features
from catanatron.players.value import value_production

DETERMINISTIC_ACTIONS = set(
    [
        ActionType.END_TURN,
        ActionType.BUILD_SETTLEMENT,
        ActionType.BUILD_ROAD,
        ActionType.BUILD_CITY,
        ActionType.PLAY_KNIGHT_CARD,
        ActionType.PLAY_YEAR_OF_PLENTY,
        ActionType.PLAY_ROAD_BUILDING,
        ActionType.MARITIME_TRADE,
        ActionType.DISCARD_RESOURCE,  # for simplicity... ok if reality is slightly different
        ActionType.PLAY_MONOPOLY,  # for simplicity... we assume good card-counting and bank is visible...
    ]
)


def execute_deterministic(game, action):
    copy = game.copy()
    copy.execute(action, validate_action=False)
    return [(copy, 1)]


def _execute_outcome(game: Game, action: Action, result):
    """Copy of ``game`` after ``action`` with its random outcome forced to ``result``.

    The engine reads random outcomes (dice, drawn card, stolen resource) only
    from ``action_record.result``; ``action.value`` is ignored for them. Passing
    the outcome in the record makes the branch deterministic and leaves the
    game's random stream untouched.
    """
    option_game = game.copy()
    option_game.execute(
        action,
        validate_action=False,
        action_record=ActionRecord(action=action, result=result),
    )
    return option_game


def roll_outcomes():
    """[(dice, proba)] for the sums 2..12; production depends only on the sum."""
    return [
        ((roll // 2, math.ceil(roll / 2)), number_probability(roll))
        for roll in range(2, 13)
    ]


def development_card_outcomes(game: Game, color):
    """[(card, proba)] for a development card bought by ``color``.

    Drawn from what is face down for the buyer: the bank's deck plus the
    opponents' unplayed cards. Only cards actually left in the bank can be
    drawn, so the others are skipped and the probabilities renormalized.
    """
    state = game.state
    pool = {card: state.development_listdeck.count(card) for card in DEVELOPMENT_CARDS}
    for enemy_color in get_enemy_colors(state.colors, color):
        for card in DEVELOPMENT_CARDS:
            pool[card] += get_dev_cards_in_hand(state, enemy_color, card)

    feasible = [
        card
        for card in DEVELOPMENT_CARDS
        if pool[card] > 0 and card in state.development_listdeck
    ]
    total = sum(pool[card] for card in feasible)
    return [(card, pool[card] / total) for card in feasible]


def steal_outcomes(game: Game, robbed_color):
    """[(resource, proba)] stolen from ``robbed_color``: proportional to the hand."""
    hand = get_player_freqdeck(game.state, robbed_color)
    total = sum(hand)
    return [
        (resource, count / total)
        for resource, count in zip(RESOURCES, hand)
        if count > 0
    ]


def execute_spectrum(game: Game, action: Action):
    """Returns [(game_copy, proba), ...] tuples for result of given action.
    Result probas should add up to 1. Does not modify self"""
    if action.action_type in DETERMINISTIC_ACTIONS:
        return execute_deterministic(game, action)
    elif action.action_type == ActionType.BUY_DEVELOPMENT_CARD:
        outcomes = development_card_outcomes(game, action.color)
        if not outcomes:
            return execute_deterministic(game, action)
        return [
            (_execute_outcome(game, action, card), proba) for card, proba in outcomes
        ]
    elif action.action_type == ActionType.ROLL:
        return [
            (_execute_outcome(game, action, dice), proba)
            for dice, proba in roll_outcomes()
        ]
    elif action.action_type == ActionType.MOVE_ROBBER:
        (coordinate, robbed_color) = action.value
        if robbed_color is None:  # no one to steal, then deterministic
            return execute_deterministic(game, action)
        outcomes = steal_outcomes(game, robbed_color)
        if not outcomes:  # nothing to steal
            return execute_deterministic(game, action)
        return [
            (_execute_outcome(game, action, resource), proba)
            for resource, proba in outcomes
        ]
    else:
        raise RuntimeError("Unknown ActionType " + str(action.action_type))


def expand_spectrum(game, actions):
    """Consumes game if playable_actions not specified"""
    children = defaultdict(list)
    for action in actions:
        outprobas = execute_spectrum(game, action)
        children[action] = outprobas
    return children  # action => (game, proba)[]


def list_prunned_actions(game: Game):
    current_color = game.state.current_color()
    playable_actions = game.playable_actions
    actions = playable_actions.copy()
    types = set(map(lambda a: a.action_type, playable_actions))

    # Prune Initial Settlements at 1-tile places
    if ActionType.BUILD_SETTLEMENT in types and game.state.is_initial_build_phase:
        actions = filter(
            lambda a: len(game.state.board.map.adjacent_tiles[a.value]) != 1, actions
        )

    # Prune Trading if can hold for resources. Only for rare resources.
    if ActionType.MARITIME_TRADE in types:
        port_resources = game.state.board.get_player_port_resources(current_color)
        has_three_to_one = None in port_resources
        # TODO: for 2:1 ports, skip any 3:1 or 4:1 trades
        # TODO: if can_safely_hold, prune all
        tmp_actions = []
        for action in actions:
            if action.action_type != ActionType.MARITIME_TRADE:
                tmp_actions.append(action)
                continue
            # has 3:1, skip any 4:1 trades
            if has_three_to_one and action.value[3] is not None:
                continue
            tmp_actions.append(action)
        actions = tmp_actions

    if ActionType.MOVE_ROBBER in types:
        actions = prune_robber_actions(current_color, game, actions)

    return list(actions)


def prune_robber_actions(current_color, game, actions):
    """Eliminate all but the most impactful tile"""
    enemy_color = next(filter(lambda c: c != current_color, game.state.colors))
    enemy_owned_tiles = set()
    for node_id in get_player_buildings(game.state, enemy_color, SETTLEMENT):
        enemy_owned_tiles.update(game.state.board.map.adjacent_tiles[node_id])
    for node_id in get_player_buildings(game.state, enemy_color, CITY):
        enemy_owned_tiles.update(game.state.board.map.adjacent_tiles[node_id])

    robber_moves = set(
        filter(
            lambda a: a.action_type == ActionType.MOVE_ROBBER
            and game.state.board.map.tiles[a.value[0]] in enemy_owned_tiles,
            actions,
        )
    )

    if len(robber_moves) == 0:
        return actions

    production_features = build_production_features(True)

    def impact(action):
        game_copy = game.copy()
        game_copy.execute(action)

        our_production_sample = production_features(game_copy, current_color)
        enemy_production_sample = production_features(game_copy, current_color)
        production = value_production(our_production_sample, "P0")
        enemy_production = value_production(enemy_production_sample, "P1")

        return enemy_production - production

    most_impactful_robber_action = max(
        robber_moves, key=impact
    )  # most production and variety producing
    actions = filter(
        lambda a: a.action_type != ActionType.MOVE_ROBBER
        or a == most_impactful_robber_action,
        # lambda a: a.action_type != ActionType.MOVE_ROBBER or a in robber_moves,
        actions,
    )
    return actions
