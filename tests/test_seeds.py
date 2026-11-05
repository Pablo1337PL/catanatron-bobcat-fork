"""Separate seeds for the game, the board and the dice, and explicit seat order."""

import json

import pytest

from catanatron.apply_action import seeded_roll
from catanatron.game import Game
from catanatron.models.enums import Action, ActionType
from catanatron.models.map import build_map
from catanatron.models.player import Color, RandomPlayer
from catanatron.players.value import ValueFunctionPlayer
from catanatron.serialization import client_view, state_from_json, state_to_json


def _players(cls=ValueFunctionPlayer):
    return [cls(Color.RED), cls(Color.BLUE)]


def _tiles(game):
    return sorted(
        (c, t.resource, t.number) for c, t in game.state.board.map.land_tiles.items()
    )


def _rolls(game):
    return [
        r.result
        for r in game.state.action_records
        if r.action.action_type == ActionType.ROLL
    ]


def test_board_seed_alone_defines_the_board():
    a = Game(_players(), seed=1, board_seed=42)
    b = Game(_players(), seed=2, board_seed=42, dice_seed=9)
    c = Game(_players(), seed=1, board_seed=43)
    assert _tiles(a) == _tiles(b)
    assert _tiles(a) != _tiles(c)
    assert a.board_seed == 42
    assert _tiles(a) == sorted(
        (c, t.resource, t.number) for c, t in build_map("BASE", board_seed=42).land_tiles.items()
    )


def test_dice_do_not_depend_on_board_or_players():
    a = Game(_players(), seed=1, board_seed=1, dice_seed=7)
    b = Game(_players(RandomPlayer), seed=5, board_seed=2, dice_seed=7)
    a.play()
    b.play()
    n = min(len(_rolls(a)), len(_rolls(b)))
    assert n > 20
    assert _rolls(a)[:n] == _rolls(b)[:n]
    assert _rolls(a) == [seeded_roll(7, i) for i in range(len(_rolls(a)))]


def test_search_on_copies_does_not_shift_the_dice():
    """Copies have no dice seed: rolling on them neither sees nor moves the real dice."""
    game = Game(_players(), seed=3, board_seed=3, dice_seed=11)
    while game.state.is_initial_build_phase:
        game.play_tick()
    roll = Action(game.state.current_color(), ActionType.ROLL, None)
    for copy in (game.copy(), game.fast_copy()):
        assert copy.dice_seed is None
        for _ in range(5):
            copy.copy().execute(roll)
    game.execute(roll)
    assert game.state.action_records[-1].result == seeded_roll(11, 0)


def test_same_seeds_same_game():
    def play():
        game = Game(_players(), seed=4, board_seed=5, dice_seed=6)
        game.play()
        return [repr(r) for r in game.state.action_records]

    assert play() == play()


def test_seeds_survive_storage_and_dice_seed_is_hidden():
    game = Game(_players(), seed=1, board_seed=2, dice_seed=3)
    for _ in range(30):
        game.play_tick()
    doc = json.loads(json.dumps(state_to_json(game)))
    restored = state_from_json(doc, _players())
    assert (restored.seed, restored.board_seed, restored.dice_seed) == (1, 2, 3)
    view = client_view(doc)
    assert "seed" not in view["game"] and "dice_seed" not in view["game"]
    assert view["game"]["board_seed"] == 2

    # the restored game rolls on exactly like the original
    for g in (game, restored):
        while len(_rolls(g)) < 15:
            g.play_tick()
    assert _rolls(game)[:15] == _rolls(restored)[:15]


def test_older_documents_without_seeds_load():
    game = Game(_players(), seed=1)
    doc = state_to_json(game)
    del doc["game"]["board_seed"], doc["game"]["dice_seed"]
    restored = state_from_json(doc, _players())
    assert restored.board_seed is None and restored.dice_seed is None


@pytest.mark.parametrize("order", [(Color.RED, Color.BLUE), (Color.BLUE, Color.RED)])
def test_seat_order(order):
    game = Game(_players(), seed=8, seat_order=order)
    assert game.state.colors == order
    assert [p.color for p in game.state.players] == list(order)
    assert game.state.current_color() == order[0]
    assert all(a.color == order[0] for a in game.playable_actions)


def test_seat_order_keeps_the_rest_of_the_game():
    """Seats are set after the random draw, so deck and map stay the same."""
    a = Game(_players(), seed=8, seat_order=(Color.RED, Color.BLUE))
    b = Game(_players(), seed=8, seat_order=(Color.BLUE, Color.RED))
    assert a.state.development_listdeck == b.state.development_listdeck
    assert _tiles(a) == _tiles(b)
    assert a.state.random.getstate() == b.state.random.getstate()


def test_seat_order_only_before_first_action():
    game = Game(_players(), seed=1)
    with pytest.raises(ValueError):
        game.set_seat_order((Color.RED, Color.ORANGE))
    game.play_tick()
    with pytest.raises(ValueError):
        game.set_seat_order((Color.RED, Color.BLUE))
