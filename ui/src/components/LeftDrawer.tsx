import React, { useCallback, useContext, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import cn from "classnames";
import SwipeableDrawer from "@mui/material/SwipeableDrawer";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";

import Button from "@mui/material/Button";

import Hidden from "./Hidden";
import PlayerStateBox from "./PlayerStateBox";
import {
  formatDuration,
  formatResourceChange,
  humanizeActionRecord,
  moveDuration,
} from "../utils/promptUtils";
import { displayedGameState, store } from "../store";
import ACTIONS from "../actions";
import { getHumanColor, playerKey } from "../utils/stateUtils";
import {
  type ActionDetails,
  type GameActionRecord,
  type GameState,
} from "../utils/api.types";
import { isTabOrShift, type InteractionEvent } from "../utils/events";
import useHighlight from "../hooks/useHighlight";

import "./LeftDrawer.scss";

function PerspectiveToggle({ gameState }: { gameState: GameState }) {
  const { state, dispatch } = useContext(store);
  const humanColor = getHumanColor(gameState);
  if (!humanColor) {
    return null; // Bots only: there is no seat to sit in.
  }
  if (state.gameState?.winning_color) {
    return null; // After the game every hand is face up.
  }
  const seated = state.perspective !== null;
  return (
    <Button
      className="perspective-toggle"
      size="small"
      onClick={() =>
        dispatch({
          type: ACTIONS.SET_PERSPECTIVE,
          data: seated ? null : humanColor,
        })
      }
      title={
        seated
          ? "Showing only what your seat can see"
          : "Showing every hand, as a spectator"
      }
    >
      {seated ? `Playing as ${humanColor}` : "Spectating"}
    </Button>
  );
}

/**
 * Seeds to replay this game. The board seed is public; the game and dice
 * seeds arrive only once the game is over (they reveal every future roll).
 */
function SeedsInfo({ gameState }: { gameState: GameState }) {
  const seeds = gameState.seeds;
  if (!seeds) {
    return null;
  }
  const parts = [
    ["Board", seeds.board],
    ["Dice", seeds.dice],
    ["Game", seeds.game],
  ].filter(([, value]) => value !== undefined && value !== null);
  if (parts.length === 0) {
    return null;
  }
  return (
    <div className="seeds-info" title="Same seeds = same game (New game → Seeds)">
      Seeds:{" "}
      {parts.map(([label, value]) => `${label} ${value}`).join(" · ")}
      {seeds.dice === undefined ? " · dice & game after the end" : ""}
    </div>
  );
}

/** What a roll paid to each seat, e.g. "RED +2 WHEAT · BLUE nothing". */
function RollPayout({
  colors,
  details,
}: {
  colors: GameState["colors"];
  details: ActionDetails | undefined;
}) {
  const changes = details?.resource_changes;
  if (!changes) {
    return null;
  }
  return (
    <span className="roll-payout">
      {colors.map((color) => (
        <span key={color} className="payout">
          <span className={cn("payout-color", color.toLowerCase())}>
            {color}
          </span>{" "}
          {changes[color] ? formatResourceChange(changes[color]) : "nothing"}
        </span>
      ))}
    </span>
  );
}

function formatClock(unixSeconds: number) {
  return new Date(unixSeconds * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function LogEntry({
  gameState,
  index,
  viewed,
  onSelect,
}: {
  gameState: GameState;
  index: number;
  viewed: boolean;
  onSelect?: (stateIndex: number) => void;
}) {
  const highlight = useHighlight();
  const actionRecord = gameState.action_records[index] as GameActionRecord;
  const details = gameState.action_details?.[index];
  const duration = moveDuration(gameState, index);
  const isRoll = actionRecord[0][1] === "ROLL";
  const rolledSeven =
    isRoll && (actionRecord[1] as [number, number]).reduce((a, b) => a + b) === 7;
  const time = details?.played_at
    ? `Played at ${formatClock(details.played_at)}`
    : undefined;

  return (
    <button
      type="button"
      className={cn("action foreground", actionRecord[0][0], { viewed })}
      disabled={!onSelect}
      title={onSelect ? "Show the board after this move" : undefined}
      onClick={() => onSelect?.(index + 1)}
      {...highlight(actionRecord[0])}
    >
      <span className="action-main">
        <span className="action-text">
          {humanizeActionRecord(gameState, actionRecord, details)}
        </span>
        {duration !== null && (
          <span className="action-time" title={time}>
            {formatDuration(duration)}
          </span>
        )}
      </span>
      {isRoll && !rolledSeven && (
        <RollPayout colors={gameState.colors} details={details} />
      )}
    </button>
  );
}

function TimeTravelBar({
  currentIndex,
  liveIndex,
  onSelectState,
}: {
  currentIndex: number;
  liveIndex: number;
  onSelectState?: (stateIndex: number) => void;
}) {
  useEffect(() => {
    if (!onSelectState) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable]")) {
        return;
      }
      if (event.key === "ArrowLeft" && currentIndex > 0) {
        event.preventDefault();
        onSelectState(currentIndex - 1);
      } else if (event.key === "ArrowRight" && currentIndex < liveIndex) {
        event.preventDefault();
        onSelectState(currentIndex + 1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [currentIndex, liveIndex, onSelectState]);

  if (!onSelectState) return null;
  const isPast = currentIndex < liveIndex;

  return (
    <div className="time-travel-bar">
      <div style={{ display: "flex", gap: 4 }}>
        <button
          type="button"
          className="nav-btn"
          disabled={currentIndex === 0}
          onClick={() => onSelectState(0)}
          title="Jump to start of game (Move 0)"
        >
          |&lt;
        </button>
        <button
          type="button"
          className="nav-btn"
          disabled={currentIndex === 0}
          onClick={() => onSelectState(currentIndex - 1)}
          title="Previous move (Left Arrow)"
        >
          &lt; Prev
        </button>
      </div>
      <div style={{ textAlign: "center" }}>
        <strong>
          Move {currentIndex} / {liveIndex}
        </strong>
        {isPast && (
          <div style={{ fontSize: 9, color: "#81c784" }}>
            Make any move on board to branch!
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        <button
          type="button"
          className="nav-btn"
          disabled={currentIndex >= liveIndex}
          onClick={() => onSelectState(currentIndex + 1)}
          title="Next move (Right Arrow)"
        >
          Next &gt;
        </button>
        <button
          type="button"
          className="nav-btn"
          disabled={currentIndex >= liveIndex}
          onClick={() => onSelectState(liveIndex)}
          title="Jump to latest move"
        >
          &gt;|
        </button>
      </div>
    </div>
  );
}

function VariationTree({ logState }: { logState: GameState }) {
  const navigate = useNavigate();
  const { dispatch } = useContext(store);
  const variations = logState.variations ?? [];
  if (variations.length === 0) {
    return null;
  }
  return (
    <div className="variation-tree-box">
      <div className="var-title">
        <span>Variation Tree (Branches)</span>
        <span>{variations.length} {variations.length === 1 ? "line" : "lines"}</span>
      </div>
      {variations.map((v, idx) => (
        <button
          key={v.game_id}
          type="button"
          className={cn("var-node", { active: v.active })}
          onClick={() => {
            dispatch({ type: ACTIONS.SET_VIEWED_STATE, data: null });
            navigate(`/games/${v.game_id}`);
          }}
        >
          <span>
            {idx === 0 ? "● Mainline" : `├─ ${v.label}`}
          </span>
          <span style={{ opacity: 0.75, fontSize: 10 }}>
            {v.head_index} moves
          </span>
        </button>
      ))}
    </div>
  );
}

function DrawerContent({
  gameState,
  logState,
  onSelectState,
}: {
  /** The state the players' boxes show: the live one or one picked in the log. */
  gameState: GameState;
  /** The live game, whose whole log is listed. */
  logState: GameState;
  onSelectState?: (stateIndex: number) => void;
}) {
  const viewedIndex =
    gameState === logState ? null : gameState.state_index;
  const playerSections = gameState.colors.map((color) => {
    const key = playerKey(gameState, color);
    return (
      <React.Fragment key={color}>
        <PlayerStateBox
          playerState={gameState.player_state}
          playerKey={key}
          color={color}
        />
        <Divider />
      </React.Fragment>
    );
  });

  return (
    <>
      <PerspectiveToggle gameState={gameState} />
      <SeedsInfo gameState={gameState} />
      {playerSections}
      <TimeTravelBar
        currentIndex={gameState.state_index}
        liveIndex={logState.state_index}
        onSelectState={onSelectState}
      />
      <VariationTree logState={logState} />
      <div className="log">
        {logState.action_records
          .map((_, index) => (
            <LogEntry
              key={index}
              gameState={logState}
              index={index}
              viewed={viewedIndex === index + 1}
              onSelect={onSelectState}
            />
          ))
          .reverse()}
      </div>
    </>
  );
}

export default function LeftDrawer({
  onSelectState,
}: {
  /** Called with the state index after a clicked log entry; without it the
   * log is not clickable. */
  onSelectState?: (stateIndex: number) => void;
}) {
  const { state, dispatch } = useContext(store);
  const content = (
    <DrawerContent
      gameState={displayedGameState(state) as GameState}
      logState={state.gameState as GameState}
      onSelectState={onSelectState}
    />
  );
  const iOS = /iPad|iPhone|iPod/.test(navigator.userAgent);

  const openLeftDrawer = useCallback(
    (event: InteractionEvent) => {
      if (isTabOrShift(event)) {
        return;
      }

      dispatch({ type: ACTIONS.SET_LEFT_DRAWER_OPENED, data: true });
    },
    [dispatch],
  );
  const closeLeftDrawer = useCallback(
    (event: InteractionEvent) => {
      if (isTabOrShift(event)) {
        return;
      }

      dispatch({ type: ACTIONS.SET_LEFT_DRAWER_OPENED, data: false });
    },
    [dispatch],
  );

  return (
    <>
      <Hidden breakpoint={{ size: "md", direction: "up" }} implementation="js">
        <SwipeableDrawer
          className="left-drawer"
          anchor="left"
          open={state.isLeftDrawerOpen}
          onClose={closeLeftDrawer}
          onOpen={openLeftDrawer}
          disableBackdropTransition={!iOS}
          disableDiscovery={iOS}
          onKeyDown={closeLeftDrawer}
        >
          {content}
        </SwipeableDrawer>
      </Hidden>
      <Hidden
        breakpoint={{ size: "sm", direction: "down" }}
        implementation="css"
      >
        <Drawer className="left-drawer" anchor="left" variant="permanent" open>
          {content}
        </Drawer>
      </Hidden>
    </>
  );
}
