import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { store, type CatanState } from "../store";
import { makeGameState } from "../test/fixtures";
import type { GameState } from "../utils/api.types";
import { type Analysis, getAnalysis } from "../utils/apiClient";
import AnalysisBox from "./AnalysisBox";

vi.mock("../utils/apiClient", () => ({
  getAnalysis: vi.fn(),
}));

const BLUE_ROLL = ["BLUE", "ROLL", null] as const;
const BLUE_END = ["BLUE", "END_TURN", null] as const;
const RED_ROLL = ["RED", "ROLL", null] as const;

function makeAnalysis(overrides: Partial<Analysis> = {}): Analysis {
  return {
    engine: "Bobcat az_v1_gen14 · MCTS 1000",
    player: "BLUE",
    win_probability: { RED: 0.3, BLUE: 0.7 },
    simulations: 1000,
    seconds: 1.2,
    state_index: 12,
    moves: [
      {
        action: [...BLUE_ROLL],
        probability: 0.8,
        prior: 0.6,
        visits: 800,
        win_probability: { RED: 0.28, BLUE: 0.72 },
        line: [[...BLUE_ROLL]],
        line_end: "chance",
      },
      {
        action: [...BLUE_END],
        probability: 0.2,
        prior: 0.4,
        visits: 200,
        win_probability: { RED: 0.4, BLUE: 0.6 },
        line: [[...BLUE_END], [...RED_ROLL]],
        line_end: "chance",
      },
    ],
    ...overrides,
  };
}

function renderBox(gameState: GameState, dispatch = vi.fn()) {
  const ui = (state: GameState) => (
    <store.Provider
      value={{
        state: { gameState: state } as CatanState,
        dispatch,
      }}
    >
      <MemoryRouter initialEntries={["/games/game-123"]}>
        <Routes>
          <Route
            path="/games/:gameId"
            element={<AnalysisBox stateIndex="latest" />}
          />
        </Routes>
      </MemoryRouter>
    </store.Provider>
  );
  const result = render(ui(gameState));
  return { rerender: (state: GameState) => result.rerender(ui(state)) };
}

beforeEach(() => {
  vi.mocked(getAnalysis).mockReset();
});

afterEach(() => {
  cleanup();
});

test("shows the evaluation bar, the moves and their lines", async () => {
  vi.mocked(getAnalysis).mockResolvedValue(makeAnalysis());
  renderBox(makeGameState());

  await userEvent.click(screen.getByRole("button", { name: /analyze/i }));

  expect(getAnalysis).toHaveBeenCalledWith("game-123", "latest");
  expect(
    await screen.findByRole("img", { name: "RED 30.0%, BLUE 70.0%" })
  ).toBeTruthy();
  expect(screen.getByText("Bobcat az_v1_gen14 · MCTS 1000")).toBeTruthy();

  const rows = screen.getAllByRole("listitem").filter((item) =>
    item.classList.contains("move-row")
  );
  expect(rows).toHaveLength(2);
  expect(within(rows[0]).getByText("80.0%")).toBeTruthy();
  expect(within(rows[0]).getByText("72.0%")).toBeTruthy();
  expect(within(rows[1]).getByText("End turn")).toBeTruthy();
  expect(within(rows[1]).getByText("Roll")).toBeTruthy();
  expect(within(rows[1]).getByTitle(/random event/)).toBeTruthy();
});

