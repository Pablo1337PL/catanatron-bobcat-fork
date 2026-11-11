import pytest

from catanatron.game import Game
from catanatron.models.map import build_map
from catanatron.models.player import Color, SimplePlayer
from catanatron.notation import CORNERS, SEPARATOR, SIDES, board_names
from catanatron.serialization import web_view


def _map(seed=None, map_type="BASE"):
    game = Game(
        [SimplePlayer(Color.RED), SimplePlayer(Color.BLUE)],
        seed=1,
        board_seed=seed,
        catan_map=build_map(map_type) if map_type != "BASE" else None,
    )
    return game.state.board.map


@pytest.mark.parametrize(
    "catan_map", [_map(1), _map(443811209), _map(77), _map(map_type="TOURNAMENT")]
)
def test_every_place_has_one_name(catan_map):
    names = board_names(catan_map)

    assert sorted(names.tiles.values()) == list("ABCDEFGHIJKLMNOPQRS")
    assert names.tiles[(0, 0, 0)] == "J"
    assert len(names.nodes) == 54 and len(set(names.nodes.values())) == 54
    assert len(names.edges) == 72 and len(set(names.edges.values())) == 72
    assert set(names.nodes) == set(catan_map.land_nodes)


def test_rows_read_left_to_right():
    names = board_names(_map(1))
    top_row = sorted(
        (c for c in names.tiles if c[2] == -2), key=lambda c: c[0]
    )
    assert [names.tiles[c] for c in top_row] == ["A", "B", "C"]


def test_names_do_not_depend_on_the_seed():
    first, second = board_names(_map(1)), board_names(_map(443811209))
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert first.tiles == second.tiles


def test_the_two_places_called_10_5_8_on_board_443811209():
    names = board_names(_map(443811209))
    assert names.nodes[18] == f"D{SEPARATOR}S"
    assert names.nodes[8] == f"K{SEPARATOR}SE"


def test_every_name_parses_back():
    catan_map = _map(5)
    names = board_names(catan_map)
    for node_id, label in names.nodes.items():
        assert names.parse_node(label) == node_id
    for edge, label in names.edges.items():
        assert names.parse_edge(label) == edge
    for coordinate, letter in names.tiles.items():
        assert names.parse_tile(letter) == coordinate
    # Every corner of every land tile names a node, canonical or not
    for coordinate, tile in catan_map.land_tiles.items():
        letter = names.tiles[coordinate]
        for ref, node_id in tile.nodes.items():
            assert names.parse_node(letter + SEPARATOR + CORNERS[ref]) == node_id
        for ref, edge in tile.edges.items():
            assert names.parse_edge(letter + SEPARATOR + SIDES[ref]) == tuple(sorted(edge))


@pytest.mark.parametrize("text", ["D·S", "D-S", "D/S", "DS", "ds", " d · s "])
def test_spellings(text):
    assert board_names(_map(1)).parse_node(text) == 18


@pytest.mark.parametrize(
    "text, parse",
    [
        ("T·N", "parse_node"),
        ("D·X", "parse_node"),
        ("D·E", "parse_node"),  # E is a side, not a corner
        ("D·N", "parse_edge"),  # N is a corner, not a side
        ("", "parse_node"),
        ("Z", "parse_tile"),
    ],
)
def test_bad_names(text, parse):
    with pytest.raises(ValueError):
        getattr(board_names(_map(1)), parse)(text)


def test_web_view_carries_labels():
    game = Game([SimplePlayer(Color.RED), SimplePlayer(Color.BLUE)], seed=3)
    view = web_view(game)

    land = [t for t in view["tiles"] if t["tile"]["type"] in ("RESOURCE_TILE", "DESERT")]
    assert sorted(t["label"] for t in land) == list("ABCDEFGHIJKLMNOPQRS")
    assert all("label" not in t for t in view["tiles"] if t not in land)
    labelled_nodes = [n for n in view["nodes"].values() if "label" in n]
    labelled_edges = [e for e in view["edges"] if "label" in e]
    assert len(labelled_nodes) == 54 and len(labelled_edges) == 72
    assert view["nodes"][18]["label"] == "D·S"
