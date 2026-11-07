import { useEffect } from "react";
import { Button, IconButton, Tooltip } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

import type { GameActionRecord, GameState } from "../utils/api.types";
import { humanizeActionRecord } from "../utils/promptUtils";

import "./HistoryBanner.scss";

type HistoryBannerProps = {
  /** The earlier state on the board. */
  viewedState: GameState;
  /** The game as it is now. */
  liveState: GameState | null;
  /** Show the board at a state index; the live index returns to the game. */
  onView: (stateIndex: number) => void;
};

/**
 * Shown while the board is at an earlier state picked in the log: which move
 * it is after, steps back and forth (also ← and →), and the way back to the
 * game (also Esc).
 */
export default function HistoryBanner({
  viewedState,
  liveState,
  onView,
}: HistoryBannerProps) {
  const index = viewedState.state_index;
  const liveIndex = liveState?.state_index ?? index;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable]")) {
        return;
      }
      if (event.key === "ArrowLeft" && index > 0) {
        onView(index - 1);
      } else if (event.key === "ArrowRight") {
        onView(index + 1);
      } else if (event.key === "Escape") {
        onView(liveIndex);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [index, liveIndex, onView]);

  const lastRecord = viewedState.action_records[index - 1] as
    | GameActionRecord
    | undefined;
  return (
    <div className="history-banner" role="status">
      <Tooltip title="Previous move (←)">
        <span>
          <IconButton
            size="small"
            aria-label="Previous move"
            disabled={index === 0}
            onClick={() => onView(index - 1)}
          >
            <ChevronLeftIcon />
          </IconButton>
        </span>
      </Tooltip>
      <div className="history-position">
        <strong>
          {index === 0 ? "Start of the game" : `After move ${index}`} of{" "}
          {liveIndex}
        </strong>
        {lastRecord && (
          <span className={`history-move ${lastRecord[0][0].toLowerCase()}`}>
            {humanizeActionRecord(
              viewedState,
              lastRecord,
              viewedState.action_details?.[index - 1]
            )}
          </span>
        )}
      </div>
      <Tooltip title="Next move (→)">
        <IconButton
          size="small"
          aria-label="Next move"
          onClick={() => onView(index + 1)}
        >
          <ChevronRightIcon />
        </IconButton>
      </Tooltip>
      <Button
        variant="contained"
        size="small"
        className="back-to-game"
        onClick={() => onView(liveIndex)}
      >
        Back to game
      </Button>
    </div>
  );
}
