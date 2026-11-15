import type { Color, GameState } from "./api.types";

export function isPlayersTurn(gameState: GameState): boolean {
  return !gameState.bot_colors.includes(gameState.current_color);
}

export function playerKey(gameState: GameState, color: Color): string {
  return `P${gameState.colors.indexOf(color)}`;
}

export function getHumanColor(gameState: GameState): Color {
  if (!gameState.bot_colors.includes(gameState.current_color)) {
    return gameState.current_color;
  }
  return gameState.colors.find(
    (color) => !gameState.bot_colors.includes(color)
  ) as Color;
}
