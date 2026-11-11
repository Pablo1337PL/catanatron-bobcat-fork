import type {
  ActionDetails,
  GameAction,
  Tile,
  PlacedTile,
  GameActionRecord,
  MaritimeTradeAction,
  BuildCityAction,
  BuildRoadAction,
  PlayYearOfPlentyAction,
  MoveRobberAction,
  ResourceCard,
} from "./api.types";
import type { GameState } from "./api.types";

export function humanizeActionRecord(
  gameState: GameState,
  actionRecord: GameActionRecord,
  details?: ActionDetails,
) {
  const botColors = gameState.bot_colors;
  const action = actionRecord[0];
  const player = botColors.includes(action[0]) ? "BOT" : "YOU";
  switch (actionRecord[0][1]) {
    case "ROLL": {
      const action = actionRecord[1] as [number, number];
      return `${player} ROLLED A ${action[0] + action[1]}`;
    }
    case "DISCARD_RESOURCE":
      return `${player} DISCARDED ${actionRecord[1] as ResourceCard}`;
    case "BUY_DEVELOPMENT_CARD": {
      // The card arrives for one's own purchases, and for the bot's only
      // once the game is over.
      const card = actionRecord[1];
      const drawn = card ? ` (${String(card).replaceAll("_", " ")})` : "";
      return `${player} BOUGHT DEVELOPMENT CARD${drawn}`;
    }
    case "BUILD_SETTLEMENT":
    case "BUILD_CITY": {
      const action = actionRecord[0] as BuildCityAction;
      const parts = action[1].split("_");
      const building = parts[parts.length - 1];
      return `${player} BUILT ${building} ON ${nodeLabel(gameState, action[2])}`;
    }
    case "BUILD_ROAD": {
      const action = actionRecord[0] as BuildRoadAction;
      return `${player} BUILT ROAD ON ${edgeLabel(gameState, action[2])}`;
    }
    case "PLAY_KNIGHT_CARD": {
      return `${player} PLAYED KNIGHT CARD`;
    }
    case "PLAY_ROAD_BUILDING": {
      return `${player} PLAYED ROAD BUILDING`;
    }
    case "PLAY_MONOPOLY": {
      const changes = details?.resource_changes;
      if (!changes) {
        return `${player} MONOPOLIZED ${action[2]}`;
      }
      const taken = changes[action[0]]?.[action[2] as ResourceCard] ?? 0;
      return `${player} MONOPOLIZED ${action[2]} (TOOK ${taken})`;
    }
    case "PLAY_YEAR_OF_PLENTY": {
      const action = actionRecord[0] as PlayYearOfPlentyAction;
      const firstResource = action[2][0];
      const secondResource = action[2][1];
      if (secondResource) {
        return `${player} PLAYED YEAR OF PLENTY. CLAIMED ${firstResource} AND ${secondResource}`;
      } else {
        return `${player} PLAYED YEAR OF PLENTY. CLAIMED ${firstResource}`;
      }
    }
    case "MOVE_ROBBER": {
      const action = actionRecord[0] as MoveRobberAction;
      const tileString = tileLabel(gameState, action[2][0]);
      const robbedResource = actionRecord[1];
      const stolenResource = robbedResource ? ` (STOLE ${robbedResource})` : "";
      return `${player} ROBBED ${tileString}${stolenResource}`;
    }
    case "MARITIME_TRADE": {
      const label = humanizeTradeAction(action as MaritimeTradeAction);
      return `${player} TRADED ${label}`;
    }
    case "END_TURN":
      return `${player} ENDED TURN`;
    default:
      throw new Error(`Unknown action type: ${action[1]}`);
  }
}
/** A hand change, e.g. "+2 WHEAT, +1 ORE". */
export function formatResourceChange(
  change: Partial<Record<ResourceCard, number>>,
): string {
  return Object.entries(change)
    .map(([resource, count]) => `${count > 0 ? "+" : ""}${count} ${resource}`)
    .join(", ");
}

