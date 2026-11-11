import type { GameAction, TileCoordinate } from "./api.types";

/** Where an action happens on the board; empty for rolls, trades, cards... */
export type Places = {
  nodes: number[];
  edges: [number, number][];
  tiles: TileCoordinate[];
};

export const NO_PLACES: Places = { nodes: [], edges: [], tiles: [] };

export function actionPlaces(action: GameAction | null | undefined): Places {
  if (!action) {
    return NO_PLACES;
  }
  switch (action[1]) {
    case "BUILD_SETTLEMENT":
    case "BUILD_CITY":
      return { ...NO_PLACES, nodes: [action[2]] };
    case "BUILD_ROAD":
      return { ...NO_PLACES, edges: [action[2]] };
    case "MOVE_ROBBER":
      return { ...NO_PLACES, tiles: [action[2][0]] };
    default:
      return NO_PLACES;
  }
}

export const edgeKey = (edge: [number, number]) =>
  `${Math.min(...edge)},${Math.max(...edge)}`;
