import { Fragment, useContext, useEffect, useState } from "react";
import { Button, CircularProgress, Tooltip } from "@mui/material";
import AssessmentIcon from "@mui/icons-material/Assessment";
import { useParams } from "react-router-dom";

import {
  type Analysis,
  type AnalysisMove,
  type HandAssumption,
  type HandCard,
  type OpponentCards,
  type StateIndex,
  getAnalysis,
} from "../utils/apiClient";
import type { Color, GameState } from "../utils/api.types";
import { describeAction } from "../utils/promptUtils";
import useHighlight from "../hooks/useHighlight";
import { displayedGameState, store } from "../store";
import ACTIONS from "../actions";

import EvalBar, { percent } from "./EvalBar";
import TurnPlanMoves, { DiscardSets } from "./TurnPlan";

import "./AnalysisBox.scss";

/** Moves listed before "Show all". */
const TOP_MOVES = 6;

const LINE_ENDS: Record<string, { mark: string; title: string }> = {
  chance: { mark: "🎲", title: "Stops at a random event (dice, card, steal)" },
  terminal: { mark: "🏁", title: "The game ends" },
  unexplored: { mark: "…", title: "The search went no further" },
};

/** Cards Bobcat leaves for after the roll (it only weighs a Knight before it). */
const AFTER_THE_ROLL = ["PLAY_YEAR_OF_PLENTY", "PLAY_MONOPOLY", "PLAY_ROAD_BUILDING"];

const CARD_NAMES: Record<HandCard, string> = {
  KNIGHT: "Knight",
  YEAR_OF_PLENTY: "Year of Plenty",
  MONOPOLY: "Monopoly",
  ROAD_BUILDING: "Road Building",
  VICTORY_POINT: "Victory Point",
};

function handText(hand: HandCard[]) {
  return hand.map((card) => CARD_NAMES[card]).join(", ");
}

function assumptionTitle(assumption: HandAssumption) {
  return `Assuming ${assumption.color} holds ${handText(assumption.hand)} (${percent(
    assumption.probability,
  )})`;
}

/** The engine's guess at a face-down hand: what it expects and how sure it is. */
function PredictedCards({ cards }: { cards: OpponentCards }) {
  const shown = (Object.keys(CARD_NAMES) as HandCard[]).filter(
    (card) => cards.expected[card] >= 0.005,
  );
  return (
    <div className="predicted-cards">
      <div className="predicted-header">
        Predicted cards ·{" "}
        <span className={cards.color.toLowerCase()}>{cards.color}</span> holds{" "}
        {cards.count}
      </div>
      <ul>
        {shown.map((card) => (
          <li key={card}>
            <span>{CARD_NAMES[card]}</span>
            <span className="predicted-values">
              {cards.expected[card].toFixed(1)} · {percent(cards.at_least_one[card])}
            </span>
          </li>
        ))}
      </ul>
      <div className="predicted-likely">
        Most likely: {handText(cards.likely_hand)} (
        {percent(cards.likely_hand_probability)})
      </div>
    </div>
  );
}

type AnalysisBoxProps = {
  stateIndex: StateIndex;
};

/** Assumed hands shown just before line step `index`. */
function assumptionsAt(move: AnalysisMove, index: number): HandAssumption[] {
  return (move.line_assumptions ?? []).filter((a) => a.step === index);
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
  const highlight = useHighlight();
  const end = move.line_end ? LINE_ENDS[move.line_end] : undefined;
  return (
    <li className="move-row" {...highlight(move.action)}>
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
          <Fragment key={index}>
            {assumptionsAt(move, index).map((assumption) => (
              <li
                key={`hand-${index}`}
                className="line-assumption"
                title={assumptionTitle(assumption)}
                aria-label={assumptionTitle(assumption)}
              >
                🂠
              </li>
            ))}
            <li
              className="line-step"
              tabIndex={0}
              {...highlight(action, move.action)}
            >
              <span
                className={`step-color ${action[0].toLowerCase()}`}
                title={action[0]}
              />
              {describeAction(gameState, action)}
            </li>
          </Fragment>
        ))}
        {assumptionsAt(move, move.line.length).map((assumption, index) => (
          <li
            key={`hand-end-${index}`}
            className="line-assumption"
            title={assumptionTitle(assumption)}
            aria-label={assumptionTitle(assumption)}
          >
            🂠
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
  const { state, dispatch } = useContext(store);
  const [analysis, setAnalysis] = useState<Analysis | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);
  const gameState = displayedGameState(state);

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
  const playable = gameState?.current_playable_actions ?? [];
  const preRollCardsLeftOut =
    playable.some((action) => action[1] === "ROLL") &&
    playable.some((action) => AFTER_THE_ROLL.includes(action[1]));
  const shown = <T,>(all: T[]) => (showAll ? all : all.slice(0, TOP_MOVES));
  const moves =
    analysis && analysis.mode !== "turn" && analysis.mode !== "discard"
      ? shown(analysis.moves)
      : [];
  // A turn plan and discard sets need a wider drawer
  const wide =
    !error && (analysis?.mode === "turn" || analysis?.mode === "discard");
  useEffect(() => {
    dispatch({ type: ACTIONS.SET_WIDE_ANALYSIS, data: wide });
  }, [dispatch, wide]);
  useEffect(
    () => () => dispatch({ type: ACTIONS.SET_WIDE_ANALYSIS, data: false }),
    [dispatch],
  );

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

          {analysis.opponent_cards?.map((cards) => (
            <PredictedCards key={cards.color} cards={cards} />
          ))}

          {analysis.player && analysis.moves.length > 0 && (
            <>
              <div className="moves-header">
                <span>
                  <span className={analysis.player.toLowerCase()}>
                    {analysis.player}
                  </span>{" "}
                  to play
                </span>
                <span>
                  {analysis.mode === "turn" || analysis.mode === "discard"
                    ? "win"
                    : "choice · win"}
                </span>
              </div>
              {analysis.turn_fallback && (
                <div className="analysis-note">
                  Too many turn variations for a turn plan: regular search.
                </div>
              )}
              {analysis.mode === "turn" ? (
                <>
                  <div className="analysis-note">
                    Whole turn searched: {analysis.turn_stats.states} positions,{" "}
                    {analysis.turn_stats.leaves} ways to end it; the best{" "}
                    {analysis.turn_stats.refined} searched further (★). Bobcat
                    picks only among those.
                  </div>
                  {analysis.assumed_hand && (
                    <div className="analysis-note">
                      Assuming {analysis.assumed_hand.color} holds{" "}
                      {handText(analysis.assumed_hand.hand)} (
                      {percent(analysis.assumed_hand.probability)}).
                    </div>
                  )}
                  <TurnPlanMoves
                    moves={shown(analysis.moves)}
                    player={analysis.player}
                    colors={colors}
                    gameState={gameState}
                  />
                </>
              ) : analysis.mode === "discard" ? (
                <DiscardSets
                  moves={shown(analysis.moves)}
                  player={analysis.player}
                  colors={colors}
                />
              ) : (
                <>
                  {analysis.averaged_over_hands && (
                    <div className="analysis-note">
                      Averaged over the hands Bobcat expects {analysis.player}{" "}
                      to hold.
                    </div>
                  )}
                  {preRollCardsLeftOut && (
                    <div className="analysis-note">
                      Bobcat does not consider Year of Plenty, Monopoly and Road
                      Building before the roll.
                    </div>
                  )}
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
                </>
              )}
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
