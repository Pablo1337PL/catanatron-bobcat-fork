import { useContext, useState } from "react";
import { Button, CircularProgress, Tooltip } from "@mui/material";
import AssessmentIcon from "@mui/icons-material/Assessment";
import { useParams } from "react-router-dom";

import {
  type Analysis,
  type AnalysisMove,
  type StateIndex,
  getAnalysis,
} from "../utils/apiClient";
import type { Color, GameState } from "../utils/api.types";
import { describeAction } from "../utils/promptUtils";
import { store } from "../store";

import "./AnalysisBox.scss";

/** Moves listed before "Show all". */
const TOP_MOVES = 6;

const LINE_ENDS: Record<string, { mark: string; title: string }> = {
  chance: { mark: "🎲", title: "Stops at a random event (dice, card, steal)" },
  terminal: { mark: "🏁", title: "The game ends" },
  unexplored: { mark: "…", title: "The search went no further" },
};

type AnalysisBoxProps = {
  stateIndex: StateIndex;
};

function percent(probability: number | undefined) {
  return `${((probability ?? 0) * 100).toFixed(1)}%`;
}

/** Two-color (or more) bar of win probabilities, like a chess evaluation bar. */
function EvalBar({
  colors,
  winProbability,
  compact = false,
}: {
  colors: Color[];
  winProbability: Partial<Record<Color, number>>;
  compact?: boolean;
}) {
  return (
    <div
      className={`eval-bar${compact ? " compact" : ""}`}
      role="img"
      aria-label={colors
        .map((color) => `${color} ${percent(winProbability[color])}`)
        .join(", ")}
    >
      {colors.map((color) => {
        const p = winProbability[color] ?? 0;
        return (
          <div
            key={color}
            className={`eval-segment ${color.toLowerCase()}`}
            style={{ flexGrow: p, flexBasis: 0 }}
          >
            {!compact && p >= 0.12 && (
              <span>
                {color} {percent(p)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function MoveRow({
  move,
  rank,
  player,
  colors,
  gameState,
}: {
  move: AnalysisMove;
  rank: number;
  player: Color;
  colors: Color[];
  gameState: GameState;
}) {
  const end = move.line_end ? LINE_ENDS[move.line_end] : undefined;
  return (
    <li className="move-row">
      <div className="move-stats">
        <span className="move-rank">{rank}.</span>
        <Tooltip
          title={`Search: ${move.visits} visits${
            move.prior !== null ? ` · network prior ${percent(move.prior)}` : ""
          }`}
          arrow
        >
          <span className="move-probability">
            <span
              className="move-probability-fill"
              style={{ width: `${move.probability * 100}%` }}
            />
            <span className="move-probability-value">
              {percent(move.probability)}
            </span>
          </span>
        </Tooltip>
        {move.win_probability ? (
          <span className="move-eval">
            <EvalBar
              colors={colors}
              winProbability={move.win_probability}
              compact
            />
            <span className={`move-eval-value ${player.toLowerCase()}`}>
              {percent(move.win_probability[player])}
            </span>
          </span>
        ) : (
          <span className="move-eval unexplored">not searched</span>
        )}
      </div>
      <ol className="move-line">
        {move.line.map((action, index) => (
          <li key={index} className="line-step">
            <span
              className={`step-color ${action[0].toLowerCase()}`}
              title={action[0]}
            />
            {describeAction(gameState, action)}
          </li>
        ))}
        {end && (
          <li className="line-end" title={end.title}>
            {end.mark}
          </li>
        )}
      </ol>
    </li>
  );
}

export default function AnalysisBox({ stateIndex }: AnalysisBoxProps) {
  const { gameId } = useParams();
  const { state } = useContext(store);
  const [analysis, setAnalysis] = useState<Analysis | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);
  const gameState = state.gameState;

  const handleAnalyzeClick = async () => {
    if (!gameId || !gameState || gameState.winning_color) return;

    try {
      setLoading(true);
      setError("");
      setAnalysis(await getAnalysis(gameId, stateIndex));
      setShowAll(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const colors = gameState?.colors ?? [];
  const stale =
    analysis !== undefined &&
    gameState !== null &&
    gameState !== undefined &&
    analysis.state_index !== gameState.state_index;
  const moves = analysis
    ? showAll
      ? analysis.moves
      : analysis.moves.slice(0, TOP_MOVES)
    : [];

  return (
    <div className="analysis-box">
      <div className="analysis-header">
        <h3>Bobcat Analysis</h3>
        <Button
          variant="contained"
          color="primary"
          onClick={handleAnalyzeClick}
          disabled={loading || !!gameState?.winning_color}
          startIcon={
            loading ? <CircularProgress size={20} /> : <AssessmentIcon />
          }
        >
          {loading ? "Analyzing..." : "Analyze"}
        </Button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {analysis && gameState && !error && (
        <div className={`analysis-result${stale ? " stale" : ""}`}>
          <div className="analysis-meta">
            {analysis.engine && <span>{analysis.engine}</span>}
            {analysis.simulations > 0 && (
              <span>{analysis.seconds.toFixed(1)} s</span>
            )}
            <span>state {analysis.state_index}</span>
          </div>
          {stale && (
            <div className="stale-note">
              The position has changed. Analyze again.
            </div>
          )}

          <EvalBar colors={colors} winProbability={analysis.win_probability} />

          {analysis.player && analysis.moves.length > 0 && (
            <>
              <div className="moves-header">
                <span>
                  <span className={analysis.player.toLowerCase()}>
                    {analysis.player}
                  </span>{" "}
                  to play
                </span>
                <span>choice · win</span>
              </div>
              <ol className="moves">
                {moves.map((move, index) => (
                  <MoveRow
                    key={index}
                    move={move}
                    rank={index + 1}
                    player={analysis.player as Color}
                    colors={colors}
                    gameState={gameState}
                  />
                ))}
              </ol>
              {analysis.moves.length > TOP_MOVES && (
                <Button
                  size="small"
                  className="show-all"
                  onClick={() => setShowAll((current) => !current)}
                >
                  {showAll
                    ? "Show fewer"
                    : `Show all ${analysis.moves.length} moves`}
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
