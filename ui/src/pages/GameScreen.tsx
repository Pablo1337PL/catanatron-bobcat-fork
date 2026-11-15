import { useCallback, useEffect, useRef, useState, useContext } from "react";
import { useParams } from "react-router-dom";
import PropTypes from "prop-types";
import { GridLoader } from "react-spinners";
import { useSnackbar } from "notistack";

import ZoomableBoard from "./ZoomableBoard";
import ActionsToolbar from "./ActionsToolbar";

import "./GameScreen.scss";
import LeftDrawer from "../components/LeftDrawer";
import RightDrawer from "../components/RightDrawer";
import { store } from "../store";
import ACTIONS from "../actions";
import {
  type StateIndex,
  getState,
  postAction,
  setPerspective,
  setActiveViewedStateIndex,
} from "../utils/apiClient";
import { dispatchSnackbar } from "../components/Snackbar";
import { getHumanColor } from "../utils/stateUtils";
import AnalysisBox from "../components/AnalysisBox";
import SandboxPanel from "../components/SandboxPanel";
import HistoryBanner from "../components/HistoryBanner";
import { Divider } from "@mui/material";

const ROBOT_THINKING_TIME = 300;

function GameScreen({ replayMode }: { replayMode: boolean }) {
  const { gameId, stateIndex } = useParams();
  const { state, dispatch } = useContext(store);
  const { enqueueSnackbar, closeSnackbar } = useSnackbar();
  const [isBotThinking, setIsBotThinking] = useState(false);
  const botMoveInFlight = useRef(false);
  const viewRequest = useRef(0);

  // Sync viewed state index with apiClient so actions played while viewing history branch cleanly
  useEffect(() => {
    setActiveViewedStateIndex(
      state.viewedState ? state.viewedState.state_index : null
    );
  }, [state.viewedState]);

  // Load game state when gameId or perspective changes
  useEffect(() => {
    if (!gameId) {
      return;
    }
    viewRequest.current += 1;
    setActiveViewedStateIndex(null);
    setPerspective(state.perspective);
    let cancelled = false;
    (async () => {
      const gameState = await getState(gameId, stateIndex as StateIndex);
      if (!cancelled) {
        dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
        dispatch({ type: ACTIONS.SET_GAME_STATE, data: gameState });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [gameId, stateIndex, state.perspective, dispatch]);

  const liveIndex = state.gameState?.state_index;
  const viewState = useCallback(
    async (index: number) => {
      if (!gameId || liveIndex === undefined) {
        return;
      }
      const request = ++viewRequest.current;
      const viewed =
        index >= liveIndex ? null : await getState(gameId, Math.max(index, 0));
      if (request === viewRequest.current) {
        dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: viewed });
      }
    },
    [gameId, liveIndex, dispatch]
  );

  // Auto-play bot only when not viewing historical state and current gameId matches loaded gameState
  useEffect(() => {
    if (
      !state.gameState ||
      replayMode ||
      !gameId ||
      state.viewedState !== null ||
      state.gameState.game?.id !== gameId
    ) {
      return;
    }
    if (
      state.gameState.bot_colors.includes(state.gameState.current_color) &&
      !state.gameState.winning_color
    ) {
      if (botMoveInFlight.current) {
        return;
      }
      botMoveInFlight.current = true;
      (async () => {
        setIsBotThinking(true);
        const start = new Date();
        let gameState;
        try {
          gameState = await postAction(gameId);
        } catch (error) {
          botMoveInFlight.current = false;
          setIsBotThinking(false);
          throw error;
        }
        const requestTime = new Date().valueOf() - start.valueOf();
        setTimeout(() => {
          botMoveInFlight.current = false;
          setIsBotThinking(false);
          dispatch({ type: ACTIONS.SET_GAME_STATE, data: gameState });
          if (getHumanColor(gameState)) {
            dispatchSnackbar(enqueueSnackbar, closeSnackbar, gameState);
          }
        }, Math.max(0, ROBOT_THINKING_TIME - requestTime));
      })();
    }
  }, [
    gameId,
    replayMode,
    state.gameState,
    state.viewedState,
    dispatch,
    enqueueSnackbar,
    closeSnackbar,
  ]);

  if (!state.gameState) {
    return (
      <main>
        <GridLoader className="loader" color="#000000" size={100} />
      </main>
    );
  }

  const viewedState = state.viewedState;
  const readOnly = replayMode;
  return (
    <main>
      <h1 className="logo">Catanatron</h1>
      <ZoomableBoard replayMode={readOnly} />
      <ActionsToolbar isBotThinking={isBotThinking} replayMode={readOnly} />
      {viewedState && (
        <HistoryBanner
          viewedState={viewedState}
          liveState={state.gameState}
          onView={viewState}
        />
      )}
      <LeftDrawer onSelectState={viewState} />
      <RightDrawer>
        <AnalysisBox stateIndex={viewedState?.state_index ?? "latest"} />
        <Divider />
        <SandboxPanel />
      </RightDrawer>
    </main>
  );
}

GameScreen.propTypes = {
  window: PropTypes.func,
};

export default GameScreen;
