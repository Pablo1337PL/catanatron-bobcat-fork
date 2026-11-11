import { expect, test } from "vitest";

import type { GameAction } from "./api.types";
import { NO_PLACES, actionPlaces, edgeKey } from "./highlight";

test.each([
  [["RED", "BUILD_SETTLEMENT", 7], { ...NO_PLACES, nodes: [7] }],
  [["RED", "BUILD_CITY", 7], { ...NO_PLACES, nodes: [7] }],
  [["RED", "BUILD_ROAD", [3, 7]], { ...NO_PLACES, edges: [[3, 7]] }],
  [["RED", "MOVE_ROBBER", [[1, -1, 0], "BLUE"]], { ...NO_PLACES, tiles: [[1, -1, 0]] }],
  [["RED", "ROLL", null], NO_PLACES],
  [["RED", "PLAY_KNIGHT_CARD", null], NO_PLACES],
  [["RED", "MARITIME_TRADE", ["WOOD", "WOOD", "WOOD", "WOOD", "ORE"]], NO_PLACES],
  [["RED", "END_TURN", null], NO_PLACES],
])("%j", (action, places) => {
  expect(actionPlaces(action as GameAction)).toEqual(places);
});

test("nothing pointed at", () => {
  expect(actionPlaces(null)).toEqual(NO_PLACES);
});

test("an edge is the same either way round", () => {
  expect(edgeKey([7, 3])).toBe(edgeKey([3, 7]));
});
