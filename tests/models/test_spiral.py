import pytest

from catanatron.models.map import BASE_MAP_TEMPLATE, initialize_tiles
from catanatron.models.spiral import spiral_land_coordinates


def test_spiral_land_coordinates_rejects_non_land_start():
    all_tiles = initialize_tiles(BASE_MAP_TEMPLATE, number_placement="random")

    with pytest.raises(ValueError, match="start must be a land tile"):
        list(spiral_land_coordinates(all_tiles, (2, -3, 1)))


def test_spiral_land_coordinates_rejects_non_edge_base_land_start():
    all_tiles = initialize_tiles(BASE_MAP_TEMPLATE, number_placement="random")

    with pytest.raises(ValueError, match="start must be on the outer edge"):
        list(spiral_land_coordinates(all_tiles, (0, 0, 0)))


def test_spiral_land_coordinates_base_map_order_from_tile_seven():
    all_tiles = initialize_tiles(BASE_MAP_TEMPLATE, number_placement="random")

    ids = [
        all_tiles[coord].id for coord in spiral_land_coordinates(all_tiles, (2, -2, 0))
    ]

    assert ids == [7, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 1, 6, 5, 4, 3, 2, 0]


def test_spiral_land_coordinates_clockwise_from_the_top_left_corner():
    all_tiles = initialize_tiles(BASE_MAP_TEMPLATE, number_placement="random")

    order = [(x, z) for x, _, z in spiral_land_coordinates(all_tiles, (0, 2, -2), clockwise=True)]

    # Along the top row first, then down the right side, ring by ring to the centre
    assert order == [(0, -2), (1, -2), (2, -2), (2, -1), (2, 0), (1, 1), (0, 2), (-1, 2), (-2, 2),
                     (-2, 1), (-2, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0), (0, 0)]
