import axios from "axios";
import { enqueueSnackbar } from "notistack";

import { API_URL } from "../configuration";
import type { Color, GameAction, GameState } from "./api.types";

/** A registry key, e.g. "CATANATRON" or "AB". The server decides what exists. */
export type PlayerKey = string;

/** One settable parameter, as published by GET /api/players. */
export type PlayerParam = {
  name: string;
  type: "int" | "float" | "str" | "bool";
  default: number | string | boolean | null;
  /** Only present when the param declares a fixed set of values. */
  choices?: Array<string | number>;
  help: string;
};

export type PlayerEntry = {
  key: PlayerKey;
  name: string;
  description: string;
  is_bot: boolean;
  source: string;
  params: PlayerParam[];
};

export type MapTemplate = "BASE" | "MINI" | "TOURNAMENT";
export type StateIndex = number | `${number}` | "latest";

/** Seeds of a new game; null (or missing) means random. */
export type GameSeeds = {
  seed?: number | null;
  boardSeed?: number | null;
  diceSeed?: number | null;
};

type CreateGameOptions = {
  players: PlayerKey[];
  mapTemplate: MapTemplate;
  vpsToWin: number;
  discardLimit: number;
  friendlyRobber: boolean;
  /** false: seats follow `players` (Player 1 places first and starts). */
  randomSeats?: boolean;
  seeds?: GameSeeds;
};

/** The players this server can seat. Replaces a hardcoded list in the UI. */
export async function getPlayers(): Promise<PlayerEntry[]> {
  const response = await axios.get<PlayerEntry[]>(API_URL + "/api/players");
  return response.data;
}

export async function createGame({
  players,
  mapTemplate,
  vpsToWin,
  discardLimit,
  friendlyRobber,
  randomSeats = false,
  seeds = {},
}: CreateGameOptions) {
  // Only seeds that were given: a missing one lets the server choose (its
  // configured default, else random).
  const seedFields = Object.fromEntries(
    [
      ["seed", seeds.seed],
      ["board_seed", seeds.boardSeed],
      ["dice_seed", seeds.diceSeed],
    ].filter(([, value]) => value !== null && value !== undefined)
  );
  const response = await axios.post(API_URL + "/api/games", {
    players,
    map_template: mapTemplate,
    vps_to_win: vpsToWin,
    discard_limit: discardLimit,
    friendly_robber: friendlyRobber,
    random_seats: randomSeats,
    ...seedFields,
  });
  return response.data.game_id;
}

/**
 * Whose eyes the server renders state through. A seat sees the other hands as
 * counts rather than cards; null watches as a spectator, every hand face up.
 *
 * It lives here rather than as an argument because every request carries it,
 * and a call site that forgot would silently show the whole table again.
 */
let perspective: Color | null = null;

export function setPerspective(color: Color | null) {
  perspective = color;
}

function viewParams() {
  return perspective ? { as: perspective } : {};
}

export async function getState(
  gameId: string,
  stateIndex: StateIndex = "latest"
): Promise<GameState> {
  const response = await axios.get(
    `${API_URL}/api/games/${gameId}/states/${stateIndex}`,
    { params: viewParams() }
  );
  return response.data;
}

/**
 * action=undefined means bot action.
 *
 * An action the game cannot take is answered with a 400 and leaves the game
 * as it was: show the server's message and carry on from the current state.
 */
export async function postAction(gameId: string, action?: GameAction) {
  try {
    const response = await axios.post<GameState>(
      `${API_URL}/api/games/${gameId}/actions`,
      action,
      { params: viewParams() }
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 400) {
      const body = error.response.data as { message?: string } | undefined;
      enqueueSnackbar(body?.message ?? "Action not allowed", {
        variant: "warning",
      });
      return getState(gameId);
    }
    throw error;
  }
}

/** One legal action of the analyzed position, as GET .../analysis returns it. */
export type AnalysisMove = {
  action: GameAction;
  /** The engine's choice, e.g. MCTS visit share; all moves sum to 1. */
  probability: number;
  /** The policy before searching, or null. */
  prior: number | null;
  visits: number;
  /** After this move; null when the engine never tried it. */
  win_probability: Partial<Record<Color, number>> | null;
  /** The expected continuation, starting with this move. */
  line: GameAction[];
  /** Why the line stops; null when it reached the engine's depth. */
  line_end: "chance" | "terminal" | "unexplored" | null;
};

/** The server engine's view of one position (create_app(analyzer=...)). */
export type Analysis = {
  engine: string | null;
  player: Color | null;
  win_probability: Partial<Record<Color, number>>;
  simulations: number;
  seconds: number;
  moves: AnalysisMove[];
  state_index: number;
};

/** Analyzes a position; throws an Error with the server's message on failure. */
export async function getAnalysis(
  gameId: string,
  stateIndex: StateIndex = "latest"
): Promise<Analysis> {
  try {
    const response = await axios.get<Analysis>(
      `${API_URL}/api/games/${gameId}/states/${stateIndex}/analysis`
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const body = error.response?.data as { message?: string } | undefined;
      if (error.response?.status === 501) {
        throw new Error("This server has no analysis engine.");
      }
      if (body?.message) {
        throw new Error(body.message);
      }
    }
    throw error;
  }
}
