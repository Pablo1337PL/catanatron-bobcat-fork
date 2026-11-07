import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import { afterEach, expect, test, vi } from "vitest";

import { store, type CatanState } from "../store";
import { makeGameState } from "../test/fixtures";
import type { GameState } from "../utils/api.types";
import LeftDrawer from "./LeftDrawer";

const liveState = makeGameState({
  state_index: 3,
  created_at: 1000,
  action_records: [
    [["RED", "ROLL", null], [3, 5]],
    [["RED", "PLAY_MONOPOLY", "WHEAT"], null],
    [["RED", "ROLL", null], [3, 4]],
  ] as GameState["action_records"],
  action_details: [
    {
      played_at: 1002.5,
      resource_changes: { RED: { WHEAT: 2, ORE: 1 } },
    },
    {
      played_at: 1010,
      resource_changes: { RED: { WHEAT: 3 }, BLUE: { WHEAT: -3 } },
    },
    { played_at: 1100, resource_changes: {} },
  ],
});

function renderDrawer(
  onSelectState?: (index: number) => void,
  viewedState: GameState | null = null
) {
  render(
    <ThemeProvider theme={createTheme()}>
      <store.Provider
        value={{
          state: { gameState: liveState, viewedState } as CatanState,
          dispatch: vi.fn(),
        }}
      >
        <LeftDrawer onSelectState={onSelectState} />
      </store.Provider>
    </ThemeProvider>
  );
  // The log is drawn by both the swipeable and the permanent drawer.
  return screen.getAllByRole("button", { name: /ROLLED A 8/ })[0]
    .parentElement as HTMLElement;
}

afterEach(() => {
  cleanup();
});

test("the log shows what each roll paid, the monopoly and the move times", () => {
  const log = within(renderDrawer());

  const roll = log.getByRole("button", { name: /ROLLED A 8/ });
  expect(within(roll).getByText("+2 WHEAT, +1 ORE")).toBeTruthy();
  expect(within(roll).getByText("nothing")).toBeTruthy(); // BLUE got nothing
  expect(within(roll).getByText("2.5 s")).toBeTruthy();

  expect(log.getByText("BOT MONOPOLIZED WHEAT (TOOK 3)")).toBeTruthy();
  expect(log.getByText("7.5 s")).toBeTruthy();
  expect(log.getByText("1:30")).toBeTruthy();

  // A seven pays nothing, so it has no payout line.
  const seven = log.getByRole("button", { name: /ROLLED A 7/ });
  expect(within(seven).queryByText("nothing")).toBeNull();
});

test("clicking a move shows the board after it", async () => {
  const onSelectState = vi.fn();
  const log = within(renderDrawer(onSelectState));

  await userEvent.click(log.getByText("BOT MONOPOLIZED WHEAT (TOOK 3)"));

  expect(onSelectState).toHaveBeenCalledWith(2);
});

test("the viewed move is marked", () => {
  const log = within(
    renderDrawer(vi.fn(), makeGameState({ state_index: 1 }))
  );
  const viewed = log
    .getAllByRole("button")
    .filter((entry) => entry.classList.contains("viewed"));
  expect(viewed).toHaveLength(1);
  expect(viewed[0].textContent).toMatch(/ROLLED A 8/);
});

test("without a handler the log is not clickable", () => {
  const log = within(renderDrawer());
  for (const entry of log.getAllByRole("button")) {
    expect((entry as HTMLButtonElement).disabled).toBe(true);
  }
});
