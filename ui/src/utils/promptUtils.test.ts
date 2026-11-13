import { describe, test, expect } from "vitest";
import {
  getTileString,
  getShortTileString,
  findTileById,
  findTileByCoordinate,
  describeAction,
  edgeLabel,
  formatDuration,
  formatResourceChange,
  humanizeActionRecord,
  humanizeTradeAction,
  moveDuration,
  nodeLabel,
  tileLabel,
} from "./promptUtils";
import { makeGameState } from "../test/fixtures";
import type { GameState, GameAction, GameActionRecord } from "./api.types";

describe("getTileString", () => {
  test("Resource", () => {
    expect(
      getTileString({
        coordinate: [0, 0, 0],
        tile: {
          id: 0,
          type: "RESOURCE_TILE",
          resource: "BRICK",
          number: 6,
        },
      })
    ).toEqual("6 BRICK");
  });
  test("Desert", () => {
    expect(
      getTileString({
        coordinate: [1, 1, 1],
        tile: {
          id: 1,
          type: "DESERT",
        },
      })
    ).toEqual("THE DESERT");
  });
  test("Other", () => {
    expect(() =>
      getTileString({
        coordinate: [0, 0, 1],
        tile: {
          id: 2,
          type: "PORT",
          resource: "WHEAT",
          direction: "NORTHEAST",
        },
      })
    ).toThrowError("getTileString() only works on Desert or Resource tiles");
  });
});

describe("getShortTileString", () => {
  test("Resource", () => {
    expect(
      getShortTileString({
        id: 0,
        type: "RESOURCE_TILE",
        resource: "BRICK",
        number: 6,
      })
    ).toEqual("6");
  });
  test("Desert", () => {
    expect(
      getShortTileString({
        id: 1,
        type: "DESERT",
      })
    ).toEqual("DESERT");
  });
  test("Port", () => {
    expect(
      getShortTileString({
        id: 2,
        type: "PORT",
        resource: "WHEAT",
        direction: "NORTHEAST",
      })
    ).toEqual("PORT");
  });
});

describe("findTileById", () => {
  const gameState = {
    tiles: [
      {
        coordinate: [0, 0, 0],
        tile: {
          id: 0,
          type: "RESOURCE_TILE",
          resource: "BRICK",
          number: 6,
        },
      },
    ],
  };
  const expected = gameState.tiles[0];
  test("found", () => {
    expect(findTileById(gameState as GameState, 0)).toEqual(expected);
  });
  test("not found", () => {
    expect(findTileById(gameState as GameState, 1)).toBeUndefined();
  });
});

describe("findTileByCoordinate", () => {
  const gameState = {
    tiles: [
      {
        coordinate: [0, 0, 0],
        tile: {
          id: 0,
          type: "RESOURCE_TILE",
          resource: "BRICK",
          number: 6,
        },
      },
    ],
  };
  const expected = gameState.tiles[0];
  test("found", () => {
    expect(findTileByCoordinate(gameState as GameState, [0, 0, 0])).toEqual(
      expected
    );
  });
  test("not found", () => {
    expect(() =>
      findTileByCoordinate(gameState as GameState, [0, 0, 1])
    ).toThrowError("Tile not found for coordinate: [0,0,1]");
  });
});

