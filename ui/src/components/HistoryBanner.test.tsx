import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { store, type CatanState } from "../store";
import { makeGameState } from "../test/fixtures";
import type { GameActionRecord, GameState } from "../utils/api.types";
import HistoryBanner from "./HistoryBanner";

afterEach(cleanup);

const RED_END = ["RED", "END_TURN", null] as const;
const BLUE_END = ["BLUE", "END_TURN", null] as const;

function viewed(index: number): GameState {
  return makeGameState({
    state_index: index,
    action_records: [
      [[...RED_END], null],
      [[...BLUE_END], null],
    ] as unknown as GameActionRecord[],
  });
}

test("the highlight follows the viewed move and goes when the banner does", () => {
  const dispatch = vi.fn();
  const ui = (state: GameState) => (
    <store.Provider value={{ state: {} as CatanState, dispatch }}>
      <HistoryBanner viewedState={state} liveState={viewed(2)} onView={() => undefined} />
    </store.Provider>
  );
  const { rerender, unmount } = render(ui(viewed(1)));
  const highlights = () =>
    dispatch.mock.calls.map(([a]) => a).filter((a) => a.type === "SET_HIGHLIGHT").map((a) => a.data);

  fireEvent.mouseOver(screen.getByText(/ENDED TURN/));
  expect(highlights()).toEqual([[...RED_END]]);

  rerender(ui(viewed(2))); // → while pointing at the move
  expect(highlights()).toEqual([[...RED_END], [...BLUE_END]]);

  unmount(); // Esc
  expect(highlights()).toEqual([[...RED_END], [...BLUE_END], null]);
});