test("lists the top moves until asked for all", async () => {
  const move = makeAnalysis().moves[1];
  vi.mocked(getAnalysis).mockResolvedValue(
    makeAnalysis({ moves: Array.from({ length: 9 }, () => move) })
  );
  renderBox(makeGameState());

  await userEvent.click(screen.getByRole("button", { name: /analyze/i }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Show all 9 moves" })
  );

  expect(screen.getAllByText("End turn")).toHaveLength(9);
});

test("marks the analysis stale once the position changes", async () => {
  vi.mocked(getAnalysis).mockResolvedValue(makeAnalysis());
  const { rerender } = renderBox(makeGameState());
  await userEvent.click(screen.getByRole("button", { name: /analyze/i }));
  await screen.findByText("Bobcat az_v1_gen14 · MCTS 1000");
  expect(screen.queryByText(/position has changed/)).toBeNull();

  rerender(makeGameState({ state_index: 13 }));

  expect(screen.getByText(/position has changed/)).toBeTruthy();
});

test("shows the server's error", async () => {
  vi.mocked(getAnalysis).mockRejectedValue(
    new Error("This server has no analysis engine.")
  );
  renderBox(makeGameState());

  await userEvent.click(screen.getByRole("button", { name: /analyze/i }));

  expect(
    await screen.findByText("This server has no analysis engine.")
  ).toBeTruthy();
});

test("cannot analyze a finished game", () => {
  renderBox(makeGameState({ winning_color: "RED" }));
  expect(
    (screen.getByRole("button", { name: /analyze/i }) as HTMLButtonElement)
      .disabled
  ).toBe(true);
});

test("pointing at a move or a step of its line lights it up on the board", async () => {
  vi.mocked(getAnalysis).mockResolvedValue(makeAnalysis());
  const dispatch = vi.fn();
  renderBox(makeGameState(), dispatch);
  await userEvent.click(screen.getByRole("button", { name: /analyze/i }));
  const rows = (await screen.findAllByRole("listitem")).filter((item) =>
    item.classList.contains("move-row")
  );
  const highlights = () =>
    dispatch.mock.calls
      .map(([action]) => action)
      .filter((action) => action.type === "SET_HIGHLIGHT")
      .map((action) => action.data);

  const step = within(rows[1]).getByText("Roll");
  const last = () => highlights()[highlights().length - 1];

  await userEvent.hover(rows[1]);
  expect(last()).toEqual([...BLUE_END]);
  await userEvent.hover(step);
  expect(last()).toEqual([...RED_ROLL]);
  // Back from the step onto its row, then off the row
  fireEvent.mouseOut(step, { relatedTarget: rows[1] });
  expect(last()).toEqual([...BLUE_END]);
  fireEvent.mouseOut(rows[1], { relatedTarget: document.body });
  expect(last()).toBeNull();

  // Keyboard: focusing a step lights the step, not its row
  dispatch.mockClear();
  within(rows[1]).getByText("Roll").focus();
  expect(highlights()).toEqual([[...RED_ROLL]]);
});

test("shows the predicted cards and where a line assumes a hidden hand", async () => {
  const analysis = makeAnalysis({
    opponent_cards: [
      {
        color: "RED",
        count: 2,
        expected: {
          KNIGHT: 1.1,
          YEAR_OF_PLENTY: 0.2,
          MONOPOLY: 0.2,
          ROAD_BUILDING: 0.1,
          VICTORY_POINT: 0.4,
        },
        at_least_one: {
          KNIGHT: 0.74,
          YEAR_OF_PLENTY: 0.15,
          MONOPOLY: 0.15,
          ROAD_BUILDING: 0.08,
          VICTORY_POINT: 0.33,
        },
        likely_hand: ["KNIGHT", "VICTORY_POINT"],
        likely_hand_probability: 0.31,
      },
    ],
  });
  analysis.moves[1] = {
    ...analysis.moves[1],
    line_assumptions: [
      { step: 1, color: "RED", hand: ["KNIGHT", "VICTORY_POINT"], probability: 0.31 },
    ],
  };
  vi.mocked(getAnalysis).mockResolvedValue(analysis);
  renderBox(makeGameState());

  await userEvent.click(screen.getByRole("button", { name: /analyze/i }));

  expect(await screen.findByText(/Predicted cards/)).toBeTruthy();
  expect(screen.getByText("1.1 · 74.0%")).toBeTruthy();
  expect(screen.getByText(/Most likely: Knight, Victory Point \(31.0%\)/)).toBeTruthy();
  const marker = screen.getByLabelText(
    "Assuming RED holds Knight, Victory Point (31.0%)"
  );
  // The marker sits right before the step it is about
  expect(marker.nextElementSibling).toHaveTextContent("Roll");
});

test("says when the moves are averaged over hidden hands", async () => {
  vi.mocked(getAnalysis).mockResolvedValue(makeAnalysis({ averaged_over_hands: true }));
  renderBox(makeGameState());

  await userEvent.click(screen.getByRole("button", { name: /analyze/i }));

  expect(await screen.findByText(/Averaged over the hands Bobcat expects/)).toBeTruthy();
});
