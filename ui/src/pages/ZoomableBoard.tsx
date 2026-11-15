import { useCallback, useContext, useEffect, useState } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import memoize from "fast-memoize";
import { IconButton, Tooltip, useMediaQuery, useTheme } from "@mui/material";
import AbcIcon from "@mui/icons-material/Abc";

import useWindowSize from "../utils/useWindowSize";

/** How much wider the right drawer is with a turn plan (variables.scss). */
const WIDE_DRAWER_EXTRA = 200;

import "./Board.scss";
import { displayedGameState, store } from "../store";
import { isPlayersTurn } from "../utils/stateUtils";
import { postAction, editGame } from "../utils/apiClient";
import { saveShowLabels } from "../utils/preferences";
import { actionPlaces } from "../utils/highlight";
import type { CatanState } from "../store";
import { useParams } from "react-router-dom";
import ACTIONS from "../actions";
import Board from "./Board";
import type { GameAction, TileCoordinate } from "../utils/api.types";

/**
 * Returns object representing actions to be taken if click on node.
 * @returns {3 => ["BLUE", "BUILD_CITY", 3], ...}
 */
function buildNodeActions(state: CatanState) {
  const gs = displayedGameState(state);
  if (!gs)
    throw new Error("GameState is not ready!");

  if (state.viewedState === null && !isPlayersTurn(gs)) {
    return {};
  }

  const nodeActions: Record<number, GameAction> = {};
  const buildInitialSettlementActions = gs.is_initial_build_phase
    ? gs.current_playable_actions.filter(
        (action) => action[1] === "BUILD_SETTLEMENT"
      )
    : [];
  const inInitialBuildPhase = gs.is_initial_build_phase;
  if (inInitialBuildPhase) {
    buildInitialSettlementActions.forEach((action) => {
      nodeActions[action[2]] = action;
    });
  } else if (state.isBuildingSettlement) {
    gs.current_playable_actions
      .filter((action) => action[1] === "BUILD_SETTLEMENT")
      .forEach((action) => {
        nodeActions[action[2]] = action;
      });
  } else if (state.isBuildingCity) {
    gs.current_playable_actions
      .filter((action) => action[1] === "BUILD_CITY")
      .forEach((action) => {
        nodeActions[action[2]] = action;
      });
  }
  return nodeActions;
}

function buildEdgeActions(state: CatanState) {
  const gs = displayedGameState(state);
  if (!gs)
    throw new Error("GameState is not ready!");
  if (state.viewedState === null && !isPlayersTurn(gs)) {
    return {};
  }

  const edgeActions: Record<`${number},${number}`, GameAction> = {};
  const buildInitialRoadActions = gs.is_initial_build_phase
    ? gs.current_playable_actions.filter(
        (action) => action[1] === "BUILD_ROAD"
      )
    : [];
  const inInitialBuildPhase = gs.is_initial_build_phase;
  if (inInitialBuildPhase) {
    buildInitialRoadActions.forEach((action) => {
      edgeActions[`${action[2][0]},${action[2][1]}`] = action;
    });
  } else if (state.isBuildingRoad || state.isRoadBuilding) {
    gs.current_playable_actions
      .filter((action) => action[1] === "BUILD_ROAD")
      .forEach((action) => {
        edgeActions[`${action[2][0]},${action[2][1]}`] = action;
      });
  }
  return edgeActions;
}

type ZoomableBoardProps = {
  replayMode: boolean;
}

