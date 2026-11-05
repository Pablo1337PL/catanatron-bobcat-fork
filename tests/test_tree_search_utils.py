"""execute_spectrum: every branch must really be the outcome it is weighted as.

Upstream passed the outcome in ``action.value``, which the engine ignores for
random outcomes, so the ROLL branches were 11 random rolls, every
BUY_DEVELOPMENT_CARD branch drew the same top card and 4 of 5 steal branches
silently failed.
"""

import pytest

from catanatron.game import Game
from catanatron.models.enums import DEVELOPMENT_CARDS, RESOURCES, Action, ActionType
from catanatron.models.player import Color, RandomPlayer
from catanatron.players.tree_search_utils import execute_spectrum
from catanatron.state_functions import (
    get_dev_cards_in_hand,
    player_deck_replenish,
    player_key,
)


def _game_after_setup(seed=5):
    game = Game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
    while game.state.is_initial_build_phase:
        game.play_tick()
    return game


def _play_until_play_turn(game):
    game.execute(Action(game.state.current_color(), ActionType.ROLL, None))
    while game.playable_actions[0].action_type in (
        ActionType.DISCARD_RESOURCE,
        ActionType.MOVE_ROBBER,
    ):
        game.execute(game.playable_actions[0])


def test_roll_branches_are_the_sums_2_to_12():
    game = _game_after_setup()
    rng_state = game.state.random.getstate()
    roll = Action(game.state.current_color(), ActionType.ROLL, None)

    outcomes = execute_spectrum(game, roll)

    sums = [sum(child.state.action_records[-1].action.value) for child, _ in outcomes]
    assert sums == list(range(2, 13))
    assert sum(p for _, p in outcomes) == pytest.approx(1)
    assert game.state.random.getstate() == rng_state  # game's stream untouched
    assert game.state.action_records[-1].action.action_type != ActionType.ROLL


def test_development_card_branches_draw_different_cards():
    game = _game_after_setup()
    _play_until_play_turn(game)
    color = game.state.current_color()
    for resource in ("SHEEP", "WHEAT", "ORE"):
        player_deck_replenish(game.state, color, resource, 1)
    buy = Action(color, ActionType.BUY_DEVELOPMENT_CARD, None)

    outcomes = execute_spectrum(game, buy)

    drawn = []
    for child, _ in outcomes:
        gained = [
            card
            for card in DEVELOPMENT_CARDS
            if get_dev_cards_in_hand(child.state, color, card)
            > get_dev_cards_in_hand(game.state, color, card)
        ]
        assert len(gained) == 1
        drawn.append(gained[0])
    assert len(set(drawn)) == len(drawn) == len(set(game.state.development_listdeck))
    assert sum(p for _, p in outcomes) == pytest.approx(1)


def test_steal_branches_follow_the_victims_hand():
    game = _game_after_setup()
    _play_until_play_turn(game)
    color = game.state.current_color()
    victim = next(c for c in game.state.colors if c != color)
    key = player_key(game.state, victim)
    for resource in RESOURCES:
        game.state.player_state[f"{key}_{resource}_IN_HAND"] = 0
    game.state.player_state[f"{key}_WOOD_IN_HAND"] = 3
    game.state.player_state[f"{key}_ORE_IN_HAND"] = 1
    coordinate = next(
        c
        for c in game.state.board.map.land_tiles
        if c != game.state.board.robber_coordinate
    )
    rob = Action(color, ActionType.MOVE_ROBBER, (coordinate, victim))

    outcomes = execute_spectrum(game, rob)

    stolen = {
        child.state.action_records[-1].result: p for child, p in outcomes
    }
    assert stolen == {"WOOD": pytest.approx(0.75), "ORE": pytest.approx(0.25)}
    for child, _ in outcomes:
        assert child.state.board.robber_coordinate == coordinate