describe("humanizeAction", () => {
  const baseGameState = {
    bot_colors: ["RED", "BLUE"],
    adjacent_tiles: {
      0: [
        { id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 },
        { id: 1, type: "DESERT" },
      ],
      1: [
        { id: 1, type: "DESERT" },
        { id: 2, type: "RESOURCE_TILE", resource: "WHEAT", number: 8 },
      ],
      2: [
        { id: 2, type: "RESOURCE_TILE", resource: "WHEAT", number: 8 },
        { id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 },
      ],
      A: [
        { id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 },
        { id: 1, type: "DESERT" },
      ],
      B: [
        { id: 1, type: "DESERT" },
        { id: 2, type: "RESOURCE_TILE", resource: "WHEAT", number: 8 },
      ],
    },
    tiles: [
      {
        coordinate: [0, 0, 0],
        tile: { id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 },
      },
      { coordinate: [1, 1, 1], tile: { id: 1, type: "DESERT" } },
      {
        coordinate: [2, 2, 2],
        tile: { id: 2, type: "RESOURCE_TILE", resource: "WHEAT", number: 8 },
      },
    ],
  } as unknown as GameState;

  test("ROLL action", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["RED", "ROLL", null],
        [3, 4],
      ])
    ).toBe("BOT ROLLED A 7");
  });

  test("DISCARD_RESOURCE action", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["ORANGE", "DISCARD_RESOURCE", "WHEAT"],
        "WHEAT",
      ])
    ).toBe("YOU DISCARDED WHEAT");
  });

  test("BUY_DEVELOPMENT_CARD action", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["BLUE", "BUY_DEVELOPMENT_CARD", null],
        "YEAR_OF_PLENTY",
      ])
    ).toBe("BOT BOUGHT DEVELOPMENT CARD (YEAR OF PLENTY)");
    // A face-down purchase comes without the card.
    expect(
      humanizeActionRecord(baseGameState, [
        ["BLUE", "BUY_DEVELOPMENT_CARD", null],
        null,
      ])
    ).toBe("BOT BOUGHT DEVELOPMENT CARD");
  });

  test("BUILD_SETTLEMENT action", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["RED", "BUILD_SETTLEMENT", 0],
        null,
      ])
    ).toBe("BOT BUILT SETTLEMENT ON 6-DESERT");
  });

  test("BUILD_CITY action", () => {
    expect(
      humanizeActionRecord(baseGameState, [["ORANGE", "BUILD_CITY", 1], null])
    ).toBe("YOU BUILT CITY ON DESERT-8");
  });

  test("BUILD_ROAD action", () => {
    expect(
      humanizeActionRecord(baseGameState, [["RED", "BUILD_ROAD", [0, 0]], null])
    ).toBe("BOT BUILT ROAD ON 6-DESERT");
  });

  test("PLAY_KNIGHT_CARD action", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["BLUE", "PLAY_KNIGHT_CARD", null],
        null,
      ])
    ).toBe("BOT PLAYED KNIGHT CARD");
  });

  test("PLAY_ROAD_BUILDING action", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["ORANGE", "PLAY_ROAD_BUILDING", null],
        null,
      ])
    ).toBe("YOU PLAYED ROAD BUILDING");
  });

  test("PLAY_MONOPOLY action", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["RED", "PLAY_MONOPOLY", "BRICK"],
        null,
      ])
    ).toBe("BOT MONOPOLIZED BRICK");
  });

  test("PLAY_MONOPOLY action says how many cards it took", () => {
    const details = {
      played_at: 10,
      resource_changes: { RED: { BRICK: 4 }, BLUE: { BRICK: -4 } },
    };
    expect(
      humanizeActionRecord(
        baseGameState,
        [["RED", "PLAY_MONOPOLY", "BRICK"], null],
        details
      )
    ).toBe("BOT MONOPOLIZED BRICK (TOOK 4)");
    expect(
      humanizeActionRecord(
        baseGameState,
        [["RED", "PLAY_MONOPOLY", "BRICK"], null],
        { played_at: 10, resource_changes: {} }
      )
    ).toBe("BOT MONOPOLIZED BRICK (TOOK 0)");
  });

  test("PLAY_YEAR_OF_PLENTY action with two resources", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["ORANGE", "PLAY_YEAR_OF_PLENTY", ["BRICK", "WHEAT"]],
        null,
      ])
    ).toBe("YOU PLAYED YEAR OF PLENTY. CLAIMED BRICK AND WHEAT");
  });

  test("PLAY_YEAR_OF_PLENTY action with one resource", () => {
    expect(
      humanizeActionRecord(baseGameState, [
        ["ORANGE", "PLAY_YEAR_OF_PLENTY", ["BRICK"]],
        null,
      ])
    ).toBe("YOU PLAYED YEAR OF PLENTY. CLAIMED BRICK");
  });

  test("MOVE_ROBBER action with stolen resource", () => {
    const actionRecord: GameActionRecord = [
      ["RED", "MOVE_ROBBER", [[0, 0, 0], "BLUE"]],
      "BRICK",
    ];
    expect(humanizeActionRecord(baseGameState, actionRecord)).toBe(
      "BOT ROBBED 6 BRICK (STOLE BRICK)"
    );
  });

  test("MOVE_ROBBER action without stolen resource", () => {
    const actionRecord: GameActionRecord = [
      ["RED", "MOVE_ROBBER", [[0, 0, 0], undefined]],
      null,
    ];
    expect(humanizeActionRecord(baseGameState, actionRecord)).toBe(
      "BOT ROBBED 6 BRICK"
    );
  });

  test("MARITIME_TRADE action", () => {
    const actionRecord: GameActionRecord = [
      ["ORANGE", "MARITIME_TRADE", ["BRICK", "BRICK", "BRICK", null, "WHEAT"]],
      null,
    ];
    expect(humanizeActionRecord(baseGameState, actionRecord)).toBe(
      "YOU TRADED 3 BRICK => WHEAT"
    );
  });

  test("END_TURN action", () => {
    expect(
      humanizeActionRecord(baseGameState, [["RED", "END_TURN", null], null])
    ).toBe("BOT ENDED TURN");
  });

  test("Unknown action type throws", () => {
    expect(() =>
      humanizeActionRecord(baseGameState, [
        [
          "RED",
          // @ts-expect-error
          "UNKNOWN_ACTION",
        ],
        null,
      ])
    ).toThrowError("Unknown action type: UNKNOWN_ACTION");
  });
});

