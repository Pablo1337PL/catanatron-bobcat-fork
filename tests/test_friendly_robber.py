"""Friendly robber, 1v1 rules: a player with <= 2 *visible* victory points is
protected, and that includes the player moving the robber."""

from catanatron.game import Game
from catanatron.models.actions import (
    FRIENDLY_ROBBER_MAX_VP,
    generate_playable_actions,
)
from catanatron.models.enums import ActionPrompt, ActionType
from catanatron.models.player import Color, RandomPlayer
from catanatron.state_functions import (
    get_actual_victory_points,
    get_visible_victory_points,
)


def _players():
    return [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)]


def _tile_owners(state, coordinate):
    tile = state.board.map.land_tiles[coordinate]
    return {
        state.board.buildings[n][0]
        for n in tile.nodes.values()
        if n in state.board.buildings
    }


def _game_at_robber_move(seed, friendly_robber=True):
    """A game stopped at a robber move right after the initial placements
    (both players have exactly 2 visible points)."""
    game = Game(_players(), seed=seed, friendly_robber=friendly_robber)
    while game.state.is_initial_build_phase:
        game.play_tick()
    game.state.current_prompt = ActionPrompt.MOVE_ROBBER
    game.state.is_moving_knight = False
    game.playable_actions = generate_playable_actions(game.state)
    return game


def test_protects_self_and_opponent_with_2_visible_points():
    game = _game_at_robber_move(seed=3)
    state = game.state
    me = state.current_color()
    assert FRIENDLY_ROBBER_MAX_VP == 2
    assert all(get_visible_victory_points(state, c) == 2 for c in state.colors)
    targets = {a.value[0] for a in game.playable_actions}
    assert targets
    for coordinate in targets:
        assert not _tile_owners(state, coordinate)  # neither theirs nor mine

    # Without the rule the robber may land next to buildings, own included
    regular = _game_at_robber_move(seed=3, friendly_robber=False)
    actions = regular.playable_actions
    assert any(_tile_owners(regular.state, a.value[0]) for a in actions)
    assert any(me in _tile_owners(regular.state, a.value[0]) for a in actions)


def test_counts_only_visible_points():
    game = _game_at_robber_move(seed=3)
    state = game.state
    me = state.current_color()
    opponent = next(c for c in state.colors if c != me)
    key = f"P{state.color_to_index[opponent]}"

    # Victory point cards in hand are hidden: still protected
    state.player_state[f"{key}_VICTORY_POINT_IN_HAND"] += 3
    state.player_state[f"{key}_ACTUAL_VICTORY_POINTS"] += 3
    actions = generate_playable_actions(state)
    assert all(opponent not in _tile_owners(state, a.value[0]) for a in actions)

    # Visible points (e.g. longest road) lift the opponent's protection, not mine
    state.player_state[f"{key}_VICTORY_POINTS"] += 2
    actions = generate_playable_actions(state)
    assert any(opponent in _tile_owners(state, a.value[0]) for a in actions)
    assert all(me not in _tile_owners(state, a.value[0]) for a in actions)


def test_whole_game_respects_rule():
    game = Game(_players(), seed=7, friendly_robber=True, vps_to_win=15, discard_limit=9)
    checked = 0
    while game.winning_color() is None and game.state.num_turns < 1000:
        actions = game.playable_actions
        if actions[0].action_type == ActionType.MOVE_ROBBER:
            protected = {
                c
                for c in game.state.colors
                if get_visible_victory_points(game.state, c) <= FRIENDLY_ROBBER_MAX_VP
            }
            allowed = [
                a for a in actions if not (_tile_owners(game.state, a.value[0]) & protected)
            ]
            if allowed:  # when no tile is allowed the engine allows them all
                assert len(allowed) == len(actions)
                checked += 1
        game.play_tick()
    assert checked > 0
    winner = game.winning_color()
    if winner is not None:
        assert get_actual_victory_points(game.state, winner) >= 15
