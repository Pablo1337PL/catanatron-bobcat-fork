import { useState } from "react";
import { Tooltip } from "@mui/material";

import type {
  DiscardMove,
  PlanOutcome,
  TurnMove,
  TurnPlan as Plan,
  WinProbability,
} from "../utils/apiClient";
import type { Color, GameAction, GameState } from "../utils/api.types";
import { describeAction } from "../utils/promptUtils";
import useHighlight from "../hooks/useHighlight";
import EvalBar, { percent } from "./EvalBar";

/** Names of what a random event can give: a development card or a resource. */
const RESULT_NAMES: Record<string, string> = {
  KNIGHT: "Knight",
  YEAR_OF_PLENTY: "Year of Plenty",
  MONOPOLY: "Monopoly",
  ROAD_BUILDING: "Road Building",
  VICTORY_POINT: "Victory Point",
  WOOD: "Wood",
  BRICK: "Brick",
  SHEEP: "Sheep",
  WHEAT: "Wheat",
  ORE: "Ore",
};

function resultText(action: GameAction, result: string | null) {
  const name = result === null ? "nothing" : (RESULT_NAMES[result] ?? result);
  return action[1] === "BUY_DEVELOPMENT_CARD" ? `Draws ${name}` : `Steals ${name}`;
}

function sameAction(a: GameAction | undefined, b: GameAction) {
  return a !== undefined && JSON.stringify(a) === JSON.stringify(b);
}

type Context = {
  player: Color;
  colors: Color[];
  gameState: GameState;
  /** Lit up again when the pointer leaves a step. */
  moveAction: GameAction;
};

function WinValue({ win, context }: { win: WinProbability; context: Context }) {
  return (
    <span className="plan-eval">
      <EvalBar colors={context.colors} winProbability={win} compact />
      <span className={`move-eval-value ${context.player.toLowerCase()}`}>
        {percent(win[context.player])}
      </span>
    </span>
  );
}

function Outcome({
  outcome,
  chanceAction,
  open: initiallyOpen,
  context,
}: {
  outcome: PlanOutcome;
  chanceAction: GameAction;
  open: boolean;
  context: Context;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const label = resultText(chanceAction, outcome.result);
  return (
    <li className="plan-outcome">
      <button
        type="button"
        className="outcome-header"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="outcome-toggle">{open ? "▾" : "▸"}</span>
        <span className="move-probability" title="Probability">
          <span
            className="move-probability-fill"
            style={{ width: `${outcome.probability * 100}%` }}
          />
          <span className="move-probability-value">
            {percent(outcome.probability)}
          </span>
        </span>
        <span className="outcome-label">{label}</span>
        <WinValue win={outcome.win_probability} context={context} />
      </button>
      {open && (
        <div className="outcome-plan">
          <PlanView plan={outcome.plan} context={context} />
        </div>
      )}
    </li>
  );
}

/** A plan: its steps one under another, then how it ends. `isMove` – the
 * plan right under its move: when the move itself is the random event (a
 * card bought, a robber moved), the row above already names it. */
export function PlanView({
  plan,
  context,
  isMove = false,
}: {
  plan: Plan;
  context: Context;
  isMove?: boolean;
}) {
  const highlight = useHighlight();
  const { end } = plan;
  // "End of turn" closes the plan with its value: no separate END_TURN step
  const last = plan.steps[plan.steps.length - 1];
  let steps =
    end.type === "end_turn" && last?.[1] === "END_TURN"
      ? plan.steps.slice(0, -1)
      : plan.steps;
  // Right under its move the plan starts with that move: the row above names it
  if (isMove && sameAction(steps[0], context.moveAction)) {
    steps = steps.slice(1);
  }
  return (
    <ol className="plan-steps">
      {steps.map((action, index) => (
        <li
          key={index}
          className="line-step"
          tabIndex={0}
          {...highlight(action, context.moveAction)}
        >
          <span
            className={`step-color ${action[0].toLowerCase()}`}
            title={action[0]}
          />
          {describeAction(context.gameState, action)}
        </li>
      ))}
      {end.type === "chance" && (
        <li className="plan-chance">
          {/* The move itself is the random event (no steps before it): its
              row already names it */}
          {!(isMove && plan.steps.length === 0) && (
            <div
              className="chance-header line-step"
              tabIndex={0}
              {...highlight(end.action, context.moveAction)}
            >
              🎲 {describeAction(context.gameState, end.action)}
            </div>
          )}
          <ul className="plan-outcomes">
            {end.outcomes.map((outcome, index) => (
              <Outcome
                key={index}
                outcome={outcome}
                chanceAction={end.action}
                open={index === 0}
                context={context}
              />
            ))}
          </ul>
        </li>
      )}
      {(end.type === "end_turn" || end.type === "terminal") && (
        <li className="plan-end">
          <span>{end.type === "terminal" ? "🏁 Game over" : "End of turn"}</span>
          {end.refined && (
            <Tooltip
              title="This end of the turn was searched further (MCTS)"
              arrow
            >
              <span className="refined">★ MCTS {end.sims}</span>
            </Tooltip>
          )}
          <WinValue win={end.win_probability} context={context} />
        </li>
      )}
      {end.type === "truncated" && (
        <li className="plan-end" title="Too many branches to show">
          …
        </li>
      )}
    </ol>
  );
}

function TurnMoveRow({
  move,
  rank,
  context,
}: {
  move: TurnMove;
  rank: number;
  context: Context;
}) {
  const highlight = useHighlight();
  const [open, setOpen] = useState(move.best);
  return (
    <li
      className={`move-row turn-move${move.excluded ? " excluded" : ""}`}
      {...highlight(move.action)}
    >
      <button
        type="button"
        className="turn-move-header"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        title={
          move.excluded
            ? "Not among the turn ends searched further: network value only"
            : undefined
        }
      >
        <span className="outcome-toggle">{open ? "▾" : "▸"}</span>
        <span className="move-rank">{rank}.</span>
        <span className="turn-move-action">
          {describeAction(context.gameState, move.action)}
        </span>
        <WinValue win={move.win_probability} context={context} />
      </button>
      {open && (
        <PlanView
          plan={move.plan}
          context={{ ...context, moveAction: move.action }}
          isMove
        />
      )}
    </li>
  );
}

/** Moves of a turn plan; the best one opened. */
export default function TurnPlanMoves({
  moves,
  player,
  colors,
  gameState,
}: {
  moves: TurnMove[];
  player: Color;
  colors: Color[];
  gameState: GameState;
}) {
  return (
    <ol className="moves turn-moves">
      {moves.map((move, index) => (
        <TurnMoveRow
          key={index}
          move={move}
          rank={index + 1}
          context={{ player, colors, gameState, moveAction: move.action }}
        />
      ))}
    </ol>
  );
}

function discardText(move: DiscardMove) {
  return Object.entries(move.discard)
    .map(([resource, count]) => `${count} ${RESULT_NAMES[resource] ?? resource}`)
    .join(", ");
}

/** Every way to discard, best first. */
export function DiscardSets({
  moves,
  player,
  colors,
}: {
  moves: DiscardMove[];
  player: Color;
  colors: Color[];
}) {
  const context = { player, colors } as Context;
  return (
    <ol className="moves discard-sets">
      {moves.map((move, index) => (
        <li key={index} className={`move-row discard-set${move.best ? " best" : ""}`}>
          <span className="move-rank">{index + 1}.</span>
          <span className="turn-move-action">Discard {discardText(move)}</span>
          <WinValue win={move.win_probability} context={context} />
        </li>
      ))}
    </ol>
  );
}