describe("humanizeTradeAction", () => {
  test("returns correct string for 3:1 trade", () => {
    const action: GameAction = [
      "RED",
      "MARITIME_TRADE",
      ["BRICK", "BRICK", "BRICK", null, "WHEAT"],
    ];
    expect(humanizeTradeAction(action)).toBe("3 BRICK => WHEAT");
  });

  test("returns correct string for 2:1 trade", () => {
    const action: GameAction = [
      "RED",
      "MARITIME_TRADE",
      ["WHEAT", "WHEAT", null, null, "BRICK"],
    ];
    expect(humanizeTradeAction(action)).toBe("2 WHEAT => BRICK");
  });

  test("returns correct string for 4:1 trade", () => {
    const action: GameAction = [
      "RED",
      "MARITIME_TRADE",
      ["ORE", "ORE", "ORE", "ORE", "WOOD"],
    ];
    expect(humanizeTradeAction(action)).toBe("4 ORE => WOOD");
  });

  test("returns correct string for 1:1 trade", () => {
    const action: GameAction = [
      "RED",
      "MARITIME_TRADE",
      ["BRICK", null, null, null, "ORE"],
    ];
    expect(humanizeTradeAction(action)).toBe("1 BRICK => ORE");
  });
});

describe("describeAction", () => {
  const gameState = {
    tiles: [
      {
        coordinate: [0, 0, 0],
        tile: { id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 },
      },
      { coordinate: [1, -1, 0], tile: { id: 1, type: "DESERT" } },
    ],
    adjacent_tiles: {
      0: [
        { id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 },
        { id: 1, type: "DESERT" },
      ],
      1: [{ id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 }],
    },
  } as unknown as GameState;

  test.each([
    [["RED", "ROLL", null], "Roll"],
    [["RED", "END_TURN", null], "End turn"],
    [["RED", "BUILD_SETTLEMENT", 0], "Settlement 6-DESERT"],
    [["RED", "BUILD_CITY", 0], "City 6-DESERT"],
    [["RED", "BUILD_ROAD", [0, 1]], "Road 6"],
    [["RED", "PLAY_MONOPOLY", "ORE"], "Monopoly ORE"],
    [["RED", "PLAY_YEAR_OF_PLENTY", ["WOOD", "ORE"]], "Year of Plenty WOOD + ORE"],
    [["RED", "MOVE_ROBBER", [[0, 0, 0], "BLUE"]], "Robber 6 BRICK, steal BLUE"],
    [["RED", "MOVE_ROBBER", [[1, -1, 0]]], "Robber THE DESERT"],
    [
      ["RED", "MARITIME_TRADE", ["WOOD", "WOOD", "WOOD", "WOOD", "ORE"]],
      "Trade 4 WOOD => ORE",
    ],
  ])("%j", (action, expected) => {
    expect(describeAction(gameState, action as GameAction)).toEqual(expected);
  });
});

