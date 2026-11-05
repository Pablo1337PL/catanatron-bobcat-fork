"""Game.fast_copy() must behave exactly like Game.copy(), only faster."""

import random
import timeit

import pytest

from catanatron.game import Game
from catanatron.models.enums import ActionRecord
from catanatron.models.player import Color, RandomPlayer


def _sample_states(num_games=4, every=7):
    states = []
    for seed in range(num_games):
        game = Game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
        tick = 0
        while game.winning_color() is None and game.state.num_turns < 300:
            if tick % every == 0:
                states.append(game.copy())
            game.play_tick()
            tick += 1
    return states


@pytest.fixture(scope="module")
def sample_states():
    return _sample_states()


def _fingerprint(game):
    """Everything executing an action mutates."""
    s, b = game.state, game.state.board
    return repr(
        (
            sorted(s.player_state.items()),
            {c: dict(v) for c, v in s.buildings_by_color.items()},
            sorted(b.buildings.items()),
            sorted(b.roads.items()),
            {
                c: sorted(sorted(x) for x in comps)
                for c, comps in b.connected_components.items()
            },
            sorted(b.board_buildable_ids),
            dict(b.road_lengths),
            b.road_color,
            b.road_length,
            b.robber_coordinate,
            {c: sorted(v) for c, v in b.buildable_edges_cache.items()},
            {c: sorted(map(str, v)) for c, v in b.player_port_resources_cache.items()},
            s.resource_freqdeck,
            s.development_listdeck,
            len(s.action_records),
            s.num_turns,
            s.current_player_index,
            s.current_turn_index,
            s.current_prompt,
            s.is_discarding,
            s.discard_counts,
            s.is_moving_knight,
            s.is_road_building,
            s.free_roads_available,
            # list order depends on set iteration order, compare as a set
            sorted(map(repr, game.playable_actions)),
        )
    )


def test_same_fields_as_copy(sample_states):
    for game in sample_states[::3]:
        game.state.board.buildable_edges(game.state.current_color())  # fill caches
        game.state.board.get_player_port_resources(game.state.current_color())
        ref, fast = game.copy(), game.fast_copy()
        assert set(vars(ref)) == set(vars(fast))
        assert set(vars(ref.state)) == set(vars(fast.state))
        assert set(vars(ref.state.board)) == set(vars(fast.state.board))
        assert _fingerprint(ref) == _fingerprint(fast)
        for name in ("random", "players", "colors", "color_to_index"):
            assert getattr(fast.state, name) is getattr(game.state, name)
        assert fast.state.board.map is game.state.board.map
        assert type(fast.state.board.connected_components) is type(
            ref.state.board.connected_components
        )
        for color in game.state.colors:
            assert type(fast.state.buildings_by_color[color]) is type(
                ref.state.buildings_by_color[color]
            )


def test_copy_is_independent(sample_states):
    checked = 0
    for game in sample_states[::5]:
        before = _fingerprint(game)
        for action in game.playable_actions:
            child = game.fast_copy()
            child.execute(action)
            for _ in range(3):  # further moves must not touch the original either
                if child.winning_color() is not None:
                    break
                child.execute(child.playable_actions[0])
            checked += 1
        assert _fingerprint(game) == before
    assert checked > 100


def test_games_continue_identically(sample_states):
    for game in sample_states[::10]:
        a, b = game.copy(), game.fast_copy()
        rng = random.Random(0)
        for _ in range(60):
            if a.winning_color() is not None:
                break
            action = sorted(a.playable_actions, key=repr)[
                rng.randrange(len(a.playable_actions))
            ]
            a.execute(action)
            result = a.state.action_records[-1].result
            b.execute(
                action,
                action_record=(
                    ActionRecord(action=action, result=result)
                    if result is not None
                    else None
                ),
            )
            assert _fingerprint(a) == _fingerprint(b)


def test_faster_than_copy(sample_states):
    game = sample_states[len(sample_states) // 2]
    ref = timeit.timeit(game.copy, number=300)
    fast = timeit.timeit(game.fast_copy, number=300)
    assert fast < ref
