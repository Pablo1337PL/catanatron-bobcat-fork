"""Longest Road (Bobcat fork): roads leading up to an enemy building count,
the length is recomputed after every settlement on an enemy road, and the card
is set aside when a broken road leaves nobody with 5+."""

from catanatron.game import Game
from catanatron.models.board import Board
from catanatron.models.player import Color, SimplePlayer
from catanatron.state_functions import maintain_longest_road, player_key

RED, BLUE = Color.RED, Color.BLUE
# A chain of nodes on the base map: 6-7-8-9-10-11-12.
RED_ROAD = [(6, 7), (7, 8), (8, 9), (9, 10), (10, 11)]


def _red_road_of_five(board):
    board.build_settlement(RED, 6, initial_build_phase=True)
    for edge in RED_ROAD:
        board.build_road(RED, edge)


def test_cut_below_five_sets_the_card_aside():
    board = Board()
    _red_road_of_five(board)
    assert (board.road_color, board.road_length) == (RED, 5)

    # Blue settles on node 8 and splits the road into 2 + 3.
    board.build_settlement(BLUE, 26, initial_build_phase=True)
    board.build_road(BLUE, (26, 27))
    board.build_road(BLUE, (27, 8))
    board.build_settlement(BLUE, 8)

    assert board.road_lengths[RED] == 3
    assert board.road_color is None


def test_road_into_enemy_settlement_counts():
    board = Board()
    board.build_settlement(BLUE, 11, initial_build_phase=True)
    _red_road_of_five(board)  # the last segment ends at Blue's settlement

    assert board.road_lengths[RED] == 5
    assert board.road_color == RED


def test_settlement_at_road_end_keeps_its_length():
    board = Board()
    _red_road_of_five(board)

    # Blue settles on node 11, the end of Red's road.
    board.build_settlement(BLUE, 13, initial_build_phase=True)
    board.build_road(BLUE, (13, 12))
    board.build_road(BLUE, (12, 11))
    board.build_settlement(BLUE, 11)

    assert board.road_lengths[RED] == 5
    assert (board.road_color, board.road_length) == (RED, 5)
    assert max(len(path) for path in board.continuous_roads_by_player(RED)) == 5


def test_reassign_after_a_break():
    board = Board()

    board.road_color, board.road_lengths = RED, {RED: 6, BLUE: 6}
    board._reassign_longest_road()
    assert board.road_color == RED  # a tie keeps the holder

    board.road_color, board.road_lengths = RED, {RED: 5, BLUE: 6}
    board._reassign_longest_road()
    assert (board.road_color, board.road_length) == (BLUE, 6)

    board.road_color, board.road_lengths = RED, {RED: 4, BLUE: 3}
    board._reassign_longest_road()
    assert (board.road_color, board.road_length) == (None, 4)


def test_card_set_aside_takes_the_points_back():
    game = Game([SimplePlayer(RED), SimplePlayer(BLUE)])
    state = game.state
    key = player_key(state, RED)
    state.player_state[f"{key}_HAS_ROAD"] = True
    state.player_state[f"{key}_VICTORY_POINTS"] = 4
    state.player_state[f"{key}_ACTUAL_VICTORY_POINTS"] = 4

    maintain_longest_road(state, RED, None, {RED: 3, BLUE: 2})

    assert state.player_state[f"{key}_HAS_ROAD"] is False
    assert state.player_state[f"{key}_VICTORY_POINTS"] == 2
    assert state.player_state[f"{key}_ACTUAL_VICTORY_POINTS"] == 2
    assert state.player_state[f"{key}_LONGEST_ROAD_LENGTH"] == 3
