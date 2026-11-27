import random

from catanatron import WOOD, BRICK
from catanatron.models.coordinate_system import Direction, UNIT_VECTORS, add
from catanatron.models.map import (
    BASE_MAP_TEMPLATE,
    CatanMap,
    LandTile,
    initialize_tiles,
    get_nodes_and_edges,
    get_node_counter_production,
    DICE_PROBAS,
    build_map,
)
from catanatron.models.spiral import spiral_land_coordinates


def assert_no_adjacent_red_pips(all_tiles):
    land_tiles = {
        coordinate: tile
        for coordinate, tile in all_tiles.items()
        if isinstance(tile, LandTile)
    }

    for coordinate, tile in land_tiles.items():
        if tile.number not in (6, 8):
            continue

        for direction in Direction:
            neighbor_coordinate = add(coordinate, UNIT_VECTORS[direction])
            if neighbor_coordinate not in land_tiles:
                continue

            neighbor = land_tiles[neighbor_coordinate]
            assert neighbor.number not in (6, 8), (
                f"adjacent red pips found at {coordinate}={tile.number} and "
                f"{neighbor_coordinate}={neighbor.number}"
            )


def test_node_production_of_same_resource_adjacent_tile():
    # See https://github.com/bcollazo/catanatron/issues/263.
    adjacent_tiles = {
        1: [
            LandTile(1, WOOD, 8, dict(), dict()),
            LandTile(2, WOOD, 6, dict(), dict()),
            LandTile(3, WOOD, 12, dict(), dict()),
        ]
    }
    result = get_node_counter_production(adjacent_tiles, 1)
    assert result["WOOD"] == DICE_PROBAS[12] + DICE_PROBAS[6] + DICE_PROBAS[8]


def test_base_map_can_be_created():
    catan_map = CatanMap.from_template(BASE_MAP_TEMPLATE)
    assert len(catan_map.land_tiles) == 19
    assert len(catan_map.node_production) == 54


def test_official_spiral():
    random.seed(0)

    for _ in range(100):
        all_tiles = initialize_tiles(
            BASE_MAP_TEMPLATE, number_placement="official_spiral"
        )
        land_tiles = [tile for tile in all_tiles.values() if isinstance(tile, LandTile)]
        desert_tiles = [tile for tile in land_tiles if tile.resource is None]

        assert len(desert_tiles) == 1
        assert desert_tiles[0].number is None
        assert all(
            tile.number is not None for tile in land_tiles if tile.resource is not None
        )
        assert_no_adjacent_red_pips(all_tiles)


def test_get_nodes_and_edges_on_empty_board():
    nodes, edges, node_autoinc = get_nodes_and_edges({}, (0, 0, 0), 0)
    assert max(map(lambda n: n, nodes.values())) == 5


def test_get_nodes_and_edges_for_east_attachment():
    nodes1, edges1, node_autoinc = get_nodes_and_edges({}, (0, 0, 0), 0)
    nodes2, edges2, node_autoinc = get_nodes_and_edges(
        {(0, 0, 0): LandTile(0, WOOD, 3, nodes1, edges1)},
        (1, -1, 0),
        node_autoinc,
    )
    assert max(map(lambda n: n, nodes2.values())) == 9
    assert len(edges2.values()) == 6


def test_get_nodes_and_edges_for_east_and_southeast_attachment():
    nodes1, edges1, node_autoinc = get_nodes_and_edges({}, (0, 0, 0), 0)
    nodes2, edges2, node_autoinc = get_nodes_and_edges(
        {(0, 0, 0): LandTile(0, WOOD, 3, nodes1, edges1)},
        (1, -1, 0),
        node_autoinc,
    )
    nodes3, edges3, node_autoinc = get_nodes_and_edges(
        {
            (0, 0, 0): LandTile(1, WOOD, 3, nodes1, edges1),
            (1, -1, 0): LandTile(2, BRICK, 6, nodes2, edges2),
        },
        (0, -1, 1),
        node_autoinc,
    )
    assert max(map(lambda n: n, nodes3.values())) == 12
    assert len(edges3.values()) == 6


# colonizing-pig's tile order (engine/catan.cpp, LAND) as (q, r) = Catanatron's (x, z),
# and its number tokens A..R (TOKENS): its Board::random puts them in this order.
PIG_TILE_ORDER = [(0, -2), (1, -2), (2, -2), (2, -1), (2, 0), (1, 1), (0, 2), (-1, 2), (-2, 2),
                  (-2, 1), (-2, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0), (0, 0)]
PIG_TOKENS = [5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11]


def test_official_spiral_is_the_spiral_of_colonizing_pig():
    for board_seed in range(50):
        catan_map = build_map("BASE", board_seed=board_seed)
        numbers = [
            catan_map.land_tiles[(q, -q - r, r)].number
            for q, r in PIG_TILE_ORDER
            if catan_map.land_tiles[(q, -q - r, r)].resource is not None
        ]
        assert numbers == PIG_TOKENS


def test_catanatron_spiral_is_kept_for_older_boards():
    catan_map = build_map("BASE", "catanatron_spiral", board_seed=7)
    order = spiral_land_coordinates(catan_map.tiles, (2, -2, 0))
    numbers = [catan_map.land_tiles[c].number for c in order if catan_map.land_tiles[c].resource is not None]
    assert numbers == PIG_TOKENS
    # Same tiles, other numbers than the official spiral
    official = build_map("BASE", board_seed=7)
    assert [t.resource for t in official.land_tiles.values()] == [
        t.resource for t in catan_map.land_tiles.values()
    ]
    assert [t.number for t in official.land_tiles.values()] != [
        t.number for t in catan_map.land_tiles.values()
    ]