export default function ZoomableBoard({ replayMode }: ZoomableBoardProps) {
  const { gameId } = useParams();
  const { state, dispatch } = useContext(store);
  const { width, height } = useWindowSize();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.up("md"));
  // Both drawers are permanent from lg up: a wide analysis drawer takes room
  // from the board (centred between the drawers by GameScreen.scss)
  const isLarge = useMediaQuery(theme.breakpoints.up("lg"));
  const [show, setShow] = useState(false);
  const gameState = displayedGameState(state);
  if (!gameState)
    throw new Error("GameState is not ready!");
  if (!gameId)
    throw new Error("expecting gameId in URL");

  // TODO: Move these up to GameScreen and let Zoomable be presentational component
  // https://stackoverflow.com/questions/61255053/react-usecallback-with-parameter
  const buildOnNodeClick = useCallback(
    (id: number, action?: GameAction) => async () => {
      if (state.sandboxTool) {
        if (state.sandboxTool.kind === "building") {
          const updated = await editGame(gameId, {
            op: "set_node",
            node_id: id,
            color: state.sandboxTool.color,
            building: state.sandboxTool.building,
          });
          dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
          dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
          return;
        }
        if (state.sandboxTool.kind === "erase") {
          const updated = await editGame(gameId, {
            op: "set_node",
            node_id: id,
            color: null,
            building: null,
          });
          dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
          dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
          return;
        }
      }
      if (action) {
        const nextState = await postAction(gameId, action);
        dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
        dispatch({ type: ACTIONS.SET_GAME_STATE, data: nextState });
      }
    },
    [gameId, state.sandboxTool, dispatch]
  );
  const buildOnEdgeClick = useCallback(
    (id: [number, number], action?: GameAction) => async () => {
      if (state.sandboxTool) {
        if (state.sandboxTool.kind === "road") {
          const updated = await editGame(gameId, {
            op: "set_edge",
            edge: id,
            color: state.sandboxTool.color,
          });
          dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
          dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
          return;
        }
        if (state.sandboxTool.kind === "erase") {
          const updated = await editGame(gameId, {
            op: "set_edge",
            edge: id,
            color: null,
          });
          dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
          dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
          return;
        }
      }
      if (action) {
        const nextState = await postAction(gameId, action);
        dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
        dispatch({ type: ACTIONS.SET_GAME_STATE, data: nextState });
      }
    },
    [gameId, state.sandboxTool, dispatch]
  );
  const handleTileClick = useCallback(
    (coordinate: TileCoordinate) => {
      if (state.sandboxTool) {
        if (state.sandboxTool.kind === "tile_resource") {
          editGame(gameId, {
            op: "set_tile",
            coordinate,
            resource: state.sandboxTool.resource,
          }).then((updated) => {
            dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
            dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
          });
          return;
        }
        if (state.sandboxTool.kind === "tile_number") {
          editGame(gameId, {
            op: "set_tile",
            coordinate,
            number: state.sandboxTool.number,
          }).then((updated) => {
            dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
            dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
          });
          return;
        }
        if (state.sandboxTool.kind === "robber") {
          editGame(gameId, {
            op: "set_robber",
            coordinate,
          }).then((updated) => {
            dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
            dispatch({ type: ACTIONS.SET_GAME_STATE, data: updated });
          });
          return;
        }
      }
      if (state.isMovingRobber) {
        const matchingAction = gameState.current_playable_actions.find(
          (action) =>
            action[1] === "MOVE_ROBBER" &&
            action[2][0].every(
              (val: number, index: number) => val === coordinate[index],
            ),
        );
        if (matchingAction) {
          postAction(gameId, matchingAction).then((nextState) => {
            dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
            dispatch({ type: ACTIONS.SET_GAME_STATE, data: nextState });
          });
        }
      }
    },
    [gameId, state.sandboxTool, state.isMovingRobber, gameState.current_playable_actions, dispatch]
  );

  const nodeActions = replayMode ? {} : buildNodeActions(state);
  const edgeActions = replayMode ? {} : buildEdgeActions(state);
  const robberCoordinates = new Set(
    state.isMovingRobber
      ? gameState.current_playable_actions
          .filter((action) => action[1] === "MOVE_ROBBER")
          .map((action) => `${action[2][0]}`)
      : []
  );

  useEffect(() => {
    setTimeout(() => {
      setShow(true);
    }, 300);
  }, []);

  if (!width || !height) return;

  const toggleLabels = () => {
    saveShowLabels(!state.showLabels);
    dispatch({ type: ACTIONS.SET_SHOW_LABELS, data: !state.showLabels });
  };
  const labelsTitle = state.showLabels ? "Hide tile letters" : "Show tile letters";

  return (
    <TransformWrapper>
      <div className="board-container">
        <Tooltip title={labelsTitle}>
          <IconButton
            className="labels-toggle"
            aria-label={labelsTitle}
            aria-pressed={state.showLabels}
            onClick={toggleLabels}
            size="small"
          >
            <AbcIcon />
          </IconButton>
        </Tooltip>
        <TransformComponent>
          <Board
            width={isLarge && state.wideAnalysis ? width - WIDE_DRAWER_EXTRA : width}
            height={height}
            buildOnNodeClick={buildOnNodeClick}
            buildOnEdgeClick={buildOnEdgeClick}
            handleTileClick={handleTileClick}
            nodeActions={nodeActions}
            edgeActions={edgeActions}
            replayMode={replayMode}
            show={show}
            gameState={gameState}
            isMobile={isMobile}
            isMovingRobber={state.isMovingRobber}
            robberCoordinates={robberCoordinates}
            showLabels={state.showLabels}
            highlight={actionPlaces(state.highlightedAction)}
          />
        </TransformComponent>
      </div>
    </TransformWrapper>
  );
}