describe("move times and hand changes", () => {
  test("formatResourceChange", () => {
    expect(formatResourceChange({ WHEAT: 2, ORE: 1 })).toBe("+2 WHEAT, +1 ORE");
    expect(formatResourceChange({ BRICK: -3 })).toBe("-3 BRICK");
  });

  test.each([
    [0.42, "0.4 s"],
    [12.34, "12.3 s"],
    [125, "2:05"],
    [3725, "1:02:05"],
  ])("formatDuration(%s)", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });

  test("moveDuration counts from the move before, or from the start", () => {
    const state = makeGameState({
      created_at: 100,
      action_details: [
        { played_at: 103.5, resource_changes: null },
        { played_at: 110, resource_changes: null },
        { played_at: null, resource_changes: null },
        { played_at: 120, resource_changes: null },
      ],
    });
    expect(moveDuration(state, 0)).toBe(3.5);
    expect(moveDuration(state, 1)).toBe(6.5);
    expect(moveDuration(state, 2)).toBeNull();
    expect(moveDuration(state, 3)).toBeNull();
    expect(moveDuration(makeGameState(), 0)).toBeNull();
  });
});

describe("board names", () => {
  const ore = { id: 2, type: "RESOURCE_TILE", resource: "ORE", number: 10 };
  const brick = { id: 0, type: "RESOURCE_TILE", resource: "BRICK", number: 6 };
  const desert = { id: 1, type: "DESERT" };
  const gameState = {
    bot_colors: ["BLUE"],
    tiles: [
      { coordinate: [0, 0, 0], tile: brick, label: "A" },
      { coordinate: [1, -1, 0], tile: desert, label: "B" },
      { coordinate: [2, -2, 0], tile: ore, label: "K" },
    ],
    adjacent_tiles: {
      0: [ore, brick],
      1: [brick, ore],
      2: [brick, desert],
    },
    nodes: {
      0: { id: 0, label: "A·S" },
      1: { id: 1, label: "K·NW" },
      2: { id: 2, label: "B·N" },
    },
    edges: [{ id: [0, 1], label: "A·E" }],
  } as unknown as GameState;

  test("two nodes with the same numbers get different names", () => {
    expect(nodeLabel(gameState, 0)).toBe("A·S (6-10)");
    expect(nodeLabel(gameState, 1)).toBe("K·NW (6-10)");
    expect(nodeLabel(gameState, 2)).toBe("B·N (6-DESERT)");
  });

  test("edges and tiles", () => {
    expect(edgeLabel(gameState, [1, 0])).toBe("A·E (6-10)");
    expect(tileLabel(gameState, [2, -2, 0])).toBe("K (10 ORE)");
    expect(tileLabel(gameState, [1, -1, 0])).toBe("B (DESERT)");
  });

  test("history and analysis use the names", () => {
    const city = [["BLUE", "BUILD_CITY", 1], null] as GameActionRecord;
    expect(humanizeActionRecord(gameState, city)).toBe("BOT BUILT CITY ON K·NW (6-10)");
    const robber = [["RED", "MOVE_ROBBER", [[2, -2, 0], "BLUE"]], "ORE"] as GameActionRecord;
    expect(humanizeActionRecord(gameState, robber)).toBe("YOU ROBBED K (10 ORE) (STOLE ORE)");
    expect(describeAction(gameState, ["RED", "BUILD_ROAD", [0, 1]] as GameAction)).toBe(
      "Road A·E (6-10)",
    );
    expect(
      describeAction(gameState, ["RED", "MOVE_ROBBER", [[2, -2, 0], "BLUE"]] as GameAction),
    ).toBe("Robber K (10 ORE), steal BLUE");
  });

  test("an older server without names keeps the numbers", () => {
    const old = { ...gameState, tiles: gameState.tiles.map(({ label: _, ...t }) => t), nodes: {}, edges: [] };
    expect(nodeLabel(old as GameState, 0)).toBe("10-6");
    expect(tileLabel(old as GameState, [2, -2, 0])).toBe("10 ORE");
  });
});

describe("who made the move", () => {
  const record = [["BLUE", "END_TURN", null], null] as GameActionRecord;

  test("a bot by its name, a human as YOU", () => {
    const gameState = {
      bot_colors: ["BLUE"],
      player_names: { RED: "Human", BLUE: "Bobcat" },
    } as unknown as GameState;
    expect(humanizeActionRecord(gameState, record)).toBe("BOBCAT ENDED TURN");
    const human = [["RED", "END_TURN", null], null] as GameActionRecord;
    expect(humanizeActionRecord(gameState, human)).toBe("YOU ENDED TURN");
  });

  test("BOT from an older server without names", () => {
    const gameState = { bot_colors: ["BLUE"] } as unknown as GameState;
    expect(humanizeActionRecord(gameState, record)).toBe("BOT ENDED TURN");
  });
});