/** How long a move took: "0.4 s", "12.3 s", "2:05", "1:02:05". */
export function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)} s`;
  }
  const total = Math.round(seconds);
  const pad = (n: number) => String(n).padStart(2, "0");
  const [h, m, s] = [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60];
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/**
 * Seconds the player spent on action `index`: since the action before it, or
 * since the game was created for the first one. null when a time is missing.
 */
export function moveDuration(gameState: GameState, index: number): number | null {
  const playedAt = gameState.action_details?.[index]?.played_at;
  const previous =
    index === 0
      ? gameState.created_at
      : gameState.action_details?.[index - 1]?.played_at;
  if (playedAt == null || previous == null) {
    return null;
  }
  return Math.max(0, playedAt - previous);
}

/**
 * A node by its board name and the numbers around it, e.g. "D·S (8-10-5)":
 * the name is unique, the numbers are quick to spot. The numbers follow the
 * tiles' letters. An older server sends no names: just the numbers.
 */
export function nodeLabel(gameState: GameState, nodeId: number): string {
  const tiles = byLetter(gameState, gameState.adjacent_tiles[nodeId]);
  const numbers = tiles.map(getShortTileString).join("-");
  const label = gameState.nodes?.[nodeId]?.label;
  return label ? `${label} (${numbers})` : numbers;
}

/** An edge, e.g. "D·E (8-4)"; the numbers are the tiles on both sides. */
export function edgeLabel(gameState: GameState, edge: [number, number]): string {
  const a = gameState.adjacent_tiles[edge[0]].flatMap((tile) =>
    "id" in tile ? [tile.id] : []
  );
  const b = gameState.adjacent_tiles[edge[1]].flatMap((tile) =>
    "id" in tile ? [tile.id] : []
  );
  const intersection = a.filter((t) => b.includes(t));
  const tiles = byLetter(
    gameState,
    intersection.map((tileId) => findTileById(gameState, tileId).tile),
  );
  const numbers = tiles.map(getShortTileString).join("-");
  const label = gameState.edges?.find(
    (e) => e.id[0] === Math.min(...edge) && e.id[1] === Math.max(...edge),
  )?.label;
  return label ? `${label} (${numbers})` : numbers;
}

/** A tile, e.g. "K (10 ORE)" or "B (DESERT)"; "10 ORE" from an older server. */
export function tileLabel(gameState: GameState, coordinate: unknown): string {
  const placed = findTileByCoordinate(gameState, coordinate);
  if (!placed.label) {
    return getTileString(placed);
  }
  const tile = placed.tile;
  const what = tile.type === "DESERT" ? "DESERT" : getTileString(placed);
  return `${placed.label} (${what})`;
}

/** Land tiles in the order of their letters (unchanged without letters). */
function byLetter(gameState: GameState, tiles: Tile[]): Tile[] {
  const letters = new Map<number, string>();
  for (const placed of gameState.tiles) {
    if (placed.label && "id" in placed.tile) {
      letters.set(placed.tile.id, placed.label);
    }
  }
  const letter = (tile: Tile) => ("id" in tile ? letters.get(tile.id) : undefined) ?? "";
  return [...tiles].sort((x, y) => letter(x).localeCompare(letter(y)));
}

/**
 * A short label for an action that has not happened yet (analysis lines),
 * without its player or outcome, e.g. "Road D·E (8-4)" or
 * "Robber K (10 ORE), steal BLUE".
 */
export function describeAction(gameState: GameState, action: GameAction): string {
  switch (action[1]) {
    case "ROLL":
      return "Roll";
    case "DISCARD_RESOURCE":
      return action[2] ? `Discard ${action[2]}` : "Discard";
    case "BUY_DEVELOPMENT_CARD":
      return "Buy development card";
    case "BUILD_SETTLEMENT":
      return `Settlement ${nodeLabel(gameState, action[2])}`;
    case "BUILD_CITY":
      return `City ${nodeLabel(gameState, action[2])}`;
    case "BUILD_ROAD":
      return `Road ${edgeLabel(gameState, action[2])}`;
    case "PLAY_KNIGHT_CARD":
      return "Knight";
    case "PLAY_ROAD_BUILDING":
      return "Road Building";
    case "PLAY_MONOPOLY":
      return `Monopoly ${action[2]}`;
    case "PLAY_YEAR_OF_PLENTY":
      return `Year of Plenty ${action[2].join(" + ")}`;
    case "MOVE_ROBBER": {
      const tile = tileLabel(gameState, action[2][0]);
      const victim = action[2][1];
      return victim ? `Robber ${tile}, steal ${victim}` : `Robber ${tile}`;
    }
    case "MARITIME_TRADE":
      return `Trade ${humanizeTradeAction(action)}`;
    case "END_TURN":
      return "End turn";
    default:
      throw new Error(`Unknown action type: ${(action as GameAction)[1]}`);
  }
}

export function humanizeTradeAction(action: MaritimeTradeAction): string {
  const out = action[2]
    .slice(0, 4)
    .filter((resource: unknown) => resource !== null);
  return `${out.length} ${out[0]} => ${action[2][4]}`;
}

export function findTileByCoordinate(gameState: GameState, coordinate: any) {
  for (const tile of Object.values(gameState.tiles)) {
    if (JSON.stringify(tile.coordinate) === JSON.stringify(coordinate)) {
      return tile;
    }
  }
  throw new Error(
    `Tile not found for coordinate: ${JSON.stringify(coordinate)}`,
  );
}

export function getShortTileString(tile: Tile): string {
  return tile.type === "RESOURCE_TILE" ? tile.number.toString() : tile.type;
}

export function getTileString(tile: PlacedTile): string {
  const tileInfo = tile.tile;
  switch (tileInfo.type) {
    case "DESERT":
      return "THE DESERT";
    case "RESOURCE_TILE":
      return `${tileInfo.number} ${tileInfo.resource}`;
    default:
      throw new Error("getTileString() only works on Desert or Resource tiles");
  }
}

export function findTileById(gameState: GameState, tileId: number): PlacedTile {
  return gameState.tiles[tileId];
}
