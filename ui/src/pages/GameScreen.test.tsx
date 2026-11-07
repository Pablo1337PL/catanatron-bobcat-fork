import { Fragment, StrictMode, useContext } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { StateProvider, store } from "../store";
import type { GameState } from "../utils/api.types";
import { getState, postAction, setPerspective } from "../utils/apiClient";
import { dispatchSnackbar } from "../components/Snackbar";
import { makeGameState } from "../test/fixtures";
import GameScreen from "./GameScreen";

const snackbar = vi.hoisted(() => ({
  enqueueSnackbar: vi.fn(),
  closeSnackbar: vi.fn(),
}));

vi.mock("../utils/apiClient", () => ({
  getState: vi.fn(),
  postAction: vi.fn(),
  getAnalysis: vi.fn(),
  setPerspective: vi.fn(),
}));
vi.mock("../components/Snackbar", () => ({
  dispatchSnackbar: vi.fn(),
}));
vi.mock("notistack", () => ({
  useSnackbar: () => snackbar,
}));
vi.mock("./ZoomableBoard", () => ({
  default: () => <div data-testid="board">Board</div>,
}));

const theme = createTheme();
const baseState = makeGameState();

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function StateIndexProbe() {
  const { state } = useContext(store);
  return <output data-testid="state-index">{state.gameState?.state_index}</output>;
}

function renderGameScreen({
  initialEntry = "/games/game-123",
  routePath = "/games/:gameId",
  replayMode = false,
  strictMode = false,
}: {
  initialEntry?: string;
  routePath?: string;
  replayMode?: boolean;
  strictMode?: boolean;
} = {}) {
  const Wrapper = strictMode ? StrictMode : Fragment;
  return render(
    <Wrapper>
      <ThemeProvider theme={theme}>
        <StateProvider>
          <MemoryRouter initialEntries={[initialEntry]}>
            <Routes>
              <Route
                path={routePath}
                element={<GameScreen replayMode={replayMode} />}
              />
            </Routes>
          </MemoryRouter>
          <StateIndexProbe />
        </StateProvider>
      </ThemeProvider>
    </Wrapper>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test("loads a persisted API state into the real gameplay controls", async () => {
  vi.mocked(getState).mockResolvedValue(baseState);

  renderGameScreen();

  expect(await screen.findByTestId("board")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "ROLL" })).toBeEnabled();
  expect(screen.getAllByTitle("Victory Points").length).toBeGreaterThan(0);
  expect(screen.getByTestId("state-index")).toHaveTextContent("12");
  expect(getState).toHaveBeenCalledWith("game-123", undefined);
  // Spectator by default: every request carries the perspective, so it is set
  // before the first fetch rather than passed at each call site.
  expect(setPerspective).toHaveBeenCalledWith(null);
  expect(postAction).not.toHaveBeenCalled();
});

test("advances a persisted bot turn and publishes the returned state", async () => {
  const botTurn = makeGameState({ current_color: "RED" });
  const humanTurn: GameState = makeGameState({
    state_index: 13,
    action_records: [
      [["RED", "END_TURN", null], null],
    ] as GameState["action_records"],
  });
  const actionResponse = deferred<GameState>();
  vi.mocked(getState).mockResolvedValue(botTurn);
  vi.mocked(postAction).mockReturnValue(actionResponse.promise);

  renderGameScreen();

  expect(await screen.findByTestId("board")).toBeInTheDocument();
  expect(postAction).toHaveBeenCalledWith("game-123");

  vi.useFakeTimers();
  await act(async () => {
    actionResponse.resolve(humanTurn);
    await actionResponse.promise;
  });

  await act(async () => {
    await vi.runAllTimersAsync();
  });

  expect(screen.getByTestId("state-index")).toHaveTextContent("13");
  expect(screen.getByRole("button", { name: "ROLL" })).toBeEnabled();
  expect(dispatchSnackbar).toHaveBeenCalledOnce();
});

test("asks the server for one bot move at a time", async () => {
  // StrictMode loads the game twice, so the state is set again while the bot
  // thinks; a second request would have the server play the move twice.
  const loads = [deferred<GameState>(), deferred<GameState>()];
  vi.mocked(getState)
    .mockReturnValueOnce(loads[0].promise)
    .mockReturnValueOnce(loads[1].promise);
  vi.mocked(postAction).mockReturnValue(deferred<GameState>().promise);

  renderGameScreen({ strictMode: true });

  for (const load of loads) {
    await act(async () => {
      load.resolve(makeGameState({ current_color: "RED" }));
      await load.promise;
    });
  }
  expect(getState).toHaveBeenCalledTimes(2);
  expect(postAction).toHaveBeenCalledOnce();
});

test("loads a historical state without advancing bots in replay mode", async () => {
  vi.mocked(getState).mockResolvedValue(makeGameState({ state_index: 7 }));

  renderGameScreen({
    initialEntry: "/games/game-123/states/7",
    routePath: "/games/:gameId/states/:stateIndex",
    replayMode: true,
  });

  expect(await screen.findByTestId("board")).toBeInTheDocument();
  expect(screen.getByTestId("state-index")).toHaveTextContent("7");
  expect(getState).toHaveBeenCalledWith("game-123", "7");
  expect(postAction).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "ROLL" })).not.toBeInTheDocument();
});

test("a move picked in the log shows its board until Back to game", async () => {
  const live = makeGameState({
    state_index: 2,
    action_records: [
      [["BLUE", "ROLL", null], [2, 4]],
      [["BLUE", "END_TURN", null], null],
    ] as GameState["action_records"],
    action_details: [
      { played_at: 10, resource_changes: {} },
      { played_at: 12, resource_changes: null },
    ],
  });
  const past = makeGameState({
    state_index: 1,
    action_records: live.action_records.slice(0, 1),
    action_details: live.action_details?.slice(0, 1),
  });
  vi.mocked(getState).mockImplementation(async (_gameId, index) =>
    index === 1 ? past : live
  );

  renderGameScreen();
  expect(await screen.findByTestId("board")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "ROLL" })).toBeEnabled();

  await act(async () => {
    screen.getAllByRole("button", { name: /ROLLED A 6/ })[0].click();
  });

  expect(getState).toHaveBeenCalledWith("game-123", 1);
  expect(await screen.findByText("After move 1 of 2")).toBeInTheDocument();
  // The live game stays in the store, and the board cannot be played on.
  expect(screen.getByTestId("state-index")).toHaveTextContent("2");
  expect(screen.queryByRole("button", { name: "ROLL" })).not.toBeInTheDocument();

  await act(async () => {
    screen.getByRole("button", { name: "Back to game" }).click();
  });

  expect(screen.queryByText("After move 1 of 2")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "ROLL" })).toBeEnabled();
});
