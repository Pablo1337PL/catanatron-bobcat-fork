"""Unambiguous names for the places on the board.

The engine knows places by number (nodes 0-53, edges as node pairs, tiles by
cube coordinate); the UI used to describe them by the numbers on the
surrounding tiles ("City 10-5-8"), which repeat. This module names them the
way a chess board does:

* **Tiles** get the letters A-S in reading order, row by row (cube ``z``) and
  left to right (cube ``x``)::

          A B C
         D E F G
        H I J K L
         M N O P
          Q R S

  The centre ``(0, 0, 0)`` is always J. Letters name places, not resources,
  so they do not depend on the board seed.
* **Nodes** are a tile and a corner (``N, NE, SE, S, SW, NW``): ``D·S``.
* **Edges** are a tile and a side (``NE, E, SE, SW, W, NW``): ``D·E``.

A node or edge touches up to three (two) land tiles; its canonical name uses
the one with the earliest letter. Any name of the place parses back to it
(``H·NE`` is the same node as ``D·S``). Water-only nodes and edges have no
name: nothing can be built there.
"""

import re
from typing import Dict, Tuple

from catanatron.models.coordinate_system import Coordinate
from catanatron.models.enums import EdgeRef, NodeRef

SEPARATOR = "·"
LETTERS = "ABCDEFGHIJKLMNOPQRS"

CORNERS = {
    NodeRef.NORTH: "N",
    NodeRef.NORTHEAST: "NE",
    NodeRef.SOUTHEAST: "SE",
    NodeRef.SOUTH: "S",
    NodeRef.SOUTHWEST: "SW",
    NodeRef.NORTHWEST: "NW",
}
SIDES = {
    EdgeRef.NORTHEAST: "NE",
    EdgeRef.EAST: "E",
    EdgeRef.SOUTHEAST: "SE",
    EdgeRef.SOUTHWEST: "SW",
    EdgeRef.WEST: "W",
    EdgeRef.NORTHWEST: "NW",
}

Edge = Tuple[int, int]

# A tile letter, an optional separator (·, -, / or a space) and a corner/side.
_PLACE = re.compile(r"^\s*([A-Za-z])\s*[·\-/]?\s*([A-Za-z]{1,2})\s*$")


class BoardNames:
    """Names of every land tile, node and edge of one board topology."""

    def __init__(self, land_tiles):
        coordinates = sorted(land_tiles, key=lambda c: (c[2], c[0]))
        if len(coordinates) != len(LETTERS):
            raise ValueError(
                f"Board names need {len(LETTERS)} land tiles, got {len(coordinates)}"
            )
        self.tiles: Dict[Coordinate, str] = dict(zip(coordinates, LETTERS))
        self.coordinates: Dict[str, Coordinate] = {
            letter: coordinate for coordinate, letter in self.tiles.items()
        }
        self.nodes: Dict[int, str] = {}
        self.edges: Dict[Edge, str] = {}
        self._node_refs: Dict[Tuple[str, str], int] = {}
        self._edge_refs: Dict[Tuple[str, str], Edge] = {}
        # Earliest letter first, so the first name given to a place is canonical
        for coordinate in coordinates:
            letter = self.tiles[coordinate]
            tile = land_tiles[coordinate]
            for ref, node_id in tile.nodes.items():
                self._node_refs[(letter, CORNERS[ref])] = node_id
                self.nodes.setdefault(node_id, letter + SEPARATOR + CORNERS[ref])
            for ref, edge in tile.edges.items():
                edge = tuple(sorted(edge))
                self._edge_refs[(letter, SIDES[ref])] = edge
                self.edges.setdefault(edge, letter + SEPARATOR + SIDES[ref])

    def parse_tile(self, text: str) -> Coordinate:
        """``"K"`` -> the cube coordinate of tile K."""
        letter = text.strip().upper()
        if letter not in self.coordinates:
            raise ValueError(f"'{text}' is not a tile: use a letter A-S")
        return self.coordinates[letter]

    def parse_node(self, text: str) -> int:
        """``"D·S"`` (or ``D-S``, ``D/S``, ``ds``...) -> node id."""
        letter, corner = self._split(text, "node", set(CORNERS.values()))
        return self._node_refs[(letter, corner)]

    def parse_edge(self, text: str) -> Edge:
        """``"D·E"`` (or ``D-E``, ``D/E``, ``de``...) -> (node, node), sorted."""
        letter, side = self._split(text, "edge", set(SIDES.values()))
        return self._edge_refs[(letter, side)]

    def _split(self, text: str, kind: str, refs) -> Tuple[str, str]:
        match = _PLACE.match(text)
        if match is None:
            raise ValueError(
                f"'{text}' is not a {kind} name: use a tile letter and "
                f"{'a corner' if kind == 'node' else 'a side'}, e.g. D{SEPARATOR}"
                f"{'S' if kind == 'node' else 'E'}"
            )
        letter, ref = match.group(1).upper(), match.group(2).upper()
        if letter not in self.coordinates:
            raise ValueError(f"'{text}': '{letter}' is not a tile, use A-S")
        if ref not in refs:
            raise ValueError(
                f"'{text}': '{ref}' is not a {'corner' if kind == 'node' else 'side'}"
                f" ({', '.join(sorted(refs))})"
            )
        return letter, ref


_cache: Dict[tuple, BoardNames] = {}


def board_names(catan_map) -> BoardNames:
    """Names for ``catan_map``; cached per topology (BASE and TOURNAMENT share one)."""
    topology = tuple(
        sorted(
            (coordinate, tuple(sorted((ref.value, n) for ref, n in tile.nodes.items())))
            for coordinate, tile in catan_map.land_tiles.items()
        )
    )
    names = _cache.get(topology)
    if names is None:
        names = _cache[topology] = BoardNames(catan_map.land_tiles)
    return names
