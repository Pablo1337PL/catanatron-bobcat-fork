import React, { useContext, useState } from "react";
import { Tooltip } from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import { enqueueSnackbar } from "notistack";

import { store, type SandboxTool } from "../store";
import ACTIONS from "../actions";
import {
  branchGame,
  editGame,
  exportGame,
  importGame,
  postAction,
  setForcedRandom,
} from "../utils/apiClient";
import { playerKey } from "../utils/stateUtils";
import type { Color, DevelopmentCard, ResourceCard } from "../utils/api.types";

import "./SandboxPanel.scss";

const RESOURCES: ResourceCard[] = ["WOOD", "BRICK", "SHEEP", "WHEAT", "ORE"];
const DEV_CARDS: (DevelopmentCard | "VICTORY_POINT")[] = [
  "KNIGHT",
  "YEAR_OF_PLENTY",
  "MONOPOLY",
  "ROAD_BUILDING",
  "VICTORY_POINT",
];
const DICE_SUMS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

export default function SandboxPanel() {
  const { gameId } = useParams();
  const navigate = useNavigate();
  const { state, dispatch } = useContext(store);
  const [editColor, setEditColor] = useState<Color>("RED");
  const [expandedSetup, setExpandedSetup] = useState(false);

  const gameState = state.gameState;
  if (!gameState || !gameId) {
    return null;
  }

  const activeTool = state.sandboxTool;
  const setTool = (tool: SandboxTool | null) => {
    dispatch({
      type: ACTIONS.SET_SANDBOX_TOOL,
      data:
        JSON.stringify(activeTool) === JSON.stringify(tool) ? null : tool,
    });
  };

  const updateForced = (patch: {
    dice?: number | null;
    dev_card?: string | null;
    robber_resource?: string | null;
  }) => {
    setForcedRandom(patch);
    dispatch({ type: ACTIONS.SET_FORCED_RANDOM, data: patch });
  };

  const handleUndo = async () => {
    const updated =
      state.viewedState !== null
        ? await branchGame(gameId, state.viewedState.state_index, {
            inPlace: true,
            playBothSides: true,
          })
        : await branchGame(gameId, "latest", {
            undo: true,
            inPlace: true,
            playBothSides: true,
          });
    dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
    dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
  };

  const handleBranchNewGame = async () => {
    const targetIdx =
      state.viewedState !== null
        ? state.viewedState.state_index
        : gameState.state_index;
    const branched = await branchGame(gameId, targetIdx, {
      inPlace: false,
      playBothSides: true,
    });
    dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
    dispatch({ type: ACTIONS.SET_GAME_STATE, data: branched });
    enqueueSnackbar(`Branched variation at move ${targetIdx}`, {
      variant: "info",
    });
    navigate(`/games/${branched.game.id}`);
  };

  const handleBotMove = async () => {
    const updated = await postAction(gameId);
    dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
  };

  const handleTogglePlayBothSides = async () => {
    const bothHumans = gameState.bot_colors.length === 0;
    const nextPlayers = bothHumans ? ["HUMAN", "BOBCAT"] : ["HUMAN", "HUMAN"];
    const updated = await editGame(gameId, {
      op: "set_players",
      players: nextPlayers,
    });
    dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
  };

  const handleExport = async () => {
    const idx = state.viewedState?.state_index ?? "latest";
    const doc = await exportGame(gameId, idx);
    const blob = new Blob([JSON.stringify(doc, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `catan-${gameId.slice(0, 8)}-move-${gameState.state_index}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const doc = JSON.parse(text);
      const newId = await importGame(doc, true);
      enqueueSnackbar("Game loaded into Sandbox!", { variant: "success" });
      navigate(`/games/${newId}`);
    } catch (err: any) {
      enqueueSnackbar(err?.message ?? "Failed to import JSON", {
        variant: "error",
      });
    }
  };

  const adjustCard = async (
    color: Color,
    kind: "resources" | "dev_cards",
    card: string,
    delta: number
  ) => {
    const pkey = playerKey(gameState, color);
    const current = Number(
      gameState.player_state[`${pkey}_${card}_IN_HAND`] ?? 0
    );
    const nextVal = Math.max(0, current + delta);
    const updated = await editGame(gameId, {
      op: "set_hand",
      color,
      [kind]: { [card]: nextVal },
    });
    dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
  };

  const setTurnPhase = async (current_color: Color, phase: string) => {
    const updated = await editGame(gameId, {
      op: "set_turn",
      current_color,
      phase,
    });
    dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
  };

  const clearBoard = async () => {
    const updated = await editGame(gameId, { op: "clear_board" });
    dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
  };

  const bothHumans = gameState.bot_colors.length === 0;
  const pkey = playerKey(gameState, editColor);

  return (
    <div className="sandbox-panel">
      <div className="sandbox-header">
        <span>Sandbox Controls</span>
        <div className="chip-row">
          <Tooltip title="Undo last move (or rewind to viewed history state)">
            <button
              type="button"
              className="tool-btn"
              disabled={false}
              onClick={handleUndo}
            >
              Undo
            </button>
          </Tooltip>
          <Tooltip title="Clone from current/viewed move as a new game variation">
            <button
              type="button"
              className="tool-btn"
              onClick={handleBranchNewGame}
            >
              Branch
            </button>
          </Tooltip>
          <Tooltip title="Have Bobcat play 1 move for the current player">
            <button type="button" className="tool-btn" onClick={handleBotMove}>
              Bot Move
            </button>
          </Tooltip>
        </div>
      </div>

      <div className="sandbox-section">
        <div className="sandbox-section-title">
          <span>Mode & File</span>
          <span>
            {bothHumans ? "Playing Both Sides (1v1)" : "Human vs Bot"}
          </span>
        </div>
        <div className="chip-row">
          <button
            type="button"
            className={`tool-btn ${bothHumans ? "active" : ""}`}
            onClick={handleTogglePlayBothSides}
          >
            {bothHumans ? "Play Both Sides: ON" : "Switch to Play Both Sides"}
          </button>
          <button type="button" className="tool-btn" onClick={handleExport}>
            Save JSON
          </button>
          <label className="tool-btn" style={{ cursor: "pointer" }}>
            Load JSON
            <input
              type="file"
              accept=".json"
              style={{ display: "none" }}
              onChange={handleImportFile}
            />
          </label>
        </div>
      </div>

      <div className="sandbox-section">
        <div className="sandbox-section-title">
          <span>Control Randomness</span>
          {(state.forcedRandom.dice ||
            state.forcedRandom.dev_card ||
            state.forcedRandom.robber_resource) && (
            <button
              type="button"
              className="tool-btn"
              onClick={() =>
                updateForced({
                  dice: null,
                  dev_card: null,
                  robber_resource: null,
                })
              }
            >
              Reset
            </button>
          )}
        </div>
        <div>
          <div style={{ fontSize: 10, opacity: 0.75, marginBottom: 3 }}>
            Next Dice Roll ({state.forcedRandom.dice ?? "Random"}):
          </div>
          <div className="chip-row">
            <button
              type="button"
              className={`tool-btn ${
                state.forcedRandom.dice === null ? "active" : ""
              }`}
              onClick={() => updateForced({ dice: null })}
            >
              Rnd
            </button>
            {DICE_SUMS.map((sum) => (
              <button
                key={sum}
                type="button"
                className={`tool-btn ${
                  state.forcedRandom.dice === sum ? "active" : ""
                }`}
                onClick={() => updateForced({ dice: sum })}
              >
                {sum}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 10, opacity: 0.75, marginBottom: 3 }}>
            Next Dev Card Drawn ({state.forcedRandom.dev_card ?? "Random"}):
          </div>
          <div className="chip-row">
            <button
              type="button"
              className={`tool-btn ${
                state.forcedRandom.dev_card === null ? "active" : ""
              }`}
              onClick={() => updateForced({ dev_card: null })}
            >
              Rnd
            </button>
            {DEV_CARDS.map((card) => (
              <button
                key={card}
                type="button"
                className={`tool-btn ${
                  state.forcedRandom.dev_card === card ? "active" : ""
                }`}
                onClick={() => updateForced({ dev_card: card })}
              >
                {card.replace("_", " ").slice(0, 8)}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 10, opacity: 0.75, marginBottom: 3 }}>
            Robber Steals ({state.forcedRandom.robber_resource ?? "Random"}):
          </div>
          <div className="chip-row">
            <button
              type="button"
              className={`tool-btn ${
                state.forcedRandom.robber_resource === null ? "active" : ""
              }`}
              onClick={() => updateForced({ robber_resource: null })}
            >
              Rnd
            </button>
            {RESOURCES.map((res) => (
              <button
                key={res}
                type="button"
                className={`tool-btn ${
                  state.forcedRandom.robber_resource === res ? "active" : ""
                }`}
                onClick={() => updateForced({ robber_resource: res })}
              >
                {res}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="sandbox-section">
        <div className="sandbox-section-title">
          <span>Set Up Position (Board & Hands)</span>
          <button
            type="button"
            className={`tool-btn ${
              expandedSetup || activeTool ? "active" : ""
            }`}
            onClick={() => {
              if (expandedSetup && activeTool) setTool(null);
              setExpandedSetup(!expandedSetup);
            }}
          >
            {expandedSetup ? "Hide Editor" : "Open Position Editor"}
          </button>
        </div>

        {expandedSetup && (
          <>
            <div className="chip-row" style={{ marginTop: 4 }}>
              <button
                type="button"
                className={`tool-btn red-chip ${
                  editColor === "RED" ? "active" : ""
                }`}
                onClick={() => setEditColor("RED")}
              >
                Editing RED
              </button>
              <button
                type="button"
                className={`tool-btn blue-chip ${
                  editColor === "BLUE" ? "active" : ""
                }`}
                onClick={() => setEditColor("BLUE")}
              >
                Editing BLUE
              </button>
              {activeTool && (
                <button
                  type="button"
                  className="tool-btn"
                  onClick={() => setTool(null)}
                >
                  Stop Placing
                </button>
              )}
              <button
                type="button"
                className="tool-btn"
                onClick={clearBoard}
                title="Remove all buildings, roads and cards"
              >
                Clear Pieces
              </button>
            </div>

            <div style={{ fontSize: 10, opacity: 0.75 }}>
              Click a tool below, then click any Node / Edge / Tile on the board:
            </div>
            <div className="chip-row">
              <button
                type="button"
                className={`tool-btn ${
                  activeTool?.kind === "building" &&
                  activeTool.building === "SETTLEMENT" &&
                  activeTool.color === editColor
                    ? "active"
                    : ""
                }`}
                onClick={() =>
                  setTool({
                    kind: "building",
                    color: editColor,
                    building: "SETTLEMENT",
                  })
                }
              >
                {editColor} Settlement
              </button>
              <button
                type="button"
                className={`tool-btn ${
                  activeTool?.kind === "building" &&
                  activeTool.building === "CITY" &&
                  activeTool.color === editColor
                    ? "active"
                    : ""
                }`}
                onClick={() =>
                  setTool({
                    kind: "building",
                    color: editColor,
                    building: "CITY",
                  })
                }
              >
                {editColor} City
              </button>
              <button
                type="button"
                className={`tool-btn ${
                  activeTool?.kind === "road" && activeTool.color === editColor
                    ? "active"
                    : ""
                }`}
                onClick={() => setTool({ kind: "road", color: editColor })}
              >
                {editColor} Road
              </button>
              <button
                type="button"
                className={`tool-btn ${
                  activeTool?.kind === "robber" ? "active" : ""
                }`}
                onClick={() => setTool({ kind: "robber" })}
              >
                Move Robber
              </button>
              <button
                type="button"
                className={`tool-btn ${
                  activeTool?.kind === "erase" ? "active" : ""
                }`}
                onClick={() => setTool({ kind: "erase" })}
              >
                Erase Piece
              </button>
            </div>

            <div style={{ fontSize: 10, opacity: 0.75 }}>
              Paint Tile Resource (click tile on board):
            </div>
            <div className="chip-row">
              {(
                ["WOOD", "BRICK", "SHEEP", "WHEAT", "ORE", "DESERT"] as const
              ).map((res) => (
                <button
                  key={res}
                  type="button"
                  className={`tool-btn ${
                    activeTool?.kind === "tile_resource" &&
                    activeTool.resource === res
                      ? "active"
                      : ""
                  }`}
                  onClick={() =>
                    setTool({ kind: "tile_resource", resource: res })
                  }
                >
                  {res}
                </button>
              ))}
            </div>

            <div style={{ fontSize: 10, opacity: 0.75 }}>
              Paint Tile Number (click land tile on board):
            </div>
            <div className="chip-row">
              {[2, 3, 4, 5, 6, 8, 9, 10, 11, 12].map((num) => (
                <button
                  key={num}
                  type="button"
                  className={`tool-btn ${
                    activeTool?.kind === "tile_number" &&
                    activeTool.number === num
                      ? "active"
                      : ""
                  }`}
                  onClick={() => setTool({ kind: "tile_number", number: num })}
                >
                  {num}
                </button>
              ))}
            </div>

            <div style={{ fontSize: 10, opacity: 0.75 }}>
              {editColor} Resources in Hand:
            </div>
            <div className="hand-grid">
              {RESOURCES.map((res) => {
                const count =
                  gameState.player_state[`${pkey}_${res}_IN_HAND`] ?? 0;
                return (
                  <div key={res} className="hand-counter">
                    <span className="res-label">{res.slice(0, 5)}</span>
                    <strong>{count}</strong>
                    <div className="counter-btns">
                      <button
                        type="button"
                        onClick={() =>
                          adjustCard(editColor, "resources", res, -1)
                        }
                      >
                        -
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          adjustCard(editColor, "resources", res, 1)
                        }
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ fontSize: 10, opacity: 0.75 }}>
              {editColor} Dev Cards in Hand:
            </div>
            <div className="hand-grid">
              {DEV_CARDS.map((card) => {
                const count =
                  gameState.player_state[`${pkey}_${card}_IN_HAND`] ?? 0;
                return (
                  <div key={card} className="hand-counter">
                    <span className="res-label">
                      {card.replace("_", "").slice(0, 5)}
                    </span>
                    <strong>{count}</strong>
                    <div className="counter-btns">
                      <button
                        type="button"
                        onClick={() =>
                          adjustCard(editColor, "dev_cards", card, -1)
                        }
                      >
                        -
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          adjustCard(editColor, "dev_cards", card, 1)
                        }
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ fontSize: 10, opacity: 0.75 }}>
              Turn & Phase Control ({editColor}):
            </div>
            <div className="chip-row">
              <button
                type="button"
                className="tool-btn"
                onClick={() => setTurnPhase(editColor, "PRE_ROLL")}
              >
                {editColor} To Roll
              </button>
              <button
                type="button"
                className="tool-btn"
                onClick={() => setTurnPhase(editColor, "POST_ROLL")}
              >
                {editColor} Main Turn
              </button>
              <button
                type="button"
                className="tool-btn"
                onClick={() => setTurnPhase(editColor, "MOVE_ROBBER")}
              >
                {editColor} Move Robber
              </button>
              <button
                type="button"
                className="tool-btn"
                onClick={() => setTurnPhase(editColor, "INITIAL_SETTLEMENT")}
              >
                {editColor} Setup Phase
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
